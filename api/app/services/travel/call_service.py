"""
Calls service (Phase 2 T7) — live call feed + transcript reads.

Assigned-only scoping mirrors leads.py's T1 pattern, joined through
lead_id: an agent-tier caller only sees calls whose lead is assigned to
them. manager+ sees the whole business, unscoped.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin


class CallService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def _assigned_lead_ids(self, business_id: UUID, assigned_agent: UUID) -> list[str]:
        rows = (
            self.db.table("travel_leads").select("id")
            .eq("business_id", str(business_id))
            .eq("assigned_agent", str(assigned_agent))
            .execute().data or []
        )
        return [r["id"] for r in rows]

    def list_live(self, business_id: UUID, *, assigned_agent: Optional[UUID] = None) -> list[dict]:
        q = (
            self.db.table("travel_calls").select("*")
            .eq("business_id", str(business_id))
            .eq("status", "active")
        )
        if assigned_agent is not None:
            lead_ids = self._assigned_lead_ids(business_id, assigned_agent)
            if not lead_ids:
                return []
            q = q.in_("lead_id", lead_ids)
        return q.order("started_at", desc=True).execute().data or []

    def get_call_scoped(self, call_id: UUID, business_id: UUID,
                        *, assigned_agent: Optional[UUID] = None) -> dict | None:
        r = (
            self.db.table("travel_calls").select("*")
            .eq("id", str(call_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        if not r.data:
            return None
        call = r.data[0]
        if assigned_agent is not None:
            lead_id = call.get("lead_id")
            if not lead_id or lead_id not in self._assigned_lead_ids(business_id, assigned_agent):
                return None
        return call

    def get_transcript(self, call_id: UUID) -> list[dict]:
        """CONTRACT: travel_transcripts carries no business_id column (see
        migration 0003) — tenancy lives on the parent travel_calls row. The
        caller MUST have resolved the call through get_call_scoped() and
        turned a None result into a 404 BEFORE calling this; get_call_scoped
        returns None rather than raising, so an unchecked result enforces
        nothing and this query would return another tenant's transcript."""
        return (
            self.db.table("travel_transcripts").select("*")
            .eq("call_id", str(call_id))
            .order("timestamp_ms").execute().data or []
        )
