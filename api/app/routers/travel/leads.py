"""Lead Qualification endpoints — pre-booking funnel."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import (
    LeadIn, LeadOut, LeadQualification, LeadStatus, LeadStatusUpdate,
)
from app.services.travel import LeadService
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def ingest_lead(req: LeadIn, biz: dict = Depends(require_business)):
    return LeadService().ingest(
        business_id=UUID(biz["id"]),
        raw_message=req.raw_message,
        source=req.source,
        customer_email=req.customer_email,
        customer_name=req.customer_name,
        customer_phone=req.customer_phone,
        language=req.language,
        franchisee_id=req.franchisee_id,
    )


@router.get("", response_model=list[LeadOut])
def list_leads(
    status_filter:        Optional[LeadStatus]        = Query(default=None, alias="status"),
    qualification_filter: Optional[LeadQualification] = Query(default=None, alias="qualification"),
    limit:                int                         = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    return LeadService().list(
        UUID(biz["id"]),
        status=status_filter, qualification=qualification_filter, limit=limit,
    )


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: UUID, biz: dict = Depends(require_business)):
    row = LeadService().get(lead_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return row


@router.put("/{lead_id}/status", response_model=LeadOut)
def update_status(
    lead_id: UUID, body: LeadStatusUpdate,
    biz: dict = Depends(require_business),
):
    row = LeadService().update_status(lead_id, UUID(biz["id"]), body.status)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return row
