"""
Business + user services.

Tenancy model:
  • A `business` is the root tenant (owns workflows, contacts, ...).
  • Users belong to a business via `business_id`.
  • Auth is dual: API-key (fast machine access) OR JWT (interactive).
"""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from app.core.security import hash_api_key, new_api_key, hash_password, verify_password
from app.database import get_supabase_admin


class BusinessService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── Businesses ────────────────────────────────────────────
    def list(self) -> list[dict]:
        return (
            self.db.table("ts_businesses").select("*")
            .order("created_at", desc=True).execute().data or []
        )

    def create(self, payload: dict[str, Any]) -> dict:
        plain, hashed = new_api_key()
        # Schema defaults — set explicitly so the row is well-formed even when
        # the underlying driver / harness skips Postgres DEFAULT clauses.
        defaults: dict[str, Any] = {
            "status":                 "active",
            "subscription_tier":      "starter",
            "industry":               "travel",
            "max_workflows":          10,
            "max_monthly_messages":   10000,
            "monthly_messages_used":  0,
            "timezone":               "UTC",
            "preferred_sms_provider": "wapi",
            "preferred_voice_provider": "twilio",
        }
        row = {**defaults, **payload, "api_key_hash": hashed}
        created = self.db.table("ts_businesses").insert(row).execute().data[0]
        return {**created, "api_key": plain}  # plain shown once

    def get(self, business_id: UUID) -> dict | None:
        r = (
            self.db.table("ts_businesses").select("*")
            .eq("id", str(business_id)).limit(1).execute()
        )
        return r.data[0] if r.data else None

    def find_by_api_key(self, plaintext_key: str) -> dict | None:
        h = hash_api_key(plaintext_key)
        r = (
            self.db.table("ts_businesses").select("*")
            .eq("api_key_hash", h).limit(1).execute()
        )
        return r.data[0] if r.data else None

    def rotate_api_key(self, business_id: UUID) -> dict:
        plain, hashed = new_api_key()
        self.db.table("ts_businesses").update({"api_key_hash": hashed}).eq(
            "id", str(business_id)
        ).execute()
        return {"api_key": plain}

    # ── Users ────────────────────────────────────────────────
    def find_user_by_email(self, email: str) -> dict | None:
        r = (
            self.db.table("ts_users").select("*")
            .eq("email", email.lower()).limit(1).execute()
        )
        return r.data[0] if r.data else None

    def create_user(
        self,
        *,
        business_id: UUID,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name:  Optional[str] = None,
        role: str = "admin",
    ) -> dict:
        row = {
            "business_id": str(business_id),
            "email":       email.lower(),
            "password_hash": hash_password(password),
            "first_name":  first_name,
            "last_name":   last_name,
            "role":        role,
            "status":      "active",
        }
        return self.db.table("ts_users").insert(row).execute().data[0]

    def authenticate(self, *, email: str, password: str) -> dict | None:
        user = self.find_user_by_email(email)
        if not user or user.get("status") != "active":
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        # last_login bookkeeping (best-effort)
        try:
            from datetime import datetime, timezone
            self.db.table("ts_users").update({
                "last_login_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", user["id"]).execute()
        except Exception:
            pass
        return user

    def set_password(self, user_id: UUID, new_password: str) -> None:
        self.db.table("ts_users").update({
            "password_hash": hash_password(new_password),
        }).eq("id", str(user_id)).execute()

    # ── Users — Phase 1 CRUD (branch-scoped) ────────────────────
    def list_users(
        self,
        *,
        business_id: UUID,
        branch_id: Optional[UUID] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """branch_id=None means unscoped (super_admin sees the whole business)."""
        q = self.db.table("ts_users").select("*", count="exact").eq(
            "business_id", str(business_id)
        )
        if branch_id is not None:
            q = q.eq("branch_id", str(branch_id))
        if role:
            q = q.eq("role", role)
        if status:
            q = q.eq("status", status)
        r = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return (r.data or []), (r.count or 0)

    def get_user_scoped(
        self, user_id: UUID, *, business_id: UUID, branch_id: Optional[UUID] = None
    ) -> dict | None:
        """branch_id=None means unscoped (super_admin). Returns None if the
        user doesn't exist OR is outside the caller's business/branch scope
        — callers must turn None into 404 (never leak existence)."""
        r = (
            self.db.table("ts_users").select("*")
            .eq("id", str(user_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        if not r.data:
            return None
        user = r.data[0]
        if branch_id is not None and user.get("branch_id") != str(branch_id):
            return None
        return user

    def create_user_scoped(self, *, business_id: UUID, payload: dict) -> dict:
        row = {
            "business_id": str(business_id),
            "email": payload["email"].lower(),
            "password_hash": hash_password(payload["password"]),
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            "role": payload.get("role", "agent"),
            "status": "active",
            "branch_id": str(payload["branch_id"]) if payload.get("branch_id") else None,
        }
        return self.db.table("ts_users").insert(row).execute().data[0]

    def update_user(self, user_id: UUID, fields: dict) -> dict:
        clean = {k: (str(v) if k == "branch_id" and v is not None else v)
                 for k, v in fields.items() if v is not None}
        r = self.db.table("ts_users").update(clean).eq("id", str(user_id)).execute()
        return r.data[0]

    def deactivate_user(self, user_id: UUID) -> dict:
        r = self.db.table("ts_users").update({"status": "inactive"}).eq(
            "id", str(user_id)
        ).execute()
        return r.data[0]

    # ── Subscription enforcement ─────────────────────────────
    def can_send_messages(self, business_id: UUID, n: int = 1) -> tuple[bool, str]:
        """Returns (allowed, reason) given current monthly usage + tier cap."""
        biz = self.get(business_id)
        if not biz:
            return False, "business not found"
        if biz.get("status") != "active":
            return False, f"business status={biz.get('status')}"
        used = int(biz.get("monthly_messages_used") or 0)
        cap  = int(biz.get("max_monthly_messages") or 0)
        if cap and used + n > cap:
            return False, f"monthly message cap exceeded ({used}/{cap})"
        return True, "ok"

    def increment_message_count(self, business_id: UUID, n: int = 1) -> None:
        biz = self.get(business_id)
        if not biz:
            return
        used = int(biz.get("monthly_messages_used") or 0)
        self.db.table("ts_businesses").update({
            "monthly_messages_used": used + n,
        }).eq("id", str(business_id)).execute()

    def reset_monthly_counter(self, business_id: UUID) -> None:
        self.db.table("ts_businesses").update({"monthly_messages_used": 0}).eq(
            "id", str(business_id)
        ).execute()
