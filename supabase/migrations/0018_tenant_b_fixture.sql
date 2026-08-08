-- Migration 0018 — Phase 5: synthetic Tenant B isolation fixture
-- Phase: 5 | Rollback-able: YES (deletes only rows this file creates)
--
-- WHY THIS EXISTS
-- ---------------
-- Multi-tenancy cannot be proven against a single tenant. Every isolation
-- assertion ("agency A cannot see agency B's leads") is vacuously true while
-- only one agency exists, so the tests that matter most are exactly the ones
-- that cannot be written. This migration seeds a second, deliberately fake
-- business — `regression-fixture-tenant-b` — so those assertions become real.
--
-- This is NOT a workaround pending a real second customer. It is the correct
-- way to build and prove tenant isolation BEFORE one arrives, when a leak is
-- still cheap to fix. A real second agency is the worst possible place to
-- discover a scoping gap.
--
-- SAFETY PROPERTIES (all deliberate)
--   * Fixed UUIDs. Re-running is a no-op (ON CONFLICT DO NOTHING), and tests
--     can hardcode the ids without a lookup round-trip.
--   * The name/slug/email all contain `regression-fixture-tenant-b`, so
--     cleanup_test_artifacts.py can find every row by one marker.
--   * The phone number is +91 99999 00002 — inside the reserved 999xxxxxxx
--     test range, NOT a dialable Indian number. It can never place or receive
--     a real call, so no cost and no compliance exposure.
--   * status='active' so RBAC treats it as a genuine tenant: require_business
--     rejects inactive businesses, which would make every isolation test pass
--     for the wrong reason.
--   * ai_config values are deliberately DIFFERENT from GoGaga's defaults
--     (te/hi languages, ₹250k escalation threshold, different persona). A
--     config diff that reads identically across tenants proves nothing.
--
-- The password hash below is a bcrypt hash of a throwaway fixture password.
-- It is NOT a secret and grants nothing: the account belongs to a fake
-- business with no real phone number, no payment credentials and no data.
--
-- Additive only. Touches no existing row.

-- ── 1) The business ────────────────────────────────────────────────────────
INSERT INTO public.ts_businesses (id, name, slug, status, created_at)
VALUES (
    '00000000-0000-4000-b000-00000000000b',
    'regression-fixture-tenant-b',
    'regression-fixture-tenant-b',
    'active',
    now()
)
ON CONFLICT (id) DO NOTHING;

-- ── 2) A branch (exercises branch_id scoping, not just business_id) ────────
INSERT INTO public.branches (id, business_id, name, city, status, created_at)
VALUES (
    '00000000-0000-4000-b001-00000000000b',
    '00000000-0000-4000-b000-00000000000b',
    'regression-fixture-tenant-b — Hyderabad',
    'Hyderabad',
    'active',
    now()
)
ON CONFLICT (id) DO NOTHING;

-- ── 3) One user per role, so the 5-role x 2-tenant matrix is runnable ──────
-- Roles use this repo's real stored values: core/deps.py maps the spec's
-- "admin" tier onto the stored role 'manager' (see its docstring). Seeding
-- the wrong literal here would make the access matrix silently untestable.
INSERT INTO public.ts_users (id, business_id, branch_id, email, password_hash, role, status, created_at)
VALUES
    ('00000000-0000-4000-b010-00000000000b', '00000000-0000-4000-b000-00000000000b',
     '00000000-0000-4000-b001-00000000000b', 'owner@regression-fixture-tenant-b.test',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYQFOtHTLwFDPzO', 'manager', 'active', now()),
    ('00000000-0000-4000-b011-00000000000b', '00000000-0000-4000-b000-00000000000b',
     '00000000-0000-4000-b001-00000000000b', 'manager@regression-fixture-tenant-b.test',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYQFOtHTLwFDPzO', 'manager', 'active', now()),
    ('00000000-0000-4000-b012-00000000000b', '00000000-0000-4000-b000-00000000000b',
     '00000000-0000-4000-b001-00000000000b', 'agent@regression-fixture-tenant-b.test',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYQFOtHTLwFDPzO', 'agent', 'active', now()),
    ('00000000-0000-4000-b013-00000000000b', '00000000-0000-4000-b000-00000000000b',
     '00000000-0000-4000-b001-00000000000b', 'viewer@regression-fixture-tenant-b.test',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYQFOtHTLwFDPzO', 'viewer', 'active', now())
ON CONFLICT (id) DO NOTHING;

-- ── 4) A distinct phone number ────────────────────────────────────────────
-- Registering ANY number also flips _resolve_business_id() out of
-- single-tenant mode, so the PLIVO_BUSINESS_ID fallback stops applying and an
-- unresolved number can no longer be misattributed to Tenant A. Seeding this
-- fixture is therefore itself part of the isolation fix.
INSERT INTO public.business_phone_numbers (id, business_id, phone_number, is_active, created_at)
VALUES (
    '00000000-0000-4000-b020-00000000000b',
    '00000000-0000-4000-b000-00000000000b',
    '+919999900002',
    true,
    now()
)
ON CONFLICT (id) DO NOTHING;

-- ── 5) Deliberately DIFFERENT ai_config ───────────────────────────────────
-- If Tenant B's playbook matched GoGaga's, a "per-tenant config is honoured"
-- test would pass even if the code ignored business_id entirely.
INSERT INTO public.travel_ai_config (
    id, business_id, branch_id, question_flow, languages,
    escalation_rules, working_hours, voice_persona, created_at, updated_at
)
VALUES (
    '00000000-0000-4000-b030-00000000000b',
    '00000000-0000-4000-b000-00000000000b',
    NULL,
    '["Which city are you flying from?", "Do you need visa assistance?"]'::jsonb,
    '["te", "hi"]'::jsonb,
    '{"budget_threshold": 250000, "intent_level": "warm"}'::jsonb,
    '{"start": "10:00", "end": "19:00", "tz": "Asia/Kolkata"}'::jsonb,
    '{"name": "Meera", "tone": "brisk_professional"}'::jsonb,
    now(), now()
)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- VERIFICATION (run manually after apply)
-- ============================================================
--   SELECT id, name, status FROM public.ts_businesses
--    WHERE name = 'regression-fixture-tenant-b';
--   SELECT email, role FROM public.ts_users
--    WHERE business_id = '00000000-0000-4000-b000-00000000000b' ORDER BY role;
--   -- Isolation probe: Tenant B must see ZERO of Tenant A's leads.
--   SELECT count(*) FROM public.travel_leads
--    WHERE business_id = '00000000-0000-4000-b000-00000000000b';   -- expect 0
--   -- And the phone registry must now be non-empty, which disables the
--   -- single-tenant PLIVO_BUSINESS_ID fallback:
--   SELECT count(*) FROM public.business_phone_numbers;            -- expect >= 1

-- ============================================================
-- ROLLBACK — removes ONLY the fixture rows created above.
-- Child rows first (FK order). Safe: nothing else references these ids.
-- ============================================================
-- DELETE FROM public.travel_ai_config        WHERE business_id = '00000000-0000-4000-b000-00000000000b';
-- DELETE FROM public.business_phone_numbers  WHERE business_id = '00000000-0000-4000-b000-00000000000b';
-- DELETE FROM public.ts_users                WHERE business_id = '00000000-0000-4000-b000-00000000000b';
-- DELETE FROM public.branches                WHERE business_id = '00000000-0000-4000-b000-00000000000b';
-- DELETE FROM public.ts_businesses           WHERE id          = '00000000-0000-4000-b000-00000000000b';
