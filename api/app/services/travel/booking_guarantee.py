"""
Booking Guarantee Service — Attack Point 3 from the strategy doc.

Verifies supplier confirmations 24h before check-in. When a supplier fails,
records the failure and (optionally) records a re-allocation to an alternative.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)


class BookingGuaranteeService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def create(self, business_id: UUID, *, itinerary_id: UUID,
               supplier_id: UUID, booking_ref: Optional[str],
               checkin_at: datetime) -> dict:
        row = self.db.table("travel_booking_guarantees").insert({
            "business_id":  str(business_id),
            "itinerary_id": str(itinerary_id),
            "supplier_id":  str(supplier_id),
            "booking_ref":  booking_ref,
            "checkin_at":   checkin_at.isoformat(),
            "verification_status": "pending",
        }).execute().data[0]
        return row

    def list(self, business_id: UUID, *,
             status: Optional[str] = None, limit: int = 100) -> list[dict]:
        q = (
            self.db.table("travel_booking_guarantees").select("*")
            .eq("business_id", str(business_id))
        )
        if status:
            q = q.eq("verification_status", status)
        return q.order("checkin_at").limit(limit).execute().data or []

    def due_for_verification(self, business_id: UUID,
                             *, hours_before: int = 24) -> list[dict]:
        """All pending records whose check-in is within `hours_before` hours."""
        now    = datetime.now(timezone.utc)
        cutoff = (now + timedelta(hours=hours_before)).isoformat()
        return (
            self.db.table("travel_booking_guarantees").select("*")
            .eq("business_id", str(business_id))
            .eq("verification_status", "pending")
            .lte("checkin_at", cutoff)
            .order("checkin_at")
            .execute().data or []
        )

    def mark_verified(self, guarantee_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_booking_guarantees").update({
                "verification_status": "verified",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", str(guarantee_id))
            .eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    def mark_failed(self, guarantee_id: UUID, business_id: UUID, *,
                    reason: str, alternative_id: Optional[UUID] = None) -> dict | None:
        patch = {
            "verification_status": "reallocated" if alternative_id else "failed",
            "verified_at":         datetime.now(timezone.utc).isoformat(),
            "failure_reason":      reason,
        }
        if alternative_id:
            patch["alternative_id"] = str(alternative_id)
        r = (
            self.db.table("travel_booking_guarantees").update(patch)
            .eq("id", str(guarantee_id))
            .eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None
