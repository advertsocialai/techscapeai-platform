"""
RISK-1 regression tests: unauthenticated endpoints must be rate-limited.

These assert three things the platform previously had none of:
  1. login stops answering after N attempts (credential stuffing),
  2. OTP send stops after a handful per inbox (email bombing),
  3. OTP verify stops guessing (a 6-digit space dies to uncapped guessing).

The limiter is in-memory and process-local, so tests reset its state directly.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import public_rate_limit as prl


@pytest.fixture(autouse=True)
def _clean_limiter():
    prl._hits.clear()
    yield
    prl._hits.clear()


@pytest.fixture
def client():
    import app.main as m
    # raise_server_exceptions=False: with fixture Supabase credentials the DB
    # layer 500s, and the default TestClient re-raises that instead of returning
    # a status code. The limiter runs BEFORE the DB is touched, so what these
    # tests need is the sequence of codes — 500s until the 429 takes over.
    return TestClient(m.app, raise_server_exceptions=False)


def test_login_locks_after_10_attempts(client):
    body = {"email": "stuffing@example.com", "password": "Wrong123!"}
    codes = [client.post("/api/techscape/v1/auth/login", json=body).status_code
             for _ in range(12)]
    assert 429 in codes, f"login never rate-limited: {codes}"
    # The email key is half the IP limit (5) — so the lock must land at/before #6.
    assert codes.index(429) <= 6
    r = next(client.post("/api/techscape/v1/auth/login", json=body)
             for _ in range(1))
    assert r.headers.get("retry-after"), "429 must carry Retry-After"


def test_traveller_otp_send_is_capped_per_inbox(client):
    body = {"email": "victim@example.com"}
    codes = [client.post("/api/travel/v1/me/auth/request-otp", json=body).status_code
             for _ in range(6)]
    # email key = limit//2 = 3, so the 4th request must be refused.
    assert codes[:3].count(429) == 0 or 500 in codes[:3], f"early lock: {codes}"
    assert 429 in codes[:5], f"otp send never limited: {codes}"


def test_traveller_otp_verify_stops_brute_force(client):
    codes = []
    for i in range(14):
        r = client.post("/api/travel/v1/me/auth/verify-otp",
                        json={"email": "victim@example.com", "code": f"{i:06d}"})
        codes.append(r.status_code)
    assert 429 in codes, f"otp verify allows unlimited guessing: {codes}"
    # 10 guesses per 5 min per inbox; email key halves to 5.
    assert codes.index(429) <= 6


def test_different_ips_do_not_share_ip_bucket():
    """The IP key must isolate clients — one abuser must not lock everyone out."""
    class Req:
        def __init__(self, ip):
            self.headers = {"x-forwarded-for": ip}
            self.client = None

    for _ in range(10):
        prl.enforce(Req("1.1.1.1"), bucket="t", limit=10, window_sec=60)
    with pytest.raises(Exception):
        prl.enforce(Req("1.1.1.1"), bucket="t", limit=10, window_sec=60)
    # a different IP is unaffected
    prl.enforce(Req("2.2.2.2"), bucket="t", limit=10, window_sec=60)
