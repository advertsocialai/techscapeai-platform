"""
Customer Memory Service — preferences, past trips, language across sessions.
"""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin


class CustomerMemoryService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def get(self, profile_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_customer_profiles").select("*")
            .eq("id", str(profile_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def find_by_email(self, business_id: UUID, email: str) -> dict | None:
        r = (
            self.db.table("travel_customer_profiles").select("*")
            .eq("business_id", str(business_id))
            .eq("email", email.lower()).limit(1).execute()
        )
        return r.data[0] if r.data else None

    def upsert(self, business_id: UUID, payload: dict[str, Any]) -> dict:
        defaults = {"preferences": {}, "past_trips": [], "family_profile": {}, "language": "en"}
        row = {**defaults, **payload, "business_id": str(business_id)}
        if "email" in row and row["email"]:
            row["email"] = row["email"].lower()
            return (
                self.db.table("travel_customer_profiles")
                .upsert(row, on_conflict="business_id,email")
                .execute().data[0]
            )
        return self.db.table("travel_customer_profiles").insert(row).execute().data[0]

    def upsert_from_intent(
        self, *, business_id: UUID, intent: str,
        email: Optional[str] = None, name: Optional[str] = None,
        phone: Optional[str] = None, language: str = "en",
        customer_id: Optional[UUID] = None,
    ) -> dict | None:
        if customer_id:
            return self.get(customer_id, business_id)
        if email:
            existing = self.find_by_email(business_id, email)
            if existing:
                return existing
            return self.upsert(business_id, {
                "email": email, "full_name": name, "phone": phone,
                "language": language, "last_intent": intent,
            })
        if name or phone:
            return self.upsert(business_id, {
                "full_name": name, "phone": phone,
                "language": language, "last_intent": intent,
            })
        return None

    def set_last_intent(self, profile_id: UUID, intent: str) -> None:
        self.db.table("travel_customer_profiles").update(
            {"last_intent": intent}
        ).eq("id", str(profile_id)).execute()

    def append_past_trip(self, profile_id: UUID, summary: dict) -> dict | None:
        cur = (
            self.db.table("travel_customer_profiles").select("past_trips")
            .eq("id", str(profile_id)).limit(1).execute().data
        )
        if not cur:
            return None
        trips = list(cur[0].get("past_trips") or [])
        trips.append(summary)
        r = self.db.table("travel_customer_profiles").update(
            {"past_trips": trips}
        ).eq("id", str(profile_id)).execute()
        return r.data[0] if r.data else None
