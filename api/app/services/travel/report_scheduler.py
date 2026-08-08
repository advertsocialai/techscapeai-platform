"""
Report delivery scheduler (Phase 4 T5).

SAME MECHANISM AS `playbook_scheduler.py` — deliberately, not a second one.
That module established this repo's in-app scheduling convention and Phase 4
was explicitly told to extend it rather than duplicate it:

    * PULL-BASED. No APScheduler, no background thread, no timer task.
      APScheduler is not installed and is not being added.
    * A class with `due(...)` (what would fire now) and `run_due(...)`
      (fire them), mirroring PlaybookScheduler.due / .run_due.
    * Exposed as GET /reports/scheduled/due + POST /reports/scheduled/run-due,
      exactly like /playbooks/scheduled/due + /playbooks/scheduled/run-due.
    * An external cron / queue worker pokes the endpoint every few minutes.
    * De-duplication is a persisted column, not in-process state
      (PlaybookScheduler uses travel_playbook_runs; this uses
      report_schedules.last_run_at), so restarts never double-send.

Difference from PlaybookScheduler: this one is TIMEZONE-AWARE. A schedule
stores a local wall-clock `send_time` plus an IANA `timezone`
(default Asia/Kolkata), and firing is decided by converting "now" into that
zone. `compute_due()` is a PURE function of (schedules, now_utc) so the
timezone arithmetic is unit-testable with no DB and no clock.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin

from .report_service import (
    DEFAULT_TIMEZONE, ReportService, parse_dt, render_report_text, resolve_tz,
)

logger = logging.getLogger(__name__)

# How long after `send_time` a schedule stays eligible. Sized for a worker
# poking run-due every ~5 minutes, with slack for a missed tick or a restart.
DEFAULT_GRACE_MINUTES = 60

# Weekly schedules fire on Monday; monthly on the 1st. There is no
# day_of_week / day_of_month column on report_schedules, so these are the
# fixed convention — documented here and surfaced in each due-item payload.
WEEKLY_WEEKDAY = 0     # Monday (date.weekday())
MONTHLY_DAY = 1        # 1st of the month


# ══════════════════════════════════════════════════════════════════════════
# PURE SCHEDULING LOGIC
# ══════════════════════════════════════════════════════════════════════════
def _parse_time(value: Any) -> Optional[time]:
    """Postgres TIME → datetime.time. Accepts 'HH:MM', 'HH:MM:SS[.ffffff]'."""
    if value is None:
        return None
    if isinstance(value, time):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        parts = raw.split(":")
        try:
            return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            return None


def period_key(report_type: str, local_day: date) -> str:
    """Stable identifier for the period a firing belongs to. PURE.

    De-duplication key: a schedule fires at most once per key. Weekly uses the
    ISO week so a Sunday/Monday boundary can't double-fire.
    """
    if report_type == "daily":
        return f"daily:{local_day.isoformat()}"
    if report_type == "weekly":
        iso = local_day.isocalendar()
        return f"weekly:{iso[0]}-W{iso[1]:02d}"
    if report_type == "monthly":
        return f"monthly:{local_day.year}-{local_day.month:02d}"
    raise ValueError(f"Unknown report_type: {report_type!r}")


def evaluate_schedule(
    schedule: dict,
    now_utc: datetime,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> dict[str, Any]:
    """Decide whether one schedule should fire right now. PURE.

    Returns a verdict dict — always, whether due or not — so
    GET /reports/scheduled/due can explain a *non*-firing schedule instead of
    silently omitting it.
    """
    tz_name = schedule.get("timezone") or DEFAULT_TIMEZONE
    tz = resolve_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    local_day = local_now.date()
    rtype = str(schedule.get("report_type") or "")

    verdict: dict[str, Any] = {
        "schedule_id": schedule.get("id"),
        "business_id": schedule.get("business_id"),
        "branch_id": schedule.get("branch_id"),
        "report_type": rtype,
        "delivery_channel": schedule.get("delivery_channel"),
        "timezone": tz_name,
        "local_now": local_now.isoformat(),
        "due": False,
        "reason": None,
        "period_key": None,
        "anchor": None,
    }

    if not schedule.get("is_active", True):
        verdict["reason"] = "inactive"
        return verdict
    if rtype not in ("daily", "weekly", "monthly"):
        verdict["reason"] = f"unknown_report_type:{rtype}"
        return verdict

    send_time = _parse_time(schedule.get("send_time"))
    if send_time is None:
        verdict["reason"] = "invalid_send_time"
        return verdict
    verdict["send_time"] = send_time.isoformat()

    # Calendar gate: which local day is this schedule allowed to fire on?
    if rtype == "weekly" and local_day.weekday() != WEEKLY_WEEKDAY:
        verdict["reason"] = "not_the_weekly_send_day (Monday)"
        return verdict
    if rtype == "monthly" and local_day.day != MONTHLY_DAY:
        verdict["reason"] = "not_the_monthly_send_day (1st)"
        return verdict

    # Wall-clock gate: [send_time, send_time + grace) in local time.
    fire_at = datetime.combine(local_day, send_time, tzinfo=tz)
    window_end = fire_at + timedelta(minutes=grace_minutes)
    if local_now < fire_at:
        verdict["reason"] = "before_send_time"
        verdict["next_fire_at_local"] = fire_at.isoformat()
        return verdict
    if local_now >= window_end:
        verdict["reason"] = f"missed_window (grace {grace_minutes}m elapsed)"
        return verdict

    # De-duplication gate: already fired for this period?
    key = period_key(rtype, local_day)
    verdict["period_key"] = key
    last_run = parse_dt(schedule.get("last_run_at"))
    if last_run is not None:
        last_local_day = last_run.astimezone(tz).date()
        if period_key(rtype, last_local_day) == key:
            verdict["reason"] = "already_ran_this_period"
            verdict["last_run_at"] = last_run.isoformat()
            return verdict

    # The report covers the period that just CLOSED, not the one in progress:
    # a Monday-morning weekly report is about last week.
    if rtype == "daily":
        anchor = local_day - timedelta(days=1)
    elif rtype == "weekly":
        anchor = local_day - timedelta(days=7)
    else:
        anchor = local_day.replace(day=1) - timedelta(days=1)

    verdict["due"] = True
    verdict["reason"] = "due"
    verdict["anchor"] = anchor.isoformat()
    return verdict


def compute_due(
    schedules: list[dict],
    now_utc: datetime,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
    include_skipped: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate a batch of schedules. PURE — no DB, no clock, no network."""
    verdicts = [evaluate_schedule(s, now_utc, grace_minutes=grace_minutes)
                for s in schedules]
    if include_skipped:
        return verdicts
    return [v for v in verdicts if v["due"]]


# ══════════════════════════════════════════════════════════════════════════
# IO SHELL — mirrors PlaybookScheduler's shape exactly
# ══════════════════════════════════════════════════════════════════════════
class ReportScheduler:
    def __init__(self) -> None:
        self.db = get_supabase_admin()
        self.reports = ReportService()

    def _schedules(self, business_id: Optional[UUID]) -> list[dict]:
        q = self.db.table("report_schedules").select("*").eq("is_active", True)
        if business_id is not None:
            q = q.eq("business_id", str(business_id))
        return q.execute().data or []

    def due(
        self,
        business_id: Optional[UUID] = None,
        *,
        now_utc: Optional[datetime] = None,
        grace_minutes: int = DEFAULT_GRACE_MINUTES,
        include_skipped: bool = False,
    ) -> list[dict[str, Any]]:
        """Schedules whose local send_time window is open right now."""
        now_utc = now_utc or datetime.now(dt_timezone.utc)
        return compute_due(
            self._schedules(business_id), now_utc,
            grace_minutes=grace_minutes, include_skipped=include_skipped,
        )

    async def run_due(
        self,
        business_id: Optional[UUID] = None,
        *,
        now_utc: Optional[datetime] = None,
        grace_minutes: int = DEFAULT_GRACE_MINUTES,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Build + deliver every due report.

        `dry_run=True` (the default, same default as
        /playbooks/scheduled/run-due) builds the report and renders the message
        but performs NO outbound send and does NOT stamp last_run_at, so it is
        safe to poke repeatedly.
        """
        now_utc = now_utc or datetime.now(dt_timezone.utc)
        items = self.due(business_id, now_utc=now_utc, grace_minutes=grace_minutes)
        dispatched: list[dict[str, Any]] = []

        for item in items:
            entry: dict[str, Any] = {
                "schedule_id": item["schedule_id"],
                "report_type": item["report_type"],
                "delivery_channel": item["delivery_channel"],
                "period_key": item["period_key"],
                "anchor": item["anchor"],
                "dry_run": dry_run,
            }
            try:
                report = self.reports.build(
                    UUID(str(item["business_id"])),
                    item["report_type"],
                    anchor=date.fromisoformat(item["anchor"]),
                    branch_id=UUID(str(item["branch_id"])) if item.get("branch_id") else None,
                    tz_name=item["timezone"],
                )
            except Exception as exc:
                logger.exception("report_scheduler: build failed for %s", item["schedule_id"])
                entry["status"] = "build_failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
                dispatched.append(entry)
                continue

            schedule = (
                self.db.table("report_schedules").select("*")
                .eq("id", str(item["schedule_id"])).limit(1).execute().data or []
            )
            recipients = (schedule[0].get("recipients") if schedule else []) or []
            body = render_report_text(report)
            entry["recipients"] = recipients
            entry["message_preview"] = body[:400]
            entry["warnings"] = report.get("warnings", [])

            if dry_run:
                entry["status"] = "dry_run"
                dispatched.append(entry)
                continue

            result = await deliver_report(
                channel=str(item["delivery_channel"]),
                recipients=list(recipients),
                body=body,
                report=report,
                dry_run=False,
                business_id=str(item["business_id"]),
            )
            entry["status"] = result["status"]
            entry["delivery"] = result
            if result["status"] in ("sent", "queued"):
                self.db.table("report_schedules").update(
                    {"last_run_at": now_utc.isoformat()}
                ).eq("id", str(item["schedule_id"])).execute()
                entry["last_run_at"] = now_utc.isoformat()
            dispatched.append(entry)

        return {
            "now_utc": now_utc.isoformat(),
            "grace_minutes": grace_minutes,
            "dry_run": dry_run,
            "dispatched": dispatched,
            "count": len(dispatched),
        }


# ══════════════════════════════════════════════════════════════════════════
# DELIVERY — WhatsApp service is owned by another workstream
# ══════════════════════════════════════════════════════════════════════════
def load_whatsapp_sender(business_id: str):
    """Resolve the WhatsApp send capability at CALL TIME, never at import time.

    `app/services/whatsapp/` is owned by a different workstream (Phase 4 T3).
    Importing it at module scope would make this module — and therefore the
    reports router, and therefore the whole app — fail to import if those files
    are missing, half-written, or land after this one. So the import lives
    inside this function body behind try/except ImportError and degrades to
    (None, reason) instead of raising.

    Preferred contract (what T3 actually shipped):
        from app.services.whatsapp import get_whatsapp_provider
        provider = get_whatsapp_provider(business_id)
        await provider.send_freeform(to, text)     # inside the 24h window
        await provider.send_template(to, name, lang, components)

    Older / alternative shapes are still probed after it, so this keeps working
    if that package is refactored.

    Returns (send_coroutine_factory, description) or (None, reason).
    The factory takes (to: str, text: str) and returns an awaitable.
    """
    tried: list[str] = []

    # 1) The real T3 contract: a provider factory.
    tried.append("app.services.whatsapp.get_whatsapp_provider")
    try:
        from app.services.whatsapp import get_whatsapp_provider  # noqa: PLC0415
    except ImportError:
        get_whatsapp_provider = None                             # type: ignore[assignment]
    except Exception as exc:            # a broken module must not 500 the report
        logger.warning("whatsapp package raised on import: %s", exc)
        get_whatsapp_provider = None                             # type: ignore[assignment]
    if get_whatsapp_provider is not None:
        try:
            provider = get_whatsapp_provider(business_id)
        except Exception as exc:
            return None, f"get_whatsapp_provider raised: {type(exc).__name__}: {exc}"[:300]

        def _send(to: str, text: str):
            return provider.send_freeform(to, text)

        return _send, f"app.services.whatsapp.get_whatsapp_provider → {type(provider).__name__}.send_freeform"

    # 2) Fallback shapes, in case the package is refactored to a flat function.
    for module_path, attr in (
        ("app.services.whatsapp", "send_message"),
        ("app.services.whatsapp", "send_whatsapp_message"),
        ("app.services.whatsapp.client", "send_message"),
    ):
        dotted = f"{module_path}.{attr}"
        tried.append(dotted)
        try:
            module = __import__(module_path, fromlist=[attr])
        except ImportError:
            continue
        except Exception as exc:
            logger.warning("whatsapp module %s raised on import: %s", module_path, exc)
            continue
        fn = getattr(module, attr, None)
        if callable(fn):
            def _send(to: str, text: str, _fn=fn):
                return _fn(to=to, body=text)
            return _send, dotted

    return None, ("whatsapp send capability not found; tried " + ", ".join(tried))


async def deliver_report(
    *,
    channel: str,
    recipients: list[str],
    body: str,
    report: dict,
    dry_run: bool = True,
    business_id: str = "",
) -> dict[str, Any]:
    """Send a rendered report over `channel`.

    Nothing leaves the process while `dry_run` is True, which is the default at
    every call site. In this environment there are no WhatsApp credentials, so
    even a non-dry run resolves to T3's StubWhatsAppProvider, which writes an
    outbox row and transmits nothing. No real message has been sent from this
    code path.
    """
    base: dict[str, Any] = {
        "channel": channel,
        "recipients": recipients,
        "body_chars": len(body),
        "dry_run": dry_run,
    }
    if not recipients:
        return {**base, "status": "skipped", "detail": "no recipients configured"}
    if dry_run:
        return {**base, "status": "dry_run", "detail": "nothing sent (dry_run=true)"}

    if channel == "whatsapp":
        sender, info = load_whatsapp_sender(business_id)
        if sender is None:
            return {**base, "status": "unavailable", "detail": info}
        results = []
        for to in recipients:
            try:
                out = sender(to, body)
                if hasattr(out, "__await__"):
                    out = await out
                results.append({"to": to, "ok": True, "result": str(out)[:300]})
            except Exception as exc:
                # SessionWindowClosed is the expected, actionable failure for an
                # unsolicited report: outside WhatsApp's 24h customer-service
                # window only a pre-approved TEMPLATE may be sent. Matched by
                # class name so this module never has to import the whatsapp
                # package at module scope.
                kind = type(exc).__name__
                detail = f"{kind}: {exc}"[:300]
                if kind == "SessionWindowClosed":
                    detail += (" — a scheduled report is an unsolicited message; "
                               "register a Meta-approved report template and send "
                               "it via provider.send_template().")
                else:
                    logger.exception("report whatsapp send failed for %s", to)
                results.append({"to": to, "ok": False, "error": detail,
                                "error_kind": kind})
        ok = all(r["ok"] for r in results)
        return {**base, "status": "sent" if ok else "partial_failure",
                "sender": info, "results": results}

    if channel == "email":
        # Email delivery is not implemented here — no mail transport is
        # configured in this repo and adding one is out of scope for T5.
        return {**base, "status": "unavailable",
                "detail": "email delivery not implemented (no mail transport configured)"}

    return {**base, "status": "unavailable", "detail": f"unknown channel {channel!r}"}
