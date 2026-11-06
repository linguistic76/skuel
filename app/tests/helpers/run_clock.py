"""The day a test run is on, read once and held.

A test that seeds "today" and a service that asks the clock when it is called agree only
while the clock stays on one day. A run takes minutes, so a module that fixed ``TODAY`` at
import, or seeded in a module fixture, fails the moment midnight falls between that and
the read, whatever the change under test. In the app default zone that is 07:00Z.

``RUN_INSTANT`` is read once, when this module is first imported, and ``RUN_TODAY`` is its
day in the zone a test starts in. A module takes its day from these and opts in to the
hold: ``pytestmark = pytest.mark.usefixtures("held_run_clock")``, the fixture in
``tests/conftest.py``. The process clock then stands on ``RUN_INSTANT`` from before the
module's first fixture to after its last, and a test's own ``time_machine.travel`` still
sits on top of it.

**The instant, not noon.** Freezing on the moment the run began keeps its hour, so a run
between 00:00Z and 07:00Z still has a UTC day ahead of the Vancouver day, which is what
exposes a read of the host's day. A fixed noon would hide that.

The hold moves the Python process only. A Cypher ``datetime()`` still reads the server's
clock, and a held module has to pass the day it means as a parameter, as production does.

``tests/unit/test_import_time_clock_reads.py`` refuses any other clock read at import.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final

import time_machine

from core.utils.timestamp_helpers import day_of
from core.utils.zone_context import current_zone

RUN_INSTANT: Final = datetime.now(UTC)
RUN_TODAY: Final = day_of(RUN_INSTANT, current_zone())


@contextmanager
def hold_run_clock() -> Iterator[None]:
    """Stand the process clock on ``RUN_INSTANT`` for the block."""
    with time_machine.travel(RUN_INSTANT, tick=False):
        yield
