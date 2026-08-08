-- Migration 0012 — Phase 4 T4/T5: report_schedules
--
-- Recurring analytics report delivery. One row = "send the <report_type>
-- report for <branch_id or whole business> to <recipients> over
-- <delivery_channel> at <send_time> in <timezone>".
--
-- Read by app/services/travel/report_scheduler.py, which is PULL-BASED
-- (same convention as playbook_scheduler.py — no APScheduler, no in-process
-- timer thread). A cron / queue worker hits POST /reports/scheduled/run-due
-- every few minutes; the scheduler decides what is due using send_time +
-- timezone + last_run_at.
--
-- Conventions followed (gogaga-migrations, the 7 laws):
--   * CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS  (idempotent)
--   * VARCHAR + CHECK, never a Postgres enum type
--   * ENABLE ROW LEVEL SECURITY + REVOKE ALL FROM anon, authenticated in the
--     SAME migration (this repo is service-role-only; FastAPI core/deps.py is
--     the gatekeeper, there are no auth.jwt() policies anywhere)
--   * DO-block guards for the policy and the trigger (Postgres has no
--     CREATE POLICY IF NOT EXISTS)
--   * -- ROLLBACK: section at the bottom
--
-- Additive only: new table, no drops, no ALTER TYPE, no data loss.
-- Rollback-able: YES (fresh table — DROP loses only rows created after this).

-- ── 1) Table ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.report_schedules (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id       UUID        NOT NULL
                                  REFERENCES public.ts_businesses(id) ON DELETE CASCADE,

    -- Which aggregation window the report covers.
    -- VARCHAR + CHECK (repo convention — see travel_leads.qualification).
    report_type       VARCHAR(20) NOT NULL
                                  CHECK (report_type IN ('daily', 'weekly', 'monthly')),

    -- NULL = whole business (all branches). Non-NULL = one branch only.
    -- ON DELETE SET NULL mirrors 0006_ai_config.sql: deleting a branch
    -- degrades its schedule to business-wide rather than destroying the row.
    branch_id         UUID        REFERENCES public.branches(id) ON DELETE SET NULL,

    delivery_channel  VARCHAR(20) NOT NULL
                                  CHECK (delivery_channel IN ('whatsapp', 'email')),

    -- JSON array of destinations. Shape depends on delivery_channel:
    --   whatsapp → ["+919876543210", ...]   (E.164 phone numbers)
    --   email    → ["ops@gogaga.co.in", ...]
    -- Validated in the router (Pydantic), not by a CHECK — the shape is
    -- channel-dependent and a CHECK over JSONB would be brittle.
    recipients        JSONB       NOT NULL DEFAULT '[]',

    -- Local wall-clock send time, interpreted in `timezone` below.
    -- TIME (not TIMETZ): a fixed UTC offset would break across DST for any
    -- non-IST tenant. The scheduler converts now() into `timezone` and
    -- compares wall clocks.
    send_time         TIME        NOT NULL,

    -- IANA tz database name (e.g. 'Asia/Kolkata', 'Asia/Dubai').
    -- 64 chars covers every current IANA identifier with headroom.
    timezone          VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',

    is_active         BOOLEAN     NOT NULL DEFAULT true,

    -- Last successful (or dry-run) dispatch. The scheduler's de-duplication
    -- key: a schedule fires at most once per period (day / ISO week / month),
    -- evaluated in `timezone`.
    last_run_at       TIMESTAMPTZ,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 2) Indexes ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_report_schedules_business
    ON public.report_schedules(business_id);

CREATE INDEX IF NOT EXISTS idx_report_schedules_branch
    ON public.report_schedules(branch_id);

-- Hot path for the router's list endpoint (business + active + newest first).
CREATE INDEX IF NOT EXISTS idx_report_schedules_business_active
    ON public.report_schedules(business_id, is_active, created_at DESC);

-- Hot path for the scheduler's due-scan: it sweeps active schedules across
-- all businesses, so is_active leads the index.
CREATE INDEX IF NOT EXISTS idx_report_schedules_due_scan
    ON public.report_schedules(is_active, report_type, send_time);

-- ── 3) updated_at trigger ─────────────────────────────────────────────────
-- Reuses the shared public.set_updated_at() that travel_schema.sql defines
-- and 0003 already reuses. DO-block guard because Postgres has no
-- CREATE TRIGGER IF NOT EXISTS.
DO $$ BEGIN
    CREATE TRIGGER trg_report_schedules_updated_at
        BEFORE UPDATE ON public.report_schedules
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── 4) RLS — same migration as the table (law 2) ──────────────────────────
-- Service-role-only, exactly like every other travel table: RLS on, a
-- deny-all policy so nothing leaks if a grant is ever added by accident,
-- and an explicit REVOKE from the PostgREST roles.
ALTER TABLE public.report_schedules ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'report_schedules'
          AND policyname = 'service_role_only'
    ) THEN
        EXECUTE 'CREATE POLICY service_role_only ON public.report_schedules USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['report_schedules'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- Destructive only for rows created after this migration ran;
-- no pre-existing table or column is touched by this file.
-- ============================================================
-- DROP TRIGGER IF EXISTS trg_report_schedules_updated_at ON public.report_schedules;
-- DROP INDEX  IF EXISTS public.idx_report_schedules_due_scan;
-- DROP INDEX  IF EXISTS public.idx_report_schedules_business_active;
-- DROP INDEX  IF EXISTS public.idx_report_schedules_branch;
-- DROP INDEX  IF EXISTS public.idx_report_schedules_business;
-- DROP TABLE  IF EXISTS public.report_schedules;
