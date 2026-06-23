"""
AI agent service — message generation + sentiment analysis using Claude.

Uses Anthropic's Messages API directly via httpx (no extra dependency on the SDK).
"""
from __future__ import annotations
import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


CHANNEL_CONSTRAINTS = {
    "email":     "Plain prose. May include line breaks. Subject and body separated.",
    "sms":       "Maximum 160 characters. No emojis if possible. No links unless essential.",
    "whatsapp":  "Conversational, may include 1-2 emojis. Maximum 1024 characters.",
    "voice":     "Spoken script for a voice call. Short sentences. No URLs. 30-45 seconds when read aloud (~80 words).",
    "voicemail": "Spoken script for voicemail. Identify yourself. Leave a callback number placeholder. ~25 seconds (~60 words).",
}


def _build_message_prompt(
    *, context: str, channel: str, client_data: dict, business_context: dict, tone: str
) -> tuple[str, str]:
    constraint = CHANNEL_CONSTRAINTS.get(channel, "")
    system = (
        "You are a senior client-communications specialist for a service business. "
        "Generate a single message that is on-brand, concise, and ready to send. "
        "Never include placeholder tokens like {{name}} — substitute actual values from the data provided. "
        "Return ONLY a JSON object with two keys: 'subject' (string or null) and 'body' (string)."
    )
    user = (
        f"Scenario: {context}\n"
        f"Channel: {channel}\n"
        f"Channel constraints: {constraint}\n"
        f"Tone: {tone}\n"
        f"Client data: {json.dumps(client_data)}\n"
        f"Business context: {json.dumps(business_context)}\n"
        "Respond with the JSON now."
    )
    return system, user


class AIService:
    def __init__(self) -> None:
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model = settings.AI_MODEL

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def generate_message(
        self,
        *,
        context: str,
        channel: str,
        client_data: dict[str, Any],
        business_context: dict[str, Any],
        tone: str = "friendly_professional",
        max_chars: Optional[int] = None,
    ) -> dict:
        if not self.configured:
            logger.warning("Anthropic key not set; returning stub message")
            stub = self._stub(context, channel, client_data)
            body = stub.get("body") or ""
            if max_chars:
                body = body[:max_chars]
            elif channel == "sms":
                body = body[:160]
            return {**stub, "body": body, "model": "stub"}

        system, user = _build_message_prompt(
            context=context, channel=channel,
            client_data=client_data, business_context=business_context, tone=tone,
        )

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type":      "application/json",
                },
                json={
                    "model":      self.model,
                    "max_tokens": 800,
                    "system":     system,
                    "messages":   [{"role": "user", "content": user}],
                },
            )
            r.raise_for_status()
            data = r.json()

        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
        parsed = _safe_json(text) or {"subject": None, "body": text}

        body = (parsed.get("body") or "").strip()
        if max_chars:
            body = body[:max_chars]
        elif channel == "sms":
            body = body[:160]

        return {
            "subject":       parsed.get("subject"),
            "body":          body,
            "model":         self.model,
            "input_tokens":  data.get("usage", {}).get("input_tokens"),
            "output_tokens": data.get("usage", {}).get("output_tokens"),
        }

    async def classify_intent(self, *, text: str) -> dict:
        """Classify a client message into one of 5 intent buckets."""
        labels = ["booking_inquiry", "cancellation_request",
                  "payment_question", "complaint", "general_info"]
        cheap = _heuristic_intent(text, labels)
        if cheap and not self.configured:
            return cheap
        if not self.configured:
            return {"intent": "general_info", "confidence": 0.5,
                    "rationale": "stub: no Anthropic key"}
        prompt = (
            "Classify the user message. Return JSON {intent, confidence (0..1), rationale}. "
            f"Allowed intents: {', '.join(labels)}."
        )
        out = await self._llm_json(system=prompt, user=text, max_tokens=120)
        if out.get("intent") not in labels:
            out["intent"] = "general_info"
        return out

    async def summarize_conversation(self, *, messages: list[dict[str, str]]) -> dict:
        """Summarize a conversation thread (list of {role, content}) → bullets + next-step."""
        if not messages:
            return {"summary": "", "next_steps": [], "tone": "neutral", "model": "stub"}
        joined = "\n".join(f"{m.get('role','user')}: {m.get('content','')}" for m in messages)[:8000]
        if not self.configured:
            preview = " ".join((m.get("content") or "") for m in messages[-3:])[:200]
            return {
                "summary":    f"Stub summary of {len(messages)} messages: {preview}",
                "next_steps": ["Reply to client", "Update CRM"],
                "tone":       "neutral",
                "model":      "stub",
            }
        out = await self._llm_json(
            system=(
                "Summarize the conversation. Return JSON: "
                "{summary (string, <=300 chars), next_steps (array of strings), tone}."
            ),
            user=joined, max_tokens=400,
        )
        return {**out, "model": self.model}

    async def optimize_workflow(self, *, workflow: dict, recent_logs: list[dict]) -> dict:
        """Suggest workflow improvements given recent execution + log data."""
        if not self.configured:
            return {
                "recommendations": [
                    "Add a 24h delay after the WhatsApp step before SMS to reduce duplicate sends.",
                    "Consolidate the email and WhatsApp confirmation into one branch driven by client preferred_channel.",
                    "Cap retries on payment_reminder_sms at 2 to avoid TCPA risk.",
                ],
                "expected_cost_delta": -0.18,
                "expected_delivery_delta": 0.04,
                "model": "stub",
            }
        payload = {
            "workflow":         {k: workflow.get(k) for k in ("name", "trigger_type", "trigger_event_type")},
            "step_count":       len(workflow.get("steps") or []),
            "recent_log_count": len(recent_logs),
            "recent_summary":   _summarize_logs(recent_logs),
        }
        out = await self._llm_json(
            system=(
                "You are a workflow optimisation expert. "
                "Return JSON {recommendations: string[], expected_cost_delta, expected_delivery_delta}."
            ),
            user=json.dumps(payload), max_tokens=600,
        )
        return {**out, "model": self.model}

    async def generate_template(
        self, *, channel: str, scenario: str,
        tone: str = "friendly_professional", brand: Optional[str] = None,
    ) -> dict:
        """Generate a reusable template (with {{vars}}) for a channel + scenario."""
        if not self.configured:
            stub = self._stub(scenario, channel, {"client_name": "{{client.name}}"})
            return {
                "subject":   stub.get("subject"),
                "content":   stub["body"],
                "variables": _extract_vars(stub["body"]),
                "model":     "stub",
            }
        out = await self._llm_json(
            system=(
                "Generate a reusable communication template for a service business. "
                "Use {{double-curly}} placeholders. Return JSON: "
                "{subject (string|null), content (string), variables (array of strings)}."
            ),
            user=json.dumps({
                "channel": channel, "scenario": scenario,
                "tone": tone, "brand": brand,
                "constraints": CHANNEL_CONSTRAINTS.get(channel, ""),
            }),
            max_tokens=600,
        )
        if "variables" not in out or not isinstance(out.get("variables"), list):
            out["variables"] = _extract_vars(out.get("content", ""))
        return {**out, "model": self.model}

    async def analyze_sentiment(self, *, text: str) -> dict:
        """Heuristic-first sentiment, with LLM fallback when configured."""
        cheap = _heuristic_sentiment(text)
        if cheap and not self.configured:
            return cheap

        if not self.configured:
            return {"sentiment": "neutral", "score": 0.0,
                    "rationale": "No Anthropic key; defaulting to neutral."}

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type":      "application/json",
                },
                json={
                    "model":      self.model,
                    "max_tokens": 150,
                    "system":     ("Classify the sentiment of the user message into one of "
                                   "positive, neutral, negative. Return JSON: "
                                   "{sentiment, score (-1..1), rationale}."),
                    "messages":   [{"role": "user", "content": text}],
                },
            )
            r.raise_for_status()
            data = r.json()
        content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        parsed = _safe_json(content) or {"sentiment": "neutral", "score": 0.0, "rationale": "fallback"}
        return parsed

    @staticmethod
    def _stub(context: str, channel: str, client_data: dict) -> dict:
        """Travel-agency themed stubs so the demo feels real without an API key."""
        name        = client_data.get("client_name") or client_data.get("name") or "there"
        destination = client_data.get("destination") or "your destination"
        booking_ref = client_data.get("booking_ref") or "BK-2026-0001"
        dates       = client_data.get("dates") or "your travel dates"
        amount      = client_data.get("amount") or "$3,500"
        ctx_key = (context or "").lower()

        # Channel-specific templates
        if channel == "email":
            if "booking" in ctx_key and "confirm" in ctx_key:
                subject = f"Booking confirmed — {destination} ({booking_ref})"
                body = (
                    f"Hi {name},\n\n"
                    f"Your booking to {destination} is confirmed for {dates}.\n"
                    f"Booking reference: {booking_ref}.\n\n"
                    "Your full itinerary is attached. We'll be in touch with check-in details closer to your trip.\n\n"
                    "Safe travels,\nThe Tech Scape Travel Team"
                )
            elif "payment" in ctx_key:
                subject = f"Payment reminder — {booking_ref}"
                body = (
                    f"Hi {name},\n\nA gentle reminder that {amount} is due on your booking {booking_ref}.\n"
                    "You can pay securely via the link in your account portal.\n\nThanks,\nTech Scape Travel"
                )
            elif "pre" in ctx_key and "trip" in ctx_key:
                subject = f"Your trip to {destination} starts soon!"
                body = (
                    f"Hi {name},\n\nYour adventure to {destination} begins in two days. "
                    "Quick checklist:\n- Passport and visa\n- Travel insurance documents\n- Local SIM or roaming\n- Cash in local currency\n\n"
                    "We've also attached a fresh weather forecast and a packing tip sheet."
                )
            elif "follow" in ctx_key or "review" in ctx_key:
                subject = f"How was {destination}, {name}?"
                body = (
                    f"Hi {name},\n\nWe hope your trip to {destination} was everything you hoped for. "
                    "If you have a moment, we'd love a quick review — and a 10% credit on your next booking is yours when you do."
                )
            else:
                subject = context.replace("_", " ").title()
                body = f"Hi {name}, an update on your trip — {context}."

        elif channel == "sms":
            if "payment" in ctx_key:
                body = f"Tech Scape Travel: {amount} due on {booking_ref}. Pay: ts.travel/p/{booking_ref}"
            elif "booking" in ctx_key:
                body = f"Tech Scape Travel: {destination} confirmed! Ref {booking_ref}. Details emailed."
            else:
                body = f"Tech Scape Travel: update on your trip — {context}."
            body, subject = body[:160], None

        elif channel == "whatsapp":
            if "booking" in ctx_key:
                body = (f"✈️ Hi {name}! Your trip to {destination} is confirmed for {dates}. "
                        f"Reference: {booking_ref}. Full details in your email.")
            elif "follow" in ctx_key:
                body = (f"Hi {name} 🌟 We hope {destination} treated you well. "
                        "Could you spare 30 seconds for a review? Tap here: ts.travel/r")
            else:
                body = f"Hi {name} 👋 Quick update on your trip — {context}."
            subject = None

        elif channel in ("voice", "voicemail"):
            body = (f"Hello {name}, this is your Tech Scape Travel agent calling about your trip to {destination}. "
                    f"Your booking {booking_ref} is all set for {dates}. "
                    "If you have any questions, please call us back at the number on your confirmation email. Safe travels!")
            subject = None
        else:
            body, subject = f"Hi {name}, this is an automated {channel} message about: {context}.", None

        return {"subject": subject, "body": body, "input_tokens": None, "output_tokens": None}


def _safe_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        # try to find a JSON object inside
        l, r = text.find("{"), text.rfind("}")
        if 0 <= l < r:
            try:
                return json.loads(text[l:r + 1])
            except Exception:
                return None
        return None


_NEG = {"angry", "terrible", "awful", "worst", "complaint", "refund", "cancel", "disappointed"}
_POS = {"thanks", "thank", "great", "love", "amazing", "excellent", "happy", "perfect"}


def _heuristic_sentiment(text: str) -> Optional[dict]:
    t = (text or "").lower()
    if any(w in t for w in _NEG):
        return {"sentiment": "negative", "score": -0.6, "rationale": "matched negative keyword"}
    if any(w in t for w in _POS):
        return {"sentiment": "positive", "score": 0.6, "rationale": "matched positive keyword"}
    return None


# ── Intent heuristics ─────────────────────────────────────────────
_INTENT_KEYWORDS = {
    "booking_inquiry":      ["book", "available", "trip", "reserve", "package", "quote"],
    "cancellation_request": ["cancel", "cancellation", "refund", "money back", "stop"],
    "payment_question":     ["payment", "invoice", "charge", "billed", "card", "due"],
    "complaint":            ["unhappy", "bad", "wrong", "missing", "broken", "delay", "complaint"],
    "general_info":         ["info", "details", "ask", "question", "hello", "hi"],
}


def _heuristic_intent(text: str, labels: list[str]) -> Optional[dict]:
    if not text:
        return None
    t = text.lower()
    scores: dict[str, int] = {}
    for label in labels:
        for kw in _INTENT_KEYWORDS.get(label, []):
            if kw in t:
                scores[label] = scores.get(label, 0) + 1
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    return {"intent": best, "confidence": min(0.95, 0.5 + 0.1 * scores[best]),
            "rationale": "heuristic keyword match"}


def _summarize_logs(logs: list[dict]) -> dict:
    counts: dict[str, int] = {}
    delivered = 0
    failed    = 0
    for r in logs[:200]:
        counts[r.get("channel", "unknown")] = counts.get(r.get("channel", "unknown"), 0) + 1
        if r.get("delivery_status") == "delivered":
            delivered += 1
        elif r.get("delivery_status") in ("failed", "bounced"):
            failed += 1
    return {"by_channel": counts, "delivered": delivered, "failed": failed}


_VAR_RE = __import__("re").compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _extract_vars(content: str) -> list[str]:
    return sorted(set(_VAR_RE.findall(content or "")))


# ── shared LLM helper attached to AIService ───────────────────────
async def _llm_json_call(self: "AIService", *, system: str, user: str, max_tokens: int = 400) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key":         self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type":      "application/json",
            },
            json={
                "model":      self.model,
                "max_tokens": max_tokens,
                "system":     system,
                "messages":   [{"role": "user", "content": user}],
            },
        )
        r.raise_for_status()
        data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    return _safe_json(text) or {}


# bind helper as instance method
AIService._llm_json = _llm_json_call  # type: ignore[attr-defined]
