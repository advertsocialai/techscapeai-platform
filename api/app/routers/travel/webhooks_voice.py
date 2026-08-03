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

from fastapi import (
    APIRouter, Header, HTTPException, Request, Response,
    WebSocket, WebSocketDisconnect, status,
)

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


# ── T3: media stream ─────────────────────────────────────────────
# Plivo's Audio Streaming protocol sends one JSON frame per event over
# the WS connection opened via the <Stream> element above:
#   {"event": "start", "start": {"callId": "...", "streamId": "...", ...}}
#   {"event": "media",  "media": {"payload": "<base64 audio>", "timestamp": ..., ...}}
#   {"event": "stop",   "stop":  {"callId": "...", ...}}
# No signature scheme applies to the WS upgrade itself in Plivo's spec —
# the stream URL is only ever handed out by our own signature-verified
# answer webhook above, which is the actual trust boundary.
def _parse_started_at(row: dict) -> datetime | None:
    raw = row.get("started_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.websocket("/{provider}/stream")
async def media_stream(websocket: WebSocket, provider: str):
    if provider not in _SUPPORTED_PROVIDERS:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    db = get_supabase_admin()
    call_row: dict | None = None
    media_frame_count = 0

    try:
        while True:
            msg = await websocket.receive_json()
            event = msg.get("event")

            if event == "start":
                call_id = (msg.get("start") or {}).get("callId") or (msg.get("start") or {}).get("streamId")
                rows = (
                    db.table("travel_calls").select("*")
                    .eq("provider_sid", call_id)
                    .order("created_at", desc=True).limit(1).execute().data
                )
                call_row = rows[0] if rows else None
                logger.info("stream start: call=%s row_found=%s", call_id, bool(call_row))

            elif event == "media":
                media_frame_count += 1
                # T4 wires msg["media"]["payload"] (base64 audio) into STT here.

            elif event == "stop":
                if call_row:
                    started_at = _parse_started_at(call_row)
                    now = datetime.now(timezone.utc)
                    duration = int((now - started_at).total_seconds()) if started_at else None
                    db.table("travel_calls").update({
                        "status":       "completed",
                        "ended_at":     now.isoformat(),
                        "duration_sec": duration,
                    }).eq("id", call_row["id"]).execute()
                    logger.info("stream stop: call=%s frames=%d duration_sec=%s",
                                call_row.get("provider_sid"), media_frame_count, duration)
                break

    except WebSocketDisconnect:
        # Caller/provider dropped without a clean "stop" frame — still
        # close out the call row rather than leaving it 'active' forever.
        if call_row and call_row.get("status") == "active":
            started_at = _parse_started_at(call_row)
            now = datetime.now(timezone.utc)
            duration = int((now - started_at).total_seconds()) if started_at else None
            db.table("travel_calls").update({
                "status": "failed", "ended_at": now.isoformat(), "duration_sec": duration,
            }).eq("id", call_row["id"]).execute()
            logger.warning("stream disconnected without stop frame: call=%s", call_row.get("provider_sid"))
