"""
AI conversation engine (Phase 2 T5) — Claude tool-calling persona for
live voice calls.

Extends app/services/techscape/ai_service.py's httpx-direct-to-Anthropic
pattern (that file is techscape-scoped and out of scope to modify — this
is the travel-scoped, tool-use-capable equivalent for the voice pipeline).

Two tools:
  extract_lead_details — Claude calls this whenever the customer states
    destination/budget/duration/pax count; writes to travel_leads via
    LeadService.update_extracted_fields(). Never touches assignment —
    that stays a separate manager+ action (leads.py's PUT /{id}/assign).
  get_packages — looks up real travel_packages for a destination via
    CatalogService, so Claude quotes prices grounded in real inventory
    instead of hallucinating them.

Stub mode (no ANTHROPIC_API_KEY — the current state): reuses
lead_service.py's existing extract_signals() keyword heuristic instead
of a real tool-calling decision, and still runs get_packages for real
(a plain DB query, not LLM-dependent) whenever a known destination
keyword appears — so standalone verification exercises real
tool-EXECUTION code even without a live Claude call. What stub mode
does NOT verify: actual persona quality, correct tool CHOICE by the
model, multi-turn coherence, voice-appropriate response length. See
PHASE2_REPORT.md for what's genuinely unverified.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from .catalog_service import CatalogService
from .lead_service import LeadService, extract_signals

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Phase 3 T2: build system prompt from ai_config (DB-driven persona + question flow)
def _build_system_prompt(ai_config: dict | None = None) -> str:
    if not ai_config:
        persona_name = "Klara"
        greeting = "Hello! I'm Klara, your GoGaga travel assistant."
        tone = "warm and professional"
        question_list = ""
        escalation_budget = 100000
    else:
        persona = ai_config.get("voice_persona") or {}
        persona_name = persona.get("name", "Klara")
        greeting = persona.get("greeting", "Hello! I'm Klara, your GoGaga travel assistant.")
        tone = persona.get("tone", "warm_professional").replace("_", " ")
        rules = ai_config.get("escalation_rules") or {}
        escalation_budget = rules.get("budget_threshold", 100000)
        flow = ai_config.get("question_flow") or []
        if flow:
            question_list = (
                " Work through these questions in order: "
                + " | ".join(f"{q.get('order', i+1)}. {q.get('question', '')}" for i, q in enumerate(flow))
            )
        else:
            question_list = ""

    return (
        f"You are {persona_name}, a {tone} AI travel agent taking a phone call. "
        f"Help the customer plan their trip. Keep every response short — this is a "
        f"spoken voice call, not a chat, so 1-2 short sentences, no lists, no markdown.{question_list} "
        f"Whenever the customer mentions a destination, budget, number of travelers, or "
        f"trip duration, call extract_lead_details with whatever you learned. Before "
        f"quoting any price, call get_packages to check real availability — never "
        f"invent a price. If the customer's budget exceeds ₹{escalation_budget:,}, "
        f"or they show strong buying intent, note 'ESCALATE: <reason>' in your reply "
        f"so the system can trigger manager escalation."
    )


SYSTEM_PROMPT = _build_system_prompt()  # hardcoded default, used when ai_config not available

TOOLS = [
    {
        "name": "extract_lead_details",
        "description": "Record travel details the customer has stated so far in the call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_hint": {"type": "string", "description": "Destination mentioned, e.g. 'Goa'"},
                "pax_count":        {"type": "integer", "description": "Number of travelers"},
                "budget_inr":       {"type": "integer", "description": "Budget in INR"},
                "duration_days":    {"type": "integer", "description": "Trip length in days"},
            },
        },
    },
    {
        "name": "get_packages",
        "description": "Look up real available travel packages for a destination before quoting a price.",
        "input_schema": {
            "type": "object",
            "properties": {"destination": {"type": "string"}},
            "required": ["destination"],
        },
    },
]


def _configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


async def _execute_tool(name: str, tool_input: dict, *, lead_id: UUID, business_id: UUID) -> dict:
    if name == "extract_lead_details":
        row = LeadService().update_extracted_fields(lead_id, business_id, tool_input)
        return {"updated": bool(row)}
    if name == "get_packages":
        return {"packages": get_packages(business_id, tool_input.get("destination", ""))}
    return {"error": f"unknown tool {name}"}


def get_packages(business_id: UUID, destination: str) -> list[dict]:
    """destination is a free-text name (as extracted from speech) —
    resolve to a real destination_id first, then list its packages."""
    catalog = CatalogService()
    dest_match = next(
        (d for d in catalog.list_destinations(business_id)
         if destination.strip().lower() in d["name"].lower()),
        None,
    )
    if not dest_match:
        return []
    packages = catalog.list_packages(business_id, destination_id=UUID(dest_match["id"]))
    return [
        {"name": p["name"], "duration_days": p["duration_days"], "base_price_inr": p["base_price_inr"]}
        for p in packages
    ]


async def _stub_turn(transcript: str, *, lead_id: UUID, business_id: UUID) -> dict[str, Any]:
    """No Claude key: reuse the existing keyword-heuristic extractor
    (lead_service.extract_signals) instead of a real tool-calling
    decision, but still run get_packages for real when a destination
    keyword is present — proves tool EXECUTION, not tool CHOICE."""
    signals = extract_signals(transcript)
    tool_calls: list[dict] = []
    if any(signals.values()):
        await _execute_tool("extract_lead_details", signals, lead_id=lead_id, business_id=business_id)
        tool_calls.append({"name": "extract_lead_details", "input": signals})

    packages: list[dict] = []
    if signals.get("destination_hint"):
        packages = get_packages(business_id, signals["destination_hint"])
        tool_calls.append({"name": "get_packages", "input": {"destination": signals["destination_hint"]},
                            "result_count": len(packages)})

    if packages:
        p = packages[0]
        reply = (f"We have a {p['duration_days']}-day package to "
                 f"{signals['destination_hint']} starting at ₹{p['base_price_inr']:,}. Interested?")
    elif signals.get("destination_hint"):
        reply = f"Got it, {signals['destination_hint']} — let me check what we have for you."
    else:
        reply = "Could you tell me a bit more about where you'd like to travel?"

    return {"reply": reply, "tool_calls": tool_calls, "model": "stub"}


async def run_turn(transcript: str, *, lead_id: UUID, business_id: UUID,
                   history: Optional[list[dict]] = None,
                   ai_config: Optional[dict] = None) -> dict[str, Any]:
    """One conversational turn: customer said `transcript`, returns
    {"reply": str, "tool_calls": [...], "model": str}. `history` is the
    prior Anthropic-format message list (empty/None for a fresh call).
    `ai_config` is the DB-driven persona/escalation config (Phase 3 T2)."""
    if not _configured():
        logger.warning("ANTHROPIC_API_KEY not set; using stub extraction heuristic")
        return await _stub_turn(transcript, lead_id=lead_id, business_id=business_id)

    system = _build_system_prompt(ai_config)
    messages = list(history or []) + [{"role": "user", "content": transcript}]
    tool_calls: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(4):  # bounded tool-use loop — never spin forever
            r = await client.post(
                ANTHROPIC_URL,
                headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                         "anthropic-version": ANTHROPIC_VERSION,
                         "content-type": "application/json"},
                json={"model": settings.AI_MODEL, "max_tokens": 300,
                      "system": system, "tools": TOOLS, "messages": messages},
            )
            r.raise_for_status()
            data = r.json()
            messages.append({"role": "assistant", "content": data["content"]})

            tool_use_blocks = [b for b in data["content"] if b.get("type") == "tool_use"]
            if not tool_use_blocks or data.get("stop_reason") != "tool_use":
                text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()

                # Check for escalation signal in AI reply
                if "ESCALATE:" in text and ai_config:
                    logger.info("ai_engine: escalation signal detected in turn: %s", text[:100])

                return {"reply": text, "tool_calls": tool_calls, "model": settings.AI_MODEL, "history": messages}

            tool_results = []
            for block in tool_use_blocks:
                result = await _execute_tool(block["name"], block.get("input", {}),
                                              lead_id=lead_id, business_id=business_id)
                tool_calls.append({"name": block["name"], "input": block.get("input", {})})
                tool_results.append({"type": "tool_result", "tool_use_id": block["id"],
                                      "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})

    return {"reply": "", "tool_calls": tool_calls, "model": settings.AI_MODEL, "error": "tool-use loop exceeded"}
