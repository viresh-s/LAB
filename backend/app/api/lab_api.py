"""
Lab API endpoints — authenticated, lab-scoped operations.

All endpoints require a valid Supabase JWT token.
The lab_id is extracted from the token and used to scope all queries.

Endpoints:
  GET  /api/lab/bookings          — List bookings for this lab
  GET  /api/lab/export            — Download monthly patient data as Excel
  POST /api/lab/report/upload     — Upload a PDF report for a booking (with validation)
  POST /api/lab/payment           — Record payment for a booking
"""
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_lab_id, verify_booking_ownership
from app.db.supabase import supabase
from app.graph.state import PatientData
from app.graph.builder import create_payment_graph, create_report_upload_graph
from app.services.file_validator import validate_pdf, generate_storage_path

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lab", tags=["Lab API"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. List bookings for this lab
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/bookings")
async def list_bookings(
    lab_id: str = Depends(get_current_lab_id),
    status: Optional[str] = Query(None, description="Filter by status: booked, sample_collected, delivered"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List bookings for the authenticated lab. Results are scoped to this lab only."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    try:
        query = (
            supabase.table("patients")
            .select("*")
            .eq("lab_id", lab_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if status:
            query = query.eq("status", status)
        if start_date:
            query = query.gte("created_at", f"{start_date}T00:00:00")
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59")

        response = query.execute()
        return {
            "lab_id": lab_id,
            "count": len(response.data or []),
            "patients": response.data or [],
        }
    except Exception as e:
        log.error("[lab_api] List bookings error: %s", e)
        raise HTTPException(500, "Failed to fetch bookings.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Export monthly patient data as Excel
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/export")
async def export_bookings(
    lab_id: str = Depends(get_current_lab_id),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    format: str = Query("xlsx", description="Export format: xlsx"),
):
    """
    Download monthly patient data as an Excel file.
    Data is scoped to the authenticated lab only — no cross-lab leakage.
    """
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    # Fetch bookings for this lab
    try:
        query = (
            supabase.table("patients")
            .select("*")
            .eq("lab_id", lab_id)
            .order("created_at", desc=False)
        )
        if start_date:
            query = query.gte("created_at", f"{start_date}T00:00:00")
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59")
            
        response = query.execute()
        bookings = response.data or []
    except Exception as e:
        log.error("[lab_api] Export query error: %s", e)
        raise HTTPException(500, "Failed to fetch bookings for export.")

    if not bookings:
        raise HTTPException(404, "No bookings found for the selected date range.")

    # Generate Excel
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        
        file_suffix = f"{start_date}_to_{end_date}" if start_date and end_date else "all"
        ws.title = f"Bookings"

        # ── Header row ────────────────────────────────────────────────────
        headers = [
            "S.No", "Booking ID", "Patient Name", "Age", "Phone",
            "Test Type", "Status", "Payment Status", "Payment Amount",
            "Payment Method", "Source", "Created At",
        ]

        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border

        # ── Data rows ─────────────────────────────────────────────────────
        for row_idx, booking in enumerate(bookings, 2):
            raw_status = booking.get("status", "")
            report_link = booking.get("report_link")
            payment_status = booking.get("payment_status", "pending")
            
            if report_link and payment_status not in ("paid", "waived") and raw_status != "report_delivered":
                display_status = "Report Ready"
            elif raw_status == "report_delivered":
                display_status = "Delivered"
            else:
                display_status = raw_status.replace("_", " ").title() if raw_status else ""
            row_data = [
                row_idx - 1,
                booking.get("id", ""),
                booking.get("name", ""),
                booking.get("age", ""),
                booking.get("phone", ""),
                booking.get("test_type", ""),
                display_status,
                booking.get("payment_status", "").title(),
                booking.get("payment_amount", ""),
                booking.get("payment_method", ""),
                booking.get("source", ""),
                booking.get("created_at", ""),
            ]
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

        # Auto-fit column widths
        for col_idx in range(1, len(headers) + 1):
            max_len = max(
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(1, len(bookings) + 2)
            )
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 4, 40)

        # Write to buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        filename = f"bookings_{lab_id[:8]}_{file_suffix}.xlsx"
        log.info("[lab_api] Excel export: lab=%s range=%s rows=%d", lab_id, file_suffix, len(bookings))

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ImportError:
        raise HTTPException(
            500,
            "openpyxl is not installed. Run: pip install openpyxl",
        )
    except Exception as e:
        log.error("[lab_api] Excel generation error: %s", e)
        raise HTTPException(500, "Failed to generate Excel export.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Upload a PDF report (authenticated + validated)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/report/upload")
async def upload_report(
    booking_id: str = Form(..., description="UUID of the booking"),
    file: UploadFile = File(..., description="The PDF report file"),
    lab_id: str = Depends(get_current_lab_id),
):
    """
    Upload a PDF report for a booking.

    Security:
      1. JWT auth → extracts lab_id
      2. Verify booking belongs to this lab
      3. Validate file (PDF, <10MB, magic bytes, no malware)
      4. Upload to Supabase Storage under lab-reports/{lab_id}/{booking_id}.pdf
      5. If payment is paid → auto-dispatch report to patient via WhatsApp
    """
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    # ── 1. Verify booking belongs to this lab ─────────────────────────────
    try:
        response = (
            supabase.table("patients")
            .select("lab_id, payment_status, phone, name, test_type")
            .eq("id", booking_id)
            .single()
            .execute()
        )
        booking = response.data
        if not booking:
            raise HTTPException(404, f"Booking {booking_id} not found.")

        verify_booking_ownership(booking["lab_id"], lab_id)

    except HTTPException:
        raise
    except Exception as e:
        log.error("[lab_api] Booking lookup error: %s", e)
        raise HTTPException(500, "Failed to verify booking.")

    # ── 2. Validate the PDF ───────────────────────────────────────────────
    errors = await validate_pdf(file)
    if errors:
        raise HTTPException(400, detail={"errors": errors})

    # ── 3. Upload to Supabase Storage ─────────────────────────────────────
    storage_path = generate_storage_path(lab_id, booking_id)
    file_content = await file.read()

    try:
        # Delete existing file if re-uploading
        try:
            supabase.storage.from_("lab-reports").remove([storage_path])
        except Exception:
            pass  # File may not exist yet

        supabase.storage.from_("lab-reports").upload(
            storage_path,
            file_content,
            {"content-type": "application/pdf"},
        )

        # Generate a signed URL (expires in 1 hour for WhatsApp delivery)
        # For storage, use the public URL pattern
        from app.core.config import settings
        report_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/lab-reports/{storage_path}"

        log.info("[lab_api] Report uploaded: %s → %s", booking_id, storage_path)

    except Exception as e:
        log.error("[lab_api] Storage upload error: %s", e)
        raise HTTPException(500, "Failed to upload report to storage.")

    # ── 4. Run the report upload graph (updates DB + checks payment) ──────
    graph = create_report_upload_graph()
    result = await graph.ainvoke({
        "event_type":       "pdf_upload",
        "lab_id":           lab_id,
        "patient_id":       None,
        "user_text":        None,
        "agent_speech":     None,
        "patient_data":     PatientData(),
        "missing_fields":   [],
        "dispatch_success": False,
        "booking_id":       booking_id,
        "status":    None,
        "collector_phone":  None,
        "payment_amount":   None,
        "payment_method":   None,
        "report_link":      report_url,
    })

    return {
        "status": "success",
        "booking_id": booking_id,
        "report_url": report_url,
        "storage_path": storage_path,
        "message": result.get("agent_speech"),
        "report_dispatched": result.get("dispatch_success", False),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Record payment (authenticated)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/payment")
async def record_payment(
    booking_id: str = Form(...),
    payment_amount: float = Form(0.0),
    payment_method: str = Form("cash"),
    lab_id: str = Depends(get_current_lab_id),
):
    """
    Record payment for a booking (authenticated).
    If the report is already uploaded, auto-dispatches it to the patient.
    """
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    # Verify booking belongs to this lab
    try:
        response = (
            supabase.table("patients")
            .select("lab_id")
            .eq("id", booking_id)
            .single()
            .execute()
        )
        booking = response.data
        if not booking:
            raise HTTPException(404, f"Booking {booking_id} not found.")

        verify_booking_ownership(booking["lab_id"], lab_id)

    except HTTPException:
        raise
    except Exception as e:
        log.error("[lab_api] Booking lookup error: %s", e)
        raise HTTPException(500, "Failed to verify booking.")

    # Run the payment graph
    graph = create_payment_graph()
    result = await graph.ainvoke({
        "event_type":       "whatsapp_payment",
        "lab_id":           lab_id,
        "patient_id":       None,
        "user_text":        None,
        "agent_speech":     None,
        "patient_data":     PatientData(),
        "missing_fields":   [],
        "dispatch_success": False,
        "booking_id":       booking_id,
        "status":    None,
        "collector_phone":  None,
        "payment_amount":   payment_amount,
        "payment_method":   payment_method,
        "report_link":      None,
    })

    return {
        "status": "success" if result.get("dispatch_success") else "payment_recorded",
        "booking_id": booking_id,
        "message": result.get("agent_speech"),
        "report_dispatched": result.get("dispatch_success", False),
    }

# ─────────────────────────────────────────────────────────────────────────────
# 5. Dashboard Metrics (authenticated)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/metrics")
async def get_metrics(lab_id: str = Depends(get_current_lab_id)):
    """Get dashboard metrics for the lab (today's counts, collections, monthly revenue)."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        today = datetime.utcnow()
        start_of_day = today.strftime("%Y-%m-%d 00:00:00")
        start_of_month = today.strftime("%Y-%m-01 00:00:00")

        # Fetch Lab Name and WhatsApp Configured Status
        lab_res = supabase.table("labs").select("business_name, whatsapp_phone_number_id, whatsapp_access_token").eq("id", lab_id).execute()
        if lab_res.data:
            lab_data = lab_res.data[0]
            lab_name = lab_data.get("business_name") or "LabSaaS"
            whatsapp_configured = bool(lab_data.get("whatsapp_phone_number_id") and lab_data.get("whatsapp_access_token"))
        else:
            lab_name = "LabSaaS"
            whatsapp_configured = False

        # 1. Today Booked (created today)
        today_booked_res = (
            supabase.table("patients")
            .select("id")
            .eq("lab_id", lab_id)
            .gte("created_at", start_of_day)
            .execute()
        )
        booked = len(today_booked_res.data or [])

        # 2. In Testing (currently sample_collected, regardless of when created)
        testing_res = (
            supabase.table("patients")
            .select("id")
            .eq("lab_id", lab_id)
            .eq("status", "sample_collected")
            .execute()
        )
        in_testing = len(testing_res.data or [])

        # 3. Today Delivered (booked today and delivered)
        delivered_res = (
            supabase.table("patients")
            .select("id")
            .eq("lab_id", lab_id)
            .gte("created_at", start_of_day)
            .eq("status", "report_delivered")
            .execute()
        )
        delivered = len(delivered_res.data or [])

        # 4. Today's collection
        today_payments = (
            supabase.table("patients")
            .select("payment_amount")
            .eq("lab_id", lab_id)
            .eq("payment_status", "paid")
            .gte("created_at", start_of_day)
            .execute()
        )
        today_collection = sum([p.get("payment_amount") or 0 for p in today_payments.data or []])

        # 5. Monthly revenue
        monthly_payments = (
            supabase.table("patients")
            .select("payment_amount")
            .eq("lab_id", lab_id)
            .eq("payment_status", "paid")
            .gte("created_at", start_of_month)
            .execute()
        )
        monthly_revenue = sum([p.get("payment_amount") or 0 for p in monthly_payments.data or []])

        return {
            "lab_name": lab_name,
            "whatsapp_configured": whatsapp_configured,
            "today_booked": booked,
            "today_in_testing": in_testing,
            "today_delivered": delivered,
            "today_collection": today_collection,
            "monthly_revenue": monthly_revenue
        }
    except Exception as e:
        log.error("[lab_api] Metrics error: %s", e)
        raise HTTPException(500, "Failed to fetch metrics.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Update Patient Data (manual UI edit — authenticated)
# ─────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel as _BaseModel

class PatientUpdateRequest(_BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    test_type: Optional[str] = None
    payment_status: Optional[str] = None
    payment_method: Optional[str] = None
    payment_amount: Optional[float] = None


@router.patch("/patient/{patient_id}")
async def update_patient(
    patient_id: str,
    body: PatientUpdateRequest,
    lab_id: str = Depends(get_current_lab_id),
):
    """
    Update patient name, phone, or test_type.
    Verifies booking ownership before applying changes.
    """
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    # Verify ownership
    try:
        res = (
            supabase.table("patients")
            .select("lab_id, payment_status")
            .eq("id", patient_id)
            .single()
            .execute()
        )
        booking = res.data
        if not booking:
            raise HTTPException(404, "Patient not found.")
        verify_booking_ownership(booking["lab_id"], lab_id)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[lab_api] Ownership check error: %s", e)
        raise HTTPException(500, "Failed to verify patient.")

    # Build update payload — only include non-None fields
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No fields provided to update.")

    try:
        # If payment is being updated to 'paid', run the payment graph
        if update_data.get("payment_status") == "paid":
            # Check if it wasn't already paid
            prev_payment_status = booking.get("payment_status")
            if prev_payment_status != "paid":
                # Run payment graph which will update DB and dispatch report if available
                from app.graph.nodes.report import create_payment_graph
                graph = create_payment_graph()
                
                from app.graph.state import PatientData
                result = await graph.ainvoke({
                    "event_type":       "manual_payment",
                    "lab_id":           lab_id,
                    "patient_id":       None,
                    "user_text":        None,
                    "agent_speech":     None,
                    "patient_data":     PatientData(),
                    "missing_fields":   [],
                    "dispatch_success": False,
                    "booking_id":       patient_id,
                    "status":           None,
                    "collector_phone":  None,
                    "payment_amount":   update_data.get("payment_amount"),
                    "payment_method":   update_data.get("payment_method", "cash"),
                    "report_link":      None,
                })
                
                # Remove payment fields from update_data since the graph handled them
                update_data.pop("payment_status", None)
                update_data.pop("payment_amount", None)
                update_data.pop("payment_method", None)
                
                # If there are still other fields (name, phone) update them
                if update_data:
                    supabase.table("patients").update(update_data).eq("id", patient_id).eq("lab_id", lab_id).execute()
                    
                log.info("[lab_api] Patient %s updated via payment graph & manual edit", patient_id)
                return {"status": "success", "patient_id": patient_id, "report_dispatched": result.get("dispatch_success", False)}

        # Normal update
        if update_data:
            supabase.table("patients").update(update_data).eq("id", patient_id).eq("lab_id", lab_id).execute()
        
        log.info("[lab_api] Patient %s updated: %s", patient_id, update_data)
        return {"status": "success", "patient_id": patient_id, "updated": update_data}
    except Exception as e:
        log.error("[lab_api] Patient update error: %s", e)
        raise HTTPException(500, "Failed to update patient.")

# ─────────────────────────────────────────────────────────────────────────────
# 6.5 Delete Patient
# ─────────────────────────────────────────────────────────────────────────────
@router.delete("/patient/{patient_id}")
async def delete_patient(
    patient_id: str,
    lab_id: str = Depends(get_current_lab_id),
):
    """
    Delete a patient record.
    Verifies booking ownership before deleting.
    """
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    try:
        # Verify ownership
        res = (
            supabase.table("patients")
            .select("lab_id")
            .eq("id", patient_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(404, "Patient not found.")
        verify_booking_ownership(res.data["lab_id"], lab_id)
        
        # Delete the record
        supabase.table("patients").delete().eq("id", patient_id).execute()
        log.info("[lab_api] Patient %s deleted by lab %s", patient_id, lab_id)
        return {"status": "success", "message": "Patient deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        log.error("[lab_api] Patient delete error: %s", e)
        raise HTTPException(500, "Failed to delete patient.")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Financials (Protected)
# ─────────────────────────────────────────────────────────────────────────────
from fastapi import Header

@router.get("/financials")
async def get_financials(
    lab_password: str = Header(..., description="Password to unlock financials"),
    lab_id: str = Depends(get_current_lab_id)
):
    """Get protected financial metrics for the lab (monthly collection, weekly collection, test-wise)."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        # Verify password using bcrypt
        import bcrypt
        lab_res = supabase.table("labs").select("financial_password, password").eq("id", lab_id).execute()
        if not lab_res.data:
            raise HTTPException(401, "Invalid lab password.")
            
        lab_data = lab_res.data[0]
        expected_hash = lab_data.get("financial_password")
        
        # Fall back to login password if no dedicated financial password
        if not expected_hash:
            expected_hash = lab_data.get("password")

        if not expected_hash:
            raise HTTPException(401, "No financial password configured for this lab.")

        # Check if the stored password is a bcrypt hash (starts with $2)
        if expected_hash.startswith("$2"):
            if not bcrypt.checkpw(lab_password.encode("utf-8"), expected_hash.encode("utf-8")):
                raise HTTPException(401, "Invalid lab password.")
        else:
            # Legacy plaintext comparison (for un-migrated passwords)
            if expected_hash != lab_password:
                raise HTTPException(401, "Invalid lab password.")

        today = datetime.utcnow()
        start_of_month = today.strftime("%Y-%m-01 00:00:00")
        
        from datetime import timedelta
        start_of_week = (today - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")

        # Monthly collection (total amount)
        monthly_payments = (
            supabase.table("patients")
            .select("payment_amount")
            .eq("lab_id", lab_id)
            .eq("payment_status", "paid")
            .gte("created_at", start_of_month)
            .execute()
        )
        monthly_collection = sum([p.get("payment_amount") or 0 for p in monthly_payments.data or []])

        # Weekly collection (total amount)
        weekly_payments = (
            supabase.table("patients")
            .select("payment_amount")
            .eq("lab_id", lab_id)
            .eq("payment_status", "paid")
            .gte("created_at", start_of_week)
            .execute()
        )
        weekly_collection = sum([p.get("payment_amount") or 0 for p in weekly_payments.data or []])

        # Test-wise collection (total amount per test)
        test_wise_payments = (
            supabase.table("patients")
            .select("test_type, payment_amount")
            .eq("lab_id", lab_id)
            .eq("payment_status", "paid")
            .gte("created_at", start_of_month)
            .execute()
        )
        
        test_wise = {}
        for p in test_wise_payments.data or []:
            t_type = p.get("test_type") or "Unknown"
            amt = p.get("payment_amount") or 0
            if t_type not in test_wise:
                test_wise[t_type] = {"amount": 0, "count": 0}
            test_wise[t_type]["amount"] += amt
            test_wise[t_type]["count"] += 1

        # Sort by highest amount
        test_wise_list = [{"test_type": k, "amount": v["amount"], "count": v["count"]} for k, v in test_wise.items()]
        test_wise_list.sort(key=lambda x: x["amount"], reverse=True)

        return {
            "monthly_collection": monthly_collection,
            "weekly_collection": weekly_collection,
            "test_wise": test_wise_list
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("[lab_api] Financials error: %s", e)
        raise HTTPException(500, "Failed to fetch financials.")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Export Patient Records (authenticated)
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse

@router.get("/export")
async def export_patients(
    start_date: str,
    end_date: str,
    format: str = "xlsx",
    lab_id: str = Depends(get_current_lab_id)
):
    """Export patient records to Excel or CSV"""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        # Convert dates to ISO timestamps for inclusive range
        start = f"{start_date}T00:00:00"
        end = f"{end_date}T23:59:59"

        # Fetch patients
        res = (
            supabase.table("patients")
            .select("name, phone, test_type, created_at, status, payment_amount, payment_status")
            .eq("lab_id", lab_id)
            .gte("created_at", start)
            .lte("created_at", end)
            .execute()
        )
        
        data = res.data or []
        
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(columns=["name", "phone", "test_type", "created_at", "status", "payment_amount", "payment_status"])
        else:
            # Rename columns for clarity
            df = df.rename(columns={
                "name": "Patient Name",
                "phone": "Mobile Number",
                "test_type": "Test Type",
                "created_at": "Date",
                "status": "Status",
                "payment_amount": "Amount Collected",
                "payment_status": "Payment Status"
            })
            # Format dates
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime('%Y-%m-%d %H:%M:%S')

        # Generate Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Patients')
        
        output.seek(0)
        
        headers = {
            'Content-Disposition': f'attachment; filename="Bookings_{start_date}_to_{end_date}.xlsx"'
        }
        
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            headers=headers
        )
    except Exception as e:
        log.error("[lab_api] Export error: %s", e)
        raise HTTPException(500, "Failed to export data.")
