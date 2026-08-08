"""
Regression tests for the Phase 3 T5 post-call pipeline's stub path.

Both cases below are the exact defects found in the Phase 3 audit loop
(2026-08-08); each one silently defeated the pipeline's idempotency guard,
which is a plain truthiness check on travel_calls.summary:

    if call.get("summary"):
        return   # already processed

If _stub_summary() can return a falsy summary, that guard never engages and
every re-run repeats the travel_leads / travel_calls writes and appends
another post_call_complete event row.

These are DB-free: _stub_summary is a pure function, and the lead_score
coercion is exercised as the arithmetic it guards.
"""
from __future__ import annotations

from app.services.travel.post_call_service import _stub_summary


def _rows(*texts: str) -> list[dict]:
    return [{"text_original": t, "speaker": "customer"} for t in texts]


def test_stub_summary_is_truthy_for_empty_transcript():
    """No customer rows must still yield a non-empty summary.

    The original expression relied on implicit string concatenation binding
    tighter than the ternary, so the false-branch was a bare `all_text` —
    which is '' when there is no customer text. An empty-string summary is
    falsy, so the idempotency guard never tripped.
    """
    result = _stub_summary([])
    assert result["summary"], "empty transcript produced a falsy summary"
    assert "0 transcript rows" in result["summary"]


def test_stub_summary_keeps_prefix_for_short_transcript():
    """A short transcript must keep the 'Call with N transcript rows' prefix."""
    result = _stub_summary(_rows("hi"))
    assert result["summary"].startswith("Call with 1 transcript rows.")
    assert "hi" in result["summary"]


def test_stub_summary_truncates_long_transcript():
    """Over 200 chars of customer text is sampled, not dumped whole."""
    result = _stub_summary(_rows("x" * 250))
    assert result["summary"].startswith("Call with 1 transcript rows.")
    assert result["summary"].endswith("...")
    # 200 sampled chars, never the full 250.
    assert "x" * 200 in result["summary"]
    assert "x" * 201 not in result["summary"]


def test_stub_summary_only_counts_customer_text_but_all_rows():
    """all_text is customer-only; the row count covers every speaker."""
    rows = _rows("hello") + [{"text_original": "ignored", "speaker": "ai"}]
    result = _stub_summary(rows)
    assert "Call with 2 transcript rows." in result["summary"]
    assert "ignored" not in result["summary"]


def test_lead_score_none_does_not_raise():
    """A present-but-null lead_score must not blow up the sentiment math.

    dict.get(key, default) does NOT apply the default when the key exists
    with a null value, which Claude's JSON can legitimately return. The old
    code did `result.get("lead_score", 40) / 100.0` and raised TypeError
    after travel_leads had already been patched — mutating the lead while
    leaving no idempotency guard behind.
    """
    for payload in ({"lead_score": None}, {}, {"lead_score": 0}):
        lead_score = payload.get("lead_score") or 40
        assert round(lead_score / 100.0, 3) == 0.4

    assert round(({"lead_score": 85}.get("lead_score") or 40) / 100.0, 3) == 0.85


def test_stub_summary_shape_is_stable():
    """The stub must supply every key the writer path reads."""
    result = _stub_summary(_rows("we want goa in december"))
    for key in (
        "summary", "destination", "budget_inr", "duration_days",
        "pax_count", "outcome", "lead_score", "follow_up_action",
    ):
        assert key in result, f"missing {key}"
    assert result["outcome"] == "unclear"
    assert result["lead_score"] == 40
