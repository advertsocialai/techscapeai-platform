"""Customer Memory endpoints — profiles, preferences, past trips."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.deps import require_role
from app.schemas.travel import CustomerProfileIn, CustomerProfileOut
from app.services.travel import CustomerMemoryService
from app.services.travel import erasure_service
from app.routers.techscape._deps import require_business

router = APIRouter()

# D-3 right-to-erasure is destructive-adjacent: admin tier only
# (require_role("admin") == admin/super_admin — hierarchy per core/deps.py,
# same convention as the other travel routers that gate writes).
_admin = require_role("admin")


class _PastTrip(BaseModel):
    title:         str
    destination:   Optional[str] = None
    travelled_at:  Optional[str] = None
    pax_count:     Optional[int] = None
    rating:        Optional[int] = None
    notes:         Optional[str] = None


@router.get("", response_model=list[CustomerProfileOut])
def list_profiles(
    limit: int = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    svc = CustomerMemoryService()
    rows = (
        svc.db.table("travel_customer_profiles").select("*")
        .eq("business_id", biz["id"])
        .order("updated_at", desc=True).limit(limit).execute().data or []
    )
    return rows


@router.post("", response_model=CustomerProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(payload: CustomerProfileIn, biz: dict = Depends(require_business)):
    return CustomerMemoryService().upsert(UUID(biz["id"]), payload.model_dump(exclude_none=True))


@router.get("/by-email", response_model=CustomerProfileOut)
def get_by_email(email: str = Query(min_length=3), biz: dict = Depends(require_business)):
    row = CustomerMemoryService().find_by_email(UUID(biz["id"]), email)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return row


@router.get("/{profile_id}", response_model=CustomerProfileOut)
def get_profile(profile_id: UUID, biz: dict = Depends(require_business)):
    row = CustomerMemoryService().get(profile_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return row


@router.delete("/{customer_id}/personal-data")
def erase_personal_data(customer_id: UUID, user: dict = Depends(_admin)):
    """DPDP right-to-erasure (COMPLIANCE_CHECKLIST.md D-3).

    ANONYMIZES (never deletes) every personal-data row for this customer —
    see erasure_service.py's module docstring for the honest table-by-table
    enumeration. Money rows are never deleted (invoice/audit integrity).
    409 when a booking is active or a call is live (Gowtham-owned edge
    cases — refused, not guessed). Out-of-scope/unknown id → 404, never 403.
    One activity_log row records the erasure.
    """
    try:
        summary = erasure_service.erase_customer(
            str(customer_id),
            user["business_id"],
            actor_id=user.get("id"),
        )
    except erasure_service.ActiveRecordConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.detail)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return {"ok": True, "erased": summary}


@router.post("/{profile_id}/past-trips", response_model=CustomerProfileOut)
def append_past_trip(
    profile_id: UUID, trip: _PastTrip, biz: dict = Depends(require_business),
):
    cur = CustomerMemoryService().get(profile_id, UUID(biz["id"]))
    if not cur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    row = CustomerMemoryService().append_past_trip(
        profile_id, UUID(biz["id"]), trip.model_dump(exclude_none=True),
    )
    if not row:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to append")
    return row
