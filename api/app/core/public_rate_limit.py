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

TWO BACKENDS, SAME INTERFACE (mirrors services/travel/call_feed.py):

  Redis backend (REDIS_URL set + redis importable): sorted-set sliding window,
    multi-worker safe. Per check, one pipeline runs
        ZREMRANGEBYSCORE key 0 (now-window)   — drop expired hits
        ZADD key {member: now}                — record this hit
        ZCARD key                             — count hits in window
        ZRANGE key 0 0 WITHSCORES             — oldest hit (for Retry-After)
        EXPIRE key window+1                   — GC idle keys
    If the count exceeds the limit, our own member is ZREM'd so a rejected
    request never consumes a slot (same semantics as the in-memory deque).
    The pipeline is one atomic round-trip; the ZREM on reject is a second
    command, so two workers racing at the boundary can each momentarily see
    the other's hit — worst case the limit is enforced one request early,
    never late. Redis path uses wall-clock time.time() (shared across
    processes); the in-memory path keeps time.monotonic().

  In-memory fallback (REDIS_URL unset, redis missing, or Redis erroring):
    the original per-process deque sliding window — the zero-config default.
    Single-process limitation as before: multi-worker deployments multiply
    the effective limit by the worker count. A Redis outage logs ONCE and
    degrades to this path (same failure semantics as call_feed) — it never
    takes login down.

Fail-open ON INTERNAL ERROR only (a broken limiter must not take login down),
fail-closed on limit — 429 with Retry-After.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}
_MAX_KEYS = 50_000  # memory backstop: beyond this, oldest-touched keys are evicted

# ── Redis client (lazy, mirrors call_feed._get_redis) ───────────────
_redis_client = None
_redis_failed = False   # redis package missing — never retry the import
_redis_warned = False   # runtime Redis error already logged once

# Key namespacing, same scheme as call_feed's channel prefix: staging and
# production sharing one Redis instance must not share rate-limit buckets.
_KEY_NAMESPACE = (getattr(settings, "ENVIRONMENT", "") or "unknown").strip().lower()
_KEY_PREFIX = f"gogaga:{_KEY_NAMESPACE}:prl:"


def _get_redis():
    global _redis_client, _redis_failed
    if _redis_failed or not settings.REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # type: ignore
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            # A slow/hung Redis must not add seconds to every login attempt:
            # short timeouts, then the in-memory fallback takes over.
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        logger.info("public_rate_limit: Redis backend active (%s)", settings.REDIS_URL)
    except Exception:
        logger.warning(
            "public_rate_limit: redis package unavailable — using in-process fallback"
        )
        _redis_failed = True
        _redis_client = None
    return _redis_client


def _allow_redis(r, key: str, limit: int, window_sec: float) -> tuple[bool, float]:
    """Sorted-set sliding window in Redis. Returns (allowed, retry_after_sec)."""
    now = time.time()  # wall clock: the score must mean the same in every worker
    member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
    rkey = _KEY_PREFIX + key
    pipe = r.pipeline()
    pipe.zremrangebyscore(rkey, 0, now - window_sec)
    pipe.zadd(rkey, {member: now})
    pipe.zcard(rkey)
    pipe.zrange(rkey, 0, 0, withscores=True)
    pipe.expire(rkey, int(window_sec) + 1)
    _, _, count, oldest, _ = pipe.execute()
    if count > limit:
        r.zrem(rkey, member)  # a rejected request must not consume a slot
        oldest_score = oldest[0][1] if oldest else now
        return False, max(0.0, window_sec - (now - oldest_score))
    return True, 0.0


def _check(key: str, limit: int, window_sec: float) -> tuple[bool, float]:
    """Route one (key, limit, window) check: Redis when available, else memory."""
    global _redis_warned
    r = _get_redis()
    if r is not None:
        try:
            return _allow_redis(r, key, limit, window_sec)
        except Exception:
            if not _redis_warned:
                logger.warning(
                    "public_rate_limit: Redis unavailable — using in-process fallback",
                    exc_info=True,
                )
                _redis_warned = True
    return _allow(key, limit, window_sec)


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
        allowed, retry = _check(f"{bucket}:ip:{ip}", limit, window_sec)
        if allowed and email:
            allowed, retry = _check(
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
