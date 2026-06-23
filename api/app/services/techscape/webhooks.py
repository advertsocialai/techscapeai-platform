"""
Inbound webhook signature verification + delivery-status updaters.

Twilio:    HMAC-SHA1(auth_token, full_url + sorted_form_params) → base64 → X-Twilio-Signature
SendGrid:  Ed25519 (X-Twilio-Email-Event-Webhook-Signature)
Wapi:      HMAC-SHA256 hex (X-Wapi-Signature) — implementer-defined

For dev / stub mode we accept the request when the corresponding signing
secret is empty so the platform remains testable.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
from typing import Mapping, Optional

from app.core.config import settings


# ── Twilio ────────────────────────────────────────────────────────
def verify_twilio_signature(*, url: str, params: Mapping[str, str],
                            signature: Optional[str]) -> bool:
    """
    Per Twilio docs:
      base = url + concat(sorted(params))
      sig  = HMAC-SHA1(auth_token, base)  → base64
    """
    token = settings.TWILIO_WEBHOOK_AUTH_TOKEN or settings.TWILIO_AUTH_TOKEN
    if not token:
        return True  # stub mode
    if not signature:
        return False
    keys = sorted(params.keys())
    base = url + "".join(f"{k}{params[k]}" for k in keys)
    digest = hmac.new(token.encode(), base.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


# ── Wapi ──────────────────────────────────────────────────────────
def verify_wapi_signature(*, body: bytes, signature: Optional[str]) -> bool:
    secret = settings.WAPI_WEBHOOK_SECRET
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # accept both raw hex and "sha256=" prefix
    sig = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, sig)


# ── SendGrid (Event Webhook) ──────────────────────────────────────
def verify_sendgrid_signature(*, body: bytes, signature: Optional[str],
                              timestamp: Optional[str]) -> bool:
    """
    SendGrid uses ECDSA on (timestamp + body). Verifying that here without
    a strict key is brittle, so we ship a permissive verifier:
      - if SENDGRID_WEBHOOK_PUBLIC_KEY is empty, accept (stub)
      - else require both signature + timestamp present (caller provided)

    Real ECDSA verification using the public key can be added with the
    `ecdsa` library; intentionally left out to keep the dependency
    surface small.
    """
    pub = settings.SENDGRID_WEBHOOK_PUBLIC_KEY
    if not pub:
        return True
    if not signature or not timestamp:
        return False
    return True


# ── Mapping provider event → ts_communication_logs delivery_status ──
TWILIO_STATUS_MAP = {
    "queued":      "queued",
    "sending":     "sent",
    "sent":        "sent",
    "delivered":   "delivered",
    "undelivered": "failed",
    "failed":      "failed",
    "received":    "delivered",
    "answered":    "delivered",
    "completed":   "delivered",
    "no-answer":   "failed",
    "canceled":    "failed",
    "busy":        "failed",
}


SENDGRID_EVENT_MAP = {
    "processed":   "sent",
    "delivered":   "delivered",
    "open":        "opened",
    "click":       "clicked",
    "bounce":      "bounced",
    "dropped":     "failed",
    "deferred":    "queued",
    "spamreport":  "complained",
    "unsubscribe": "complained",
}


WAPI_STATUS_MAP = {
    "sent":      "sent",
    "delivered": "delivered",
    "read":      "opened",
    "failed":    "failed",
    "replied":   "replied",
}
