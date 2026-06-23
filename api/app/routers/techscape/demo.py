"""Demo / seed endpoints — provision a full travel-agency setup in one call."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.services.techscape.demo_seed import seed_travel_demo

from ._deps import require_business

router = APIRouter()


@router.post("/seed-travel")
def seed_travel(biz: dict = Depends(require_business)):
    """
    Wipes the demo workflows / templates by name and recreates them fresh.
    Returns a summary of what was created.
    """
    return seed_travel_demo(UUID(biz["id"]))
