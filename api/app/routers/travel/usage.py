"""
Cost & usage analytics endpoints (Phase 4 T9) + the multi-currency revenue
rollup (Phase 4 T8).

GET /analytics/cost?period=&branch=            → manager+ , business-scoped
GET /analytics/cost/rate-card                  → manager+ , the estimation model itself
GET /analytics/revenue-rollup?period=&branch=  → manager+ , business-scoped

╔══════════════════════════════════════════════════════════════════════╗
║  READ THIS BEFORE PUTTING THESE NUMBERS IN FRONT OF ANYONE           ║
║                                                                      ║
║  Every figure returned here is an ESTIMATE, not a measurement.       ║
║  Phase 2B never ran: no provider usage or billing API is integrated, ║
║  so nothing in this system has ever recorded real metered spend.     ║
║                                                                      ║
║  The response therefore carries, at three levels:                    ║
║    * per line item : `is_estimated` (bool) and `cost_basis`          ║
║                      ("ESTIMATED" | "METERED")                       ║
║    * per report    : `cost_basis`, `all_estimated`, `disclaimer`     ║
║    * per summary   : `estimated` and `metered` totals kept SEPARATE  ║
║                      and never summed into one headline number       ║
║                                                                      ║
║  Any UI rendering this MUST surface the estimated label next to the  ║
║  number. Presenting an estimate as measured spend is a financial     ║
║  misrepresentation, not a formatting choice.                         ║
╚══════════════════════════════════════════════════════════════════════╝

Cost data is financial, so the gate is manager+ (agents do not see it).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import require_role
from app.database import get_supabase_admin
from app.services.travel.fx_service import (
    DEFAULT_QUOTE_CURRENCY,
    rollup_to_quote_currency,
)
from app.services.travel.usage_service import (
    LLM_USD_PER_1K_INPUT,
    LLM_USD_PER_1K_OUTPUT,
    PER_MINUTE_TARGET_USD,
    RATE_CARD_VERSION,
    STT_USD_PER_SECOND,
    TELEPHONY_USD_PER_SECOND,
    TTS_USD_PER_1K_CHARS,
    UsageService,
    estimate_per_minute,
    resolve_period,
)

router = APIRouter()

_MANAGER_PLUS = require_role("manager")
_UNSCOPED_ROLES = {"admin", "super_admin"}


@router.get("/cost")
def get_cost_report(
    period: str            = Query(default="30d", description="'today', 'mtd', or '<N>d' e.g. 7d/30d/90d"),
    branch: Optional[UUID] = Query(default=None),
    limit:  int            = Query(default=5000, ge=1, le=20000),
    user: dict = Depends(_MANAGER_PLUS),
):
    """Cost report. EVERY line item carries its own `is_estimated` flag."""
    own_branch = user.get("branch_id")
    if own_branch and user.get("role") not in _UNSCOPED_ROLES:
        branch = UUID(own_branch)

    try:
        return UsageService().cost_report(
            UUID(user["business_id"]), period=period, branch_id=branch, limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/cost/rate-card")
def get_rate_card(user: dict = Depends(_MANAGER_PLUS)):
    """The estimation model, in the open — formula, rates, and provenance.

    `per_minute_model` shows what the formula predicts for one modelled
    conversational minute, next to the architecture-doc targets. That
    comparison is model-vs-goal; it is not evidence about real spend.
    """
    return {
        "rate_card_version": RATE_CARD_VERSION,
        "formula": (
            "cost_usd = stt_seconds*STT_USD_PER_SECOND[engine] "
            "+ (llm_input_tokens/1000)*LLM_USD_PER_1K_INPUT[model] "
            "+ (llm_output_tokens/1000)*LLM_USD_PER_1K_OUTPUT[model] "
            "+ (tts_characters/1000)*TTS_USD_PER_1K_CHARS[engine] "
            "+ telephony_seconds*TELEPHONY_USD_PER_SECOND[provider]"
        ),
        "rates_usd": {
            "stt_per_second":        {k: str(v) for k, v in STT_USD_PER_SECOND.items()},
            "llm_per_1k_input":      {k: str(v) for k, v in LLM_USD_PER_1K_INPUT.items()},
            "llm_per_1k_output":     {k: str(v) for k, v in LLM_USD_PER_1K_OUTPUT.items()},
            "tts_per_1k_characters": {k: str(v) for k, v in TTS_USD_PER_1K_CHARS.items()},
            "telephony_per_second":  {k: str(v) for k, v in TELEPHONY_USD_PER_SECOND.items()},
        },
        "targets_usd_per_min": {
            k: {"low": str(v[0]), "high": str(v[1])}
            for k, v in PER_MINUTE_TARGET_USD.items()
        },
        "per_minute_model": {
            "en": _stringify(estimate_per_minute(
                language="en", stt_engine="deepgram", tts_engine="elevenlabs")),
            "te": _stringify(estimate_per_minute(
                language="te", stt_engine="sarvam", tts_engine="sarvam")),
        },
        "provenance": (
            "ASSUMED PUBLIC LIST PRICES, hand-entered as modelling inputs. "
            "Not contracted rates, not read from any provider API, not "
            "reconciled against an invoice. Telephony is modelled per second "
            "though real billing uses 6s/60s increments, which under-states "
            "short calls."
        ),
        "all_estimated": True,
        "disclaimer": (
            "This is an estimation model. No real provider usage has ever "
            "been logged in this system (Phase 2B never ran), so no cost "
            "produced from this card has been measured or billed."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# Phase 4 T8 — multi-currency revenue rollup
# ══════════════════════════════════════════════════════════════════════════
#
# GET /analytics/revenue-rollup?period=&branch=
#
# Sums paid payment_links across currencies into INR. The conversion rule is
# non-negotiable and lives in app/services/travel/fx_service.py (pure, no DB,
# no clock): every row is converted with the fx_rate_snapshots rate in effect
# at THAT ROW'S OWN created_at, resolved exactly the way migration 0015's
# public.fx_rate_at() resolves it. Nothing here reads a live rate, so July's
# number re-run in September is byte-identical to July's number.
#
# DEBT-11 is answered here rather than papered over: when no snapshot precedes
# a payment, fx_rate_at() returns NULL by design (forward-filling would
# fabricate history). That row is NOT dropped and NOT counted as zero — it
# lands in `unconvertible` with its id, currency, native amount and reason,
# and the payload's top level says `complete: false` / `total_is_partial: true`.
#
# SCHEMA NOTE — payment_links has NO branch_id column (migration 0010). Branch
# attribution is therefore DERIVED from created_by -> ts_users.branch_id, and
# rows with no attributable creator are reported in `branch_attribution`
# instead of vanishing from a branch-filtered report. See the endpoint body.

_PAYMENTS_TABLE = "payment_links"
_FX_TABLE = "fx_rate_snapshots"
_PAID_STATUS = "paid"


def _assert_branch_in_business(db, branch_id: UUID, business_id: str) -> None:
    """Out-of-scope branch → 404, never 403 (never leak existence)."""
    rows = (
        db.table("branches").select("id")
        .eq("id", str(branch_id)).eq("business_id", business_id)
        .limit(1).execute().data
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")


@router.get("/revenue-rollup")
def get_revenue_rollup(
    period: str            = Query(default="30d", description="'today', 'mtd', or '<N>d' e.g. 7d/30d/90d"),
    branch: Optional[UUID] = Query(default=None),
    limit:  int            = Query(default=5000, ge=1, le=20000),
    user: dict = Depends(_MANAGER_PLUS),
):
    """Multi-currency paid-revenue rollup, converted to INR point-in-time.

    Financial data → manager+ (`require_role("manager")`), scoped to
    `business_id`. An out-of-scope `branch` returns 404, never 403.

    The returned `total` covers ONLY the rows that had a resolvable
    historical rate. Read `complete` before reading `total`.
    """
    own_branch = user.get("branch_id")
    if own_branch and user.get("role") not in _UNSCOPED_ROLES:
        branch = UUID(own_branch)

    business_id = str(user["business_id"])
    db = get_supabase_admin()

    if branch is not None:
        _assert_branch_in_business(db, branch, business_id)

    try:
        start, end = resolve_period(period, datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    rows = (
        db.table(_PAYMENTS_TABLE)
        .select("id,amount,currency,created_at,lead_id,package_id,created_by,gateway")
        .eq("business_id", business_id)
        .eq("status", _PAID_STATUS)
        .gte("created_at", start.isoformat())
        .lte("created_at", end.isoformat())
        .order("created_at", desc=True)
        .limit(limit)
        .execute().data
    ) or []

    # ── Branch attribution (derived — payment_links has no branch_id) ──────
    branch_attribution: dict = {
        "requested_branch_id": str(branch) if branch else None,
        "derivation": "payment_links.created_by -> ts_users.branch_id",
        "schema_note": (
            "payment_links carries no branch_id column (migration 0010), so a "
            "branch-filtered rollup is derived from the link creator's branch, "
            "not stored on the payment itself."
        ),
        "excluded_unattributable_rows": 0,
        "excluded_unattributable_ids": [],
    }
    if branch is not None:
        member_ids = {
            str(u["id"])
            for u in (
                db.table("ts_users").select("id")
                .eq("business_id", business_id).eq("branch_id", str(branch))
                .execute().data or []
            )
        }
        kept, dropped = [], []
        for row in rows:
            creator = row.get("created_by")
            if creator is not None and str(creator) in member_ids:
                kept.append(row)
            else:
                dropped.append(row)
        rows = kept
        branch_attribution["excluded_unattributable_rows"] = len(dropped)
        branch_attribution["excluded_unattributable_ids"] = [
            str(r.get("id")) for r in dropped
        ]

    # ── Snapshots: everything captured at or before the window end, for the
    # currencies actually present. Deliberately NOT limited to the window's
    # start — the rate in effect at a payment may have been captured long
    # before it, and clipping the lower bound would manufacture a NULL.
    bases = sorted({
        (str(r.get("currency") or DEFAULT_QUOTE_CURRENCY)).strip().upper()
        for r in rows
    } - {DEFAULT_QUOTE_CURRENCY})

    snapshots: list[dict] = []
    if bases:
        snapshots = (
            db.table(_FX_TABLE)
            .select("base_currency,quote_currency,rate,captured_at")
            .eq("quote_currency", DEFAULT_QUOTE_CURRENCY)
            .in_("base_currency", bases)
            .lte("captured_at", end.isoformat())
            .order("captured_at", desc=False)
            .execute().data
        ) or []

    # ── The rule itself lives in the pure function. ────────────────────────
    rollup = rollup_to_quote_currency(
        rows, snapshots,
        quote_currency=DEFAULT_QUOTE_CURRENCY,
        timestamp_field="created_at",
    )

    return {
        "period": {"token": period or "30d",
                   "start": start.isoformat(), "end": end.isoformat()},
        "branch_id": str(branch) if branch else None,
        "status_filter": _PAID_STATUS,
        **rollup,
        "branch_attribution": branch_attribution,
        "fx": {
            "resolver": "public.fx_rate_at(base, quote, at) — mirrored in "
                        "app/services/travel/fx_service.py",
            "snapshots_considered": len(snapshots),
            "forward_fill": False,
            "live_rate_used": False,
            "determinism": (
                "Re-running this endpoint with the same explicit window returns "
                "byte-identical figures: every conversion is pinned to the "
                "payment's own created_at, never to the request time. (A "
                "relative ?period= token such as '30d' moves the WINDOW with "
                "the clock — the conversion of any row inside it does not.)"
            ),
        },
    }


def _stringify(payload: dict) -> dict:
    """Decimals → strings so the JSON encoder never silently floats money."""
    out = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            out[key] = {k: str(v) for k, v in value.items()}
        elif isinstance(value, bool) or value is None:
            out[key] = value
        else:
            out[key] = str(value)
    return out
