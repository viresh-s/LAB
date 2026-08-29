import logging
import asyncio
from app.db.supabase import supabase

log = logging.getLogger(__name__)

# Standard SaaS API Pricing (in USD for calculation)
PRICING = {
    "exotel_voice": 0.012,       # per minute (approx)
    "deepgram_stt": 0.0043,      # per minute
    "openai_tts": 0.015,         # per 1000 characters
    "openai_llm_input": 5.0,     # per 1,000,000 tokens (GPT-4o)
    "openai_llm_output": 15.0,   # per 1,000,000 tokens (GPT-4o)
}

def log_usage_async(lab_id: str, service_type: str, units_used: float, cost_incurred: float):
    """
    Fire-and-forget wrapper to log usage asynchronously so it doesn't block the API response.
    """
    if not supabase or not lab_id:
        return
        
    async def _log():
        try:
            supabase.table("resource_usage").insert({
                "lab_id": lab_id,
                "service_type": service_type,
                "units_used": units_used,
                "cost_incurred": cost_incurred
            }).execute()
            log.debug("[usage] Logged %s cost: $%f for lab %s", service_type, cost_incurred, lab_id)
        except Exception as e:
            log.error("[usage] Failed to log resource usage: %s", e)
            
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_log())
    except RuntimeError:
        # If no running loop, just run it sync (for testing)
        asyncio.run(_log())


def track_llm_cost(lab_id: str, input_tokens: int, output_tokens: int):
    """Calculate and log OpenAI LLM costs."""
    if not lab_id or lab_id == "test-lab-id-123": return
    cost = (input_tokens / 1_000_000.0) * PRICING["openai_llm_input"] + (output_tokens / 1_000_000.0) * PRICING["openai_llm_output"]
    log_usage_async(lab_id, "openai_llm", input_tokens + output_tokens, cost)

def track_tts_cost(lab_id: str, char_count: int):
    """Calculate and log OpenAI TTS costs."""
    if not lab_id or lab_id == "test-lab-id-123": return
    cost = (char_count / 1000.0) * PRICING["openai_tts"]
    log_usage_async(lab_id, "openai_tts", char_count, cost)

def track_stt_cost(lab_id: str, seconds: float):
    """Calculate and log Deepgram STT costs."""
    if not lab_id or lab_id == "test-lab-id-123": return
    minutes = seconds / 60.0
    cost = minutes * PRICING["deepgram_stt"]
    log_usage_async(lab_id, "deepgram_stt", seconds, cost)

def track_exotel_cost(lab_id: str, seconds: int):
    """Calculate and log Exotel Voice costs."""
    if not lab_id or lab_id == "test-lab-id-123": return
    import math
    minutes = math.ceil(seconds / 60.0)
    cost = minutes * PRICING["exotel_voice"]
    log_usage_async(lab_id, "exotel_voice", minutes, cost)
