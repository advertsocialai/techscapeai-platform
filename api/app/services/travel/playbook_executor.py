"""
TravelWorkflow OS — playbook executor.

Renders a UC's templates with merged context, then dispatches each channel via
the same provider router the rest of TechScape uses (Twilio · Wapi · SendGrid).
Every dispatch writes a row to travel_playbook_runs so operators can audit
which UCs fired for which booking/customer.

Compliance: dispatch reuses the live `get_router().send(...)` path, so cap +
DNC checks remain enforceable at the provider layer if configured.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.services.techscape.providers.router import get_router

from . import playbooks as pb_registry

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _fmt_inr(n: Any) -> str:
    try:
        v = int(n or 0)
    except (TypeError, ValueError):
        return str(n or "")
    return f"₹{v:,}"


def _fmt_date(d: Any) -> str:
    if not d:
        return ""
    if isinstance(d, (date, datetime)):
        return d.strftime("%d %b %Y")
    return str(d)


class PlaybookExecutor:
    """Render + dispatch a TravelWorkflow OS use case."""

    def __init__(self) -> None:
        self.db = get_supabase_admin()

    # ─────────────────────────────────────────────────────────
    # context assembly — pull data from booking + customer + biz
    # ─────────────────────────────────────────────────────────
    def build_context(
        self,
        *,
        business: dict,
        booking: Optional[dict] = None,
        customer: Optional[dict] = None,
        extra: Optional[dict] = None,
    ) -> dict[str, Any]:
        b   = business or {}
        bkg = booking or {}
        cu  = customer or {}
        ctx: dict[str, Any] = {
            "company_name": b.get("name") or b.get("business_name") or "TravelCo",
            "phone":        b.get("phone") or b.get("support_phone") or "",
            "email":        cu.get("email") or b.get("support_email") or "",
            "website":      b.get("website") or "",
            "whatsapp_num": b.get("whatsapp_number") or b.get("phone") or "",
            "emergency_line": b.get("emergency_line") or b.get("phone") or "",
            "timeofday":    self._timeofday(),
            "datetime":     _now_iso(),
            "today":        date.today().strftime("%d %b %Y"),
        }
        if cu:
            full_name = cu.get("full_name") or ""
            first = (full_name.split(" ") or [""])[0]
            ctx.update({
                "name":      cu.get("first_name") or first or "Traveller",
                "lead_name": full_name or first or "Lead Traveller",
            })
        if bkg:
            ctx.update({
                "ref":              bkg.get("booking_ref"),
                "destination":      bkg.get("destination") or "",
                "destination_upper": (bkg.get("destination") or "").upper(),
                "departure_date":   _fmt_date(bkg.get("departure_date")),
                "return_date":      _fmt_date(bkg.get("return_date")),
                "nights":           bkg.get("nights")
                                     or self._nights(bkg.get("departure_date"),
                                                    bkg.get("return_date")),
                "pax":              str(bkg.get("pax_count") or 1),
                "trip_type":        bkg.get("trip_type") or "trip",
                "package_type":     bkg.get("trip_type") or "Holiday Package",
                "grand_total":      _fmt_inr(bkg.get("grand_total_inr")),
                "deposit":          _fmt_inr(bkg.get("deposit_inr")),
                "balance":          _fmt_inr(bkg.get("balance_inr")),
                "balance_due_date": _fmt_date(bkg.get("balance_due_date")),
                "coordinator_name": bkg.get("coordinator_name") or "",
                "coordinator":      (bkg.get("coordinator_name") or "").split(" ")[0],
                "coord_phone":      bkg.get("coordinator_phone") or "",
                "visa_status":      (bkg.get("visa_status") or "").upper(),
            })
        if extra:
            ctx.update(extra)
        # Auto-derived
        ctx.setdefault("agent_name",   ctx.get("coordinator_name") or ctx["company_name"])
        ctx.setdefault("agent_phone",  ctx.get("coord_phone") or ctx["phone"])
        ctx.setdefault("agent",        ctx.get("agent_name"))
        return ctx

    # ─────────────────────────────────────────────────────────
    # render — for preview/UI
    # ─────────────────────────────────────────────────────────
    def render(self, uc_id: str, context: dict, channels: Optional[list[str]] = None) -> dict:
        pb = pb_registry.get_playbook(uc_id)
        if not pb:
            return {}
        chans = channels or pb["channels"]
        out: dict[str, Any] = {"id": uc_id.upper(), "title": pb["title"], "channels": {}}
        for ch in chans:
            r = pb_registry.render(uc_id, ch, context)
            if r:
                out["channels"][ch] = r
        return out

    # ─────────────────────────────────────────────────────────
    # dispatch — render + send via provider + write run row
    # ─────────────────────────────────────────────────────────
    async def dispatch(
        self,
        *,
        business_id:  UUID,
        uc_id:        str,
        context:      dict,
        channels:     Optional[list[str]] = None,
        to_email:     Optional[str] = None,
        to_phone:     Optional[str] = None,
        booking_id:   Optional[UUID] = None,
        customer_id:  Optional[UUID] = None,
        lead_id:      Optional[UUID] = None,
        incident_id:  Optional[UUID] = None,
        trigger_kind: str = "manual",
        dry_run:      bool = False,
    ) -> dict:
        pb = pb_registry.get_playbook(uc_id)
        if not pb:
            raise ValueError(f"unknown use case: {uc_id}")

        chans = [c for c in (channels or pb["channels"]) if c in pb["channels"]]
        rendered: dict[str, Any] = {}
        delivery: dict[str, Any] = {}
        sent_channels: list[str] = []
        failures: list[str] = []

        for ch in chans:
            r = pb_registry.render(uc_id, ch, context)
            if not r:
                continue
            rendered[ch] = r
            if dry_run:
                delivery[ch] = {"status": "dry_run"}
                continue
            try:
                if ch == "email" and to_email:
                    res = await get_router().send(
                        channel="email", to_email=to_email, to_phone=None,
                        subject=r.get("subject"), content=r.get("body"),
                    )
                elif ch == "whatsapp" and to_phone:
                    res = await get_router().send(
                        channel="whatsapp", to_email=None, to_phone=to_phone,
                        subject=None, content=r.get("content"),
                    )
                elif ch == "sms" and to_phone:
                    res = await get_router().send(
                        channel="sms", to_email=None, to_phone=to_phone,
                        subject=None, content=r.get("content"),
                    )
                elif ch == "voice":
                    # Voice dispatch is human-driven from the script; we log only.
                    res = {"provider": "script", "delivery_status": "drafted"}
                else:
                    res = {"provider": None, "delivery_status": "skipped",
                           "error": f"no recipient for {ch}"}
                delivery[ch] = res
                if res.get("delivery_status") in ("queued", "sent", "delivered", "drafted"):
                    sent_channels.append(ch)
                else:
                    failures.append(ch)
            except Exception as exc:
                logger.exception("playbook dispatch failed: %s %s", uc_id, ch)
                delivery[ch] = {"status": "failed", "error": str(exc)}
                failures.append(ch)

        status = (
            "queued" if dry_run
            else "sent" if sent_channels and not failures
            else "partial" if sent_channels and failures
            else "failed" if failures
            else "skipped"
        )

        row = self.db.table("travel_playbook_runs").insert({
            "business_id":   str(business_id),
            "use_case_id":   uc_id.upper(),
            "booking_id":    str(booking_id)  if booking_id else None,
            "customer_id":   str(customer_id) if customer_id else None,
            "lead_id":       str(lead_id)     if lead_id else None,
            "incident_id":   str(incident_id) if incident_id else None,
            "trigger_kind":  trigger_kind,
            "channels":      chans,
            "status":        status,
            "rendered":      rendered,
            "delivery":      delivery,
            "error_message": ", ".join(failures) or None,
        }).execute().data[0]
        return row

    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _timeofday() -> str:
        hr = datetime.now().hour
        return "morning" if hr < 12 else "afternoon" if hr < 17 else "evening"

    @staticmethod
    def _nights(dep: Any, ret: Any) -> int:
        try:
            d = dep if isinstance(dep, date) else datetime.fromisoformat(str(dep)).date()
            r = ret if isinstance(ret, date) else datetime.fromisoformat(str(ret)).date()
            return max(0, (r - d).days)
        except Exception:
            return 0
