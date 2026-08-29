"""
Authentication middleware for Lab Booking SaaS.

Auth strategy:
  1. Supabase JWT — for dashboard/lab API endpoints (lab receptionist)
     Extracts lab_id from the JWT's `sub` claim (Supabase Auth user UUID = lab_id)

Usage in FastAPI:
    from app.core.auth import get_current_lab_id

    @router.post("/payment")
    async def payment(body: PaymentRequest, lab_id: str = Depends(get_current_lab_id)):
        ...  # lab_id is verified, only this lab's data is accessible
"""
import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

log = logging.getLogger(__name__)

# ── Supabase JWT verification ────────────────────────────────────────────────
# We use Supabase's own JWT verification via the PostgREST-compatible approach:
#   - Decode the JWT using the Supabase JWT secret
#   - Extract `sub` (user UUID) as the lab_id
#
# For simplicity and reliability, we verify the token by calling Supabase Auth
# getUser() which handles expiry, revocation, etc.

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_lab_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """
    Dependency that extracts and verifies the lab_id from a Supabase JWT.

    Returns:
        lab_id (str): The authenticated lab's UUID.

    Raises:
        HTTPException 401: If no token or invalid token.
        HTTPException 403: If token is valid but user is not a lab owner.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization token.")

    token = credentials.credentials

    # ── Verify token via Supabase Auth API ────────────────────────────────
    try:
        from app.db.supabase import supabase

        if supabase is None:
            raise HTTPException(status_code=503, detail="Authentication service unavailable.")

        # Supabase client.auth.get_user(token) verifies the JWT and returns user
        user_response = supabase.auth.get_user(token)
        user = user_response.user

        if not user or not user.id:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")

        lab_id = str(user.id)
        log.info("[auth] Authenticated lab: %s", lab_id)
        return lab_id

    except HTTPException:
        raise
    except Exception as e:
        log.error("[auth] Token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Token verification failed.")


async def get_optional_lab_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[str]:
    """
    Same as get_current_lab_id but returns None instead of raising 401.
    Used for endpoints that work with or without auth (e.g., dev/test endpoints).
    """
    if not credentials:
        return None
    try:
        return await get_current_lab_id(request, credentials)
    except HTTPException:
        return None


def verify_booking_ownership(booking_lab_id: str, authenticated_lab_id: str) -> None:
    """
    Ensure the booking belongs to the authenticated lab.
    Call this after fetching a booking from the DB.

    Raises:
        HTTPException 403 if the lab doesn't own this booking.
    """
    if booking_lab_id != authenticated_lab_id:
        log.warning(
            "[auth] Lab %s tried to access booking owned by lab %s",
            authenticated_lab_id, booking_lab_id,
        )
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this booking.",
        )


async def verify_master_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """
    Dependency that ensures the authenticated user is the Master Admin.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
        
    token = credentials.credentials
    try:
        from app.db.supabase import supabase
        if supabase is None:
            raise HTTPException(status_code=503, detail="Database not configured.")
            
        user_response = supabase.auth.get_user(token)
        user = user_response.user
        
        if not user or not user.email:
            raise HTTPException(status_code=401, detail="Invalid token.")
            
        if user.email != settings.MASTER_ADMIN_EMAIL:
            log.warning("[auth] Unauthorized master admin attempt by %s", user.email)
            raise HTTPException(status_code=403, detail="Access denied. Super Admin only.")
            
        return str(user.id)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[auth] Master Admin verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Verification failed.")
