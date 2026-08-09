"""
Error tracking behind a Sentry-shaped interface (PLATFORM_STATUS.md: Observability).

WHAT THIS IS AND IS NOT
-----------------------
The platform had structured logging and nothing else: an unhandled exception in
production would be a log line on a box nobody tails. This module gives every
call site one stable function — `capture_exception()` — wired into the global
exception handler, so the day a DSN exists, errors start arriving somewhere
with zero call-site changes.

The interface is deliberately Sentry-shaped (init-with-DSN, capture_exception,
capture_message, before-send scrubbing) because a Sentry account plausibly
already exists for this org. But the sentry-sdk is NOT imported unless a DSN is
configured — no dependency, no network, no startup cost while unconfigured.

STUB TRANSPORT, honestly labelled
---------------------------------
With no SENTRY_DSN, capture_exception() logs the event at ERROR with an
`[error-tracking:stub]` prefix and counts it. That is a STUB: nothing leaves
the process. It exists so the code path is exercised (tests assert against the
counter) and the wiring cannot rot unnoticed — the difference between "we would
have reported this" and "we forgot to call anything" is visible in logs today.

SCRUBBING RUNS IN BOTH MODES. Tokens/passwords are stripped before the event is
even handed to a transport, so a future DSN cannot start exfiltrating
credentials that the stub was quietly logging all along.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SCRUB_KEYS = re.compile(
    r"(password|passwd|secret|token|authorization|api[_-]?key|cookie)", re.I
)
_SCRUB_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")

_lock = threading.Lock()
_state: dict[str, Any] = {"initialised": False, "live": False, "stub_events": 0}


def _scrub(value: Any) -> Any:
    """Strip credential-shaped values from dicts/strings before ANY transport."""
    if isinstance(value, dict):
        return {
            k: ("[scrubbed]" if _SCRUB_KEYS.search(str(k)) else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, str):
        return _SCRUB_BEARER.sub("Bearer [scrubbed]", value)
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def init() -> None:
    """
    Idempotent. Called at app startup. Live mode only when SENTRY_DSN is set
    AND sentry-sdk is importable; otherwise the stub transport, loudly.
    """
    with _lock:
        if _state["initialised"]:
            return
        _state["initialised"] = True

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info(
            "error-tracking: no SENTRY_DSN — stub transport active. Events are "
            "logged locally and counted, nothing leaves the process (BLK-6)."
        )
        return
    try:
        import sentry_sdk  # deferred: not a dependency until a DSN exists

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("ENVIRONMENT", "development"),
            traces_sample_rate=0.0,  # errors only; tracing is a separate decision
            before_send=lambda event, hint: _scrub(event),
        )
        _state["live"] = True
        logger.info("error-tracking: sentry-sdk live")
    except ImportError:
        logger.error(
            "error-tracking: SENTRY_DSN set but sentry-sdk not installed — "
            "falling back to stub. `pip install sentry-sdk` to go live."
        )


def capture_exception(exc: BaseException, *, context: Optional[dict] = None) -> None:
    """The one function call sites use. Never raises."""
    try:
        if _state["live"]:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                for k, v in (_scrub(context) or {}).items():
                    scope.set_extra(k, v)
                sentry_sdk.capture_exception(exc)
            return
        with _lock:
            _state["stub_events"] += 1
            n = _state["stub_events"]
        logger.error(
            "[error-tracking:stub] event #%d %s: %s ctx=%s",
            n, type(exc).__name__, _scrub(str(exc)), _scrub(context or {}),
        )
    except Exception:  # pragma: no cover — tracking must never add a failure
        logger.exception("error-tracking itself failed")


def capture_message(message: str, *, level: str = "warning") -> None:
    try:
        if _state["live"]:
            import sentry_sdk
            sentry_sdk.capture_message(_scrub(message), level=level)
            return
        with _lock:
            _state["stub_events"] += 1
        logger.warning("[error-tracking:stub] message: %s", _scrub(message))
    except Exception:  # pragma: no cover
        logger.exception("error-tracking itself failed")


def stub_event_count() -> int:
    """For tests: proves the wiring fires without a DSN."""
    return int(_state["stub_events"])
