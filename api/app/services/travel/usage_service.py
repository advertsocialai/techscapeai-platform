"""
Cost & usage tracking (Phase 4 T9).

╔══════════════════════════════════════════════════════════════════════╗
║  FINANCIAL INTEGRITY — THE ONE RULE                                  ║
║                                                                      ║
║  EVERY COST THIS MODULE PRODUCES TODAY IS AN ESTIMATE.               ║
║                                                                      ║
║  Phase 2B (real provider usage logging) never ran. No provider       ║
║  usage or billing API is integrated. Nothing in this system has      ║
║  ever recorded a metered figure from Deepgram, Sarvam, Anthropic,    ║
║  ElevenLabs or Plivo, and no invoice has been reconciled. There is   ║
║  therefore NO code path here that can write is_estimated = FALSE,    ║
║  and none must be added until a provider usage API is actually       ║
║  wired up and checked against a bill.                                ║
║                                                                      ║
║  Consequently:                                                       ║
║   * record_usage() forces is_estimated = True and stamps the rate    ║
║     card version that produced the number.                           ║
║   * cost_report() carries is_estimated on EVERY line item, splits    ║
║     metered from estimated totals, and refuses to merge them into    ║
║     one headline figure.                                             ║
║   * An estimate is never labelled, formatted or summed as if it      ║
║     were measured.                                                   ║
╚══════════════════════════════════════════════════════════════════════╝

ESTIMATION FORMULA (explicit, per component — provider rate x unit):

    stt_cost        = stt_seconds        x STT_USD_PER_SECOND[stt_engine]
    llm_cost        = (llm_input_tokens  / 1000) x LLM_USD_PER_1K_INPUT[model]
                    + (llm_output_tokens / 1000) x LLM_USD_PER_1K_OUTPUT[model]
    tts_cost        = (tts_characters    / 1000) x TTS_USD_PER_1K_CHARS[tts_engine]
    telephony_cost  = telephony_seconds  x TELEPHONY_USD_PER_SECOND[provider]

    cost_usd        = stt + llm + tts + telephony      (rounded to 6 dp)

RATE PROVENANCE — read this before quoting any number downstream.
    The constants below are ASSUMED PUBLIC LIST PRICES, hand-entered as
    modelling inputs. They are NOT contracted rates, NOT read from any
    provider API, and NOT reconciled against an invoice. Actual spend will
    differ with negotiated pricing, tier discounts, minimum billing
    increments (most telephony bills per 6s or 60s, not per second),
    concurrency surcharges and currency conversion. Update RATE_CARD and
    bump RATE_CARD_VERSION together, never separately — old rows keep
    their version stamp so they stay interpretable after a re-price.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional
from uuid import UUID

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# RATE CARD — assumed list prices, USD. See RATE PROVENANCE above.
# ══════════════════════════════════════════════════════════════════════

#: Bump this whenever any rate below changes. Stamped onto every row.
RATE_CARD_VERSION = "2026-08-estimate-v1"

_D = Decimal

#: Speech-to-text, USD per second of audio.
#: Deepgram Nova streaming ~ $0.0059/min; Sarvam (Indic) ~ $0.0036/min.
STT_USD_PER_SECOND: dict[str, Decimal] = {
    "deepgram": _D("0.0059") / _D(60),
    "sarvam":   _D("0.0036") / _D(60),
    "whisper":  _D("0.0060") / _D(60),
    "other":    _D("0.0059") / _D(60),
}
DEFAULT_STT_ENGINE = "deepgram"

#: LLM, USD per 1000 tokens. Haiku-class assumption: $1/M in, $5/M out.
LLM_USD_PER_1K_INPUT: dict[str, Decimal] = {
    "haiku":  _D("0.001"),
    "sonnet": _D("0.003"),
    "other":  _D("0.001"),
}
LLM_USD_PER_1K_OUTPUT: dict[str, Decimal] = {
    "haiku":  _D("0.005"),
    "sonnet": _D("0.015"),
    "other":  _D("0.005"),
}
DEFAULT_LLM_MODEL = "haiku"

#: Text-to-speech, USD per 1000 characters.
#: ElevenLabs Turbo/Flash on a mid tier ~ $0.15/1k chars; Sarvam ~ $0.03/1k.
TTS_USD_PER_1K_CHARS: dict[str, Decimal] = {
    "elevenlabs": _D("0.15"),
    "sarvam":     _D("0.03"),
    "other":      _D("0.15"),
}
DEFAULT_TTS_ENGINE = "elevenlabs"

#: Telephony, USD per second. Plivo India inbound ~ $0.0085/min.
#: NOTE: real telephony bills in 6s or 60s increments — a per-second model
#: UNDER-states short calls. Another reason this is an estimate.
TELEPHONY_USD_PER_SECOND: dict[str, Decimal] = {
    "plivo":  _D("0.0085") / _D(60),
    "twilio": _D("0.0140") / _D(60),
    "other":  _D("0.0085") / _D(60),
}
DEFAULT_TELEPHONY_PROVIDER = "plivo"

#: Architecture-doc targets for comparison ONLY, USD per minute.
#: These are goals to measure against, not measurements.
PER_MINUTE_TARGET_USD: dict[str, tuple[Decimal, Decimal]] = {
    "en": (_D("0.08"), _D("0.15")),
    "te": (_D("0.04"), _D("0.07")),
}

#: A modelled "typical conversational minute" used by
#: estimate_per_minute() for the target-band comparison. These usage
#: volumes are ASSUMPTIONS too, not observed averages — Phase 2B never ran.
TYPICAL_MINUTE_PROFILE: dict[str, Any] = {
    "stt_seconds":       _D(60),
    "llm_input_tokens":  800,
    "llm_output_tokens": 120,
    "tts_characters":    400,
    "telephony_seconds": _D(60),
}

_CENTS = _D("0.000001")  # NUMERIC(10,6)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return _D(0)
    return _D(str(value))


# ══════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS — no I/O, no clock (except where `now` is injected)
# ══════════════════════════════════════════════════════════════════════

def estimate_cost_usd(
    *,
    stt_seconds: Any = 0,
    llm_input_tokens: int = 0,
    llm_output_tokens: int = 0,
    tts_characters: int = 0,
    telephony_seconds: Any = 0,
    stt_engine: Optional[str] = None,
    llm_model: Optional[str] = None,
    tts_engine: Optional[str] = None,
    telephony_provider: Optional[str] = None,
) -> dict:
    """PURE. Model the USD cost of one unit of work from the rate card.

    Returns a dict whose `is_estimated` is HARD-CODED True — this function
    computes a model, and a model is an estimate, always. It has no way to
    observe real spend and must never claim to.
    """
    stt_key = stt_engine if stt_engine in STT_USD_PER_SECOND else DEFAULT_STT_ENGINE
    llm_key = llm_model if llm_model in LLM_USD_PER_1K_INPUT else DEFAULT_LLM_MODEL
    tts_key = tts_engine if tts_engine in TTS_USD_PER_1K_CHARS else DEFAULT_TTS_ENGINE
    tel_key = (
        telephony_provider if telephony_provider in TELEPHONY_USD_PER_SECOND
        else DEFAULT_TELEPHONY_PROVIDER
    )

    stt_cost = _dec(stt_seconds) * STT_USD_PER_SECOND[stt_key]
    llm_cost = (
        (_dec(llm_input_tokens)  / _D(1000)) * LLM_USD_PER_1K_INPUT[llm_key]
        + (_dec(llm_output_tokens) / _D(1000)) * LLM_USD_PER_1K_OUTPUT[llm_key]
    )
    tts_cost = (_dec(tts_characters) / _D(1000)) * TTS_USD_PER_1K_CHARS[tts_key]
    tel_cost = _dec(telephony_seconds) * TELEPHONY_USD_PER_SECOND[tel_key]

    breakdown = {
        "stt":       _money(stt_cost),
        "llm":       _money(llm_cost),
        "tts":       _money(tts_cost),
        "telephony": _money(tel_cost),
    }
    return {
        "cost_usd":          _money(stt_cost + llm_cost + tts_cost + tel_cost),
        "cost_breakdown":    breakdown,
        "is_estimated":      True,   # never anything else — see module header
        "rate_card_version": RATE_CARD_VERSION,
        "rates_applied": {
            "stt_engine": stt_key, "llm_model": llm_key,
            "tts_engine": tts_key, "telephony_provider": tel_key,
        },
    }


def estimate_per_minute(
    *, stt_engine: str = DEFAULT_STT_ENGINE, tts_engine: str = DEFAULT_TTS_ENGINE,
    llm_model: str = DEFAULT_LLM_MODEL,
    telephony_provider: str = DEFAULT_TELEPHONY_PROVIDER,
    language: str = "en", profile: Optional[dict] = None,
) -> dict:
    """PURE. Modelled USD/minute, compared against the architecture targets.

    `within_target` answers "does the MODEL land in the target band" — it
    says nothing about real spend, because no real spend has been measured.
    """
    p = dict(profile or TYPICAL_MINUTE_PROFILE)
    est = estimate_cost_usd(
        stt_seconds=p["stt_seconds"],
        llm_input_tokens=p["llm_input_tokens"],
        llm_output_tokens=p["llm_output_tokens"],
        tts_characters=p["tts_characters"],
        telephony_seconds=p["telephony_seconds"],
        stt_engine=stt_engine, llm_model=llm_model,
        tts_engine=tts_engine, telephony_provider=telephony_provider,
    )
    low, high = PER_MINUTE_TARGET_USD.get(language, PER_MINUTE_TARGET_USD["en"])
    cost = est["cost_usd"]
    return {
        **est,
        "language":          language,
        "usage_profile":     {k: str(v) for k, v in p.items()},
        "target_usd_per_min": {"low": str(low), "high": str(high)},
        "within_target":     low <= cost <= high,
        "vs_target":         "below" if cost < low else ("above" if cost > high else "within"),
        "basis":             "ESTIMATED — modelled usage profile x assumed list rates",
    }


def resolve_period(period: Optional[str], now: datetime) -> tuple[datetime, datetime]:
    """PURE. Turn a ?period= token into an explicit [start, end) window."""
    end = now
    token = (period or "30d").strip().lower()
    if token == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif token == "mtd":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif token.endswith("d") and token[:-1].isdigit():
        days = int(token[:-1])
        if not 1 <= days <= 365:
            raise ValueError("period days must be between 1 and 365")
        start = now - timedelta(days=days)
    else:
        raise ValueError(
            "period must be 'today', 'mtd', or '<N>d' (e.g. 7d, 30d, 90d)"
        )
    return start, end


def summarise_rows(rows: Iterable[dict]) -> dict:
    """PURE. Aggregate usage rows, keeping estimated and metered APART.

    Returns separate `estimated` and `metered` blocks. They are NEVER
    summed into one headline number: adding a modelled figure to a billed
    figure produces something that is neither, and reporting it as a total
    is exactly the lie this module exists to prevent.
    """
    buckets = {
        "estimated": {"rows": 0, "cost_usd": _D(0), "components": {
            "stt": _D(0), "llm": _D(0), "tts": _D(0), "telephony": _D(0)}},
        "metered":   {"rows": 0, "cost_usd": _D(0), "components": {
            "stt": _D(0), "llm": _D(0), "tts": _D(0), "telephony": _D(0)}},
    }
    units = {
        "stt_seconds": _D(0), "llm_input_tokens": 0, "llm_output_tokens": 0,
        "tts_characters": 0, "telephony_seconds": _D(0),
    }

    for row in rows:
        key = "estimated" if row.get("is_estimated", True) else "metered"
        bucket = buckets[key]
        bucket["rows"] += 1
        bucket["cost_usd"] += _dec(row.get("cost_usd"))
        breakdown = row.get("cost_breakdown") or {}
        for comp in bucket["components"]:
            bucket["components"][comp] += _dec(breakdown.get(comp))

        units["stt_seconds"]       += _dec(row.get("stt_seconds"))
        units["telephony_seconds"] += _dec(row.get("telephony_seconds"))
        units["llm_input_tokens"]  += int(row.get("llm_input_tokens")  or 0)
        units["llm_output_tokens"] += int(row.get("llm_output_tokens") or 0)
        units["tts_characters"]    += int(row.get("tts_characters")    or 0)

    for bucket in buckets.values():
        bucket["cost_usd"] = str(_money(bucket["cost_usd"]))
        bucket["components"] = {k: str(_money(v)) for k, v in bucket["components"].items()}

    total_seconds = units["telephony_seconds"] or units["stt_seconds"]
    minutes = (total_seconds / _D(60)) if total_seconds else _D(0)
    est_cost = _dec(buckets["estimated"]["cost_usd"])

    return {
        "estimated": buckets["estimated"],
        "metered":   buckets["metered"],
        "units": {
            "stt_seconds":       str(units["stt_seconds"]),
            "telephony_seconds": str(units["telephony_seconds"]),
            "llm_input_tokens":  units["llm_input_tokens"],
            "llm_output_tokens": units["llm_output_tokens"],
            "tts_characters":    units["tts_characters"],
            "minutes":           str(_money(minutes)),
        },
        "estimated_cost_per_minute": (
            str(_money(est_cost / minutes)) if minutes > 0 else None
        ),
        # Deliberately no "total_cost_usd" key. See the docstring.
        "note": (
            "estimated and metered are reported separately and are NOT summed. "
            "As of Phase 4, metered.rows is expected to be 0 — no provider "
            "usage API is integrated, so no cost here has been measured."
        ),
    }


# ══════════════════════════════════════════════════════════════════════
# SERVICE — I/O lives here and nowhere else
# ══════════════════════════════════════════════════════════════════════

class UsageService:
    def __init__(self) -> None:
        self.db = get_supabase_admin()

    def record_usage(
        self, business_id: UUID, *, call_id: Optional[UUID] = None,
        branch_id: Optional[UUID] = None,
        stt_seconds: Any = 0, llm_input_tokens: int = 0, llm_output_tokens: int = 0,
        tts_characters: int = 0, telephony_seconds: Any = 0,
        stt_engine: Optional[str] = None, llm_model: Optional[str] = None,
        tts_engine: Optional[str] = None, telephony_provider: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        """Persist one usage row with an ESTIMATED cost.

        There is no `is_estimated` parameter, on purpose. This method can
        only ever write True, because the number it writes came from the
        rate card. A metered writer would be a different method backed by a
        provider billing API, and does not exist yet.
        """
        est = estimate_cost_usd(
            stt_seconds=stt_seconds,
            llm_input_tokens=llm_input_tokens, llm_output_tokens=llm_output_tokens,
            tts_characters=tts_characters, telephony_seconds=telephony_seconds,
            stt_engine=stt_engine, llm_model=llm_model,
            tts_engine=tts_engine, telephony_provider=telephony_provider,
        )
        row = {
            "business_id":        str(business_id),
            "call_id":            str(call_id) if call_id else None,
            "branch_id":          str(branch_id) if branch_id else None,
            "stt_engine":         stt_engine,
            "stt_seconds":        str(_dec(stt_seconds)),
            "llm_input_tokens":   int(llm_input_tokens or 0),
            "llm_output_tokens":  int(llm_output_tokens or 0),
            "tts_characters":     int(tts_characters or 0),
            "telephony_seconds":  str(_dec(telephony_seconds)),
            "llm_model":          llm_model,
            "tts_engine":         tts_engine,
            "telephony_provider": telephony_provider,
            "cost_usd":           str(est["cost_usd"]),
            "is_estimated":       True,
            "rate_card_version":  est["rate_card_version"],
            "cost_breakdown":     {k: str(v) for k, v in est["cost_breakdown"].items()},
            "metadata":           metadata or {},
        }
        inserted = self.db.table("usage_metrics").insert(row).execute().data or []
        return inserted[0] if inserted else None

    def cost_report(
        self, business_id: UUID, *, period: Optional[str] = "30d",
        branch_id: Optional[UUID] = None, now: Optional[datetime] = None,
        limit: int = 5000,
    ) -> dict:
        """GET /analytics/cost payload.

        Every line item carries its own `is_estimated`. Estimated and
        metered totals are reported separately and never merged.
        """
        moment = now or datetime.now(timezone.utc)
        start, end = resolve_period(period, moment)

        q = (
            self.db.table("usage_metrics").select("*")
            .eq("business_id", str(business_id))
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat())
        )
        if branch_id is not None:
            q = q.eq("branch_id", str(branch_id))
        rows = q.order("created_at", desc=True).limit(limit).execute().data or []

        line_items = [
            {
                "id":                 r.get("id"),
                "call_id":            r.get("call_id"),
                "branch_id":          r.get("branch_id"),
                "at":                 r.get("created_at"),
                "stt_engine":         r.get("stt_engine"),
                "stt_seconds":        r.get("stt_seconds"),
                "llm_input_tokens":   r.get("llm_input_tokens"),
                "llm_output_tokens":  r.get("llm_output_tokens"),
                "tts_characters":     r.get("tts_characters"),
                "telephony_seconds":  r.get("telephony_seconds"),
                "cost_usd":           r.get("cost_usd"),
                "cost_breakdown":     r.get("cost_breakdown") or {},
                # LOAD-BEARING — per line item, never inferred from the header.
                "is_estimated":       bool(r.get("is_estimated", True)),
                "cost_basis":         "ESTIMATED" if r.get("is_estimated", True) else "METERED",
                "rate_card_version":  r.get("rate_card_version"),
            }
            for r in rows
        ]

        summary = summarise_rows(rows)
        metered_rows = summary["metered"]["rows"]

        return {
            "period":       {"token": period or "30d",
                             "start": start.isoformat(), "end": end.isoformat()},
            "branch_id":    str(branch_id) if branch_id else None,
            "summary":      summary,
            "line_items":   line_items,
            "targets_usd_per_min": {
                k: {"low": str(v[0]), "high": str(v[1])}
                for k, v in PER_MINUTE_TARGET_USD.items()
            },
            "cost_basis":   "METERED" if (metered_rows and not summary["estimated"]["rows"])
                            else ("MIXED" if metered_rows else "ESTIMATED"),
            "all_estimated": metered_rows == 0,
            "rate_card": {
                "version": RATE_CARD_VERSION,
                "formula": (
                    "cost_usd = stt_seconds*STT_USD_PER_SECOND "
                    "+ (llm_input_tokens/1000)*LLM_USD_PER_1K_INPUT "
                    "+ (llm_output_tokens/1000)*LLM_USD_PER_1K_OUTPUT "
                    "+ (tts_characters/1000)*TTS_USD_PER_1K_CHARS "
                    "+ telephony_seconds*TELEPHONY_USD_PER_SECOND"
                ),
                "rates_usd": {
                    "stt_per_second":        {k: str(v) for k, v in STT_USD_PER_SECOND.items()},
                    "llm_per_1k_input":      {k: str(v) for k, v in LLM_USD_PER_1K_INPUT.items()},
                    "llm_per_1k_output":     {k: str(v) for k, v in LLM_USD_PER_1K_OUTPUT.items()},
                    "tts_per_1k_characters": {k: str(v) for k, v in TTS_USD_PER_1K_CHARS.items()},
                    "telephony_per_second":  {k: str(v) for k, v in TELEPHONY_USD_PER_SECOND.items()},
                },
                "provenance": (
                    "ASSUMED PUBLIC LIST PRICES, hand-entered. Not contracted "
                    "rates, not read from any provider API, not reconciled "
                    "against an invoice."
                ),
            },
            "disclaimer": (
                "ALL COSTS SHOWN ARE ESTIMATES unless a line item's "
                "is_estimated is false. Phase 2B never ran, so no real "
                "provider usage has ever been logged in this system and no "
                "figure here has been measured or billed. Treat these as "
                "modelled numbers for planning only."
            ),
        }
