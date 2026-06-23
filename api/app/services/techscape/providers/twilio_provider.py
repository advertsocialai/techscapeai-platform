"""Twilio voice + SMS provider — uses the REST API directly via httpx.

In stub mode (no credentials configured) returns a believable delivered
response so workflows complete end-to-end without real credentials.
"""
from __future__ import annotations
import logging
import secrets
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Spec costs
COST_PER_SMS_INTL = 0.0075
COST_PER_VOICE_MIN = 0.015  # midpoint of $0.01–$0.025/min


def _stub_id(kind: str) -> str:
    return f"stub-tw-{kind}-{secrets.token_hex(8)}"


class TwilioProvider:
    name = "twilio"

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ) -> None:
        self.sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_number = from_number or settings.TWILIO_PHONE_NUMBER

    @property
    def _configured(self) -> bool:
        return bool(self.sid and self.token and self.from_number)

    @property
    def _base(self) -> str:
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}"

    async def send_sms(self, *, to: str, body: str) -> dict:
        if not self._configured:
            logger.info("Twilio stub-SMS to %s", to)
            return {
                "provider_message_id": _stub_id("sms"),
                "delivery_status":     "delivered",
                "cost":                COST_PER_SMS_INTL,
                "stub":                True,
            }

        async with httpx.AsyncClient(
            auth=(self.sid, self.token), timeout=15,
        ) as client:
            try:
                r = await client.post(
                    f"{self._base}/Messages.json",
                    data={"To": to, "From": self.from_number, "Body": body},
                )
                r.raise_for_status()
                data = r.json()
                return {
                    "provider_message_id": data.get("sid"),
                    "delivery_status": "sent",
                    "cost": COST_PER_SMS_INTL,
                }
            except Exception as e:
                logger.exception("Twilio send_sms failed")
                return {"provider_message_id": None, "delivery_status": "failed",
                        "cost": 0.0, "error": str(e)[:240]}

    async def make_voice_call(
        self, *, to: str, twiml: Optional[str] = None,
        say_text: Optional[str] = None, status_callback: Optional[str] = None,
    ) -> dict:
        if not self._configured:
            logger.info("Twilio stub-voice to %s", to)
            return {
                "provider_message_id": _stub_id("call"),
                "delivery_status":     "delivered",
                "cost":                COST_PER_VOICE_MIN,
                "stub":                True,
            }

        if not twiml and say_text:
            twiml = f'<Response><Say voice="alice">{say_text}</Say></Response>'

        data = {"To": to, "From": self.from_number}
        if twiml:
            data["Twiml"] = twiml
        if status_callback:
            data["StatusCallback"] = status_callback
            data["StatusCallbackEvent"] = "initiated ringing answered completed"
            data["MachineDetection"] = "Enable"

        async with httpx.AsyncClient(
            auth=(self.sid, self.token), timeout=15,
        ) as client:
            try:
                r = await client.post(f"{self._base}/Calls.json", data=data)
                r.raise_for_status()
                return {
                    "provider_message_id": r.json().get("sid"),
                    "delivery_status": "sent",
                    "cost": COST_PER_VOICE_MIN,
                }
            except Exception as e:
                logger.exception("Twilio make_voice_call failed")
                return {"provider_message_id": None, "delivery_status": "failed",
                        "cost": 0.0, "error": str(e)[:240]}
