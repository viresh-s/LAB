import asyncio
import json
import base64
import logging
import io
import audioop
try:
    import webrtcvad
    _HAS_VAD = True
except ImportError:
    _HAS_VAD = False
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import websockets
from app.core.config import settings
from app.api.webhooks import _load_session, _save_session
from app.services.speech import SpeechService
from app.graph.builder import create_voice_graph
from app.graph.state import PatientData

log = logging.getLogger(__name__)
router = APIRouter()
speech = SpeechService()

# Initialize VAD (Aggressiveness 3 is highest) — optional
vad = webrtcvad.Vad(3) if _HAS_VAD else None
if not _HAS_VAD:
    log.warning("webrtcvad not installed — barge-in detection disabled. Install with: pip install webrtcvad")

async def transcode_to_mulaw(audio_bytes: bytes) -> bytes:
    import asyncio
    import subprocess
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    cmd = [
        ffmpeg_exe,
        "-i", "pipe:0",
        "-f", "mulaw",
        "-ar", "8000",
        "-ac", "1",
        "pipe:1"
    ]
    
    def run_ffmpeg():
        return subprocess.run(
            cmd,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
    result = await asyncio.to_thread(run_ffmpeg)
    if result.returncode != 0:
        log.error(f"ffmpeg error: {result.stderr.decode()}")
        return b""
    return result.stdout

@router.websocket("/stream")
async def exotel_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket connected for Exotel Stream")
    
    deepgram_url = "wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1&model=nova-2&language=en-IN&endpointing=800&interim_results=true&keepalive=true"
    
    call_sid = None
    stream_sid = None
    
    # Shared state for Barge-in
    state_flags = {
        "is_bot_speaking": False,
        "vad_buffer": bytearray()
    }
    
    try:
        async with websockets.connect(
            deepgram_url,
            additional_headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}
        ) as dg_socket:
            
            async def sender():
                nonlocal call_sid, stream_sid
                try:
                    while True:
                        msg = await websocket.receive_text()
                        data = json.loads(msg)
                        if data["event"] == "start":
                            call_sid = data["start"]["callSid"]
                            stream_sid = data["start"]["streamSid"]
                            log.info(f"Stream started: CallSid {call_sid}, StreamSid {stream_sid}")
                            
                            # Push initial greeting in English
                            state_flags["is_bot_speaking"] = True
                            greeting_en = "Hello! Welcome to the lab. How can I help you today?"
                            mp3_bytes = await speech.text_to_speech(greeting_en)
                            if mp3_bytes:
                                mulaw_bytes = await transcode_to_mulaw(mp3_bytes)
                                if mulaw_bytes:
                                    for i in range(0, len(mulaw_bytes), 4000):
                                        chunk = mulaw_bytes[i:i+4000]
                                        payload = base64.b64encode(chunk).decode('ascii')
                                        await websocket.send_json({
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {"payload": payload}
                                        })
                            state_flags["is_bot_speaking"] = False
                            
                        elif data["event"] == "media":
                            audio_data = base64.b64decode(data["media"]["payload"])
                            
                            # VAD Logic for Barge-in (only if webrtcvad is installed)
                            if vad is not None:
                                try:
                                    pcm_data = audioop.ulaw2lin(audio_data, 2)
                                    state_flags["vad_buffer"].extend(pcm_data)
                                    
                                    # 20ms frames at 8000Hz = 160 samples = 320 bytes
                                    FRAME_SIZE = 320
                                    while len(state_flags["vad_buffer"]) >= FRAME_SIZE:
                                        frame = bytes(state_flags["vad_buffer"][:FRAME_SIZE])
                                        state_flags["vad_buffer"] = state_flags["vad_buffer"][FRAME_SIZE:]
                                        
                                        if vad.is_speech(frame, 8000):
                                            if state_flags["is_bot_speaking"]:
                                                log.info("BARGE-IN DETECTED: Sending clear event")
                                                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                                                state_flags["is_bot_speaking"] = False
                                except Exception as e:
                                    log.error(f"VAD Error: {e}")

                            # Forward to Deepgram
                            await dg_socket.send(audio_data)
                            
                        elif data["event"] == "stop":
                            log.info(f"Stream stopped: {stream_sid}")
                            break
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    log.error(f"WebSocket Sender error: {e}")
                finally:
                    try:
                        await dg_socket.send(b'') # Close deepgram
                    except:
                        pass
            
            async def receiver():
                graph = create_voice_graph()
                try:
                    while True:
                        resp = await dg_socket.recv()
                        data = json.loads(resp)
                        
                        if data.get("is_final") and data.get("speech_final"):
                            alternatives = data.get("channel", {}).get("alternatives", [])
                            if not alternatives:
                                continue
                            transcript = alternatives[0].get("transcript", "").strip()
                            
                            if transcript:
                                log.info(f"User: '{transcript}'")
                                
                                # Play filler audio immediately before calling graph
                                state_flags["is_bot_speaking"] = True
                                filler_msg = "Let me check..."
                                filler_mp3 = await speech.text_to_speech(filler_msg)
                                if filler_mp3:
                                    filler_mulaw = await transcode_to_mulaw(filler_mp3)
                                    if filler_mulaw:
                                        chunk = filler_mulaw[:4000]
                                        payload = base64.b64encode(chunk).decode('ascii')
                                        await websocket.send_json({
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {"payload": payload}
                                        })
                                
                                session = _load_session(call_sid) if call_sid else {}
                                patient_data_obj = PatientData(**session.get("patient_data", {}))
                                
                                # Run Graph (LLM Call)
                                state = await graph.ainvoke({
                                    "event_type": "voice_call",
                                    "lab_id": settings.DEFAULT_LAB_ID,
                                    "patient_id": None,
                                    "user_text": transcript,
                                    "agent_speech": None,
                                    "patient_data": patient_data_obj,
                                    "missing_fields": session.get("missing_fields", []),
                                    "dispatch_success": False
                                })
                                
                                agent_speech_en = state.get("agent_speech", "")
                                if agent_speech_en:
                                    log.info(f"Agent (EN): '{agent_speech_en}'")
                                    
                                    # TTS -> MP3 (Skipping Translation for Test)
                                    mp3_bytes = await speech.text_to_speech(agent_speech_en)
                                    if mp3_bytes:
                                        mulaw_bytes = await transcode_to_mulaw(mp3_bytes)
                                        if mulaw_bytes:
                                            chunk_size = 4000
                                            for i in range(0, len(mulaw_bytes), chunk_size):
                                                chunk = mulaw_bytes[i:i+chunk_size]
                                                payload = base64.b64encode(chunk).decode('ascii')
                                                await websocket.send_json({
                                                    "event": "media",
                                                    "streamSid": stream_sid,
                                                    "media": {"payload": payload}
                                                })
                                    
                                    # Finished speaking main response
                                    state_flags["is_bot_speaking"] = False
                                            
                                # Save state
                                if call_sid:
                                    _save_session(
                                        call_sid, 
                                        settings.DEFAULT_LAB_ID,
                                        state["patient_data"].dict(),
                                        state["missing_fields"]
                                    )
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    log.error(f"Deepgram Receiver error: {e}")

            await asyncio.gather(sender(), receiver())
            
    except Exception as e:
        log.error(f"Deepgram WebSocket connection error: {e}")
