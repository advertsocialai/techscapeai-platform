-- Migration 0007 — Phase 3 T7: business_phone_numbers (multi-tenant phone routing)
-- Kills the PLIVO_BUSINESS_ID single-tenant debt.
-- One row per DID; webhook handler resolves tenant from the "To" field.
-- Additive only (new table). No destructive ops.

CREATE TABLE IF NOT EXISTS public.business_phone_numbers (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) UNIQUE NOT NULL,  -- E.164, e.g. +919876543210
    business_id  UUID        NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    is_active    BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bpn_phone_number
    ON public.business_phone_numbers(phone_number) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_bpn_business_id
    ON public.business_phone_numbers(business_id);

-- RLS
ALTER TABLE public.business_phone_numbers ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'business_phone_numbers' AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.business_phone_numbers USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['business_phone_numbers'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP TABLE IF EXISTS public.business_phone_numbers;
