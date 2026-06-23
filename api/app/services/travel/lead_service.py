"""
Lead Qualification & Scoring — pre-booking funnel (strategy doc section 05).

Reads raw inbound text from any channel, extracts the budget/duration/pax/
destination signals, scores intent strength, and persists a lead. Used by
the inbound WhatsApp dispatcher and direct UI submissions.
"""
from __future__ import annotations
import re
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin

from .customer_memory import CustomerMemoryService


_NUM_RE = re.compile(r"(\d[\d,]*)\s*(k|K|lakh|lakhs|L|crore|cr)?")
_PAX_RE = re.compile(r"(\d+)\s*(?:pax|people|persons?|adults?|members?|family of)", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*(?:days?|nights?|d\b|n\b)", re.I)

_HOT_TOKENS  = ["book", "confirm", "pay", "asap", "urgent", "tomorrow", "next week", "this month"]
_WARM_TOKENS = ["plan", "looking", "quote", "price", "package", "itinerary", "honeymoon", "family"]
_DEST_TOKENS = [
    "kerala", "himachal", "rajasthan", "goa", "thailand", "singapore", "dubai",
    "bali", "manali", "shimla", "munnar", "alleppey", "udaipur", "jaipur",
    "andaman", "ladakh", "kashmir", "north india", "south india",
]


def _to_inr(num: str, unit: Optional[str]) -> int:
    raw = num.replace(",", "")
    try:
        n = int(raw)
    except ValueError:
        return 0
    u = (unit or "").lower()
    if u in ("k",):
        return n * 1_000
    if u in ("lakh", "lakhs", "l"):
        return n * 100_000
    if u in ("crore", "cr"):
        return n * 10_000_000
    return n


def extract_signals(text: str) -> dict:
    t = (text or "").lower()
    budget = None
    for m in _NUM_RE.finditer(text or ""):
        val = _to_inr(m.group(1), m.group(2))
        if val >= 5_000:
            budget = val if budget is None else max(budget, val)
    pax_m  = _PAX_RE.search(text or "")
    days_m = _DAYS_RE.search(text or "")
    dest = next((d.title() for d in _DEST_TOKENS if d in t), None)
    return {
        "budget_inr":   budget,
        "pax_count":    int(pax_m.group(1)) if pax_m else None,
        "duration_days": int(days_m.group(1)) if days_m else None,
        "destination_hint": dest,
    }


def score_lead(text: str, signals: dict) -> tuple[int, str]:
    """Returns (score 0..100, qualification)."""
    t = (text or "").lower()
    score = 0
    if signals.get("destination_hint"):  score += 25
    if signals.get("pax_count"):         score += 15
    if signals.get("duration_days"):     score += 15
    if signals.get("budget_inr"):        score += 25
    if any(k in t for k in _HOT_TOKENS):  score += 20
    elif any(k in t for k in _WARM_TOKENS): score += 10
    score = min(score, 100)
    if score >= 70: q = "hot"
    elif score >= 40: q = "warm"
    else: q = "cold"
    return score, q


class LeadService:
    def __init__(self) -> None:
        self.db     = get_supabase_admin()
        self.memory = CustomerMemoryService()

    def ingest(
        self,
        *,
        business_id:  UUID,
        raw_message:  str,
        source:       str = "whatsapp",
        customer_email: Optional[str] = None,
        customer_name:  Optional[str] = None,
        customer_phone: Optional[str] = None,
        language:     str = "en",
        franchisee_id: Optional[UUID] = None,
    ) -> dict:
        signals = extract_signals(raw_message)
        score, qual = score_lead(raw_message, signals)
        profile = self.memory.upsert_from_intent(
            business_id=business_id, intent=raw_message,
            email=customer_email, name=customer_name, phone=customer_phone,
            language=language,
        )
        row = self.db.table("travel_leads").insert({
            "business_id":     str(business_id),
            "customer_id":     profile.get("id") if profile else None,
            "source":          source,
            "raw_message":     raw_message,
            "intent":          raw_message[:500],
            "destination_hint": signals.get("destination_hint"),
            "pax_count":       signals.get("pax_count"),
            "budget_inr":      signals.get("budget_inr"),
            "duration_days":   signals.get("duration_days"),
            "score":           score,
            "qualification":   qual,
            "status":          "new",
            "franchisee_id":   str(franchisee_id) if franchisee_id else None,
        }).execute().data[0]
        return row

    def list(self, business_id: UUID, *,
             status: Optional[str] = None,
             qualification: Optional[str] = None,
             limit: int = 100) -> list[dict]:
        q = (
            self.db.table("travel_leads").select("*")
            .eq("business_id", str(business_id))
        )
        if status:        q = q.eq("status", status)
        if qualification: q = q.eq("qualification", qualification)
        return q.order("created_at", desc=True).limit(limit).execute().data or []

    def get(self, lead_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_leads").select("*")
            .eq("id", str(lead_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def attach_itinerary(self, lead_id: UUID, business_id: UUID,
                         itinerary_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_leads").update({
                "itinerary_id": str(itinerary_id),
                "status":       "itinerary_sent",
            })
            .eq("id", str(lead_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    def update_status(self, lead_id: UUID, business_id: UUID,
                      status: str) -> dict | None:
        patch: dict = {"status": status}
        if status == "booked":
            patch["qualification"] = "converted"
        elif status == "lost":
            patch["qualification"] = "lost"
        r = (
            self.db.table("travel_leads").update(patch)
            .eq("id", str(lead_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None
