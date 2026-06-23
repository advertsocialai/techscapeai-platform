"""
Direct-send endpoint — bypasses workflows but goes through the SAME compliance
pipeline as ExecutionService so callers cannot side-step billing or regulations:

  1. Subscription cap (max_monthly_messages)
  2. Contact DNC + per-channel consent flags
  3. TCPA window (sms / voice / voicemail only)
  4. Provider call (Wapi / Twilio / SendGrid via ChannelRouter)
  5. ts_communication_logs row written
  6. monthly_messages_used incremented on success
  7. ts_audit_logs row written
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase_admin
from app.schemas.techscape import DirectSendIn, DirectSendOut
from app.services.techscape import BusinessService
from app.services.techscape.audit import write_audit
from app.services.techscape.providers.router import get_router
from app.services.techscape.tcpa import is_within_tcpa_window

from ._deps import require_business

router = APIRouter()


@router.post("/send", response_model=DirectSendOut)
async def direct_send(payload: DirectSendIn,
                      biz: dict = Depends(require_business)):
    biz_id  = UUID(biz["id"])
    biz_svc = BusinessService()
    db      = get_supabase_admin()
    user    = (biz.get("_user") or {})

    # 1. Subscription cap
    ok, reason = biz_svc.can_send_messages(biz_id, 1)
    if not ok:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, reason)

    # 2. Contact DNC + per-channel consent (look up by email or phone)
    contact = None
    if payload.to_email:
        r = (db.table("ts_business_contacts").select("*")
             .eq("business_id", str(biz_id)).eq("email", payload.to_email)
             .limit(1).execute().data)
        contact = r[0] if r else None
    if not contact and payload.to_phone:
        r = (db.table("ts_business_contacts").select("*")
             .eq("business_id", str(biz_id)).eq("phone", payload.to_phone)
             .limit(1).execute().data)
        contact = r[0] if r else None

    if contact and contact.get("do_not_contact"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "recipient has do_not_contact=true")
    if contact and not contact.get(f"consent_{payload.channel}", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"recipient opted out of {payload.channel}")

    # 3. TCPA window
    ok_tcpa, why = is_within_tcpa_window(
        channel=payload.channel,
        timezone_str=biz.get("timezone") or "UTC",
    )
    if not ok_tcpa:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, why)

    # 4. Provider call
    res = await get_router().send(
        channel=payload.channel,
        to_email=payload.to_email,
        to_phone=payload.to_phone,
        subject=payload.subject,
        content=payload.content,
    )

    # 5. Log row (always)
    log = db.table("ts_communication_logs").insert({
        "business_id":         str(biz_id),
        "recipient_email":     payload.to_email,
        "recipient_phone":     payload.to_phone,
        "channel":             payload.channel,
        "message_subject":     payload.subject,
        "message_content":     payload.content[:8000],
        "provider":            res.get("provider"),
        "provider_message_id": res.get("provider_message_id"),
        "delivery_status":     res.get("delivery_status", "queued"),
        "cost":                res.get("cost", 0.0),
        "error_message":       res.get("error"),
        "retry_count":         0,
        "max_retries":         0,
        "sent_at":             datetime.now(timezone.utc).isoformat(),
    }).execute().data[0]

    # 6. Bill on success
    if res.get("delivery_status") in ("sent", "delivered"):
        biz_svc.increment_message_count(biz_id, 1)

    # 7. Audit
    write_audit(
        business_id=str(biz_id), user_id=user.get("id"),
        action="send.direct", resource_type="communication_log",
        resource_id=log["id"],
        details={"channel": payload.channel,
                 "provider": res.get("provider"),
                 "delivery_status": res.get("delivery_status")},
    )

    return DirectSendOut(
        log_id=UUID(log["id"]),
        provider=res.get("provider", "internal"),
        delivery_status=res.get("delivery_status", "failed"),
        provider_message_id=res.get("provider_message_id"),
        cost=float(res.get("cost", 0.0)),
    )
