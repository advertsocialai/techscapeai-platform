"""Traveller authentication — public OTP login scoped by agency subdomain (Phase 3.3)."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr

from app.core.security import issue_access_token
from app.services.travel import CustomerMemoryService
from app.routers.techscape.auth import _verify_otp

router = APIRouter()


def _extract_business_id_from_subdomain(request: Request) -> Optional[UUID]:
    """Extract business_id by resolving subdomain to agency.

    For Phase 3.3 multi-agency support: each agency gets a subdomain
    (e.g. "agencyname.klara.ai" or "agencyname.localhost:8000").
    In production, this would query a subdomain→business_id mapping.
    For now, this placeholder returns None — traveller login accepts
    explicit business_id as a query parameter until the mapping exists.
    """
    # TODO(Phase 3.3): Implement subdomain→business_id lookup
    # - Query ts_businesses WHERE subdomain = extracted_subdomain
    # - Return business_id if found, else None
    return None


class TravellerLoginIn(BaseModel):
    email: EmailStr
    code: str


class TravellerTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_min: int


@router.post("/login", response_model=TravellerTokenOut)
def traveller_login(
    payload: TravellerLoginIn,
    request: Request,
    business_id: str = Query(..., description="Business ID / agency UUID")
):
    """Traveller OTP login scoped to agency subdomain.

    1. Verify OTP (shared pool with business registration)
    2. Lookup travel_customer_profile by (business_id, email)
    3. Issue a read-only JWT token for the traveller

    Flow:
    - Traveller visits https://agencyname.klara.ai
    - Calls POST /api/travel/traveller/otp/send with email
    - Receives OTP via email
    - Calls POST /api/travel/traveller/login with email + code + business_id
    """
    # Verify OTP (reusing the shared pool from business auth)
    valid = _verify_otp(str(payload.email), payload.code)
    if not valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid or expired OTP"
        )

    # Scope lookup to this business only
    try:
        biz_id = UUID(business_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid business ID format")

    svc = CustomerMemoryService()
    profile = svc.find_by_email(biz_id, str(payload.email))
    if not profile:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No customer profile found for this email"
        )

    # Issue traveller token (scoped to this profile + business)
    # Use profile["id"] as the JWT subject, carry business_id for multi-tenant safety
    access = issue_access_token(
        sub=profile["id"],
        business_id=str(biz_id),
        role="traveller"  # read-only access
    )

    return TravellerTokenOut(
        access_token=access,
        expires_in_min=15,  # short-lived for traveller sessions
    )
