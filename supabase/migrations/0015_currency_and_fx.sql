-- Migration 0015 — Phase 4 T8: multi-currency (branches.currency + fx_rate_snapshots)
-- Phase: 4 | Rollback-able: YES (see ROLLBACK section at bottom)
--
-- ═══════════════════════════════════════════════════════════════════════════
-- SPEC DEVIATION — READ THIS FIRST
-- ═══════════════════════════════════════════════════════════════════════════
-- The Phase 4 spec assumes public.branches already has a `currency` column.
-- It does NOT. Verified against migration 0002_branches_and_user_branch_scoping.sql,
-- which creates branches with exactly: id, business_id, name, city, status,
-- created_at. Nothing else has added a currency column since. This migration
-- therefore ADDS it (additively, with a safe 'INR' default that matches every
-- existing domestic branch) rather than assuming it.
--
-- ═══════════════════════════════════════════════════════════════════════════
-- FINANCIAL INTEGRITY RULE — ABSOLUTE, NON-NEGOTIABLE
-- ═══════════════════════════════════════════════════════════════════════════
-- Any historical rollup, report, or reconciliation that converts between
-- currencies MUST use the STORED SNAPSHOT RATE that was in effect at the
-- timestamp of the underlying financial event — NEVER a freshly fetched or
-- live-recalculated rate.
--
-- Why: a revenue report for July, re-run in September, must produce byte-identical
-- numbers. If conversion used "today's rate", every re-run would silently restate
-- history, reconciliation against bank/gateway settlements would drift, and the
-- books would never close. Determinism over freshness — always.
--
-- Concretely:
--   * fx_rate_snapshots is APPEND-ONLY. Never UPDATE a rate row; capture a new
--     snapshot instead. The UNIQUE (base, quote, captured_at) key enforces one
--     observation per pair per instant.
--   * All conversion goes through public.fx_rate_at(base, quote, at), which
--     resolves the most recent snapshot whose captured_at <= `at` — i.e. the
--     rate that was in effect at that moment, as known at that moment.
--   * fx_rate_at() is declared STABLE (not VOLATILE): for a fixed `at` it always
--     returns the same value within a transaction, and never performs I/O.
--   * A rollup written as
--         SELECT sum(amount * public.fx_rate_at(currency, 'INR', created_at))
--         FROM   public.payment_links WHERE status = 'paid' ...
--     is deterministic on re-run. A rollup written against a live rate is a bug.
--   * If no snapshot exists at or before `at`, fx_rate_at() returns NULL — it
--     deliberately does NOT fall back to the newest available rate, because a
--     silent forward-fill would fabricate history. Callers must surface the gap.
--
-- Additive only: one nullable-safe column add + one new table + one new function.

-- ── 1) branches.currency (the column the spec assumed already existed) ────
-- CHAR(3), ISO-4217. Default 'INR' backfills every existing row correctly:
-- all branches predating Phase 4 are domestic Indian branches.
ALTER TABLE public.branches
    ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'INR';

-- ── 2) fx_rate_snapshots — append-only rate observation ledger ────────────
-- rate semantics: 1 unit of base_currency == `rate` units of quote_currency.
--   e.g. base='USD', quote='INR', rate=83.12000000  →  1 USD = 83.12 INR
-- NUMERIC(18,8): 8 decimal places is enough for every fiat pair including
-- low-value bases (e.g. IDR→INR); NUMERIC, never float — no binary rounding.
CREATE TABLE IF NOT EXISTS public.fx_rate_snapshots (
    id              UUID           PRIMARY KEY DEFAULT gen_random_uuid(),

    base_currency   CHAR(3)        NOT NULL,
    quote_currency  CHAR(3)        NOT NULL,
    rate            NUMERIC(18,8)  NOT NULL CHECK (rate > 0),

    -- Provenance of the observation. VARCHAR + CHECK, never a Postgres enum
    -- (repo convention — see travel_leads.status).
    source          VARCHAR(50)    NOT NULL DEFAULT 'manual'
                                   CHECK (source IN ('manual', 'openexchangerates', 'ecb', 'razorpay', 'stripe', 'stub')),

    -- The instant this rate was observed to be in effect. This is the axis
    -- fx_rate_at() searches; it is NOT created_at (which is merely when the
    -- row was written, and may lag a backfilled observation by days).
    captured_at     TIMESTAMPTZ    NOT NULL DEFAULT now(),

    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),

    CONSTRAINT fx_rate_snapshots_pair_instant_unique
        UNIQUE (base_currency, quote_currency, captured_at),

    -- A self-pair rate is always 1 by definition; storing one invites drift.
    CONSTRAINT fx_rate_snapshots_no_self_pair
        CHECK (base_currency <> quote_currency)
);

-- Primary access path: "newest snapshot for this pair at or before T".
-- DESC on captured_at makes that an index-backed single-row lookup.
CREATE INDEX IF NOT EXISTS idx_fx_rate_snapshots_pair_time
    ON public.fx_rate_snapshots(base_currency, quote_currency, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_fx_rate_snapshots_captured_at
    ON public.fx_rate_snapshots(captured_at DESC);

-- ── 3) fx_rate_at() — THE point-in-time resolver ──────────────────────────
-- Returns the rate in effect at `at_ts`: the most recent snapshot whose
-- captured_at <= at_ts. This is the ONLY sanctioned way to convert money
-- for a historical event.
--
-- Contract:
--   base = quote            → 1.0 (identity, no table read)
--   snapshot exists <= at_ts → that snapshot's rate
--   no snapshot <= at_ts     → NULL  (caller MUST handle; no forward-fill,
--                                     no "nearest rate" — fabricating history
--                                     is worse than a visible gap)
--
-- STABLE, not VOLATILE: same inputs → same output within a transaction, which
-- is exactly the determinism guarantee the rollups depend on.
CREATE OR REPLACE FUNCTION public.fx_rate_at(
    p_base_currency  CHAR(3),
    p_quote_currency CHAR(3),
    p_at             TIMESTAMPTZ
)
RETURNS NUMERIC(18,8)
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN upper(p_base_currency) = upper(p_quote_currency) THEN 1.0::NUMERIC(18,8)
        ELSE (
            SELECT f.rate
            FROM   public.fx_rate_snapshots f
            WHERE  upper(f.base_currency)  = upper(p_base_currency)
              AND  upper(f.quote_currency) = upper(p_quote_currency)
              AND  f.captured_at <= p_at
            ORDER BY f.captured_at DESC
            LIMIT 1
        )
    END;
$$;

COMMENT ON FUNCTION public.fx_rate_at(CHAR(3), CHAR(3), TIMESTAMPTZ) IS
    'Point-in-time FX resolver. Returns the stored snapshot rate in effect at p_at '
    '(most recent captured_at <= p_at), or NULL if none exists. Historical rollups '
    'MUST use this and never a live rate, so a re-run days later is byte-identical.';

-- ── 4) RLS — SAME migration as the table (service-role-only pattern) ──────
ALTER TABLE public.fx_rate_snapshots ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'fx_rate_snapshots'
          AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.fx_rate_snapshots USING (false)';
    END IF;
END $$;

DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['fx_rate_snapshots'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- branches already had RLS enabled + revoked in 0002; adding a column does not
-- change that. Re-asserted here idempotently so this file is self-contained.
ALTER TABLE public.branches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.branches FROM anon, authenticated;

-- ============================================================
-- ROLLBACK
--   * fx_rate_snapshots DROP is destructive (loses rate history — and with it
--     the ability to re-run any historical multi-currency rollup deterministically).
--     Export the table before rolling back.
--   * branches.currency DROP is non-destructive beyond the column itself
--     (every value is the 'INR' default unless explicitly set).
-- ============================================================
-- DROP FUNCTION IF EXISTS public.fx_rate_at(CHAR(3), CHAR(3), TIMESTAMPTZ);
-- DROP INDEX IF EXISTS idx_fx_rate_snapshots_captured_at;
-- DROP INDEX IF EXISTS idx_fx_rate_snapshots_pair_time;
-- DROP TABLE IF EXISTS public.fx_rate_snapshots;
-- ALTER TABLE public.branches DROP COLUMN IF EXISTS currency;
