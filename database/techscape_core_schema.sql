-- ================================================================
-- TechScape core tenancy tables — ts_businesses, ts_users
-- ================================================================
-- NOTE: these two tables are NOT defined anywhere else in this repo.
-- techscape_schema.sql only contains comments + later ALTER/hardening
-- statements for the 13 ts_* tables — the original CREATE TABLE DDL
-- was applied directly to the hosted Supabase project (ref
-- xhrrkwojitchaaghohvr) and never committed here.
--
-- This file reconstructs ONLY the two tables required to boot
-- require_business()/auth.py and satisfy the travel_* FKs, inferred
-- directly from every `.table("ts_businesses"/"ts_users")` call in
-- api/app/services/techscape/business_service.py and
-- api/app/routers/techscape/auth.py + _deps.py. It is for LOCAL DEV
-- ONLY (`supabase start`) — it is NOT a substitute for the real
-- production schema and does not attempt to recreate the other 11
-- ts_* tables (workflows, templates, executions, billing, etc.),
-- which nothing in the GoGaga dashboard build touches.
-- ================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.ts_businesses (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     VARCHAR(255) NOT NULL,
    contact_email            VARCHAR(255) NOT NULL,
    contact_phone            VARCHAR(20),
    industry                 VARCHAR(50) DEFAULT 'travel',
    website_url              VARCHAR(500),
    timezone                 VARCHAR(50) DEFAULT 'UTC',
    status                   VARCHAR(20) DEFAULT 'active' CHECK (status IN (
        'active','suspended','cancelled'
    )),
    subscription_tier        VARCHAR(20) DEFAULT 'starter',
    max_workflows            INTEGER DEFAULT 10,
    max_monthly_messages     INTEGER DEFAULT 10000,
    monthly_messages_used    INTEGER DEFAULT 0,
    preferred_sms_provider   VARCHAR(20) DEFAULT 'wapi',
    preferred_voice_provider VARCHAR(20) DEFAULT 'twilio',
    api_key_hash             VARCHAR(255) UNIQUE,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ts_businesses_api_key_hash ON public.ts_businesses(api_key_hash);
ALTER TABLE public.ts_businesses ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER trg_ts_businesses_updated_at BEFORE UPDATE ON public.ts_businesses
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS public.ts_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    role            VARCHAR(20) DEFAULT 'admin' CHECK (role IN (
        'admin','manager','user','viewer'
    )),
    status          VARCHAR(20) DEFAULT 'active' CHECK (status IN (
        'active','disabled'
    )),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email)
);
CREATE INDEX IF NOT EXISTS idx_ts_users_business ON public.ts_users(business_id);
ALTER TABLE public.ts_users ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER trg_ts_users_updated_at BEFORE UPDATE ON public.ts_users
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ts_business_contacts — travel_customer_profiles.contact_id FKs to this.
-- Fields inferred from api/app/services/techscape/contact_service.py
-- (list/get/upsert/update/delete) — name/email/phone/tags/metadata/consent flags.
CREATE TABLE IF NOT EXISTS public.ts_business_contacts (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id        UUID NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,
    name               VARCHAR(255),
    email              VARCHAR(255),
    phone              VARCHAR(20),
    do_not_contact     BOOLEAN DEFAULT FALSE,
    consent_email      BOOLEAN DEFAULT TRUE,
    consent_sms        BOOLEAN DEFAULT TRUE,
    consent_whatsapp   BOOLEAN DEFAULT TRUE,
    consent_voice      BOOLEAN DEFAULT TRUE,
    tags               JSONB DEFAULT '[]',
    metadata           JSONB DEFAULT '{}',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, email)
);
CREATE INDEX IF NOT EXISTS idx_ts_business_contacts_business ON public.ts_business_contacts(business_id);
ALTER TABLE public.ts_business_contacts ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER trg_ts_business_contacts_updated_at BEFORE UPDATE ON public.ts_business_contacts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Lock down anon/auth — only the service-role key (used by FastAPI) accesses these.
REVOKE ALL ON TABLE public.ts_businesses FROM anon, authenticated;
REVOKE ALL ON TABLE public.ts_users      FROM anon, authenticated;
REVOKE ALL ON TABLE public.ts_business_contacts FROM anon, authenticated;
