-- Migration 0005 — Phase 3: takeover state + call events + post-call summary
-- Tasks: T1 (takeover_state, mpc_uuid, travel_call_events), T5 (summary)
-- Additive only — new columns on existing table + new table.
-- Next migration number after this: 0006
--
-- ROLLBACK section at the bottom. Column adds are not destructive; table drop is.

-- ── travel_calls additions ────────────────────────────────────────────────
ALTER TABLE public.travel_calls
    ADD COLUMN IF NOT EXISTS mpc_uuid VARCHAR(255),
    ADD COLUMN IF NOT EXISTS takeover_state VARCHAR(20) DEFAULT 'ai'
        CHECK (takeover_state IN ('ai', 'monitoring', 'coaching', 'human')),
    ADD COLUMN IF NOT EXISTS summary TEXT;

-- ── travel_call_events — one row per state-machine transition / notable event ─
CREATE TABLE IF NOT EXISTS public.travel_call_events (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id      UUID        NOT NULL REFERENCES public.travel_calls(id) ON DELETE CASCADE,
    event_type   VARCHAR(50) NOT NULL,  -- takeover_monitor|takeover_barge|takeover_full|takeover_release|sentiment_update|suggestion_generated|post_call_complete
    actor_id     UUID        REFERENCES public.ts_users(id) ON DELETE SET NULL,
    payload      JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_travel_call_events_call_id
    ON public.travel_call_events(call_id);
CREATE INDEX IF NOT EXISTS idx_travel_call_events_created_at
    ON public.travel_call_events(created_at DESC);

-- RLS: service-role-only (same pattern as every other travel table)
ALTER TABLE public.travel_call_events ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'travel_call_events' AND policyname = 'service_role_only'
    ) THEN
        -- Intentionally no policy body — REVOKE from anon/authenticated below
        -- ensures no JWT-claim-based access. FastAPI service-role is the sole writer.
        EXECUTE 'CREATE POLICY service_role_only ON public.travel_call_events USING (false)';
    END IF;
END $$;

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['travel_call_events'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
    END LOOP;
END $$;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Destructive: DROP TABLE removes all event rows.
-- Column removes: ALTER TABLE travel_calls DROP COLUMN mpc_uuid / takeover_state / summary
-- (not destructive if no data; safe in dev, check prod first)
--
-- DROP TABLE IF EXISTS public.travel_call_events;
-- ALTER TABLE public.travel_calls DROP COLUMN IF EXISTS summary;
-- ALTER TABLE public.travel_calls DROP COLUMN IF EXISTS takeover_state;
-- ALTER TABLE public.travel_calls DROP COLUMN IF EXISTS mpc_uuid;
