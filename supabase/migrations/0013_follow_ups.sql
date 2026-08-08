-- Migration 0013 — Phase 4 T6: follow-up ladder (Day 1 / Day 3 / Day 7)
-- Phase: 4 | Rollback-able: YES (both tables are new — DROP loses only
--                                rows created after this migration)
--
-- Two tables:
--   follow_up_rules — the LADDER CONFIG. Business-wide (branch_id NULL) or
--                     branch-scoped. Says which ladder day maps to which
--                     follow-up type + channel, and (optionally) overrides
--                     the default day→hours offset.
--   follow_ups      — the SCHEDULED ROWS. Exactly one per (lead, ladder_day),
--                     created when a lead is created.
--
-- CONVENTIONS HONOURED
--   * VARCHAR + CHECK constraints — this repo NEVER uses Postgres enum types
--     (matches travel_leads.qualification / travel_calls.status style).
--   * Service-role-only RLS: ENABLE ROW LEVEL SECURITY + USING(false) policy
--     + REVOKE ALL FROM anon, authenticated — in THIS migration.
--     FastAPI (app/core/deps.py require_role) is the only gatekeeper.
--   * Additive only. Nothing existing is renamed, retyped or dropped.
--
-- STATUS SEMANTICS (load-bearing — see services/travel/followup_service.py)
--   'due'         → scheduled, not yet actioned.
--   'overdue'     → DERIVED at read time from (status='due' AND due_at<=now()).
--                   The value is ALSO in the CHECK set so the optional
--                   sweep_overdue() job may persist it, but the API's
--                   authoritative answer is computed, never trusted from the
--                   column. Time passing must never require a write.
--   'in_progress' → an agent has picked it up.
--   'done'        → actioned, terminal.

-- ============================================================
-- 1) follow_up_rules — the ladder configuration
-- ============================================================
CREATE TABLE IF NOT EXISTS public.follow_up_rules (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id       UUID        NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- NULL = business-wide default ladder. Non-NULL = this branch overrides
    -- the business-wide rule for the same ladder_day. A rule is a pure child
    -- of its branch, so CASCADE (not SET NULL — that would silently promote a
    -- branch override into a business-wide default and collide on the
    -- uniqueness rule below).
    branch_id         UUID        REFERENCES public.branches(id) ON DELETE CASCADE,

    -- The ladder is fixed at Day 1 / Day 3 / Day 7 by product spec.
    ladder_day        INTEGER     NOT NULL CHECK (ladder_day IN (1, 3, 7)),

    type              VARCHAR(20) NOT NULL CHECK (type IN
                        ('nudge', 'summary', 'personal_call', 'price_alert')),

    channel           VARCHAR(20) NOT NULL DEFAULT 'whatsapp' CHECK (channel IN
                        ('whatsapp', 'sms', 'email', 'call', 'in_app')),

    -- NULL => due_at offset is derived as ladder_day * 24 hours (the default).
    -- Set it to fine-tune (e.g. 20 so the Day-1 nudge lands next morning).
    due_offset_hours  INTEGER     CHECK (due_offset_hours IS NULL OR due_offset_hours >= 0),

    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One rule per ladder day per scope. Two PARTIAL unique indexes rather than a
-- plain UNIQUE(business_id, branch_id, ladder_day): in Postgres NULLs are
-- distinct under UNIQUE, so a plain constraint would let a business
-- accumulate unlimited duplicate business-wide (branch_id IS NULL) rules.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_follow_up_rules_business_scope
    ON public.follow_up_rules(business_id, ladder_day)
    WHERE branch_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uniq_follow_up_rules_branch_scope
    ON public.follow_up_rules(business_id, branch_id, ladder_day)
    WHERE branch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_follow_up_rules_business
    ON public.follow_up_rules(business_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_rules_branch
    ON public.follow_up_rules(branch_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_rules_active
    ON public.follow_up_rules(business_id, is_active);

-- ============================================================
-- 2) follow_ups — the scheduled ladder rows
-- ============================================================
CREATE TABLE IF NOT EXISTS public.follow_ups (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID        NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- A follow-up has no meaning without its lead — pure child row, CASCADE
    -- (same reasoning as travel_transcripts → travel_calls in 0003).
    lead_id       UUID        NOT NULL REFERENCES public.travel_leads(id) ON DELETE CASCADE,

    -- Denormalised from the lead's branch at schedule time so the list
    -- endpoint can filter by branch without a join.
    branch_id     UUID        REFERENCES public.branches(id) ON DELETE SET NULL,

    -- Which rule produced this row (audit trail for "why is this due now?").
    -- SET NULL: deleting a rule must never destroy already-scheduled work.
    rule_id       UUID        REFERENCES public.follow_up_rules(id) ON DELETE SET NULL,

    ladder_day    INTEGER     NOT NULL CHECK (ladder_day IN (1, 3, 7)),

    type          VARCHAR(20) NOT NULL CHECK (type IN
                    ('nudge', 'summary', 'personal_call', 'price_alert')),

    due_at        TIMESTAMPTZ NOT NULL,

    status        VARCHAR(20) NOT NULL DEFAULT 'due' CHECK (status IN
                    ('due', 'overdue', 'in_progress', 'done')),

    assigned_to   UUID        REFERENCES public.ts_users(id) ON DELETE SET NULL,

    channel       VARCHAR(20) NOT NULL DEFAULT 'whatsapp' CHECK (channel IN
                    ('whatsapp', 'sms', 'email', 'call', 'in_app')),

    completed_at  TIMESTAMPTZ,
    metadata      JSONB       NOT NULL DEFAULT '{}',

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent auto-scheduling: re-running schedule_for_lead() for the same
-- lead can never produce a 4th/5th row. This is what makes the acceptance
-- check ("exactly 3 rows") hold even if the lead-creation hook fires twice.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_follow_ups_lead_day
    ON public.follow_ups(lead_id, ladder_day);

CREATE INDEX IF NOT EXISTS idx_follow_ups_business
    ON public.follow_ups(business_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_lead
    ON public.follow_ups(lead_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_branch
    ON public.follow_ups(branch_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_assigned_to
    ON public.follow_ups(assigned_to);
-- Hot path for GET /follow-ups?status= and for the overdue derivation.
CREATE INDEX IF NOT EXISTS idx_follow_ups_status_due
    ON public.follow_ups(business_id, status, due_at);

-- ============================================================
-- 3) updated_at triggers (both tables are user-editable)
-- ============================================================
-- public.set_updated_at() already exists (database/travel_schema.sql).
-- CREATE OR REPLACE it here so this migration is safe standalone.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_follow_up_rules_updated_at ON public.follow_up_rules;
CREATE TRIGGER trg_follow_up_rules_updated_at
    BEFORE UPDATE ON public.follow_up_rules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_follow_ups_updated_at ON public.follow_ups;
CREATE TRIGGER trg_follow_ups_updated_at
    BEFORE UPDATE ON public.follow_ups
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- 4) RLS — service-role-only pattern, SAME migration (law 2)
-- ============================================================
ALTER TABLE public.follow_up_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.follow_ups      ENABLE ROW LEVEL SECURITY;

-- Postgres has no CREATE POLICY IF NOT EXISTS — DO-block guard (law 6).
-- USING (false) => zero direct client access; only the service-role key
-- (which bypasses RLS) reaches these tables, via FastAPI.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['follow_up_rules', 'follow_ups'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public' AND tablename = t
              AND policyname = 'service_role_only'
        ) THEN
            EXECUTE format(
                'CREATE POLICY service_role_only ON public.%I USING (false)', t);
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['follow_up_rules', 'follow_ups'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- 5) VERIFICATION (run manually after apply — law 7)
-- ============================================================
-- Structure:
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--    WHERE table_schema='public' AND table_name IN ('follow_ups','follow_up_rules')
--    ORDER BY table_name, ordinal_position;
-- CHECK constraints landed (expect ladder_day / type / status / channel):
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid IN ('public.follow_ups'::regclass,
--                       'public.follow_up_rules'::regclass);
-- No Postgres enum types were created (must return 0 rows):
--   SELECT typname FROM pg_type WHERE typtype='e'
--    AND typname LIKE '%follow%';
-- RLS on:
--   SELECT relname, relrowsecurity FROM pg_class
--    WHERE relname IN ('follow_ups','follow_up_rules');
-- Policies:
--   SELECT tablename, policyname, qual FROM pg_policies
--    WHERE tablename IN ('follow_ups','follow_up_rules');
-- Grants gone (must return 0 rows):
--   SELECT grantee, privilege_type FROM information_schema.role_table_grants
--    WHERE table_name IN ('follow_ups','follow_up_rules')
--      AND grantee IN ('anon','authenticated');
-- Acceptance probe — exactly 3 rows per lead, correct offsets:
--   SELECT ladder_day, type, channel, due_at,
--          due_at - (SELECT created_at FROM public.travel_leads l
--                     WHERE l.id = f.lead_id) AS offset_from_lead
--     FROM public.follow_ups f WHERE lead_id = '<test-lead-uuid>'
--    ORDER BY ladder_day;   -- expect 3 rows: +1 day, +3 days, +7 days
-- Idempotency probe — re-running the scheduler must NOT add rows:
--   SELECT lead_id, count(*) FROM public.follow_ups GROUP BY lead_id
--    HAVING count(*) > 3;   -- expect 0 rows

-- ============================================================
-- ROLLBACK (destructive — drops both tables and every scheduled
-- follow-up. Nothing that pre-dates this migration is touched.)
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_follow_ups_updated_at ON public.follow_ups;
-- DROP TRIGGER IF EXISTS trg_follow_up_rules_updated_at ON public.follow_up_rules;
-- DROP TABLE IF EXISTS public.follow_ups;        -- must drop first (FK → rules)
-- DROP TABLE IF EXISTS public.follow_up_rules;
-- NOTE: public.set_updated_at() is intentionally NOT dropped — it pre-dates
-- this migration and is used by travel_leads / travel_bookings / travel_calls.
