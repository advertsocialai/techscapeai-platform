"""
Analytics reports + report-schedule CRUD (Phase 4 T4 + T5).

────────────────────────────────────────────────────────────────────────────
REGISTRATION (one line, owned by whoever maintains routers/travel/__init__.py)
────────────────────────────────────────────────────────────────────────────
This router declares FULL paths (`/reports/...` and `/report-schedules/...`)
because it serves two path roots, so it must be mounted WITHOUT a prefix:

    from .reports import router as reports_router          # Phase 4 T4/T5
    travel_router.include_router(reports_router, tags=["Travel · Reports"])

Everything then lives under /travel/v1/reports* as usual. This file does not
touch __init__.py — that file is owned elsewhere.

────────────────────────────────────────────────────────────────────────────
ENDPOINTS
────────────────────────────────────────────────────────────────────────────
  GET    /reports/daily                    viewer+   aggregate for a day
  GET    /reports/weekly                   viewer+   aggregate for an ISO week
  GET    /reports/monthly                  viewer+   aggregate for a month
  GET    /reports/scheduled/due            viewer+   what would fire now
  POST   /reports/scheduled/run-due        manager+  fire due reports
  GET    /reports/{schedule_id}/pdf        viewer+   printable HTML (see below)
  POST   /reports/{schedule_id}/send-whatsapp
                                           manager+  deliver via WhatsApp
  GET    /report-schedules                 viewer+   list
  POST   /report-schedules                 manager+  create
  GET    /report-schedules/{id}            viewer+   read one
  PATCH  /report-schedules/{id}            manager+  update
  DELETE /report-schedules/{id}            manager+  delete

RBAC: reads are `require_role("viewer")`, writes/sends `require_role("manager")`
(hierarchy, per core/deps.py — manager also admits admin/super_admin).
Everything is scoped by the caller's own `business_id`. A row belonging to
another business, or a branch_id outside the caller's business/branch scope,
returns 404 — never 403 — so scope can't be probed by status code, matching
leads.py.

`{schedule_id}` is a report_schedules row: those two endpoints render/deliver
the report that schedule describes. There is no persisted "report" table —
reports are computed on demand from travel_calls / travel_leads /
travel_packages / payment_links.

────────────────────────────────────────────────────────────────────────────
PDF DECISION — read this before filing a bug that "the PDF endpoint isn't PDF"
────────────────────────────────────────────────────────────────────────────
GET /reports/{schedule_id}/pdf returns **HTML**, media type text/html, with
`X-Report-Format: html` and `X-PDF-Conversion: deferred` response headers and
a visible banner in the document body.

Neither reportlab nor weasyprint is installed, and adding either is a heavy
dependency (weasyprint pulls cairo/pango system libraries) that this task was
explicitly told not to introduce. Hand-rolling a minimal PDF writer would only
produce untyped, unstyled text and would be a worse artefact than the HTML.

So: the HTML is deterministic and print-ready (`@media print` rules included);
Cmd/Ctrl-P → "Save as PDF" produces the document. Asking for real PDF bytes
(`?format=pdf`) returns 501 with that explanation rather than pretending.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone as dt_timezone
from typing import Any, Literal, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from app.core.deps import require_role
from app.database import get_supabase_admin
from app.services.travel.report_scheduler import (
    DEFAULT_GRACE_MINUTES, ReportScheduler, deliver_report,
)
from app.services.travel.report_service import (
    DEFAULT_TIMEZONE, ReportService, render_report_html,
    render_report_text, resolve_tz,
)

router = APIRouter()

_VIEWER_PLUS = require_role("viewer")
_MANAGER_PLUS = require_role("manager")

ReportType = Literal["daily", "weekly", "monthly"]
DeliveryChannel = Literal["whatsapp", "email"]


# ══════════════════════════════════════════════════════════════════════════
# Pydantic models (kept in the router file, per this repo's ai_config.py)
# ══════════════════════════════════════════════════════════════════════════
class ReportScheduleIn(BaseModel):
    report_type: ReportType
    delivery_channel: DeliveryChannel
    send_time: time
    recipients: list[str] = Field(default_factory=list)
    branch_id: Optional[UUID] = None
    timezone: str = DEFAULT_TIMEZONE
    is_active: bool = True

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v

    @field_validator("recipients")
    @classmethod
    def _clean_recipients(cls, v: list[str]) -> list[str]:
        out = [str(r).strip() for r in v if str(r).strip()]
        if len(out) > 50:
            raise ValueError("At most 50 recipients per schedule")
        return out


class ReportSchedulePatch(BaseModel):
    report_type: Optional[ReportType] = None
    delivery_channel: Optional[DeliveryChannel] = None
    send_time: Optional[time] = None
    recipients: Optional[list[str]] = None
    branch_id: Optional[UUID] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v


class ReportScheduleOut(BaseModel):
    id: UUID
    business_id: UUID
    report_type: str
    branch_id: Optional[UUID] = None
    delivery_channel: str
    recipients: list[str] = Field(default_factory=list)
    send_time: str
    timezone: str
    is_active: bool
    last_run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SendWhatsAppIn(BaseModel):
    # Defaults to a dry run on purpose: no WhatsApp credentials exist in this
    # environment and nothing should leave the process by accident.
    dry_run: bool = True
    anchor_date: Optional[date] = None
    recipients_override: Optional[list[str]] = None


# ══════════════════════════════════════════════════════════════════════════
# Scoping helpers — out-of-scope resolves to 404, never 403
# ══════════════════════════════════════════════════════════════════════════
def _resolve_branch(user: dict, requested: Optional[UUID]) -> Optional[UUID]:
    """Effective branch filter for this caller, or 404 if out of scope.

    Mirrors ai_config.py: a branch-pinned user (`ts_users.branch_id` set) is
    locked to their own branch. Asking for a different one is indistinguishable
    from asking for a branch that does not exist — both are 404.
    """
    own = user.get("branch_id")
    if own:
        if requested is not None and str(requested) != str(own):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
        return UUID(str(own))
    if requested is None:
        return None
    if not ReportService().branch_exists(requested, UUID(user["business_id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    return requested


def _get_schedule_scoped(schedule_id: UUID, user: dict) -> dict:
    db = get_supabase_admin()
    rows = (
        db.table("report_schedules").select("*")
        .eq("id", str(schedule_id))
        .eq("business_id", str(user["business_id"]))
        .limit(1).execute().data or []
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report schedule not found")
    row = rows[0]
    own = user.get("branch_id")
    # A branch-pinned user only sees their own branch's (or business-wide)
    # schedules. Anything else is 404.
    if own and row.get("branch_id") and str(row["branch_id"]) != str(own):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report schedule not found")
    return row


def _serialize(row: dict) -> dict:
    out = dict(row)
    st = out.get("send_time")
    out["send_time"] = st.isoformat() if isinstance(st, time) else str(st or "")
    out["recipients"] = out.get("recipients") or []
    return out


def _build(user: dict, report_type: str, when: Optional[date],
           branch: Optional[UUID], tz_name: str) -> dict[str, Any]:
    svc = ReportService()
    anchor = when or datetime.now(resolve_tz(tz_name)).date()
    return svc.build(
        UUID(user["business_id"]), report_type,
        anchor=anchor, branch_id=branch, tz_name=tz_name,
    )


# ══════════════════════════════════════════════════════════════════════════
# T4 — report generation
# ══════════════════════════════════════════════════════════════════════════
@router.get("/reports/daily", tags=["Travel · Reports"])
def daily_report(
    date_: Optional[date] = Query(default=None, alias="date"),
    branch_id: Optional[UUID] = Query(default=None),
    tz: str = Query(default=DEFAULT_TIMEZONE, description="IANA timezone"),
    user: dict = Depends(_VIEWER_PLUS),
):
    """Call volume, conversion funnel, top packages and (if available) revenue
    for a single day. Sentiment figures are labelled stub-derived while the
    Phase 3 pipeline has no ANTHROPIC_API_KEY — see the report's
    `data_quality` and `warnings` blocks."""
    return _build(user, "daily", date_, _resolve_branch(user, branch_id), tz)


@router.get("/reports/weekly", tags=["Travel · Reports"])
def weekly_report(
    date_: Optional[date] = Query(default=None, alias="date",
                                  description="Any date inside the ISO week"),
    branch_id: Optional[UUID] = Query(default=None),
    tz: str = Query(default=DEFAULT_TIMEZONE),
    user: dict = Depends(_VIEWER_PLUS),
):
    return _build(user, "weekly", date_, _resolve_branch(user, branch_id), tz)


@router.get("/reports/monthly", tags=["Travel · Reports"])
def monthly_report(
    date_: Optional[date] = Query(default=None, alias="date",
                                  description="Any date inside the month"),
    branch_id: Optional[UUID] = Query(default=None),
    tz: str = Query(default=DEFAULT_TIMEZONE),
    user: dict = Depends(_VIEWER_PLUS),
):
    return _build(user, "monthly", date_, _resolve_branch(user, branch_id), tz)


# ── Scheduler poke endpoints — literal paths declared BEFORE /{schedule_id} ─
@router.get("/reports/scheduled/due", tags=["Travel · Reports"])
def scheduled_due(
    include_skipped: bool = Query(default=False,
                                  description="Also return non-firing schedules with a reason"),
    grace_minutes: int = Query(default=DEFAULT_GRACE_MINUTES, ge=1, le=1440),
    user: dict = Depends(_VIEWER_PLUS),
):
    """Which of this business's schedules would fire right now.

    Same shape as GET /playbooks/scheduled/due — pull-based, no in-process
    timer. An external cron pokes run-due below.
    """
    return ReportScheduler().due(
        UUID(user["business_id"]),
        grace_minutes=grace_minutes, include_skipped=include_skipped,
    )


@router.post("/reports/scheduled/run-due", tags=["Travel · Reports"])
async def scheduled_run_due(
    dry_run: bool = Query(default=True),
    grace_minutes: int = Query(default=DEFAULT_GRACE_MINUTES, ge=1, le=1440),
    user: dict = Depends(_MANAGER_PLUS),
):
    """Build + deliver every due report for this business.

    `dry_run` defaults to true (same as /playbooks/scheduled/run-due): the
    reports are built and messages rendered, but nothing is sent and
    `last_run_at` is not stamped.
    """
    return await ReportScheduler().run_due(
        UUID(user["business_id"]), grace_minutes=grace_minutes, dry_run=dry_run,
    )


@router.get("/reports/{schedule_id}/pdf", response_class=HTMLResponse,
            tags=["Travel · Reports"])
def report_pdf(
    schedule_id: UUID,
    date_: Optional[date] = Query(default=None, alias="date"),
    format: str = Query(default="html", pattern="^(html|pdf)$"),
    user: dict = Depends(_VIEWER_PLUS),
):
    """Printable rendering of the report this schedule describes.

    RETURNS HTML, NOT PDF. See the module docstring's PDF DECISION section:
    no PDF engine is installed and none was added, so `format=pdf` returns 501
    instead of claiming a capability that does not exist. The HTML is
    deterministic and carries `@media print` rules — browser "Save as PDF"
    produces the document.
    """
    schedule = _get_schedule_scoped(schedule_id, user)
    if format == "pdf":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Server-side PDF generation is not implemented: no PDF engine "
            "(reportlab / weasyprint) is installed in this deployment and adding "
            "one is out of scope. Use format=html (the default) and print to PDF "
            "from the browser.",
        )
    branch = UUID(str(schedule["branch_id"])) if schedule.get("branch_id") else None
    report = _build(user, str(schedule["report_type"]), date_, branch,
                    str(schedule.get("timezone") or DEFAULT_TIMEZONE))
    report["schedule_id"] = str(schedule_id)
    html = render_report_html(report, business_name=str(user.get("business_name") or ""))
    return HTMLResponse(
        content=html,
        headers={
            "X-Report-Format": "html",
            "X-PDF-Conversion": "deferred",
            "X-Report-Schedule-Id": str(schedule_id),
        },
    )


# ══════════════════════════════════════════════════════════════════════════
# T5 — delivery
# ══════════════════════════════════════════════════════════════════════════
@router.post("/reports/{schedule_id}/send-whatsapp", tags=["Travel · Reports"])
async def send_report_whatsapp(
    schedule_id: UUID,
    body: SendWhatsAppIn = SendWhatsAppIn(),
    user: dict = Depends(_MANAGER_PLUS),
):
    """Deliver this schedule's report over WhatsApp.

    The WhatsApp send capability lives in `app/services/whatsapp/`, owned by a
    different workstream. It is imported lazily inside
    `report_scheduler.load_whatsapp_sender()` (function body, try/except
    ImportError) so this router imports cleanly whether or not those files
    exist yet; if they are missing the response is
    `{"status": "unavailable", ...}` with a 200, not an import crash.

    As of this writing that package HAS landed and resolves to
    `get_whatsapp_provider(business_id).send_freeform(...)`, which — with no
    Meta credentials configured — is `StubWhatsAppProvider`: it writes a
    `whatsapp_outbox` row and transmits nothing.

    Note the 24-hour rule: a scheduled report is an UNSOLICITED message, so
    outside WhatsApp's customer-service window `send_freeform` raises
    `SessionWindowClosed`. That surfaces as a structured per-recipient error
    telling the operator to register a Meta-approved report template — it is
    not a crash, and the endpoint still returns the rendered report.

    `dry_run` defaults to TRUE and no real message has been sent from this code
    path — there are no WhatsApp credentials in this environment.
    """
    schedule = _get_schedule_scoped(schedule_id, user)
    branch = UUID(str(schedule["branch_id"])) if schedule.get("branch_id") else None
    tz_name = str(schedule.get("timezone") or DEFAULT_TIMEZONE)
    report = _build(user, str(schedule["report_type"]), body.anchor_date, branch, tz_name)
    text = render_report_text(report, business_name=str(user.get("business_name") or ""))

    recipients = body.recipients_override
    if recipients is None:
        recipients = list(schedule.get("recipients") or [])
    recipients = [str(r).strip() for r in recipients if str(r).strip()]

    result = await deliver_report(
        channel="whatsapp", recipients=recipients, body=text,
        report=report, dry_run=body.dry_run,
        business_id=str(user["business_id"]),
    )
    if result["status"] in ("sent", "queued"):
        get_supabase_admin().table("report_schedules").update(
            {"last_run_at": datetime.now(dt_timezone.utc).isoformat()}
        ).eq("id", str(schedule_id)).eq(
            "business_id", str(user["business_id"])
        ).execute()

    return {
        "schedule_id": str(schedule_id),
        "report_type": report["report_type"],
        "period": report["period"],
        "message": text,
        "delivery": result,
        "warnings": report.get("warnings", []),
    }


# ══════════════════════════════════════════════════════════════════════════
# T4 — /report-schedules CRUD
# ══════════════════════════════════════════════════════════════════════════
@router.get("/report-schedules", response_model=list[ReportScheduleOut],
            tags=["Travel · Report Schedules"])
def list_schedules(
    report_type: Optional[ReportType] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(_VIEWER_PLUS),
):
    db = get_supabase_admin()
    q = db.table("report_schedules").select("*").eq("business_id", str(user["business_id"]))
    if report_type is not None:
        q = q.eq("report_type", report_type)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    own = user.get("branch_id")
    rows = q.order("created_at", desc=True).limit(limit).execute().data or []
    if own:
        rows = [r for r in rows
                if r.get("branch_id") in (None, str(own))]
    return [_serialize(r) for r in rows]


@router.post("/report-schedules", response_model=ReportScheduleOut,
             status_code=status.HTTP_201_CREATED, tags=["Travel · Report Schedules"])
def create_schedule(payload: ReportScheduleIn, user: dict = Depends(_MANAGER_PLUS)):
    branch = _resolve_branch(user, payload.branch_id)
    db = get_supabase_admin()
    row = db.table("report_schedules").insert({
        "business_id": str(user["business_id"]),
        "report_type": payload.report_type,
        "branch_id": str(branch) if branch else None,
        "delivery_channel": payload.delivery_channel,
        "recipients": payload.recipients,
        "send_time": payload.send_time.isoformat(),
        "timezone": payload.timezone,
        "is_active": payload.is_active,
    }).execute().data
    if not row:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "Failed to create report schedule")
    return _serialize(row[0])


@router.get("/report-schedules/{schedule_id}", response_model=ReportScheduleOut,
            tags=["Travel · Report Schedules"])
def get_schedule(schedule_id: UUID, user: dict = Depends(_VIEWER_PLUS)):
    return _serialize(_get_schedule_scoped(schedule_id, user))


@router.patch("/report-schedules/{schedule_id}", response_model=ReportScheduleOut,
              tags=["Travel · Report Schedules"])
def update_schedule(schedule_id: UUID, payload: ReportSchedulePatch,
                    user: dict = Depends(_MANAGER_PLUS)):
    _get_schedule_scoped(schedule_id, user)          # 404 if out of scope
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update")

    patch: dict[str, Any] = {}
    for key, value in data.items():
        if key == "branch_id":
            branch = _resolve_branch(user, value)
            patch["branch_id"] = str(branch) if branch else None
        elif key == "send_time":
            patch["send_time"] = value.isoformat() if isinstance(value, time) else str(value)
        elif key == "recipients":
            patch["recipients"] = [str(r).strip() for r in (value or []) if str(r).strip()]
        else:
            patch[key] = value

    db = get_supabase_admin()
    updated = (
        db.table("report_schedules").update(patch)
        .eq("id", str(schedule_id)).eq("business_id", str(user["business_id"]))
        .execute().data
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report schedule not found")
    return _serialize(updated[0])


@router.delete("/report-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["Travel · Report Schedules"])
def delete_schedule(schedule_id: UUID, user: dict = Depends(_MANAGER_PLUS)):
    _get_schedule_scoped(schedule_id, user)          # 404 if out of scope
    get_supabase_admin().table("report_schedules").delete().eq(
        "id", str(schedule_id)).eq("business_id", str(user["business_id"])).execute()
    return None
