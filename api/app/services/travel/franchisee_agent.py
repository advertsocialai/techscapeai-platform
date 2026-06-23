"""
Franchisee Support Agent — answers the top 80% of franchisee queries from
the wiki without involving HQ support. Strategy doc Tier 1 item.
"""
from __future__ import annotations
import json
import logging
from typing import Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin

from .wiki_service import WikiService

logger = logging.getLogger(__name__)

ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = """\
You are the support agent for the franchisee network of Gogaga Holidays.
You are professional, precise, and grounded in the company's SOPs.
Answer ONLY from the wiki context provided. If the answer is not in the
context, say "I'll route this to HQ" — never invent a policy.
Output JSON: {answer (string), confident (bool)}.
"""


class FranchiseeAgent:
    def __init__(self) -> None:
        self.db   = get_supabase_admin()
        self.wiki = WikiService()
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model   = settings.AI_MODEL

    async def ask(
        self, *, business_id: UUID, question: str,
        franchisee_id: Optional[UUID] = None,
        franchisee_city: Optional[str] = None,
    ) -> dict:
        # Pull relevant wiki hits — prefer policy/sop/objection
        hits = []
        for cat in ("policy", "sop", "objection", "package", "general"):
            hits.extend(self.wiki.search(business_id, query=question,
                                          category=cat, limit=3))
            if len(hits) >= 8:
                break
        hits = hits[:8]

        if not self.api_key:
            return self._stub(question, hits)

        ctx = {
            "question":       question,
            "franchisee_city": franchisee_city,
            "wiki": [{"title": h.get("title"),
                      "category": h.get("category"),
                      "content": (h.get("content") or "")[:500]}
                     for h in hits],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={"x-api-key": self.api_key,
                         "anthropic-version": ANTHROPIC_VERSION,
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 600,
                      "system": SYSTEM_PROMPT,
                      "messages": [{"role": "user", "content": json.dumps(ctx)}]},
            )
            r.raise_for_status()
            data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()
        parsed = _safe_json(text) or {"answer": text or "I'll route this to HQ",
                                       "confident": False}
        parsed["sources"] = [
            {"id": h["id"], "title": h["title"], "category": h["category"]}
            for h in hits
        ]
        parsed["model"] = self.model
        return parsed

    def _stub(self, question: str, hits: list[dict]) -> dict:
        if not hits:
            return {"answer": "I'll route this to HQ — I don't have that information yet.",
                    "confident": False, "sources": [], "model": "stub"}
        # Concatenate top 2 hits into a clean response
        top = hits[:2]
        bullets = "\n".join(f"• {h['title']}: {h['content'][:280]}…" for h in top)
        return {
            "answer": f"Based on Gogaga policy:\n\n{bullets}",
            "confident": True,
            "sources": [{"id": h["id"], "title": h["title"],
                         "category": h["category"]} for h in top],
            "model":   "stub",
        }


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        l, r = text.find("{"), text.rfind("}")
        if 0 <= l < r:
            try:
                return json.loads(text[l:r + 1])
            except Exception:
                return None
    return None
