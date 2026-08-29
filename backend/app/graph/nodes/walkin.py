"""
Walk-in booking nodes for LangGraph.

Flow:  extract_walkin_data  →  db_insert_walkin_booking
       (validate input)        (insert into Supabase + dispatch WhatsApp to collector)

Unlike the voice flow, all data arrives in one shot from the lab receptionist
via a REST API call — no multi-turn conversation needed.
"""
import logging
from app.graph.state import OrchestratorState as AgentState, PatientData
from app.db.supabase import supabase
from app.services.meta_wa import whatsapp_service

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Validate the walk-in data
# ─────────────────────────────────────────────────────────────────────────────
async def extract_walkin_data(state: AgentState) -> AgentState:
    """
    Validates the incoming walk-in booking data.
    Expects patient_data to be pre-populated from the API request body.
    Sets missing_fields if any required field is absent.
    """
    patient: PatientData = state.get("patient_data") or PatientData()

    required = ["name", "age", "phone", "test_type"]
    missing = [f for f in required if getattr(patient, f) is None]

    if missing:
        log.warning("[walkin] Missing fields: %s", missing)
    else:
        log.info("[walkin] All fields present for patient: %s", patient.name)

    return {
        **state,
        "patient_data": patient,
        "missing_fields": missing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Insert booking into Supabase + dispatch WhatsApp to collector
# ─────────────────────────────────────────────────────────────────────────────
async def db_insert_walkin_booking(state: AgentState) -> AgentState:
    """
    Inserts a walk-in booking into Supabase and dispatches a WhatsApp message
    to the assigned collector with the patient details.
    The collector_phone is fetched from the lab's record (fixed per-lab).
    """
    patient: PatientData = state["patient_data"]
    lab_id: str = state.get("lab_id", "")
    
    collector_phone = ""
    receptionist_phone = ""
    wa_phone_id = None
    wa_token = None

    if lab_id and supabase:
        try:
            lab_res = supabase.table("labs").select(
                "collector_phone, receptionist_phone, exotel_number, "
                "whatsapp_phone_number_id, whatsapp_access_token"
            ).eq("id", lab_id).single().execute()
            lab_data = lab_res.data or {}
            collector_phone = lab_data.get("collector_phone") or ""
            receptionist_phone = lab_data.get("receptionist_phone") or ""
            wa_phone_id = lab_data.get("whatsapp_phone_number_id") or None
            wa_token = lab_data.get("whatsapp_access_token") or None
        except Exception as e:
            log.warning("[walkin] Could not fetch lab details: %s", e)

    row = {
        "lab_id":         lab_id,
        "name":           patient.name,
        "age":            patient.age,
        "phone":          patient.phone,
        "test_type":      patient.test_type,
        "status":         "booked",
        "payment_status": patient.payment_status,
        "report_link":    "",
    }

    booking_id = None
    dispatch_success = False

    if supabase is None:
        log.warning("[walkin] Supabase not configured — skipping DB insert.")
        return {
            **state,
            "agent_speech": f"Booking confirmed for   {patient.name} ({patient.test_type}).",
            "dispatch_success": False,
        }

    # ── Insert into bookings table ────────────────────────────────────────
    try:
        response = supabase.table("patients").insert(row).execute()
        inserted = response.data[0] if response.data else {}
        booking_id = inserted.get("id")
        log.info("[walkin] Booking inserted: id=%s name=%s", booking_id, patient.name)
    except Exception as e:
        log.error("[walkin] DB insert error: %s", e)
        return {
            **state,
            "agent_speech": f"Error creating booking for {patient.name}. Please try again.",
            "dispatch_success": False,
        }

    # ── Dispatch WhatsApp to collector ────────────────────────────────────
    if collector_phone:
        try:
            short_id = booking_id[:8]
            msg = (
                f"🚨 *New Booking Alert*\n\n"
                f"A new walk-in patient requires sample collection.\n\n"
                f"👤 *Name:* {patient.name}\n"
                f"📅 *Age:* {patient.age}\n"
                f"📞 *Phone:* {patient.phone}\n"
                f"🔬 *Test:* {patient.test_type}\n\n"
                f"🆔 *Booking ID:*\n"
                f"`{short_id}`\n\n"
                f"Please collect the sample ASAP."
            )
            wa_sent = await whatsapp_service.send_text_message(
                to=collector_phone, text=msg,
                lab_phone_number_id=wa_phone_id,
                lab_access_token=wa_token,
            )
            dispatch_success = wa_sent
        except Exception as e:
            log.error("[walkin] WhatsApp dispatch error: %s", e)
    else:
        log.info("[walkin] No collector_phone provided — skipping WhatsApp dispatch.")

    # ── Send confirmation to patient via WhatsApp ─────────────────────────
    if patient.phone and booking_id:
        try:
            short_id = booking_id[:8]
            msg = (
                f"Hello *{patient.name}*, your booking for *{patient.test_type}* is confirmed.\n\n"
                f"Your Booking ID:\n"
                f"`{short_id}`\n\n"
                f"Our collector will contact you shortly to collect the sample. 🙏"
            )
            sent = await whatsapp_service.send_text_message(
                to=patient.phone, text=msg,
                lab_phone_number_id=wa_phone_id,
                lab_access_token=wa_token,
            )
            
            # If not sent, maybe they don't have WhatsApp
            if not sent and receptionist_phone:
                log.warning("[walkin] Patient %s may not have WhatsApp on %s", patient.name, patient.phone)
                try:
                    alert_msg = (
                        f"⚠️ *No WhatsApp Alert*\n\n"
                        f"Patient *{patient.name}* (ID: {booking_id[:8]}) "
                        f"might not have WhatsApp on number *{patient.phone}*.\n\n"
                        f"Please contact them directly."
                    )
                    await whatsapp_service.send_text_message(
                        to=receptionist_phone, text=alert_msg,
                        lab_phone_number_id=wa_phone_id,
                        lab_access_token=wa_token,
                    )
                except Exception as alert_err:
                    log.warning("[walkin] Could not send no-WhatsApp alert to receptionist: %s", alert_err)
        except Exception as e:
            log.warning("[walkin] Patient WhatsApp confirmation error: %s", e)

    confirmation_msg = (
        f"Walk-in booking confirmed for {patient.name}! "
        f"Test: {patient.test_type}. Booking ID: {booking_id[:8]}. "
        "Collector has been notified via WhatsApp."
    )

    return {
        **state,
        "booking_id":       str(booking_id) if booking_id else None,
        "patient_id":       str(booking_id) if booking_id else None,
        "agent_speech":     confirmation_msg,
        "dispatch_success": dispatch_success,
    }
