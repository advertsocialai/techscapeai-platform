"""Booking Guarantee endpoints — 24h pre-checkin supplier reconfirmation."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.schemas.travel import (
    BookingGuaranteeIn, BookingGuaranteeOut, GuaranteeStatus,
)
from app.services.travel import BookingGuaranteeService
from app.routers.techscape._deps import require_business

router = APIRouter()


class _FailBody(BaseModel):
    reason:         str  = Field(min_length=1, max_length=2000)
    alternative_id: Optional[UUID] = None


@router.post("/guarantees", response_model=BookingGuaranteeOut, status_code=status.HTTP_201_CREATED)
def create_guarantee(req: BookingGuaranteeIn, biz: dict = Depends(require_business)):
    return BookingGuaranteeService().create(
        UUID(biz["id"]),
        itinerary_id=req.itinerary_id,
        supplier_id=req.supplier_id,
        booking_ref=req.booking_ref,
        checkin_at=req.checkin_at,
    )


@router.get("/guarantees", response_model=list[BookingGuaranteeOut])
def list_guarantees(
    status_filter: Optional[GuaranteeStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    return BookingGuaranteeService().list(
        UUID(biz["id"]), status=status_filter, limit=limit,
    )


@router.get("/guarantees/due", response_model=list[BookingGuaranteeOut])
def due_guarantees(
    hours_before: int = Query(default=24, ge=1, le=168),
    biz: dict = Depends(require_business),
):
    return BookingGuaranteeService().due_for_verification(
        UUID(biz["id"]), hours_before=hours_before,
    )


@router.post("/guarantees/{guarantee_id}/verify", response_model=BookingGuaranteeOut)
def verify_guarantee(guarantee_id: UUID, biz: dict = Depends(require_business)):
    row = BookingGuaranteeService().mark_verified(guarantee_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guarantee not found")
    return row


@router.post("/guarantees/{guarantee_id}/fail", response_model=BookingGuaranteeOut)
def fail_guarantee(
    guarantee_id: UUID, body: _FailBody,
    biz: dict = Depends(require_business),
):
    row = BookingGuaranteeService().mark_failed(
        guarantee_id, UUID(biz["id"]),
        reason=body.reason, alternative_id=body.alternative_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guarantee not found")
    return row
