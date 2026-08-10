"""
Voice provider webhooks — Plivo answer + media stream.

Phase 2: signature verification, travel_calls lifecycle, batch STT.
Phase 3 additions:
  T3: suggestion_service.schedule() after each transcript (fire-and-forget)
  T4: sentiment_service.schedule() after each transcript (fire-and-forget)
  T5: post_call_service.schedule() on call stop (fire-and-forget)
  T6: embeddings.schedule_transcript_embedding() after transcript row created
  T7: multi-tenant phone routing — resolves business_id from the "To"
      field via business_phone_numbers table (falls back to PLIVO_BUSINESS_ID)
  T9: per-participant recording URL stored in travel_calls (BLOCKED: no Plivo creds)

IMPORTANT — auth model:
  These endpoints are called BY Plivo, not by a logged-in user.
  Auth = Plivo's HMAC-SHA256 signature scheme (X-Plivo-Signature-V2 +
  X-Plivo-Signature-V2-Nonce), verified in services/travel/voice.py.
  Stub-mode (PLIVO_AUTH_TOKEN unset) accepts all — testable without creds.
"""
from __future__ import annotations
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter, Header, HTTPException, Request, Response,
    WebSocket, WebSocketDisconnect, status,
)

from app.core.config import settings
from app.database import get_supabase_admin
from app.services.travel import call_feed
from app.services.travel.voice import (
    CONSENT_ANNOUNCEMENT_LANGUAGE, CONSENT_WORDING_VERSION,
    select_stt_engine, stream_xml, transcribe_utterance, verify_plivo_signature,
)
from app.services.travel import (
    suggestion_service,
    sentiment_service,
    post_call_service,
    voice_turn_service,
)
from app.services.travel.embeddings import schedule_transcript_embedding

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_PROVIDERS = {"plivo"}


def _webhook_url(request: Request) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else str(request.base_url).rstrip("/")
    path = request.url.path
    qs = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{path}{qs}"


# ── T7: multi-tenant phone routing ───────────────────────────────────
def _resolve_business_id(db, to_number: Optional[str]) -> Optional[str]:
    """Resolve business_id from the dialed number (P4 T7).

    The legacy PLIVO_BUSINESS_ID fallback is now confined to genuine
    single-tenant mode — i.e. only when business_phone_numbers is EMPTY.

    Why (Phase 5 isolation audit): the fallback previously applied whenever a
    number failed to resolve, for any reason. In a multi-tenant deployment that
    is a cross-tenant WRITE, not merely a misroute — an unregistered or
    mistyped number belonging to Tenant B would be attributed to whichever
    business PLIVO_BUSINESS_ID names, creating that call's travel_calls row and
    its travel_leads row inside the WRONG tenant. Silent, and very hard to
    unpick afterwards.

    Once any tenant registers a number, the table is non-empty and this
    function fails closed: an unrecognised number resolves to None, the caller
    answers without tenant context, and no row is written anywhere. That is the
    correct multi-tenant behaviour and it switches on automatically — nobody
    has to remember to turn the fallback off.
    """
    if to_number:
        rows = (
            db.table("business_phone_numbers").select("business_id")
            .eq("phone_number", to_number).eq("is_active", True)
            .limit(1).execute().data
        )
        if rows:
            return rows[0]["business_id"]

    if not settings.PLIVO_BUSINESS_ID:
        return None

    # Only fall back while NO number is registered at all (single-tenant mode).
    try:
        any_registered = (
            db.table("business_phone_numbers").select("business_id")
            .limit(1).execute().data
        )
    except Exception:
        # Cannot prove we are single-tenant, so do not risk attributing the
        # call to an arbitrary tenant. Fail closed.
        logger.exception("phone-number registry lookup failed for to=%s", to_number)
        return None

    if any_registered:
        logger.error(
            "Unresolved dialed number %s and business_phone_numbers is NOT empty — "
            "refusing to fall back to PLIVO_BUSINESS_ID, which would attribute this "
            "call to the wrong tenant. Register this number to route it.",
            to_number,
        )
        return None

    logger.warning(
        "Single-tenant fallback: no numbers registered, attributing to "
        "PLIVO_BUSINESS_ID. Register numbers in business_phone_numbers before "
        "onboarding a second tenant.",
    )
    return settings.PLIVO_BUSINESS_ID


# ── T9: load ai_config for live calls ────────────────────────────────
def _load_ai_config(business_id: str) -> dict:
    try:
        from app.routers.travel.ai_config import load_ai_config
        return load_ai_config(business_id)
    except Exception:
        return {}


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
    to_number = body.get("To")  # T7: dialed number → resolve business
    logger.info("Plivo answer webhook: call=%s from=%s to=%s", call_uuid, from_number, to_number)

    db = get_supabase_admin()

    # T7: resolve business from "To" number
    business_id = _resolve_business_id(db, to_number)

    if not business_id:
        logger.warning("No business_id resolved for to=%s — answering without DB row", to_number)
    else:
        lead_row = (
            db.table("travel_leads").select("id")
            .eq("business_id", business_id)
            .eq("phone", from_number)
            .order("created_at", desc=True).limit(1).execute().data
        )
        lead_id = lead_row[0]["id"] if lead_row else db.table("travel_leads").insert({
            "business_id": business_id,
            "source": "phone",
            "raw_message": f"Inbound call from {from_number}",
            "phone": from_number,
            "status": "new",
        }).execute().data[0]["id"]

        call_rows = db.table("travel_calls").insert({
            "business_id":  business_id,
            "lead_id":      lead_id,
            "provider_sid": call_uuid,
            "status":       "active",
            "mode":         "ai",
            "started_at":   datetime.now(timezone.utc).isoformat(),
            "takeover_state": "ai",
        }).execute().data

        # C-3 (COMPLIANCE_CHECKLIST.md): record that the consent disclosure
        # was served with this call's answer XML. stream_xml() below always
        # includes CONSENT_ANNOUNCEMENT (announce_consent defaults True), so
        # the event is written at the same moment the XML that plays it is
        # returned to Plivo. event_type is a free VARCHAR(50) on
        # travel_call_events (migration 0005 — no CHECK constraint), so no
        # schema change is needed. Wording/language are versioned in
        # payload — see voice.py CONSENT_WORDING_VERSION
        # (PENDING LEGAL REVIEW, BLK-8: wording placeholder, mechanism final).
        # Failure to write the event must never fail the answer webhook —
        # the caller still gets answered; the gap is logged instead.
        # NOTE: when no business_id resolves, no travel_calls row exists and
        # the FK makes an event row impossible — the announcement still
        # PLAYS (stream_xml is unconditional); only the persisted marker is
        # tied to having a call row.
        try:
            db.table("travel_call_events").insert({
                "call_id":    call_rows[0]["id"],
                "event_type": "consent_disclosure_played",
                "payload": {
                    "language":        CONSENT_ANNOUNCEMENT_LANGUAGE,
                    "wording_version": CONSENT_WORDING_VERSION,
                },
            }).execute()
        except Exception:
            logger.warning(
                "consent event write failed for call=%s — answering anyway",
                call_uuid, exc_info=True,
            )

        # T9: request per-participant recording (customer leg)
        # BLOCKED: Plivo API call needs PLIVO_AUTH_ID/TOKEN (B-P3-06)
        # When unblocked: POST /Account/{auth_id}/Recording/ with participant-specific params
        if settings.PLIVO_AUTH_ID:
            logger.info("T9: would request per-participant recording for call=%s — creds present", call_uuid)
        else:
            logger.debug("T9: per-participant recording skipped — PLIVO_AUTH_ID absent (B-P3-06)")

    stream_url = (
        _webhook_url(request)
        .replace("/voice", "/stream")
        .replace("https://", "wss://")
        .replace("http://", "ws://")
    )
    return Response(content=stream_xml(stream_url=stream_url), media_type="application/xml")


# ── T3: media stream ─────────────────────────────────────────────────
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
    audio_chunks: list[bytes] = []
    call_start_ms: int | None = None
    ai_config: dict = {}

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
                if call_row:
                    # Load ai_config for this business (T2)
                    ai_config = _load_ai_config(call_row["business_id"])
                    await call_feed.publish(call_row["id"], {
                        "type": "call_status", "call_id": call_row["id"],
                        "status": "active", "mode": call_row.get("mode", "ai"),
                    })

            elif event == "media":
                media_frame_count += 1
                payload = (msg.get("media") or {}).get("payload")
                if payload:
                    try:
                        audio_chunks.append(base64.b64decode(payload))
                    except Exception:
                        logger.warning("undecodable media payload, skipping frame")
                    ts = (msg.get("media") or {}).get("timestamp")
                    if ts is not None and call_start_ms is None:
                        call_start_ms = int(ts)

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
                    await call_feed.publish(call_row["id"], {
                        "type": "call_status", "call_id": call_row["id"],
                        "status": "completed", "mode": call_row.get("mode", "ai"),
                    })

                    if audio_chunks:
                        engine = select_stt_engine(call_row.get("language"))
                        result = await transcribe_utterance(
                            engine=engine, audio_bytes=b"".join(audio_chunks),
                            language=call_row.get("language"),
                        )
                        db.table("travel_calls").update({"stt_engine": engine}).eq(
                            "id", call_row["id"]
                        ).execute()
                        transcript_row = db.table("travel_transcripts").insert({
                            "call_id":       call_row["id"],
                            "speaker":       "customer",
                            "text_original": result["text"],
                            "timestamp_ms":  call_start_ms or 0,
                        }).execute().data[0]
                        logger.info("transcript written: call=%s engine=%s stub=%s len=%d",
                                    call_row.get("provider_sid"), engine,
                                    result.get("stub"), len(result["text"]))
                        # seq must be really monotonic, not the hardcoded 1 it
                        # used to be — the AI-reply emit already counts rows
                        # via _next_seq; the customer emit now does the same.
                        from app.services.travel.voice_turn_service import _next_seq
                        await call_feed.publish(call_row["id"], {
                            "type": "transcript", "call_id": call_row["id"],
                            "seq": _next_seq(db, call_row["id"]),
                            "speaker": transcript_row["speaker"],
                            "text_original": transcript_row["text_original"],
                            "text_translated": transcript_row.get("text_translated"),
                            "language": call_row.get("language", "en"),
                            "timestamp_ms": transcript_row["timestamp_ms"], "is_final": True,
                        })

                        # T4: sentiment scoring (fire-and-forget, OFFLINE mode)
                        sentiment_service.schedule(
                            call_row["id"], transcript_row["id"],
                            result["text"], "customer"
                        )

                        # T6: embed transcript text (fire-and-forget, off the event loop)
                        schedule_transcript_embedding(transcript_row["id"], result["text"])

                        # T3: suggestion generation (fire-and-forget, OFFLINE mode)
                        suggestion_service.schedule(
                            call_row["id"], result["text"], "customer", ai_config
                        )

                        # THE VOICE TURN — the AI actually replies.
                        # Until this line existed, ai_engine.run_turn(),
                        # voice.synthesize_speech() and voice.log_voice_turn()
                        # had ZERO call sites: the customer spoke, we transcribed,
                        # scored, embedded and whispered to the agent — and the AI
                        # never said a word back. Nothing errored, which is why it
                        # went unnoticed; the feature was simply absent.
                        # Runs credential-free (stub model + silent TTS) and
                        # fire-and-forget so a 30s model call cannot stall the
                        # media socket and make Plivo drop the stream.
                        voice_turn_service.schedule(
                            call_id=call_row["id"],
                            business_id=call_row["business_id"],
                            lead_id=call_row.get("lead_id"),
                            customer_text=result["text"],
                            language=call_row.get("language", "en"),
                            stt_engine=engine,
                            ai_config=ai_config,
                        )

                    # T5: post-call intelligence pipeline (fire-and-forget)
                    post_call_service.schedule(call_row["id"], call_row["business_id"])
                break

    except WebSocketDisconnect:
        if call_row and call_row.get("status") == "active":
            started_at = _parse_started_at(call_row)
            now = datetime.now(timezone.utc)
            duration = int((now - started_at).total_seconds()) if started_at else None
            db.table("travel_calls").update({
                "status": "failed", "ended_at": now.isoformat(), "duration_sec": duration,
            }).eq("id", call_row["id"]).execute()
            logger.warning("stream disconnected without stop frame: call=%s", call_row.get("provider_sid"))
