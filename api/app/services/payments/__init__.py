"""
Payment gateway package (Phase 4 T2).

Public surface:
    get_gateway(name=None) -> PaymentGateway     # the factory
    gateway_mode()         -> "razorpay" | "stub"
    PaymentGateway, PaymentLinkResult, PaymentGatewayError
    status-machine helpers: can_transition, is_terminal, STATUS_*

FACTORY RULE
------------
Razorpay is selected only when BOTH RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are
present in settings. Otherwise the deterministic StubGateway is returned.

Credentials are read via _setting(), a getattr(settings, "...", "") indirection.
RAZORPAY_KEY_ID/KEY_SECRET/WEBHOOK_SECRET are now declared fields in
config.py's Settings class, so this correctly picks up real env values.
_setting() itself stays — it's still load-bearing for STRIPE_SECRET_KEY /
STRIPE_WEBHOOK_SECRET / STUB_WEBHOOK_SECRET, none of which are (or need to be)
declared Settings fields, since Stripe is a Phase 5 skeleton that always
raises NotImplementedError.

NOTE (found in a full-repo audit): this indirection previously assumed
pydantic-settings would attach ANY matching env var to the Settings instance
even if config.py never declared the field. That assumption was false —
config.py sets extra="ignore", which silently drops undeclared env vars, so
razorpay_configured() stayed False forever regardless of what was set in the
environment. Declaring the fields in config.py was the actual fix; this
indirection alone was not enough.

In this sandbox no Razorpay credentials exist, so gateway_mode() == "stub" and
NO network call is ever made.
"""
from __future__ import annotations

import logging
from typing import Optional

from .base import (
    ALLOWED_TRANSITIONS,
    PAYMENT_LINK_STATUSES,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_PAID,
    STATUS_SENT,
    STATUS_VIEWED,
    PaymentGateway,
    PaymentGatewayError,
    PaymentLinkResult,
    can_transition,
    currency_exponent,
    from_minor_units,
    is_terminal,
    normalize_currency,
    status_rank,
    to_minor_units,
)
from .razorpay_gateway import RazorpayGateway
from .stripe_gateway import StripeGateway
from .stub_gateway import DEFAULT_STUB_WEBHOOK_SECRET, STUB_URL_SCHEME, StubGateway

logger = logging.getLogger(__name__)


def _setting(name: str, default: str = "") -> str:
    """Read a setting without requiring config.py to declare it."""
    try:
        from app.core.config import settings
    except Exception:  # pragma: no cover - config import failure
        return default
    value = getattr(settings, name, default)
    return value if isinstance(value, str) else (str(value) if value else default)


def razorpay_configured() -> bool:
    """True only when BOTH Razorpay credentials are present."""
    return bool(_setting("RAZORPAY_KEY_ID") and _setting("RAZORPAY_KEY_SECRET"))


def gateway_mode() -> str:
    """Which backend the factory would pick right now: 'razorpay' or 'stub'."""
    return "razorpay" if razorpay_configured() else "stub"


def get_gateway(name: Optional[str] = None) -> PaymentGateway:
    """Return a PaymentGateway.

    name=None      -> razorpay when credentials are configured, else stub.
    name='razorpay'-> live gateway; raises PaymentGatewayError if unconfigured
                      (never silently downgrades to stub — that would mint a
                      stub:// link where real money was expected).
    name='stub'    -> deterministic stub.
    name='stripe'  -> Phase 5 skeleton; every method raises NotImplementedError.
    """
    requested = (name or "").strip().lower()

    if requested == "stub":
        return StubGateway(webhook_secret=_setting("STUB_WEBHOOK_SECRET", DEFAULT_STUB_WEBHOOK_SECRET))

    if requested == "stripe":
        return StripeGateway(
            secret_key=_setting("STRIPE_SECRET_KEY"),
            webhook_secret=_setting("STRIPE_WEBHOOK_SECRET"),
        )

    if requested == "razorpay":
        if not razorpay_configured():
            raise PaymentGatewayError(
                "Razorpay was requested explicitly but RAZORPAY_KEY_ID / "
                "RAZORPAY_KEY_SECRET are not configured."
            )
        return _razorpay()

    if requested and requested not in ("razorpay", "stripe", "stub"):
        raise PaymentGatewayError(f"Unknown payment gateway: {requested!r}")

    # Auto-select.
    if razorpay_configured():
        return _razorpay()
    logger.info("payments: no Razorpay credentials — using deterministic StubGateway (stub:// links)")
    return StubGateway(webhook_secret=_setting("STUB_WEBHOOK_SECRET", DEFAULT_STUB_WEBHOOK_SECRET))


def _razorpay() -> RazorpayGateway:
    return RazorpayGateway(
        key_id=_setting("RAZORPAY_KEY_ID"),
        key_secret=_setting("RAZORPAY_KEY_SECRET"),
        webhook_secret=_setting("RAZORPAY_WEBHOOK_SECRET"),
    )


__all__ = [
    "get_gateway", "gateway_mode", "razorpay_configured",
    "PaymentGateway", "PaymentGatewayError", "PaymentLinkResult",
    "RazorpayGateway", "StripeGateway", "StubGateway",
    "STUB_URL_SCHEME", "DEFAULT_STUB_WEBHOOK_SECRET",
    "PAYMENT_LINK_STATUSES", "ALLOWED_TRANSITIONS",
    "can_transition", "is_terminal", "status_rank",
    "STATUS_CREATED", "STATUS_SENT", "STATUS_VIEWED", "STATUS_PAID", "STATUS_EXPIRED",
    "normalize_currency", "currency_exponent", "to_minor_units", "from_minor_units",
]
