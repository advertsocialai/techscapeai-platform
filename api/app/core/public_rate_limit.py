"""
Rate limiting for UNAUTHENTICATED endpoints (RISK-1 in PLATFORM_STATUS.md).

WHY A SECOND LIMITER EXISTS
---------------------------
The existing limiter (services/techscape/rate_limit.py) is keyed by business_id
and applied inside require_business — which by definition runs AFTER
authentication. Every unauthenticated endpoint was therefore wide open:

    POST /auth/login                    credential stuffing
    POST /auth/otp/send                 email bombing
    POST /auth/password/forgot          email bombing
    POST /travel/v1/me/auth/request-otp email bombing
    POST /travel/v1/me/auth/verify-otp  OTP brute force (6 digits = 1e6 guesses)

There is no business context at these call sites, so the fix cannot reuse the
business-keyed limiter. Keys here are IP and (where applicable) the target
email — IP alone lets one attacker with many addresses bomb one victim's inbox;
email alone lets a botnet stay under per-IP limits. Both, always.

IN-MEMORY, single-process — same honest limitation as the JTI blacklist before
Redis (B-P3-04): multi-worker deployments multiply the effective limit by the
worker count. Acceptable now, noted here so it is a known trade-off rather than
a surprise. The interface takes (key, limit, window) so a Redis swap later is a
transport change, not a call-site change.

Fail-open ON INTERNAL ERROR only (a broken limiter must not take login down),
fail-closed on limit — 429 with Retry-After.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}
_MAX_KEYS = 50_000  # memory backstop: beyond this, oldest-touched keys are evicted


def _allow(key: str, limit: int, window_sec: float) -> tuple[bool, float]:
    """Sliding window. Returns (allowed, seconds_until_next_slot)."""
    now = time.monotonic()
    with _lock:
        if len(_hits) > _MAX_KEYS:
            # Crude but bounded: drop ~10% of keys. An attacker who can churn
            # 50k keys is doing IP rotation the in-memory tier can't stop anyway.
            for k in list(_hits.keys())[: _MAX_KEYS // 10]:
                _hits.pop(k, None)
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > window_sec:
            q.popleft()
        if len(q) >= limit:
            return False, max(0.0, window_sec - (now - q[0]))
        q.append(now)
        return True, 0.0


def client_ip(request: Request) -> str:
    """First X-Forwarded-For hop when present (we deploy behind a proxy), else peer."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, *, bucket: str, limit: int, window_sec: float,
            email: str | None = None) -> None:
    """
    Raise 429 when over. Keys by IP always, and by email additionally when given —
    the email key uses HALF the limit, since one inbox being hammered from many
    IPs is the attack the IP key cannot see.
    """
    try:
        ip = client_ip(request)
        allowed, retry = _allow(f"{bucket}:ip:{ip}", limit, window_sec)
        if allowed and email:
            allowed, retry = _allow(
                f"{bucket}:email:{email.lower()}", max(1, limit // 2), window_sec
            )
        if not allowed:
            logger.warning("public rate limit hit bucket=%s ip=%s", bucket, ip)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Wait a moment and try again.",
                headers={"Retry-After": str(int(retry) + 1)},
            )
    except HTTPException:
        raise
    except Exception:  # pragma: no cover — the limiter must never break login
        logger.exception("public rate limiter failed open bucket=%s", bucket)
