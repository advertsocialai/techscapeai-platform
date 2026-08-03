"""
In-process live-call feed broadcaster (Phase 2 T7).

Bridges the webhook media-stream handler (producer — writes transcripts/
call_status as a call progresses) to /ws/calls/{call_id} subscribers
(consumers — the future dashboard, or gogaga-verifier's ws_probe.py).
Single-process only (matches this repo's existing in-memory jti
blacklist in core/security.py — same acknowledged limitation, same
reason: no Redis pub/sub wired in yet, P2 TODO).

Message shapes match the WebSocket contract in gogaga-backend/
references/api-conventions.md exactly (type discriminator, so unknown
types are safely ignorable by any future client).
"""
from __future__ import annotations
from typing import Any

from fastapi import WebSocket

_listeners: dict[str, set[WebSocket]] = {}


def register(call_id: str, ws: WebSocket) -> None:
    _listeners.setdefault(call_id, set()).add(ws)


def unregister(call_id: str, ws: WebSocket) -> None:
    _listeners.get(call_id, set()).discard(ws)
    if call_id in _listeners and not _listeners[call_id]:
        del _listeners[call_id]


async def publish(call_id: str, message: dict[str, Any]) -> None:
    for ws in list(_listeners.get(call_id, ())):
        try:
            await ws.send_json(message)
        except Exception:
            unregister(call_id, ws)
