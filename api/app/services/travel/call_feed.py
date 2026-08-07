"""
Live-call feed broadcaster (Phase 2 T7; upgraded Phase 3 T8 with Redis).

Two backends, same interface:

  Redis backend (REDIS_URL set): Redis pub/sub — multi-worker safe.
    publish() → RPUBLISH "gogaga:call:{call_id}" (JSON)
    WS handlers subscribe to that channel and relay messages.
    Handles multiple uvicorn workers: worker A WS sees events from worker B.

  In-process fallback (REDIS_URL unset): original in-memory set of
    WebSocket objects per call_id. Single-worker only. Same behaviour
    as Phase 2's original call_feed — zero regression.

The interface (register / unregister / publish) is identical to Phase 2
so no route code changes. Phase 2's ws_probe.py works against either.

See BLOCKERS.md B-P3-04 — Redis not yet provisioned; fallback runs.
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── In-process store (fallback) ────────────────────────────────────
_listeners: dict[str, set[WebSocket]] = {}

# ── Redis client (lazy) ────────────────────────────────────────────
_redis_client = None
_redis_failed = False  # avoids repeated import errors if redis pkg missing


def _get_redis():
    global _redis_client, _redis_failed
    if _redis_failed or not settings.REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis  # type: ignore
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info("call_feed: Redis backend active (%s)", settings.REDIS_URL)
    except Exception:
        logger.warning("call_feed: redis package unavailable — using in-process fallback")
        _redis_failed = True
        _redis_client = None
    return _redis_client


_CHANNEL_PREFIX = "gogaga:call:"


# ── Public interface ────────────────────────────────────────────────

def register(call_id: str, ws: WebSocket) -> None:
    """Register a WS connection for a call (in-process path only)."""
    _listeners.setdefault(call_id, set()).add(ws)


def unregister(call_id: str, ws: WebSocket) -> None:
    _listeners.get(call_id, set()).discard(ws)
    if call_id in _listeners and not _listeners[call_id]:
        del _listeners[call_id]


async def publish(call_id: str, message: dict[str, Any]) -> None:
    """Publish a message to all WS subscribers of call_id.

    Redis path: PUBLISH to the channel; subscribers listening via
    subscribe_call() relay it to their WS connections.
    In-process path: directly send to registered WebSocket objects.
    """
    r = _get_redis()
    if r is not None:
        try:
            await r.publish(_CHANNEL_PREFIX + call_id, json.dumps(message))
            return
        except Exception:
            logger.exception("call_feed: Redis publish failed, falling back to in-process")

    # In-process fallback
    for ws in list(_listeners.get(call_id, ())):
        try:
            await ws.send_json(message)
        except Exception:
            unregister(call_id, ws)


async def subscribe_call(call_id: str, ws: WebSocket) -> None:
    """Subscribe to Redis channel and relay messages to ws.
    Used by the WS endpoint when Redis is active (replaces register/wait loop).
    Falls back to the in-process register pattern if Redis unavailable."""
    r = _get_redis()
    if r is None:
        # In-process: just keep connection alive (relay happens via publish)
        register(call_id, ws)
        try:
            while True:
                await ws.receive_text()
        except Exception:
            pass
        finally:
            unregister(call_id, ws)
        return

    # Redis: subscribe and relay
    async with r.pubsub() as pubsub:
        await pubsub.subscribe(_CHANNEL_PREFIX + call_id)
        try:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                try:
                    await ws.send_text(msg["data"])
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("call_feed: Redis subscribe relay error for call=%s", call_id)
        finally:
            await pubsub.unsubscribe(_CHANNEL_PREFIX + call_id)
