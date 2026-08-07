"""
Human takeover endpoints (Phase 3 T1).

POST /calls/{call_id}/takeover/monitor  → supervisor joins silently
POST /calls/{call_id}/takeover/barge    → supervisor speaks to customer
POST /calls/{call_id}/takeover/full     → AI muted, human handles call
POST /calls/{call_id}/takeover/release  → AI resumes

State machine: ai → monitoring → coaching → human → ai
All transitions write a travel_call_events row + broadcast takeover_state
on /ws/calls/{call_id}.

RBAC:
  - agent+ if lead is assigned to them
  - admin/manager/super_admin: unscoped (any call in the business)
  - viewer: 403

📞 Live audio (monitor/barge hearing): BLOCKED — Plivo MPC not active
(Phase 2B not run, no Plivo creds). State machine + DB + WS parts work
without live calls. See BLOCKERS.md B-P3-01.
"""
from __future__ import annotations
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import require_role
from app.schemas.travel import CallOut
from app.services.travel import call_feed
from app.services.travel.call_service import CallService
from app.services.travel.takeover_service import TakeoverError, TakeoverService

router = APIRouter()

_AGENT_PLUS = require_role("agent")
_MANAGER_PLUS_ROLES = {"manager", "admin", "super_admin"}


def _scoped_agent(user: dict) -> Optional[UUID]:
    """None = unscoped (manager+). UUID = agent-scoped to their leads."""
    return None if user.get("role") in _MANAGER_PLUS_ROLES else UUID(user["id"])


class TakeoverRequest(BaseModel):
    supervisor_number: Optional[str] = None  # E.164 +91... (India only)


async def _resolve_call(call_id: UUID, user: dict) -> dict:
    """Get call row and enforce RBAC scoping."""
    call = CallService().get_call_scoped(
        call_id, UUID(user["business_id"]), assigned_agent=_scoped_agent(user)
    )
    if not call:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")
    if call["status"] != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Call is not active")
    return call


async def _broadcast_takeover(call_id: str, new_state: str) -> None:
    await call_feed.publish(call_id, {
        "type": "takeover_state",
        "call_id": call_id,
        "takeover_state": new_state,
    })


@router.post("/{call_id}/takeover/monitor", response_model=CallOut)
async def monitor_call(
    call_id: UUID,
    body: TakeoverRequest,
    user: dict = Depends(_AGENT_PLUS),
):
    """Supervisor joins silently — coachMode=true (hears both, neither hears supervisor)."""
    await _resolve_call(call_id, user)
    try:
        updated = await TakeoverService().monitor(
            call_id, UUID(user["business_id"]),
            actor_id=UUID(user["id"]),
            supervisor_number=body.supervisor_number,
        )
    except TakeoverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await _broadcast_takeover(str(call_id), "monitoring")
    return updated


@router.post("/{call_id}/takeover/barge", response_model=CallOut)
async def barge_call(
    call_id: UUID,
    body: TakeoverRequest,
    user: dict = Depends(_AGENT_PLUS),
):
    """Supervisor can now be heard by customer — AI still speaking."""
    await _resolve_call(call_id, user)
    try:
        updated = await TakeoverService().barge(
            call_id, UUID(user["business_id"]),
            actor_id=UUID(user["id"]),
            supervisor_number=body.supervisor_number,
        )
    except TakeoverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await _broadcast_takeover(str(call_id), "coaching")
    return updated


@router.post("/{call_id}/takeover/full", response_model=CallOut)
async def full_takeover(
    call_id: UUID,
    user: dict = Depends(_AGENT_PLUS),
):
    """AI muted/removed. Human handles call. AI continues as silent note-taker."""
    await _resolve_call(call_id, user)
    try:
        updated = await TakeoverService().full_takeover(
            call_id, UUID(user["business_id"]),
            actor_id=UUID(user["id"]),
        )
    except TakeoverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await _broadcast_takeover(str(call_id), "human")
    return updated


@router.post("/{call_id}/takeover/release", response_model=CallOut)
async def release_call(
    call_id: UUID,
    user: dict = Depends(_AGENT_PLUS),
):
    """Return to AI mode. Un-mute AI participant."""
    await _resolve_call(call_id, user)
    try:
        updated = await TakeoverService().release(
            call_id, UUID(user["business_id"]),
            actor_id=UUID(user["id"]),
        )
    except TakeoverError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await _broadcast_takeover(str(call_id), "ai")
    return updated


@router.get("/{call_id}/events")
def get_call_events(call_id: UUID, user: dict = Depends(_AGENT_PLUS)):
    """List all state-machine events for a call."""
    CallService().get_call_scoped(
        call_id, UUID(user["business_id"]), assigned_agent=_scoped_agent(user)
    )  # scope check — raises 404 if out of scope
    return TakeoverService().get_events(call_id)
