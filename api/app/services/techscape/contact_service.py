"""Business contact CRUD."""
from __future__ import annotations
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin


class ContactService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def list(self, business_id: UUID, *, search: str | None = None, limit: int = 200) -> list[dict]:
        q = self.db.table("ts_business_contacts").select("*").eq("business_id", str(business_id))
        if search:
            q = q.or_(f"name.ilike.%{search}%,email.ilike.%{search}%,phone.ilike.%{search}%")
        return q.order("created_at", desc=True).limit(limit).execute().data or []

    def get(self, contact_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("ts_business_contacts").select("*")
            .eq("id", str(contact_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def upsert(self, business_id: UUID, payload: dict[str, Any]) -> dict:
        defaults = {
            "do_not_contact":   False,
            "consent_email":    True,
            "consent_sms":      True,
            "consent_whatsapp": True,
            "consent_voice":    True,
            "tags":             [],
            "metadata":         {},
        }
        row = {**defaults, **payload, "business_id": str(business_id)}
        # Using upsert on (business_id, email) when email present
        if row.get("email"):
            return (
                self.db.table("ts_business_contacts")
                .upsert(row, on_conflict="business_id,email")
                .execute()
                .data[0]
            )
        return self.db.table("ts_business_contacts").insert(row).execute().data[0]

    def update(self, contact_id: UUID, business_id: UUID, patch: dict[str, Any]) -> dict | None:
        r = (
            self.db.table("ts_business_contacts").update(patch)
            .eq("id", str(contact_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    def delete(self, contact_id: UUID, business_id: UUID) -> bool:
        r = (
            self.db.table("ts_business_contacts").delete()
            .eq("id", str(contact_id)).eq("business_id", str(business_id))
            .execute()
        )
        return bool(r.data)
