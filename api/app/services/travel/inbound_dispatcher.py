"""
Inbound WhatsApp / message dispatcher (Layer 4 — Workflow Engine, demo flow).

Decides whether a fresh inbound message is:
  • a NEW LEAD              → create lead + generate itinerary
  • an IN-TRIP ISSUE         → on-ground companion
  • a TRANSLATION request    → language bridge
  • GENERAL / unknown        → franchisee-style wiki answer

The classifier is local (fast, deterministic) so the demo flow works without
an Anthropic key. When Claude is available, it is used by the downstream
agents (itinerary, on-ground), not for the dispatch decision.
"""
from __future__ import annotations
import re
from typing import Optional
from uuid import UUID

from app.database import get_supabase_admin

from .itinerary_agent  import ItineraryAgent
from .language_bridge  import LanguageBridge, SUPPORTED
from .lead_service     import LeadService, extract_signals
from .on_ground_agent  import OnGroundAgent, _classify_local


_LEAD_RE = re.compile(
    r"\b(trip|holiday|vacation|honeymoon|tour|package|itinerary|family|"
    r"days?|nights?|book|plan|going to|visit|travel)\b", re.I,
)
_INTRIP_TOKENS = [
    "cab", "taxi", "driver", "hotel changed", "lost", "stolen", "delayed",
    "no show", "isn't showing", "isnt showing", "issue", "problem",
    "right now", "currently at", "checked in",
]
_TRANSLATE_RE = re.compile(
    r"\btranslate\b|\bin (hindi|tamil|telugu|kannada|malayalam|marathi|bengali|gujarati|punjabi|urdu)\b",
    re.I,
)


def _classify_intent(text: str, *, itinerary_id: Optional[UUID]) -> str:
    t = (text or "").lower()
    if _TRANSLATE_RE.search(t):
        return "translate"

    # If the customer has an active itinerary, lean toward in-trip
    if itinerary_id:
        return "in_trip_issue"

    if any(tok in t for tok in _INTRIP_TOKENS):
        return "in_trip_issue"

    # Hard classify medical/safety as in-trip
    local_type, _ = _classify_local(t)
    if local_type in ("medical", "safety"):
        return "in_trip_issue"

    if _LEAD_RE.search(t):
        return "new_lead"

    # Has any travel-shaped signals?
    sig = extract_signals(text)
    if sig.get("destination_hint") or sig.get("budget_inr") or sig.get("duration_days"):
        return "new_lead"

    return "general"


def _extract_target_lang(text: str) -> str:
    t = (text or "").lower()
    for code, name in SUPPORTED.items():
        if name.lower() in t:
            return code
    return "hi"


class InboundDispatcher:
    def __init__(self) -> None:
        self.db        = get_supabase_admin()
        self.leads     = LeadService()
        self.itinerary = ItineraryAgent()
        self.on_ground = OnGroundAgent()
        self.language  = LanguageBridge()

    async def dispatch(
        self,
        *,
        business_id:    UUID,
        from_number:    str,
        text:           str,
        customer_name:  Optional[str] = None,
        customer_email: Optional[str] = None,
        language:       str = "en",
        itinerary_id:   Optional[UUID] = None,
    ) -> dict:
        intent = _classify_intent(text, itinerary_id=itinerary_id)

        if intent == "translate":
            target = _extract_target_lang(text)
            tr = await self.language.translate(
                text=text, source_lang=language, target_lang=target,
            )
            return {
                "intent":        "translate",
                "response_text": tr.get("translated", ""),
                "translated":    tr.get("translated"),
            }

        if intent == "in_trip_issue":
            row = await self.on_ground.handle(
                business_id=business_id,
                message=text,
                itinerary_id=itinerary_id,
                channel="whatsapp",
            )
            return {
                "intent":        "in_trip_issue",
                "response_text": row.get("agent_response") or "",
                "incident_id":   row.get("id"),
                "itinerary_id":  itinerary_id,
            }

        if intent == "new_lead":
            lead = self.leads.ingest(
                business_id=business_id,
                raw_message=text,
                source="whatsapp",
                customer_email=customer_email,
                customer_name=customer_name,
                customer_phone=from_number,
                language=language,
            )
            # Demo flow — for hot/warm leads, auto-generate an itinerary
            itin = None
            if lead.get("qualification") in ("hot", "warm"):
                itin = await self.itinerary.generate(
                    business_id=business_id,
                    intent=text,
                    pax_count=lead.get("pax_count") or 2,
                    budget_inr=lead.get("budget_inr"),
                    duration_days=lead.get("duration_days"),
                    destination_hint=lead.get("destination_hint"),
                    customer_email=customer_email,
                    customer_name=customer_name,
                    customer_phone=from_number,
                    language=language,
                )
                self.leads.attach_itinerary(
                    UUID(lead["id"]), business_id, UUID(itin["id"]),
                )
            response = self._lead_summary(lead, itin)
            return {
                "intent":        "new_lead",
                "response_text": response,
                "lead_id":       lead["id"],
                "itinerary_id":  itin["id"] if itin else None,
                "customer_id":   lead.get("customer_id"),
            }

        # general — fall through to a polite acknowledgement that nudges signals.
        return {
            "intent":        "general",
            "response_text": (
                "Got it. Could you share a few details — destination, dates, "
                "number of travelers and approximate budget? I'll put together "
                "an itinerary for you."
            ),
        }

    def _lead_summary(self, lead: dict, itin: Optional[dict]) -> str:
        dest = lead.get("destination_hint") or "your destination"
        days = lead.get("duration_days") or (itin.get("days") and len(itin["days"]))
        pax  = lead.get("pax_count") or 2
        budget = lead.get("budget_inr")

        if itin:
            cost = itin.get("total_cost_inr") or 0
            lines = [
                f"Here's a draft itinerary for {dest} — {days or len(itin.get('days') or [])} days, "
                f"{pax} traveler(s).",
                f"Total estimated cost: ₹{cost:,}.",
                "",
                "Reply with any change (e.g. add a houseboat night, make it 4 days, "
                "switch to a 4★ hotel) and I'll update it instantly.",
            ]
            return "\n".join(lines)

        bits = [f"Got your inquiry for {dest}"]
        if days:   bits.append(f"{days} days")
        if pax:    bits.append(f"{pax} traveler(s)")
        if budget: bits.append(f"under ₹{budget:,}")
        return (
            ", ".join(bits) + ". A consultant will reach out within the hour "
            "with a tailored itinerary."
        )
