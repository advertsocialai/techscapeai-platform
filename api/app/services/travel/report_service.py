"""
Analytics report generation (Phase 4 T4).

Two clearly separated halves:

  1. PURE functions (no DB, no clock, no network) — `period_bounds()` and
     `aggregate_report()`. Everything numeric a report contains is computed
     here from plain lists of dicts, so the acceptance criterion
     ("daily report matches manual calculation on the same data") is
     verifiable with an in-memory fixture and no Supabase.

  2. `ReportService` — the thin IO shell that fetches rows from Supabase and
     hands them to the pure half.

────────────────────────────────────────────────────────────────────────────
DATA-HONESTY RULE (read before adding anything to this file)
────────────────────────────────────────────────────────────────────────────
Phase 3's post-call pipeline (`post_call_service.py`) runs in STUB mode
whenever ANTHROPIC_API_KEY is unset — which is the current state of this
deployment. In stub mode `_stub_summary()` returns the CONSTANT
`lead_score = 40`, and the pipeline then writes
`travel_calls.sentiment_score = round(40 / 100.0, 3) = 0.4` for EVERY call.

So a "sentiment trend" computed off this column is a flat constant, not a
measurement. This module therefore:

  * never emits a sentiment `trend` value while the data is stub-derived —
    the key is present but always `None`, with a machine-readable reason;
  * detects the stub signature two independent ways: config (`ai_stub_mode`,
    driven by ANTHROPIC_API_KEY) AND data shape (every observed
    sentiment_score identical, and equal to the known stub constant 0.4);
  * labels every sentiment-derived figure it does emit as raw and
    stub-derived, under key names that cannot be mistaken for a metric
    (`avg_score_raw`, not `avg_sentiment`);
  * does the same for `travel_leads.score`, which the same stub writes as
    the constant 40.

Raw counts (call volume, funnel counts, revenue) are unaffected by the stub
and are reported normally.
"""
from __future__ import annotations

import calendar
import logging
import statistics
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any, Iterable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

REPORT_TYPES = ("daily", "weekly", "monthly")

DEFAULT_TIMEZONE = "Asia/Kolkata"

# The exact constants Phase 3's stub pipeline writes. Used for detection only —
# see the DATA-HONESTY RULE above. post_call_service._stub_summary() →
# lead_score 40 → travel_calls.sentiment_score round(40/100, 3) = 0.4.
STUB_LEAD_SCORE = 40
STUB_SENTIMENT_SCORE = 0.4

_STUB_SENTIMENT_LABEL = (
    "STUB-DERIVED CONSTANT — NOT A MEASUREMENT. Phase 3's post-call pipeline "
    "runs without ANTHROPIC_API_KEY and writes a fixed lead_score of 40, which "
    "becomes sentiment_score 0.4 on every call. Treat these figures as a "
    "placeholder, never as signal. No trend is computed."
)
_STUB_LEAD_SCORE_LABEL = (
    "STUB-DERIVED CONSTANT — NOT A MEASUREMENT. travel_leads.score is written "
    "as a fixed 40 by the keyword-only stub summariser."
)


# ══════════════════════════════════════════════════════════════════════════
# PURE HELPERS
# ══════════════════════════════════════════════════════════════════════════
def resolve_tz(name: Optional[str]) -> ZoneInfo:
    """IANA name → ZoneInfo, falling back to Asia/Kolkata on anything bad."""
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse a Supabase timestamptz (or datetime) into an aware UTC datetime.

    Naive input is assumed UTC — that is what Postgres hands back for a
    timestamptz rendered without an offset.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        # Postgres emits '+00' / 'Z'; fromisoformat wants '+00:00'.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        # Trailing 2-digit offset like '+05' → '+05:00'
        if len(raw) >= 3 and raw[-3] in "+-" and raw[-2:].isdigit():
            raw = raw + ":00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            try:
                dt = datetime.fromisoformat(raw[:19])
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def local_date(value: Any, tz: ZoneInfo) -> Optional[date]:
    """Calendar date of a timestamp AS SEEN IN `tz`.

    This is what makes an IST tenant's "8 Aug" report contain the call that
    Postgres stored at 2026-08-07T20:00:00Z (= 8 Aug 01:30 IST).
    """
    dt = parse_dt(value)
    return dt.astimezone(tz).date() if dt else None


def period_bounds(report_type: str, anchor: date) -> tuple[date, date]:
    """Inclusive [start, end] the report covers. PURE.

    daily   → the anchor day itself
    weekly  → the ISO week (Mon–Sun) containing the anchor
    monthly → the calendar month containing the anchor
    """
    if report_type == "daily":
        return anchor, anchor
    if report_type == "weekly":
        start = anchor - timedelta(days=anchor.weekday())   # Monday
        return start, start + timedelta(days=6)             # Sunday
    if report_type == "monthly":
        start = anchor.replace(day=1)
        last = calendar.monthrange(anchor.year, anchor.month)[1]
        return start, anchor.replace(day=last)
    raise ValueError(f"Unknown report_type: {report_type!r}")


def _count_by(rows: Iterable[dict], key: str, *, unknown: str = "unknown") -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        k = unknown if v in (None, "") else str(v)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(part: int, whole: int) -> float:
    return round(part * 100.0 / whole, 2) if whole else 0.0


def _match_keys(pkg: dict, dest_by_id: dict[str, str]) -> set[str]:
    """Lowercase strings a lead's destination_hint may be matched against."""
    keys: set[str] = set()
    name = pkg.get("name")
    if name:
        keys.add(str(name).strip().lower())
    dest = dest_by_id.get(str(pkg.get("destination_id")))
    if dest:
        keys.add(str(dest).strip().lower())
    return {k for k in keys if k}


# ══════════════════════════════════════════════════════════════════════════
# PURE AGGREGATION — the whole report body is computed here
# ══════════════════════════════════════════════════════════════════════════
def aggregate_report(
    *,
    report_type: str,
    anchor: date,
    calls: list[dict],
    leads: list[dict],
    packages: list[dict],
    destinations: Optional[list[dict]] = None,
    payments: Optional[list[dict]] = None,
    payments_available: bool = False,
    payments_error: Optional[str] = None,
    ai_stub_mode: bool = True,
    tz_name: str = DEFAULT_TIMEZONE,
    branch_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build the full report dict from in-memory rows. PURE — no IO, no clock.

    Rows may span a wider window than the report period (the fetch layer pads
    by a day for timezone slack); this function does the exact date filtering
    itself, in `tz_name`, so the arithmetic is reproducible.

    Period membership:
      calls    → started_at, falling back to created_at
      leads    → created_at
      payments → created_at  (payment_links has no paid_at column; a link
                 created in-period and later marked paid counts here)
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report_type: {report_type!r}")

    tz = resolve_tz(tz_name)
    start, end = period_bounds(report_type, anchor)
    destinations = destinations or []
    payments = payments or []
    warnings: list[str] = []

    def in_period(row: dict, *fields: str) -> bool:
        for f in fields:
            d = local_date(row.get(f), tz)
            if d is not None:
                return start <= d <= end
        return False

    p_calls = [c for c in calls if in_period(c, "started_at", "created_at")]
    p_leads = [l for l in leads if in_period(l, "created_at")]
    p_pay = [p for p in payments if in_period(p, "created_at")]

    # ── Call volume ───────────────────────────────────────────────────────
    durations = [d for d in (_num(c.get("duration_sec")) for c in p_calls) if d is not None]
    total_duration = int(sum(durations))
    by_call_status = _count_by(p_calls, "status")
    calls_block = {
        "total": len(p_calls),
        "completed": by_call_status.get("completed", 0),
        "failed": by_call_status.get("failed", 0),
        "active": by_call_status.get("active", 0),
        "by_status": by_call_status,
        "by_mode": _count_by(p_calls, "mode"),
        "by_language": _count_by(p_calls, "language"),
        "total_duration_sec": total_duration,
        "avg_duration_sec": round(total_duration / len(durations), 2) if durations else 0.0,
        "calls_with_duration": len(durations),
        "connected_rate_pct": _pct(by_call_status.get("completed", 0), len(p_calls)),
    }

    # ── Conversion funnel ─────────────────────────────────────────────────
    by_qual = _count_by(p_leads, "qualification")
    by_status = _count_by(p_leads, "status")
    n_leads = len(p_leads)
    booked = by_status.get("booked", 0)
    converted = by_qual.get("converted", 0)
    funnel_block = {
        "leads_total": n_leads,
        "by_qualification": {k: by_qual.get(k, 0)
                             for k in ("cold", "warm", "hot", "converted", "lost")}
        | {k: v for k, v in by_qual.items()
           if k not in ("cold", "warm", "hot", "converted", "lost")},
        "by_status": {k: by_status.get(k, 0)
                      for k in ("new", "qualified", "itinerary_sent",
                                "negotiating", "booked", "lost")}
        | {k: v for k, v in by_status.items()
           if k not in ("new", "qualified", "itinerary_sent",
                        "negotiating", "booked", "lost")},
        "qualified_or_better": sum(by_status.get(k, 0) for k in
                                   ("qualified", "itinerary_sent", "negotiating", "booked")),
        "hot_leads": by_qual.get("hot", 0),
        "booked": booked,
        "converted": converted,
        "lost": by_status.get("lost", 0),
        "conversion_rate_pct": _pct(booked, n_leads),
        "leads_from_calls": sum(1 for l in p_leads if str(l.get("source")) == "phone"),
        "by_source": _count_by(p_leads, "source"),
    }

    # ── Revenue (payment_links — may not exist yet) ────────────────────────
    if payments_available:
        paid = [p for p in p_pay if str(p.get("status")) == "paid"]
        by_ccy: dict[str, float] = {}
        for p in paid:
            amt = _num(p.get("amount")) or 0.0
            ccy = str(p.get("currency") or "INR").upper()
            by_ccy[ccy] = round(by_ccy.get(ccy, 0.0) + amt, 2)
        revenue_block = {
            "available": True,
            "source": "payment_links",
            "links_created": len(p_pay),
            "links_paid": len(paid),
            "payment_conversion_pct": _pct(len(paid), len(p_pay)),
            "collected_by_currency": dict(sorted(by_ccy.items())),
            "collected_inr": by_ccy.get("INR", 0.0),
            "by_link_status": _count_by(p_pay, "status"),
            "note": ("payment_links has no paid_at column — a link is counted in "
                     "this period by its created_at, and counted as revenue if its "
                     "current status is 'paid'."),
        }
    else:
        revenue_block = {
            "available": False,
            "source": "payment_links",
            "reason": payments_error or "payment_links table not reachable",
            "note": ("Revenue is omitted, not zero. The payment_links table is "
                     "owned by another workstream; this report degrades to "
                     "non-revenue aggregates rather than reporting a false 0."),
            "collected_by_currency": {},
            "collected_inr": None,
        }
        warnings.append("revenue_unavailable: " + revenue_block["reason"])

    # ── Top packages ──────────────────────────────────────────────────────
    # Attribution rule, stated because there is no lead→package FK in the
    # schema: a lead counts toward a package when the lead's destination_hint
    # and one of the package's match keys (package name, destination name)
    # contain one another, case-insensitively. Revenue attribution is exact —
    # payment_links.package_id is a real FK.
    dest_by_id = {str(d.get("id")): str(d.get("name") or "") for d in destinations}
    pay_by_pkg: dict[str, dict[str, Any]] = {}
    if payments_available:
        for p in p_pay:
            pid = p.get("package_id")
            if not pid:
                continue
            slot = pay_by_pkg.setdefault(str(pid), {"paid": 0, "amount": 0.0})
            if str(p.get("status")) == "paid":
                slot["paid"] += 1
                slot["amount"] = round(slot["amount"] + (_num(p.get("amount")) or 0.0), 2)

    hints = [str(l.get("destination_hint") or "").strip().lower() for l in p_leads]
    hints = [h for h in hints if h]

    pkg_rows: list[dict[str, Any]] = []
    for pkg in packages:
        pid = str(pkg.get("id"))
        keys = _match_keys(pkg, dest_by_id)
        matched = sum(1 for h in hints if any(k in h or h in k for k in keys))
        pay = pay_by_pkg.get(pid, {"paid": 0, "amount": 0.0})
        pkg_rows.append({
            "package_id": pid,
            "name": pkg.get("name"),
            "destination": dest_by_id.get(str(pkg.get("destination_id"))),
            "base_price_inr": pkg.get("base_price_inr"),
            "leads_matched": matched,
            "paid_links": pay["paid"],
            "revenue_attributed": pay["amount"] if payments_available else None,
        })
    # Deterministic ordering: revenue desc, then lead interest desc, then name.
    pkg_rows.sort(key=lambda r: (
        -(r["revenue_attributed"] or 0.0),
        -r["leads_matched"],
        str(r["name"] or ""),
    ))
    top_packages = [r for r in pkg_rows if r["leads_matched"] or r["paid_links"]][:10]
    if not top_packages:
        warnings.append(
            "top_packages_empty: no lead destination_hint matched any package "
            "and no payment link was attributed to a package in this period."
        )

    # ── Sentiment / AI-derived scores — STUB-AWARE, see DATA-HONESTY RULE ──
    s_scores = [s for s in (_num(c.get("sentiment_score")) for c in p_calls) if s is not None]
    s_distinct = sorted({round(s, 3) for s in s_scores})
    s_is_constant = len(s_scores) > 0 and len(s_distinct) == 1
    s_matches_stub = bool(s_scores) and all(
        abs(s - STUB_SENTIMENT_SCORE) < 1e-9 for s in s_scores
    )
    s_stub_derived = bool(ai_stub_mode or s_matches_stub)

    sentiment_block: dict[str, Any] = {
        "samples": len(s_scores),
        "distinct_values": len(s_distinct),
        "is_constant": s_is_constant,
        "stub_derived": s_stub_derived,
        "detected_via": (
            ["config:ANTHROPIC_API_KEY_unset"] if ai_stub_mode else []
        ) + (["data:all_values_equal_stub_constant_0.4"] if s_matches_stub else []),
        # Deliberately named *_raw so it can never read as a metric.
        "avg_score_raw": round(statistics.fmean(s_scores), 3) if s_scores else None,
        "min_score_raw": round(min(s_scores), 3) if s_scores else None,
        "max_score_raw": round(max(s_scores), 3) if s_scores else None,
        # NEVER a number while the underlying data is a constant.
        "trend": None,
        "trend_suppressed_reason": None,
        "label": None,
    }
    if s_stub_derived:
        sentiment_block["label"] = _STUB_SENTIMENT_LABEL
        sentiment_block["trend_suppressed_reason"] = (
            "stub_derived_constant — a trend over a constant is not a trend"
        )
        warnings.append(
            "sentiment_stub_derived: every sentiment figure in this report is a "
            "placeholder constant written by the no-API-key stub pipeline. Do not "
            "read it as signal."
        )
    elif s_is_constant:
        sentiment_block["label"] = (
            "CONSTANT INPUT — all observed sentiment_score values are identical, "
            "so no trend is computable even though the pipeline is not in stub mode."
        )
        sentiment_block["trend_suppressed_reason"] = "constant_input"
        warnings.append("sentiment_constant: all sentiment_score values identical.")
    elif len(s_scores) < 2:
        sentiment_block["label"] = "measured (insufficient samples for a trend)"
        sentiment_block["trend_suppressed_reason"] = "insufficient_samples"
    else:
        # Real, non-constant data: first half vs second half by call order.
        half = len(s_scores) // 2
        early = statistics.fmean(s_scores[:half])
        late = statistics.fmean(s_scores[half:])
        delta = round(late - early, 3)
        sentiment_block["label"] = "measured"
        sentiment_block["trend"] = {
            "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
            "delta": delta,
            "first_half_avg": round(early, 3),
            "second_half_avg": round(late, 3),
        }

    l_scores = [s for s in (_num(l.get("score")) for l in p_leads) if s is not None]
    l_distinct = sorted({round(s, 3) for s in l_scores})
    l_matches_stub = bool(l_scores) and all(
        abs(s - STUB_LEAD_SCORE) < 1e-9 for s in l_scores
    )
    lead_score_block: dict[str, Any] = {
        "samples": len(l_scores),
        "distinct_values": len(l_distinct),
        "is_constant": len(l_scores) > 0 and len(l_distinct) == 1,
        "stub_derived": bool(ai_stub_mode or l_matches_stub),
        "avg_score_raw": round(statistics.fmean(l_scores), 3) if l_scores else None,
        "label": _STUB_LEAD_SCORE_LABEL if (ai_stub_mode or l_matches_stub) else "measured",
    }
    if lead_score_block["stub_derived"]:
        warnings.append(
            "lead_score_stub_derived: travel_leads.score is the stub constant 40."
        )

    return {
        "report_type": report_type,
        "period": {
            "anchor": anchor.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": (end - start).days + 1,
            "timezone": tz_name,
        },
        "scope": {"branch_id": branch_id, "branch_scoped": branch_id is not None},
        "calls": calls_block,
        "funnel": funnel_block,
        "revenue": revenue_block,
        "top_packages": top_packages,
        "sentiment": sentiment_block,
        "lead_score": lead_score_block,
        "data_quality": {
            "ai_stub_mode": ai_stub_mode,
            "ai_stub_reason": (
                "ANTHROPIC_API_KEY is not configured — post_call_service falls back "
                "to _stub_summary(), which returns a fixed lead_score of 40."
            ) if ai_stub_mode else None,
            "trustworthy": ["calls", "funnel"] + (["revenue"] if payments_available else []),
            "not_trustworthy": ["sentiment", "lead_score"]
            if (s_stub_derived or lead_score_block["stub_derived"]) else [],
            "rows_scanned": {
                "calls": len(calls), "leads": len(leads),
                "packages": len(packages), "payment_links": len(payments),
            },
            "rows_in_period": {
                "calls": len(p_calls), "leads": len(p_leads), "payment_links": len(p_pay),
            },
        },
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════════
# PURE RENDERERS
# ══════════════════════════════════════════════════════════════════════════
def _esc(v: Any) -> str:
    s = "" if v is None else str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def render_report_text(report: dict, *, business_name: str = "") -> str:
    """Compact plain-text summary — WhatsApp / email body. PURE, deterministic."""
    p = report["period"]
    c = report["calls"]
    f = report["funnel"]
    r = report["revenue"]
    head = f"{business_name} — " if business_name else ""
    lines = [
        f"{head}{report['report_type'].title()} report",
        f"{p['start']} → {p['end']} ({p['timezone']})",
        "",
        f"Calls: {c['total']} total · {c['completed']} completed · {c['failed']} failed",
        f"Talk time: {c['total_duration_sec']}s (avg {c['avg_duration_sec']}s)",
        "",
        f"Leads: {f['leads_total']} · hot {f['hot_leads']} · booked {f['booked']} "
        f"({f['conversion_rate_pct']}% conversion)",
    ]
    if r.get("available"):
        lines.append(f"Collected: INR {r['collected_inr']} across {r['links_paid']} paid links")
    else:
        lines.append("Collected: unavailable (payment_links not reachable)")
    if report["top_packages"]:
        lines.append("")
        lines.append("Top packages:")
        for row in report["top_packages"][:3]:
            lines.append(f"  • {row['name']} — {row['leads_matched']} leads, "
                         f"{row['paid_links']} paid")
    s = report["sentiment"]
    if s.get("stub_derived") or s.get("is_constant"):
        lines += ["", "⚠ Sentiment figures omitted: stub-derived constant, not a measurement."]
    elif s.get("trend"):
        lines += ["", f"Sentiment trend: {s['trend']['direction']} ({s['trend']['delta']:+})"]
    return "\n".join(lines)


def render_report_html(report: dict, *, business_name: str = "") -> str:
    """Deterministic, print-ready HTML. PURE — no clock, no randomness.

    This is what GET /reports/{id}/pdf returns. See that endpoint's docstring:
    real PDF conversion is DEFERRED (no reportlab / weasyprint in this repo and
    we are not adding a heavy dependency for it).
    """
    p, c, f, r = report["period"], report["calls"], report["funnel"], report["revenue"]
    s, ls = report["sentiment"], report["lead_score"]

    def kv(label: str, value: Any) -> str:
        return f"<div class='kv'><span>{_esc(label)}</span><b>{_esc(value)}</b></div>"

    banner = (
        "<div class='banner'><b>PDF conversion is deferred.</b> This document is "
        "a deterministic HTML rendering, print-ready via your browser "
        "(Cmd/Ctrl-P → Save as PDF). No server-side PDF engine "
        "(reportlab / weasyprint) is installed in this repo and none was added.</div>"
    )

    warn_html = ""
    if report["warnings"]:
        items = "".join(f"<li>{_esc(w)}</li>" for w in report["warnings"])
        warn_html = f"<div class='warn'><h3>Data warnings</h3><ul>{items}</ul></div>"

    if s["stub_derived"] or s["is_constant"] or s["trend"] is None:
        sentiment_html = (
            "<div class='stub'><h3>Sentiment — NOT A MEASUREMENT</h3>"
            f"<p>{_esc(s['label'])}</p>"
            + kv("Samples", s["samples"])
            + kv("Distinct values", s["distinct_values"])
            + kv("Raw average (placeholder)", s["avg_score_raw"])
            + kv("Trend", "suppressed — " + str(s["trend_suppressed_reason"]))
            + "</div>"
        )
    else:
        trend_txt = "{} ({:+})".format(s["trend"]["direction"], s["trend"]["delta"])
        sentiment_html = (
            "<div class='card'><h3>Sentiment</h3>"
            + kv("Samples", s["samples"])
            + kv("Average", s["avg_score_raw"])
            + kv("Trend", trend_txt)
            + "</div>"
        )

    lead_score_html = (
        f"<div class='stub'><h3>Lead score — NOT A MEASUREMENT</h3>"
        f"<p>{_esc(ls['label'])}</p>{kv('Raw average (placeholder)', ls['avg_score_raw'])}</div>"
        if ls["stub_derived"] else
        f"<div class='card'><h3>Lead score</h3>{kv('Average', ls['avg_score_raw'])}</div>"
    )

    if r.get("available"):
        rev_rows = "".join(kv(ccy, amt) for ccy, amt
                           in r["collected_by_currency"].items()) or kv("Collected", 0)
        revenue_html = (f"<div class='card'><h3>Revenue</h3>"
                        f"{kv('Links created', r['links_created'])}"
                        f"{kv('Links paid', r['links_paid'])}"
                        f"{kv('Payment conversion', str(r['payment_conversion_pct']) + '%')}"
                        f"{rev_rows}</div>")
    else:
        revenue_html = (f"<div class='stub'><h3>Revenue — unavailable</h3>"
                        f"<p>{_esc(r['reason'])}</p><p>{_esc(r['note'])}</p></div>")

    pkg_rows = "".join(
        f"<tr><td>{_esc(row['name'])}</td><td>{_esc(row['destination'])}</td>"
        f"<td class='n'>{_esc(row['leads_matched'])}</td>"
        f"<td class='n'>{_esc(row['paid_links'])}</td>"
        f"<td class='n'>{_esc(row['revenue_attributed'])}</td></tr>"
        for row in report["top_packages"]
    ) or "<tr><td colspan='5'>No package activity in this period.</td></tr>"

    title = f"{business_name + ' — ' if business_name else ''}{report['report_type'].title()} report"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{_esc(title)} {_esc(p['start'])}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font: 14px/1.5 -apple-system, "Segoe UI", Inter, sans-serif;
         color: #1a1a1a; background: #fff; margin: 0; padding: 32px; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }}
  h3 {{ font-size: 14px; margin: 0 0 8px; text-transform: uppercase;
        letter-spacing: .06em; color: #555; }}
  .sub {{ color: #666; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
           gap: 14px; }}
  .card, .stub, .warn, .banner {{ border: 1px solid #e5e5e5; border-radius: 8px;
           padding: 14px; background: #fafafa; }}
  .stub {{ background: #fff6e5; border-color: #f0c674; }}
  .warn {{ background: #fdecea; border-color: #e5a29b; margin-top: 18px; }}
  .banner {{ background: #eef3ff; border-color: #b8ccf5; margin-bottom: 20px; }}
  .kv {{ display: flex; justify-content: space-between; gap: 12px;
         padding: 3px 0; border-bottom: 1px dotted #ddd; }}
  .kv:last-child {{ border-bottom: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; }}
  td.n, th.n {{ text-align: right; }}
  section {{ margin-top: 18px; }}
  @media print {{ body {{ padding: 0; }} .banner {{ display: none; }} }}
</style></head><body>
{banner}
<h1>{_esc(title)}</h1>
<div class="sub">{_esc(p['start'])} → {_esc(p['end'])} · {_esc(p['timezone'])}
 · scope: {_esc('branch ' + str(report['scope']['branch_id']) if report['scope']['branch_scoped'] else 'whole business')}</div>

<div class="grid">
  <div class="card"><h3>Call volume</h3>
    {kv('Total calls', c['total'])}{kv('Completed', c['completed'])}
    {kv('Failed', c['failed'])}{kv('Still active', c['active'])}
    {kv('Total talk time (s)', c['total_duration_sec'])}
    {kv('Average duration (s)', c['avg_duration_sec'])}
    {kv('Connected rate', str(c['connected_rate_pct']) + '%')}</div>

  <div class="card"><h3>Conversion funnel</h3>
    {kv('Leads', f['leads_total'])}{kv('Qualified or better', f['qualified_or_better'])}
    {kv('Hot', f['hot_leads'])}{kv('Booked', f['booked'])}{kv('Lost', f['lost'])}
    {kv('Conversion rate', str(f['conversion_rate_pct']) + '%')}</div>

  {revenue_html}
  {sentiment_html}
  {lead_score_html}
</div>

<section><h3>Top packages</h3>
<table><thead><tr><th>Package</th><th>Destination</th><th class="n">Leads</th>
<th class="n">Paid links</th><th class="n">Revenue</th></tr></thead>
<tbody>{pkg_rows}</tbody></table>
<p class="sub">Lead attribution has no FK in the schema: a lead counts toward a
package when its <code>destination_hint</code> and the package name or destination
name contain one another (case-insensitive). Revenue attribution is exact
(<code>payment_links.package_id</code>).</p></section>

{warn_html}
</body></html>"""


# ══════════════════════════════════════════════════════════════════════════
# IO SHELL
# ══════════════════════════════════════════════════════════════════════════
class ReportService:
    """Fetches rows from Supabase and delegates every number to the pure half."""

    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ── stub-mode detection ───────────────────────────────────────────────
    @staticmethod
    def ai_stub_mode() -> bool:
        """True when Phase 3's post-call pipeline is writing constants.

        Config-side detection. The pure aggregator additionally sniffs the
        data itself, so a report is still labelled correctly if a key is
        present now but the historical rows were written by the stub.
        """
        try:
            from app.core.config import settings
            return not bool(getattr(settings, "ANTHROPIC_API_KEY", ""))
        except Exception:
            return True

    # ── branch scoping ────────────────────────────────────────────────────
    def branch_exists(self, branch_id: UUID, business_id: UUID) -> bool:
        rows = (
            self.db.table("branches").select("id")
            .eq("id", str(branch_id)).eq("business_id", str(business_id))
            .limit(1).execute().data or []
        )
        return bool(rows)

    def _branch_agent_ids(self, branch_id: UUID, business_id: UUID) -> list[str]:
        """Users belonging to a branch.

        travel_calls and travel_leads carry no branch_id column (see 0003 —
        only travel_packages gained one, in 0009). The only real branch link
        for call/lead rows is travel_leads.assigned_agent → ts_users.branch_id,
        so that is what branch scoping uses. Stated explicitly in the report's
        `scope` block so nobody mistakes it for a direct column filter.
        """
        rows = (
            self.db.table("ts_users").select("id")
            .eq("business_id", str(business_id)).eq("branch_id", str(branch_id))
            .execute().data or []
        )
        return [str(r["id"]) for r in rows]

    # ── fetch ─────────────────────────────────────────────────────────────
    def _fetch(self, business_id: UUID, start: date, end: date,
               branch_id: Optional[UUID]) -> dict[str, Any]:
        biz = str(business_id)
        # Pad by a day on each side: rows are filtered by UTC timestamp here
        # but by LOCAL date in the pure aggregator.
        lo = (start - timedelta(days=1)).isoformat()
        hi = (end + timedelta(days=2)).isoformat()

        lead_q = (
            self.db.table("travel_leads").select("*")
            .eq("business_id", biz).gte("created_at", lo).lt("created_at", hi)
        )
        agent_ids: list[str] = []
        if branch_id is not None:
            agent_ids = self._branch_agent_ids(branch_id, business_id)
            if not agent_ids:
                leads: list[dict] = []
            else:
                leads = lead_q.in_("assigned_agent", agent_ids).execute().data or []
        else:
            leads = lead_q.execute().data or []

        call_q = (
            self.db.table("travel_calls").select("*")
            .eq("business_id", biz).gte("created_at", lo).lt("created_at", hi)
        )
        if branch_id is not None:
            lead_ids = [str(l["id"]) for l in leads]
            calls = call_q.in_("lead_id", lead_ids).execute().data or [] if lead_ids else []
        else:
            calls = call_q.execute().data or []

        pkg_q = self.db.table("travel_packages").select("*").eq("business_id", biz)
        packages = pkg_q.execute().data or []
        if branch_id is not None:
            # NULL branch_id = global package, visible to every branch (0009).
            packages = [p for p in packages
                        if p.get("branch_id") in (None, str(branch_id))]

        try:
            destinations = (
                self.db.table("travel_destinations").select("id,name")
                .eq("business_id", biz).execute().data or []
            )
        except Exception as exc:                              # pragma: no cover
            logger.warning("reports: travel_destinations unreadable: %s", exc)
            destinations = []

        # payment_links is owned by another workstream (migration 0010). Query
        # DEFENSIVELY — a missing table must degrade the report, never 500 it.
        payments: list[dict] = []
        payments_available = False
        payments_error: Optional[str] = None
        try:
            payments = (
                self.db.table("payment_links").select("*")
                .eq("business_id", biz).gte("created_at", lo).lt("created_at", hi)
                .execute().data or []
            )
            payments_available = True
        except Exception as exc:
            payments_error = f"{type(exc).__name__}: {exc}"[:300]
            logger.info("reports: payment_links unavailable, degrading — %s", payments_error)

        if branch_id is not None and payments_available:
            pkg_ids = {str(p["id"]) for p in packages}
            lead_ids_set = {str(l["id"]) for l in leads}
            payments = [p for p in payments
                        if str(p.get("package_id")) in pkg_ids
                        or str(p.get("lead_id")) in lead_ids_set]

        return {
            "calls": calls, "leads": leads, "packages": packages,
            "destinations": destinations, "payments": payments,
            "payments_available": payments_available, "payments_error": payments_error,
        }

    # ── public API ────────────────────────────────────────────────────────
    def build(
        self,
        business_id: UUID,
        report_type: str,
        *,
        anchor: Optional[date] = None,
        branch_id: Optional[UUID] = None,
        tz_name: str = DEFAULT_TIMEZONE,
    ) -> dict[str, Any]:
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unknown report_type: {report_type!r}")
        tz = resolve_tz(tz_name)
        anchor = anchor or datetime.now(tz).date()
        start, end = period_bounds(report_type, anchor)
        data = self._fetch(business_id, start, end, branch_id)
        report = aggregate_report(
            report_type=report_type,
            anchor=anchor,
            calls=data["calls"],
            leads=data["leads"],
            packages=data["packages"],
            destinations=data["destinations"],
            payments=data["payments"],
            payments_available=data["payments_available"],
            payments_error=data["payments_error"],
            ai_stub_mode=self.ai_stub_mode(),
            tz_name=tz_name,
            branch_id=str(branch_id) if branch_id else None,
        )
        report["business_id"] = str(business_id)
        if branch_id is not None:
            report["scope"]["branch_link"] = (
                "travel_calls/travel_leads have no branch_id column; branch scoping "
                "is derived through travel_leads.assigned_agent → ts_users.branch_id."
            )
        return report
