-- Migration 0016 — Phase 4 T9: usage_metrics (cost & usage tracking)
-- Phase: 4 | Rollback-able: YES (new table — DROP loses only metric rows
--                                created after this migration)
--
-- One row per costed unit of work — normally one per call, but the shape
-- also allows per-turn rows (call_id repeated) if finer granularity is
-- wired later.
--
-- ############################################################
-- # FINANCIAL INTEGRITY — READ BEFORE USING THIS TABLE       #
-- ############################################################
-- `is_estimated` is LOAD-BEARING and NOT NULL ON PURPOSE (no default —
-- every writer must state, explicitly, whether the number is measured):
--
--   is_estimated = TRUE  → cost_usd was COMPUTED from a rate card
--                          (provider rate x unit). It is a MODEL, not money
--                          that was actually billed. It may be wrong.
--   is_estimated = FALSE → cost_usd came from a provider's own metered
--                          usage/billing API and is reconciled to an invoice.
--
-- AS OF THIS MIGRATION, EVERY ROW IS is_estimated = TRUE.
-- Phase 2B (real provider usage logging) never ran, so no real provider
-- usage data is recorded anywhere in this system. There is no code path
-- today that can honestly write is_estimated = FALSE, and none should be
-- added until a provider usage/billing API is actually integrated and
-- reconciled. GET /analytics/cost must therefore label its entire output
-- as estimated. Never present an estimate as a measurement.
--
-- The rate card lives in app/services/travel/usage_service.py as named
-- constants; `rate_card_version` records WHICH card produced `cost_usd` so
-- old rows stay interpretable after a re-price.
--
-- CONVENTIONS: VARCHAR + CHECK (never Postgres enum types); service-role-only
-- RLS in the same migration; additive only.

CREATE TABLE IF NOT EXISTS public.usage_metrics (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id         UUID          NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- NULL = usage not attributable to one call (batch embedding job,
    -- WhatsApp summary generation, morning brief, ...).
    -- SET NULL, not CASCADE: deleting a call must not silently erase the
    -- cost it incurred — the money was still spent.
    call_id             UUID          REFERENCES public.travel_calls(id) ON DELETE SET NULL,

    -- Denormalised so GET /analytics/cost?branch= filters without a join
    -- (travel_calls carries no branch_id).
    branch_id           UUID          REFERENCES public.branches(id) ON DELETE SET NULL,

    -- ── Metered / modelled units ────────────────────────────────────────
    stt_engine          VARCHAR(20)   CHECK (stt_engine IS NULL OR stt_engine IN
                            ('deepgram', 'sarvam', 'whisper', 'other')),
    stt_seconds         NUMERIC(12, 3) NOT NULL DEFAULT 0 CHECK (stt_seconds        >= 0),
    llm_input_tokens    INTEGER        NOT NULL DEFAULT 0 CHECK (llm_input_tokens   >= 0),
    llm_output_tokens   INTEGER        NOT NULL DEFAULT 0 CHECK (llm_output_tokens  >= 0),
    tts_characters      INTEGER        NOT NULL DEFAULT 0 CHECK (tts_characters     >= 0),
    telephony_seconds   NUMERIC(12, 3) NOT NULL DEFAULT 0 CHECK (telephony_seconds  >= 0),

    -- Which provider/model priced each unit. Nullable: the rate card falls
    -- back to its documented default when these are unset.
    llm_model           VARCHAR(50),
    tts_engine          VARCHAR(20)   CHECK (tts_engine IS NULL OR tts_engine IN
                            ('elevenlabs', 'sarvam', 'other')),
    telephony_provider  VARCHAR(20)   CHECK (telephony_provider IS NULL OR telephony_provider IN
                            ('plivo', 'twilio', 'other')),

    -- ── The number ──────────────────────────────────────────────────────
    cost_usd            NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),

    -- NO DEFAULT, NOT NULL: the writer MUST decide. See the header block.
    is_estimated        BOOLEAN        NOT NULL,

    -- e.g. '2026-08-estimate-v1'. NULL only permitted for a future
    -- is_estimated = FALSE row sourced straight from a provider invoice.
    rate_card_version   VARCHAR(30),

    -- Per-component USD breakdown, so a report can show WHERE the money went
    -- without re-deriving it: {"stt": 0.0012, "llm": 0.0014, "tts": 0.06,
    --                          "telephony": 0.0085}
    cost_breakdown      JSONB          NOT NULL DEFAULT '{}',
    metadata            JSONB          NOT NULL DEFAULT '{}',

    created_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),

    -- A row claiming to be MEASURED must say nothing about a rate card being
    -- the source of truth; a row claiming to be ESTIMATED must name the card
    -- that produced it. This makes "estimate silently relabelled as measured"
    -- a constraint violation rather than a reporting bug.
    CONSTRAINT usage_metrics_estimated_needs_rate_card
        CHECK (is_estimated = FALSE OR rate_card_version IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_usage_metrics_business_created
    ON public.usage_metrics(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_call
    ON public.usage_metrics(call_id);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_branch
    ON public.usage_metrics(business_id, branch_id, created_at DESC);
-- Lets the report split metered vs estimated without a sequential scan.
CREATE INDEX IF NOT EXISTS idx_usage_metrics_estimated
    ON public.usage_metrics(business_id, is_estimated);

-- updated_at trigger (rows are re-priced when a metered figure later
-- replaces an estimate). public.set_updated_at() pre-exists in
-- database/travel_schema.sql; CREATE OR REPLACE keeps this file standalone.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_usage_metrics_updated_at ON public.usage_metrics;
CREATE TRIGGER trg_usage_metrics_updated_at
    BEFORE UPDATE ON public.usage_metrics
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- RLS — service-role-only pattern, SAME migration (law 2)
-- ============================================================
ALTER TABLE public.usage_metrics ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'usage_metrics'
          AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.usage_metrics USING (false)';
    END IF;
END $$;

REVOKE ALL ON TABLE public.usage_metrics FROM anon, authenticated;

-- ============================================================
-- VERIFICATION (run manually after apply — law 7)
-- ============================================================
-- Structure (expect is_estimated NOT NULL with NO column_default):
--   SELECT column_name, data_type, is_nullable, column_default
--     FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='usage_metrics'
--    ORDER BY ordinal_position;
-- CHECK constraints landed:
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid='public.usage_metrics'::regclass;
-- is_estimated is genuinely mandatory (this INSERT must FAIL):
--   INSERT INTO public.usage_metrics (business_id) VALUES ('<b>'::uuid);
--   -- expect: null value in column "is_estimated" violates not-null constraint
-- FINANCIAL-INTEGRITY PROBE — today this must return 0 rows. A non-zero
-- result means someone claimed a MEASURED cost without a provider
-- integration; investigate before trusting any cost report:
--   SELECT count(*) FROM public.usage_metrics WHERE is_estimated = FALSE;
-- RLS on:
--   SELECT relname, relrowsecurity FROM pg_class WHERE relname='usage_metrics';
-- Grants gone (must return 0 rows):
--   SELECT grantee, privilege_type FROM information_schema.role_table_grants
--    WHERE table_name='usage_metrics' AND grantee IN ('anon','authenticated');

-- ============================================================
-- ROLLBACK (destructive — drops all recorded usage/cost rows.
-- Nothing that pre-dates this migration is touched.)
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_usage_metrics_updated_at ON public.usage_metrics;
-- DROP TABLE IF EXISTS public.usage_metrics;
-- NOTE: public.set_updated_at() is intentionally NOT dropped — it pre-dates
-- this migration and is used by travel_leads / travel_bookings / travel_calls.
