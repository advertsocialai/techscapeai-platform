"""
Deterministic stub gateway (Phase 4 T2).

This is what the factory selects when RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are
absent — which is the case in this sandbox. It is NOT a mock object: it is a
real, fully-implemented PaymentGateway backend that makes zero network calls and
requires zero credentials, so the entire downstream stack — the payment_links
row, the created -> sent -> viewed -> paid status machine, the webhook handler,
RBAC and business scoping — runs for real and is genuinely testable.

Two properties make it safe:

1. Every URL it mints uses the ``stub://`` scheme, exactly as the spec requires.
   A stub link is therefore impossible to mistake for a real payment page: it
   will not resolve in a browser, will not render, and cannot take money. If a
   stub URL ever leaks into a customer-facing message it fails loudly and
   visibly instead of quietly pretending to be a checkout.

2. It is deterministic. gateway_link_id is derived by hashing the reference_id
   (our payment_links.id) plus amount/currency, so the same inputs always
   produce the same id — replayable tests, stable fixtures, no random drift.

Webhook verification accepts a manually-triggered test payload: sign the raw
body with STUB_WEBHOOK_SECRET (default "stub-secret") using the same
HMAC-SHA256-hex scheme Razorpay uses, so exercising the webhook route locally
exercises the identical code path, not a bypass.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional

from .base import (
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_PAID,
    STATUS_SENT,
    STATUS_VIEWED,
    PaymentGateway,
    PaymentLinkResult,
    from_minor_units,
    normalize_currency,
    to_minor_units,
)

logger = logging.getLogger(__name__)

#: Scheme every stub link carries. Non-resolvable by construction.
STUB_URL_SCHEME = "stub://"

#: Default secret for locally-triggered test webhooks. Overridable via
#: settings.STUB_WEBHOOK_SECRET without touching config.py (getattr default).
DEFAULT_STUB_WEBHOOK_SECRET = "stub-secret"

#: Stub event names -> our status vocabulary. Deliberately mirrors Razorpay's
#: shape so the webhook route needs no special-casing.
_EVENT_STATUS_MAP: dict[str, Optional[str]] = {
    "payment_link.sent": STATUS_SENT,
    "payment_link.viewed": STATUS_VIEWED,
    "payment_link.paid": STATUS_PAID,
    "payment_link.expired": STATUS_EXPIRED,
    "payment_link.cancelled": STATUS_EXPIRED,
}

_DEFAULT_TTL = timedelta(days=7)


class StubGateway(PaymentGateway):
    name = "stub"

    def __init__(self, *, webhook_secret: str = DEFAULT_STUB_WEBHOOK_SECRET) -> None:
        self.webhook_secret = webhook_secret or DEFAULT_STUB_WEBHOOK_SECRET

    # ── deterministic id ─────────────────────────────────────────────────
    @staticmethod
    def make_link_id(reference_id: str, amount_minor: int, currency: str) -> str:
        """Well-formed, Razorpay-shaped, and fully deterministic.

        `plink_stub_` + 14 hex chars of SHA-256 over the inputs. Same inputs
        always produce the same id, so tests and fixtures are replayable.
        """
        seed = f"{reference_id}|{amount_minor}|{currency}".encode("utf-8")
        return f"plink_stub_{hashlib.sha256(seed).hexdigest()[:14]}"

    # ── create_link ──────────────────────────────────────────────────────
    async def create_link(
        self,
        *,
        amount: Decimal,
        currency: str = "INR",
        description: str = "",
        reference_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        expiry_at: Optional[datetime] = None,
        notes: Optional[Mapping[str, Any]] = None,
    ) -> PaymentLinkResult:
        currency = normalize_currency(currency)
        amount_minor = to_minor_units(amount, currency)
        ref = str(reference_id or "no-reference")

        link_id = self.make_link_id(ref, amount_minor, currency)
        expiry = expiry_at or (datetime.now(timezone.utc) + _DEFAULT_TTL)

        # stub:// — unmistakably not a real checkout page.
        short_url = f"{STUB_URL_SCHEME}payments.local/l/{link_id}"

        logger.info(
            "stub gateway minted payment link id=%s amount_minor=%s currency=%s ref=%s "
            "(NO network call, NO credentials)",
            link_id, amount_minor, currency, ref,
        )

        return PaymentLinkResult(
            gateway=self.name,
            gateway_link_id=link_id,
            gateway_short_url=short_url,
            amount=from_minor_units(amount_minor, currency),
            currency=currency,
            status=STATUS_CREATED,
            expiry_at=expiry,
            raw={
                "id": link_id,
                "short_url": short_url,
                "amount": amount_minor,
                "currency": currency,
                "status": "created",
                "reference_id": ref,
                "description": description,
                "expire_by": int(expiry.timestamp()),
                "customer": {
                    "name": customer_name, "email": customer_email, "contact": customer_phone,
                },
                "notes": dict(notes or {}),
                "stub": True,
            },
        )

    # ── signing helper for manually-triggered test webhooks ──────────────
    def sign(self, raw_body: bytes) -> str:
        """Produce the X-Razorpay-Signature value for a hand-rolled test
        payload. Same HMAC-SHA256-hex scheme as the live gateway, so the
        webhook route under test is the production route."""
        if not isinstance(raw_body, (bytes, bytearray)):
            raw_body = str(raw_body).encode("utf-8")
        return hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # ── verify_webhook_signature ─────────────────────────────────────────
    def verify_webhook_signature(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> bool:
        """Accepts a manually-triggered test payload signed with the stub
        secret. Constant-time compare, identical scheme to Razorpay."""
        signature = None
        if headers:
            for key in ("X-Razorpay-Signature", "X-Stub-Signature"):
                signature = _header(headers, key)
                if signature:
                    break
        if not signature:
            return False
        try:
            return hmac.compare_digest(self.sign(raw_body), signature.strip())
        except (TypeError, ValueError):
            return False

    # ── parse_webhook_event ──────────────────────────────────────────────
    def parse_webhook_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "event": None, "gateway": self.name, "gateway_link_id": None,
            "reference_id": None, "status": None, "amount": None,
            "currency": None, "raw": dict(payload or {}),
        }
        if not isinstance(payload, Mapping):
            return envelope

        event = payload.get("event")
        envelope["event"] = str(event) if event else None

        entity: Mapping[str, Any] = {}
        inner = payload.get("payload")
        if isinstance(inner, Mapping):
            wrap = inner.get("payment_link")
            if isinstance(wrap, Mapping) and isinstance(wrap.get("entity"), Mapping):
                entity = wrap["entity"]
        # Also accept a flat {"event":..., "payment_link_id":...} test payload.
        if not entity:
            flat_id = payload.get("payment_link_id") or payload.get("gateway_link_id")
            if flat_id:
                entity = {"id": flat_id, "reference_id": payload.get("reference_id")}

        if entity:
            envelope["gateway_link_id"] = _str_or_none(entity.get("id"))
            envelope["reference_id"] = _str_or_none(entity.get("reference_id"))
            currency = _str_or_none(entity.get("currency"))
            if currency:
                try:
                    envelope["currency"] = normalize_currency(currency)
                except ValueError:
                    envelope["currency"] = None
            amount = entity.get("amount")
            if amount is not None and envelope["currency"]:
                try:
                    envelope["amount"] = from_minor_units(int(amount), envelope["currency"])
                except (TypeError, ValueError):
                    envelope["amount"] = None

        envelope["status"] = _EVENT_STATUS_MAP.get(envelope["event"] or "")
        return envelope


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value:
            return value
    except Exception:
        return None
    lowered = name.lower()
    for k, v in dict(headers).items():
        if str(k).lower() == lowered:
            return v
    return None


def _str_or_none(value: Any) -> Optional[str]:
    return str(value) if value not in (None, "") else None
