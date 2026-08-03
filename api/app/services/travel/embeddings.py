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
