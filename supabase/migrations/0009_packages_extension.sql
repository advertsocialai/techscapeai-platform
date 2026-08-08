-- Migration 0009 — Phase 4 T1: travel_packages extension (Packages CRUD)
-- Phase: 4 | Rollback-able: YES (all changes are additive column/constraint adds)
--
-- VERIFY-DON'T-REBUILD: public.travel_packages ALREADY EXISTS
-- (see database/travel_schema.sql §3). This migration ONLY adds the
-- columns the Phase 4 spec needs on top of the existing shape:
--     id, business_id, name, destination_id, duration_days, base_price_inr,
--     inclusions, exclusions, itinerary_template, min_pax, max_pax,
--     is_active, created_at, updated_at
--
-- REGRESSION-CRITICAL — DO NOT RENAME OR DROP:
--   * base_price_inr  — read by services/travel/catalog_service.py
--                       (list_packages ORDER BY base_price_inr) and by
--                       services/travel/ai_engine.py get_packages() tool-call,
--                       plus itinerary_agent.py and gogaga_seed.py.
--   * duration_days   — read by ai_engine.get_packages() / itinerary_agent.
--                       We ADD `nights` alongside it; we do NOT rename it.
--   * is_active       — DELETE is a SOFT delete (is_active = FALSE); the
--                       existing catalog_service.list_packages() filter
--                       .eq("is_active", True) keeps working unchanged.
--
-- Nothing existing is renamed, retyped or dropped. Additive only.

-- ============================================================
-- 1) New columns (idempotent — ADD COLUMN IF NOT EXISTS everywhere)
-- ============================================================

-- category: this repo uses VARCHAR + CHECK, NEVER Postgres enum types
-- (matches travel_leads.qualification/status/source style).
-- Column and CHECK are added separately so re-running on a DB that
-- already has the column still (re)installs a missing constraint.
ALTER TABLE public.travel_packages
    ADD COLUMN IF NOT EXISTS category VARCHAR(20);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'travel_packages_category_check'
          AND conrelid = 'public.travel_packages'::regclass
    ) THEN
        EXECUTE $ddl$
            ALTER TABLE public.travel_packages
                ADD CONSTRAINT travel_packages_category_check
                CHECK (category IS NULL OR category IN
                       ('budget','luxury','honeymoon','family'))
        $ddl$;
    END IF;
END $$;

-- currency: ISO-4217, defaults to INR (every existing row is INR-priced
-- via base_price_inr). NOT NULL + DEFAULT is safe here — Postgres 11+
-- backfills existing rows without a table rewrite.
ALTER TABLE public.travel_packages
    ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'INR';

-- branch_id: NULL = global package, visible to every branch of the
-- business. Non-NULL = package owned by one branch.
-- ON DELETE SET NULL mirrors 0006_ai_config.sql — deleting a branch
-- degrades its packages to global rather than destroying catalog rows.
ALTER TABLE public.travel_packages
    ADD COLUMN IF NOT EXISTS branch_id UUID REFERENCES public.branches(id) ON DELETE SET NULL;

-- nights: ADDED ALONGSIDE the existing duration_days. duration_days is
-- NOT renamed (ai_engine.get_packages() and itinerary_agent read it).
ALTER TABLE public.travel_packages
    ADD COLUMN IF NOT EXISTS nights INTEGER;

-- Backfill nights from the existing duration_days for pre-existing rows
-- only (NULL-guarded, so re-running is a no-op and never overwrites a
-- value someone set explicitly).
UPDATE public.travel_packages
   SET nights = GREATEST(duration_days - 1, 0)
 WHERE nights IS NULL
   AND duration_days IS NOT NULL;

-- ============================================================
-- 2) Indexes for the new filter axes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_travel_packages_branch
    ON public.travel_packages(branch_id);
CREATE INDEX IF NOT EXISTS idx_travel_packages_category
    ON public.travel_packages(category);
-- Hot path for the list endpoint: business + active + price ordering
CREATE INDEX IF NOT EXISTS idx_travel_packages_business_active
    ON public.travel_packages(business_id, is_active);

-- ============================================================
-- 3) RLS — service-role-only pattern (law 2)
-- ============================================================
-- NOTE: travel_packages ALREADY has RLS enabled
-- (database/travel_schema.sql:74 `ALTER TABLE public.travel_packages
-- ENABLE ROW LEVEL SECURITY;`) and is ALREADY in that file's DO $$ FOREACH
-- revoke block. Both statements below are idempotent and are restated here
-- so this migration is self-contained and safe to apply standalone.
ALTER TABLE public.travel_packages ENABLE ROW LEVEL SECURITY;

-- Postgres has no CREATE POLICY IF NOT EXISTS — DO-block guard (law 6).
-- USING (false) => no direct client access at all; FastAPI's
-- app/core/deps.py require_role() is the only gatekeeper.
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'travel_packages' AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.travel_packages USING (false)';
    END IF;
END $$;

REVOKE ALL ON TABLE public.travel_packages FROM anon, authenticated;

-- ============================================================
-- 4) VERIFICATION (run manually after apply)
-- ============================================================
-- New columns landed, old ones intact:
--   SELECT column_name, data_type, is_nullable, column_default
--     FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='travel_packages'
--    ORDER BY ordinal_position;
--   -- expect base_price_inr + duration_days STILL PRESENT, plus
--   -- category / currency / branch_id / nights.
-- CHECK constraint present:
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid='public.travel_packages'::regclass;
-- RLS on:
--   SELECT relname, relrowsecurity FROM pg_class WHERE relname='travel_packages';
-- Policies:
--   SELECT policyname, cmd, qual FROM pg_policies WHERE tablename='travel_packages';
-- Regression probe (must still return rows for a seeded business):
--   SELECT id, name, duration_days, base_price_inr FROM public.travel_packages
--    WHERE is_active = TRUE ORDER BY base_price_inr LIMIT 5;

-- ============================================================
-- ROLLBACK (non-destructive to pre-existing data — only removes
-- columns/indexes/constraints THIS migration added)
-- ============================================================
-- DROP INDEX IF EXISTS public.idx_travel_packages_business_active;
-- DROP INDEX IF EXISTS public.idx_travel_packages_category;
-- DROP INDEX IF EXISTS public.idx_travel_packages_branch;
-- ALTER TABLE public.travel_packages DROP CONSTRAINT IF EXISTS travel_packages_category_check;
-- ALTER TABLE public.travel_packages DROP COLUMN IF EXISTS nights;
-- ALTER TABLE public.travel_packages DROP COLUMN IF EXISTS branch_id;
-- ALTER TABLE public.travel_packages DROP COLUMN IF EXISTS currency;
-- ALTER TABLE public.travel_packages DROP COLUMN IF EXISTS category;
-- NOTE: the RLS enable + REVOKE are intentionally NOT rolled back — they
-- pre-date this migration (travel_schema.sql) and undoing them would
-- open the table to anon/authenticated.
