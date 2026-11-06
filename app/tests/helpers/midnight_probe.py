"""A pytest plugin that makes a run straddle midnight, to find what a crossing breaks.

    MIDNIGHT_PROBE=call uv run python -m pytest tests/integration -p tests.helpers.midnight_probe

``MIDNIGHT_PROBE`` picks the boundary the clock crosses:

- ``import``: every module is collected on the day before and every test runs on the day
  after, which finds a day fixed at import.
- ``call``: each test's setup runs on the day before and its call on the day after, which
  finds a seed that reads today and a read that reads it again. It is the only instrument
  for that shape: ``tests/unit/test_import_time_clock_reads.py`` cannot see it.

``MIDNIGHT_PROBE_ZONE`` names whose midnight, the one nearest now: ``America/Vancouver`` by
default, ``UTC`` for a read of the host's day. A test body that seeds and reads inline is
inside one hook, and no setting here crosses midnight between the two.

The probe moves an outer travel, so a held module's clock, or a test's own travel, sits above
it and stays put, as it does when the real clock crosses.

**It moves the process clock only.** The Neo4j server's stays real, so the two drift apart by
the distance to that midnight, and a test that compares a server stamp with the process clock
fails for that alone. A failure counts as a crossing only if the test passes with the process
clock shifted back the same distance and no day crossed.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine

_MODE = os.environ.get("MIDNIGHT_PROBE", "import")
_ZONE = ZoneInfo(os.environ.get("MIDNIGHT_PROBE_ZONE", "America/Vancouver"))


def _nearest_midnight() -> datetime:
    now = datetime.now(_ZONE)
    gone = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return gone if now - gone <= timedelta(hours=12) else gone + timedelta(days=1)


_MIDNIGHT = _nearest_midnight()
_BEFORE = (_MIDNIGHT - timedelta(seconds=60)).timestamp()
_AFTER = (_MIDNIGHT + timedelta(seconds=60)).timestamp()

_clock = time_machine.travel(_BEFORE, tick=True).start()


def pytest_report_header() -> str:
    return f"midnight probe: {_MODE} across {_MIDNIGHT.astimezone(UTC):%Y-%m-%d %H:%MZ}"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish() -> None:
    if _MODE == "import":
        _clock.move_to(_AFTER)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup() -> None:
    if _MODE == "call":
        _clock.move_to(_BEFORE)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call() -> None:
    if _MODE == "call":
        _clock.move_to(_AFTER)
