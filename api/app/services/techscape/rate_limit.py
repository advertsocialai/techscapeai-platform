"""
In-memory token-bucket rate limiter keyed by (business_id, route).
Tier limits per spec §1: starter/professional/enterprise.

This is intentionally process-local. For multi-instance prod use Redis or
the Postgres advisory-lock approach.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from threading import Lock
from typing import Optional


# requests-per-minute per business tier
TIER_LIMITS = {
    "starter":      60,
    "professional": 300,
    "enterprise":   1500,
}


@dataclass
class _Bucket:
    capacity: int
    tokens:   float
    refilled: float


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock    = Lock()

    def allow(self, *, business_id: str, route: str, tier: str) -> tuple[bool, int]:
        """
        Try to consume one token. Returns (allowed, remaining).
        Replenishes at capacity / 60 tokens per second.
        """
        key      = f"{business_id}:{route}"
        capacity = TIER_LIMITS.get(tier, TIER_LIMITS["starter"])
        per_sec  = capacity / 60.0
        now      = time.monotonic()

        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(capacity=capacity, tokens=capacity - 1, refilled=now)
                self._buckets[key] = b
                return True, int(b.tokens)

            elapsed   = now - b.refilled
            b.tokens  = min(capacity, b.tokens + elapsed * per_sec)
            b.refilled = now

            if b.tokens >= 1:
                b.tokens -= 1
                return True, int(b.tokens)
            return False, 0

    def reset(self) -> None:  # pragma: no cover - test helper
        with self._lock:
            self._buckets.clear()


_singleton: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _singleton
    if _singleton is None:
        _singleton = RateLimiter()
    return _singleton
