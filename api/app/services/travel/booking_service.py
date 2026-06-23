"""Booking service — CRUD for travel_bookings (the playbook trigger anchor)."""
from __future__ import annotations
from datetime import date
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin


class BookingService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def create(self, *, business_id: UUID, payload: dict) -> dict:
        data = {"business_id": str(business_id), **payload}
        data = {k: v for k, v in data.items() if v is not None}
        return self.db.table("travel_bookings").insert(data).execute().data[0]

    def get(self, booking_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_bookings").select("*")
            .eq("id", str(booking_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def by_ref(self, business_id: UUID, booking_ref: str) -> dict | None:
        r = (
            self.db.table("travel_bookings").select("*")
            .eq("business_id", str(business_id)).eq("booking_ref", booking_ref)
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def list(
        self, business_id: UUID, *,
        status: Optional[str] = None, limit: int = 100,
    ) -> list[dict]:
        q = self.db.table("travel_bookings").select("*").eq("business_id", str(business_id))
        if status:
            q = q.eq("status", status)
        return q.order("created_at", desc=True).limit(limit).execute().data or []

    def update(self, booking_id: UUID, business_id: UUID, patch: dict) -> dict | None:
        clean = {k: v for k, v in (patch or {}).items() if v is not None}
        if not clean:
            return self.get(booking_id, business_id)
        r = (
            self.db.table("travel_bookings").update(clean)
            .eq("id", str(booking_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None
