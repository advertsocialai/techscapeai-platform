"""
Outbound webhook queue worker.

Reads pending rows from `ts_webhook_queue` and POSTs each `event_payload` to
its `webhook_url`. Failures are retried with exponential backoff, capped at
`max_attempts`.

Started by the FastAPI lifespan when ENABLE_WEBHOOK_WORKER=1 (or always in DEBUG).
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.security import hmac_sha256_hex
from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

POLL_SECONDS = 15


async def deliver_one(row: dict) -> dict:
    """Attempt a single delivery. Returns the patch to write back."""
    url     = row["webhook_url"]
    payload = row.get("event_payload") or {}
    secret  = settings.WAPI_WEBHOOK_SECRET  # reuse signing secret for outbound
    headers = {"Content-Type": "application/json"}
    body_bytes = httpx._content.encode_request(json=payload)[1]  # type: ignore[attr-defined]
    if secret:
        headers["X-Event-Signature"] = "sha256=" + hmac_sha256_hex(secret, body_bytes)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
        if 200 <= r.status_code < 300:
            return {"delivery_status": "delivered",
                    "attempt_count":   (row.get("attempt_count") or 0) + 1,
                    "next_retry_at":   None,
                    "last_error":      None}
        return _retry_patch(row, f"HTTP {r.status_code}")
    except Exception as e:
        return _retry_patch(row, str(e)[:240])


def _retry_patch(row: dict, error: str) -> dict:
    attempts = (row.get("attempt_count") or 0) + 1
    cap      = row.get("max_attempts") or 5
    if attempts >= cap:
        return {"delivery_status": "failed", "attempt_count": attempts,
                "next_retry_at": None, "last_error": error}
    backoff = timedelta(seconds=min(900, 30 * (2 ** (attempts - 1))))
    next_ts = datetime.now(timezone.utc) + backoff
    return {"delivery_status": "pending", "attempt_count": attempts,
            "next_retry_at": next_ts.isoformat(), "last_error": error}


async def run_loop(stop_event: asyncio.Event) -> None:  # pragma: no cover - long running
    db = get_supabase_admin()
    logger.info("webhook worker started, polling every %ss", POLL_SECONDS)
    while not stop_event.is_set():
        try:
            now = datetime.now(timezone.utc).isoformat()
            rows = (
                db.table("ts_webhook_queue").select("*")
                .eq("delivery_status", "pending")
                .or_(f"next_retry_at.is.null,next_retry_at.lte.{now}")
                .limit(20).execute().data or []
            )
            for row in rows:
                patch = await deliver_one(row)
                db.table("ts_webhook_queue").update(patch).eq("id", row["id"]).execute()
        except Exception:
            logger.exception("webhook_worker iteration failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("webhook worker stopped")
