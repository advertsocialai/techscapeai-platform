-- Migration 0010 — Phase 4 T2: payment_links
-- Phase: 4 | Rollback-able: YES (see ROLLBACK section at bottom)
--
-- Gateway-agnostic payment link ledger. One row per link handed to a customer,
-- carrying the full lifecycle created → sent → viewed → paid (terminal), with
-- `expired` as the alternate terminal state.
--
-- DESIGN NOTES
-- ------------
-- 1. "Enums" are VARCHAR + CHECK, never Postgres enum types — this matches
--    travel_leads.status/qualification/source. Changing allowed values later =
--    DROP CONSTRAINT + ADD CONSTRAINT in a new migration (safe, no ALTER TYPE).
--
-- 2. `gateway` is the backend that minted the link. 'stub' is a first-class,
--    permanently-supported value: it is what the factory selects when no
--    RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are configured, so the entire status
--    machine is exercisable end-to-end without credentials or network access.
--    'stripe' is reserved for the Phase 5 international branches.
--
-- 3. `amount` is NUMERIC(12,2) in MAJOR units of `currency` (i.e. rupees, not
--    paise). The gateway adapters convert to the provider's minor-unit integer
--    at the boundary. Never store floats for money.
--
-- 4. `currency` is CHAR(3) ISO-4217, defaulting to 'INR'. It pairs with
--    migration 0015 (branches.currency + fx_rate_snapshots): a link is always
--    settled in the currency it was created in, and any cross-currency rollup
--    must go through the STORED fx snapshot, never a live rate.
--
-- 5. `gateway_link_id` is the provider's own identifier (Razorpay `plink_...`).
--    It is UNIQUE because the webhook handler resolves rows by it alone — the
--    gateway does not know our business_id, so the lookup must be unambiguous.
--
-- Additive only: new table, no drops, no data loss.

-- ── 1) Table ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.payment_links (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id       UUID          NOT NULL
                                    REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    lead_id           UUID          REFERENCES public.travel_leads(id)    ON DELETE SET NULL,
    package_id        UUID          REFERENCES public.travel_packages(id) ON DELETE SET NULL,

    -- Money: major units of `currency`. NUMERIC, never float.
    amount            NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency          CHAR(3)       NOT NULL DEFAULT 'INR',

    gateway           VARCHAR(20)   NOT NULL DEFAULT 'stub'
                                    CHECK (gateway IN ('razorpay', 'stripe', 'stub')),

    -- Lifecycle. Forward-only: created → sent → viewed → paid.
    -- 'expired' is reachable from any non-paid state.
    status            VARCHAR(20)   NOT NULL DEFAULT 'created'
                                    CHECK (status IN ('created', 'sent', 'viewed', 'paid', 'expired')),

    expiry_at         TIMESTAMPTZ,

    -- Provider-side identifiers. UNIQUE: the webhook resolves rows by this alone.
    gateway_link_id   VARCHAR(255),
    gateway_short_url TEXT,

    created_by        UUID          REFERENCES public.ts_users(id) ON DELETE SET NULL,

    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- ── 2) Indexes ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_payment_links_business
    ON public.payment_links(business_id);
CREATE INDEX IF NOT EXISTS idx_payment_links_lead
    ON public.payment_links(lead_id);
CREATE INDEX IF NOT EXISTS idx_payment_links_status
    ON public.payment_links(business_id, status);
CREATE INDEX IF NOT EXISTS idx_payment_links_created_at
    ON public.payment_links(business_id, created_at DESC);

-- Webhook lookup path: gateway_link_id must resolve to exactly one row.
-- Partial unique index so multiple rows may sit at NULL (link not yet minted).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_payment_links_gateway_link_id
    ON public.payment_links(gateway_link_id)
    WHERE gateway_link_id IS NOT NULL;

-- ── 3) updated_at trigger ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at_payment_links()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_payment_links_updated_at ON public.payment_links;
CREATE TRIGGER trg_payment_links_updated_at
    BEFORE UPDATE ON public.payment_links
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_payment_links();

-- ── 4) RLS — SAME migration as the table (service-role-only pattern) ──────
-- This repo authorizes in FastAPI (app/core/deps.py require_role + explicit
-- business_id scoping), NOT in policies. anon/authenticated get nothing;
-- only the service-role key (which bypasses RLS) reads or writes.
ALTER TABLE public.payment_links ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'payment_links'
          AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.payment_links USING (false)';
    END IF;
END $$;

DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['payment_links'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK (destructive — drops payment_links and all link history)
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_payment_links_updated_at ON public.payment_links;
-- DROP FUNCTION IF EXISTS public.set_updated_at_payment_links();
-- DROP INDEX IF EXISTS uniq_payment_links_gateway_link_id;
-- DROP INDEX IF EXISTS idx_payment_links_created_at;
-- DROP INDEX IF EXISTS idx_payment_links_status;
-- DROP INDEX IF EXISTS idx_payment_links_lead;
-- DROP INDEX IF EXISTS idx_payment_links_business;
-- DROP TABLE IF EXISTS public.payment_links;
