"""Wapi WhatsApp + SMS provider.

In stub mode (no token configured) returns a believable delivered response so
workflows complete end-to-end without real credentials.
"""
from __future__ import annotations
import logging
import secrets
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

COST_PER_WHATSAPP = 0.03  # spec midpoint of $0.01–$0.05
COST_PER_SMS      = 0.05  # spec midpoint of $0.02–$0.08


def _stub_id(kind: str) -> str:
    return f"stub-wapi-{kind}-{secrets.token_hex(8)}"


class WapiProvider:
    name = "wapi"

    def __init__(self, api_token: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.token = api_token or settings.WAPI_API_TOKEN
        self.base  = base_url  or settings.WAPI_BASE_URL

    @property
    def _configured(self) -> bool:
        return bool(self.token)

    async def send_whatsapp(
        self, *, to: str, message: str,
        template_name: Optional[str] = None,
        template_params: Optional[list[Any]] = None,
        media_url: Optional[str] = None,
    ) -> dict:
        if not self._configured:
            logger.info("Wapi stub-WhatsApp to %s", to)
            return {
                "provider_message_id": _stub_id("wa"),
                "delivery_status":     "delivered",
                "cost":                COST_PER_WHATSAPP,
                "stub":                True,
            }

        if template_name:
            payload = {
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en"},
                    "components": [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(p)} for p in (template_params or [])
                        ],
                    }],
                },
            }
        else:
            payload = {"to": to, "type": "text", "text": {"body": message}}
            if media_url:
                payload = {"to": to, "type": "image",
                           "image": {"link": media_url, "caption": message}}

        return await self._post("/api/send/message", payload, COST_PER_WHATSAPP)

    async def send_sms(self, *, to: str, message: str) -> dict:
        if not self._configured:
            logger.info("Wapi stub-SMS to %s", to)
            return {
                "provider_message_id": _stub_id("sms"),
                "delivery_status":     "delivered",
                "cost":                COST_PER_SMS,
                "stub":                True,
            }
        return await self._post("/api/send/sms", {"to": to, "message": message}, COST_PER_SMS)

    async def _post(self, path: str, payload: dict, cost: float) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.post(
                    f"{self.base}{path}",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type":  "application/json",
                    },
                    json=payload,
                )
                r.raise_for_status()
                data = r.json() if r.content else {}
                return {
                    "provider_message_id": data.get("message_id") or data.get("id"),
                    "delivery_status":     "sent",
                    "cost":                cost,
                }
            except Exception as e:
                logger.exception("Wapi POST %s failed", path)
                return {"provider_message_id": None, "delivery_status": "failed",
                        "cost": 0.0, "error": str(e)[:240]}
