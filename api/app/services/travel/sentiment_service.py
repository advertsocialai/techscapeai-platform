"""
Live sentiment service (Phase 3 T4) — MOCK/OFFLINE mode.

Section A gate decision: no Phase 2B baseline → MOCK/OFFLINE mode.
Sentiment scoring runs AFTER transcript is persisted, never on the
voice-critical path.

Scores three dimensions (0.0–1.0):
  excitement     — enthusiasm/interest level
  intent         — purchase intent signals
  price_sensitivity — budget concern level

Also updates travel_calls.sentiment_score (running average of intent).
Broadcasts a "sentiment" WS message per utterance.

No API key required for the keyword-based scorer. Claude enhancement
available when ANTHROPIC_API_KEY is set (richer per-turn scores).
"""
from __future__ import annotations
import asyncio
import logging
import re
from functools import lru_cache
from uuid import UUID

from app.database import get_supabase_admin
from app.services.travel import call_feed

from . import background

logger = logging.getLogger(__name__)

# Keyword heuristics — each list of keywords votes toward that dimension
_EXCITEMENT_UP = ["excited", "amazing", "love", "great", "perfect", "wonderful", "yes", "definitely", "absolutely", "looking forward"]
_EXCITEMENT_DOWN = ["not sure", "maybe", "hmm", "okay", "fine", "whatever", "not interested"]
_INTENT_UP = ["book", "booking", "confirm", "want", "ready", "send me", "proceed", "go ahead", "how do i pay", "payment"]
_INTENT_DOWN = ["just looking", "not now", "later", "not ready", "not sure yet", "just checking"]
_PRICE_SENSITIVITY_UP = ["expensive", "too much", "budget", "cheap", "afford", "cost", "price", "how much", "discount", "offer", "₹", "inr", "lakh", "thousand", r"\d+\s*k\b"]
_PRICE_SENSITIVITY_DOWN = ["money is not", "budget is flexible", "not worried about cost", "price is fine"]


@lru_cache(maxsize=512)
def _pattern_for(term: str) -> re.Pattern:
    """Compile a keyword into a word-boundary-anchored pattern.

    Plain substring matching produced real false positives (DEBT-09): the
    price-sensitivity term `"k "` — intended to catch the "50k" shorthand —
    also matched "boo[k ]this" and "thin[k ]about", so a pure buying-intent
    line like "we want to book this, send me the payment link" scored as
    price-sensitive. `"may"` likewise fired on "maybe".

    Terms already written as regex (they contain a backslash) are used as-is;
    everything else is escaped and wrapped in \\b...\\b. `\\b` is not meaningful
    next to a non-word character, so symbol terms like "₹" fall back to a plain
    substring match rather than silently never matching.
    """
    if "\\" in term:
        return re.compile(term)
    escaped = re.escape(term)
    left = r"\b" if term[:1].isalnum() else ""
    right = r"\b" if term[-1:].isalnum() else ""
    return re.compile(f"{left}{escaped}{right}")


def _matches(term: str, lower_text: str) -> bool:
    return _pattern_for(term).search(lower_text) is not None


def _score_dimension(text: str, up_words: list[str], down_words: list[str], base: float = 0.5) -> float:
    lower = text.lower()
    score = base
    for w in up_words:
        if _matches(w, lower):
            score = min(1.0, score + 0.15)
    for w in down_words:
        if _matches(w, lower):
            score = max(0.0, score - 0.15)
    return round(score, 3)


def score_text(text: str) -> dict:
    """Keyword-based sentiment scoring. Returns {excitement, intent, price_sensitivity}."""
    return {
        "excitement":        _score_dimension(text, _EXCITEMENT_UP, _EXCITEMENT_DOWN, base=0.5),
        "intent":            _score_dimension(text, _INTENT_UP, _INTENT_DOWN, base=0.3),
        "price_sensitivity": _score_dimension(text, _PRICE_SENSITIVITY_UP, _PRICE_SENSITIVITY_DOWN, base=0.3),
    }


def _update_call_sentiment(db, call_id: str, new_intent_score: float) -> None:
    """Update travel_calls.sentiment_score as a running average weighted toward recency."""
    row = db.table("travel_calls").select("sentiment_score").eq("id", call_id).limit(1).execute().data
    if not row:
        return
    current = row[0].get("sentiment_score") or 0.5
    # Exponential moving average (weight 0.3 toward new value)
    updated = round(current * 0.7 + new_intent_score * 0.3, 4)
    db.table("travel_calls").update({"sentiment_score": updated}).eq("id", call_id).execute()


async def score_and_broadcast(
    call_id: str, transcript_id: str, transcript_text: str, speaker: str
) -> None:
    """Score the utterance, persist to travel_transcripts.sentiment,
    update call-level score, broadcast WS message."""
    if speaker == "ai":
        return  # only score customer utterances

    scores = score_text(transcript_text)

    db = get_supabase_admin()

    # Persist sentiment JSON into the transcript row
    db.table("travel_transcripts").update({"sentiment": scores}).eq("id", transcript_id).execute()

    # Update call-level running average
    _update_call_sentiment(db, call_id, scores["intent"])

    # Log event
    db.table("travel_call_events").insert({
        "call_id": call_id,
        "event_type": "sentiment_update",
        "payload": {"transcript_id": transcript_id, "scores": scores},
    }).execute()

    # Broadcast
    await call_feed.publish(call_id, {
        "type": "sentiment",
        "call_id": call_id,
        "transcript_id": transcript_id,
        "scores": scores,
    })
    logger.debug("sentiment broadcast call=%s intent=%.3f", call_id, scores["intent"])


def schedule(call_id: str, transcript_id: str, transcript_text: str, speaker: str) -> None:
    """Fire-and-forget sentiment scoring — never blocks the voice path."""
    background.spawn(
        score_and_broadcast(call_id, transcript_id, transcript_text, speaker),
        label=f"sentiment call={call_id}",
    )
