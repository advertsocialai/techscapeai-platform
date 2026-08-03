"""
Outbound compliance guard (Phase 2 T9) — 09:00-21:00 IST window per
gogaga-backend's domain rules.

Not wired to any endpoint yet: Phase 2 only builds the INBOUND voice
pipeline (answering calls FROM customers) — there is no outbound call/
message feature in this repo yet for it to gate. Built as a standalone,
independently-verified utility so whichever Phase 3 feature makes
outbound calls/SMS/WhatsApp can call is_within_outbound_hours() without
re-deriving the IST conversion.
"""
from __future__ import annotations
from datetime import datetime, time, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
_WINDOW_START = time(9, 0)
_WINDOW_END = time(21, 0)


def is_within_outbound_hours(when: datetime | None = None) -> bool:
    """`when` defaults to now (UTC or any tz-aware datetime — converted
    to IST). Naive datetimes are assumed to already be UTC."""
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ist_time = when.astimezone(IST).time()
    return _WINDOW_START <= ist_time < _WINDOW_END
