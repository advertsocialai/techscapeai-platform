"""On-Ground Companion endpoints — Attack Point 4 (in-trip support)."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.travel import (
    IncidentEscalateIn, IncidentResolveIn,
    IncidentStatus, InTripIssueIn, InTripIssueOut,
)
from app.services.travel import OnGroundAgent
from app.services.travel.customer_memory import CustomerMemoryService
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("/issues", response_model=InTripIssueOut, status_code=status.HTTP_201_CREATED)
async def report_issue(req: InTripIssueIn, biz: dict = Depends(require_business)):
    customer_id = req.customer_id
    if not customer_id and (req.customer_email or req.customer_phone):
        profile = CustomerMemoryService().upsert_from_intent(
            business_id=UUID(biz["id"]), intent=req.message,
            email=req.customer_email, phone=req.customer_phone,
            language=req.language,
        )
        if profile:
            customer_id = UUID(profile["id"])
    return await OnGroundAgent().handle(
        business_id=UUID(biz["id"]),
        message=req.message,
        itinerary_id=req.itinerary_id,
        customer_id=customer_id,
        channel=req.channel,
    )


@router.get("/issues", response_model=list[InTripIssueOut])
def list_issues(
    status_filter: Optional[IncidentStatus] = Query(default=None, alias="status"),
    itinerary_id:  Optional[UUID] = Query(default=None),
    limit:         int            = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    return OnGroundAgent().list_incidents(
        UUID(biz["id"]),
        status=status_filter, itinerary_id=itinerary_id, limit=limit,
    )


@router.get("/issues/{incident_id}", response_model=InTripIssueOut)
def get_issue(incident_id: UUID, biz: dict = Depends(require_business)):
    row = OnGroundAgent().get_incident(incident_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return row


@router.post("/issues/{incident_id}/resolve", response_model=InTripIssueOut)
def resolve_issue(
    incident_id: UUID, body: IncidentResolveIn,
    biz: dict = Depends(require_business),
):
    row = OnGroundAgent().resolve(
        incident_id, UUID(biz["id"]), note=body.resolution_note,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return row


@router.post("/issues/{incident_id}/escalate", response_model=InTripIssueOut)
def escalate_issue(
    incident_id: UUID, body: IncidentEscalateIn,
    biz: dict = Depends(require_business),
):
    row = OnGroundAgent().escalate(
        incident_id, UUID(biz["id"]),
        escalate_to=body.escalate_to, note=body.note,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return row
