"""Phase 3 T3/T4 MOCK/OFFLINE keyword scorers — no ANTHROPIC_API_KEY needed.

These are the fallback code paths that run for every real call until
Claude enhancement is verified live (see BLOCKERS.md B-P3-02/B-P3-03).
"""
from __future__ import annotations


def test_sentiment_scorer_directional_signal():
    from app.services.travel.sentiment_service import score_text

    excited = score_text("This sounds amazing, we are so excited for our honeymoon trip!")
    hesitant = score_text("Actually I am not sure, maybe later, just checking prices for now")
    assert excited["excitement"] > hesitant["excitement"]

    booking = score_text("We want to book this Goa trip, how do I pay, send me the payment link")
    browsing = score_text("just checking, not ready yet")
    assert booking["intent"] > browsing["intent"]

    price_sensitive = score_text("that sounds expensive, is there a discount or cheaper option")
    price_neutral = score_text("sounds wonderful, tell me more")
    assert price_sensitive["price_sensitivity"] > price_neutral["price_sensitivity"]

    for scores in (excited, hesitant, booking, browsing, price_sensitive, price_neutral):
        for v in scores.values():
            assert 0.0 <= v <= 1.0


def test_keyword_suggestion_matches_known_intents():
    from app.services.travel.suggestion_service import _keyword_suggestion

    assert "affordable" in _keyword_suggestion(
        "I am looking for a budget-friendly package, cost is a concern", []
    ).lower()
    assert "refund" in _keyword_suggestion(
        "What about cancellation, can I get a refund if we cancel later?", []
    ).lower()
    assert "honeymoon" in _keyword_suggestion(
        "This sounds amazing, we are so excited for our honeymoon trip!", []
    ).lower()
    assert _keyword_suggestion("hello there, nice weather today", []) is None


def test_post_call_stub_summary_never_crashes_on_empty_or_minimal_transcript():
    from app.services.travel.post_call_service import _stub_summary

    result = _stub_summary([])
    assert result["outcome"] == "unclear"
    assert isinstance(result["lead_score"], int)

    result2 = _stub_summary([{"speaker": "customer", "text_original": "hi"}])
    assert "hi" in result2["summary"]
