"""
Wiki / RAG service for the Travel AI Operating Layer.

Phase 2 T8: search now tries real cosine similarity first (pgvector,
via the match_travel_wiki RPC — see migrations/0004), falling back to
the original keyword scorer when semantic search can't run (embedder
unavailable, or this business has no embedded rows yet — e.g. before
backfill_embeddings() has been run). Embeddings are computed on write
(create/bulk_create) and can be backfilled for pre-existing rows.
"""
from __future__ import annotations
import logging
import re
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin
from .embeddings import embed_text

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2]


def _score(haystack: str, needles: list[str]) -> int:
    h = (haystack or "").lower()
    return sum(h.count(n) for n in needles)


class WikiService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def create(self, business_id: UUID, payload: dict[str, Any]) -> dict:
        row = {**payload, "business_id": str(business_id)}
        embedding = embed_text(f"{payload.get('title', '')} {payload.get('content', '')}")
        if embedding is not None:
            row["embedding"] = embedding
        return self.db.table("travel_wiki").insert(row).execute().data[0]

    def list(self, business_id: UUID, *, category: Optional[str] = None,
             limit: int = 100) -> list[dict]:
        q = self.db.table("travel_wiki").select("*").eq("business_id", str(business_id))
        if category:
            q = q.eq("category", category)
        return q.order("updated_at", desc=True).limit(limit).execute().data or []

    def search(self, business_id: UUID, *, query: str,
               category: Optional[str] = None, limit: int = 8) -> list[dict]:
        semantic = self._search_semantic(business_id, query=query, category=category, limit=limit)
        if semantic is not None:
            return semantic
        return self._search_keyword(business_id, query=query, category=category, limit=limit)

    def _search_semantic(self, business_id: UUID, *, query: str,
                         category: Optional[str], limit: int) -> Optional[list[dict]]:
        """Returns None (not []) when semantic search couldn't run at all,
        so the caller knows to fall back — an empty real result set is a
        valid answer, not a signal to fall back."""
        embedding = embed_text(query)
        if embedding is None:
            return None
        try:
            r = self.db.rpc("match_travel_wiki", {
                "p_business_id": str(business_id),
                "p_query_embedding": embedding,
                "p_match_count": limit,
                "p_category": category,
            }).execute()
            return r.data or []
        except Exception:
            logger.exception("semantic search RPC failed; falling back to keyword")
            return None

    def _search_keyword(self, business_id: UUID, *, query: str,
                        category: Optional[str], limit: int) -> list[dict]:
        """Keyword-ranked search across title+content+tags — the pre-T8
        implementation, kept as the fallback path."""
        rows = self.list(business_id, category=category, limit=500)
        tokens = _tokenize(query)
        if not tokens:
            return rows[:limit]

        scored = []
        for r in rows:
            tag_blob = " ".join(r.get("tags") or [])
            s = (_score(r.get("title", ""),   tokens) * 3
                 + _score(r.get("content", ""), tokens)
                 + _score(tag_blob,             tokens) * 2)
            if s:
                scored.append((s, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def delete(self, entry_id: UUID, business_id: UUID) -> bool:
        r = (
            self.db.table("travel_wiki").delete()
            .eq("id", str(entry_id)).eq("business_id", str(business_id))
            .execute()
        )
        return bool(r.data)

    def bulk_create(self, business_id: UUID, entries: list[dict]) -> int:
        if not entries:
            return 0
        rows = []
        for e in entries:
            row = {**e, "business_id": str(business_id)}
            embedding = embed_text(f"{e.get('title', '')} {e.get('content', '')}")
            if embedding is not None:
                row["embedding"] = embedding
            rows.append(row)
        r = self.db.table("travel_wiki").insert(rows).execute()
        return len(r.data or [])

    def backfill_embeddings(self, business_id: UUID) -> int:
        """Embeds every pre-existing row for this business that doesn't
        have one yet. Returns the number of rows updated."""
        rows = (
            self.db.table("travel_wiki").select("id, title, content")
            .eq("business_id", str(business_id)).is_("embedding", "null")
            .execute().data or []
        )
        updated = 0
        for r in rows:
            embedding = embed_text(f"{r.get('title', '')} {r.get('content', '')}")
            if embedding is None:
                continue
            self.db.table("travel_wiki").update({"embedding": embedding}).eq("id", r["id"]).execute()
            updated += 1
        return updated
