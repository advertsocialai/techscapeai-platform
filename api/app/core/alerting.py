"""
Alerting rules as code (Observability — stubbed-100%, PLATFORM_STATUS.md).

WHAT THIS IS
------------
The platform has an error-tracking stub (app/core/error_tracking.py) that
counts and logs every captured event, and a VOICE_TURN latency log line, and a
payment webhook that rejects bad signatures. None of those ever *told* anyone
when things went wrong in aggregate. This module closes that gap with a small
in-process rule evaluator:

  RULES (all thresholds env-tunable, see app/core/config.py):
    1. error_rate_spike            — captured-exception rate (per minute, via
                                     error_tracking.stub_event_count() deltas)
                                     exceeds ALERT_ERROR_RATE_PER_MIN.
    2. voice_turn_latency_breach   — median voice-turn total_ms in the last
                                     60s window exceeds ALERT_VOICE_TURN_BUDGET_MS
                                     (the ≤1.1s mouth-to-ear budget), given at
                                     least ALERT_VOICE_TURN_MIN_SAMPLES turns.
                                     Fed by the hook in voice.log_voice_turn().
    3. payment_webhook_sig_failures— ALERT_PAYMENT_SIG_FAILURES or more rejected
                                     webhook signatures in the last 60s window.
                                     Fed by routers/travel/payments.py.

A fired rule calls error_tracking.capture_message(level="error") — i.e. alerts
flow into the SAME transport as errors: the loud [error-tracking:stub] log line
today, Sentry the day a DSN exists, with zero call-site changes.

SELF-FEEDING GUARD: capture_message() itself increments stub_event_count, so
the error-rate baseline is re-taken AFTER alerts fire — an alert can never
count itself into the next window's error rate.

WIRING
------
Periodic evaluation is an asyncio task started from app.main's lifespan, OFF by
default: it runs only when OBSERVABILITY_ALERTS=true (interval:
ALERT_CHECK_INTERVAL_SECONDS, default 60). The recording hooks
(observe_voice_turn / record_payment_signature_failure) are always live — they
are two O(1) appends under a lock — so enabling the loop needs no restart-order
thinking and tests can evaluate rules synchronously via evaluate_rules().

Zero new dependencies: stdlib only.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from app.core import error_tracking
from app.core.config import settings

logger = logging.getLogger(__name__)

# Rules look at a fixed trailing window. One minute matches the "per minute"
# semantics of every threshold and keeps memory bounded regardless of interval.
WINDOW_SECONDS = 60.0

_lock = threading.Lock()
# (monotonic_ts, total_ms) per voice turn — maxlen bounds memory under load.
_voice_turns: deque[tuple[float, int]] = deque(maxlen=2048)
# monotonic_ts per rejected payment-webhook signature.
_payment_sig_failures: deque[float] = deque(maxlen=2048)
_state: dict[str, Optional[float]] = {
    "last_eval_at": None,        # monotonic time of the previous evaluation
    "last_error_count": None,    # stub_event_count() baseline for rule 1
}
_last_fired: dict[str, float] = {}  # rule name -> monotonic time it last fired


@dataclass(frozen=True)
class Alert:
    rule: str
    message: str


# ── Recording hooks (always live, never raise) ────────────────────────────
def observe_voice_turn(*, total_ms: int) -> None:
    """Called from voice.log_voice_turn() — one sample per completed turn."""
    try:
        with _lock:
            _voice_turns.append((time.monotonic(), int(total_ms)))
    except Exception:  # pragma: no cover — telemetry must never break a call
        logger.exception("alerting.observe_voice_turn failed")


def record_payment_signature_failure(*, gateway: str = "unknown") -> None:
    """Called from the payment webhook's 403-reject path."""
    try:
        with _lock:
            _payment_sig_failures.append(time.monotonic())
        logger.info("alerting: recorded payment webhook signature failure (gateway=%s)", gateway)
    except Exception:  # pragma: no cover
        logger.exception("alerting.record_payment_signature_failure failed")


# ── The rules ─────────────────────────────────────────────────────────────
def _rule_error_rate(now: float) -> Optional[Alert]:
    """Fires when captured events per minute exceed ALERT_ERROR_RATE_PER_MIN.

    Uses deltas of error_tracking.stub_event_count() between evaluations
    (works identically in stub and live mode — the counter only counts in
    stub mode, but stub mode is exactly when nobody else is watching).
    First evaluation only establishes the baseline and never fires.
    """
    current = error_tracking.stub_event_count()
    baseline = _state["last_error_count"]
    last_at = _state["last_eval_at"]
    if baseline is None or last_at is None:
        return None
    elapsed = max(now - last_at, 1.0)  # clamp: avoid divide-by-tiny on manual runs
    delta = current - int(baseline)
    per_min = delta * 60.0 / elapsed
    if per_min > settings.ALERT_ERROR_RATE_PER_MIN:
        return Alert(
            "error_rate_spike",
            f"{delta} captured error events in {elapsed:.0f}s "
            f"(~{per_min:.0f}/min, threshold {settings.ALERT_ERROR_RATE_PER_MIN}/min)",
        )
    return None


def _rule_voice_turn_latency(now: float) -> Optional[Alert]:
    """Fires when the MEDIAN turn latency in the window breaches the budget
    (the product SLO is a median ≤1.1s mouth-to-ear, not a worst case —
    a single slow turn is normal; a slow median means every caller feels it)."""
    cutoff = now - WINDOW_SECONDS
    samples = [ms for (t, ms) in _voice_turns if t >= cutoff]
    if len(samples) < settings.ALERT_VOICE_TURN_MIN_SAMPLES:
        return None
    med = statistics.median(samples)
    if med > settings.ALERT_VOICE_TURN_BUDGET_MS:
        return Alert(
            "voice_turn_latency_breach",
            f"median voice-turn latency {med:.0f}ms over last {len(samples)} turns "
            f"(budget {settings.ALERT_VOICE_TURN_BUDGET_MS}ms)",
        )
    return None


def _rule_payment_signature_failures(now: float) -> Optional[Alert]:
    """Fires on a burst of rejected webhook signatures — either someone is
    probing the endpoint or a gateway secret rotated without a config update."""
    cutoff = now - WINDOW_SECONDS
    fails = sum(1 for t in _payment_sig_failures if t >= cutoff)
    if fails >= settings.ALERT_PAYMENT_SIG_FAILURES:
        return Alert(
            "payment_webhook_sig_failures",
            f"{fails} payment webhook signature rejections in the last "
            f"{WINDOW_SECONDS:.0f}s (threshold {settings.ALERT_PAYMENT_SIG_FAILURES}) "
            "— probing attempt or rotated webhook secret",
        )
    return None


_RULES = (_rule_error_rate, _rule_voice_turn_latency, _rule_payment_signature_failures)


# ── Evaluation ────────────────────────────────────────────────────────────
def evaluate_rules(*, fire: bool = True, _now: Optional[float] = None) -> list[Alert]:
    """Evaluate every rule once. Returns the alerts that FIRED (i.e. breached
    AND not suppressed by the per-rule cooldown). With fire=True each one is
    pushed through error_tracking.capture_message(level='error').
    Safe to call from tests without the loop running."""
    now = time.monotonic() if _now is None else _now
    with _lock:
        breached = [a for rule in _RULES if (a := rule(now)) is not None]
        fired: list[Alert] = []
        for a in breached:
            last = _last_fired.get(a.rule)
            if last is not None and (now - last) < settings.ALERT_COOLDOWN_SECONDS:
                continue  # still cooling down — condition already reported
            _last_fired[a.rule] = now
            fired.append(a)
        _state["last_eval_at"] = now
    if fire:
        for a in fired:
            error_tracking.capture_message(f"[alert:{a.rule}] {a.message}", level="error")
    # Re-baseline AFTER firing so our own capture_message calls never feed
    # the next window's error-rate delta (self-feeding guard, see docstring).
    with _lock:
        _state["last_error_count"] = error_tracking.stub_event_count()
    return fired


def reset() -> None:
    """Test helper: clear all recorded samples, baselines and cooldowns."""
    with _lock:
        _voice_turns.clear()
        _payment_sig_failures.clear()
        _state["last_eval_at"] = None
        _state["last_error_count"] = None
        _last_fired.clear()


# ── Periodic loop (started from app.main lifespan when enabled) ───────────
async def run_alert_loop(stop_event: asyncio.Event) -> None:
    """Evaluate rules every ALERT_CHECK_INTERVAL_SECONDS until stop_event.
    First pass only establishes the error-count baseline (rule 1 never fires
    on pass one by construction). Evaluation errors are logged, never fatal."""
    interval = max(5, int(settings.ALERT_CHECK_INTERVAL_SECONDS))
    logger.info("alerting: rule evaluation loop started (interval=%ds, %d rules)",
                interval, len(_RULES))
    while not stop_event.is_set():
        try:
            fired = evaluate_rules()
            if fired:
                logger.warning("alerting: %d rule(s) fired: %s",
                               len(fired), ", ".join(a.rule for a in fired))
        except Exception:  # the loop must survive any rule bug
            logger.exception("alerting: rule evaluation failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
    logger.info("alerting: rule evaluation loop stopped")
