"""
WhatsApp send + outbox endpoints (Phase 4 T3).

POST /whatsapp/send          → agent+   : send a template or free-form message
GET  /whatsapp/outbox        → viewer+  : paginated, business-scoped send log
GET  /whatsapp/outbox/{id}   → viewer+  : one row; out-of-scope ⇒ 404, never 403

MOUNTING: this module exposes a bare `router`; travel/__init__.py (owned by
another task) mounts it as

    travel_router.include_router(whatsapp_router, prefix="/whatsapp",
                                 tags=["Travel · WhatsApp"])

giving /travel/v1/whatsapp/send and /travel/v1/whatsapp/outbox.

WITHOUT CREDENTIALS THIS ENDPOINT STILL WORKS AND STILL SENDS NOTHING. The
factory returns the stub provider, which writes the exact would-be payload to
whatsapp_outbox with status='stubbed'. `provider`/`status` on the response tell
the caller unambiguously which happened — there is no mode where a stubbed
message is reported as delivered.

Pydantic models are defined here on purpose: app/schemas/travel.py is owned by
another task this phase, and these shapes are endpoint-local.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from app.core.deps import require_role
from app.database import get_supabase_admin
from app.services.whatsapp import (
    OUTBOX_TABLE,
    SessionWindowClosed,
    WhatsAppSendError,
    get_whatsapp_provider,
)

router = APIRouter()

_VIEWER_PLUS = require_role("viewer")
_AGENT_PLUS = require_role("agent")

MessageType = Literal["template", "freeform"]
OutboxStatus = Literal["queued", "sent", "failed", "stubbed"]


# ── Request / response models ───────────────────────────────────────────────
class WhatsAppSendIn(BaseModel):
    """
    One of two shapes, discriminated by `message_type`:

      template → template_name required, `text` must be absent
      freeform → text required, template_name must be absent, AND the 24-hour
                 customer-service window must be open (else 409)
    """

    to: str = Field(..., description="Recipient. E.164, or a bare 10-digit Indian mobile.")
    message_type: MessageType = "template"
    template_name: Optional[str] = Field(default=None, max_length=255)
    language: str = Field(default="en", max_length=10)
    components: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Meta template component array (header/body/button parameters).",
    )
    text: Optional[str] = Field(
        default=None, max_length=4096, description="Free-form body. Ignored for templates.",
    )

    @model_validator(mode="after")
    def _check_shape(self) -> "WhatsAppSendIn":
        if self.message_type == "template":
            if not self.template_name:
                raise ValueError("template_name is required when message_type='template'")
            if self.text:
                raise ValueError("text is not allowed when message_type='template'")
        else:
            if not (self.text or "").strip():
                raise ValueError("text is required when message_type='freeform'")
            if self.template_name:
                raise ValueError("template_name is not allowed when message_type='freeform'")
            if self.components:
                raise ValueError("components are not allowed when message_type='freeform'")
        return self


class WhatsAppOutboxOut(BaseModel):
    id: str
    business_id: str
    to_number: str
    message_type: str
    template_name: Optional[str] = None
    language: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    provider: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    sent_at: Optional[str] = None


class WhatsAppOutboxPage(BaseModel):
    """Repo list convention: {items, total} so pagination never breaks clients."""

    items: list[WhatsAppOutboxOut]
    total: int


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.post("/send", response_model=WhatsAppOutboxOut,
             status_code=status.HTTP_201_CREATED)
async def send_whatsapp(body: WhatsAppSendIn, user: dict = Depends(_AGENT_PLUS)):
    """
    Send a WhatsApp message on behalf of the caller's business.

    Returns the persisted outbox row, so the caller always learns whether the
    message was actually transmitted ('sent') or recorded only ('stubbed').

    409 means the 24-hour session window is closed and the caller must retry
    with an approved template — a policy outcome, not a server fault.
    """
    provider = get_whatsapp_provider(user["business_id"])
    try:
        if body.message_type == "template":
            row = await provider.send_template(
                body.to,
                body.template_name or "",
                body.language,
                body.components or [],
            )
        else:
            row = await provider.send_freeform(body.to, body.text or "")
    except SessionWindowClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:  # normalize_msisdn rejected the recipient
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except WhatsAppSendError as exc:
        # The provider refused/failed; the outbox row is already marked failed.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return row


@router.get("/outbox", response_model=WhatsAppOutboxPage)
def list_outbox(
    status_filter: Optional[OutboxStatus] = Query(default=None, alias="status"),
    message_type: Optional[MessageType] = Query(default=None),
    to_number: Optional[str] = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(_VIEWER_PLUS),
):
    """
    Business-scoped send log, newest first.

    The business_id filter is taken from the caller's own token and is not
    overridable by query param — there is no way to ask for another tenant's
    outbox.
    """
    db = get_supabase_admin()
    q = (
        db.table(OUTBOX_TABLE).select("*", count="exact")
        .eq("business_id", user["business_id"])
    )
    if status_filter:
        q = q.eq("status", status_filter)
    if message_type:
        q = q.eq("message_type", message_type)
    if to_number:
        q = q.eq("to_number", to_number)

    res = (
        q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    items = res.data or []
    total = res.count if getattr(res, "count", None) is not None else len(items)
    return {"items": items, "total": total}


@router.get("/outbox/{outbox_id}", response_model=WhatsAppOutboxOut)
def get_outbox_row(outbox_id: str, user: dict = Depends(_VIEWER_PLUS)):
    """
    Out-of-scope rows are indistinguishable from missing ones: both 404.
    A 403 here would confirm that some other tenant owns this id.
    """
    db = get_supabase_admin()
    rows = (
        db.table(OUTBOX_TABLE).select("*")
        .eq("id", outbox_id)
        .eq("business_id", user["business_id"])
        .limit(1).execute().data
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outbox message not found")
    return rows[0]
