"""Lead Qualification endpoints — pre-booking funnel.

T6 (partial, Phase 1): role-gated per core/deps.py's hierarchy, business-
scoped via the user's own business_id (same pattern as wiki.py/users.py/
branches.py — JWT-only, no API-key fallback, which is why this switched
from require_business to get_current_user/require_role).

Read = agent+ (rank>=2). Write = manager+ (rank>=3, == product spec's
"admin+" — see core/deps.py's role-mapping note, same convention wiki.py
uses). NOT built here: assigned-only row scoping for agents (an agent
should eventually only see/act on their OWN assigned leads) — that needs
travel_leads.assigned_agent, which doesn't exist until the Phase 2
travel_leads extension. Building row-level scoping against a column that
doesn't exist yet would mean redoing it once P2 lands it, so this phase
only adds the coarse role gate (business-wide read for any agent+,
business-wide write for any manager+). Formally deferred to Phase 2.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import (
    LeadIn, LeadOut, LeadQualification, LeadStatus, LeadStatusUpdate,
)
from app.services.travel import LeadService
from app.core.deps import require_role

router = APIRouter()

_read  = require_role("agent")
_write = require_role("manager")


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def ingest_lead(req: LeadIn, user: dict = Depends(_write)):
    return LeadService().ingest(
        business_id=UUID(user["business_id"]),
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
    user: dict = Depends(_read),
):
    return LeadService().list(
        UUID(user["business_id"]),
        status=status_filter, qualification=qualification_filter, limit=limit,
    )


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: UUID, user: dict = Depends(_read)):
    row = LeadService().get(lead_id, UUID(user["business_id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return row


@router.put("/{lead_id}/status", response_model=LeadOut)
def update_status(
    lead_id: UUID, body: LeadStatusUpdate,
    user: dict = Depends(_write),
):
    row = LeadService().update_status(lead_id, UUID(user["business_id"]), body.status)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return row
