"""
Voice provider webhooks (Phase 2) — Plivo answer + media stream.

IMPORTANT — auth model differs from every other route in this repo:
these endpoints are called BY Plivo, not by a logged-in user, so they do
NOT use get_current_user/require_role (there is no JWT to check). Auth
here is Plivo's own request-signing scheme (X-Plivo-Signature-V2 +
X-Plivo-Signature-V2-Nonce), verified in app/services/travel/voice.py —
same "accept when secret unset" stub-mode convention as the existing
Twilio/Wapi webhook verifiers in app/services/techscape/webhooks.py.

T2 status: signature verification is real and testable today (HMAC
logic needs no live Plivo account). The actual "answer a real call"
path is BLOCKED pending real PLIVO_AUTH_ID/TOKEN/PHONE_NUMBER and a
reachable PUBLIC_BASE_URL (ngrok) — see PHASE2_REPORT.md Blocked Items.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.core.config import settings
from app.database import get_supabase_admin
from app.services.travel.voice import stream_xml, verify_plivo_signature

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_PROVIDERS = {"plivo"}


def _webhook_url(request: Request) -> str:
    """The exact public URL Plivo posted to — signature is computed against
    this, not the internal request URL FastAPI sees behind a tunnel/proxy."""
    base = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else str(request.base_url).rstrip("/")
    path = request.url.path
    qs = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{path}{qs}"


@router.post("/{provider}/voice")
async def answer_call(
    provider: str,
    request: Request,
    x_plivo_signature_v2: str | None = Header(default=None, alias="X-Plivo-Signature-V2"),
    x_plivo_signature_v2_nonce: str | None = Header(default=None, alias="X-Plivo-Signature-V2-Nonce"),
):
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown voice provider: {provider}")

    body = await request.form()
    if not verify_plivo_signature(
        url=_webhook_url(request),
        nonce=x_plivo_signature_v2_nonce,
        signature=x_plivo_signature_v2,
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing Plivo signature")

    call_uuid = body.get("CallUUID")
    from_number = body.get("From")
    to_number = body.get("To")
    logger.info("Plivo answer webhook: call=%s from=%s to=%s", call_uuid, from_number, to_number)

    if not settings.PLIVO_BUSINESS_ID:
        # Nothing to attribute the call to yet — see config.py's note on
        # single-tenant PLIVO_BUSINESS_ID (Phase 3 needs real per-business
        # phone routing). Answer gracefully instead of 500ing on a caller.
        logger.warning("PLIVO_BUSINESS_ID not configured — cannot create a travel_calls row")
    else:
        db = get_supabase_admin()
        lead_row = (
            db.table("travel_leads").select("id")
            .eq("business_id", settings.PLIVO_BUSINESS_ID)
            .eq("phone", from_number)
            .order("created_at", desc=True).limit(1).execute().data
        )
        lead_id = lead_row[0]["id"] if lead_row else db.table("travel_leads").insert({
            "business_id": settings.PLIVO_BUSINESS_ID,
            "source": "phone",
            "raw_message": f"Inbound call from {from_number}",
            "phone": from_number,
            "status": "new",
        }).execute().data[0]["id"]

        db.table("travel_calls").insert({
            "business_id":  settings.PLIVO_BUSINESS_ID,
            "lead_id":      lead_id,
            "provider_sid": call_uuid,
            "status":       "active",
            "mode":         "ai",
            "started_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()

    stream_url = _webhook_url(request).replace("/voice", "/stream").replace("https://", "wss://").replace("http://", "ws://")
    return Response(content=stream_xml(stream_url=stream_url), media_type="application/xml")
