"""
Follow-up ladder endpoints (Phase 4 T6).

GET    /follow-ups                    → queue, filterable by status
PATCH  /follow-ups/{id}               → work an item (status/assignee/etc)
GET    /follow-ups/rules              → the effective ladder for this scope
PUT    /follow-ups/rules              → edit a ladder rung (manager+);
                                        cascades to FUTURE-scheduled rows only
POST   /follow-ups/schedule           → (re)schedule the ladder for a lead;
                                        idempotent, manager+

STATUS DERIVATION — `due` → `overdue` is COMPUTED at read time, not stored
(see services/travel/followup_service.py). `?status=overdue` therefore
returns rows whose due_at has simply passed, with no cron job involved.
Each row also carries `stored_status` so the raw column value stays visible.

SCOPING — mirrors leads.py / calls.py:
  * read  = agent+ ; an agent-tier caller (rank 2) only sees follow-ups
            assigned to themself. manager+ sees the whole business.
  * write = agent+ for PATCH (agents must be able to work their own queue,
            and are scoped to it), manager+ for rules and scheduling.
  * Out-of-scope rows 404, never 403 — an agent must not be able to probe
    for the existence of another agent's work.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import require_role
from app.services.travel.followup_service import FollowUpService

router = APIRouter()

_AGENT_PLUS   = require_role("agent")
_MANAGER_PLUS = require_role("manager")

# Same literal set leads.py/takeover.py use to detect "ranks >= manager".
_MANAGER_PLUS_ROLES = {"manager", "admin", "super_admin"}

FollowUpStatus  = Literal["due", "overdue", "in_progress", "done"]
FollowUpType    = Literal["nudge", "summary", "personal_call", "price_alert"]
FollowUpChannel = Literal["whatsapp", "sms", "email", "call", "in_app"]
LadderDay       = Literal[1, 3, 7]


def _is_manager_plus(user: dict) -> bool:
    return user.get("role") in _MANAGER_PLUS_ROLES


def _assignee_scope(user: dict) -> Optional[UUID]:
    """None = unscoped (manager+). UUID = restricted to own assignments."""
    return None if _is_manager_plus(user) else UUID(user["id"])


def _branch_scope(user: dict) -> Optional[UUID]:
    """A branch-scoped user only ever configures their own branch."""
    branch_id = user.get("branch_id")
    return UUID(branch_id) if branch_id else None


class FollowUpPatch(BaseModel):
    status:      Optional[FollowUpStatus]  = None
    assigned_to: Optional[UUID]            = None
    channel:     Optional[FollowUpChannel] = None
    due_at:      Optional[datetime]        = None
    metadata:    Optional[dict[str, Any]]  = None


class LadderRuleIn(BaseModel):
    ladder_day:       LadderDay
    type:             FollowUpType
    channel:          FollowUpChannel = "whatsapp"
    #: NULL => derived as ladder_day * 24 hours.
    due_offset_hours: Optional[int]   = Field(default=None, ge=0, le=24 * 30)
    is_active:        bool            = True
    #: Only honoured for unscoped (business-wide) users; a branch-scoped
    #: user always writes their own branch.
    branch_id:        Optional[UUID]  = None


class ScheduleIn(BaseModel):
    lead_id:     UUID
    branch_id:   Optional[UUID] = None
    assigned_to: Optional[UUID] = None


@router.get("")
def list_follow_ups(
    status_filter: Optional[FollowUpStatus] = Query(default=None, alias="status"),
    lead_id:       Optional[UUID]           = Query(default=None),
    branch_id:     Optional[UUID]           = Query(default=None, alias="branch"),
    limit:         int                      = Query(default=100, ge=1, le=500),
    user: dict = Depends(_AGENT_PLUS),
):
    return FollowUpService().list(
        UUID(user["business_id"]),
        status=status_filter,
        lead_id=lead_id,
        branch_id=branch_id,
        assigned_to=_assignee_scope(user),
        limit=limit,
    )


@router.get("/rules")
def get_ladder_rules(user: dict = Depends(_AGENT_PLUS)):
    """The resolved ladder for the caller's scope (branch overrides business)."""
    svc = FollowUpService()
    branch_id = _branch_scope(user)
    return {
        "branch_id": str(branch_id) if branch_id else None,
        "ladder":    svc.effective_ladder(UUID(user["business_id"]), branch_id=branch_id),
        "raw_rules": svc.list_rules(
            UUID(user["business_id"]), branch_id=branch_id, include_inactive=True
        ),
    }


@router.put("/rules")
def upsert_ladder_rule(body: LadderRuleIn, user: dict = Depends(_MANAGER_PLUS)):
    """Edit one rung of the ladder.

    The edit cascades to FUTURE-scheduled follow-ups only. Follow-ups that
    are already due/overdue, in progress, or done are left exactly as they
    are — rewriting them would falsify the record of what was scheduled.
    `rescheduled` reports how many future rows moved.
    """
    branch_id = _branch_scope(user) or body.branch_id
    try:
        return FollowUpService().upsert_rule(
            UUID(user["business_id"]),
            ladder_day=body.ladder_day,
            type=body.type,
            channel=body.channel,
            due_offset_hours=body.due_offset_hours,
            is_active=body.is_active,
            branch_id=branch_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.post("/schedule", status_code=status.HTTP_201_CREATED)
def schedule_ladder(body: ScheduleIn, user: dict = Depends(_MANAGER_PLUS)):
    """(Re)schedule the Day 1/3/7 ladder for a lead. Idempotent.

    Normally invoked automatically on lead creation; exposed here for
    backfill and for verifying the acceptance criterion directly.
    Returns only the rows this call created ([] when already scheduled).
    """
    created = FollowUpService().schedule_for_lead(
        body.lead_id, UUID(user["business_id"]),
        branch_id=body.branch_id or _branch_scope(user),
        assigned_to=body.assigned_to,
    )
    return {"lead_id": str(body.lead_id), "created": created, "count": len(created)}


@router.patch("/{follow_up_id}")
def update_follow_up(
    follow_up_id: UUID, body: FollowUpPatch, user: dict = Depends(_AGENT_PLUS),
):
    try:
        row = FollowUpService().update(
            follow_up_id, UUID(user["business_id"]),
            body.model_dump(exclude_none=True),
            assigned_to=_assignee_scope(user),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if row is None:
        # Out of scope => 404, never 403 (repo convention).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found")
    return row
