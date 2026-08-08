"""
Regression tests for DEBT-09 — substring false positives in the keyword scorers.

Both offline scorers matched bare substrings, which produced wrong output on
ordinary utterances:

  * sentiment: the price-sensitivity term `"k "` (meant to catch the "50k"
    shorthand) also matched "boo[k ]this" and "thin[k ]about", so a pure
    buying-intent line scored as price-sensitive.
  * suggestions: the month rule's `"may"` matched "maybe", so an utterance with
    no timing content produced "Timing mentioned — confirm availability".

These matter more than they look: offline mode is the ONLY mode running today
(no ANTHROPIC_API_KEY anywhere), so these scores are the entire signal a
supervisor sees.

Both scorers now match on word boundaries via sentiment_service._matches.
"""
from __future__ import annotations

from app.services.travel.sentiment_service import score_text
from app.services.travel.suggestion_service import _keyword_suggestion

# The scorer rounds to 3dp, so compare against rounded literals rather than
# float arithmetic: 0.3 + 0.15 is 0.44999999999999996, not 0.45.
_PRICE_BASE = 0.3
_ONE_HIT = 0.45
_TWO_HITS = 0.6


def _price(text: str) -> float:
    return score_text(text)["price_sensitivity"]


# ── sentiment: false positives must not elevate price sensitivity ──────────

def test_book_this_is_not_price_sensitive():
    """'book this' contains 'k ' — it must not read as price talk."""
    assert _price("We want to book this Goa trip, send me the payment link") == _PRICE_BASE


def test_think_about_it_is_not_price_sensitive():
    """'think about' also contains 'k '."""
    assert _price("I will think about it") == _PRICE_BASE


def test_neutral_utterance_stays_at_base():
    assert _price("sounds wonderful, tell me more") == _PRICE_BASE


# ── sentiment: real price talk must still be detected ──────────────────────

def test_amount_shorthand_still_detected():
    """The '50k' shorthand the 'k ' term existed for must still fire."""
    assert _price("can you do it for 50k?") == _ONE_HIT
    assert _price("budget is around 50 k") > _PRICE_BASE


def test_explicit_price_words_still_detected():
    assert _price("what is the price for 3 nights") == _ONE_HIT
    # two distinct terms -> two increments
    assert _price("that is too expensive, any discount?") == _TWO_HITS


def test_buying_intent_scores_high_on_intent_dimension():
    """The line that used to be mis-scored is, correctly, high intent."""
    assert score_text("We want to book this, send me the payment link")["intent"] >= 0.8


# ── suggestions: month rule must not fire on 'maybe' ───────────────────────

def test_maybe_does_not_trigger_timing_suggestion():
    assert _keyword_suggestion("maybe next year", []) is None


def test_marching_does_not_trigger_timing_suggestion():
    assert _keyword_suggestion("we saw a marching band", []) is None


def test_real_month_still_triggers_timing_suggestion():
    out = _keyword_suggestion("we want to travel in May", [])
    assert out is not None and "Timing" in out


def test_other_rules_still_fire():
    out = _keyword_suggestion("travelling with kids", [])
    assert out is not None and "family" in out.lower()


def test_cancellation_variants_match():
    """'cancelling' was previously unreachable — the list had 'cancel' twice."""
    for phrasing in ("I want a refund", "thinking of cancelling", "cancellation policy?"):
        out = _keyword_suggestion(phrasing, [])
        assert out is not None and "cancellation" in out.lower(), phrasing
