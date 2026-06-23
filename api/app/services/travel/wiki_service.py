"""
Wiki / RAG service for the Travel AI Operating Layer.

For now uses trigram-based keyword search (fast, requires no model).
Vector embedding column is in place — swap to cosine search when an
embeddings provider is wired in.
"""
from __future__ import annotations
import re
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin


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
        return self.db.table("travel_wiki").insert(row).execute().data[0]

    def list(self, business_id: UUID, *, category: Optional[str] = None,
             limit: int = 100) -> list[dict]:
        q = self.db.table("travel_wiki").select("*").eq("business_id", str(business_id))
        if category:
            q = q.eq("category", category)
        return q.order("updated_at", desc=True).limit(limit).execute().data or []

    def search(self, business_id: UUID, *, query: str,
               category: Optional[str] = None, limit: int = 8) -> list[dict]:
        """Keyword-ranked search across title+content+tags."""
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
        rows = [{**e, "business_id": str(business_id)} for e in entries]
        r = self.db.table("travel_wiki").insert(rows).execute()
        return len(r.data or [])
