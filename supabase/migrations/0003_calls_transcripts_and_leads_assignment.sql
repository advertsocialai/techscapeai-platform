-- Migration: travel_calls + travel_transcripts tables, travel_leads
-- assignment/telephony columns (phone, assigned_agent, language, embedding)
-- Phase: 2 (T1) | Rollback-able: YES (see ROLLBACK section — table drops
-- are destructive, ts_users/travel_leads column additions are not)
--
-- Additive only. Column specs per gogaga-backend/references/schema.md's
-- P2 plan. business_id is carried directly on travel_calls (not only via
-- lead_id join) to match this repo's "everything scopes by business_id"
-- convention (same pattern as travel_playbook_runs).

-- 1) travel_leads: telephony + assignment columns
ALTER TABLE public.travel_leads ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_travel_leads_phone ON public.travel_leads(phone);

ALTER TABLE public.travel_leads
    ADD COLUMN IF NOT EXISTS assigned_agent UUID REFERENCES public.ts_users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_travel_leads_assigned_agent ON public.travel_leads(assigned_agent);

ALTER TABLE public.travel_leads ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en';

ALTER TABLE public.travel_leads ADD COLUMN IF NOT EXISTS embedding vector(1536);
-- Index deferred until row count justifies it (>10k) — see gogaga-migrations.

-- 2) travel_calls
CREATE TABLE IF NOT EXISTS public.travel_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    lead_id         UUID REFERENCES public.travel_leads(id) ON DELETE SET NULL,
    provider_sid    VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'failed')),
    mode            VARCHAR(20) NOT NULL DEFAULT 'ai'
                    CHECK (mode IN ('ai', 'agent', 'conference')),
    duration_sec    INTEGER,
    recording_url   TEXT,
    sentiment_score NUMERIC(4, 3),
    stt_engine      VARCHAR(20),
    language        VARCHAR(10) DEFAULT 'en',
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_travel_calls_business ON public.travel_calls(business_id);
CREATE INDEX IF NOT EXISTS idx_travel_calls_lead     ON public.travel_calls(lead_id);
CREATE INDEX IF NOT EXISTS idx_travel_calls_provider_sid ON public.travel_calls(provider_sid);

DO $$ BEGIN
  CREATE TRIGGER trg_travel_calls_updated_at
    BEFORE UPDATE ON public.travel_calls
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE public.travel_calls ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.travel_calls FROM anon, authenticated;

-- 3) travel_transcripts (append-only — no updated_at trigger)
CREATE TABLE IF NOT EXISTS public.travel_transcripts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id          UUID NOT NULL REFERENCES public.travel_calls(id) ON DELETE CASCADE,
    speaker          VARCHAR(20) NOT NULL CHECK (speaker IN ('ai', 'customer', 'agent')),
    text_original    TEXT NOT NULL,
    text_translated  TEXT,
    timestamp_ms     BIGINT NOT NULL,
    sentiment        JSONB DEFAULT '{}',
    embedding        vector(1536),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_travel_transcripts_call ON public.travel_transcripts(call_id);

ALTER TABLE public.travel_transcripts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.travel_transcripts FROM anon, authenticated;

-- ============================================================
-- ROLLBACK (table drops are destructive; column drops on
-- travel_leads lose no other data — those columns are new)
-- ============================================================
-- DROP TABLE IF EXISTS public.travel_transcripts;
-- DROP TABLE IF EXISTS public.travel_calls;
-- ALTER TABLE public.travel_leads DROP COLUMN IF EXISTS embedding;
-- ALTER TABLE public.travel_leads DROP COLUMN IF EXISTS language;
-- DROP INDEX IF EXISTS idx_travel_leads_assigned_agent;
-- ALTER TABLE public.travel_leads DROP COLUMN IF EXISTS assigned_agent;
-- DROP INDEX IF EXISTS idx_travel_leads_phone;
-- ALTER TABLE public.travel_leads DROP COLUMN IF EXISTS phone;
