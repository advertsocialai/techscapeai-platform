"""
Calls API (Phase 2 T7) — JWT-only, same core/deps.py pattern as every
other Phase 1/2 route. Two router objects on purpose:

  `router`    — REST endpoints, mounted under travel_router (gets the
                normal /api/travel/v1 prefix).
  `ws_router` — the live-feed WebSocket, mounted directly on `app` with
                NO prefix, matching gogaga-verifier's ws_probe.py and
                the target contract in api-contract.md exactly:
                ws://<host>/ws/calls/{call_id} (not under /api/v1/...).

Assigned-only scoping mirrors leads.py's T1 pattern (agent-tier sees
only calls whose lead is assigned to them; manager+ unscoped), joined
through lead_id via CallService.
"""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.core.deps import get_current_user, require_role
from app.schemas.travel import CallOut, TranscriptOut
from app.services.travel import call_feed
from app.services.travel.call_service import CallService

router = APIRouter()
ws_router = APIRouter()

_read = require_role("agent")
_MANAGER_PLUS_ROLES = {"manager", "admin", "super_admin"}


def _is_manager_plus(user: dict) -> bool:
    return user.get("role") in _MANAGER_PLUS_ROLES


@router.get("/live", response_model=list[CallOut])
def list_live_calls(user: dict = Depends(_read)):
    scope = None if _is_manager_plus(user) else UUID(user["id"])
    return CallService().list_live(UUID(user["business_id"]), assigned_agent=scope)


@router.get("/{call_id}/transcript", response_model=list[TranscriptOut])
def get_call_transcript(call_id: UUID, user: dict = Depends(_read)):
    scope = None if _is_manager_plus(user) else UUID(user["id"])
    svc = CallService()
    call = svc.get_call_scoped(call_id, UUID(user["business_id"]), assigned_agent=scope)
    if not call:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call not found")
    return svc.get_transcript(call_id)


# ── Live feed WS ──────────────────────────────────────────────────
# Auth: JWT via the Authorization header on the WS handshake (a FastAPI
# Depends() with a Header() param works the same way on WebSocket routes
# as it does on HTTP ones — resolved before .accept(), so an invalid/
# missing token closes the connection instead of ever accepting it).
# Matches gogaga-verifier/scripts/ws_probe.py's `additional_headers`
# convention exactly.
@ws_router.websocket("/ws/calls/{call_id}")
async def call_feed_ws(websocket: WebSocket, call_id: UUID, user: dict = Depends(get_current_user)):
    scope = None if _is_manager_plus(user) else UUID(user["id"])
    call = CallService().get_call_scoped(call_id, UUID(user["business_id"]), assigned_agent=scope)
    if not call:
        await websocket.close(code=4404)  # not found / out of scope — never leak which
        return

    await websocket.accept()
    key = str(call_id)
    call_feed.register(key, websocket)
    try:
        while True:
            # Clients don't need to send anything — this is a push feed —
            # but we still need to await something to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        call_feed.unregister(key, websocket)
