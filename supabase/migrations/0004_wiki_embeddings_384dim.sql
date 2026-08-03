-- Migration: resize embedding columns to 384-dim + cosine search RPC
-- Phase: 2 (T8) | Rollback-able: YES (see ROLLBACK section)
--
-- Decision: local embedder chosen is BAAI/bge-small-en-v1.5 via fastembed
-- (ONNX, no API key, no torch — 384 dims, 67MB). No cloud embedding key
-- exists (OpenAI/Voyage/Cohere all unconfigured) and a full
-- sentence-transformers+torch install is unnecessarily heavy for this
-- phase. The pre-existing vector(1536) columns (travel_wiki, plus
-- travel_leads/travel_transcripts added in Phase 2 T1) assumed an
-- OpenAI-shaped embedding that was never actually wired in — zero rows
-- have a populated embedding anywhere (confirmed before this migration),
-- so resizing to 384 is lossless today. Deliberately noted as NOT
-- additive in the strict gogaga-migrations sense (it changes an existing
-- column's type) — flagging it per law 3 rather than treating it as
-- routine, even though nothing is actually destroyed.

ALTER TABLE public.travel_wiki        ALTER COLUMN embedding TYPE vector(384);
ALTER TABLE public.travel_leads       ALTER COLUMN embedding TYPE vector(384);
ALTER TABLE public.travel_transcripts ALTER COLUMN embedding TYPE vector(384);

-- Cosine-similarity RPC (Supabase's standard pgvector search pattern —
-- postgrest can't express `<=>` through the table-builder API, so this
-- goes through db.rpc() instead). business_id-scoped, same multi-tenancy
-- rule as every other query in this repo.
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
LANGUAGE sql STABLE
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

-- Index deferred until row count justifies it (>10k) — see gogaga-migrations.

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP FUNCTION IF EXISTS public.match_travel_wiki(uuid, vector(384), int, varchar);
-- ALTER TABLE public.travel_transcripts ALTER COLUMN embedding TYPE vector(1536);
-- ALTER TABLE public.travel_leads       ALTER COLUMN embedding TYPE vector(1536);
-- ALTER TABLE public.travel_wiki        ALTER COLUMN embedding TYPE vector(1536);
