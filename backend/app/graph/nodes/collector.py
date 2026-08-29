"""
Collector update nodes for LangGraph.

Flow:  extract_collector_data  →  db_update_sample
       (validate payload)         (update booking status in Supabase)

Used when a field collector reports back with sample collection status
(e.g. "collected", "in_transit", "delivered") for an existing booking.
"""
import logging
from app.graph.state import OrchestratorState as AgentState
from app.db.supabase import supabase
from app.services.meta_wa import whatsapp_service

log = logging.getLogger(__name__)

# Valid sample statuses
VALID_STATUSES = {"collected", "in_transit", "delivered", "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Validate collector update payload
# ─────────────────────────────────────────────────────────────────────────────
async def extract_collector_data(state: AgentState) -> AgentState:
    """
    Validates the collector's update payload.
    Requires: booking_id and sample_status.
    """
    booking_id = state.get("booking_id")
    sample_status = state.get("status")

    missing = []
    if not booking_id:
        missing.append("booking_id")
    if not sample_status:
        missing.append("status")
    elif sample_status not in VALID_STATUSES:
        log.warning(
            "[collector] Invalid sample_status '%s'. Valid: %s",
            sample_status, VALID_STATUSES,
        )
        missing.append("status")

    if missing:
        log.warning("[collector] Missing/invalid fields: %s", missing)
    else:
        log.info("[collector] Valid update: booking=%s status=%s", booking_id, sample_status)

    return {
        **state,
        "missing_fields": missing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Update booking status in Supabase
# ─────────────────────────────────────────────────────────────────────────────
async def db_update_sample(state: AgentState) -> AgentState:
    """
    Updates the booking row in Supabase with the new sample_status.
    If status is 'collected', also notifies the patient via WhatsApp.
    """
    booking_id = state.get("booking_id")
    sample_status = state.get("status")
    
    # collector_phone was removed from patients table, we shouldn't try to update it there.

    if not booking_id or not sample_status:
        return {
            **state,
            "agent_speech": "Missing booking_id or sample_status. Cannot update.",
            "dispatch_success": False,
        }

    if supabase is None:
        log.warning("[collector] Supabase not configured — skipping update.")
        return {
            **state,
            "agent_speech": f"Sample status '{sample_status}' noted for booking {booking_id} (DB offline).",
            "dispatch_success": False,
        }

    # ── Update booking in Supabase ────────────────────────────────────────
    update_data = {"status": sample_status}

    try:
        lab_id = state.get("lab_id")
        response = (
            supabase.table("patients")
            .update(update_data)
            .eq("id", booking_id)
            .eq("lab_id", lab_id)
            .execute()
        )
        updated = response.data[0] if response.data else {}
        patient_phone = updated.get("phone")
        patient_name = updated.get("name", "Patient")
        test_type = updated.get("test_type", "test")
        lab_id = updated.get("lab_id")

        log.info(
            "[collector] Booking %s updated → status=%s",
            booking_id, sample_status,
        )
    except Exception as e:
        log.error("[collector] DB update error: %s", e)
        return {
            **state,
            "agent_speech": f"Error updating booking {booking_id}. Please try again.",
            "dispatch_success": False,
        }

    wa_phone_id = None
    wa_token = None
    if lab_id:
        try:
            lab_res = supabase.table("labs").select(
                "whatsapp_phone_number_id, whatsapp_access_token"
            ).eq("id", lab_id).single().execute()
            lab_data = lab_res.data or {}
            wa_phone_id = lab_data.get("whatsapp_phone_number_id") or None
            wa_token = lab_data.get("whatsapp_access_token") or None
        except Exception as e:
            log.warning("[collector] Could not fetch lab WA credentials: %s", e)

    # ── Notify patient if sample was collected ────────────────────────────
    dispatch_success = True
    if patient_phone:
        if sample_status == "collected":
            try:
                message = (
                    f"✅ *Sample Collected!*\n\n"
                    f"Hi {patient_name}, your sample for {test_type} has been collected.\n\n"
                    f"📋 Booking ID:\n"
                    f"`{booking_id[:8]}`\n\n"
                    f"Your report will be ready soon. We'll notify you when it's uploaded. 🙏"
                )
                await whatsapp_service.send_text_message(
                    to=patient_phone, text=message,
                    lab_phone_number_id=wa_phone_id,
                    lab_access_token=wa_token,
                )
            except Exception as e:
                log.warning("[collector] Patient notification error: %s", e)

        elif sample_status == "delivered":
            try:
                message = (
                    f"🏥 *Sample Delivered to Lab!*\n\n"
                    f"Hi {patient_name}, your sample for {test_type} has arrived at the lab.\n\n"
                    f"📋 Booking ID:\n"
                    f"`{booking_id[:8]}`\n\n"
                    f"Processing will begin shortly. You'll be notified when the report is ready. 🙏"
                )
                await whatsapp_service.send_text_message(
                    to=patient_phone, text=message,
                    lab_phone_number_id=wa_phone_id,
                    lab_access_token=wa_token,
                )
            except Exception as e:
                log.warning("[collector] Patient notification error: %s", e)

    status_labels = {
        "collected": "Sample collected",
        "in_transit": "Sample in transit to lab",
        "delivered": "Sample delivered to lab",
        "failed": "Collection failed",
    }

    confirmation_msg = (
        f"{status_labels.get(sample_status, sample_status)} for booking {booking_id}. "
        "Status updated successfully."
    )

    return {
        **state,
        "agent_speech":     confirmation_msg,
        "dispatch_success": dispatch_success,
    }
