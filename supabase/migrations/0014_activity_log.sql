-- Migration 0014 — Phase 4 T7: activity_log (append-only audit trail)
-- Phase: 4 | Rollback-able: YES (new table — DROP loses only audit rows
--                                created after this migration)
--
-- One row per meaningful state change anywhere in the product: takeover
-- transitions, AI-config edits, payment-link creation, WhatsApp sends,
-- package CRUD. Written through ONE helper —
-- app/services/travel/activity_log.py record() — which swallows every
-- exception so that adding audit logging can NEVER change the behaviour
-- (or the status code) of the endpoint it is wired into.
--
-- INSERT-ONLY ENFORCEMENT — how it actually works here, stated honestly:
--   * anon / authenticated: REVOKE ALL below => no access at all, of any
--     verb. RLS is on with a USING(false) policy on top.
--   * The FastAPI service-role key bypasses RLS (that is what service-role
--     means), so the append-only guarantee for non-super roles is enforced
--     at the APPLICATION layer and is verifiable by inspection: the only
--     write path in the codebase is activity_log.record() (INSERT), and the
--     only router surface is GET /activity-log (read, manager+). There is
--     no UPDATE or DELETE code path for this table anywhere. Any future
--     super-admin purge/retention job must be added deliberately, as its
--     own reviewed migration + endpoint.
--   * There is intentionally NO updated_at column and NO updated_at trigger
--     — an audit row that can be updated is not an audit row.
--
-- CONVENTIONS: VARCHAR + CHECK (never Postgres enum types); service-role-only
-- RLS in the same migration; additive only.

CREATE TABLE IF NOT EXISTS public.activity_log (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID         NOT NULL REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- NULL = system / automated actor (webhook, scheduler, AI engine).
    -- SET NULL on user delete: the audit row must SURVIVE the user leaving.
    actor_id     UUID         REFERENCES public.ts_users(id) ON DELETE SET NULL,

    -- Verb-ish, dotted, stable, e.g. 'call.takeover.full',
    -- 'ai_config.updated', 'payment_link.created', 'package.deleted'.
    -- Deliberately NOT CHECK-constrained: the vocabulary grows every phase
    -- and a rejected audit INSERT would be worse than an unknown verb.
    action       VARCHAR(100) NOT NULL,

    -- Small, slow-moving vocabulary => CHECK is safe here and catches typos
    -- at the call site. Extend by dropping and re-adding the constraint in a
    -- new migration (never ALTER TYPE — this repo has no enum types).
    entity_type  VARCHAR(50)  NOT NULL CHECK (entity_type IN (
                    'call', 'lead', 'follow_up', 'package', 'booking',
                    'payment_link', 'ai_config', 'user', 'branch',
                    'whatsapp_message', 'report', 'business', 'other'
                 )),

    -- NULL when the action is not about one specific row (e.g. a bulk export).
    -- Deliberately NOT a foreign key: entity_id is polymorphic across a dozen
    -- tables, and an FK would make the audit row deletable-by-cascade.
    entity_id    UUID,

    branch_id    UUID         REFERENCES public.branches(id) ON DELETE SET NULL,

    metadata     JSONB        NOT NULL DEFAULT '{}',

    at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Hot path: GET /activity-log is always business-scoped, newest first.
CREATE INDEX IF NOT EXISTS idx_activity_log_business_at
    ON public.activity_log(business_id, at DESC);
-- ?actor= filter
CREATE INDEX IF NOT EXISTS idx_activity_log_actor
    ON public.activity_log(business_id, actor_id, at DESC);
-- ?entity= filter (entity_type, optionally narrowed by entity_id)
CREATE INDEX IF NOT EXISTS idx_activity_log_entity
    ON public.activity_log(business_id, entity_type, entity_id);
-- ?branch= filter
CREATE INDEX IF NOT EXISTS idx_activity_log_branch
    ON public.activity_log(business_id, branch_id, at DESC);
-- "everything that ever happened to THIS row", across businesses
CREATE INDEX IF NOT EXISTS idx_activity_log_entity_id
    ON public.activity_log(entity_id);

-- ============================================================
-- RLS — service-role-only pattern, SAME migration (law 2)
-- ============================================================
ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;

-- DO-block guard: Postgres has no CREATE POLICY IF NOT EXISTS (law 6).
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'activity_log'
          AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.activity_log USING (false)';
    END IF;
END $$;

REVOKE ALL ON TABLE public.activity_log FROM anon, authenticated;

-- ============================================================
-- VERIFICATION (run manually after apply — law 7)
-- ============================================================
-- Structure (expect NO updated_at column):
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='activity_log'
--    ORDER BY ordinal_position;
-- entity_type CHECK landed:
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid='public.activity_log'::regclass;
-- RLS on:
--   SELECT relname, relrowsecurity FROM pg_class WHERE relname='activity_log';
-- Policy:
--   SELECT policyname, cmd, qual FROM pg_policies WHERE tablename='activity_log';
-- Grants gone (must return 0 rows):
--   SELECT grantee, privilege_type FROM information_schema.role_table_grants
--    WHERE table_name='activity_log' AND grantee IN ('anon','authenticated');
-- Behaviour probe — the helper must not break its caller: run any wired
-- endpoint with the DB unreachable and assert the endpoint's status code is
-- unchanged (record() swallows, logs at WARNING, returns None).

-- ============================================================
-- ROLLBACK (destructive — drops the audit trail itself. Nothing that
-- pre-dates this migration is touched.)
-- ============================================================
-- DROP TABLE IF EXISTS public.activity_log;
