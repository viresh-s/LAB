"""
Exotel service: multi-tenant, serverless-safe.

- make_call(to, from_, callback_url)  → outbound call
- XML builders for the voice webhook handlers
"""
import logging
import httpx
from app.core.config import settings
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)

async def make_call(to: str, from_: str, callback_url: str) -> str | None:
    """
    Initiate an outbound Exotel voice call.

    Args:
        to:           Patient's phone number, e.g. "+919876543210"
        from_:        Lab's Exotel number (ExoPhone)
        callback_url: Public URL Exotel will POST to when the call connects

    Returns:
        Exotel Call SID string, or None on failure.
    """
    if not settings.EXOTEL_ACCOUNT_SID or not settings.EXOTEL_API_KEY or not settings.EXOTEL_API_TOKEN:
        log.warning("[Exotel] Credentials not configured.")
        return None

    # Exotel requires numbers without '+' or starting with '0' for India.
    # Usually, E.164 without '+' works best, but Exotel is flexible.
    to_num = to.replace("+", "")
    from_num = from_.replace("+", "")

    url = f"https://api.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect.json"
    
    auth = (settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN)
    data = {
        "From": to_num,          # The number to call (Customer)
        "CallerId": from_num,    # The ExoPhone number
        "Url": callback_url,     # The App URL returning XML
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, auth=auth)
            resp.raise_for_status()
            
            resp_data = resp.json()
            call_sid = resp_data.get("Call", {}).get("Sid")
            log.info("[Exotel] Outbound call created: sid=%s to=%s from=%s", call_sid, to, from_)
            return call_sid
    except Exception as e:
        log.error("[Exotel] make_call error: %s", e)
        return None


# ── XML helpers (pure functions) ──────────────

def exotel_say_hangup(text: str) -> str:
    """Return XML that says a final message and hangs up."""
    response = ET.Element("Response")
    say = ET.SubElement(response, "Say")
    say.text = text
    ET.SubElement(response, "Hangup")
    return ET.tostring(response, encoding="unicode")


def exotel_play_hangup(audio_url: str) -> str:
    """Return XML that plays a final audio clip and hangs up."""
    response = ET.Element("Response")
    play = ET.SubElement(response, "Play")
    play.text = audio_url
    ET.SubElement(response, "Hangup")
    return ET.tostring(response, encoding="unicode")
