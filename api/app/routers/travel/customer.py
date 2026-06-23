"""Customer Memory endpoints — profiles, preferences, past trips."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.schemas.travel import CustomerProfileIn, CustomerProfileOut
from app.services.travel import CustomerMemoryService
from app.routers.techscape._deps import require_business

router = APIRouter()


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


@router.post("/{profile_id}/past-trips", response_model=CustomerProfileOut)
def append_past_trip(
    profile_id: UUID, trip: _PastTrip, biz: dict = Depends(require_business),
):
    cur = CustomerMemoryService().get(profile_id, UUID(biz["id"]))
    if not cur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    row = CustomerMemoryService().append_past_trip(profile_id, trip.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to append")
    return row
