"""
Razorpay Payment Links adapter (Phase 4 T2).

Real implementation against Razorpay's HTTP API using httpx — the repo already
depends on httpx (pinned >=0.26,<0.28 for supabase compat) and deliberately
does NOT take the `razorpay` SDK as a dependency.

API surface used
----------------
  POST https://api.razorpay.com/v1/payment_links
    auth: HTTP Basic (key_id : key_secret)
    body: {"amount": <paise int>, "currency": "INR", "description": ...,
           "reference_id": ..., "expire_by": <unix seconds>,
           "customer": {"name","email","contact"}, "notes": {...},
           "notify": {"sms": false, "email": false}}
    200 -> {"id": "plink_...", "short_url": "https://rzp.io/i/...", "status": "created", ...}

Webhook authentication
----------------------
  signature = HMAC-SHA256(webhook_secret, RAW_REQUEST_BODY) -> lowercase hex
  header    = X-Razorpay-Signature
Compared with hmac.compare_digest (constant-time). The digest is computed over
the exact bytes received — re-serializing parsed JSON would change whitespace
and key order and silently break every verification.

NOTE: in this sandbox there are no Razorpay credentials, so this class is never
instantiated by the factory (it falls back to StubGateway) and NO network call
is ever made. The code below is the real integration, ready the moment
RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET / RAZORPAY_WEBHOOK_SECRET are set.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional

import httpx

from .base import (
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_PAID,
    STATUS_VIEWED,
    PaymentGateway,
    PaymentGatewayError,
    PaymentLinkResult,
    from_minor_units,
    normalize_currency,
    to_minor_units,
)

logger = logging.getLogger(__name__)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Razorpay payment-link status -> our vocabulary.
_LINK_STATUS_MAP: dict[str, str] = {
    "created": STATUS_CREATED,
    "partially_paid": STATUS_VIEWED,  # engagement, but not settled
    "paid": STATUS_PAID,
    "expired": STATUS_EXPIRED,
    "cancelled": STATUS_EXPIRED,
}

#: Razorpay webhook event name -> our vocabulary. Events not listed here carry
#: no status meaning for us and map to None (caller no-ops).
_EVENT_STATUS_MAP: dict[str, Optional[str]] = {
    "payment_link.paid": STATUS_PAID,
    "payment_link.partially_paid": STATUS_VIEWED,
    "payment_link.expired": STATUS_EXPIRED,
    "payment_link.cancelled": STATUS_EXPIRED,
}


class RazorpayGateway(PaymentGateway):
    name = "razorpay"

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        *,
        webhook_secret: str = "",
        api_base: str = RAZORPAY_API_BASE,
    ) -> None:
        if not key_id or not key_secret:
            raise ValueError("RazorpayGateway requires both key_id and key_secret")
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.api_base = api_base.rstrip("/")

    # ── auth header ──────────────────────────────────────────────────────
    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        return f"Basic {token}"

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

        body: dict[str, Any] = {
            "amount": to_minor_units(amount, currency),
            "currency": currency,
            "description": (description or "Payment")[:2048],
            "notify": {"sms": False, "email": False},  # we own delivery
            "reminder_enable": False,
        }
        if reference_id:
            body["reference_id"] = str(reference_id)
        if expiry_at:
            # Razorpay wants unix seconds and rejects anything <15 min out.
            body["expire_by"] = int(expiry_at.astimezone(timezone.utc).timestamp())

        customer = {
            k: v for k, v in (
                ("name", customer_name),
                ("email", customer_email),
                ("contact", customer_phone),
            ) if v
        }
        if customer:
            body["customer"] = customer
        if notes:
            # Razorpay caps notes at 15 keys, values must be strings.
            body["notes"] = {str(k): str(v) for k, v in list(dict(notes).items())[:15]}

        url = f"{self.api_base}/payment_links"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={
                        "Authorization": self._auth_header(),
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("razorpay create_link transport error: %s", exc)
            raise PaymentGatewayError(f"Razorpay unreachable: {exc}") from exc

        if resp.status_code >= 400:
            # Never log the response wholesale — it can echo customer PII.
            detail = ""
            try:
                detail = str((resp.json().get("error") or {}).get("description", ""))
            except Exception:
                detail = resp.text[:200]
            logger.error("razorpay create_link failed: status=%s detail=%s", resp.status_code, detail)
            raise PaymentGatewayError(f"Razorpay rejected the payment link ({resp.status_code}): {detail}")

        data = resp.json()
        link_id = data.get("id")
        if not link_id:
            raise PaymentGatewayError("Razorpay response missing payment link id")

        expire_by = data.get("expire_by")
        resolved_expiry = (
            datetime.fromtimestamp(int(expire_by), tz=timezone.utc) if expire_by else expiry_at
        )

        return PaymentLinkResult(
            gateway=self.name,
            gateway_link_id=str(link_id),
            gateway_short_url=str(data.get("short_url") or ""),
            amount=from_minor_units(int(data.get("amount", body["amount"])), currency),
            currency=currency,
            status=_LINK_STATUS_MAP.get(str(data.get("status", "created")), STATUS_CREATED),
            expiry_at=resolved_expiry,
            raw=data,
        )

    # ── verify_webhook_signature ─────────────────────────────────────────
    def verify_webhook_signature(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> bool:
        """HMAC-SHA256 of the RAW body under the webhook secret, hex-compared
        constant-time against X-Razorpay-Signature."""
        if not self.webhook_secret:
            # No secret configured: refuse rather than accept. A live Razorpay
            # gateway with an unset webhook secret is a misconfiguration, and
            # accepting unauthenticated "paid" events would let anyone mark
            # links paid. (Stub mode is a separate gateway entirely.)
            logger.error("razorpay webhook rejected: RAZORPAY_WEBHOOK_SECRET is not configured")
            return False

        signature = _header(headers, "X-Razorpay-Signature")
        if not signature:
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode(),
            hashlib.sha256,
        ).hexdigest()

        try:
            return hmac.compare_digest(expected, signature.strip())
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

        # Razorpay nests entities: payload.payload.payment_link.entity
        entity: Mapping[str, Any] = {}
        inner = payload.get("payload")
        if isinstance(inner, Mapping):
            link_wrap = inner.get("payment_link")
            if isinstance(link_wrap, Mapping) and isinstance(link_wrap.get("entity"), Mapping):
                entity = link_wrap["entity"]

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

        # Event name is authoritative; fall back to the entity's own status.
        status = _EVENT_STATUS_MAP.get(envelope["event"] or "")
        if status is None and entity:
            status = _LINK_STATUS_MAP.get(str(entity.get("status", "")))
            # A 'created' entity status on a webhook tells us nothing new.
            if status == STATUS_CREATED:
                status = None
        envelope["status"] = status
        return envelope


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    """Case-insensitive header lookup (Starlette headers are already
    case-insensitive; a plain dict from a test is not)."""
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
