"""
Payment links (Phase 4 T2).

  POST /payment-links                  → mint a link      (agent+)
  GET  /payment-links?lead_id=         → list, scoped     (viewer+)
  GET  /payment-links/{id}             → one, scoped      (viewer+)
  POST /payment-links/{id}/transition  → advance status   (agent+)
  POST /webhook/razorpay               → gateway callback (NO JWT)

AUTH MODEL — two different worlds in one file
---------------------------------------------
The four /payment-links routes are called by logged-in staff: they carry a
Bearer JWT, go through require_role(), and are scoped to user["business_id"].
Anything belonging to another business returns 404, never 403 — a 403 would
confirm the row exists and leak cross-tenant information.

/webhook/razorpay is called BY the gateway, which has no JWT and never will.
Its authentication is the HMAC signature over the raw request body, verified by
the gateway adapter. This mirrors exactly how routers/travel/webhooks_voice.py
authenticates Plivo (X-Plivo-Signature-V2, verified in services/travel/voice.py
with hmac.compare_digest) — same convention, same shape, different provider.
The raw body is read with `await request.body()` BEFORE any JSON parsing,
because re-serializing parsed JSON changes byte order and breaks the digest.

STATUS MACHINE
--------------
created → sent → viewed → paid, with expired reachable from any non-paid state.
Forward-only, enforced by can_transition() in services/payments/base.py, so a
late or replayed 'viewed' webhook can never demote a row that is already 'paid'.

GATEWAY
-------
services.payments.get_gateway() picks Razorpay when credentials exist, else the
deterministic stub (stub:// links, no network). Every route below is identical
in both modes — the stub exercises real DB state transitions, not mocks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from pydantic import BaseModel, Field, field_validator

from app.core.deps import require_role
from app.database import get_supabase_admin
from app.services.payments import (
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_PAID,
    PAYMENT_LINK_STATUSES,
    PaymentGatewayError,
    can_transition,
    get_gateway,
    gateway_mode,
    is_terminal,
    normalize_currency,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_VIEWER_PLUS = require_role("viewer")
_AGENT_PLUS = require_role("agent")

_TABLE = "payment_links"


# ── Models ────────────────────────────────────────────────────────────────
class PaymentLinkCreate(BaseModel):
    amount: Decimal = Field(..., description="Major units (rupees), NOT paise")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    lead_id: Optional[UUID] = None
    package_id: Optional[UUID] = None
    description: str = Field(default="", max_length=2048)
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    expiry_at: Optional[datetime] = None
    #: Force a specific backend. Omit to let the factory decide.
    gateway: Optional[str] = Field(default=None, pattern="^(razorpay|stripe|stub)$")
    notes: Optional[dict[str, Any]] = None

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: Decimal) -> Decimal:
        try:
            v = Decimal(str(v))
        except (InvalidOperation, TypeError):
            raise ValueError("amount must be a decimal number")
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        if v > Decimal("9999999999.99"):  # NUMERIC(12,2) ceiling
            raise ValueError("amount exceeds the maximum supported value")
        return v

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, v: str) -> str:
        return normalize_currency(v)


class PaymentLinkTransition(BaseModel):
    status: str = Field(..., description="Target status: sent | viewed | paid | expired")

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in PAYMENT_LINK_STATUSES:
            raise ValueError(f"status must be one of {', '.join(PAYMENT_LINK_STATUSES)}")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────
def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _apply_expiry(db, row: dict) -> dict:
    """Lazily flip a lapsed link to 'expired'.

    Cheaper and more reliable than a cron: the state is corrected the moment
    anyone looks at it. Never touches a paid row — money already moved, and an
    expiry timestamp passing afterwards is meaningless.
    """
    if not row or is_terminal(row.get("status", "")):
        return row
    expiry = _parse_ts(row.get("expiry_at"))
    if expiry and expiry <= datetime.now(timezone.utc):
        updated = (
            db.table(_TABLE).update({"status": STATUS_EXPIRED})
            .eq("id", row["id"]).execute().data
        )
        return updated[0] if updated else {**row, "status": STATUS_EXPIRED}
    return row


def _get_scoped(db, link_id: UUID | str, business_id: str) -> Optional[dict]:
    """Fetch by id AND business_id. Cross-tenant reads simply find nothing."""
    rows = (
        db.table(_TABLE).select("*")
        .eq("id", str(link_id)).eq("business_id", str(business_id))
        .limit(1).execute().data
    )
    return rows[0] if rows else None


def _assert_owned(db, table: str, row_id: UUID, business_id: str, label: str) -> None:
    """A lead/package from another business must be indistinguishable from a
    nonexistent one → 404."""
    rows = (
        db.table(table).select("id")
        .eq("id", str(row_id)).eq("business_id", str(business_id))
        .limit(1).execute().data
    )
    if not rows:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"{label} not found")


# ── POST /payment-links ───────────────────────────────────────────────────
@router.post("/payment-links", status_code=http_status.HTTP_201_CREATED)
async def create_payment_link(body: PaymentLinkCreate, user: dict = Depends(_AGENT_PLUS)):
    db = get_supabase_admin()
    business_id = str(user["business_id"])

    if body.lead_id:
        _assert_owned(db, "travel_leads", body.lead_id, business_id, "Lead")
    if body.package_id:
        _assert_owned(db, "travel_packages", body.package_id, business_id, "Package")

    if body.expiry_at:
        expiry = body.expiry_at if body.expiry_at.tzinfo else body.expiry_at.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "expiry_at must be in the future")
    else:
        expiry = None

    gw = get_gateway(body.gateway)

    # Two-phase insert: the row's own id becomes the gateway reference_id, so
    # every webhook the gateway sends back correlates to exactly one row.
    placeholder = (
        db.table(_TABLE).insert({
            "business_id": business_id,
            "lead_id": str(body.lead_id) if body.lead_id else None,
            "package_id": str(body.package_id) if body.package_id else None,
            "amount": str(body.amount),
            "currency": body.currency,
            "gateway": gw.name,
            "status": STATUS_CREATED,
            "expiry_at": expiry.isoformat() if expiry else None,
            "created_by": str(user["id"]),
        }).execute().data
    )
    if not placeholder:
        raise HTTPException(http_status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not create payment link row")
    row = placeholder[0]

    try:
        result = await gw.create_link(
            amount=body.amount,
            currency=body.currency,
            description=body.description or f"Payment for lead {body.lead_id or ''}".strip(),
            reference_id=row["id"],
            customer_name=body.customer_name,
            customer_email=body.customer_email,
            customer_phone=body.customer_phone,
            expiry_at=expiry,
            notes={**(body.notes or {}), "business_id": business_id, "payment_link_id": row["id"]},
        )
    except NotImplementedError as exc:
        db.table(_TABLE).delete().eq("id", row["id"]).execute()
        raise HTTPException(http_status.HTTP_501_NOT_IMPLEMENTED, str(exc))
    except PaymentGatewayError as exc:
        # Roll back the placeholder — a row with no link is worse than no row.
        db.table(_TABLE).delete().eq("id", row["id"]).execute()
        raise HTTPException(http_status.HTTP_502_BAD_GATEWAY, str(exc))
    except ValueError as exc:
        db.table(_TABLE).delete().eq("id", row["id"]).execute()
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    updated = (
        db.table(_TABLE).update({
            "gateway_link_id": result.gateway_link_id,
            "gateway_short_url": result.gateway_short_url,
            "status": result.status,
            "expiry_at": result.expiry_at.isoformat() if result.expiry_at else None,
        }).eq("id", row["id"]).execute().data
    )
    final = updated[0] if updated else row
    logger.info(
        "payment link created id=%s business=%s gateway=%s mode=%s",
        final["id"], business_id, gw.name, gateway_mode(),
    )
    return final


# ── GET /payment-links ────────────────────────────────────────────────────
@router.get("/payment-links")
def list_payment_links(
    lead_id: Optional[UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(_VIEWER_PLUS),
):
    db = get_supabase_admin()
    business_id = str(user["business_id"])

    q = db.table(_TABLE).select("*").eq("business_id", business_id)
    if lead_id:
        q = q.eq("lead_id", str(lead_id))
    if status_filter:
        s = status_filter.strip().lower()
        if s not in PAYMENT_LINK_STATUSES:
            raise HTTPException(
                http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"status must be one of {', '.join(PAYMENT_LINK_STATUSES)}",
            )
        q = q.eq("status", s)

    rows = q.order("created_at", desc=True).limit(limit).execute().data or []
    return {"count": len(rows), "gateway_mode": gateway_mode(), "items": rows}


# ── GET /payment-links/{id} ───────────────────────────────────────────────
@router.get("/payment-links/{link_id}")
def get_payment_link(link_id: UUID, user: dict = Depends(_VIEWER_PLUS)):
    db = get_supabase_admin()
    row = _get_scoped(db, link_id, str(user["business_id"]))
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Payment link not found")
    return _apply_expiry(db, row)


# ── POST /payment-links/{id}/transition ───────────────────────────────────
@router.post("/payment-links/{link_id}/transition")
def transition_payment_link(
    link_id: UUID, body: PaymentLinkTransition, user: dict = Depends(_AGENT_PLUS)
):
    """Staff-driven half of the status machine.

    'sent' is set here (we own delivery — WhatsApp/SMS — so the gateway never
    tells us a link was sent). 'viewed'/'paid' normally arrive by webhook, but
    are permitted here too for manual reconciliation.
    """
    db = get_supabase_admin()
    row = _get_scoped(db, link_id, str(user["business_id"]))
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Payment link not found")

    row = _apply_expiry(db, row)
    current = row.get("status", STATUS_CREATED)
    target = body.status

    if current == target:
        return row  # idempotent no-op
    if not can_transition(current, target):
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Illegal status transition {current} -> {target}",
        )

    updated = db.table(_TABLE).update({"status": target}).eq("id", row["id"]).execute().data
    logger.info("payment link %s transitioned %s -> %s by user=%s", row["id"], current, target, user["id"])
    return updated[0] if updated else {**row, "status": target}


# ── POST /webhook/razorpay — NO JWT, gateway-signed ───────────────────────
@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    """Gateway callback.

    Authentication is the HMAC signature over the RAW body — same convention as
    the Plivo webhook in webhooks_voice.py. There is no Bearer token here and
    there must not be: Razorpay cannot hold one.

    Always returns 200 on a verified-but-unactionable event. Gateways retry on
    non-2xx, so returning an error for "event I don't care about" or "row
    already paid" would produce an infinite retry storm. Only an invalid
    signature (403) or a malformed body (400) is an error.
    """
    raw_body = await request.body()

    # Auto-select: razorpay when configured, stub otherwise. The stub still
    # demands a valid signature — it is not a bypass.
    gw = get_gateway()

    if not gw.verify_webhook_signature(raw_body, request.headers):
        logger.warning("payment webhook rejected: invalid or missing signature (gateway=%s)", gw.name)
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Invalid or missing webhook signature")

    try:
        import json
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Malformed webhook body")
    if not isinstance(payload, dict):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Malformed webhook body")

    event = gw.parse_webhook_event(payload)
    target = event.get("status")
    link_id = event.get("gateway_link_id")
    reference_id = event.get("reference_id")

    if not target:
        logger.info("payment webhook: event=%s carries no status change — ignoring", event.get("event"))
        return {"ok": True, "applied": False, "reason": "no_status_change"}

    db = get_supabase_admin()

    # Resolve by the gateway's own id first (unique in the schema), then by our
    # reference_id, which is the payment_links.id we handed the gateway.
    row = None
    if link_id:
        rows = db.table(_TABLE).select("*").eq("gateway_link_id", link_id).limit(1).execute().data
        row = rows[0] if rows else None
    if not row and reference_id:
        rows = db.table(_TABLE).select("*").eq("id", reference_id).limit(1).execute().data
        row = rows[0] if rows else None

    if not row:
        # Verified signature but unknown link: log and 200 so the gateway stops
        # retrying something we can never resolve.
        logger.warning("payment webhook: no matching row for link_id=%s ref=%s", link_id, reference_id)
        return {"ok": True, "applied": False, "reason": "unknown_link"}

    current = row.get("status", STATUS_CREATED)
    if current == target:
        return {"ok": True, "applied": False, "reason": "already_in_state", "status": current}
    if not can_transition(current, target):
        # Out-of-order/replayed delivery. Forward-only machine refuses to
        # demote — notably, nothing can un-pay a paid link.
        logger.info("payment webhook: refusing %s -> %s for link %s", current, target, row["id"])
        return {"ok": True, "applied": False, "reason": "illegal_transition", "status": current}

    patch: dict[str, Any] = {"status": target}
    if link_id and not row.get("gateway_link_id"):
        patch["gateway_link_id"] = link_id

    db.table(_TABLE).update(patch).eq("id", row["id"]).execute()
    logger.info(
        "payment webhook applied: link=%s %s -> %s (event=%s, business=%s)",
        row["id"], current, target, event.get("event"), row.get("business_id"),
    )
    return {"ok": True, "applied": True, "status": target, "payment_link_id": row["id"]}
