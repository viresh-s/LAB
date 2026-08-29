"""
Payment & Report nodes for LangGraph.

Two entry-point flows that converge on a shared dispatch node:

  ─── Payment Flow ───────────────────────────────────────────────
  extract_payment → db_update_paid → check_and_dispatch

  ─── Report Upload Flow ─────────────────────────────────────────
  db_update_report_link → check_and_dispatch

  ─── Shared ─────────────────────────────────────────────────────
  check_and_dispatch (routing fn):
      BOTH paid + report available  →  wa_dispatch_report  →  END
      otherwise                     →  END (do NOT send)

Business rule:
  • Payment paid  +  Report NOT available  →  Don't send
  • Payment NOT paid  +  Report available  →  Don't send
  • Payment paid  +  Report available      →  Send report to patient via WhatsApp
"""
import logging
from typing import Literal

from app.graph.state import OrchestratorState as AgentState, PatientData
from app.db.supabase import supabase
from app.services.meta_wa import whatsapp_service

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ▸ PAYMENT FLOW — Node 1: Validate payment data
# ─────────────────────────────────────────────────────────────────────────────
async def extract_payment(state: AgentState) -> AgentState:
    """
    Validates incoming payment confirmation payload.
    Requires: booking_id.  Optional: payment_amount, payment_method.
    Looks up the booking from Supabase to get current report_link status.
    """
    booking_id = state.get("booking_id")
    payment_amount = state.get("payment_amount")
    payment_method = state.get("payment_method") or "cash"

    missing = []
    if not booking_id:
        missing.append("booking_id")

    if missing:
        log.warning("[payment] Missing fields: %s", missing)
        return {
            **state,
            "missing_fields": missing,
            "agent_speech": "Missing booking_id. Cannot process payment.",
            "dispatch_success": False,
        }

    # Fetch current booking data from Supabase (to check report_link)
    report_link = None
    patient_phone = None
    patient_name = "Patient"
    test_type = "test"

    if supabase:
        try:
            response = (
                supabase.table("patients")
                .select("*")
                .eq("id", booking_id)
                .eq("lab_id", lab_id)
                .single()
                .execute()
            )
            booking = response.data or {}
            report_link = booking.get("report_link")
            patient_phone = booking.get("phone")
            patient_name = booking.get("name", "Patient")
            test_type = booking.get("test_type", "test")
            log.info(
                "[payment] Booking %s found: payment_status=%s report_link=%s",
                booking_id, booking.get("payment_status"), report_link,
            )
        except Exception as e:
            log.error("[payment] Booking lookup error: %s", e)

    return {
        **state,
        "missing_fields": [],
        "payment_amount": payment_amount,
        "payment_method": payment_method,
        "report_link": report_link,
        # Carry patient info for dispatch
        "patient_data": PatientData(
            name=patient_name,
            phone=patient_phone,
            test_type=test_type,
            payment_status="paid",
            report_link=report_link,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ▸ PAYMENT FLOW — Node 2: Update payment status in Supabase
# ─────────────────────────────────────────────────────────────────────────────
async def db_update_paid(state: AgentState) -> AgentState:
    """
    Updates the booking row: payment_status → 'paid',
    stores payment_amount and payment_method.
    """
    booking_id = state.get("booking_id")
    payment_amount = state.get("payment_amount")
    payment_method = state.get("payment_method") or "cash"

    if not booking_id:
        return {
            **state,
            "agent_speech": "Missing booking_id. Cannot update payment.",
            "dispatch_success": False,
        }

    if supabase is None:
        log.warning("[payment] Supabase not configured — skipping update.")
        return {
            **state,
            "agent_speech": f"Payment noted for booking {booking_id} (DB offline).",
            "dispatch_success": False,
        }

    update_data = {
        "payment_status": "paid",
        "payment_method": payment_method,
    }
    if payment_amount is not None:
        update_data["payment_amount"] = payment_amount

    lab_id = state.get("lab_id")
    try:
        response = (
            supabase.table("patients")
            .update(update_data)
            .eq("id", booking_id)
            .eq("lab_id", lab_id)
            .execute()
        )
        updated = response.data[0] if response.data else {}
        # Refresh report_link from DB (may have been uploaded meanwhile)
        report_link = updated.get("report_link") or state.get("report_link")
        patient_phone = updated.get("phone")
        patient_name = updated.get("name", "Patient")
        test_type = updated.get("test_type", "test")

        log.info("[payment] Booking %s → payment_status=paid", booking_id)

        return {
            **state,
            "report_link": report_link,
            "patient_data": PatientData(
                name=patient_name,
                phone=patient_phone,
                test_type=test_type,
                payment_status="paid",
                report_link=report_link,
            ),
            "agent_speech": f"Payment of ₹{payment_amount or 'N/A'} ({payment_method}) recorded for booking {booking_id}.",
            "dispatch_success": True,
        }
    except Exception as e:
        log.error("[payment] DB update error: %s", e)
        return {
            **state,
            "agent_speech": f"Error updating payment for booking {booking_id}.",
            "dispatch_success": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ▸ PDF UPLOAD FLOW — Node 1: Save report link in Supabase
# ─────────────────────────────────────────────────────────────────────────────
async def db_update_report_link(state: AgentState) -> AgentState:
    """
    Updates the booking row with the uploaded report PDF URL.
    Sets status to 'delivered' (test completed + report uploaded).
    Also fetches payment_status from DB to decide dispatch.
    """
    booking_id = state.get("booking_id")
    report_link = state.get("report_link")

    if not booking_id or not report_link:
        return {
            **state,
            "agent_speech": "Missing booking_id or report_link. Cannot update.",
            "dispatch_success": False,
        }

    if supabase is None:
        log.warning("[report] Supabase not configured — skipping update.")
        return {
            **state,
            "agent_speech": f"Report link noted for booking {booking_id} (DB offline).",
            "dispatch_success": False,
        }

    lab_id = state.get("lab_id")
    try:
        response = (
            supabase.table("patients")
            .update({
                "report_link": report_link,
            })
            .eq("id", booking_id)
            .eq("lab_id", lab_id)
            .execute()
        )
        updated = response.data[0] if response.data else {}
        payment_status = updated.get("payment_status", "pending")
        patient_phone = updated.get("phone")
        patient_name = updated.get("name", "Patient")
        test_type = updated.get("test_type", "test")

        log.info(
            "[report] Booking %s → report_link=%s, status=delivered, payment_status=%s",
            booking_id, report_link[:50], payment_status,
        )

        return {
            **state,
            "report_link": report_link,
            "patient_data": PatientData(
                name=patient_name,
                phone=patient_phone,
                test_type=test_type,
                payment_status=payment_status,
                report_link=report_link,
            ),
            "agent_speech": f"Report uploaded for booking {booking_id}. Payment status: {payment_status}.",
            "dispatch_success": True,
        }
    except Exception as e:
        log.error("[report] DB update error: %s", e)
        return {
            **state,
            "agent_speech": f"Error saving report link for booking {booking_id}.",
            "dispatch_success": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ▸ SHARED ROUTER — check BOTH conditions before dispatching
# ─────────────────────────────────────────────────────────────────────────────
def check_and_dispatch(state: AgentState) -> Literal["wa_dispatch_report", "end"]:
    """
    Routing function: decides whether to send the report to the patient.

    Business rule (STRICT — all must be true):
      ✅ payment_status == 'paid'   AND   ✅ report_link is not None
        → route to wa_dispatch_report

      ❌ Any condition missing
        → route to end (do NOT send report)
    """
    patient_data: PatientData = state.get("patient_data") or PatientData()
    report_link = state.get("report_link") or patient_data.report_link
    payment_status = patient_data.payment_status

    is_paid = (payment_status == "paid")
    has_report = bool(report_link)

    log.info(
        "[check_and_dispatch] paid=%s, has_report=%s → %s",
        is_paid, has_report,
        "SEND" if (is_paid and has_report) else "SKIP",
    )

    if is_paid and has_report:
        return "wa_dispatch_report"
    return "end"


# ─────────────────────────────────────────────────────────────────────────────
# ▸ SHARED FINAL NODE — Send report PDF to patient via WhatsApp
# ─────────────────────────────────────────────────────────────────────────────
async def wa_dispatch_report(state: AgentState) -> AgentState:
    """
    Sends the PDF report to the patient via WhatsApp document message.
    Only called when BOTH payment is paid AND report_link is available.
    """
    patient_data: PatientData = state.get("patient_data") or PatientData()
    booking_id = state.get("booking_id", "N/A")
    report_link = state.get("report_link") or patient_data.report_link
    patient_phone = patient_data.phone
    patient_name = patient_data.name or "Patient"
    test_type = patient_data.test_type or "test"

    if not patient_phone:
        log.warning("[dispatch] No patient phone — cannot send report.")
        return {
            **state,
            "agent_speech": f"Report ready for {patient_name} but no phone number on file.",
            "dispatch_success": False,
        }

    if not report_link:
        log.warning("[dispatch] No report_link — cannot send.")
        return {
            **state,
            "agent_speech": f"No report link available for booking {booking_id}.",
            "dispatch_success": False,
        }

    # Fetch per-lab WA credentials for this booking's lab
    wa_phone_id = None
    wa_token = None
    if supabase:
        try:
            # first get lab_id
            b_res = supabase.table("patients").select("lab_id").eq("id", booking_id).single().execute()
            if b_res.data:
                lab_res = supabase.table("labs").select(
                    "whatsapp_phone_number_id, whatsapp_access_token"
                ).eq("id", b_res.data["lab_id"]).single().execute()
                lab_data = lab_res.data or {}
                wa_phone_id = lab_data.get("whatsapp_phone_number_id") or None
                wa_token = lab_data.get("whatsapp_access_token") or None
        except Exception as e:
            log.warning("[dispatch] Could not fetch lab WA credentials: %s", e)

    # ── Send report document via WhatsApp ─────────────────────────────────
    dispatch_success = False
    try:
        caption = (
            f"📋 *Lab Report Ready!*\n\n"
            f"Hi {patient_name}, your {test_type} report is ready.\n\n"
            f"Booking ID:\n"
            f"`{booking_id[:8]}`\n\n"
            f"Thank you for choosing our lab! 🙏"
        )
        dispatch_success = await whatsapp_service.send_media_message(
            to=patient_phone,
            media_url=report_link,
            caption=caption,
            lab_phone_number_id=wa_phone_id,
            lab_access_token=wa_token,
        )
        if dispatch_success:
            log.info("[dispatch] Report sent to %s for booking %s", patient_phone, booking_id)
            if supabase:
                try:
                    supabase.table("patients").update({"status": "report_delivered"}).eq("id", booking_id).eq("lab_id", lab_id).execute()
                except Exception as e:
                    log.error("[dispatch] Failed to update status to report_delivered: %s", e)
        else:
            log.warning("[dispatch] WhatsApp send_document returned False for %s", patient_phone)
    except Exception as e:
        log.error("[dispatch] WhatsApp dispatch error: %s", e)

    if dispatch_success:
        confirmation = (
            f"✅ Report for {patient_name} ({test_type}) has been sent to "
            f"{patient_phone} via WhatsApp. Booking: {booking_id}."
        )
    else:
        confirmation = (
            f"⚠️ Report is ready for {patient_name} but WhatsApp delivery failed. "
            f"Report link: {report_link}"
        )

    return {
        **state,
        "agent_speech": confirmation,
        "dispatch_success": dispatch_success,
    }
