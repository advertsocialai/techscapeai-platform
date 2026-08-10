-- Migration 0023 — Phase 10 DEBT-10: WhatsApp session state (multi-worker persistence)
--
-- Track the last inbound message timestamp per (business_id, recipient), so the
-- 24-hour session window check is consistent across uvicorn workers. Previously
-- stored in an in-process dict (_INBOUND_SEEN) — now persistent in Postgres.
--
-- Additive only — new table, no destructive ops, nothing existing is touched.

CREATE TABLE IF NOT EXISTS public.whatsapp_sessions (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- tenant scope. Every lookup filters on this.
    business_id         UUID         NOT NULL
                                     REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- E.164 recipient, normalised by services/whatsapp/base.py:normalize_msisdn
    -- (bare 10-digit Indian mobiles are promoted to +91). 20 chars is E.164's max
    -- (+ plus 15 digits) with headroom.
    to_number           VARCHAR(20)  NOT NULL,

    -- The timestamp of the most recent inbound message from this recipient.
    -- This is what opens the 24-hour session window for free-form sends.
    last_inbound_at     TIMESTAMPTZ  NOT NULL,

    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- (business_id, to_number) is unique — one session per business-recipient pair
    CONSTRAINT whatsapp_sessions_unique_business_recipient
        UNIQUE (business_id, to_number)
);

-- Lookup by (business_id, to_number) — the hot path in session_window_open()
CREATE INDEX IF NOT EXISTS idx_whatsapp_sessions_business_to
    ON public.whatsapp_sessions (business_id, to_number);

-- ── RLS — service-role-only, matching every other WhatsApp table ──────────────
ALTER TABLE public.whatsapp_sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'whatsapp_sessions' AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.whatsapp_sessions USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['whatsapp_sessions'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Destructive: drops the session registry.
--
-- DROP INDEX IF EXISTS public.idx_whatsapp_sessions_business_to;
-- DROP POLICY IF EXISTS service_role_only ON public.whatsapp_sessions;
-- DROP TABLE IF EXISTS public.whatsapp_sessions;
