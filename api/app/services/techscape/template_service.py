"""Communication template CRUD + variable interpolation."""
from __future__ import annotations
import re
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class TemplateService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def list(self, business_id: UUID, *, channel: str | None = None) -> list[dict]:
        q = self.db.table("ts_communication_templates").select("*").eq(
            "business_id", str(business_id)
        )
        if channel:
            q = q.eq("channel", channel)
        return q.order("created_at", desc=True).execute().data or []

    def get(self, template_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("ts_communication_templates")
            .select("*")
            .eq("id", str(template_id))
            .eq("business_id", str(business_id))
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def create(self, business_id: UUID, payload: dict[str, Any]) -> dict:
        # auto-detect variables if not provided
        if not payload.get("variables"):
            payload["variables"] = sorted(set(VAR_RE.findall(payload.get("content", ""))))
        defaults = {
            "approval_status": "draft",
            "usage_count":     0,
            "conversion_rate": 0.0,
            "is_ai_generated": False,
            "media_urls":      [],
        }
        row = {**defaults, **payload, "business_id": str(business_id)}
        return self.db.table("ts_communication_templates").insert(row).execute().data[0]

    def update(self, template_id: UUID, business_id: UUID, patch: dict[str, Any]) -> dict | None:
        if "content" in patch and "variables" not in patch:
            patch["variables"] = sorted(set(VAR_RE.findall(patch["content"])))
        r = (
            self.db.table("ts_communication_templates")
            .update(patch)
            .eq("id", str(template_id))
            .eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    def delete(self, template_id: UUID, business_id: UUID) -> bool:
        r = (
            self.db.table("ts_communication_templates")
            .delete()
            .eq("id", str(template_id))
            .eq("business_id", str(business_id))
            .execute()
        )
        return bool(r.data)

    @staticmethod
    def render(content: str, sample: dict[str, Any]) -> str:
        """Replace {{var}} placeholders with values from sample (dot notation supported)."""
        def _resolve(path: str) -> str:
            cur: Any = sample
            for part in path.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part, "")
                else:
                    return ""
            return str(cur)
        return VAR_RE.sub(lambda m: _resolve(m.group(1)), content)
