"""
Direct Meta Cloud API provider (Phase 4 T3).

=============================================================================
DECISION: direct Meta Cloud API, NOT an Indian BSP (Gupshup / Interakt)
=============================================================================
This was weighed on the three axes that actually matter for GoGaga, not
rubber-stamped. The BSP case is real and it is recorded here so the reversal
is cheap if reality disagrees with us.

1. TEMPLATE-APPROVAL TURNAROUND — narrower gap than the folklore claims.
   Meta's template review is now largely automated; the common case is minutes,
   with manual escalation only on borderline marketing copy. What Indian BSPs
   actually sell here is not raw speed but *authoring assistance* and legible
   rejection reasons — an ops nicety, not an API capability. GoGaga's Phase-4
   template set is small and utility-shaped (booking confirmation, itinerary
   sent, payment link, D1/D3/D7 follow-up) — the category Meta approves fastest
   and least contentiously. VERDICT: weak advantage BSP, low weight.

2. MULTI-TENANT NUMBERS — each agency eventually needs its OWN number.
   This is the axis that decided it, and it cuts BOTH ways.
   Direct: we must become a Meta Tech Provider — app review for
   whatsapp_business_messaging + whatsapp_business_management, our own Business
   Verification, and an Embedded Signup flow so each agency attaches its own
   WABA and number under our app. Real, front-loaded engineering.
   BSP: their partner API gives us the same multi-tenancy on day one, plus
   humans who walk a non-technical Indian travel agency through *its own*
   Business Verification (GST/CIN/registered-address docs) — which is the true
   bottleneck in India, and it does not disappear under either option.
   The deciding observation: under a BSP we still build tenant-scoped
   credential plumbing, still handle Embedded Signup semantics, and still own
   per-tenant number state — we just build it against a proprietary API we
   cannot port. The Tech Provider work is largely one-time; the BSP dependency
   is permanent. VERDICT: advantage direct, high weight.

3. COST — clear, and it compounds.
   Meta bills conversations/messages at list rates; India is among the cheapest
   markets. A BSP layers a per-message markup (and typically a monthly platform
   fee per tenant) on top of those same Meta rates. At one agency that is
   noise; across N agencies × routine utility volume it is a permanent
   percentage tax on every message GoGaga will ever send, and it grows exactly
   as the product succeeds. Direct also lets us exploit Meta's own pricing
   structure (utility messages inside an open service window are the cheap
   path) because we control the session window — see base.py.
   VERDICT: advantage direct, high weight.

TRADEOFF WE ARE EXPLICITLY ACCEPTING: slower, unassisted onboarding. We absorb
Tech Provider app review, our own Business Verification, and — worst — we
become the support desk when an agency's verification stalls. That is an ops
cost paid in Phase 4/5, in exchange for no per-message markup and no
proprietary lock-in for the life of the product.

SWITCH TRIGGERS (pre-agreed, so this is a decision and not a religion):
  * Meta Tech Provider app review or GoGaga's Business Verification stalls
    beyond ~2 weeks and blocks the first paying agency, OR
  * >2 of the initial utility templates get rejected with opaque reasons, OR
  * agency-side Business Verification failure becomes the top onboarding
    drop-off.
Any of those => adopt Gupshup or Interakt. Because everything routes through
WhatsAppProvider (base.py), that is a new subclass + one factory branch. No
caller, schema, or outbox-row change.
=============================================================================

SAFETY: this class REFUSES TO CONSTRUCT without real credentials. There are no
credentials in this environment, so the factory returns StubWhatsAppProvider
and no real message can be sent, by construction rather than by convention.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings

from .base import WhatsAppProvider, WhatsAppSendError, normalize_msisdn, session_window_open

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"
DEFAULT_TIMEOUT_SEC = 20.0


class MetaCloudProvider(WhatsAppProvider):
    """
    POST https://graph.facebook.com/{version}/{phone_number_id}/messages
    Authorization: Bearer {access_token}

    Credentials are read with getattr() defaults so app/core/config.py needs no
    edit (it is owned by another task). Once these land in Settings the getattr
    calls keep working unchanged.

    Per-tenant credentials: `phone_number_id`/`access_token` are constructor
    arguments precisely because each agency will eventually own its number.
    When the tenant-credential table lands, `_resolve_credentials()` is the
    single place that changes.
    """

    name = "meta_cloud"

    def __init__(
        self,
        business_id: str,
        *,
        db: Any = None,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> None:
        super().__init__(business_id, db=db)
        token, pnid = self._resolve_credentials(business_id)
        self.access_token = access_token or token
        self.phone_number_id = phone_number_id or pnid
        self.api_version = (
            api_version
            or getattr(settings, "WHATSAPP_API_VERSION", "")
            or DEFAULT_API_VERSION
        )
        if not (self.access_token and self.phone_number_id):
            # Hard stop. A half-configured live provider is how accidental or
            # misdirected real sends happen; the factory must fall back to stub.
            raise RuntimeError(
                "MetaCloudProvider requires WHATSAPP_ACCESS_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID. Use get_whatsapp_provider(), which "
                "falls back to the stub provider when credentials are absent."
            )

    # -- credentials ----------------------------------------------------------
    @staticmethod
    def _resolve_credentials(business_id: str) -> tuple[str, str]:
        """
        Global credentials today; per-business lookup tomorrow.

        This is THE multi-tenant seam: when each agency has its own WABA and
        number (see the decision note above), this reads that tenant's row and
        nothing else in the package changes.
        """
        return (
            getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "",
            getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "",
        )

    @classmethod
    def configured(cls) -> bool:
        """True iff a real send is possible. The factory's only gate."""
        return bool(
            (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "")
            and (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "")
        )

    @property
    def _url(self) -> str:
        return f"{GRAPH_BASE}/{self.api_version}/{self.phone_number_id}/messages"

    # -- contract -------------------------------------------------------------
    async def check_session_window(self, to: str) -> bool:
        """
        Meta exposes no endpoint to query the window, so it is derived from the
        last inbound message we observed (base.py). Unknown => closed.
        """
        return session_window_open(normalize_msisdn(to))

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> dict:
        to_number = normalize_msisdn(to)
        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language},
        }
        if components:
            template["components"] = components
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "template",
            "template": template,
        }
        return await self._dispatch(
            payload,
            to_number=to_number,
            message_type="template",
            template_name=template_name,
            language=language,
        )

    async def send_freeform(self, to: str, text: str) -> dict:
        # The ABC has already proven the 24h window is open — see base.py's
        # __init_subclass__ guard. Do not re-check here.
        to_number = normalize_msisdn(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self._dispatch(
            payload,
            to_number=to_number,
            message_type="freeform",
            template_name=None,
            language="en",
        )

    # -- transport ------------------------------------------------------------
    async def _dispatch(
        self,
        payload: dict[str, Any],
        *,
        to_number: str,
        message_type: str,
        template_name: Optional[str],
        language: str,
    ) -> dict:
        """
        Write-ahead, then send. The 'queued' row exists BEFORE the network call
        so a crash or timeout leaves an inspectable record instead of an
        untraceable maybe-sent message.
        """
        row = self._outbox_insert(
            to_number=to_number,
            message_type=message_type,
            payload=payload,
            status="queued",
            language=language,
            template_name=template_name,
        )
        outbox_id = row.get("id")

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SEC) as client:
                resp = await client.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:  # network/timeout — nothing was confirmed
            logger.error("WhatsApp send failed (transport) to %s: %s", to_number, exc)
            self._fail(outbox_id, f"transport error: {exc}")
            raise WhatsAppSendError(f"WhatsApp transport error: {exc}", outbox_id=outbox_id)

        if resp.status_code >= 400:
            detail = _error_detail(resp)
            logger.error(
                "WhatsApp send rejected (%s) to %s: %s", resp.status_code, to_number, detail
            )
            self._fail(outbox_id, f"HTTP {resp.status_code}: {detail}")
            raise WhatsAppSendError(
                f"Meta Cloud API rejected the message (HTTP {resp.status_code}): {detail}",
                outbox_id=outbox_id,
            )

        body = _safe_json(resp)
        messages = body.get("messages") or []
        provider_message_id = messages[0].get("id") if messages else None
        logger.info("WhatsApp %s sent to %s (wamid=%s)", message_type, to_number, provider_message_id)

        if not outbox_id:
            return {**row, "status": "sent", "provider_message_id": provider_message_id}
        return self._outbox_update(outbox_id, {
            "status": "sent",
            "provider_message_id": provider_message_id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

    def _fail(self, outbox_id: Optional[str], error: str) -> None:
        if not outbox_id:
            return
        try:
            self._outbox_update(outbox_id, {"status": "failed", "error": error[:4000]})
        except Exception:  # never let audit-write failure mask the real error
            logger.exception("Could not mark outbox row %s failed", outbox_id)


def _safe_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}
    except Exception:
        return {}


def _error_detail(resp: httpx.Response) -> str:
    err = _safe_json(resp).get("error") or {}
    if isinstance(err, dict) and err:
        parts = [str(err.get(k)) for k in ("message", "error_data", "code") if err.get(k)]
        if parts:
            return " | ".join(parts)
    return (resp.text or "")[:500]
