"""Import-level smoke tests — the check that would have caught the Phase 1
deps.py/security.py import-break documented in PHASE2_REPORT.md before it
ever hit a live loop."""
from __future__ import annotations


def test_app_imports_and_registers_routes():
    import app.main as m

    assert m.app is not None
    assert len(m.app.routes) > 50, "expected the real route count, got suspiciously few"


def test_expected_travel_and_voice_routes_present():
    import app.main as m

    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    expected = {
        "/api/health",
        "/api/travel/v1/wiki",
        "/api/travel/v1/leads",
        "/api/travel/v1/calls/live",
        "/api/travel/v1/ai-config",
        "/api/travel/v1/ai-config/seed",
        "/api/travel/v1/webhook/{provider}/voice",
        "/api/travel/v1/webhook/{provider}/stream",
        "/api/travel/v1/calls/{call_id}/takeover/monitor",
        "/api/travel/v1/calls/{call_id}/takeover/barge",
        "/api/travel/v1/calls/{call_id}/takeover/full",
        "/api/travel/v1/calls/{call_id}/takeover/release",
        "/ws/calls/{call_id}",
    }
    missing = expected - paths
    assert not missing, f"expected routes missing from the app: {missing}"
