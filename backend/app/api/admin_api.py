import logging
import bcrypt
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from supabase import create_client
from app.core.auth import verify_master_admin
from app.db.supabase import supabase
from app.core.config import settings
from app.services.meta_wa import whatsapp_service


class FinancialPasswordVerify(BaseModel):
    password: str


def _hash_password(plain: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# Columns safe to return to the frontend — excludes secrets
_SAFE_LAB_COLUMNS = (
    "id, business_name, email, exotel_number, collector_phone, receptionist_phone, "
    "whatsapp_phone_number_id, services, created_at, extended_storage"
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin API"])

# Dedicated service-role client ONLY for auth.admin operations.
# Must use the service role key — NEVER the anon key.
# Kept separate so sign_in_with_password() doesn't overwrite its session.
def _get_admin_client():
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return None


class LabCreate(BaseModel):
    email: str
    password: str
    business_name: str
    exotel_number: str
    collector_phone: Optional[str] = None
    receptionist_phone: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    services: Optional[List[dict]] = None
    financial_password: Optional[str] = None

class LabUpdate(BaseModel):
    business_name: Optional[str] = None
    exotel_number: Optional[str] = None
    collector_phone: Optional[str] = None
    receptionist_phone: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    services: Optional[List[dict]] = None
    extended_storage: Optional[bool] = None
    financial_password: Optional[str] = None

class LabBillCreate(BaseModel):
    amount: float
    description: str
    notify_whatsapp: bool = False

class LabDelete(BaseModel):
    password: str

# ─────────────────────────────────────────────────────────────────────────────
# 1. Labs Management
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/labs")
async def list_labs(admin_id: str = Depends(verify_master_admin)):
    """List all registered labs and calculate extended storage fees."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        response = supabase.table("labs").select(_SAFE_LAB_COLUMNS).order("created_at", desc=True).execute()
        labs = response.data or []
        
        from datetime import datetime, timedelta
        cutoff_date = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        # We will augment each lab with extended storage stats
        for lab in labs:
            lab_id = lab.get("id")
            # Count patients older than 30 days
            old_res = (
                supabase.table("patients")
                .select("id", count="exact")
                .eq("lab_id", lab_id)
                .lt("created_at", cutoff_date)
                .execute()
            )
            old_count = old_res.count or 0
            lab["old_records_count"] = old_count
            
            # Assuming ₹1 per record > 30 days as the fee
            lab["extended_storage_fee"] = old_count * 1
            
        return {"labs": labs}
    except Exception as e:
        log.error("[admin_api] List labs error: %s", e)
        raise HTTPException(500, "Failed to fetch labs.")


@router.post("/labs")
async def create_lab(lab: LabCreate, admin_id: str = Depends(verify_master_admin)):
    """Create a new Lab tenant (Auth User + labs table entry)."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    # Use the dedicated admin client — avoids session corruption on the shared client
    admin_client = _get_admin_client()
    if admin_client is None:
        raise HTTPException(503, "Service role key not configured.")

    try:
        # 1. Try to create user in Supabase Auth (requires service role)
        user = None
        try:
            auth_response = admin_client.auth.admin.create_user({
                "email": lab.email,
                "password": lab.password,
                "email_confirm": True
            })
            user = auth_response.user
        except Exception as auth_err:
            err_msg = str(auth_err)
            if "already been registered" in err_msg:
                # The auth user exists but the lab row was deleted (orphan).
                # Look up the existing auth user and check if lab row exists.
                log.warning("[admin_api] Auth user %s already exists, checking for orphan...", lab.email)
                try:
                    # List users filtered by email to find the orphan
                    users_list = admin_client.auth.admin.list_users()
                    for u in users_list:
                        if getattr(u, 'email', None) == lab.email:
                            existing_id = str(u.id)
                            # Check if a lab row exists for this auth user
                            lab_check = supabase.table("labs").select("id").eq("id", existing_id).execute()
                            if not lab_check.data:
                                # Orphan! Delete old auth user and create fresh
                                log.info("[admin_api] Deleting orphaned auth user %s", existing_id)
                                admin_client.auth.admin.delete_user(existing_id)
                                # Re-create
                                auth_response = admin_client.auth.admin.create_user({
                                    "email": lab.email,
                                    "password": lab.password,
                                    "email_confirm": True
                                })
                                user = auth_response.user
                            else:
                                raise HTTPException(400, f"A lab with email {lab.email} already exists.")
                            break
                    if user is None:
                        raise HTTPException(400, f"Auth user with email {lab.email} exists but could not be resolved.")
                except HTTPException:
                    raise
                except Exception as inner_err:
                    log.error("[admin_api] Orphan cleanup failed: %s", inner_err)
                    raise HTTPException(400, f"Failed to handle existing auth user: {str(inner_err)}")
            else:
                raise  # Re-raise non-duplicate errors

        if not user or not user.id:
            raise HTTPException(500, "Auth creation failed — no user returned.")

        lab_id = str(user.id)

        # 2. Insert into public.labs
        row = {
            "id": lab_id,
            "business_name": lab.business_name,
            "exotel_number": lab.exotel_number,
            "email": lab.email,
            "password": lab.password,  # Kept for master admin reference only
        }
        if lab.collector_phone:
            row["collector_phone"] = lab.collector_phone
        if lab.receptionist_phone:
            row["receptionist_phone"] = lab.receptionist_phone
        if lab.whatsapp_phone_number_id:
            row["whatsapp_phone_number_id"] = lab.whatsapp_phone_number_id
        if lab.whatsapp_access_token:
            row["whatsapp_access_token"] = lab.whatsapp_access_token
        if lab.services is not None:
            row["services"] = lab.services
        if lab.financial_password:
            row["financial_password"] = _hash_password(lab.financial_password)

        supabase.table("labs").insert(row).execute()

        return {"status": "success", "lab_id": lab_id, "business_name": lab.business_name}

    except HTTPException:
        raise
    except Exception as e:
        log.error("[admin_api] Create lab error: %s", e)
        raise HTTPException(400, "Failed to create lab. Check inputs and try again.")


@router.patch("/labs/{lab_id}")
async def update_lab(lab_id: str, updates: LabUpdate, admin_id: str = Depends(verify_master_admin)):
    """Update a lab's details."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            return {"status": "success", "message": "No changes provided"}

        # Hash financial_password if being updated
        if "financial_password" in update_data and update_data["financial_password"]:
            update_data["financial_password"] = _hash_password(update_data["financial_password"])

        supabase.table("labs").update(update_data).eq("id", lab_id).execute()
        return {"status": "success", "message": "Lab updated successfully."}
    except Exception as e:
        log.error("[admin_api] Update lab error: %s", e)
        raise HTTPException(500, "Failed to update lab.")


@router.delete("/labs/{lab_id}")
async def delete_lab(lab_id: str, data: LabDelete, admin_id: str = Depends(verify_master_admin)):
    """Delete a lab. Requires Master Admin password verification."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")

    admin_client = _get_admin_client()
    if admin_client is None:
        raise HTTPException(503, "Service role key not configured.")

    # ── Verify master admin password via Supabase Auth ──────────────────
    try:
        admin_user = admin_client.auth.admin.get_user_by_id(admin_id)
        admin_email = admin_user.user.email if admin_user and admin_user.user else None
        if not admin_email:
            raise HTTPException(401, "Could not verify admin identity.")

        # Attempt sign-in with the provided password to verify it
        verify_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        verify_client.auth.sign_in_with_password({"email": admin_email, "password": data.password})
        log.info("[admin_api] Master admin password verified for delete operation.")
    except HTTPException:
        raise
    except Exception as e:
        log.warning("[admin_api] Delete password verification failed: %s", e)
        raise HTTPException(403, "Incorrect admin password.")

    try:
        # Delete from public.labs first (triggers ON DELETE CASCADE)
        supabase.table("labs").delete().eq("id", lab_id).execute()
        log.info("[admin_api] Lab %s deleted from DB (cascade wiped all data).", lab_id)

        # Delete the auth account
        admin_client.auth.admin.delete_user(lab_id)
        log.info("[admin_api] Auth user %s deleted.", lab_id)

        return {"status": "success", "message": "Lab and all associated data permanently deleted."}
    except Exception as e:
        log.error("[admin_api] Delete lab error: %s", e)
        raise HTTPException(500, "Failed to delete lab.")


@router.post("/labs/{lab_id}/verify-financial-password")
async def verify_financial_password(lab_id: str, data: FinancialPasswordVerify, admin_id: str = Depends(verify_master_admin)):
    """Verify the financial password of a lab."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        lab_res = supabase.table("labs").select("financial_password, password").eq("id", lab_id).execute()
        if not lab_res.data:
            raise HTTPException(404, "Lab not found.")
            
        lab_data = lab_res.data[0]
        expected_hash = lab_data.get("financial_password")
        
        if not expected_hash:
            expected_hash = lab_data.get("password")
            
        if not expected_hash:
            raise HTTPException(401, "No financial password configured for this lab.")
            
        if expected_hash.startswith("$2"):
            if not _verify_password(data.password, expected_hash):
                raise HTTPException(401, "Incorrect financial password.")
        else:
            if expected_hash != data.password:
                raise HTTPException(401, "Incorrect financial password.")
                
        return {"status": "success", "message": "Password verified."}
    except HTTPException:
        raise
    except Exception as e:
        log.error("[admin_api] Verify financial password error: %s", e)
        raise HTTPException(500, "Failed to verify password.")


@router.get("/labs/{lab_id}/metrics")
async def get_lab_metrics(lab_id: str, admin_id: str = Depends(verify_master_admin)):
    """Get usage metrics for a specific lab."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        patients_res = supabase.table("patients").select("payment_amount, report_link").eq("lab_id", lab_id).execute()
        patients = patients_res.data or []
        
        total_patients = len(patients)
        total_reports = sum(1 for p in patients if p.get("report_link") is not None)
        total_revenue = sum(float(p.get("payment_amount") or 0) for p in patients)
        
        # Simple avg monthly calculation (assume 1 month for now if just starting out)
        # In a real app, you'd calculate based on first_patient_date to now
        avg_monthly_revenue = total_revenue
        
        # 2. Fetch usage costs
        usage_res = supabase.table("resource_usage").select("service_type, cost_incurred").eq("lab_id", lab_id).execute()
        usage_records = usage_res.data or []
        
        saas_costs = {
            "total_cost": 0.0,
            "openai_llm": 0.0,
            "openai_tts": 0.0,
            "deepgram_stt": 0.0,
            "exotel_voice": 0.0
        }
        
        for record in usage_records:
            cost = float(record.get("cost_incurred") or 0)
            svc = record.get("service_type", "unknown")
            saas_costs["total_cost"] += cost
            if svc in saas_costs:
                saas_costs[svc] += cost
        
        return {
            "total_patients": total_patients,
            "total_reports": total_reports,
            "total_revenue": total_revenue,
            "avg_monthly_revenue": avg_monthly_revenue,
            "saas_costs": saas_costs
        }
    except Exception as e:
        log.error("[admin_api] Get lab metrics error: %s", e)
        raise HTTPException(500, "Failed to fetch metrics.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Lab Bills Management
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/labs/{lab_id}/bills")
async def list_bills(lab_id: str, admin_id: str = Depends(verify_master_admin)):
    """List bills for a specific lab."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    try:
        response = (
            supabase.table("lab_bills")
            .select("*")
            .eq("lab_id", lab_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"bills": response.data or []}
    except Exception as e:
        log.error("[admin_api] List bills error: %s", e)
        raise HTTPException(500, "Failed to fetch bills.")


@router.post("/labs/{lab_id}/bills")
async def create_bill(lab_id: str, bill: LabBillCreate, admin_id: str = Depends(verify_master_admin)):
    """Create a new bill for a lab and optionally notify via WhatsApp."""
    if supabase is None:
        raise HTTPException(503, "Database not configured.")
        
    row = {
        "lab_id": lab_id,
        "amount": bill.amount,
        "description": bill.description,
        "status": "unpaid"
    }
    
    try:
        # Save to DB
        response = supabase.table("lab_bills").insert(row).execute()
        new_bill = response.data[0] if response.data else {}
        
        # Send WhatsApp Notification
        if bill.notify_whatsapp:
            lab_res = supabase.table("labs").select("business_name, exotel_number").eq("id", lab_id).execute()
            if lab_res.data:
                lab_info = lab_res.data[0]
                business_name = lab_info.get("business_name", "Lab")
                exotel_num = lab_info.get("exotel_number")
                
                if exotel_num:
                    try:
                        to_number = settings.TEST_PHONE_NUMBER or exotel_num
                        
                        msg_body = f"Hello {business_name}, your SaaS usage bill for ₹{bill.amount} has been generated for: {bill.description}."
                        
                        # Meta WhatsApp API expects phone numbers without the '+' sign
                        to_wa = to_number.replace("+", "").strip()
                        
                        await whatsapp_service.send_text_message(
                            to=to_wa,
                            text=msg_body
                        )
                        log.info(f"WhatsApp bill notification sent to {to_number}")
                    except Exception as wa_err:
                        log.error(f"WhatsApp Meta error: {str(wa_err)}")
                        # We don't fail the request if just the notification fails, but we log it.
        
        return {"status": "success", "bill": new_bill}
    except Exception as e:
        log.error("[admin_api] Create bill error: %s", e)
        raise HTTPException(500, "Failed to create bill.")
