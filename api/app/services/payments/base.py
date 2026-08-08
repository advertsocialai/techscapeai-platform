"""
Payment gateway abstraction (Phase 4 T2).

Every gateway — Razorpay (live, India), Stripe (Phase 5, international),
and the deterministic Stub (no credentials, no network) — implements the
same ABC. The router never branches on provider: it asks the factory for a
gateway and calls the same three methods. That is what makes the stub a
real backend rather than a mock, and what makes every downstream code path
(status machine, DB transitions, webhook handling) genuinely testable here
and genuinely correct in production.

Contract, in three methods:
  create_link(...)                       -> PaymentLinkResult
  verify_webhook_signature(raw, headers) -> bool
  parse_webhook_event(payload)           -> dict   (normalized envelope)

MONEY
-----
`amount` crosses this boundary as a Decimal in MAJOR units (rupees, dollars),
matching payment_links.amount NUMERIC(12,2). Providers want minor-unit
integers (paise, cents); each adapter converts at its own edge via
to_minor_units(). Never float, anywhere.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, Optional

# ── Status machine ────────────────────────────────────────────────────────
# Mirrors the CHECK constraint in supabase/migrations/0010_payment_links.sql.
# Forward-only: a link never moves backwards, so a late-arriving 'viewed' webhook
# can never demote a row that is already 'paid'.
STATUS_CREATED = "created"
STATUS_SENT = "sent"
STATUS_VIEWED = "viewed"
STATUS_PAID = "paid"
STATUS_EXPIRED = "expired"

PAYMENT_LINK_STATUSES: tuple[str, ...] = (
    STATUS_CREATED, STATUS_SENT, STATUS_VIEWED, STATUS_PAID, STATUS_EXPIRED,
)

#: Rank along the happy path. 'expired' is off-path (terminal, no rank).
_STATUS_RANK: dict[str, int] = {
    STATUS_CREATED: 0,
    STATUS_SENT: 1,
    STATUS_VIEWED: 2,
    STATUS_PAID: 3,
}

#: Explicit adjacency. Skipping ahead is allowed (a customer can pay a link
#: that was never marked 'viewed'), but going backwards never is.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_CREATED: frozenset({STATUS_SENT, STATUS_VIEWED, STATUS_PAID, STATUS_EXPIRED}),
    STATUS_SENT:    frozenset({STATUS_VIEWED, STATUS_PAID, STATUS_EXPIRED}),
    STATUS_VIEWED:  frozenset({STATUS_PAID, STATUS_EXPIRED}),
    STATUS_PAID:    frozenset(),   # terminal — money moved, nothing follows
    STATUS_EXPIRED: frozenset(),   # terminal — mint a new link instead
}


def can_transition(current: str, target: str) -> bool:
    """True iff `current` -> `target` is a legal move in the status machine."""
    if current not in ALLOWED_TRANSITIONS or target not in PAYMENT_LINK_STATUSES:
        return False
    return target in ALLOWED_TRANSITIONS[current]


def is_terminal(status: str) -> bool:
    return status in (STATUS_PAID, STATUS_EXPIRED)


def status_rank(status: str) -> int:
    """Happy-path position; -1 for off-path/unknown ('expired')."""
    return _STATUS_RANK.get(status, -1)


# ── Currency ──────────────────────────────────────────────────────────────
#: Currencies whose smallest unit IS the major unit (no cents). Everything
#: else is assumed to be 2-decimal, which covers every currency this platform
#: transacts in. Getting this wrong overcharges by 100x, so it is explicit.
_ZERO_DECIMAL_CURRENCIES: frozenset[str] = frozenset({
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW",
    "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
})

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def normalize_currency(currency: str) -> str:
    """Validate + upper-case an ISO-4217 alpha-3 code."""
    if not currency or not _CURRENCY_RE.match(currency):
        raise ValueError(f"Invalid ISO-4217 currency code: {currency!r}")
    return currency.upper()


def currency_exponent(currency: str) -> int:
    return 0 if normalize_currency(currency) in _ZERO_DECIMAL_CURRENCIES else 2


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Major units (Decimal) -> provider minor-unit integer (paise/cents).

    Half-up rounding at the currency's exponent. Rejects sub-unit precision
    loss silently only in the last place, which is the standard behaviour
    gateways themselves apply.
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("amount must be > 0")
    exp = currency_exponent(currency)
    quantum = Decimal(1).scaleb(-exp)
    return int((amount.quantize(quantum, rounding=ROUND_HALF_UP)) * (10 ** exp))


def from_minor_units(minor: int, currency: str) -> Decimal:
    """Provider minor-unit integer -> major-unit Decimal."""
    exp = currency_exponent(currency)
    return (Decimal(int(minor)) / (10 ** exp)).quantize(Decimal(1).scaleb(-exp))


# ── Result / event envelopes ──────────────────────────────────────────────
@dataclass(frozen=True)
class PaymentLinkResult:
    """What every gateway returns from create_link()."""
    gateway: str
    gateway_link_id: str
    gateway_short_url: str
    amount: Decimal
    currency: str
    status: str = STATUS_CREATED
    expiry_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        """Column subset of public.payment_links this result owns."""
        return {
            "gateway": self.gateway,
            "gateway_link_id": self.gateway_link_id,
            "gateway_short_url": self.gateway_short_url,
            "amount": str(self.amount),
            "currency": self.currency,
            "status": self.status,
            "expiry_at": self.expiry_at.isoformat() if self.expiry_at else None,
        }


class PaymentGatewayError(RuntimeError):
    """Provider call failed. Callers map this to 502, never to a 500."""


# ── The ABC ───────────────────────────────────────────────────────────────
class PaymentGateway(ABC):
    """Provider-agnostic payment-link interface.

    Implementations MUST NOT raise on a hostile webhook payload — an attacker
    controls that input. verify_webhook_signature returns False and
    parse_webhook_event returns an envelope with status=None rather than
    blowing up the request handler.
    """

    #: Value written to payment_links.gateway — must be in that CHECK list.
    name: str = "base"

    @abstractmethod
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
        """Mint a payment link at the provider.

        `reference_id` is our payment_links.id, echoed back by the provider on
        every webhook — it is the idempotency + correlation key.
        Raises PaymentGatewayError on provider failure.
        """

    @abstractmethod
    def verify_webhook_signature(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> bool:
        """Authenticate a webhook.

        MUST operate on the RAW request body — re-serializing parsed JSON
        changes key order/whitespace and breaks the digest. MUST compare with
        hmac.compare_digest, never ==, so the check is constant-time.
        Returns bool; never raises.
        """

    @abstractmethod
    def parse_webhook_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize a provider event into this envelope:

            {
              "event":           str | None,   # provider event name, verbatim
              "gateway":         str,
              "gateway_link_id": str | None,   # resolves our row
              "reference_id":    str | None,   # our payment_links.id, if echoed
              "status":          str | None,   # mapped to OUR status vocabulary
              "amount":          Decimal | None,
              "currency":        str | None,
              "raw":             dict,
            }

        `status` is None when the event carries no status meaning for us —
        the caller then no-ops instead of guessing. Never raises.
        """


__all__ = [
    "PaymentGateway", "PaymentGatewayError", "PaymentLinkResult",
    "PAYMENT_LINK_STATUSES", "ALLOWED_TRANSITIONS", "can_transition",
    "is_terminal", "status_rank",
    "STATUS_CREATED", "STATUS_SENT", "STATUS_VIEWED", "STATUS_PAID", "STATUS_EXPIRED",
    "normalize_currency", "currency_exponent", "to_minor_units", "from_minor_units",
]
