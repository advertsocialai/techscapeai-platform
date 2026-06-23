"""Bookings — the anchor record for TravelWorkflow OS scheduled UCs."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import (
    BookingIn, BookingOut, BookingPatch, BookingStatus,
)
from app.services.travel import BookingService
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(req: BookingIn, biz: dict = Depends(require_business)):
    return BookingService().create(
        business_id=UUID(biz["id"]),
        payload=req.model_dump(mode="json", exclude_none=True),
    )


@router.get("", response_model=list[BookingOut])
def list_bookings(
    status_filter: Optional[BookingStatus] = Query(default=None, alias="status"),
    limit:         int = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    return BookingService().list(UUID(biz["id"]), status=status_filter, limit=limit)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: UUID, biz: dict = Depends(require_business)):
    row = BookingService().get(booking_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return row


@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: UUID, patch: BookingPatch,
    biz: dict = Depends(require_business),
):
    row = BookingService().update(
        booking_id, UUID(biz["id"]),
        patch.model_dump(mode="json", exclude_none=True),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return row
