"""
Row-8 tests: the public rate limiter's Redis backend (multi-worker safe).

Three things test_public_rate_limit.py cannot prove:
  1. THE MULTI-WORKER PROOF (the whole point of the Redis move): two separate
     Python PROCESSES sharing one Redis must share one budget. In-memory each
     process gets its own full limit; with Redis the combined count trips.
     Pattern follows Phase-3 T8 (call_feed): subprocess workers against a
     local redis-server on a non-default port.
  2. The email-at-half-limit semantics survive the backend swap.
  3. Fallback: REDIS_URL pointing at a dead port degrades to the in-memory
     path — no crash, still trips at the limit in-process (call_feed failure
     semantics: log once, keep working).

The local redis-server (port 6390) is started by the module fixture if not
already running; tests skip rather than fail when redis-server is absent.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import public_rate_limit as prl

REDIS_PORT = 6390
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"
API_DIR = Path(__file__).resolve().parents[1]


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _free_port() -> int:
    """A port that is guaranteed closed (bound then released)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Req:
    """Minimal Request stand-in — the limiter only reads headers/client."""

    def __init__(self, ip: str):
        self.headers = {"x-forwarded-for": ip}
        self.client = None


@pytest.fixture(scope="module")
def redis_server():
    if not _port_open(REDIS_PORT):
        try:
            subprocess.run(
                ["redis-server", "--port", str(REDIS_PORT),
                 "--daemonize", "yes", "--save", ""],
                check=True, capture_output=True, timeout=15,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            pytest.skip("redis-server not available in this environment")
        for _ in range(50):
            if _port_open(REDIS_PORT):
                break
            time.sleep(0.1)
        else:
            pytest.skip("redis-server failed to start on port %d" % REDIS_PORT)
    yield REDIS_URL


@pytest.fixture(autouse=True)
def _reset_limiter_state():
    """Fresh backend selection + empty in-memory store around every test."""
    def reset():
        prl._hits.clear()
        prl._redis_client = None
        prl._redis_failed = False
        prl._redis_warned = False
    reset()
    yield
    reset()


# ── 1. The multi-worker proof ───────────────────────────────────────

_WORKER = textwrap.dedent("""\
    import sys
    from fastapi import HTTPException
    from app.core import public_rate_limit as prl

    class Req:
        headers = {"x-forwarded-for": "203.0.113.7"}
        client = None

    bucket, n = sys.argv[1], int(sys.argv[2])
    for _ in range(n):
        try:
            prl.enforce(Req(), bucket=bucket, limit=10, window_sec=60)
            print("OK")
        except HTTPException as e:
            print(e.status_code)
""")


def test_limit_is_shared_across_two_processes(redis_server, tmp_path):
    """
    limit=10 per IP. Process A burns 6 slots, process B fires 6 more.
    In-memory (per-process) B would get 6× OK — each process has its own 10.
    With Redis, B's 5th request is the combined 11th and MUST 429.
    """
    bucket = f"xproc-{uuid.uuid4().hex}"  # unique per run: no stale Redis state
    script = tmp_path / "rl_worker.py"
    script.write_text(_WORKER)
    env = {**os.environ, "REDIS_URL": redis_server, "PYTHONPATH": str(API_DIR)}

    def run_worker(n: int) -> list[str]:
        proc = subprocess.run(
            [sys.executable, str(script), bucket, str(n)],
            capture_output=True, text=True, cwd=API_DIR, env=env, timeout=120,
        )
        assert proc.returncode == 0, f"worker crashed:\n{proc.stderr}"
        return proc.stdout.split()

    lines_a = run_worker(6)
    assert lines_a == ["OK"] * 6, f"process A should be under limit: {lines_a}"

    lines_b = run_worker(6)
    assert "429" in lines_b, (
        f"process B never limited — counting is per-process, not shared: {lines_b}"
    )
    # B's first 4 requests are combined #7-#10 (allowed); its 5th is #11 → 429.
    assert lines_b.index("429") == 4, f"limit tripped at wrong point: {lines_b}"


# ── 2. Semantics preserved on the Redis path ────────────────────────

def _codes(n: int, ip: str, bucket: str, limit: int, email: str | None = None) -> list[int]:
    out = []
    for _ in range(n):
        try:
            prl.enforce(Req(ip), bucket=bucket, limit=limit, window_sec=60, email=email)
            out.append(200)
        except HTTPException as e:
            out.append(e.status_code)
    return out


def test_redis_path_trips_at_limit_with_retry_after(redis_server, monkeypatch):
    monkeypatch.setattr(prl.settings, "REDIS_URL", redis_server)
    bucket = f"unit-{uuid.uuid4().hex}"
    codes = _codes(5, "198.51.100.1", bucket, limit=3)
    assert codes == [200, 200, 200, 429, 429]
    with pytest.raises(HTTPException) as exc:
        prl.enforce(Req("198.51.100.1"), bucket=bucket, limit=3, window_sec=60)
    assert exc.value.headers.get("Retry-After"), "429 must carry Retry-After"
    assert prl._hits == {}, "Redis path must not touch the in-memory store"


def test_email_half_limit_preserved_on_redis(redis_server, monkeypatch):
    monkeypatch.setattr(prl.settings, "REDIS_URL", redis_server)
    bucket = f"mail-{uuid.uuid4().hex}"
    codes = _codes(6, "198.51.100.2", bucket, limit=10, email="Victim@Example.com")
    # email key = limit // 2 = 5 → the 6th request must be refused even though
    # the IP key (10) still has room.
    assert codes == [200] * 5 + [429], f"email half-limit broken: {codes}"


def test_different_ips_isolated_on_redis(redis_server, monkeypatch):
    monkeypatch.setattr(prl.settings, "REDIS_URL", redis_server)
    bucket = f"iso-{uuid.uuid4().hex}"
    assert _codes(4, "198.51.100.3", bucket, limit=3) == [200, 200, 200, 429]
    # a different IP is unaffected
    assert _codes(1, "198.51.100.4", bucket, limit=3) == [200]


# ── 3. Fallback: dead Redis degrades to in-memory, never crashes ────

def test_fallback_to_memory_when_redis_unreachable(monkeypatch):
    dead_url = f"redis://127.0.0.1:{_free_port()}/0"
    monkeypatch.setattr(prl.settings, "REDIS_URL", dead_url)
    bucket = f"dead-{uuid.uuid4().hex}"
    codes = _codes(5, "192.0.2.55", bucket, limit=3)
    assert codes == [200, 200, 200, 429, 429], (
        f"in-memory fallback must still enforce the limit: {codes}"
    )
    assert prl._hits, "fallback must have used the in-memory store"
    assert prl._redis_warned is True, "Redis failure must be logged (once)"


def test_fallback_when_redis_url_unset(monkeypatch):
    monkeypatch.setattr(prl.settings, "REDIS_URL", "")
    bucket = f"nourl-{uuid.uuid4().hex}"
    assert _codes(4, "192.0.2.56", bucket, limit=3) == [200, 200, 200, 429]
    assert prl._get_redis() is None
