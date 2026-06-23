"""Catalog endpoints — destinations / packages / franchisees / suppliers CRUD."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.schemas.travel import (
    DestinationIn, DestinationOut,
    FranchiseeIn, FranchiseeOut,
    PackageIn, PackageOut,
    SupplierIn, SupplierOut, SupplierType,
)
from app.services.travel import CatalogService
from app.routers.techscape._deps import require_business

router = APIRouter()


# ── Destinations ────────────────────────────────────────────
@router.get("/destinations", response_model=list[DestinationOut])
def list_destinations(biz: dict = Depends(require_business)):
    return CatalogService().list_destinations(UUID(biz["id"]))


@router.post("/destinations", response_model=DestinationOut, status_code=status.HTTP_201_CREATED)
def create_destination(payload: DestinationIn, biz: dict = Depends(require_business)):
    return CatalogService().create_destination(UUID(biz["id"]), payload.model_dump())


# ── Packages ────────────────────────────────────────────────
@router.get("/packages", response_model=list[PackageOut])
def list_packages(
    destination_id: Optional[UUID] = Query(default=None),
    biz: dict = Depends(require_business),
):
    return CatalogService().list_packages(UUID(biz["id"]), destination_id=destination_id)


@router.post("/packages", response_model=PackageOut, status_code=status.HTTP_201_CREATED)
def create_package(payload: PackageIn, biz: dict = Depends(require_business)):
    return CatalogService().create_package(UUID(biz["id"]), payload.model_dump())


# ── Franchisees ─────────────────────────────────────────────
@router.get("/franchisees", response_model=list[FranchiseeOut])
def list_franchisees(biz: dict = Depends(require_business)):
    return CatalogService().list_franchisees(UUID(biz["id"]))


@router.post("/franchisees", response_model=FranchiseeOut, status_code=status.HTTP_201_CREATED)
def create_franchisee(payload: FranchiseeIn, biz: dict = Depends(require_business)):
    return CatalogService().create_franchisee(UUID(biz["id"]), payload.model_dump())


# ── Suppliers ───────────────────────────────────────────────
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    supplier_type: Optional[SupplierType] = Query(default=None),
    biz: dict = Depends(require_business),
):
    return CatalogService().list_suppliers(UUID(biz["id"]), supplier_type=supplier_type)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierIn, biz: dict = Depends(require_business)):
    return CatalogService().create_supplier(UUID(biz["id"]), payload.model_dump())
