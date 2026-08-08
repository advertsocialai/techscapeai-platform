-- Migration 0011 — Phase 4 T3: whatsapp_outbox
--
-- Durable audit log for every WhatsApp message this platform intends to send.
--
-- Two roles, one table:
--   1. STUB MODE (no Meta credentials configured) — the provider writes the
--      fully-formed, provider-shaped payload here with status='stubbed' and
--      NEVER calls the network. The row is the deliverable: it is exactly what
--      would have gone on the wire.
--   2. LIVE MODE (meta_cloud provider) — the row is written 'queued' BEFORE the
--      HTTP call and moved to 'sent' (+ provider_message_id, sent_at) or
--      'failed' (+ error) after. So a crash mid-send leaves an inspectable
--      'queued' row rather than a silent loss.
--
-- Repo conventions honoured: VARCHAR + CHECK constraints (never Postgres enum
-- types), service-role-only RLS (REVOKE from anon/authenticated in the SAME
-- migration), DO-block policy guard, IF NOT EXISTS everywhere.
--
-- Additive only — new table, no destructive ops, nothing existing is touched.

CREATE TABLE IF NOT EXISTS public.whatsapp_outbox (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- tenant scope. Every read path filters on this; the API never exposes
    -- a row outside the caller's business (out-of-scope -> 404, not 403).
    business_id         UUID         NOT NULL
                                     REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- E.164 recipient, normalised by services/whatsapp/base.py:normalize_msisdn
    -- (bare 10-digit Indian mobiles are promoted to +91 — this product is
    -- India-focused). 20 chars is E.164's max (+ plus 15 digits) with headroom.
    to_number           VARCHAR(20)  NOT NULL,

    -- 'template'  = pre-approved Meta message template. The ONLY thing that may
    --               be sent outside the 24-hour customer-service window.
    -- 'freeform'  = plain session text. Legal ONLY inside the 24-hour window,
    --               which opens on the customer's last inbound message.
    message_type        VARCHAR(20)  NOT NULL
                                     CHECK (message_type IN ('template', 'freeform')),

    -- Meta-approved template name; NULL for freeform (enforced below).
    template_name       VARCHAR(255),

    -- BCP-47-ish template language code, e.g. 'en', 'en_US', 'hi', 'te'.
    language            VARCHAR(10)  NOT NULL DEFAULT 'en',

    -- The exact provider-shaped request body (Meta Cloud API
    -- POST /{phone_number_id}/messages JSON). Stored verbatim so a stubbed row
    -- can be diffed byte-for-byte against what live mode would transmit.
    payload             JSONB        NOT NULL DEFAULT '{}'::jsonb,

    -- 'queued'  = row written, provider call not yet completed (live mode)
    -- 'sent'    = provider accepted it (provider_message_id populated)
    -- 'failed'  = provider rejected/errored (error populated)
    -- 'stubbed' = no credentials; deliberately never transmitted
    status              VARCHAR(20)  NOT NULL DEFAULT 'queued'
                                     CHECK (status IN ('queued', 'sent', 'failed', 'stubbed')),

    -- which implementation of WhatsAppProvider produced this row:
    -- 'stub' | 'meta_cloud' | (future) 'gupshup' | 'interakt'
    provider            VARCHAR(20)  NOT NULL DEFAULT 'stub',

    -- Meta's wamid.* on success; the synthetic 'stub-wa-*' id in stub mode.
    provider_message_id VARCHAR(255),

    -- provider error text on status='failed'; NULL otherwise.
    error               TEXT,

    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    sent_at             TIMESTAMPTZ,

    -- A template message is meaningless without its approved template name.
    CONSTRAINT whatsapp_outbox_template_needs_name
        CHECK (message_type <> 'template' OR template_name IS NOT NULL),

    -- Freeform messages never carry a template name.
    CONSTRAINT whatsapp_outbox_freeform_has_no_template
        CHECK (message_type <> 'freeform' OR template_name IS NULL)
);

-- Primary read path: GET /whatsapp/outbox — business-scoped, newest first, paginated.
CREATE INDEX IF NOT EXISTS idx_whatsapp_outbox_business_created
    ON public.whatsapp_outbox (business_id, created_at DESC);

-- Retry/monitoring sweeps: "anything stuck in 'queued' or 'failed'".
CREATE INDEX IF NOT EXISTS idx_whatsapp_outbox_status
    ON public.whatsapp_outbox (status);

-- Per-recipient history — also the fallback source for reconstructing the
-- 24-hour session window during incident review.
CREATE INDEX IF NOT EXISTS idx_whatsapp_outbox_to_number
    ON public.whatsapp_outbox (business_id, to_number, created_at DESC);

-- ── RLS — service-role-only, matching every other travel table ──────────────
-- Authorization lives in FastAPI (app/core/deps.py:require_role), NOT in
-- policies. The permissive-false policy + REVOKE means anon/authenticated
-- PostgREST clients can never touch this table directly.
ALTER TABLE public.whatsapp_outbox ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'whatsapp_outbox' AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.whatsapp_outbox USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['whatsapp_outbox'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Destructive: drops the send audit trail. Export first if any rows exist:
--   COPY (SELECT * FROM public.whatsapp_outbox) TO '/tmp/whatsapp_outbox.csv' CSV HEADER;
--
-- DROP INDEX IF EXISTS public.idx_whatsapp_outbox_to_number;
-- DROP INDEX IF EXISTS public.idx_whatsapp_outbox_status;
-- DROP INDEX IF EXISTS public.idx_whatsapp_outbox_business_created;
-- DROP POLICY IF EXISTS service_role_only ON public.whatsapp_outbox;
-- DROP TABLE IF EXISTS public.whatsapp_outbox;
