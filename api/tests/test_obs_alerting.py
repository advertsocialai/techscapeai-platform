"""
Observability: alerting rules as code (app/core/alerting.py).

DB-free like the rest of this suite (fixture env from conftest.py, no network).
Covers each rule's fire/no-fire boundary, the cooldown, the self-feeding guard
(an alert's own capture_message must not count into the next error-rate
window), and BOTH producer hooks — voice.log_voice_turn() and the payment
webhook's 403 path — because "a function that exists, is correct, and is never
called" is this repo's recurring failure mode: rule code without wired
producers would evaluate forever against empty data and never fire.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core import alerting, error_tracking
from app.core.config import settings


@pytest.fixture(autouse=True)
def clean_alerting():
    """Every test starts with no samples, no baselines, no cooldowns."""
    alerting.reset()
    yield
    alerting.reset()


# ── Rule 1: error-rate spike ──────────────────────────────────────────────
def test_first_evaluation_only_baselines_and_never_fires():
    # Even with prior stub events on the global counter, pass one has no
    # baseline to diff against — it must observe, not fire.
    error_tracking.capture_message("pre-existing noise")
    assert alerting.evaluate_rules() == []


def test_error_rate_spike_fires_and_reports_through_error_tracking():
    alerting.evaluate_rules()  # establish baseline
    for i in range(settings.ALERT_ERROR_RATE_PER_MIN + 5):
        error_tracking.capture_exception(RuntimeError(f"boom {i}"))
    before = error_tracking.stub_event_count()
    fired = alerting.evaluate_rules()
    assert [a.rule for a in fired] == ["error_rate_spike"]
    # The alert itself went through capture_message (stub transport counts it).
    assert error_tracking.stub_event_count() == before + 1


def test_quiet_system_fires_nothing():
    alerting.evaluate_rules()
    assert alerting.evaluate_rules() == []


def test_fired_alert_does_not_feed_next_windows_error_rate(monkeypatch):
    """Self-feeding guard: the capture_message an alert emits is re-baselined
    away, so with cooldown disabled the next evaluation stays quiet."""
    monkeypatch.setattr(settings, "ALERT_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "ALERT_ERROR_RATE_PER_MIN", 0)
    alerting.evaluate_rules()
    error_tracking.capture_exception(RuntimeError("one real error"))
    assert [a.rule for a in alerting.evaluate_rules()] == ["error_rate_spike"]
    # No new real errors since — only the alert's own message. Must not re-fire.
    assert alerting.evaluate_rules() == []


# ── Rule 2: voice-turn latency budget ─────────────────────────────────────
def _observe_turns(latencies_ms):
    for ms in latencies_ms:
        alerting.observe_voice_turn(total_ms=ms)


def test_voice_latency_breach_fires_on_slow_median():
    _observe_turns([1500, 1600, 1700, 1800, 1900, 2000])  # median 1750 > 1100
    fired = alerting.evaluate_rules()
    assert [a.rule for a in fired] == ["voice_turn_latency_breach"]
    assert "1750" in fired[0].message


def test_voice_latency_judges_median_not_worst_case():
    # One catastrophic turn among fast ones: median 900 ≤ 1100 → no alert.
    _observe_turns([850, 880, 900, 920, 950, 9000])
    assert alerting.evaluate_rules() == []


def test_voice_latency_needs_min_samples(monkeypatch):
    monkeypatch.setattr(settings, "ALERT_VOICE_TURN_MIN_SAMPLES", 5)
    _observe_turns([3000, 3000, 3000, 3000])  # 4 < 5 — too few to judge
    assert alerting.evaluate_rules() == []


def test_log_voice_turn_hook_actually_feeds_the_rule():
    """Producer wiring: the real VOICE_TURN log call must land samples here."""
    from app.services.travel.voice import log_voice_turn

    for seq in range(1, 7):
        log_voice_turn(call_id="c-hook", seq=seq, stt_ms=300, llm_ttft_ms=400,
                       llm_total_ms=700, tts_ttfb_ms=200, total_ms=2500,
                       engine="deepgram", lang="en")
    fired = alerting.evaluate_rules()
    assert [a.rule for a in fired] == ["voice_turn_latency_breach"]


# ── Rule 3: payment webhook signature failures ────────────────────────────
def test_payment_sig_failures_fire_at_threshold():
    for _ in range(settings.ALERT_PAYMENT_SIG_FAILURES):
        alerting.record_payment_signature_failure(gateway="stub")
    fired = alerting.evaluate_rules()
    assert [a.rule for a in fired] == ["payment_webhook_sig_failures"]


def test_payment_sig_failures_below_threshold_stay_quiet():
    for _ in range(settings.ALERT_PAYMENT_SIG_FAILURES - 1):
        alerting.record_payment_signature_failure(gateway="stub")
    assert alerting.evaluate_rules() == []


def test_rejected_webhook_403_path_records_a_failure():
    """Producer wiring: a real tampered webhook must increment the counter."""
    import app.main as m
    from app.services.payments.stub_gateway import StubGateway

    raw = json.dumps({"event": "payment_link.paid",
                      "payment_link_id": "plink_x"}).encode()
    sig = StubGateway().sign(raw)
    c = TestClient(m.app, raise_server_exceptions=False)
    r = c.post("/api/travel/v1/webhook/razorpay", content=raw + b" ",  # tampered
               headers={"X-Razorpay-Signature": sig,
                        "Content-Type": "application/json"})
    assert r.status_code == 403
    for _ in range(settings.ALERT_PAYMENT_SIG_FAILURES - 1):
        alerting.record_payment_signature_failure(gateway="stub")
    # The webhook's own rejection supplies the final count needed to fire.
    assert [a.rule for a in alerting.evaluate_rules()] == ["payment_webhook_sig_failures"]


# ── Cooldown ──────────────────────────────────────────────────────────────
def test_cooldown_suppresses_immediate_refire():
    for _ in range(settings.ALERT_PAYMENT_SIG_FAILURES):
        alerting.record_payment_signature_failure(gateway="stub")
    assert len(alerting.evaluate_rules()) == 1
    # Condition still true, but within ALERT_COOLDOWN_SECONDS → suppressed.
    assert alerting.evaluate_rules() == []


def test_cooldown_expiry_allows_refire(monkeypatch):
    monkeypatch.setattr(settings, "ALERT_COOLDOWN_SECONDS", 0)
    for _ in range(settings.ALERT_PAYMENT_SIG_FAILURES):
        alerting.record_payment_signature_failure(gateway="stub")
    assert len(alerting.evaluate_rules()) == 1
    assert len(alerting.evaluate_rules()) == 1  # cooldown 0 → fires again


# ── Loop wiring ───────────────────────────────────────────────────────────
def test_alert_loop_is_gated_by_settings_flag():
    """The lifespan only launches the loop when OBSERVABILITY_ALERTS is true
    (default false). Assert the default so nobody flips it silently."""
    assert settings.OBSERVABILITY_ALERTS is False


@pytest.mark.parametrize("name", [
    "ALERT_CHECK_INTERVAL_SECONDS", "ALERT_ERROR_RATE_PER_MIN",
    "ALERT_VOICE_TURN_BUDGET_MS", "ALERT_VOICE_TURN_MIN_SAMPLES",
    "ALERT_PAYMENT_SIG_FAILURES", "ALERT_COOLDOWN_SECONDS",
])
def test_thresholds_are_configurable(name):
    assert isinstance(getattr(settings, name), int)
