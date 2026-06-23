"""
GDPR / CCPA helpers:
  • export_business(): gathers everything tied to a business into a single dict
  • erase_business(): hard-delete cascade + tombstones a contact's PII
  • erase_contact(): scrub a single contact's PII (right-to-be-forgotten)
"""
from __future__ import annotations
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin


_TABLES = (
    "ts_workflows", "ts_workflow_steps", "ts_communication_templates",
    "ts_workflow_executions", "ts_communication_logs",
    "ts_api_integrations", "ts_webhook_queue", "ts_business_contacts",
    "ts_workflow_analytics", "ts_billing_records", "ts_audit_logs",
)


class GDPRService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def export_business(self, business_id: UUID) -> dict[str, Any]:
        out: dict[str, Any] = {}
        biz = (
            self.db.table("ts_businesses").select("*")
            .eq("id", str(business_id)).execute().data or []
        )
        out["ts_businesses"] = [{k: v for k, v in (biz[0] if biz else {}).items()
                                  if k != "api_key_hash"}]
        for t in _TABLES:
            try:
                out[t] = (
                    self.db.table(t).select("*").eq("business_id", str(business_id)).execute().data or []
                )
            except Exception:
                out[t] = []
        # never leak ciphertext blobs
        for row in out.get("ts_api_integrations", []):
            row.pop("credentials_encrypted", None)
        return out

    def erase_business(self, business_id: UUID) -> dict[str, int]:
        """Cascade delete then anonymise the business row itself."""
        deleted: dict[str, int] = {}
        for t in _TABLES:
            try:
                r = self.db.table(t).delete().eq("business_id", str(business_id)).execute()
                deleted[t] = len(r.data or [])
            except Exception:
                deleted[t] = 0
        # tombstone the business
        self.db.table("ts_businesses").update({
            "name":          "[ERASED]",
            "contact_email": f"erased-{str(business_id)[:8]}@deleted.local",
            "contact_phone": None,
            "website_url":   None,
            "status":        "inactive",
        }).eq("id", str(business_id)).execute()
        return deleted

    def erase_contact(self, *, contact_id: UUID, business_id: UUID) -> bool:
        """Right-to-be-forgotten on a single client contact: scrub PII, mark DNC."""
        r = self.db.table("ts_business_contacts").update({
            "email":            None,
            "phone":            None,
            "name":             "[ERASED]",
            "do_not_contact":   True,
            "consent_email":    False,
            "consent_sms":      False,
            "consent_whatsapp": False,
            "consent_voice":    False,
            "metadata":         {},
            "tags":             [],
        }).eq("id", str(contact_id)).eq("business_id", str(business_id)).execute()
        return bool(r.data)
