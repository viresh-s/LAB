"""
Multi-Tenant Meta WhatsApp Cloud API Service.

Architecture:
  - Each lab has its OWN WhatsApp Business number registered on Meta.
  - Each lab's credentials (phone_number_id + access_token) are stored in the
    Supabase 'labs' table columns: whatsapp_phone_number_id, whatsapp_access_token.
  - All send methods accept optional per-lab credentials.
  - If per-lab credentials are NOT passed, falls back to .env globals
    (useful for demo / single-lab testing).

Multi-lab flow:
  Patient at Apollo Labs → AI sends message using Apollo's own WA number.
  Patient at SRL Labs   → AI sends message using SRL's own WA number.
  One Python class. Zero duplicate code. Infinite labs.
"""
import logging
import httpx
from typing import Optional
from app.core.config import settings

log = logging.getLogger(__name__)


def _resolve_credentials(
    lab_phone_number_id: Optional[str],
    lab_access_token: Optional[str],
) -> tuple[str, str]:
    """
    Returns (phone_number_id, access_token) to use for this request.
    Strictly uses per-lab credentials in production. No global defaults.
    """
    return lab_phone_number_id, lab_access_token


class MetaWhatsAppService:
    """
    Multi-tenant WhatsApp Cloud API service.

    Usage (single lab / demo — uses .env):
        await wa.send_text_message(to="919876543210", text="Hello!")

    Usage (multi-lab production — uses per-lab DB credentials):
        lab = supabase.table("labs").select("whatsapp_phone_number_id, whatsapp_access_token").eq("id", lab_id).single().execute()
        await wa.send_text_message(
            to="919876543210",
            text="Hello from Apollo Labs!",
            lab_phone_number_id=lab.data["whatsapp_phone_number_id"],
            lab_access_token=lab.data["whatsapp_access_token"],
        )
    """

    def __init__(self):
        self.base_url = "https://graph.facebook.com/v19.0"

    async def send_text_message(
        self,
        to: str,
        text: str,
        lab_phone_number_id: Optional[str] = None,
        lab_access_token: Optional[str] = None,
    ) -> bool:
        """
        Send a WhatsApp text message via Meta Cloud API.

        Args:
            to:                    Recipient phone with country code (e.g. 919876543210).
            text:                  Message body.
            lab_phone_number_id:   Per-lab Meta Phone Number ID (from Supabase labs table).
            lab_access_token:      Per-lab Meta Access Token (from Supabase labs table).
                                   Falls back to .env values if not provided.
        """
        phone_id, token = _resolve_credentials(lab_phone_number_id, lab_access_token)
        if not phone_id or not token:
            log.warning("[Meta WA] No credentials available (check .env or lab DB row). Cannot send message.")
            return False

        url     = f"{self.base_url}/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        to_str = str(to)
        to_clean = to_str.replace("+", "").replace(" ", "").strip()
        if len(to_clean) == 10:
            to_clean = f"91{to_clean}"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to_clean,
            "type":              "text",
            "text":              {"preview_url": False, "body": text},
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                resp.raise_for_status()
                log.info("[Meta WA] ✅ Text sent → %s (phone_id=%s)", to_clean, phone_id)
                return True
        except Exception as e:
            log.error("[Meta WA] ❌ Failed to send text to %s: %s", to_clean, e)
            if hasattr(e, "response") and e.response:
                log.error("[Meta WA] Response body: %s", e.response.text)
            return False

    async def send_media_message(
        self,
        to: str,
        media_url: str,
        caption: str = "",
        lab_phone_number_id: Optional[str] = None,
        lab_access_token: Optional[str] = None,
    ) -> bool:
        """
        Send a document/PDF message via Meta Cloud API.

        Args:
            to:                    Recipient phone with country code.
            media_url:             Public URL of the PDF/document.
            caption:               Optional caption under the document.
            lab_phone_number_id:   Per-lab Meta Phone Number ID.
            lab_access_token:      Per-lab Meta Access Token.
        """
        phone_id, token = _resolve_credentials(lab_phone_number_id, lab_access_token)
        if not phone_id or not token:
            log.warning("[Meta WA] No credentials available. Cannot send media.")
            return False

        url      = f"{self.base_url}/{phone_id}/messages"
        headers  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        to_str = str(to)
        to_clean = to_str.replace("+", "").replace(" ", "").strip()
        if len(to_clean) == 10:
            to_clean = f"91{to_clean}"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to_clean,
            "type":              "document",
            "document":          {"link": media_url, "caption": caption},
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                resp.raise_for_status()
                log.info("[Meta WA] ✅ Document sent → %s (phone_id=%s)", to_clean, phone_id)
                return True
        except Exception as e:
            log.error("[Meta WA] ❌ Failed to send document to %s: %s", to_clean, e)
            if hasattr(e, "response") and e.response:
                log.error("[Meta WA] Response body: %s", e.response.text)
            return False


# Singleton instance to be imported by other modules
whatsapp_service = MetaWhatsAppService()

