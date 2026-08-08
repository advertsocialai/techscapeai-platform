"""
Offline proofs for app/services/travel/fx_service.py (Phase 4 T8).

No database, no network, no credentials — in-memory fixtures only.

Two things are proven here, and they are the two things the task exists for:

  1. DETERMINISM — the same fixtures produce byte-identical output no matter
     what "now" is when the report runs, because conversion is pinned to each
     payment's own timestamp.
  2. LOUD FAILURE ON A MISSING RATE (DEBT-11) — a payment that predates every
     snapshot for its pair is neither silently dropped from the total nor
     counted as zero.

NOTE ON LOCATION: this file lives in the session scratchpad rather than
api/tests/ because the task that produced it granted write access to exactly
three repo files. Move it to api/tests/test_fx_rollup_offline.py verbatim —
it imports only from app.services.travel.fx_service and needs no fixtures,
no conftest and no environment.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, "/home/user/techscapeai-platform/api")

# fx_service imports nothing from the app, but `app.services.__init__` pulls in
# modules that build pydantic settings at import time. Same fixture values as
# api/tests/conftest.py — non-real, never dialled. Delete these five lines when
# this file moves into api/tests/, where conftest.py already does it.

from app.services.travel.fx_service import (  # noqa: E402
    REASON_NO_SNAPSHOT,
    build_snapshot_index,
    resolve_rate_at,
    rollup_to_quote_currency,
)

UTC = timezone.utc

# ── Fixtures ──────────────────────────────────────────────────────────────
# Two USD→INR observations. Nothing before 2026-06-01.
SNAPSHOTS = [
    {"base_currency": "USD", "quote_currency": "INR",
     "rate": "83.00000000", "captured_at": "2026-06-01T00:00:00+00:00"},
    {"base_currency": "USD", "quote_currency": "INR",
     "rate": "90.00000000", "captured_at": "2026-07-01T00:00:00+00:00"},
    {"base_currency": "AED", "quote_currency": "INR",
     "rate": "22.50000000", "captured_at": "2026-06-15T00:00:00+00:00"},
]

PAYMENTS = [
    # Native INR — identity, needs no snapshot at all.
    {"id": "11111111-1111-1111-1111-111111111111", "amount": "50000.00",
     "currency": "INR", "created_at": "2026-06-10T09:00:00+00:00"},
    # USD paid in June → must use the 83.00 rate, NOT the later 90.00.
    {"id": "22222222-2222-2222-2222-222222222222", "amount": "100.00",
     "currency": "USD", "created_at": "2026-06-10T09:00:00+00:00"},
    # USD paid in July → must use the 90.00 rate.
    {"id": "33333333-3333-3333-3333-333333333333", "amount": "100.00",
     "currency": "USD", "created_at": "2026-07-05T09:00:00+00:00"},
    # AED after its snapshot.
    {"id": "44444444-4444-4444-4444-444444444444", "amount": "1000.00",
     "currency": "AED", "created_at": "2026-06-20T09:00:00+00:00"},
]

# A payment that PREDATES every USD snapshot. fx_rate_at() returns NULL here.
PRE_SNAPSHOT_PAYMENT = {
    "id": "99999999-9999-9999-9999-999999999999", "amount": "777.00",
    "currency": "USD", "created_at": "2026-01-15T09:00:00+00:00",
}


# ── 1. Point-in-time resolution ───────────────────────────────────────────

def test_resolver_picks_the_rate_in_effect_not_the_newest():
    idx = build_snapshot_index(SNAPSHOTS)
    june = datetime(2026, 6, 10, tzinfo=UTC)
    july = datetime(2026, 7, 5, tzinfo=UTC)
    assert resolve_rate_at(idx, "USD", "INR", june) == Decimal("83.00000000")
    assert resolve_rate_at(idx, "USD", "INR", july) == Decimal("90.00000000")


def test_resolver_boundary_is_inclusive_at_or_before():
    idx = build_snapshot_index(SNAPSHOTS)
    exactly = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    a_microsecond_before = exactly - timedelta(microseconds=1)
    assert resolve_rate_at(idx, "USD", "INR", exactly) == Decimal("90.00000000")
    assert resolve_rate_at(idx, "USD", "INR", a_microsecond_before) == Decimal("83.00000000")


def test_resolver_returns_none_and_never_forward_fills():
    idx = build_snapshot_index(SNAPSHOTS)
    before_everything = datetime(2026, 1, 15, tzinfo=UTC)
    assert resolve_rate_at(idx, "USD", "INR", before_everything) is None


def test_identity_pair_is_one_without_a_snapshot():
    assert resolve_rate_at({}, "INR", "INR", datetime(2026, 6, 1, tzinfo=UTC)) == Decimal(1)


# ── 2. DETERMINISM — the whole point ──────────────────────────────────────

def test_rollup_is_byte_identical_across_two_different_nows():
    """Same rows, same snapshots, two wildly different 'report run' moments.

    The pure function takes no clock at all, which is the mechanical reason
    this holds: there is no input through which "now" could leak in.
    """
    first_run_now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    second_run_now = first_run_now + timedelta(days=400)

    # The only thing "now" is allowed to influence is the WINDOW, and here
    # the window is fixed — the same rows go in both times.
    a = rollup_to_quote_currency(PAYMENTS, SNAPSHOTS)
    b = rollup_to_quote_currency(PAYMENTS, SNAPSHOTS)

    dump_a = json.dumps(a, sort_keys=True)
    dump_b = json.dumps(b, sort_keys=True)
    assert dump_a == dump_b, "rollup drifted between runs"
    assert dump_a.encode() == dump_b.encode()

    # And the number is the point-in-time one:
    #   50000 + (100*83) + (100*90) + (1000*22.5) = 89800
    assert a["total"] == "89800.00"
    assert a["complete"] is True
    assert a["rows_converted"] == 4

    print(f"\n  run@{first_run_now.isoformat()}  total={a['total']} INR")
    print(f"  run@{second_run_now.isoformat()}  total={b['total']} INR")
    print(f"  byte-identical: {dump_a.encode() == dump_b.encode()}")


def test_a_newer_snapshot_appearing_later_does_not_restate_the_past():
    """The books stay closed even after new rates are captured.

    This is the failure mode a live-rate rollup has: capture tomorrow's rate,
    and yesterday's report changes. Here it cannot.
    """
    before = rollup_to_quote_currency(PAYMENTS, SNAPSHOTS)
    later_snapshots = SNAPSHOTS + [
        {"base_currency": "USD", "quote_currency": "INR",
         "rate": "120.00000000", "captured_at": "2026-12-31T00:00:00+00:00"},
    ]
    after = rollup_to_quote_currency(PAYMENTS, later_snapshots)
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
    print(f"\n  total before new snapshot: {before['total']}")
    print(f"  total after  new snapshot: {after['total']}  (unchanged)")


# ── 3. DEBT-11 — an unresolvable row must be LOUD ─────────────────────────

def test_pre_snapshot_payment_is_not_silently_omitted():
    rows = PAYMENTS + [PRE_SNAPSHOT_PAYMENT]
    out = rollup_to_quote_currency(rows, SNAPSHOTS)

    # It is accounted for: every input row is on one side of the ledger.
    assert out["rows_in"] == 5
    assert out["rows_converted"] + out["rows_unconvertible"] == out["rows_in"]

    # It is NOT in the total (that would be a fabricated rate) ...
    assert out["total"] == "89800.00"
    # ... and it is NOT counted as zero — the payload refuses to look complete.
    assert out["complete"] is False
    assert out["total_is_partial"] is True
    assert "PARTIAL TOTAL" in out["total_note"]

    # It is named, with enough detail to fix it.
    ids = [i["id"] for i in out["unconvertible"]["items"]]
    assert PRE_SNAPSHOT_PAYMENT["id"] in ids
    item = next(i for i in out["unconvertible"]["items"]
                if i["id"] == PRE_SNAPSHOT_PAYMENT["id"])
    assert item["currency"] == "USD"
    assert item["amount"] == "777.00"
    assert item["reason"] == REASON_NO_SNAPSHOT
    assert out["unconvertible"]["currencies"] == ["USD"]
    assert out["unconvertible"]["by_currency"][0]["native_amount"] == "777.00"

    print("\n  unconvertible bucket:")
    print("  " + json.dumps({
        "complete": out["complete"],
        "total_is_partial": out["total_is_partial"],
        "total": out["total"],
        "rows_in": out["rows_in"],
        "rows_converted": out["rows_converted"],
        "rows_unconvertible": out["rows_unconvertible"],
        "unconvertible": {k: out["unconvertible"][k]
                          for k in ("rows", "currencies", "by_currency", "items")},
    }, indent=2).replace("\n", "\n  "))


def test_unconvertible_row_is_not_counted_as_zero():
    """Distinguish 'excluded and flagged' from 'included as 0.00'.

    A zero-counted row would leave complete=True and rows_converted=5, which
    is exactly the silent corruption DEBT-11 warns about.
    """
    with_gap = rollup_to_quote_currency(PAYMENTS + [PRE_SNAPSHOT_PAYMENT], SNAPSHOTS)
    without = rollup_to_quote_currency(PAYMENTS, SNAPSHOTS)
    assert with_gap["total"] == without["total"]       # not summed in
    assert with_gap["complete"] is False               # but not pretended away
    assert without["complete"] is True
    assert with_gap["rows_converted"] == without["rows_converted"] == 4


def test_backfilling_the_missing_snapshot_makes_it_complete():
    fixed = SNAPSHOTS + [
        {"base_currency": "USD", "quote_currency": "INR",
         "rate": "80.00000000", "captured_at": "2026-01-01T00:00:00+00:00"},
    ]
    out = rollup_to_quote_currency(PAYMENTS + [PRE_SNAPSHOT_PAYMENT], fixed)
    assert out["complete"] is True
    assert out["rows_unconvertible"] == 0
    # 89800.00 + 777*80 = 89800 + 62160
    assert out["total"] == "151960.00"


# ── 4. Money handling ─────────────────────────────────────────────────────

def test_conversion_uses_decimal_not_float():
    rows = [{"id": "a", "amount": "0.10", "currency": "USD",
             "created_at": "2026-06-02T00:00:00+00:00"}] * 3
    out = rollup_to_quote_currency(rows, SNAPSHOTS)
    assert out["total"] == "24.90"          # 3 * (0.10 * 83) exactly


def test_currency_case_is_normalised_like_fx_rate_at():
    rows = [{"id": "a", "amount": "1.00", "currency": "usd",
             "created_at": "2026-06-02T00:00:00+00:00"}]
    out = rollup_to_quote_currency(rows, SNAPSHOTS)
    assert out["complete"] is True
    assert out["total"] == "83.00"


def test_empty_input_is_complete_and_zero():
    out = rollup_to_quote_currency([], [])
    assert out["total"] == "0.00"
    assert out["complete"] is True
    assert out["rows_in"] == 0
