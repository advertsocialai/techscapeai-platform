-- Migration 0008 — Phase 3 T6: match_travel_transcripts() cosine-similarity RPC
-- Mirrors match_travel_wiki() from migration 0004.
-- Requires: travel_transcripts.embedding vector(384) (set in migration 0003+0004).
-- Additive only (new function). No destructive ops.

CREATE OR REPLACE FUNCTION public.match_travel_transcripts(
    p_business_id    uuid,
    p_query_embedding vector(384),
    p_match_count    int DEFAULT 8,
    p_call_id        uuid DEFAULT NULL  -- optional: search within one call
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
LANGUAGE sql STABLE
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

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP FUNCTION IF EXISTS public.match_travel_transcripts(uuid, vector(384), int, uuid);
