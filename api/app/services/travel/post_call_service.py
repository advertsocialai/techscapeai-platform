"""
Post-call intelligence pipeline (Phase 3 T5).

Triggered asynchronously when a call reaches status='completed'.
Runs a Claude Sonnet call over the full transcript to produce:
  - Structured summary (key intents, decisions, follow-ups)
  - Final sentiment_score
  - Lead score update + qualification upgrade
  - Extraction reconciliation (resolve conflicting per-turn extractions)

Idempotent: re-running on a call_id that already has a summary
produces the same output and does NOT create duplicate rows.

Stub mode (no ANTHROPIC_API_KEY): extracts basic stats from the
transcript and writes a keyword-summary. See BLOCKERS.md B-P3-03.
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin

from . import background

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_SUMMARY_SYSTEM = (
    "You are a post-call analyst for a travel agency. "
    "Given a call transcript, return a JSON object with these keys ONLY:\n"
    "  summary: string (2-4 sentences: what the customer wanted, what was offered, outcome)\n"
    "  destination: string or null (primary destination discussed)\n"
    "  budget_inr: integer or null\n"
    "  duration_days: integer or null\n"
    "  pax_count: integer or null\n"
    "  outcome: one of 'interested'|'not_interested'|'booked'|'escalated'|'unclear'\n"
    "  lead_score: integer 1-100 (purchase intent)\n"
    "  follow_up_action: string or null (specific next step for the agent)\n"
    "Return ONLY the JSON object, no markdown."
)


def _stub_summary(transcript_rows: list[dict]) -> dict:
    """Fallback when no ANTHROPIC_API_KEY: keyword-extract from transcript."""
    all_text = " ".join(r["text_original"] for r in transcript_rows if r.get("speaker") == "customer")
    turns = len(transcript_rows)
    # The prefix must stay outside the ternary: implicit string concatenation
    # binds tighter than `if/else`, so writing it inline made the whole prefixed
    # string the true-branch and left the false-branch as bare `all_text`. That
    # returned '' for a transcript with no customer text, and since the pipeline's
    # idempotency guard is a truthiness check on `summary`, an empty summary let
    # every re-run repeat all writes.
    sample = f"{all_text[:200]}..." if len(all_text) > 200 else all_text
    return {
        "summary": f"Call with {turns} transcript rows. Customer text sample: {sample}",
        "destination": None,
        "budget_inr": None,
        "duration_days": None,
        "pax_count": None,
        "outcome": "unclear",
        "lead_score": 40,
        "follow_up_action": "Review transcript manually — no ANTHROPIC_API_KEY configured",
    }


async def _claude_summary(transcript_rows: list[dict]) -> dict:
    formatted = "\n".join(
        f"[{r['speaker'].upper()}] {r['text_original']}" for r in transcript_rows
    )
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(
                ANTHROPIC_URL,
                headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-sonnet-4-6",
                      "max_tokens": 512,
                      "system": _SUMMARY_SYSTEM,
                      "messages": [{"role": "user", "content": f"Transcript:\n{formatted}"}]},
            )
            r.raise_for_status()
            data = r.json()
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            # Strip any markdown fences
            text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(text)
    except Exception:
        logger.exception("Claude post-call summary failed")
        return {}


async def run_pipeline(call_id: str, business_id: str) -> None:
    """Idempotent: checks if summary already written before doing work."""
    db = get_supabase_admin()

    # Idempotency guard
    call_row = db.table("travel_calls").select("summary, lead_id, takeover_state").eq(
        "id", call_id).limit(1).execute().data
    if not call_row:
        logger.warning("post_call: call %s not found", call_id)
        return
    call = call_row[0]
    if call.get("summary"):
        logger.info("post_call: call %s already has summary — skipping (idempotent)", call_id)
        return

    # Fetch transcript
    transcript_rows = (
        db.table("travel_transcripts").select("speaker, text_original, timestamp_ms, sentiment")
        .eq("call_id", call_id)
        .order("timestamp_ms").execute().data or []
    )
    if not transcript_rows:
        logger.info("post_call: call %s has no transcript rows — skipping", call_id)
        return

    # Generate summary
    if settings.ANTHROPIC_API_KEY:
        result = await _claude_summary(transcript_rows)
    else:
        result = _stub_summary(transcript_rows)

    if not result:
        logger.warning("post_call: empty result for call %s — skipping write", call_id)
        return

    # Reconcile extraction → update travel_leads if we found structured data
    lead_patch: dict = {}
    if result.get("destination") and call.get("lead_id"):
        lead_patch["destination_hint"] = result["destination"]
    if result.get("budget_inr") and call.get("lead_id"):
        lead_patch["budget_inr"] = result["budget_inr"]
    if result.get("duration_days") and call.get("lead_id"):
        lead_patch["duration_days"] = result["duration_days"]
    if result.get("pax_count") and call.get("lead_id"):
        lead_patch["pax_count"] = result["pax_count"]
    if result.get("lead_score") and call.get("lead_id"):
        lead_patch["score"] = result["lead_score"]
        # Upgrade qualification based on outcome
        outcome_to_qual = {
            "interested": "warm", "booked": "converted",
            "escalated": "hot", "not_interested": "cold",
        }
        qual = outcome_to_qual.get(result.get("outcome", ""), None)
        if qual:
            lead_patch["qualification"] = qual

    if lead_patch and call.get("lead_id"):
        db.table("travel_leads").update(lead_patch).eq("id", call["lead_id"]).eq(
            "business_id", business_id).execute()
        logger.info("post_call: updated travel_leads %s with %s", call["lead_id"], list(lead_patch))

    # Write summary + final sentiment to travel_calls.
    # `.get(key, default)` does not apply the default when the key is present
    # and null, which Claude's JSON can be — so coerce explicitly. Otherwise
    # `None / 100.0` raised a TypeError here, after travel_leads had already
    # been patched above and before the summary landed, leaving the row mutated
    # with no idempotency guard set.
    lead_score = result.get("lead_score") or 40
    summary_text = result.get("summary") or "(no summary produced)"
    # sentiment_score is NUMERIC(4,3) — round to 3, not 4, so Postgres stores
    # exactly what we computed instead of silently re-rounding.
    final_sentiment = round(lead_score / 100.0, 3)
    db.table("travel_calls").update({
        "summary": summary_text,
        "sentiment_score": final_sentiment,
    }).eq("id", call_id).execute()

    # Log event
    db.table("travel_call_events").insert({
        "call_id": call_id,
        "event_type": "post_call_complete",
        "payload": {
            "outcome": result.get("outcome"),
            "lead_score": result.get("lead_score"),
            "follow_up_action": result.get("follow_up_action"),
            "model": "claude-sonnet-4-6" if settings.ANTHROPIC_API_KEY else "stub",
        },
    }).execute()

    logger.info("post_call: completed for call=%s outcome=%s lead_score=%s",
                call_id, result.get("outcome"), result.get("lead_score"))


def schedule(call_id: str, business_id: str) -> None:
    """Fire-and-forget post-call pipeline — called from the 'stop' event handler."""
    background.spawn(
        run_pipeline(call_id, business_id),
        label=f"post_call call={call_id}",
    )
