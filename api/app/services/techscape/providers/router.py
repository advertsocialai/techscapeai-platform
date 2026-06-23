"""
Channel router: picks the right provider for a channel + scenario, with fallbacks.

Default chains (per spec section 5.5):
  email     → SendGrid
  whatsapp  → Wapi  → SMS via Wapi
  sms       → Wapi  → SMS via Twilio (international)
  voice     → Twilio
  voicemail → Twilio
"""
from __future__ import annotations
import logging
from typing import Optional

from .sendgrid_provider import SendGridProvider
from .twilio_provider   import TwilioProvider
from .wapi_provider     import WapiProvider

logger = logging.getLogger(__name__)


class ChannelRouter:
    def __init__(self) -> None:
        self.sendgrid = SendGridProvider()
        self.twilio   = TwilioProvider()
        self.wapi     = WapiProvider()

    async def send(
        self,
        *,
        channel: str,
        to_email: Optional[str] = None,
        to_phone: Optional[str] = None,
        subject: Optional[str] = None,
        content: str,
        template_name: Optional[str] = None,
        template_params: Optional[list] = None,
    ) -> dict:
        """
        Route to the right provider. Returns:
          {provider, provider_message_id, delivery_status, cost, error?}
        """
        if channel == "email":
            if not to_email:
                return _err("email channel requires to_email")
            res = await self.sendgrid.send_email(
                to=to_email, subject=subject or "(no subject)",
                html=content, text=None,
            )
            return {**res, "provider": self.sendgrid.name}

        if channel == "whatsapp":
            if not to_phone:
                return _err("whatsapp channel requires to_phone")
            res = await self.wapi.send_whatsapp(
                to=to_phone, message=content,
                template_name=template_name, template_params=template_params,
            )
            if res["delivery_status"] == "failed":
                logger.info("WhatsApp failed; falling back to Wapi SMS")
                res = await self.wapi.send_sms(to=to_phone, message=content)
                return {**res, "provider": self.wapi.name, "fallback": "sms"}
            return {**res, "provider": self.wapi.name}

        if channel == "sms":
            if not to_phone:
                return _err("sms channel requires to_phone")
            res = await self.wapi.send_sms(to=to_phone, message=content)
            if res["delivery_status"] == "failed":
                logger.info("Wapi SMS failed; falling back to Twilio SMS")
                res = await self.twilio.send_sms(to=to_phone, body=content)
                return {**res, "provider": self.twilio.name, "fallback": "twilio"}
            return {**res, "provider": self.wapi.name}

        if channel in ("voice", "voicemail"):
            if not to_phone:
                return _err("voice channel requires to_phone")
            res = await self.twilio.make_voice_call(to=to_phone, say_text=content)
            return {**res, "provider": self.twilio.name}

        return _err(f"unsupported channel: {channel}")


def _err(msg: str) -> dict:
    return {"provider": "internal", "provider_message_id": None,
            "delivery_status": "failed", "cost": 0.0, "error": msg}


_router_singleton: ChannelRouter | None = None


def get_router() -> ChannelRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = ChannelRouter()
    return _router_singleton
