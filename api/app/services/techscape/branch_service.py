"""
Branch service (Phase 1).

`branches` is a dedicated table (migration 0002) — distinct from
travel_franchisees (a separate franchise-partner concept). Service-role
client only; RLS on `branches` blocks anon/authenticated entirely.
"""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin


class BranchService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def list(self, *, business_id: UUID, limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
        r = (
            self.db.table("branches").select("*", count="exact")
            .eq("business_id", str(business_id))
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return (r.data or []), (r.count or 0)

    def get(self, branch_id: UUID, *, business_id: UUID) -> dict | None:
        r = (
            self.db.table("branches").select("*")
            .eq("id", str(branch_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def create(self, *, business_id: UUID, payload: dict[str, Any]) -> dict:
        row = {
            "business_id": str(business_id),
            "name": payload["name"],
            "city": payload.get("city"),
            "status": payload.get("status", "active"),
        }
        return self.db.table("branches").insert(row).execute().data[0]

    # Phase-4 will replace this stub with real aggregates once travel_leads
    # gains a branch_id linkage and travel_calls exists (P2). For now the
    # endpoint just needs a stable shape.
    @staticmethod
    def stats_stub() -> dict[str, Any]:
        return {"leads": 0, "calls": 0, "conversion_rate": 0}
