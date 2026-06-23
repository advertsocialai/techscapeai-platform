"""
TCPA / time-of-day enforcement for SMS, voice and voicemail channels.

Default allowed window: 08:00–21:00 local time (configurable).
When a channel is blocked we surface that as a `failed` log row with a clear
reason instead of silently sending.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

REGULATED_CHANNELS = {"sms", "voice", "voicemail"}


def is_within_tcpa_window(
    *,
    channel: str,
    timezone_str: str = "UTC",
    now: Optional[datetime] = None,
    start_hour: int = 8,
    end_hour:   int = 21,
) -> tuple[bool, str]:
    """
    Returns (allowed, reason). If `channel` is not regulated, always allowed.
    """
    if channel not in REGULATED_CHANNELS:
        return True, "non-regulated channel"
    try:
        tz = ZoneInfo(timezone_str or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    cur = (now or datetime.now(tz)).astimezone(tz)
    h = cur.hour
    if start_hour <= h < end_hour:
        return True, f"within {start_hour:02d}-{end_hour:02d} {timezone_str}"
    return False, (
        f"TCPA window {start_hour:02d}:00–{end_hour:02d}:00 "
        f"{timezone_str} not satisfied (now is {cur.strftime('%H:%M %Z')})"
    )
