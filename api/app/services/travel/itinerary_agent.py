"""
Itinerary Agent — Attack Point 2 from the strategy doc.

Takes a customer intent ("Family of 4, North India, 6 days, ₹2L"), builds
a full itinerary using Claude grounded by RAG (travel_wiki + travel_packages),
and persists the result so it can be refined or sent to the customer.

In stub mode (no Anthropic key) returns a believable hand-crafted itinerary
so the platform works end-to-end without external calls.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin

from .customer_memory import CustomerMemoryService
from .wiki_service    import WikiService

logger = logging.getLogger(__name__)


ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


SYSTEM_PROMPT = """\
You are a senior travel consultant for Gogaga Holidays — India's no.1 holiday company.
Build a clear, day-by-day itinerary that fits the customer's intent, pax count, and budget.

Rules:
  • Output ONLY a JSON object: {title, days, total_cost_inr, cost_breakdown}
  • days: array of {day, location, title, activities, meals, hotel, transport, notes}
  • total_cost_inr: integer (rupees) — must match the sum of cost_breakdown values
  • cost_breakdown: {flights, hotels, transport, activities, meals, miscellaneous}
  • Use ONLY destinations / packages from the provided RAG context. Do not invent properties or prices.
  • Stay within the budget. If it cannot fit, lower the duration or cut activities and say so in days[0].notes.
"""


def _safe_json(text: str) -> Optional[dict]:
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


_NUM_RE = re.compile(r"(\d[\d,]*)\s*(?:k|K|lakh|lakhs|L)?")


def _extract_budget_inr(text: str) -> Optional[int]:
    m = _NUM_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        n = int(raw)
    except ValueError:
        return None
    tail = (text[m.end():] or "")[:4].lower()
    if "lakh" in tail or text[m.end():m.end()+1].lower() == "l":
        return n * 100_000
    if text[m.end():m.end()+1].lower() == "k":
        return n * 1_000
    return n


class ItineraryAgent:
    def __init__(self) -> None:
        self.db        = get_supabase_admin()
        self.wiki      = WikiService()
        self.memory    = CustomerMemoryService()
        self.api_key   = settings.ANTHROPIC_API_KEY
        self.model     = settings.AI_MODEL

    async def generate(
        self,
        *,
        business_id:  UUID,
        intent:       str,
        pax_count:    int = 2,
        budget_inr:   Optional[int] = None,
        duration_days: Optional[int] = None,
        destination_hint: Optional[str] = None,
        customer_id: Optional[UUID] = None,
        customer_email: Optional[str] = None,
        customer_name:  Optional[str] = None,
        customer_phone: Optional[str] = None,
        language: str = "en",
    ) -> dict:
        # 1. Resolve / upsert the customer profile so we have memory across runs.
        profile = self.memory.upsert_from_intent(
            business_id=business_id, intent=intent,
            email=customer_email, name=customer_name, phone=customer_phone,
            language=language, customer_id=customer_id,
        )

        # 2. Pull RAG context from the wiki + packages.
        wiki_hits = self.wiki.search(business_id, query=intent, limit=6)
        packages  = self._top_packages(business_id, intent, destination_hint, limit=5)
        dests     = self._destinations(business_id, intent, destination_hint, limit=5)

        budget_inr = budget_inr or _extract_budget_inr(intent)

        # 3. Run the LLM (or stub).
        result = await self._call_llm(
            intent=intent, pax_count=pax_count,
            budget_inr=budget_inr, duration_days=duration_days,
            wiki_hits=wiki_hits, packages=packages, destinations=dests,
            past_trips=profile.get("past_trips") or [],
        )

        title          = result.get("title")  or f"{(destination_hint or '').title() or 'Custom'} Trip"
        days           = result.get("days") or []
        total_cost_inr = int(result.get("total_cost_inr") or 0)
        cost_breakdown = result.get("cost_breakdown") or {}

        # 4. Persist.
        row = self.db.table("travel_itineraries").insert({
            "business_id":    str(business_id),
            "customer_id":    profile.get("id") if profile else None,
            "title":          title,
            "intent":         intent,
            "days":           days,
            "total_cost_inr": total_cost_inr,
            "cost_breakdown": cost_breakdown,
            "status":         "draft",
            "pax_count":      pax_count,
            "version":        1,
            "model":          self.model if self.api_key else "stub",
            "raw_response":   {"wiki_hits": [w["id"] for w in wiki_hits],
                                "packages":   [p["id"] for p in packages]},
        }).execute().data[0]

        # 5. Remember the latest intent on the profile.
        if profile and profile.get("id"):
            self.memory.set_last_intent(UUID(profile["id"]), intent)

        return row

    async def refine(
        self, *, itinerary_id: UUID, business_id: UUID, modifications: str,
    ) -> dict:
        original = (
            self.db.table("travel_itineraries").select("*")
            .eq("id", str(itinerary_id)).eq("business_id", str(business_id))
            .limit(1).execute().data
        )
        if not original:
            raise ValueError("itinerary not found")
        src = original[0]

        # Reuse intent + add modifications
        new_intent = f"{src.get('intent') or ''}\n[MODIFICATIONS]: {modifications}"
        result = await self._call_llm(
            intent=new_intent, pax_count=src.get("pax_count") or 2,
            budget_inr=None, duration_days=None,
            wiki_hits=[], packages=[], destinations=[],
            past_trips=[], modify_from=src,
        )

        days           = result.get("days") or src.get("days")
        title          = result.get("title") or src.get("title")
        total_cost_inr = int(result.get("total_cost_inr") or src.get("total_cost_inr") or 0)
        cost_breakdown = result.get("cost_breakdown") or src.get("cost_breakdown") or {}

        # mark original as modified and insert a new version
        self.db.table("travel_itineraries").update({"status": "modified"}).eq(
            "id", str(itinerary_id)
        ).execute()

        new_row = self.db.table("travel_itineraries").insert({
            "business_id":    str(business_id),
            "customer_id":    src.get("customer_id"),
            "title":          title,
            "intent":         new_intent,
            "days":           days,
            "total_cost_inr": total_cost_inr,
            "cost_breakdown": cost_breakdown,
            "status":         "draft",
            "pax_count":      src.get("pax_count") or 2,
            "version":        (src.get("version") or 1) + 1,
            "parent_id":      str(itinerary_id),
            "model":          self.model if self.api_key else "stub",
        }).execute().data[0]
        return new_row

    def get(self, itinerary_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_itineraries").select("*")
            .eq("id", str(itinerary_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def list(self, business_id: UUID, *, limit: int = 50) -> list[dict]:
        return (
            self.db.table("travel_itineraries").select("*")
            .eq("business_id", str(business_id))
            .order("created_at", desc=True).limit(limit)
            .execute().data or []
        )

    def update_status(self, itinerary_id: UUID, business_id: UUID,
                      status: str) -> dict | None:
        r = (
            self.db.table("travel_itineraries").update({"status": status})
            .eq("id", str(itinerary_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    # ── helpers ──────────────────────────────────────────────
    def _top_packages(self, business_id, intent, hint, *, limit) -> list[dict]:
        rows = (
            self.db.table("travel_packages").select("*")
            .eq("business_id", str(business_id)).eq("is_active", True)
            .limit(50).execute().data or []
        )
        if not rows:
            return []
        needles = (intent + " " + (hint or "")).lower().split()
        scored = []
        for r in rows:
            blob = (r["name"] + " " + json.dumps(r.get("inclusions") or [])).lower()
            s = sum(blob.count(n) for n in needles if len(n) > 2)
            scored.append((s, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def _destinations(self, business_id, intent, hint, *, limit) -> list[dict]:
        rows = (
            self.db.table("travel_destinations").select("*")
            .eq("business_id", str(business_id)).eq("is_active", True)
            .limit(50).execute().data or []
        )
        needles = (intent + " " + (hint or "")).lower().split()
        scored = []
        for r in rows:
            blob = (r["name"] + " " + (r.get("country") or "") + " " + (r.get("region") or "")).lower()
            s = sum(blob.count(n) for n in needles if len(n) > 2)
            scored.append((s, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    async def _call_llm(
        self, *, intent, pax_count, budget_inr, duration_days,
        wiki_hits, packages, destinations, past_trips, modify_from=None,
    ) -> dict:
        if not self.api_key:
            return self._stub(intent=intent, pax_count=pax_count,
                              budget_inr=budget_inr, duration_days=duration_days,
                              packages=packages, destinations=destinations,
                              modify_from=modify_from)

        context = {
            "intent":         intent,
            "pax_count":      pax_count,
            "budget_inr":     budget_inr,
            "duration_days":  duration_days,
            "modify_from":    {k: modify_from.get(k) for k in
                                ("title", "days", "total_cost_inr", "cost_breakdown")}
                              if modify_from else None,
            "wiki": [
                {"category": w.get("category"), "title": w.get("title"),
                 "content": (w.get("content") or "")[:600]}
                for w in wiki_hits
            ],
            "packages": [
                {"name": p["name"], "duration_days": p["duration_days"],
                 "base_price_inr": p["base_price_inr"],
                 "inclusions": p.get("inclusions") or []}
                for p in packages
            ],
            "destinations": [
                {"name": d["name"], "country": d["country"],
                 "region": d.get("region"), "highlights": d.get("highlights") or [],
                 "avg_cost_inr": d.get("avg_cost_inr")}
                for d in destinations
            ],
            "past_trips": past_trips,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type":      "application/json",
                },
                json={
                    "model":      self.model,
                    "max_tokens": 2200,
                    "system":     SYSTEM_PROMPT,
                    "messages":   [{"role": "user", "content": json.dumps(context)}],
                },
            )
            r.raise_for_status()
            data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return _safe_json(text) or {}

    # ── stub itinerary (deterministic, package-driven if any) ─
    def _stub(self, *, intent, pax_count, budget_inr, duration_days,
              packages, destinations, modify_from=None) -> dict:
        days_target = duration_days or 5
        # if a modification, try to honour duration change in the modifications text
        if modify_from:
            m = re.search(r"(\d+)\s*day", intent.lower())
            if m:
                days_target = int(m.group(1))

        # pick a destination
        dest = (destinations[0]["name"] if destinations else None) or \
               (packages[0]["name"]    if packages    else None) or "Kerala"
        per_person_base = (packages[0]["base_price_inr"] if packages
                            else 18000)  # ~₹18k/person/5d default
        per_pax = per_person_base * (days_target / 5)
        total = int(per_pax * pax_count)
        if budget_inr:
            total = min(total, budget_inr)
            # rebalance per_pax
            per_pax = total / pax_count

        title = f"{dest.title()} — {days_target} days for {pax_count}"
        days = []
        templates = [
            ("Arrival & Welcome", ["Airport pickup", "Hotel check-in", "Evening leisure walk"],
             ["Welcome dinner"]),
            ("Local sights",      ["Guided city tour", "Boat ride", "Local market visit"],
             ["Breakfast", "Lunch at heritage cafe", "Dinner"]),
            ("Day trip",          ["Backwater cruise", "Spice plantation visit"],
             ["Breakfast", "Onboard lunch", "Dinner"]),
            ("Nature & culture",  ["Tea estate walk", "Cultural show"],
             ["Breakfast", "Lunch", "Dinner"]),
            ("Beach / leisure",   ["Beach day", "Sunset cruise"],
             ["Breakfast", "Lunch", "Farewell dinner"]),
            ("Departure",         ["Hotel checkout", "Souvenir shopping", "Airport drop"],
             ["Breakfast"]),
        ]
        for i in range(1, days_target + 1):
            t, acts, meals = templates[(i - 1) % len(templates)]
            days.append({
                "day": i,
                "location": dest,
                "title": t,
                "activities": acts,
                "meals": meals,
                "hotel": f"3★ partner hotel in {dest}",
                "transport": "Private car" if i in (1, days_target) else "Group coach",
                "notes": None,
            })

        breakdown = {
            "flights":       int(total * 0.30),
            "hotels":        int(total * 0.35),
            "transport":     int(total * 0.10),
            "activities":    int(total * 0.10),
            "meals":         int(total * 0.10),
            "miscellaneous": int(total * 0.05),
        }
        breakdown["miscellaneous"] += total - sum(breakdown.values())

        return {
            "title": title,
            "days":  days,
            "total_cost_inr": total,
            "cost_breakdown": breakdown,
        }
