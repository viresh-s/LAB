from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # ── Exotel ────────────────────────────────────────────────────────────────
    EXOTEL_ACCOUNT_SID: str = ""
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    # Fallback for local testing
    TEST_PHONE_NUMBER: str = ""

    # ── Speech & LLM ────────────────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # ── Eden AI (TTS router → Microsoft Azure Neural) ─────────────────────
    EDEN_AI_API_KEY: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    # Fallback lab used during development / before any lab registers
    DEFAULT_LAB_ID: str = "test-lab-id-123"
    # Public base URL of your deployed backend (used for Exotel callback construction)
    BASE_URL: str = ""
    # Master Admin email for the master dashboard
    MASTER_ADMIN_EMAIL: str = ""

    # ── Meta WhatsApp Cloud API ───────────────────────────────────────
    # Get these from: https://developers.facebook.com → WhatsApp → API Setup
    WHATSAPP_PHONE_NUMBER_ID: str = ""   # Your WhatsApp Business phone number ID
    WHATSAPP_ACCESS_TOKEN: str = ""      # Permanent or temporary access token
    WHATSAPP_VERIFY_TOKEN: str = ""  # Token for webhook verification
    WHATSAPP_TEMPLATE_NAME: str = "new_booking_alert"  # Pre-approved template name

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
