"""A moment on the laptop's wall clock, in the form a naive writer stores it.

The process is pinned to UTC and the stored corpus holds UTC digits, so a stamp
written at 09:00 on the laptop's wall clock (America/Vancouver) is stored as the
naive UTC digits of that moment — 16:00 in summer. A test that means "a stamp
written at this wall-clock time on the laptop" builds it here, rather than
hand-writing digits that would read seven or eight hours off.

    completed_at = laptop_wall(2026, 7, 21, 8, 30)  # 08:30 in Vancouver, stored naive

See: /docs/roadmap/utc-instants-arc.md § The bridge
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.utils.timestamp_helpers import as_stored_clock

#: The laptop's zone — the app default, ``DEFAULT_TIMEZONE``.
LAPTOP = ZoneInfo("America/Vancouver")


def laptop_wall(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> datetime:
    """The stored form (naive, on the stored clock) of a moment on the laptop's wall clock."""
    wall = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=LAPTOP)
    return as_stored_clock(wall)
