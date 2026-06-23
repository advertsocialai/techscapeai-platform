"""Workflow + steps CRUD against Supabase."""
from __future__ import annotations
import logging
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── Workflows ────────────────────────────────────────────
    def list_workflows(self, business_id: UUID, *, include_archived: bool = False) -> list[dict]:
        q = self.db.table("ts_workflows").select("*").eq("business_id", str(business_id))
        if not include_archived:
            q = q.eq("is_archived", False)
        return q.order("created_at", desc=True).execute().data or []

    def get_workflow(self, workflow_id: UUID, business_id: UUID) -> dict | None:
        wf = (
            self.db.table("ts_workflows")
            .select("*")
            .eq("id", str(workflow_id))
            .eq("business_id", str(business_id))
            .limit(1)
            .execute()
            .data
        )
        if not wf:
            return None
        steps = (
            self.db.table("ts_workflow_steps")
            .select("*")
            .eq("workflow_id", str(workflow_id))
            .order("step_number")
            .execute()
            .data
            or []
        )
        return {**wf[0], "steps": steps}

    def create_workflow(self, business_id: UUID, payload: dict[str, Any]) -> dict:
        steps = payload.pop("steps", [])
        # Schema defaults — make explicit so the row is consistent regardless
        # of whether the driver applies Postgres DEFAULTs.
        defaults: dict[str, Any] = {
            "is_active":              True,
            "is_archived":            False,
            "version":                1,
            "execution_count":        0,
            "success_rate":           0.0,
            "estimated_monthly_cost": 0.0,
            "trigger_config":         {},
        }
        row = {**defaults, **payload, "business_id": str(business_id)}
        wf = self.db.table("ts_workflows").insert(row).execute().data[0]
        if steps:
            for s in steps:
                s.setdefault("enabled", True)
                s.setdefault("delay_seconds", 0)
                s.setdefault("max_retries", 3)
                s.setdefault("retry_delay_seconds", 300)
                s.setdefault("timeout_seconds", 3600)
                s.setdefault("condition_type", "none")
                s["workflow_id"] = wf["id"]
            self.db.table("ts_workflow_steps").insert(steps).execute()
        return self.get_workflow(UUID(wf["id"]), business_id) or wf

    def update_workflow(self, workflow_id: UUID, business_id: UUID, patch: dict[str, Any]) -> dict | None:
        if not patch:
            return self.get_workflow(workflow_id, business_id)
        self.db.table("ts_workflows").update(patch).eq("id", str(workflow_id)).eq(
            "business_id", str(business_id)
        ).execute()
        return self.get_workflow(workflow_id, business_id)

    def delete_workflow(self, workflow_id: UUID, business_id: UUID) -> bool:
        r = (
            self.db.table("ts_workflows")
            .update({"is_archived": True, "is_active": False})
            .eq("id", str(workflow_id))
            .eq("business_id", str(business_id))
            .execute()
        )
        return bool(r.data)

    def set_active(self, workflow_id: UUID, business_id: UUID, is_active: bool) -> dict | None:
        return self.update_workflow(workflow_id, business_id, {"is_active": is_active})

    # ── Steps ────────────────────────────────────────────────
    def add_step(self, workflow_id: UUID, step: dict[str, Any]) -> dict:
        step.setdefault("enabled", True)
        step.setdefault("delay_seconds", 0)
        step.setdefault("max_retries", 3)
        step.setdefault("retry_delay_seconds", 300)
        step.setdefault("timeout_seconds", 3600)
        step.setdefault("condition_type", "none")
        step["workflow_id"] = str(workflow_id)
        return self.db.table("ts_workflow_steps").insert(step).execute().data[0]

    def update_step(self, step_id: UUID, patch: dict[str, Any]) -> dict | None:
        r = self.db.table("ts_workflow_steps").update(patch).eq("id", str(step_id)).execute()
        return r.data[0] if r.data else None

    def delete_step(self, step_id: UUID) -> bool:
        r = self.db.table("ts_workflow_steps").delete().eq("id", str(step_id)).execute()
        return bool(r.data)

    def reorder_steps(self, workflow_id: UUID, ordered_step_ids: list[UUID]) -> list[dict]:
        results: list[dict] = []
        for new_num, sid in enumerate(ordered_step_ids, start=1):
            r = (
                self.db.table("ts_workflow_steps")
                .update({"step_number": new_num})
                .eq("id", str(sid))
                .eq("workflow_id", str(workflow_id))
                .execute()
            )
            if r.data:
                results.extend(r.data)
        return results

    def duplicate(self, workflow_id: UUID, business_id: UUID) -> dict | None:
        """Clone a workflow + every step. Returns the new workflow."""
        original = self.get_workflow(workflow_id, business_id)
        if not original:
            return None
        clone_payload = {
            "name":               f"{original['name']} (copy)",
            "description":        original.get("description"),
            "trigger_type":       original["trigger_type"],
            "trigger_event_type": original.get("trigger_event_type"),
            "trigger_config":     original.get("trigger_config") or {},
            "is_active":          False,
            "is_archived":        False,
            "version":            1,
            "execution_count":    0,
            "success_rate":       0.0,
            "estimated_monthly_cost": 0.0,
            "created_by_user_id": original.get("created_by_user_id"),
            "steps": [
                {k: v for k, v in s.items()
                 if k in ("step_number", "action_type", "action_config",
                          "condition_type", "condition_logic", "delay_seconds",
                          "max_retries", "retry_delay_seconds", "timeout_seconds",
                          "enabled")}
                for s in (original.get("steps") or [])
            ],
        }
        return self.create_workflow(business_id, clone_payload)
