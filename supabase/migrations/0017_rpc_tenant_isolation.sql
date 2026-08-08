-- Migration 0017 — Phase 5 P1: tenant isolation hardening for the
-- semantic-search RPCs (match_travel_wiki, match_travel_transcripts).
--
-- Phase: 5 (P1 tenant-isolation audit) | Rollback-able: YES (see ROLLBACK)
-- Additive / privilege-only. No table, column, index or row is touched.
--
-- ============================================================
-- WHAT THE AUDIT FOUND (state BEFORE this migration)
-- ============================================================
-- Both RPCs ALREADY enforce business_id inside the SQL body — this is not a
-- leak being closed, it is a verified-good invariant being pinned down:
--
--   match_travel_wiki (0004)
--     WHERE w.business_id = p_business_id
--       AND w.embedding IS NOT NULL
--       AND (p_category IS NULL OR w.category = p_category)
--
--   match_travel_transcripts (0008)
--     JOIN public.travel_calls c ON c.id = t.call_id
--     WHERE c.business_id = p_business_id
--       AND t.embedding IS NOT NULL
--       AND (p_call_id IS NULL OR t.call_id = p_call_id)
--
-- The transcripts RPC does NOT need a separate ownership check on p_call_id:
-- the join to travel_calls is already gated on the business, so a call_id
-- belonging to another tenant returns zero rows rather than that tenant's
-- transcripts. Passing p_business_id => NULL likewise returns zero rows
-- (NULL = NULL is NULL, not TRUE), so a missing argument fails closed.
--
-- ============================================================
-- WHAT THIS MIGRATION ACTUALLY CHANGES
-- ============================================================
-- The gap was NOT the WHERE clause, it was WHO MAY CALL THE FUNCTION.
--
--   * RLS is a TABLE-level mechanism. It applies to travel_wiki /
--     travel_transcripts / travel_calls, NOT to a function. There is no such
--     thing as a row-level policy on an RPC.
--   * Postgres grants EXECUTE on every new function to PUBLIC by default. Both
--     RPCs are therefore reachable by the PostgREST `anon` and `authenticated`
--     roles, which can pass ANY p_business_id they like — the FastAPI layer is
--     bypassed entirely.
--   * What saves the current deployment is only that the underlying tables have
--     RLS enabled (travel_wiki: 0004/travel_schema; travel_transcripts +
--     travel_calls: 0003, which additionally REVOKEs from anon/authenticated),
--     and these functions are SECURITY INVOKER — so the scan runs with the
--     caller's own privileges and returns nothing. That is one permissive
--     policy away from becoming a cross-tenant read.
--
-- So: function-level EXECUTE is revoked from PUBLIC/anon/authenticated and
-- granted to service_role only, and both functions are re-declared with an
-- explicit SECURITY INVOKER + a pinned search_path so a future edit cannot
-- silently turn them into SECURITY DEFINER bypasses. The bodies are byte-for-
-- byte the audited ones from 0004 and 0008 — 0004 and 0008 themselves are
-- applied migrations and are NOT edited.

-- ── match_travel_wiki (body unchanged from 0004) ────────────────────────────
CREATE OR REPLACE FUNCTION public.match_travel_wiki(
    p_business_id uuid,
    p_query_embedding vector(384),
    p_match_count int DEFAULT 8,
    p_category varchar DEFAULT NULL
)
RETURNS TABLE (
    id uuid, business_id uuid, category varchar, title varchar, content text,
    metadata jsonb, tags jsonb, source varchar, created_at timestamptz,
    updated_at timestamptz, similarity float
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_catalog
AS $$
    SELECT
        w.id, w.business_id, w.category, w.title, w.content,
        w.metadata, w.tags, w.source, w.created_at, w.updated_at,
        1 - (w.embedding <=> p_query_embedding) AS similarity
    FROM public.travel_wiki w
    WHERE w.business_id = p_business_id
      AND w.embedding IS NOT NULL
      AND (p_category IS NULL OR w.category = p_category)
    ORDER BY w.embedding <=> p_query_embedding
    LIMIT p_match_count;
$$;

-- ── match_travel_transcripts (body unchanged from 0008) ─────────────────────
CREATE OR REPLACE FUNCTION public.match_travel_transcripts(
    p_business_id    uuid,
    p_query_embedding vector(384),
    p_match_count    int DEFAULT 8,
    p_call_id        uuid DEFAULT NULL
)
RETURNS TABLE (
    id              uuid,
    call_id         uuid,
    speaker         varchar,
    text_original   text,
    text_translated text,
    timestamp_ms    bigint,
    sentiment       jsonb,
    created_at      timestamptz,
    similarity      float
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_catalog
AS $$
    SELECT
        t.id, t.call_id, t.speaker, t.text_original, t.text_translated,
        t.timestamp_ms, t.sentiment, t.created_at,
        1 - (t.embedding <=> p_query_embedding) AS similarity
    FROM public.travel_transcripts t
    JOIN public.travel_calls c ON c.id = t.call_id
    WHERE c.business_id = p_business_id
      AND t.embedding IS NOT NULL
      AND (p_call_id IS NULL OR t.call_id = p_call_id)
    ORDER BY t.embedding <=> p_query_embedding
    LIMIT p_match_count;
$$;

-- ── Function-level privileges (the actual fix) ──────────────────────────────
-- CREATE OR REPLACE does not reset an existing function's ACL, so these run
-- unconditionally and are idempotent.
REVOKE ALL ON FUNCTION public.match_travel_wiki(uuid, vector(384), int, varchar)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.match_travel_transcripts(uuid, vector(384), int, uuid)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.match_travel_wiki(uuid, vector(384), int, varchar)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.match_travel_transcripts(uuid, vector(384), int, uuid)
    TO service_role;

COMMENT ON FUNCTION public.match_travel_wiki(uuid, vector(384), int, varchar) IS
    'Cosine-similarity wiki search. Tenant-scoped: WHERE w.business_id = '
    'p_business_id. SECURITY INVOKER; EXECUTE restricted to service_role '
    '(migration 0017) so the RPC cannot be called around the FastAPI layer.';
COMMENT ON FUNCTION public.match_travel_transcripts(uuid, vector(384), int, uuid) IS
    'Cosine-similarity transcript search. Tenant-scoped through the join to '
    'travel_calls: WHERE c.business_id = p_business_id, so p_call_id needs no '
    'separate ownership check. SECURITY INVOKER; EXECUTE restricted to '
    'service_role (migration 0017).';

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Restores the pre-0017 privilege state (EXECUTE to PUBLIC) and the 0004/0008
-- function definitions. Non-destructive: no data is involved either way.
--
-- GRANT EXECUTE ON FUNCTION public.match_travel_wiki(uuid, vector(384), int, varchar)
--     TO PUBLIC;
-- GRANT EXECUTE ON FUNCTION public.match_travel_transcripts(uuid, vector(384), int, uuid)
--     TO PUBLIC;
-- COMMENT ON FUNCTION public.match_travel_wiki(uuid, vector(384), int, varchar) IS NULL;
-- COMMENT ON FUNCTION public.match_travel_transcripts(uuid, vector(384), int, uuid) IS NULL;
-- -- then re-run the CREATE OR REPLACE blocks from 0004 and 0008 verbatim to
-- -- drop the explicit SECURITY INVOKER / search_path pinning.
