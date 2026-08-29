"""
Speech service — Deepgram STT + Eden AI TTS (Azure Neural) + Groq/OpenAI translation.

Three responsibilities:
  1. speech_to_text(audio_bytes, lang)  → transcript text   (Deepgram Nova-2)
  2. translate(text, src, tgt)          → translated text   (Groq llama-3.3-70b  → OpenAI GPT-4o-mini fallback)
  3. text_to_speech(text)               → MP3 audio bytes   (Eden AI Azure Neural → Deepgram Aura fallback)

Fallback chain:
  TTS:         Eden AI (Microsoft Azure Neural $16/1M)  →  Deepgram Aura (emergency)
  Translation: Groq llama-3.3-70b  →  OpenAI GPT-4o-mini
  STT:         Deepgram Nova-2  (single provider, always)
"""
import logging
import base64
import httpx
from app.core.config import settings

log = logging.getLogger(__name__)

# ── Deepgram (STT + emergency TTS fallback) ───────────────────────────────────
_DEEPGRAM_STT_URL = "https://api.deepgram.com/v1/listen"
_DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"
_DEEPGRAM_TTS_MODEL = "aura-asteria-en"   # Deepgram Aura — emergency fallback only

# ── Eden AI → Microsoft Azure Neural (Primary TTS) ───────────────────────────
# Cost: ~$16 per 1M characters — cheapest neural voice on Eden AI
_EDENAI_TTS_URL = "https://api.edenai.run/v2/audio/text_to_speech"

# ── Groq (Primary LLM for translation) ───────────────────────────────────────
_GROQ_BASE        = "https://api.groq.com/openai/v1"
_GROQ_CHAT_MODEL  = "llama-3.3-70b-versatile"

# ── OpenAI (Translation fallback only — NOT used for TTS) ─────────────────────
_OPENAI_BASE  = "https://api.openai.com/v1"
_CHAT_MODEL   = "gpt-4o-mini"


# ── Header builders ───────────────────────────────────────────────────────────
def _deepgram_headers() -> dict:
    return {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}


def _edenai_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.EDEN_AI_API_KEY}",
        "Content-Type":  "application/json",
    }


def _groq_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }


def _openai_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type":  "application/json",
    }


class SpeechService:
    """
    Async speech service with automatic fallbacks.

    Primary → Fallback:
      TTS:         Eden AI (Azure Neural)  →  Deepgram Aura (emergency)
      Translation: Groq llama-3.3-70b  →  OpenAI GPT-4o-mini
      STT:         Deepgram Nova-2  (no fallback needed, very reliable)
    """

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Speech-to-Text  (Deepgram Nova-2)
    # ─────────────────────────────────────────────────────────────────────────
    async def speech_to_text(
        self,
        audio_bytes: bytes,
        lang: str = "kn",
        content_type: str = "audio/mpeg",
    ) -> str:
        """
        Transcribe audio bytes with Deepgram Nova-2.

        Args:
            audio_bytes:  Raw audio (MP3/WAV from Exotel recording).
            lang:         BCP-47 language code. "kn" = Kannada, "en" = English.
            content_type: MIME type of the audio.

        Returns:
            Transcript string, or "" on failure.
        """
        if not settings.DEEPGRAM_API_KEY:
            log.warning("[Deepgram STT] API key not set — returning empty transcript.")
            return ""

        params = {
            "model":        "nova-2",
            "language":     lang,
            "smart_format": "true",
            "punctuate":    "true",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    _DEEPGRAM_STT_URL,
                    params=params,
                    content=audio_bytes,
                    headers={**_deepgram_headers(), "Content-Type": content_type},
                )
                resp.raise_for_status()
                data = resp.json()
                transcript = (
                    data["results"]["channels"][0]
                    ["alternatives"][0]["transcript"]
                )
                log.info("[Deepgram STT] (%s): '%s'", lang, transcript[:80])
                return transcript
        except Exception as e:
            log.error("[Deepgram STT] Error: %s", e)
            return ""



    # ─────────────────────────────────────────────────────────────────────────
    # 3. Text-to-Speech  (Deepgram Aura for Testing → Eden AI)
    # ─────────────────────────────────────────────────────────────────────────
    async def text_to_speech(
        self,
        text: str,
        voice: str = "FEMALE",
        speed: float = 0.9,
        lab_id: str = None,
    ) -> bytes | None:
        """
        Convert text to MP3 audio bytes.

        Production Setup:
          1. Eden AI → Microsoft Azure Neural  (Primary — $16/1M chars)
          2. Deepgram Aura                     (Fallback — emergency only)

        Returns: Raw MP3 bytes, or None if all providers fail.
        """
        audio_bytes = None

        # ── Primary (Production): Eden AI → Microsoft Azure Neural ─────────────
        if settings.EDEN_AI_API_KEY:
            try:
                audio_bytes = await self._edenai_tts(text)
                if audio_bytes:
                    log.info(
                        "[Eden AI / Azure TTS] Generated %d bytes for '%s...'",
                        len(audio_bytes), text[:25],
                    )
                    if lab_id:
                        from app.services.usage import track_tts_cost
                        track_tts_cost(lab_id, len(text))
                    return audio_bytes
            except Exception as e:
                log.warning("[Eden AI / Azure TTS] Failed (%s) — trying Deepgram Aura fallback.", e)
        else:
            log.warning("[Eden AI TTS] No API key set — trying Deepgram Aura fallback.")

        # ── Fallback (Emergency): Deepgram Aura ───────────────────────────────
        if settings.DEEPGRAM_API_KEY:
            try:
                audio_bytes = await self._deepgram_tts(text)
                if audio_bytes:
                    log.info(
                        "[Deepgram Aura TTS fallback] Generated %d bytes for '%s...'",
                        len(audio_bytes), text[:25],
                    )
                    if lab_id:
                        from app.services.usage import track_tts_cost
                        track_tts_cost(lab_id, len(text))
                    return audio_bytes
            except Exception as e:
                log.error("[Deepgram Aura TTS fallback] Also failed: %s", e)

        log.error("[TTS] All providers failed — no audio generated.")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _edenai_tts(self, text: str) -> bytes | None:
        """
        Call Eden AI TTS routed to Microsoft Azure Neural.
        Specifically uses provider="microsoft" for the $16/1M char rate.
        Eden AI returns JSON with 'audio_resource_url'; we download the audio.
        """
        payload = {
            "providers":  "microsoft",    # Specifically Microsoft Azure Neural
            "language":   "en-IN",        # English (India) — Azure Neural voice
            "text":       text,
            "option":     "FEMALE",       # Natural female voice
            "settings": {
                "microsoft": {
                    "model": "neural",    # Standard Neural = $16/1M chars (NOT neural_hd = $22/1M)
                }
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Request TTS from Eden AI → routed to Microsoft Azure
            resp = await client.post(
                _EDENAI_TTS_URL,
                json=payload,
                headers=_edenai_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            # Step 2: Extract audio from the Microsoft provider response
            microsoft_result = data.get("microsoft", {})
            audio_url = microsoft_result.get("audio_resource_url")

            if not audio_url:
                # Some Eden AI responses include audio as base64
                audio_b64 = microsoft_result.get("audio")
                if audio_b64:
                    return base64.b64decode(audio_b64)
                log.warning("[Eden AI TTS] No audio_resource_url or audio in response: %s",
                            list(microsoft_result.keys()))
                return None

            # Step 3: Download the actual audio bytes from the hosted URL
            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()
            return audio_resp.content

    async def _deepgram_tts(self, text: str) -> bytes | None:
        """
        Call Deepgram Aura TTS and return raw MP3 bytes.
        Used ONLY as emergency fallback when Eden AI is down.
        """
        params = {
            "model":    _DEEPGRAM_TTS_MODEL,
            "encoding": "mp3",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _DEEPGRAM_TTS_URL,
                params=params,
                json={"text": text},
                headers={**_deepgram_headers(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.content


