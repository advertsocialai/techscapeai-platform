"""
Local text embeddings (Phase 2 T8) — BAAI/bge-small-en-v1.5 via fastembed
(ONNX runtime, no torch, no API key, 384 dims, ~67MB). Chosen because no
cloud embedding provider is configured (OpenAI/Voyage/Cohere all
unconfigured) — see migrations/0004's header for the full rationale and
the pgvector column-resize this required (1536 -> 384).

Lazy singleton: the model loads (and downloads on first use) only when
embed_text() is first called, not at import time, so routes that never
touch search stay fast to import.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_model = None  # lazy-loaded fastembed.TextEmbedding


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        logger.info("Loading embedding model BAAI/bge-small-en-v1.5 (first call, may download)...")
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _model


def embeddings_available() -> bool:
    try:
        _get_model()
        return True
    except Exception:
        logger.exception("Embedding model unavailable")
        return False


def embed_text(text: str) -> Optional[list[float]]:
    if not text or not text.strip():
        return None
    try:
        model = _get_model()
        vec = next(model.embed([text]))
        return vec.tolist()
    except Exception:
        logger.exception("embed_text failed")
        return None


def embed_transcript(transcript_id: str, text: str) -> bool:
    """Embed a transcript row and persist the vector (Phase 3 T6).
    Returns True if embedding was written, False if skipped/failed."""
    vec = embed_text(text)
    if vec is None:
        return False
    try:
        from app.database import get_supabase_admin
        db = get_supabase_admin()
        db.table("travel_transcripts").update({"embedding": vec}).eq("id", transcript_id).execute()
        return True
    except Exception:
        logger.exception("embed_transcript: failed to persist for id=%s", transcript_id)
        return False


def schedule_transcript_embedding(transcript_id: str, text: str) -> None:
    """Fire-and-forget transcript embedding — never blocks the voice path.

    embed_transcript() is synchronous and slow: ONNX inference plus a blocking
    Supabase write, and on the very first call it also downloads the ~67MB
    model. Awaiting it (or calling it inline) from the media-stream handler
    stalls the event loop for every concurrent call, so it runs in the default
    executor thread instead.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, embed_transcript, transcript_id, text)
        else:
            embed_transcript(transcript_id, text)
    except Exception:
        logger.exception("Failed to schedule embedding for transcript=%s", transcript_id)
