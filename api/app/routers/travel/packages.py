"""
Packages CRUD endpoints (Phase 4 T1).

GET    /packages              → list (filters: category, destination_id, active)
GET    /packages/{id}         → one package
POST   /packages              → create
PATCH  /packages/{id}         → partial update
DELETE /packages/{id}         → SOFT delete (is_active = FALSE)

RBAC (app/core/deps.py hierarchy — same convention as wiki.py/ai_config.py):
  read  = require_role("viewer")   → every authenticated role
  write = require_role("manager")  → manager/admin/super_admin
          (== the product spec's "owner/manager" tier — see the
          role-mapping note in core/deps.py)

Scoping: every query is filtered by the authenticated principal's
business_id, and by branch_id when the caller is branch-scoped
(branch_id NULL on a package == global, visible to all branches).
A package outside the caller's scope returns 404, never 403 — we do not
leak the existence of another tenant's rows.

Schema note: this rides on the PRE-EXISTING public.travel_packages table.
Migration 0009 only adds category/currency/branch_id/nights.
`base_price_inr` and `duration_days` are deliberately preserved because
catalog_service.list_packages() and ai_engine.get_packages() read them.
Request/response models live HERE on purpose — app/schemas/travel.py is
shared and owned elsewhere.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import require_role
from app.services.travel.package_service import PackageService
from app.services.travel import activity_log

router = APIRouter()

_read = require_role("viewer")
_write = require_role("manager")

PackageCategory = Literal["budget", "luxury", "honeymoon", "family"]


# ── Schemas ──────────────────────────────────────────────────
class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    destination_id: Optional[UUID] = None
    duration_days: int = Field(ge=1, le=60)
    nights: Optional[int] = Field(default=None, ge=0, le=60)
    base_price_inr: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    category: Optional[PackageCategory] = None
    branch_id: Optional[UUID] = None  # NULL = global package
    inclusions: list[str] = []
    exclusions: list[str] = []
    itinerary_template: list[dict[str, Any]] = []
    min_pax: int = Field(default=1, ge=1)
    max_pax: int = Field(default=20, ge=1)


class PackageUpdate(BaseModel):
    """All-optional PATCH body — unset fields are left untouched."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    destination_id: Optional[UUID] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=60)
    nights: Optional[int] = Field(default=None, ge=0, le=60)
    base_price_inr: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    category: Optional[PackageCategory] = None
    branch_id: Optional[UUID] = None
    inclusions: Optional[list[str]] = None
    exclusions: Optional[list[str]] = None
    itinerary_template: Optional[list[dict[str, Any]]] = None
    min_pax: Optional[int] = Field(default=None, ge=1)
    max_pax: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class PackageOut(BaseModel):
    id: UUID
    business_id: UUID
    branch_id: Optional[UUID] = None
    name: str
    destination_id: Optional[UUID] = None
    duration_days: int
    nights: Optional[int] = None
    base_price_inr: int
    currency: str = "INR"
    category: Optional[str] = None
    inclusions: list[str] = []
    exclusions: list[str] = []
    itinerary_template: list[dict[str, Any]] = []
    min_pax: Optional[int] = None
    max_pax: Optional[int] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def _scope(user: dict) -> Optional[UUID]:
    """Branch of the caller, or None for business-wide principals."""
    raw = user.get("branch_id")
    return UUID(raw) if raw else None


# ── Routes ───────────────────────────────────────────────────
@router.get("", response_model=list[PackageOut])
def list_packages(
    category: Optional[PackageCategory] = Query(default=None),
    destination_id: Optional[UUID] = Query(default=None),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(_read),
):
    return PackageService().list(
        UUID(user["business_id"]),
        branch_id=_scope(user),
        destination_id=destination_id,
        category=category,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: UUID, user: dict = Depends(_read)):
    row = PackageService().get(
        package_id, UUID(user["business_id"]), branch_id=_scope(user)
    )
    if not row:
        # Out of scope OR nonexistent — same 404 either way (no leak).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return row


@router.post("", response_model=PackageOut, status_code=status.HTTP_201_CREATED)
def create_package(payload: PackageCreate, user: dict = Depends(_write)):
    body = payload.model_dump()
    if body.get("max_pax") is not None and body.get("min_pax") is not None:
        if body["max_pax"] < body["min_pax"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "max_pax must be >= min_pax"
            )
    body["currency"] = body["currency"].upper()
    row = PackageService().create(
        UUID(user["business_id"]), body, branch_id=_scope(user)
    )
    activity_log.record(
        user["id"], "package.created", "package", row.get("id"),
        user["business_id"], user.get("branch_id"),
        {"name": row.get("name"), "category": row.get("category")},
    )
    return row


@router.patch("/{package_id}", response_model=PackageOut)
def update_package(
    package_id: UUID, payload: PackageUpdate, user: dict = Depends(_write)
):
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update")
    if isinstance(patch.get("currency"), str):
        patch["currency"] = patch["currency"].upper()

    row = PackageService().update(
        package_id, UUID(user["business_id"]), patch, branch_id=_scope(user)
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    activity_log.record(
        user["id"], "package.updated", "package", package_id,
        user["business_id"], user.get("branch_id"),
        {"fields": sorted(patch)},
    )
    return row


@router.delete("/{package_id}", response_model=PackageOut)
def delete_package(package_id: UUID, user: dict = Depends(_write)):
    """SOFT delete — sets is_active = FALSE and returns the archived row.
    Packages are never hard-deleted (itineraries/bookings reference them)."""
    row = PackageService().soft_delete(
        package_id, UUID(user["business_id"]), branch_id=_scope(user)
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    activity_log.record(
        user["id"], "package.deleted", "package", package_id,
        user["business_id"], user.get("branch_id"),
        {"soft": True},
    )
    return row
