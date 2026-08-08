"""
Stripe adapter — SKELETON ONLY. Phase 5, NOT this phase.

Scope note (deliberate, not an oversight)
-----------------------------------------
Phase 4 T2 ships Razorpay (India, INR) plus the deterministic stub. Stripe is
for the INTERNATIONAL branches and lands in Phase 5, alongside the multi-currency
settlement work that builds on migration 0015 (branches.currency +
fx_rate_snapshots + fx_rate_at()).

This file exists now so the ABC has its third conformant implementation and the
factory can already dispatch on gateway='stripe' (a value the payment_links
CHECK constraint accepts today). Every method raises NotImplementedError with an
explicit Phase 5 message — loudly unfinished, never silently wrong. Nothing in
Phase 4 routes here: the factory only returns StripeGateway on an explicit
opt-in request, never by default.

Phase 5 implementation notes (so the next agent starts from the right place):
  * Endpoint: POST https://api.stripe.com/v1/payment_links
      auth  : Bearer <STRIPE_SECRET_KEY>
      body  : application/x-www-form-urlencoded (NOT json) — Stripe's API is
              form-encoded, unlike Razorpay's.
      needs : a Price object first (POST /v1/prices) — Stripe payment links
              reference line_items[0][price], they do not take a bare amount.
  * Amounts are minor units (cents), same as Razorpay — reuse to_minor_units().
  * Webhook signature: the `Stripe-Signature` header is a comma-separated list
      of `t=<unix>` and `v1=<hex>` parts. The signed payload is
      f"{t}.{raw_body}", HMAC-SHA256 under the endpoint's signing secret
      (whsec_...). Compare with hmac.compare_digest, and ALSO reject timestamps
      outside a tolerance window (~5 min) — Stripe replay protection, which
      Razorpay's scheme does not have.
  * Events to map: checkout.session.completed / payment_intent.succeeded -> paid.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from .base import PaymentGateway, PaymentLinkResult

_PHASE_5 = (
    "StripeGateway is a Phase 5 deliverable (international branches) and is not "
    "implemented in Phase 4. Use the razorpay or stub gateway."
)


class StripeGateway(PaymentGateway):
    name = "stripe"

    def __init__(
        self,
        secret_key: str = "",
        *,
        webhook_secret: str = "",
        api_base: str = "https://api.stripe.com/v1",
    ) -> None:
        # Construction is allowed (so the factory and tests can reference the
        # class); every operation is what refuses.
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.api_base = api_base.rstrip("/")

    async def create_link(
        self,
        *,
        amount: Decimal,
        currency: str = "USD",
        description: str = "",
        reference_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        expiry_at: Optional[datetime] = None,
        notes: Optional[Mapping[str, Any]] = None,
    ) -> PaymentLinkResult:
        raise NotImplementedError(_PHASE_5)

    def verify_webhook_signature(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> bool:
        raise NotImplementedError(_PHASE_5)

    def parse_webhook_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(_PHASE_5)
