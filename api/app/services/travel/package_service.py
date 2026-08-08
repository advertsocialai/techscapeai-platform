"""
Package service — Phase 4 T1 CRUD over public.travel_packages.

The table PRE-DATES this phase (database/travel_schema.sql §3); migration
0009_packages_extension.sql only ADDS category / currency / branch_id /
nights to it. `base_price_inr`, `duration_days` and `is_active` are
untouched, so the existing readers keep working unchanged:
  * catalog_service.CatalogService.list_packages() — ORDER BY base_price_inr
  * ai_engine.get_packages()                       — the Klara tool-call
  * itinerary_agent / gogaga_seed

Every method is scoped by business_id, so a row belonging to another
business is simply "not found" (the router turns that into 404, never
403 — we don't leak existence across tenants).

Branch scoping: branch_id NULL == a global package visible to every
branch. A branch-scoped caller sees its own branch's packages PLUS the
global ones; an unscoped (business-wide) caller sees everything.

DELETE is a SOFT delete — `is_active = FALSE`. Rows are never removed.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin

_TABLE = "travel_packages"

# Columns a client is allowed to write. Anything else in a payload is
# dropped rather than passed to Postgres — business_id/id/timestamps are
# server-owned, and this keeps a stray key from 400-ing the whole insert.
_WRITABLE = {
    "name", "destination_id", "duration_days", "nights", "base_price_inr",
    "currency", "category", "branch_id", "inclusions", "exclusions",
    "itinerary_template", "min_pax", "max_pax", "is_active",
}


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep writable keys only, and stringify UUIDs for the REST client."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k not in _WRITABLE:
            continue
        out[k] = str(v) if isinstance(v, UUID) else v
    return out


class PackageService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── internals ────────────────────────────────────────────
    def _scoped(self, business_id: UUID):
        return self.db.table(_TABLE).select("*").eq("business_id", str(business_id))

    @staticmethod
    def _apply_branch_scope(q, branch_id: Optional[UUID]):
        """Branch-scoped caller sees its branch + global (NULL) packages."""
        if branch_id is None:
            return q
        return q.or_(f"branch_id.eq.{branch_id},branch_id.is.null")

    # ── read ─────────────────────────────────────────────────
    def list(
        self,
        business_id: UUID,
        *,
        branch_id: Optional[UUID] = None,
        destination_id: Optional[UUID] = None,
        category: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        q = self._scoped(business_id)
        if not include_inactive:
            q = q.eq("is_active", True)
        if destination_id:
            q = q.eq("destination_id", str(destination_id))
        if category:
            q = q.eq("category", category)
        q = self._apply_branch_scope(q, branch_id)
        return (
            q.order("base_price_inr")
            .range(offset, offset + limit - 1)
            .execute().data or []
        )

    def get(
        self,
        package_id: UUID,
        business_id: UUID,
        *,
        branch_id: Optional[UUID] = None,
    ) -> Optional[dict]:
        """None when the package doesn't exist OR belongs to another
        business/branch — the caller must 404 either way."""
        q = self._scoped(business_id).eq("id", str(package_id))
        q = self._apply_branch_scope(q, branch_id)
        rows = q.limit(1).execute().data or []
        return rows[0] if rows else None

    # ── write ────────────────────────────────────────────────
    def create(
        self,
        business_id: UUID,
        payload: dict[str, Any],
        *,
        branch_id: Optional[UUID] = None,
    ) -> dict:
        row = _clean(payload)
        row["business_id"] = str(business_id)
        # A branch-scoped author can only create packages for their own
        # branch — they cannot mint a global or cross-branch package.
        if branch_id is not None:
            row["branch_id"] = str(branch_id)
        return self.db.table(_TABLE).insert(row).execute().data[0]

    def update(
        self,
        package_id: UUID,
        business_id: UUID,
        patch: dict[str, Any],
        *,
        branch_id: Optional[UUID] = None,
    ) -> Optional[dict]:
        # Existence/scope check first so a cross-tenant id 404s instead of
        # silently updating zero rows.
        if not self.get(package_id, business_id, branch_id=branch_id):
            return None
        clean = _clean(patch)
        if not clean:
            return self.get(package_id, business_id, branch_id=branch_id)
        if branch_id is not None:
            clean.pop("branch_id", None)  # can't move a package out of your branch
        rows = (
            self.db.table(_TABLE).update(clean)
            .eq("id", str(package_id)).eq("business_id", str(business_id))
            .execute().data or []
        )
        return rows[0] if rows else self.get(package_id, business_id, branch_id=branch_id)

    def soft_delete(
        self,
        package_id: UUID,
        business_id: UUID,
        *,
        branch_id: Optional[UUID] = None,
    ) -> Optional[dict]:
        """SOFT delete only — flips is_active to FALSE. Repo rule: catalog
        rows are never hard-deleted (bookings/itineraries reference them)."""
        if not self.get(package_id, business_id, branch_id=branch_id):
            return None
        rows = (
            self.db.table(_TABLE).update({"is_active": False})
            .eq("id", str(package_id)).eq("business_id", str(business_id))
            .execute().data or []
        )
        return rows[0] if rows else None
