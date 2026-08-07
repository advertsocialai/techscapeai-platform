"""Outbound-hours guard (compliance.py) — 09:00-21:00 IST boundary cases."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    "hour,minute,expected",
    [
        (8, 59, False),   # just before window
        (9, 0, True),     # window opens
        (13, 0, True),    # midday
        (20, 59, True),   # last minute inside
        (21, 0, False),   # window closes
        (2, 0, False),    # deep night
    ],
)
def test_outbound_hours_boundaries(hour, minute, expected):
    from app.services.travel.compliance import is_within_outbound_hours

    dt = datetime(2026, 8, 7, hour, minute, tzinfo=IST)
    assert is_within_outbound_hours(dt) is expected
