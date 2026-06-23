"""Catalog service — destinations / packages / franchisees / suppliers CRUD."""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin


class CatalogService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── Destinations ─────────────────────────────────────────
    def list_destinations(self, business_id: UUID) -> list[dict]:
        return (
            self.db.table("travel_destinations").select("*")
            .eq("business_id", str(business_id))
            .order("name").execute().data or []
        )

    def create_destination(self, business_id: UUID, payload: dict) -> dict:
        return self.db.table("travel_destinations").insert(
            {**payload, "business_id": str(business_id)}
        ).execute().data[0]

    # ── Packages ─────────────────────────────────────────────
    def list_packages(self, business_id: UUID,
                       *, destination_id: Optional[UUID] = None) -> list[dict]:
        q = (
            self.db.table("travel_packages").select("*")
            .eq("business_id", str(business_id))
            .eq("is_active", True)
        )
        if destination_id:
            q = q.eq("destination_id", str(destination_id))
        return q.order("base_price_inr").execute().data or []

    def create_package(self, business_id: UUID, payload: dict) -> dict:
        return self.db.table("travel_packages").insert(
            {**payload, "business_id": str(business_id)}
        ).execute().data[0]

    # ── Franchisees ──────────────────────────────────────────
    def list_franchisees(self, business_id: UUID) -> list[dict]:
        return (
            self.db.table("travel_franchisees").select("*")
            .eq("business_id", str(business_id))
            .order("name").execute().data or []
        )

    def create_franchisee(self, business_id: UUID, payload: dict) -> dict:
        return self.db.table("travel_franchisees").insert(
            {**payload, "business_id": str(business_id)}
        ).execute().data[0]

    # ── Suppliers ────────────────────────────────────────────
    def list_suppliers(self, business_id: UUID,
                        *, supplier_type: Optional[str] = None) -> list[dict]:
        q = (
            self.db.table("travel_suppliers").select("*")
            .eq("business_id", str(business_id))
            .eq("is_active", True)
        )
        if supplier_type:
            q = q.eq("supplier_type", supplier_type)
        return q.order("reliability_score", desc=True).execute().data or []

    def create_supplier(self, business_id: UUID, payload: dict) -> dict:
        return self.db.table("travel_suppliers").insert(
            {**payload, "business_id": str(business_id)}
        ).execute().data[0]
