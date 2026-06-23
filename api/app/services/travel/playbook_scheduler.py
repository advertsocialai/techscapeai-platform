"""
TravelWorkflow OS — time-based scheduler.

Finds bookings whose `departure_date` / `return_date` / `balance_due_date`
match the anchor + offset of a scheduled UC, then asks the executor to
dispatch each one. A UNIQUE index on (business_id, use_case_id, booking_id)
guarantees a scheduled UC only fires once per booking.

This is intentionally pull-based — call it from a cron / queue worker
(every 5 minutes is fine) or via `/playbooks/scheduled/run-due` for demos.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

from . import playbooks as pb_registry
from .playbook_executor import PlaybookExecutor

logger = logging.getLogger(__name__)


# Map of UC → (anchor field on booking, offset in days)
# offset_minutes < 0 means BEFORE the anchor; > 0 means AFTER.
def _scheduled_ucs() -> list[tuple[str, str, int]]:
    """Returns (uc_id, anchor_field, day_offset)."""
    items: list[tuple[str, str, int]] = []
    field_map = {
        "departure_date": "departure_date",
        "return_date":    "return_date",
        "balance_due":    "balance_due_date",
        "booking_confirmed": "created_at",
    }
    for uc_id, spec in pb_registry.PLAYBOOKS.items():
        sched = spec.get("schedule") or {}
        anchor = sched.get("anchor")
        field = field_map.get(anchor)
        if not field:
            continue
        days = (sched.get("offset_minutes") or 0) // (24 * 60)
        items.append((uc_id, field, days))
    return items


class PlaybookScheduler:
    def __init__(self) -> None:
        self.db   = get_supabase_admin()
        self.exec = PlaybookExecutor()

    def due(self, business_id: UUID, *, on_date: date | None = None) -> list[dict[str, Any]]:
        """List bookings whose anchor + offset lands on `on_date` (default today)."""
        target = on_date or date.today()
        bookings = (
            self.db.table("travel_bookings").select("*")
            .eq("business_id", str(business_id))
            .in_("status", ["confirmed", "in_progress"])
            .execute().data or []
        )
        due_items: list[dict[str, Any]] = []
        already_fired = self._already_fired(business_id)

        for uc_id, field, day_offset in _scheduled_ucs():
            for bkg in bookings:
                anchor_val = bkg.get(field)
                if not anchor_val:
                    continue
                anchor_date = self._to_date(anchor_val)
                if anchor_date is None:
                    continue
                fire_date = anchor_date + timedelta(days=day_offset)
                if fire_date != target:
                    continue
                key = (uc_id, bkg["id"])
                if key in already_fired:
                    continue
                due_items.append({
                    "use_case_id": uc_id,
                    "booking_id":  bkg["id"],
                    "booking_ref": bkg.get("booking_ref"),
                    "anchor":      field,
                    "anchor_date": anchor_date.isoformat(),
                    "fire_date":   fire_date.isoformat(),
                    "title":       pb_registry.PLAYBOOKS[uc_id]["title"],
                })
        return due_items

    async def run_due(
        self, business: dict, *, on_date: date | None = None, dry_run: bool = True,
    ) -> dict[str, Any]:
        business_id = UUID(business["id"])
        items = self.due(business_id, on_date=on_date)
        dispatched: list[dict] = []
        for item in items:
            bkg = (
                self.db.table("travel_bookings").select("*")
                .eq("id", item["booking_id"]).limit(1).execute().data
            )
            if not bkg:
                continue
            bkg = bkg[0]
            customer = None
            if bkg.get("customer_id"):
                cu = (
                    self.db.table("travel_customer_profiles").select("*")
                    .eq("id", bkg["customer_id"]).limit(1).execute().data
                )
                customer = cu[0] if cu else None
            ctx = self.exec.build_context(business=business, booking=bkg, customer=customer)
            row = await self.exec.dispatch(
                business_id=business_id,
                uc_id=item["use_case_id"],
                context=ctx,
                booking_id=UUID(bkg["id"]),
                customer_id=UUID(bkg["customer_id"]) if bkg.get("customer_id") else None,
                to_email=(customer or {}).get("email"),
                to_phone=(customer or {}).get("phone"),
                trigger_kind="schedule",
                dry_run=dry_run,
            )
            dispatched.append({"use_case_id": item["use_case_id"],
                                "booking_ref": item["booking_ref"],
                                "run_id":      row.get("id"),
                                "status":      row.get("status")})
        return {"date": (on_date or date.today()).isoformat(),
                "dispatched": dispatched, "count": len(dispatched)}

    # helpers ──────────────────────────────────────────────
    def _already_fired(self, business_id: UUID) -> set[tuple[str, str]]:
        rows = (
            self.db.table("travel_playbook_runs")
            .select("use_case_id,booking_id")
            .eq("business_id", str(business_id))
            .eq("trigger_kind", "schedule")
            .execute().data or []
        )
        return {(r["use_case_id"], r["booking_id"])
                for r in rows if r.get("booking_id")}

    @staticmethod
    def _to_date(v: Any) -> date | None:
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None
