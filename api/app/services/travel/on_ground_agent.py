"""
On-Ground Companion — Attack Point 4 from the strategy doc.

Travelers WhatsApp "cab isn't showing up" or "hotel changed my room" mid-trip.
This agent classifies the issue, drafts a grounded response (using wiki + the
customer's current itinerary), persists an incident, and escalates when the
severity warrants it (medical, safety, complaint, etc.).

Stub mode: produces deterministic responses for the 11 issue types so the
demo works without an Anthropic key.
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin

from .wiki_service import WikiService

logger = logging.getLogger(__name__)

ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = """\
You are the on-ground companion agent for Gogaga Holidays travelers — their
intelligent local friend during the trip. The customer messages from inside an
active trip; you have their itinerary and the company SOP/wiki.

Rules:
  • Be calm, brief, action-oriented. Lead with the FIX, not sympathy.
  • Use ONLY the itinerary + wiki context provided. If you do not know, say so
    and recommend immediate human escalation.
  • Output JSON: {issue_type, severity, response, escalate (bool), escalate_to}
  • issue_type ∈ cab_no_show|hotel_change|flight_delay|lost_item|language_help|
                  payment_issue|medical|safety|complaint|request|other
  • severity ∈ low|normal|high|critical
  • Always escalate medical/safety/critical to HQ.
"""


# Pattern-based classifier for the stub + a fast preflight before LLM
_ISSUE_PATTERNS: list[tuple[str, list[str]]] = [
    ("medical",      ["medical","hospital","sick","pain","fever","blood","ambulance","injured","hurt"]),
    ("safety",       ["unsafe","threat","police","robbed","stolen","attacked","scared"]),
    ("cab_no_show",  ["cab","taxi","driver","uber","ola","not showing","no show","didn't come","didnt come"]),
    ("hotel_change", ["hotel","room","check-in","checkin","upgraded","downgraded","reassigned","changed my room"]),
    ("flight_delay", ["flight","delayed","cancelled","missed","gate","boarding","airline"]),
    ("lost_item",    ["lost","misplaced","forgot","left","passport","wallet","luggage","bag"]),
    ("language_help",["translate","hindi","language","don't understand","cant understand","local language"]),
    ("payment_issue",["payment","refund","charge","bill","invoice","money back","extra charge"]),
    ("complaint",    ["complaint","unhappy","worst","disappointed","poor","bad service","review"]),
    ("request",      ["please","could you","can you","need","want","help me"]),
]

_SEVERITY_OVERRIDE = {
    "medical":  "critical",
    "safety":   "critical",
}


def _classify_local(text: str) -> tuple[str, str]:
    lower = (text or "").lower()
    for itype, patterns in _ISSUE_PATTERNS:
        if any(p in lower for p in patterns):
            sev = _SEVERITY_OVERRIDE.get(itype, "normal")
            return itype, sev
    return "other", "normal"


_STUB_RESPONSES = {
    "cab_no_show":  "Got it — I'm calling your driver now and arranging a backup cab. You'll have a vehicle within 10 minutes. I'll text the new driver's name and number here.",
    "hotel_change": "I'm contacting the property to reverse the room change. If they can't restore your booked category, I'll move you to a comparable 4★ property nearby at no extra cost.",
    "flight_delay": "I see the delay. I've rebooked your airport transfer to the new arrival time and notified your hotel. You don't need to do anything.",
    "lost_item":    "Don't worry — I'm filing a lost-and-found report at your last 3 stops and the airline. I'll update you within 2 hours.",
    "language_help":"Send me the Hindi (or local) text you want translated and I'll relay it. I can also call the vendor in Hindi on your behalf.",
    "payment_issue":"Sharing this with our billing team now. You'll have a written response within 4 hours, and any erroneous charge will be reversed.",
    "medical":      "Routing to HQ medical desk immediately — please call +91-99999-99999 right now. Nearest hospital and a Hindi-speaking coordinator are being arranged.",
    "safety":       "Escalating to HQ safety desk + local emergency contact. If you are in immediate danger, dial 112. Stay on this chat — I'm with you.",
    "complaint":    "Heard. I've raised a priority ticket and a supervisor will message you within 30 minutes with a resolution path.",
    "request":      "I'll take care of it — confirming details with the supplier and I'll be back within 15 minutes.",
    "other":        "I'm on it. I'll get back within 15 minutes with the next step.",
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


class OnGroundAgent:
    def __init__(self) -> None:
        self.db      = get_supabase_admin()
        self.wiki    = WikiService()
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model   = settings.AI_MODEL

    async def handle(
        self,
        *,
        business_id:  UUID,
        message:      str,
        itinerary_id: Optional[UUID] = None,
        customer_id:  Optional[UUID] = None,
        channel:      str = "whatsapp",
    ) -> dict:
        # 1. Pull supporting context.
        itinerary = self._get_itinerary(itinerary_id, business_id) if itinerary_id else None
        wiki_hits = self.wiki.search(business_id, query=message, limit=4)

        # 2. Classify (also helps when LLM is unavailable).
        local_type, local_sev = _classify_local(message)

        # 3. Run LLM, else stub.
        if self.api_key:
            result = await self._call_llm(
                message=message, itinerary=itinerary,
                wiki_hits=wiki_hits, hint_type=local_type,
            )
        else:
            result = {
                "issue_type":  local_type,
                "severity":    local_sev,
                "response":    _STUB_RESPONSES.get(local_type, _STUB_RESPONSES["other"]),
                "escalate":    local_sev in ("critical", "high"),
                "escalate_to": "HQ Medical Desk" if local_type == "medical"
                               else "HQ Safety Desk" if local_type == "safety"
                               else None,
            }

        # 4. Persist as an incident.
        status_val = "escalated" if result.get("escalate") else "in_progress"
        row = self.db.table("travel_in_trip_incidents").insert({
            "business_id":      str(business_id),
            "itinerary_id":     str(itinerary_id) if itinerary_id else None,
            "customer_id":      str(customer_id)  if customer_id  else None,
            "channel":          channel,
            "issue_type":       result.get("issue_type") or local_type,
            "severity":         result.get("severity")   or local_sev,
            "customer_message": message,
            "agent_response":   result.get("response"),
            "status":           status_val,
            "escalated_to":     result.get("escalate_to"),
            "metadata":         {"wiki_hits": [h["id"] for h in wiki_hits]},
        }).execute().data[0]
        return row

    def list_incidents(
        self, business_id: UUID, *, status: Optional[str] = None,
        itinerary_id: Optional[UUID] = None, limit: int = 100,
    ) -> list[dict]:
        q = (
            self.db.table("travel_in_trip_incidents").select("*")
            .eq("business_id", str(business_id))
        )
        if status:
            q = q.eq("status", status)
        if itinerary_id:
            q = q.eq("itinerary_id", str(itinerary_id))
        return q.order("created_at", desc=True).limit(limit).execute().data or []

    def get_incident(self, incident_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_in_trip_incidents").select("*")
            .eq("id", str(incident_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    def resolve(self, incident_id: UUID, business_id: UUID,
                *, note: Optional[str] = None) -> dict | None:
        patch: dict[str, Any] = {
            "status":      "resolved",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        if note:
            patch["metadata"] = {"resolution_note": note}
        r = (
            self.db.table("travel_in_trip_incidents").update(patch)
            .eq("id", str(incident_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    def escalate(self, incident_id: UUID, business_id: UUID,
                 *, escalate_to: str, note: Optional[str] = None) -> dict | None:
        patch: dict[str, Any] = {
            "status":       "escalated",
            "escalated_to": escalate_to,
        }
        if note:
            patch["metadata"] = {"escalation_note": note}
        r = (
            self.db.table("travel_in_trip_incidents").update(patch)
            .eq("id", str(incident_id)).eq("business_id", str(business_id))
            .execute()
        )
        return r.data[0] if r.data else None

    # ── helpers ──────────────────────────────────────────────
    def _get_itinerary(self, itinerary_id: UUID, business_id: UUID) -> dict | None:
        r = (
            self.db.table("travel_itineraries").select("*")
            .eq("id", str(itinerary_id)).eq("business_id", str(business_id))
            .limit(1).execute()
        )
        return r.data[0] if r.data else None

    async def _call_llm(self, *, message, itinerary, wiki_hits, hint_type) -> dict:
        ctx = {
            "customer_message": message,
            "hint_classification": hint_type,
            "itinerary": {k: itinerary.get(k) for k in ("title", "days", "status")}
                         if itinerary else None,
            "wiki": [
                {"title": w.get("title"), "category": w.get("category"),
                 "content": (w.get("content") or "")[:400]}
                for w in wiki_hits
            ],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={"x-api-key": self.api_key,
                         "anthropic-version": ANTHROPIC_VERSION,
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 700,
                      "system": SYSTEM_PROMPT,
                      "messages": [{"role": "user", "content": json.dumps(ctx)}]},
            )
            r.raise_for_status()
            data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()
        parsed = _safe_json(text) or {}
        parsed.setdefault("issue_type", hint_type)
        parsed.setdefault("severity",   _SEVERITY_OVERRIDE.get(hint_type, "normal"))
        parsed.setdefault("response",   text or _STUB_RESPONSES.get(hint_type, ""))
        parsed.setdefault("escalate",   parsed.get("severity") in ("high", "critical"))
        return parsed
