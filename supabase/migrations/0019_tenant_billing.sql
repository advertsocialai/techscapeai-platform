-- Migration 0019 — Phase 5 P3: tenant billing accounts + usage invoices
-- Phase: 5 | Rollback-able: YES (new tables only)
--
-- SCOPE, STATED UP FRONT
-- ----------------------
-- This is BILLING SCAFFOLDING ONLY. It records what a tenant owes and tracks
-- an invoice through draft -> sent -> paid via explicit manual transitions.
-- It does NOT charge anyone, and it deliberately contains no gateway
-- customer/mandate/token columns, because wiring real collection is a
-- permanently human-gated action (BLOCKERS.md B-P5-04) rather than something
-- a future task should be able to switch on by filling in a column.
--
-- FINANCIAL-INTEGRITY RULES ENCODED IN THE SCHEMA (not left to callers)
--   * Money is NUMERIC, never float. Currency is stored per row.
--   * `is_estimated` is NOT NULL with NO DEFAULT on usage_invoices, so every
--     writer must state explicitly whether the figure was metered or modelled.
--     Phase 2B never ran, so today every line is estimated (B-P4-04) — the
--     column exists so that stops being invisible the moment it changes.
--   * `rate_card_version` is required whenever is_estimated is true, so an
--     old invoice stays interpretable after a re-price. An estimate whose
--     assumptions cannot be reconstructed is not auditable.
--   * A sent or paid invoice is IMMUTABLE in its financial fields, enforced by
--     a trigger rather than convention (see below). Editing an already-sent
--     invoice's total silently restates what a customer was told they owe.
--   * `period_start`/`period_end` are half-open [start, end) with a CHECK, so
--     consecutive periods cannot double-count a usage row at the boundary.
--
-- Repo conventions: VARCHAR + CHECK (never Postgres enum types), RLS +
-- REVOKE from anon/authenticated in the SAME migration, DO-block policy
-- guards, IF NOT EXISTS throughout, ROLLBACK section at the bottom.
-- Additive only.

-- ── 1) One billing account per tenant ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenant_billing_accounts (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id       UUID         NOT NULL UNIQUE
                                   REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- Legal entity the invoice is addressed to (may differ from the trading name).
    billing_name      VARCHAR(255) NOT NULL,
    billing_email     VARCHAR(255),

    -- India-specific: GSTIN is 15 chars. Nullable — an intl tenant has none.
    gstin             VARCHAR(15),

    -- Invoice currency for this tenant. Drives which FX snapshot (migration
    -- 0015) is used to roll a multi-currency period up for reporting.
    currency          CHAR(3)      NOT NULL DEFAULT 'INR',

    plan              VARCHAR(30)  NOT NULL DEFAULT 'usage_only'
                                   CHECK (plan IN ('usage_only', 'flat', 'flat_plus_usage')),
    -- Monthly platform fee for flat/flat_plus_usage plans; 0 for usage_only.
    monthly_fee       NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (monthly_fee >= 0),

    is_active         BOOLEAN      NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT tenant_billing_flat_fee_consistent
        CHECK (plan = 'usage_only' OR monthly_fee > 0)
);

CREATE INDEX IF NOT EXISTS idx_tenant_billing_accounts_active
    ON public.tenant_billing_accounts(is_active);

-- ── 2) Usage invoices ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.usage_invoices (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id       UUID         NOT NULL
                                   REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    billing_account_id UUID        NOT NULL
                                   REFERENCES public.tenant_billing_accounts(id) ON DELETE RESTRICT,

    -- Half-open interval [period_start, period_end). The CHECK is what stops
    -- two consecutive invoices both claiming a usage row on the boundary.
    period_start      TIMESTAMPTZ  NOT NULL,
    period_end        TIMESTAMPTZ  NOT NULL,
    CONSTRAINT usage_invoices_period_ordered CHECK (period_end > period_start),

    currency          CHAR(3)      NOT NULL DEFAULT 'INR',
    subtotal          NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (subtotal   >= 0),
    tax_amount        NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    total             NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total      >= 0),

    -- Per-line detail: [{kind, quantity, unit, unit_rate, amount, is_estimated}]
    line_items        JSONB        NOT NULL DEFAULT '[]',

    -- TRUE when ANY line is modelled rather than metered. Deliberately no
    -- DEFAULT: the writer must decide, so "estimated" can never be the result
    -- of someone forgetting to pass it.
    is_estimated      BOOLEAN      NOT NULL,
    rate_card_version VARCHAR(50),
    CONSTRAINT usage_invoices_estimate_needs_rate_card
        CHECK (is_estimated = FALSE OR rate_card_version IS NOT NULL),

    status            VARCHAR(20)  NOT NULL DEFAULT 'draft'
                                   CHECK (status IN ('draft', 'sent', 'paid', 'void')),
    sent_at           TIMESTAMPTZ,
    paid_at           TIMESTAMPTZ,
    -- Free-text reason, required to void — a voided invoice with no
    -- explanation is an audit gap.
    void_reason       TEXT,
    CONSTRAINT usage_invoices_void_needs_reason
        CHECK (status <> 'void' OR void_reason IS NOT NULL),

    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- One invoice per tenant per period. Makes generation idempotent: a
    -- re-run cannot double-bill.
    CONSTRAINT usage_invoices_unique_period UNIQUE (business_id, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_usage_invoices_business_period
    ON public.usage_invoices(business_id, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_usage_invoices_status
    ON public.usage_invoices(status);

-- ── 3) Immutability of issued invoices, enforced by trigger ───────────────
-- A CHECK constraint cannot see the OLD row, so this has to be a trigger.
-- Once an invoice leaves 'draft' its financial fields are frozen; only the
-- status timestamps and a void may change. Without this, a later bug or a
-- careless PATCH could restate what a customer was already told they owe —
-- the kind of silent change that is very hard to detect after the fact.
CREATE OR REPLACE FUNCTION public.freeze_issued_invoice()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('sent', 'paid') THEN
        IF NEW.subtotal   IS DISTINCT FROM OLD.subtotal
        OR NEW.tax_amount IS DISTINCT FROM OLD.tax_amount
        OR NEW.total      IS DISTINCT FROM OLD.total
        OR NEW.currency   IS DISTINCT FROM OLD.currency
        OR NEW.line_items IS DISTINCT FROM OLD.line_items
        OR NEW.period_start IS DISTINCT FROM OLD.period_start
        OR NEW.period_end   IS DISTINCT FROM OLD.period_end THEN
            RAISE EXCEPTION
                'invoice % is % — financial fields are immutable once issued; void it and raise a new one',
                OLD.id, OLD.status;
        END IF;
    END IF;
    -- Forward-only status: nothing may return to draft, and paid is terminal
    -- except for an explicit void.
    IF OLD.status = 'paid' AND NEW.status NOT IN ('paid', 'void') THEN
        RAISE EXCEPTION 'invoice % is paid — cannot move back to %', OLD.id, NEW.status;
    END IF;
    IF OLD.status <> 'draft' AND NEW.status = 'draft' THEN
        RAISE EXCEPTION 'invoice % cannot return to draft from %', OLD.id, OLD.status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    CREATE TRIGGER trg_usage_invoices_freeze
        BEFORE UPDATE ON public.usage_invoices
        FOR EACH ROW EXECUTE FUNCTION public.freeze_issued_invoice();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_tenant_billing_accounts_updated_at
        BEFORE UPDATE ON public.tenant_billing_accounts
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_usage_invoices_updated_at
        BEFORE UPDATE ON public.usage_invoices
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── 4) RLS — service-role-only, same migration as the tables (law 2) ──────
ALTER TABLE public.tenant_billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_invoices          ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['tenant_billing_accounts', 'usage_invoices'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public' AND tablename = t AND policyname = 'service_role_only'
        ) THEN
            EXECUTE format('CREATE POLICY service_role_only ON public.%I USING (false)', t);
        END IF;
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- VERIFICATION (run manually after apply)
-- ============================================================
--   -- Immutability must actually bite:
--   UPDATE public.usage_invoices SET total = 1 WHERE status = 'sent';
--   -- expect: ERROR ... financial fields are immutable once issued
--   -- Forward-only status:
--   UPDATE public.usage_invoices SET status = 'draft' WHERE status = 'sent';
--   -- expect: ERROR ... cannot return to draft
--   -- No double-billing a period:
--   INSERT ... same (business_id, period_start, period_end)  -- expect unique violation
--   -- RLS blocks the PostgREST roles:
--   SET ROLE anon; SELECT * FROM public.usage_invoices;      -- expect permission denied

-- ============================================================
-- ROLLBACK
-- Destructive: drops billing history. Export before running.
--   COPY (SELECT * FROM public.usage_invoices) TO '/tmp/usage_invoices.csv' CSV HEADER;
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_usage_invoices_updated_at ON public.usage_invoices;
-- DROP TRIGGER IF EXISTS trg_usage_invoices_freeze ON public.usage_invoices;
-- DROP TRIGGER IF EXISTS trg_tenant_billing_accounts_updated_at ON public.tenant_billing_accounts;
-- DROP FUNCTION IF EXISTS public.freeze_issued_invoice();
-- DROP INDEX IF EXISTS public.idx_usage_invoices_status;
-- DROP INDEX IF EXISTS public.idx_usage_invoices_business_period;
-- DROP TABLE IF EXISTS public.usage_invoices;
-- DROP INDEX IF EXISTS public.idx_tenant_billing_accounts_active;
-- DROP TABLE IF EXISTS public.tenant_billing_accounts;
