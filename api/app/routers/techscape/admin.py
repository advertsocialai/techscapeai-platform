"""Admin / ops endpoints — analytics aggregation, monthly reset, manual workers."""
from __future__ import annotations
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.techscape.analytics_service import AnalyticsService
from app.services.techscape.business_service  import BusinessService

from ._deps import require_business

router = APIRouter()


def _admin_only(principal: dict) -> None:
    user = principal.get("_user") or {}
    if user and user.get("role") not in ("admin", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")


@router.post("/aggregate-day")
def aggregate_day(biz: dict = Depends(require_business), target_date: str | None = None):
    _admin_only(biz)
    d = date.fromisoformat(target_date) if target_date else date.today()
    rows = AnalyticsService().aggregate_day(business_id=UUID(biz["id"]), target_date=d)
    return {"ok": True, "rows_written": rows, "date": d.isoformat()}


@router.post("/reset-monthly-counter")
def reset_monthly_counter(biz: dict = Depends(require_business)):
    _admin_only(biz)
    BusinessService().reset_monthly_counter(UUID(biz["id"]))
    return {"ok": True}
