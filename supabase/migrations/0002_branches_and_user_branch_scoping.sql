-- Migration: branches table + branch_id scoping on ts_users + role CHECK widening
-- Phase: 1 | Rollback-able: YES (see ROLLBACK section at bottom)
--
-- Additive only: no drops of data, no data loss. Existing ts_users rows get
-- branch_id = NULL (unscoped / all-branches, matches "admin/super_admin sees all").
--
-- Deviation from gogaga-backend/references/schema.md's suggested default
-- (branch_id -> travel_franchisees): a prior draft of this file had already
-- decided on a dedicated `branches` table instead, matching the shape the
-- verifier's matrix-spec.json expects (POST /branches {"name","city"}).
-- Recon confirms travel_franchisees is a richer, separate franchise-partner
-- concept (owner_name, onboarding, metadata) — reusing it would overload two
-- different meanings onto one table. Keeping the dedicated `branches` table.

-- 1) branches table
CREATE TABLE IF NOT EXISTS public.branches (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    city        VARCHAR(255),
    status      VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_branches_business ON public.branches(business_id);

-- 2) RLS — same migration as the table (this repo: service-role-only pattern).
--    Matches ts_users/ts_businesses: ENABLE RLS + explicit REVOKE ALL from
--    anon/authenticated. No auth.jwt() policies — FastAPI (_deps.py / core
--    /deps.py) is the gatekeeper. Only postgres/service_role bypass RLS.
ALTER TABLE public.branches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.branches FROM anon, authenticated;

-- 3) branch_id scoping on ts_users (nullable = unscoped)
ALTER TABLE public.ts_users
    ADD COLUMN IF NOT EXISTS branch_id UUID REFERENCES public.branches(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_ts_users_branch ON public.ts_users(branch_id);

-- 4) Soft-delete support: DELETE /users/{id} sets status='inactive'.
--    Existing CHECK only allowed ('active','disabled') — widen it additively.
--    'disabled' stays valid for any other existing use; 'inactive' is the
--    value the new soft-delete endpoint writes.
ALTER TABLE public.ts_users DROP CONSTRAINT IF EXISTS ts_users_status_check;
ALTER TABLE public.ts_users ADD CONSTRAINT ts_users_status_check
    CHECK (status IN ('active', 'disabled', 'inactive'));

-- 5) Role CHECK widening: add super_admin/agent (product-spec role names)
--    while keeping every legacy value valid (admin/manager/user/viewer).
--    Mapping used by api/app/core/deps.py: admin==super_admin (highest),
--    manager==admin, user==agent, viewer==viewer (lowest). This migration
--    does not touch existing rows — only new users created via P1's users.py
--    can use the new literal role names going forward.
ALTER TABLE public.ts_users DROP CONSTRAINT IF EXISTS ts_users_role_check;
ALTER TABLE public.ts_users ADD CONSTRAINT ts_users_role_check
    CHECK (role IN ('admin', 'manager', 'user', 'viewer', 'super_admin', 'agent'));

-- ============================================================
-- ROLLBACK (destructive — drops the branches table and its data;
-- ts_users column/constraint changes are reversible with no data loss)
-- ============================================================
-- ALTER TABLE public.ts_users DROP CONSTRAINT IF EXISTS ts_users_role_check;
-- ALTER TABLE public.ts_users ADD CONSTRAINT ts_users_role_check
--     CHECK (role IN ('admin', 'manager', 'user', 'viewer'));
-- ALTER TABLE public.ts_users DROP CONSTRAINT IF EXISTS ts_users_status_check;
-- ALTER TABLE public.ts_users ADD CONSTRAINT ts_users_status_check
--     CHECK (status IN ('active', 'disabled'));
-- DROP INDEX IF EXISTS idx_ts_users_branch;
-- ALTER TABLE public.ts_users DROP COLUMN IF EXISTS branch_id;
-- DROP TABLE IF EXISTS public.branches;
