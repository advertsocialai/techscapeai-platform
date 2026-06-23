"""
Inbound webhook handlers for delivery-status callbacks.

These do NOT require auth (callbacks come from providers); instead they verify
HMAC / signature headers per provider. Stub mode accepts unsigned requests.

Endpoints:
  POST /webhooks/twilio/status   — message status (queued/sent/delivered/failed)
  POST /webhooks/twilio/voice    — voice call status (initiated/ringing/answered/completed)
  POST /webhooks/sendgrid/events — SendGrid Event Webhook (array of events)
  POST /webhooks/wapi/status     — Wapi delivery status
  POST /webhooks/event           — generic external trigger that queues a workflow
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.database import get_supabase_admin
from app.services.techscape.execution_service import ExecutionService
from app.services.techscape.webhooks import (
    SENDGRID_EVENT_MAP, TWILIO_STATUS_MAP, WAPI_STATUS_MAP,
    verify_sendgrid_signature, verify_twilio_signature, verify_wapi_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────
def _update_log_by_provider_id(
    *, provider: str, provider_message_id: str, patch: dict[str, Any],
) -> int:
    db = get_supabase_admin()
    r = (
        db.table("ts_communication_logs").update(patch)
        .eq("provider", provider)
        .eq("provider_message_id", provider_message_id)
        .execute()
    )
    return len(r.data or [])


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── Twilio ───────────────────────────────────────────────────────
@router.post("/twilio/status")
async def twilio_status(request: Request,
                        x_twilio_signature: str | None = Header(default=None,
                                                                 alias="X-Twilio-Signature")):
    form = dict((await request.form()).multi_items())
    full_url = str(request.url)
    if not verify_twilio_signature(url=full_url, params=form, signature=x_twilio_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid Twilio signature")

    sid = form.get("MessageSid") or form.get("SmsSid")
    raw_status = form.get("MessageStatus") or form.get("SmsStatus") or ""
    if not sid:
        return {"ok": True, "ignored": True}
    mapped = TWILIO_STATUS_MAP.get(raw_status.lower(), "sent")
    patch: dict[str, Any] = {"delivery_status": mapped}
    if mapped == "delivered":
        patch["delivered_at"] = _now_iso()
    if mapped in ("failed", "bounced"):
        patch["error_message"] = form.get("ErrorMessage") or raw_status
        patch["error_code"]    = form.get("ErrorCode")
    n = _update_log_by_provider_id(provider="twilio", provider_message_id=sid, patch=patch)
    return {"ok": True, "updated": n}


@router.post("/twilio/voice")
async def twilio_voice(request: Request,
                       x_twilio_signature: str | None = Header(default=None,
                                                                alias="X-Twilio-Signature")):
    form = dict((await request.form()).multi_items())
    full_url = str(request.url)
    if not verify_twilio_signature(url=full_url, params=form, signature=x_twilio_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid Twilio signature")

    sid = form.get("CallSid")
    raw_status = (form.get("CallStatus") or "").lower()
    if not sid:
        return {"ok": True, "ignored": True}
    mapped = TWILIO_STATUS_MAP.get(raw_status, "sent")
    patch: dict[str, Any] = {"delivery_status": mapped}
    if mapped == "delivered":
        patch["delivered_at"] = _now_iso()
    if form.get("CallDuration"):
        try:
            secs = int(form["CallDuration"])
            patch["cost"] = round(secs / 60.0 * 0.015, 4)
        except ValueError:
            pass
    n = _update_log_by_provider_id(provider="twilio", provider_message_id=sid, patch=patch)
    return {"ok": True, "updated": n}


# ── SendGrid Event Webhook ───────────────────────────────────────
@router.post("/sendgrid/events")
async def sendgrid_events(request: Request,
                          signature:  str | None = Header(default=None,
                                                          alias="X-Twilio-Email-Event-Webhook-Signature"),
                          timestamp:  str | None = Header(default=None,
                                                          alias="X-Twilio-Email-Event-Webhook-Timestamp")):
    body = await request.body()
    if not verify_sendgrid_signature(body=body, signature=signature, timestamp=timestamp):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid SendGrid signature")

    try:
        events = (await request.json()) or []
    except Exception:
        events = []
    if not isinstance(events, list):
        events = [events]

    updated = 0
    for evt in events:
        sg_id = evt.get("sg_message_id") or evt.get("smtp-id") or evt.get("message_id")
        if not sg_id:
            continue
        # SendGrid's sg_message_id has a suffix; X-Message-Id from send is the prefix
        sg_id = sg_id.split(".")[0]
        mapped = SENDGRID_EVENT_MAP.get((evt.get("event") or "").lower())
        if not mapped:
            continue
        patch: dict[str, Any] = {"delivery_status": mapped}
        if mapped == "delivered":
            patch["delivered_at"] = _now_iso()
        if mapped == "opened":
            patch["opened_at"] = _now_iso()
        if mapped == "bounced":
            patch["bounced_at"]    = _now_iso()
            patch["error_message"] = evt.get("reason") or "bounced"
        if mapped == "failed":
            patch["error_message"] = evt.get("reason") or "dropped"
        updated += _update_log_by_provider_id(
            provider="sendgrid", provider_message_id=sg_id, patch=patch,
        )
    return {"ok": True, "updated": updated}


# ── Wapi ─────────────────────────────────────────────────────────
@router.post("/wapi/status")
async def wapi_status(request: Request,
                      x_wapi_signature: str | None = Header(default=None,
                                                             alias="X-Wapi-Signature")):
    body = await request.body()
    if not verify_wapi_signature(body=body, signature=x_wapi_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid Wapi signature")

    try:
        evt = await request.json()
    except Exception:
        evt = {}
    msg_id     = evt.get("message_id") or evt.get("id")
    raw_status = (evt.get("status") or "").lower()
    if not msg_id:
        return {"ok": True, "ignored": True}
    mapped = WAPI_STATUS_MAP.get(raw_status, "sent")
    patch: dict[str, Any] = {"delivery_status": mapped}
    if mapped == "delivered":
        patch["delivered_at"] = _now_iso()
    if mapped == "opened":
        patch["opened_at"] = _now_iso()
    if mapped == "replied":
        patch["replied_at"]    = _now_iso()
        patch["reply_content"] = evt.get("text") or evt.get("body")
    if mapped == "failed":
        patch["error_message"] = evt.get("reason") or "wapi failed"
    n = _update_log_by_provider_id(provider="wapi", provider_message_id=msg_id, patch=patch)
    return {"ok": True, "updated": n}


# ── Generic external event ───────────────────────────────────────
@router.post("/event")
async def external_event(request: Request,
                         x_event_signature: str | None = Header(default=None,
                                                                 alias="X-Event-Signature")):
    """
    External systems POST events (booking.created, lead.created, etc.).
    We look up workflows whose trigger matches and start them.

    Body shape:
      {
        "business_id": "uuid",
        "event_type":  "booking.created",
        "event_data":  { ... }
      }
    """
    body = await request.body()
    if not verify_wapi_signature(body=body, signature=x_event_signature):  # reuse HMAC-SHA256 path
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid json")

    business_id = payload.get("business_id")
    event_type  = payload.get("event_type")
    if not business_id or not event_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "business_id and event_type required")

    db = get_supabase_admin()
    workflows = (
        db.table("ts_workflows").select("id")
        .eq("business_id", business_id)
        .eq("trigger_type", "event_based")
        .eq("trigger_event_type", event_type)
        .eq("is_active", True)
        .eq("is_archived", False)
        .execute().data
        or []
    )

    svc = ExecutionService()
    started = []
    data = payload.get("event_data") or {}
    for w in workflows:
        try:
            row = await svc.trigger(
                workflow_id=UUID(w["id"]),
                business_id=UUID(business_id),
                trigger_data=data,
                client_email=data.get("client_email") or data.get("email"),
                client_phone=data.get("client_phone") or data.get("phone"),
                client_name=data.get("client_name")  or data.get("name"),
                client_identifier=data.get("client_id"),
            )
            started.append(row["id"])
        except Exception as e:
            logger.warning("event trigger of %s failed: %s", w["id"], e)
    return {"ok": True, "matched": len(workflows), "started": started}
