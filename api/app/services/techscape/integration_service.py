"""
External-system integrations (booking systems, CRMs, payment gateways, custom APIs).

Stores credentials encrypted with Fernet (see app.core.security.encrypt_text /
decrypt_text). The `credentials_encrypted` column is BYTEA on the DB.
"""
from __future__ import annotations
import json
from typing import Any, Optional
from uuid import UUID

from app.core.security import decrypt_text, encrypt_text
from app.database import get_supabase_admin


class IntegrationService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def list(self, business_id: UUID) -> list[dict]:
        rows = (
            self.db.table("ts_api_integrations").select("*")
            .eq("business_id", str(business_id))
            .order("created_at", desc=True).execute().data or []
        )
        # never return ciphertext bytes to clients
        for r in rows:
            r.pop("credentials_encrypted", None)
        return rows

    def create(
        self,
        *,
        business_id: UUID,
        integration_name: str,
        integration_type: str,
        api_endpoint: Optional[str] = None,
        authentication_type: Optional[str] = None,
        credentials: Optional[dict] = None,
        webhook_url: Optional[str] = None,
        event_types: Optional[list[str]] = None,
        sync_frequency: str = "manual",
    ) -> dict:
        row: dict[str, Any] = {
            "business_id":          str(business_id),
            "integration_name":     integration_name,
            "integration_type":     integration_type,
            "api_endpoint":         api_endpoint,
            "authentication_type":  authentication_type,
            "webhook_url":          webhook_url,
            "event_types":          event_types or [],
            "sync_frequency":       sync_frequency,
            "is_active":            True,
        }
        if credentials:
            row["credentials_encrypted"] = encrypt_text(json.dumps(credentials)).decode()
        created = self.db.table("ts_api_integrations").insert(row).execute().data[0]
        created.pop("credentials_encrypted", None)
        return created

    def get_credentials(self, integration_id: UUID, business_id: UUID) -> Optional[dict]:
        r = (
            self.db.table("ts_api_integrations").select("credentials_encrypted")
            .eq("id", str(integration_id)).eq("business_id", str(business_id))
            .limit(1).execute().data
        )
        if not r or not r[0].get("credentials_encrypted"):
            return None
        try:
            txt = decrypt_text(r[0]["credentials_encrypted"])
            return json.loads(txt)
        except Exception:
            return None

    def update(self, integration_id: UUID, business_id: UUID, patch: dict[str, Any]) -> dict | None:
        if "credentials" in patch:
            creds = patch.pop("credentials")
            patch["credentials_encrypted"] = encrypt_text(json.dumps(creds)).decode()
        r = (
            self.db.table("ts_api_integrations").update(patch)
            .eq("id", str(integration_id)).eq("business_id", str(business_id))
            .execute()
        )
        if not r.data:
            return None
        out = r.data[0]
        out.pop("credentials_encrypted", None)
        return out

    def delete(self, integration_id: UUID, business_id: UUID) -> bool:
        r = (
            self.db.table("ts_api_integrations").delete()
            .eq("id", str(integration_id)).eq("business_id", str(business_id))
            .execute()
        )
        return bool(r.data)
