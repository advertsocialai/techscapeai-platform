"""
TravelWorkflow OS endpoints — all 24 UCs (UC-001..UC-024).

Public (read-only spec catalogue — no auth):
  GET  /playbooks                       — list all 24 use cases
  GET  /playbooks/{uc_id}                — full spec including templates
  POST /playbooks/{uc_id}/render         — render with caller-supplied context

Auth-gated (tenant data + dispatch):
  POST /playbooks/{uc_id}/dispatch       — send via providers + audit row
  GET  /playbooks/runs                   — dispatch audit log
  GET  /playbooks/scheduled/due          — bookings due today
  POST /playbooks/scheduled/run-due      — fire all due UCs
"""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.schemas.travel import (
    PlaybookDispatchIn, PlaybookRender, PlaybookRunOut,
)
from app.services.travel import (
    BookingService, PlaybookExecutor, PlaybookScheduler, playbooks as pb_registry,
)
from app.routers.techscape._deps import require_business

router = APIRouter()


# ── Public catalogue (no auth) ───────────────────────────────────
@router.get("")
def list_playbooks():
    return pb_registry.use_case_summary()


@router.get("/runs", response_model=list[PlaybookRunOut])
def list_runs(
    use_case_id: Optional[str] = Query(default=None),
    booking_id:  Optional[UUID] = Query(default=None),
    limit:       int = Query(default=100, ge=1, le=500),
    biz: dict = Depends(require_business),
):
    db = PlaybookExecutor().db
    q = (
        db.table("travel_playbook_runs").select("*")
        .eq("business_id", biz["id"])
    )
    if use_case_id:
        q = q.eq("use_case_id", use_case_id.upper())
    if booking_id:
        q = q.eq("booking_id", str(booking_id))
    return q.order("created_at", desc=True).limit(limit).execute().data or []


@router.get("/scheduled/due")
def scheduled_due(
    on_date: Optional[date] = Query(default=None),
    biz: dict = Depends(require_business),
):
    return PlaybookScheduler().due(UUID(biz["id"]), on_date=on_date)


@router.post("/scheduled/run-due")
async def scheduled_run_due(
    on_date: Optional[date] = Query(default=None),
    dry_run: bool = Query(default=True),
    biz: dict = Depends(require_business),
):
    return await PlaybookScheduler().run_due(biz, on_date=on_date, dry_run=dry_run)


@router.get("/{uc_id}")
def get_playbook(uc_id: str):
    pb = pb_registry.get_playbook(uc_id)
    if not pb:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Use case not found")
    return {"id": uc_id.upper(), **pb,
            "category_label": pb_registry.CATEGORY.get(pb["category"], pb["category"])}


@router.post("/{uc_id}/render")
def render_playbook(
    uc_id: str, body: PlaybookRender = Body(default=PlaybookRender()),
):
    pb = pb_registry.get_playbook(uc_id)
    if not pb:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Use case not found")
    return PlaybookExecutor().render(uc_id, body.context or {}, body.channels)


@router.post("/{uc_id}/dispatch", response_model=PlaybookRunOut)
async def dispatch_playbook(
    uc_id: str, body: PlaybookDispatchIn,
    biz: dict = Depends(require_business),
):
    pb = pb_registry.get_playbook(uc_id)
    if not pb:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Use case not found")

    booking_id = body.booking_id
    customer = None
    booking = None
    biz_id = UUID(biz["id"])

    if body.booking_ref and not booking_id:
        booking = BookingService().by_ref(biz_id, body.booking_ref)
        if booking:
            booking_id = UUID(booking["id"])
    elif booking_id:
        booking = BookingService().get(booking_id, biz_id)

    db = PlaybookExecutor().db
    if booking and booking.get("customer_id"):
        cu = (
            db.table("travel_customer_profiles").select("*")
            .eq("id", booking["customer_id"]).limit(1).execute().data
        )
        customer = cu[0] if cu else None
    elif body.customer_id:
        cu = (
            db.table("travel_customer_profiles").select("*")
            .eq("id", str(body.customer_id)).limit(1).execute().data
        )
        customer = cu[0] if cu else None

    executor = PlaybookExecutor()
    ctx = executor.build_context(business=biz, booking=booking, customer=customer,
                                  extra=body.context or {})
    return await executor.dispatch(
        business_id=biz_id, uc_id=uc_id, context=ctx, channels=body.channels,
        to_email=body.to_email or (customer or {}).get("email"),
        to_phone=body.to_phone or (customer or {}).get("phone"),
        booking_id=booking_id, customer_id=body.customer_id,
        lead_id=body.lead_id, incident_id=body.incident_id,
        trigger_kind="manual", dry_run=body.dry_run,
    )
