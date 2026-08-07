-- Migration 0006 — Phase 3 T2: travel_ai_config (configurable AI Playbook)
-- One config row per business (or per branch when branch_id is set).
-- Replaces hardcoded constants in ai_engine.py: escalation threshold, persona, question flow.
-- Additive only (new table). No destructive ops.

CREATE TABLE IF NOT EXISTS public.travel_ai_config (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id       UUID        NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    branch_id         UUID        REFERENCES public.branches(id) ON DELETE SET NULL,

    -- ordered list of questions Klara works through on a call
    -- e.g. [{"order": 1, "question": "Where would you like to travel?", "field": "destination_hint"}]
    question_flow     JSONB       NOT NULL DEFAULT '[]',

    -- languages the AI should handle; first element is default
    languages         JSONB       NOT NULL DEFAULT '["en"]',

    -- escalation rules wired into ai_engine.py
    -- budget_threshold: INR above which a human manager should be looped in
    -- intent_level: lead qualification level that triggers escalation
    escalation_rules  JSONB       NOT NULL DEFAULT '{"budget_threshold": 100000, "intent_level": "hot"}',

    -- outbound calling window (IST); mirrors compliance.py defaults
    working_hours     JSONB       NOT NULL DEFAULT '{"start": "09:00", "end": "21:00", "timezone": "Asia/Kolkata"}',

    -- voice persona — name, greeting, tone for the system prompt
    voice_persona     JSONB       NOT NULL DEFAULT '{"name": "Klara", "tone": "warm_professional", "greeting": "Hello! I''m Klara, your GoGaga travel assistant. How can I help plan your perfect trip?"}',

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- one config per scope: either business-wide (branch_id IS NULL) or per-branch
    CONSTRAINT travel_ai_config_unique_scope UNIQUE (business_id, branch_id)
);

CREATE INDEX IF NOT EXISTS idx_travel_ai_config_business_id
    ON public.travel_ai_config(business_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION public.set_updated_at_travel_ai_config()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_travel_ai_config_updated_at ON public.travel_ai_config;
CREATE TRIGGER trg_travel_ai_config_updated_at
    BEFORE UPDATE ON public.travel_ai_config
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_travel_ai_config();

-- RLS
ALTER TABLE public.travel_ai_config ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'travel_ai_config' AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.travel_ai_config USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['travel_ai_config'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_travel_ai_config_updated_at ON public.travel_ai_config;
-- DROP FUNCTION IF EXISTS public.set_updated_at_travel_ai_config();
-- DROP TABLE IF EXISTS public.travel_ai_config;
