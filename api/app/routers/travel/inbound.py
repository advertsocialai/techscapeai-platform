"""
Inbound dispatcher — implements the 3-minute WhatsApp demo flow from the
strategy doc. Classifies inbound messages and routes them to the right agent.

`POST /inbound/whatsapp` is the canonical entry point. The same dispatcher
is reused from the Wapi inbound webhook (when wired) so the demo flow runs
end-to-end without a separate path.
"""
from fastapi import APIRouter, Depends, status
from uuid import UUID

from app.schemas.travel import WhatsAppInboundIn, WhatsAppInboundOut
from app.services.travel import InboundDispatcher
from app.routers.techscape._deps import require_business

router = APIRouter()


@router.post("/whatsapp", response_model=WhatsAppInboundOut, status_code=status.HTTP_200_OK)
async def inbound_whatsapp(req: WhatsAppInboundIn, biz: dict = Depends(require_business)):
    result = await InboundDispatcher().dispatch(
        business_id=UUID(biz["id"]),
        from_number=req.from_number,
        text=req.text,
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        language=req.language,
        itinerary_id=req.itinerary_id,
    )
    return result
