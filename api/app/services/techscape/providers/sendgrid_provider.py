"""SendGrid email provider — uses the v3 mail/send REST endpoint.

When no API key is configured the provider runs in **stub mode**:
returns a believable delivered response with a fake provider_message_id so the
rest of the platform (workflows, logs, analytics) works end-to-end without
real credentials. This is intentional for demos and CI environments.
"""
from __future__ import annotations
import logging
import secrets
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
COST_PER_EMAIL = 0.0001  # spec: $0.0001/email at volume


def _stub_id(prefix: str) -> str:
    return f"stub-{prefix}-{secrets.token_hex(8)}"


class SendGridProvider:
    name = "sendgrid"

    def __init__(self, api_key: Optional[str] = None, from_email: Optional[str] = None) -> None:
        self.api_key = api_key or settings.SENDGRID_API_KEY
        self.from_email = from_email or settings.FROM_EMAIL

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html: Optional[str] = None,
        text: Optional[str] = None,
    ) -> dict:
        """
        Returns:
            {provider_message_id, delivery_status, cost, error?}
        """
        if not self.api_key:
            logger.info("SendGrid stub-send to %s (subject=%s)", to, subject)
            return {
                "provider_message_id": _stub_id("sg"),
                "delivery_status": "delivered",
                "cost": COST_PER_EMAIL,
                "stub": True,
            }

        body = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email},
            "subject": subject,
            "content": [
                c for c in [
                    {"type": "text/plain", "value": text} if text else None,
                    {"type": "text/html",  "value": html} if html else None,
                ] if c
            ] or [{"type": "text/plain", "value": ""}],
            "tracking_settings": {
                "open_tracking":  {"enable": True},
                "click_tracking": {"enable": True},
            },
        }

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.post(
                    SENDGRID_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type":  "application/json",
                    },
                    json=body,
                )
                r.raise_for_status()
                msg_id = r.headers.get("X-Message-Id")
                return {
                    "provider_message_id": msg_id,
                    "delivery_status": "sent",
                    "cost": COST_PER_EMAIL,
                }
            except httpx.HTTPStatusError as e:
                logger.error("SendGrid send failed: %s %s", e.response.status_code, e.response.text)
                return {
                    "provider_message_id": None,
                    "delivery_status": "failed",
                    "cost": 0.0,
                    "error": f"{e.response.status_code} {e.response.text[:240]}",
                }
            except Exception as e:
                logger.exception("SendGrid send unexpected error")
                return {
                    "provider_message_id": None,
                    "delivery_status": "failed",
                    "cost": 0.0,
                    "error": str(e)[:240],
                }
