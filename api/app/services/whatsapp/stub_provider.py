"""
Stub WhatsApp provider (Phase 4 T3) — the default in every environment that
has no Meta credentials, including this one.

CONTRACT: it builds the EXACT payload meta_cloud.py would put on the wire, then
writes it to `whatsapp_outbox` with status='stubbed' and performs no network
I/O whatsoever. There is no code path from this class to httpx. Sending a real
WhatsApp message requires explicit human sign-off and real credentials; this
class exists so the rest of Phase 4 can be built and verified without either.

The acceptance criterion for T3 is a correctly-formatted outbox row, so the
payload construction below is deliberately duplicated from meta_cloud rather
than simplified: a stubbed row is only useful if it is byte-identical to the
live request body. Any divergence would make the stub a lie.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from .base import WhatsAppProvider, normalize_msisdn, session_window_open

logger = logging.getLogger(__name__)


def _stub_message_id() -> str:
    """Shaped like Meta's wamid but unmistakably synthetic."""
    return f"stub-wa-{secrets.token_hex(10)}"


class StubWhatsAppProvider(WhatsAppProvider):
    """No-network provider. Every send lands in whatsapp_outbox as 'stubbed'."""

    name = "stub"

    async def check_session_window(self, to: str) -> bool:
        """
        Identical rule to live mode — the stub does NOT relax the 24-hour
        window. If it did, code written against the stub would start failing
        the day credentials arrive, which is precisely when it is most
        expensive to discover.
        """
        return session_window_open(
            normalize_msisdn(to), business_id=self.business_id
        )

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
        logger.info(
            "WhatsApp STUB template '%s' -> %s (not transmitted)", template_name, to_number
        )
        return self._record(
            to_number=to_number,
            message_type="template",
            payload=payload,
            language=language,
            template_name=template_name,
        )

    async def send_freeform(self, to: str, text: str) -> dict:
        # Reached only when the ABC's window guard passed (see base.py).
        to_number = normalize_msisdn(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        logger.info("WhatsApp STUB freeform -> %s (not transmitted)", to_number)
        return self._record(
            to_number=to_number,
            message_type="freeform",
            payload=payload,
            language="en",
            template_name=None,
        )

    def _record(
        self,
        *,
        to_number: str,
        message_type: str,
        payload: dict[str, Any],
        language: str,
        template_name: Optional[str],
    ) -> dict:
        return self._outbox_insert(
            to_number=to_number,
            message_type=message_type,
            payload=payload,
            status="stubbed",
            language=language,
            template_name=template_name,
            provider_message_id=_stub_message_id(),
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
