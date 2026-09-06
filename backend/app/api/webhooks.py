"""
Exotel Voice Webhook Handlers — Serverless-safe, Multi-tenant.

STT:  Deepgram Nova-2  (Kannada audio → Kannada text)
NMT:  OpenAI GPT-4o-mini  (Kannada ↔ English translation)
TTS:  OpenAI tts-1  (Kannada text → MP3 audio)

Flow per turn:
  /exotel/voice      → greet (OpenAI TTS) + <Connect><Stream>
  /exotel/recording  → Deepgram STT → GPT translate → LangGraph
                     → GPT translate → OpenAI TTS → <Play> + <Record> (or Hangup)
  /exotel/status     → cleanup session (logging)
"""
import uuid
import logging
import httpx

from fastapi import APIRouter, Form, Response, Request, BackgroundTasks
from typing import Optional

from app.db.supabase import supabase
from app.core.config import settings
from app.services.speech import SpeechService
from app.graph.builder import create_voice_graph
from app.graph.state import PatientData

log = logging.getLogger(__name__)
router = APIRouter()
speech = SpeechService()

# ── English greeting & fallback texts ────────────────────────────────────────
_GREETING_EN = "Hi! Welcome to Apollo Labs. How can I help you today?"
_REPEAT_EN    = "I'm sorry, I didn't catch that. Could you repeat?"
_GOODBYE_EN   = "Thank you! Your booking is confirmed. Our collector will contact you shortly on WhatsApp."


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_lab_by_exotel_number(exotel_number: str) -> str:
    """Resolve lab_id from the dialled Exotel number. Falls back to DEFAULT_LAB_ID."""
    if supabase and exotel_number:
        try:
            res = (
                supabase.table("labs")
                .select("id")
                .eq("exotel_number", exotel_number)
                .single()
                .execute()
            )
            if res.data:
                return res.data["id"]
        except Exception as e:
            log.warning("[webhook] Lab lookup failed for %s: %s", exotel_number, e)
    return settings.DEFAULT_LAB_ID


def _load_session(call_sid: str) -> dict:
    if not supabase:
        return {}
    try:
        res = (
            supabase.table("call_sessions")
            .select("*")
            .eq("call_sid", call_sid)
            .single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def _save_session(call_sid: str, lab_id: str, patient_data: dict, missing_fields: list[str]) -> None:
    if not supabase:
        return
    try:
        supabase.table("call_sessions").upsert(
            {
                "call_sid":       call_sid,
                "lab_id":         lab_id,
                "patient_data":   patient_data,
                "missing_fields": missing_fields,
            },
            on_conflict="call_sid",
        ).execute()
    except Exception as e:
        log.error("[webhook] Session save error: %s", e)


async def _tts_to_storage(text: str) -> Optional[str]:
    """
    Generate MP3 via OpenAI TTS, upload to Supabase Storage, return public URL.
    Returns None if TTS or upload fails — caller should fall back to Exotel <Response><Say>.
    """
    audio_bytes = await speech.text_to_speech(text)
    if not audio_bytes or not supabase:
        return None
    try:
        file_path = f"{uuid.uuid4()}.mp3"
        supabase.storage.from_("tts-audio").upload(
            file_path,
            audio_bytes,
            {"content-type": "audio/mpeg"},
        )
        url = f"{settings.SUPABASE_URL}/storage/v1/object/public/tts-audio/{file_path}"
        log.info("[webhook] TTS uploaded → %s", url)
        return url
    except Exception as e:
        log.error("[webhook] TTS upload error: %s", e)
        return None


def _build_record_twiml(action_url: str, play_url: Optional[str], say_text: Optional[str]) -> str:
    """
    Build XML that plays / says a prompt then opens <Record> for the caller's response.
    """
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']
    if play_url:
        xml.append(f'<Play>{play_url}</Play>')
    elif say_text:
        xml.append(f'<Say>{say_text}</Say>')
    
    xml.append(f'<Record action="{action_url}" method="POST" maxLength="20" playBeep="false" timeout="1" finishOnKey="#"/>')
    xml.append(f'<Redirect method="POST">{action_url}</Redirect>')
    xml.append('</Response>')
    return "\\n".join(xml)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 1 — Incoming call: greet + start recording
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/exotel/voice")
async def exotel_voice(request: Request, CallSid: str = Form(None), To: str = Form(None), From: str = Form(None)):
    base = str(request.base_url).rstrip("/")
    action_url = f"{base}/webhooks/exotel/recording"
    
    play_url = await _tts_to_storage(_GREETING_EN)
    xml_content = _build_record_twiml(action_url=action_url, play_url=play_url, say_text=_GREETING_EN)
    return Response(content=xml_content, media_type="application/xml")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 2 — Recording ready: Deepgram STT → GPT NMT → LangGraph → TTS → reply
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/exotel/recording")
async def exotel_recording(
    request: Request,
    CallSid:       str = Form(""),
    RecordingUrl:  str = Form(""),
    RecordingSid:  str = Form(""),
):
    log.info("[recording] CallSid=%s RecordingUrl=%s", CallSid, RecordingUrl)

    base = str(request.base_url).rstrip("/")
    action_url = f"{base}/webhooks/exotel/recording"

    # ── 1. Download Exotel recording ─────────────────────────────────────────
    # Exotel appends .mp3 or .wav; always request MP3
    audio_url = f"{RecordingUrl}.mp3"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            audio_resp = await client.get(
                audio_url,
                auth=(settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN),
            )
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content
    except Exception as e:
        log.error("[recording] Could not download recording: %s", e)
        audio_bytes = b""

    # ── 2. Deepgram STT — English ─────────────────────────────────────────────
    speech_en = ""
    if audio_bytes:
        speech_en = await speech.speech_to_text(audio_bytes, lang="en-IN", content_type="audio/mpeg")

    if not speech_en.strip():
        # Nothing heard — re-prompt
        play_url = await _tts_to_storage(_REPEAT_EN)
        twiml = _build_record_twiml(action_url=action_url, play_url=play_url, say_text=_REPEAT_EN)
        return Response(content=twiml, media_type="application/xml")

    # ── 4. LangGraph voice agent ──────────────────────────────────────────────
    session = _load_session(CallSid)
    lab_id  = session.get("lab_id") or settings.DEFAULT_LAB_ID
    try:
        existing_patient = PatientData(**(session.get("patient_data") or {}))
    except Exception:
        existing_patient = PatientData()

    graph = create_voice_graph()
    result = await graph.ainvoke({
        "event_type":     "voice_call",
        "lab_id":         lab_id,
        "patient_id":     None,
        "user_text":      speech_en,
        "agent_speech":   None,
        "patient_data":   existing_patient,
        "missing_fields": [],
        "dispatch_success": False,
    })

    agent_speech_en: str     = result.get("agent_speech") or "Please repeat that."
    missing_fields: list     = result.get("missing_fields", [])
    new_patient: PatientData = result.get("patient_data") or PatientData()
    booking_done: bool       = (len(missing_fields) == 0)

    # ── 5. Persist session ────────────────────────────────────────────────────
    _save_session(
        call_sid=CallSid,
        lab_id=lab_id,
        patient_data=new_patient.model_dump(),
        missing_fields=missing_fields,
    )

    # ── 6. OpenAI TTS → Supabase Storage ─────────────────────────────────────
    tts_url = await _tts_to_storage(agent_speech_en)

    # ── 7. Build XML response ───────────────────────────────────────────────
    if booking_done:
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']
        if tts_url:
            xml.append(f'<Play>{tts_url}</Play>')
        else:
            xml.append(f'<Say>{agent_speech_en}</Say>')
        xml.append('<Hangup/>')
        xml.append('</Response>')
        return Response(content="\\n".join(xml), media_type="application/xml")
    else:
        twiml = _build_record_twiml(
            action_url=action_url,
            play_url=tts_url,
            say_text=agent_speech_en if not tts_url else None,
        )
        return Response(content=twiml, media_type="application/xml")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 3 — Call status (cleanup)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/exotel/status")
async def exotel_status(
    CallSid:      str = Form(""),
    CallStatus:   str = Form(""),
    CallDuration: str = Form(""),
    To:           str = Form(""),
    From:         str = Form(""),
):
    log.info("[status] CallSid=%s Status=%s Duration=%ss", CallSid, CallStatus, CallDuration)
    if supabase and CallStatus in ("completed", "failed", "canceled"):
        try:
            # 1. Get lab_id to log costs
            session = _load_session(CallSid)
            lab_id = session.get("lab_id")
            
            if lab_id and CallDuration and CallDuration.isdigit():
                duration = int(CallDuration)
                if duration > 0:
                    from app.services.usage import track_exotel_cost, track_stt_cost
                    # Track Exotel Voice Cost
                    track_exotel_cost(lab_id, duration)
                    # For streams, STT is active for the entire duration of the call
                    track_stt_cost(lab_id, float(duration))
            
            # 2. Cleanup session
            supabase.table("call_sessions").delete().eq("call_sid", CallSid).execute()
        except Exception as e:
            log.warning("[status] Session cleanup error: %s", e)
    return {"status": "logged"}


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Incoming — Receptionist UPDATE Commands
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Strip whatsapp: prefix and + sign for comparison."""
    return phone.replace("whatsapp:", "").replace("+", "").strip()


async def _send_wa_reply(
    to_raw: str, text: str,
    lab_phone_number_id: Optional[str] = None,
    lab_access_token: Optional[str] = None,
) -> None:
    """Send a WhatsApp text reply using per-lab credentials when available."""
    from app.services.meta_wa import whatsapp_service
    to = _normalize_phone(to_raw)
    await whatsapp_service.send_text_message(
        to=to, text=text,
        lab_phone_number_id=lab_phone_number_id,
        lab_access_token=lab_access_token,
    )


async def _alert_no_whatsapp(
    receptionist_phone: str, patient_name: str, patient_id: str, patient_phone: str,
    lab_phone_number_id: Optional[str] = None,
    lab_access_token: Optional[str] = None,
) -> None:
    """
    Alert the lab receptionist that a patient doesn't have WhatsApp.
    Called whenever a Meta send fails with a no-WhatsApp error.
    """
    from app.services.meta_wa import whatsapp_service
    rp = _normalize_phone(receptionist_phone)
    msg = (
        f"⚠️ *No WhatsApp Alert*\n\n"
        f"Patient *{patient_name}* (ID: `{patient_id}`) "
        f"does not have WhatsApp on number *{patient_phone}*.\n\n"
        f"Please contact them directly or update their number."
    )
    await whatsapp_service.send_text_message(
        to=rp, text=msg,
        lab_phone_number_id=lab_phone_number_id,
        lab_access_token=lab_access_token,
    )


@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """
    Handle Meta's one-time webhook verification challenge.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return {"error": "Invalid token"}


async def _process_whatsapp_payload(payload: dict):
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]["value"]
        
        # Sometimes Meta sends status updates (read/delivered), skip those
        if "messages" not in changes:
            return
            
        message_obj = changes["messages"][0]
        
        to_number = _normalize_phone(changes["metadata"]["display_phone_number"])
        from_number = _normalize_phone(message_obj["from"])
        wa_phone_id = changes["metadata"].get("phone_number_id")
        
        # We only handle text messages for now
        if message_obj["type"] != "text":
            return
            
        body = message_obj["text"]["body"]
        
    except (KeyError, IndexError):
        return

    log.info("[whatsapp] Incoming Meta: From=%s To=%s Body=%s", from_number, to_number, body[:100])

    if not supabase:
        return

    # ── 1. Resolve lab from incoming Meta number ─────────────────────────
    try:
        lab = None
        # Try finding lab by whatsapp_phone_number_id first (most accurate for Meta webhooks)
        if wa_phone_id:
            lab_res = supabase.table("labs").select("id, business_name, services, receptionist_phone, collector_phone, whatsapp_phone_number_id, whatsapp_access_token").eq("whatsapp_phone_number_id", str(wa_phone_id)).execute()
            if lab_res.data:
                lab = lab_res.data[0]
                
        # Fallback to exotel_number if not found
        if not lab:
            lab_res = supabase.table("labs").select("id, business_name, services, receptionist_phone, collector_phone, whatsapp_phone_number_id, whatsapp_access_token").like("exotel_number", f"%{to_number[-10:]}%").execute()
            if lab_res.data:
                lab = lab_res.data[0]
                
    except Exception as e:
        log.warning("[whatsapp] Could not resolve lab from number %s or phone ID %s: %s", to_number, wa_phone_id, e)
        return

    if not lab:
        log.warning("[whatsapp] No lab found for Meta number: %s", to_number)
        return

    lab_id = lab["id"]
    receptionist_phone = _normalize_phone(lab.get("receptionist_phone") or "")
    collector_phone = _normalize_phone(lab.get("collector_phone") or "")
    wa_phone_id = lab.get("whatsapp_phone_number_id") or None
    wa_token = lab.get("whatsapp_access_token") or None
    services = lab.get("services") or []
    business_name = lab.get("business_name") or "LabSaaS"

    # ── 2. Authorize: only receptionist or collector can send messages ───
    sender_role = None
    if receptionist_phone and from_number[-10:] == receptionist_phone[-10:]:
        sender_role = "receptionist"
    elif collector_phone and from_number[-10:] == collector_phone[-10:]:
        sender_role = "collector"

    # ── 3. Parse and Process using LLM Agent ─────────────────────────────────
    try:
        if sender_role:
            from app.graph.whatsapp_agent import process_whatsapp_message
            reply_msg = await process_whatsapp_message(
                text=body, 
                sender_role=sender_role, 
                lab_id=lab_id, 
                sender_phone=from_number
            )
        else:
            # Route to Patient Chatbot
            from app.graph.patient_whatsapp_agent import process_patient_whatsapp_message
            
            session_key = f"whatsapp_{from_number}_{lab_id}"
            session_data = {}
            
            # 1. Load persistent session from DB
            try:
                session_res = supabase.table("whatsapp_sessions").select("data").eq("session_key", session_key).execute()
                if session_res.data:
                    session_data = session_res.data[0]["data"]
            except Exception as e:
                log.error("[whatsapp] Error fetching session: %s", e)
            
            log.info("[whatsapp] LOADED session for %s: intent=%s name=%s age=%s phone=%s test=%s",
                     session_key, session_data.get("intent"), session_data.get("name"),
                     session_data.get("age"), session_data.get("patient_phone"), session_data.get("test_type"))
                
            reply_msg = await process_patient_whatsapp_message(
                text=body,
                sender_phone=from_number,
                lab_id=lab_id,
                session=session_data,
                services=services,
                business_name=business_name
            )
            
            log.info("[whatsapp] SAVING session for %s: intent=%s name=%s age=%s phone=%s test=%s",
                     session_key, session_data.get("intent"), session_data.get("name"),
                     session_data.get("age"), session_data.get("patient_phone"), session_data.get("test_type"))
            
            # 2. Save persistent session back to DB
            try:
                supabase.table("whatsapp_sessions").upsert({
                    "session_key": session_key,
                    "data": session_data
                }, on_conflict="session_key").execute()
            except Exception as e:
                log.error("[whatsapp] Error saving session: %s", e)

        await _send_wa_reply(
            from_number, reply_msg,
            lab_phone_number_id=wa_phone_id,
            lab_access_token=wa_token,
        )
        log.info("[whatsapp] Agent replied: %s", reply_msg)
    except Exception as e:
        log.error("[whatsapp] CRITICAL ERROR in message processing: %s", e, exc_info=True)


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages from the Meta Cloud API.
    Immediately returns 200 OK to prevent Meta retries, and processes via background task.
    """
    payload = await request.json()
    background_tasks.add_task(_process_whatsapp_payload, payload)
    return {"status": "accepted"}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 4 — Walk-in Booking (JSON API — called by lab receptionist app)
# ─────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field as PydField
from fastapi import Depends
from app.core.auth import get_current_lab_id
from app.graph.builder import (
    create_walkin_graph,
    create_collector_graph,
)

class WalkinRequest(BaseModel):
    lab_id: str
    name: str
    age: int
    phone: str
    test_type: str
    collector_phone: str = ""   # optional — if provided, WhatsApp alert is sent


@router.post("/walkin")
async def walkin_booking(body: WalkinRequest, token_lab_id: str = Depends(get_current_lab_id)):
    """
    Register a walk-in patient. Inserts booking into Supabase and
    sends a WhatsApp message to the assigned collector with patient details.
    """
    log.info(
        "[walkin] New walk-in: name=%s test=%s lab=%s",
        body.name, body.test_type, token_lab_id,
    )

    graph = create_walkin_graph()
    result = await graph.ainvoke({
        "event_type":       "whatsapp_walkin",
        "lab_id":           token_lab_id,
        "patient_id":       None,
        "user_text":        None,
        "agent_speech":     None,
        "patient_data":     PatientData(
            name=body.name,
            age=body.age,
            phone=body.phone,
            test_type=body.test_type,
        ),
        "missing_fields":   [],
        "dispatch_success": False,
        "booking_id":       None,
        "sample_status":    None,
        "collector_phone":  body.collector_phone or None,
        "payment_amount":   None,
        "payment_method":   None,
        "report_link":      None,
    })

    return {
        "status":           "success" if result.get("dispatch_success") or result.get("booking_id") else "partial",
        "booking_id":       result.get("booking_id"),
        "message":          result.get("agent_speech"),
        "dispatch_success": result.get("dispatch_success"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 5 — Collector Update (JSON API — called by collector app)
# ─────────────────────────────────────────────────────────────────────────────
class CollectorUpdateRequest(BaseModel):
    booking_id: str
    sample_status: str                # collected, in_transit, delivered, failed
    collector_phone: str = ""         # optional


@router.post("/collector/update")
async def collector_update(body: CollectorUpdateRequest, token_lab_id: str = Depends(get_current_lab_id)):
    """
    Update the sample collection status for an existing booking.
    Valid statuses: collected, in_transit, delivered, failed.
    """
    log.info(
        "[collector] Update: booking=%s status=%s",
        body.booking_id, body.sample_status,
    )

    graph = create_collector_graph()
    result = await graph.ainvoke({
        "event_type":       "whatsapp_collector",
        "lab_id":           token_lab_id,
        "patient_id":       None,
        "user_text":        None,
        "agent_speech":     None,
        "patient_data":     PatientData(),
        "missing_fields":   [],
        "dispatch_success": False,
        "booking_id":       body.booking_id,
        "sample_status":    body.sample_status,
        "collector_phone":  body.collector_phone or None,
        "payment_amount":   None,
        "payment_method":   None,
        "report_link":      None,
    })

    return {
        "status":           "success" if result.get("dispatch_success") else "error",
        "booking_id":       result.get("booking_id"),
        "message":          result.get("agent_speech"),
    }



