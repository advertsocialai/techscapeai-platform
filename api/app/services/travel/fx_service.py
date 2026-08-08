"""
Point-in-time FX conversion (Phase 4 T8) — PURE, no DB, no clock, no network.

╔══════════════════════════════════════════════════════════════════════════╗
║  THE ABSOLUTE RULE                                                       ║
║                                                                          ║
║  A financial row is converted with the FX snapshot that was in effect    ║
║  at THAT ROW'S OWN TIMESTAMP — never a live rate, never "today's" rate,  ║
║  never the newest snapshot available.                                    ║
║                                                                          ║
║  Consequence, and the whole reason this module exists: re-running the    ║
║  same report days or months later returns byte-identical numbers.        ║
║  A rollup that converts at read time silently restates closed books      ║
║  every time it is refreshed, and reconciliation against gateway          ║
║  settlements drifts forever after.                                       ║
║                                                                          ║
║  Nothing in this module reads the clock. `datetime.now()` does not       ║
║  appear here and must never be added — a function that cannot see        ║
║  "now" cannot accidentally convert at "now".                             ║
╚══════════════════════════════════════════════════════════════════════════╝

WHY THIS IS A PYTHON MIRROR OF A SQL FUNCTION
---------------------------------------------
Migration 0015 defines `public.fx_rate_at(base, quote, at)` (LANGUAGE sql,
STABLE) as the sanctioned resolver. `resolve_rate_at()` below implements
EXACTLY that contract against a list of snapshot rows:

    base = quote                  -> Decimal(1)      (identity, no lookup)
    newest snapshot captured_at <= at -> that snapshot's rate
    no snapshot captured_at <= at     -> None        (NO forward-fill)

Doing the resolution in Python rather than one `fx_rate_at()` RPC per row
keeps the rollup to two queries instead of O(rows) round trips, and — more
importantly — makes the rule unit-testable with in-memory fixtures on a
machine with no database. The two implementations must stay in lockstep:
if 0015's resolver ever changes, THIS FILE CHANGES IN THE SAME COMMIT.

DEBT-11, ANSWERED HERE
----------------------
`fx_rate_at()` deliberately returns NULL when no snapshot precedes the
timestamp, because forward-filling would fabricate history. Nothing in the
database forces a caller to notice that NULL. This module is that caller,
and it handles the NULL the only two acceptable ways:

  * an unconvertible row is NEVER dropped from the result, and
  * an unconvertible row is NEVER counted as zero.

It goes into an explicit `unconvertible` bucket carrying the row ids, the
currency, the native amount and a machine-readable reason, and the payload's
top level is marked `complete: false` / `total_is_partial: true` so a
consumer cannot read the total as a whole number by accident.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "DEFAULT_QUOTE_CURRENCY",
    "REASON_NO_SNAPSHOT",
    "REASON_BAD_TIMESTAMP",
    "REASON_BAD_AMOUNT",
    "build_snapshot_index",
    "resolve_rate_at",
    "convert_amount_at",
    "rollup_to_quote_currency",
    "parse_ts",
]

DEFAULT_QUOTE_CURRENCY = "INR"

#: Machine-readable reasons. Stable strings — clients may switch on them.
REASON_NO_SNAPSHOT = "no_fx_snapshot_at_or_before_row_timestamp"
REASON_BAD_TIMESTAMP = "row_timestamp_missing_or_unparseable"
REASON_BAD_AMOUNT = "row_amount_missing_or_unparseable"

_ONE = Decimal(1)
_CENTS = Decimal("0.01")


# ══════════════════════════════════════════════════════════════════════════
# Parsing helpers (pure)
# ══════════════════════════════════════════════════════════════════════════

def parse_ts(raw: Any) -> Optional[datetime]:
    """ISO-8601 string / datetime -> tz-aware UTC datetime. None if unusable.

    Naive input is *assumed* UTC, matching how TIMESTAMPTZ columns come back
    from PostgREST when a client strips the offset. Assuming rather than
    raising is safe here because the assumption is applied identically to
    payments and to snapshots, so the ordering between them is preserved.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _dec(raw: Any) -> Optional[Decimal]:
    """Money/rate -> Decimal. None if unusable. Never float arithmetic."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _ccy(raw: Any, default: str = "") -> str:
    text = (str(raw).strip().upper() if raw is not None else "")
    return text or default


# ══════════════════════════════════════════════════════════════════════════
# The resolver — a faithful mirror of 0015's public.fx_rate_at()
# ══════════════════════════════════════════════════════════════════════════

def build_snapshot_index(
    snapshots: Iterable[dict],
) -> dict[tuple[str, str], list[tuple[datetime, Decimal]]]:
    """Index snapshot rows by (base, quote), ascending by captured_at.

    Accepts raw `fx_rate_snapshots` rows (base_currency, quote_currency,
    rate, captured_at). Rows missing any of those, or carrying a
    non-positive rate, are skipped — the table's CHECK (rate > 0) makes
    them impossible in the database, so their presence means a caller
    hand-built a fixture wrong and a bad rate must not silently apply.
    """
    index: dict[tuple[str, str], list[tuple[datetime, Decimal]]] = {}
    for row in snapshots or []:
        base = _ccy(row.get("base_currency"))
        quote = _ccy(row.get("quote_currency"))
        rate = _dec(row.get("rate"))
        at = parse_ts(row.get("captured_at"))
        if not base or not quote or rate is None or at is None or rate <= 0:
            continue
        index.setdefault((base, quote), []).append((at, rate))
    for series in index.values():
        # Ties on captured_at cannot exist in the database (UNIQUE on
        # base/quote/captured_at), so ordering by the timestamp alone is
        # total and therefore deterministic.
        series.sort(key=lambda pair: pair[0])
    return index


def resolve_rate_at(
    index: dict[tuple[str, str], list[tuple[datetime, Decimal]]],
    base: str,
    quote: str,
    at: datetime,
) -> Optional[Decimal]:
    """The rate in effect at `at`: newest snapshot with captured_at <= at.

    Returns None when no snapshot precedes `at`. It does NOT fall back to
    the nearest later rate — see the module header. Identity pairs return
    exactly Decimal(1) with no lookup, matching fx_rate_at()'s CASE branch.
    """
    base_u, quote_u = _ccy(base), _ccy(quote)
    if base_u and base_u == quote_u:
        return _ONE
    series = index.get((base_u, quote_u))
    if not series:
        return None
    chosen: Optional[Decimal] = None
    for captured_at, rate in series:
        if captured_at <= at:
            chosen = rate          # ascending order -> last match is newest
        else:
            break
    return chosen


def convert_amount_at(
    index: dict[tuple[str, str], list[tuple[datetime, Decimal]]],
    amount: Decimal,
    base: str,
    quote: str,
    at: datetime,
) -> Optional[Decimal]:
    """amount in `base` -> `quote`, at `at`'s rate. None if unresolvable.

    Rounded HALF_UP to 2dp per row, not at the end: the per-row converted
    figure is what appears on the line item, and a total must equal the sum
    of the numbers printed beside it.
    """
    rate = resolve_rate_at(index, base, quote, at)
    if rate is None:
        return None
    return (amount * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)


# ══════════════════════════════════════════════════════════════════════════
# The rollup — PURE. Lists of dicts in, plain dict out.
# ══════════════════════════════════════════════════════════════════════════

def rollup_to_quote_currency(
    rows: Sequence[dict],
    snapshots: Sequence[dict],
    *,
    quote_currency: str = DEFAULT_QUOTE_CURRENCY,
    amount_field: str = "amount",
    currency_field: str = "currency",
    timestamp_field: str = "created_at",
    id_field: str = "id",
) -> dict:
    """Sum `rows` into `quote_currency` using each row's own point-in-time rate.

    PURE: no database, no clock, no I/O. Same inputs -> byte-identical output,
    which is exactly the determinism guarantee the books depend on. Feed it
    the same fixture rows a year apart and it cannot answer differently.

    `timestamp_field` defaults to `created_at` and should stay that way for
    payment_links: `created_at` is immutable, while `updated_at` moves on
    every later edit — converting at `updated_at` would let an unrelated row
    edit silently restate a closed period. Migration 0015's own sanctioned
    example converts at `created_at` for the same reason.

    Returns a payload whose top level is honest about incompleteness:

        complete          False as soon as ANY row could not be converted
        total_is_partial  the negation, stated positively so it is hard to skim past
        total             sum of the CONVERTED rows only — never includes a
                          zero standing in for a row that had no rate
        unconvertible     ids + currency + native amount + reason, per row,
                          plus a per-currency breakdown

    An unconvertible row is neither dropped nor zero-counted. That is the
    entire point (DEBT-11).
    """
    quote = _ccy(quote_currency, DEFAULT_QUOTE_CURRENCY)
    index = build_snapshot_index(snapshots)

    converted_items: list[dict] = []
    unconvertible_items: list[dict] = []
    total = Decimal("0.00")
    by_currency: dict[str, dict[str, Any]] = {}
    unconvertible_by_currency: dict[str, dict[str, Any]] = {}

    for row in rows or []:
        row_id = row.get(id_field)
        base = _ccy(row.get(currency_field), quote)
        amount = _dec(row.get(amount_field))
        at = parse_ts(row.get(timestamp_field))

        raw_amount = None if amount is None else str(amount)
        common = {
            "id": None if row_id is None else str(row_id),
            "currency": base,
            "amount": raw_amount,
            "at": row.get(timestamp_field),
        }

        if amount is None or at is None:
            reason = REASON_BAD_AMOUNT if amount is None else REASON_BAD_TIMESTAMP
            unconvertible_items.append({**common, "rate": None, "reason": reason})
            bucket = unconvertible_by_currency.setdefault(
                base, {"currency": base, "rows": 0, "native_amount": Decimal("0.00"),
                       "reasons": set()},
            )
            bucket["rows"] += 1
            if amount is not None:
                bucket["native_amount"] += amount
            bucket["reasons"].add(reason)
            continue

        rate = resolve_rate_at(index, base, quote, at)
        if rate is None:
            # DEBT-11 lands here. Loud bucket, never a silent drop or a zero.
            unconvertible_items.append(
                {**common, "rate": None, "reason": REASON_NO_SNAPSHOT}
            )
            bucket = unconvertible_by_currency.setdefault(
                base, {"currency": base, "rows": 0, "native_amount": Decimal("0.00"),
                       "reasons": set()},
            )
            bucket["rows"] += 1
            bucket["native_amount"] += amount
            bucket["reasons"].add(REASON_NO_SNAPSHOT)
            continue

        value = (amount * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)
        total += value
        converted_items.append({
            **common,
            "rate": str(rate),
            "rate_as_of": at.isoformat(),
            f"amount_{quote.lower()}": str(value),
        })
        agg = by_currency.setdefault(
            base, {"currency": base, "rows": 0, "native_amount": Decimal("0.00"),
                   "converted": Decimal("0.00")},
        )
        agg["rows"] += 1
        agg["native_amount"] += amount
        agg["converted"] += value

    unconvertible_count = len(unconvertible_items)
    complete = unconvertible_count == 0

    return {
        "quote_currency": quote,
        # ── Completeness, stated twice and first, so it cannot be skimmed past.
        "complete": complete,
        "total_is_partial": not complete,
        "total": str(total),
        "total_note": (
            f"Complete: every row converted at its own point-in-time rate."
            if complete else
            f"PARTIAL TOTAL — {unconvertible_count} row(s) had no FX snapshot at or "
            f"before their own timestamp and are EXCLUDED from this figure. They are "
            f"listed under `unconvertible`; they were not dropped and were not "
            f"counted as zero. Do not present this total as the period's revenue."
        ),
        "rows_in": len(rows or []),
        "rows_converted": len(converted_items),
        "rows_unconvertible": unconvertible_count,
        "by_currency": [
            {
                "currency": agg["currency"],
                "rows": agg["rows"],
                "native_amount": str(agg["native_amount"]),
                f"converted_{quote.lower()}": str(agg["converted"]),
            }
            for agg in sorted(by_currency.values(), key=lambda a: a["currency"])
        ],
        "unconvertible": {
            "rows": unconvertible_count,
            "currencies": sorted(unconvertible_by_currency),
            "by_currency": [
                {
                    "currency": bucket["currency"],
                    "rows": bucket["rows"],
                    "native_amount": str(bucket["native_amount"]),
                    "reasons": sorted(bucket["reasons"]),
                }
                for bucket in sorted(
                    unconvertible_by_currency.values(), key=lambda b: b["currency"]
                )
            ],
            "items": unconvertible_items,
            "remedy": (
                "Insert an fx_rate_snapshots row for the pair whose captured_at is at "
                "or before the listed payment timestamp, then re-run. Do NOT backfill "
                "with today's rate to make the gap disappear — fx_rate_at() refuses to "
                "forward-fill precisely so a fabricated historical rate never enters "
                "the books (migration 0015)."
            ),
        },
        "line_items": converted_items,
        "conversion_basis": (
            "POINT_IN_TIME — each row converted with the fx_rate_snapshots rate in "
            f"effect at its own {timestamp_field} (newest captured_at <= that "
            "timestamp), mirroring public.fx_rate_at(). No live or current rate is "
            "read anywhere in this computation, so a re-run is byte-identical."
        ),
        "timestamp_field": timestamp_field,
    }
