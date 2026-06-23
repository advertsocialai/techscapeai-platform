"""Billing endpoints — current period synthesis + history listing."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.services.techscape.billing_service import BillingService

from ._deps import require_business

router = APIRouter()


@router.get("/current")
def current_period(biz: dict = Depends(require_business)):
    return BillingService().current_period(UUID(biz["id"]))


@router.get("/history")
def history(biz: dict = Depends(require_business), limit: int = 12):
    return BillingService().list_records(UUID(biz["id"]), limit=limit)


@router.post("/generate")
def generate_period(start: str = Query(..., description="YYYY-MM-DD"),
                    end:   str = Query(..., description="YYYY-MM-DD"),
                    biz: dict = Depends(require_business)):
    s = datetime.fromisoformat(start).date()
    e = datetime.fromisoformat(end).date()
    return BillingService().generate_period(business_id=UUID(biz["id"]), start=s, end=e)


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: UUID, biz: dict = Depends(require_business)):
    """Retrieve a billing record (invoice). Strictly scoped to the calling business."""
    from fastapi import HTTPException, status
    db = BillingService().db
    r = (
        db.table("ts_billing_records").select("*")
        .eq("id", str(invoice_id)).eq("business_id", str(biz["id"]))
        .limit(1).execute().data
    )
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return r[0]
