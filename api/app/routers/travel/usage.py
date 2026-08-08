"""
Cost & usage analytics endpoints (Phase 4 T9).

GET /analytics/cost?period=&branch=    → manager+ , business-scoped
GET /analytics/cost/rate-card          → manager+ , the estimation model itself

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

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import require_role
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
