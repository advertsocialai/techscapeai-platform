"""
Shared pytest fixtures for the api/tests/ smoke suite.

This suite is intentionally DB-free — there is no local Supabase stack
wired into CI (or, as of the 2026-08-07 sprint, into most dev sandboxes
either — see BLOCKERS.md B-SPRINT2B-01). Every test here either:
  (a) exercises pure functions that never touch the DB (JWT, HMAC
      signatures, keyword scorers, IST time-window math), or
  (b) imports app.main / app.app to prove the app assembles cleanly and
      registers its expected routes, using fixture (non-real) Supabase/
      JWT settings that only need to satisfy pydantic-settings' "field is
      present" validation — nothing here ever calls out to Supabase.

Real per-role RBAC / RLS / live-call verification still requires an
actual Supabase project — see gogaga-verifier's scripts/regression_check.sh
and scripts/access_matrix.py for those (they need real credentials this
suite deliberately does not use).
"""
from __future__ import annotations
import os

# Must be set BEFORE any `app.*` import anywhere in the test session —
# app.core.config.settings is built at import time (module-level
# `settings = get_settings()`), so conftest.py (which pytest always
# imports first) is the one safe place to guarantee ordering.
os.environ.setdefault("SUPABASE_URL", "http://fixture.invalid")
os.environ.setdefault("SUPABASE_ANON_KEY", "fixture-anon-key-not-real")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "fixture-service-key-not-real")
os.environ.setdefault("JWT_SECRET", "fixture-jwt-secret-not-real")
os.environ.setdefault("JWT_REFRESH_SECRET", "fixture-jwt-refresh-not-real")
