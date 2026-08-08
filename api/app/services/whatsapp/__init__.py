"""
WhatsApp integration package (Phase 4 T3).

    from app.services.whatsapp import get_whatsapp_provider
    provider = get_whatsapp_provider(business_id)
    row = await provider.send_template(to, "booking_confirmation", "en", components)

`get_whatsapp_provider` is the ONLY place a concrete provider is constructed.
Callers depend on the WhatsAppProvider ABC, which is what makes swapping direct
Meta Cloud API for a BSP (Gupshup / Interakt) a one-class change — see
meta_cloud.py's header for the full decision and the pre-agreed switch triggers.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .base import (
    OUTBOX_TABLE,
    SESSION_WINDOW_HOURS,
    SessionWindowClosed,
    WhatsAppError,
    WhatsAppProvider,
    WhatsAppSendError,
    clear_inbound_registry,
    last_inbound_at,
    normalize_msisdn,
    record_inbound,
    session_window_open,
)
from .meta_cloud import MetaCloudProvider
from .stub_provider import StubWhatsAppProvider

logger = logging.getLogger(__name__)


def get_whatsapp_provider(
    business_id: str,
    *,
    db: Any = None,
    force: Optional[str] = None,
) -> WhatsAppProvider:
    """
    Meta Cloud API when credentials are configured, stub otherwise.

    Credential absence is treated as an explicit instruction to stub, not as an
    error: the platform must stay fully exercisable without live WhatsApp
    access, and — more importantly — a misconfigured deploy must be incapable
    of sending real messages rather than half-capable.

    `force` ("stub" | "meta_cloud") exists for tests and for a future
    per-business override; forcing "meta_cloud" without credentials raises
    from MetaCloudProvider.__init__ rather than silently degrading.
    """
    if force == "stub":
        return StubWhatsAppProvider(business_id, db=db)
    if force == "meta_cloud" or MetaCloudProvider.configured():
        return MetaCloudProvider(business_id, db=db)

    logger.info(
        "WhatsApp credentials absent — using stub provider for business %s "
        "(messages are written to %s, never transmitted)",
        business_id, OUTBOX_TABLE,
    )
    return StubWhatsAppProvider(business_id, db=db)


__all__ = [
    "get_whatsapp_provider",
    "WhatsAppProvider",
    "MetaCloudProvider",
    "StubWhatsAppProvider",
    "WhatsAppError",
    "SessionWindowClosed",
    "WhatsAppSendError",
    "SESSION_WINDOW_HOURS",
    "OUTBOX_TABLE",
    "normalize_msisdn",
    "record_inbound",
    "last_inbound_at",
    "session_window_open",
    "clear_inbound_registry",
]
