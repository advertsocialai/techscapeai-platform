"""Itinerary Agent endpoints — generate, refine, list, status."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.schemas.travel import (
    ItineraryOut, ItineraryRefineIn, ItineraryRequest, ItineraryStatus,
)
from app.services.travel import ItineraryAgent
from app.routers.techscape._deps import require_business

router = APIRouter()


class _StatusUpdate(BaseModel):
    status: ItineraryStatus


@router.post("/generate", response_model=ItineraryOut, status_code=status.HTTP_201_CREATED)
async def generate_itinerary(req: ItineraryRequest, biz: dict = Depends(require_business)):
    agent = ItineraryAgent()
    return await agent.generate(
        business_id=UUID(biz["id"]),
        intent=req.intent,
        pax_count=req.pax_count,
        budget_inr=req.budget_inr,
        duration_days=req.duration_days,
        destination_hint=req.destination_hint,
        customer_id=req.customer_id,
        customer_email=req.customer_email,
        customer_name=req.customer_name,
        customer_phone=req.customer_phone,
        language=req.language,
    )


@router.post("/{itinerary_id}/refine", response_model=ItineraryOut)
async def refine_itinerary(
    itinerary_id: UUID, req: ItineraryRefineIn,
    biz: dict = Depends(require_business),
):
    try:
        return await ItineraryAgent().refine(
            itinerary_id=itinerary_id,
            business_id=UUID(biz["id"]),
            modifications=req.modifications,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.get("", response_model=list[ItineraryOut])
def list_itineraries(
    limit: int = Query(default=50, ge=1, le=200),
    biz: dict = Depends(require_business),
):
    return ItineraryAgent().list(UUID(biz["id"]), limit=limit)


@router.get("/{itinerary_id}", response_model=ItineraryOut)
def get_itinerary(itinerary_id: UUID, biz: dict = Depends(require_business)):
    row = ItineraryAgent().get(itinerary_id, UUID(biz["id"]))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Itinerary not found")
    return row


@router.put("/{itinerary_id}/status", response_model=ItineraryOut)
def update_itinerary_status(
    itinerary_id: UUID, body: _StatusUpdate,
    biz: dict = Depends(require_business),
):
    row = ItineraryAgent().update_status(itinerary_id, UUID(biz["id"]), body.status)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Itinerary not found")
    return row
