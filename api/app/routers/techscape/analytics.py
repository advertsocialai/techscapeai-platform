"""Analytics endpoints — overview, per-workflow, per-channel, costs, ROI."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.schemas.techscape import AnalyticsOverview
from app.services.techscape import AnalyticsService

from ._deps import require_business

router = APIRouter()


@router.get("/overview", response_model=AnalyticsOverview)
def overview(biz: dict = Depends(require_business)):
    return AnalyticsService().overview(UUID(biz["id"]))


@router.get("/workflows")
def per_workflow(biz: dict = Depends(require_business),
                 days: int = Query(30, ge=1, le=365)):
    return AnalyticsService().by_workflow(UUID(biz["id"]), days=days)


@router.get("/channels")
def per_channel(biz: dict = Depends(require_business),
                days: int = Query(30, ge=1, le=365)):
    return AnalyticsService().by_channel(UUID(biz["id"]), days=days)


@router.get("/costs")
def costs(biz: dict = Depends(require_business),
          days: int = Query(30, ge=1, le=365)):
    return AnalyticsService().costs(UUID(biz["id"]), days=days)


@router.get("/roi")
def roi(biz: dict = Depends(require_business),
        days: int = Query(30, ge=1, le=365),
        manual_minutes_per_message: float = Query(5.0, ge=0.1, le=120.0),
        hourly_rate: float = Query(35.0, ge=1.0, le=1000.0)):
    return AnalyticsService().roi(
        UUID(biz["id"]), days=days,
        manual_minutes_per_message=manual_minutes_per_message,
        hourly_rate=hourly_rate,
    )
