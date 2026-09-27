"""Run a block with the process's local zone forced — the UTC arc's forced-zone rule.

CI runners and the Neo4j testcontainer run UTC, and nothing sets ``TZ``. A test of
how the host zone shapes a result passes with and without the fix unless it moves
the process off UTC first, so it forces one: ``TZ`` set and ``time.tzset()`` called,
both restored when the block exits, whatever it raised.

    with forced_zone("America/Vancouver"):
        assert as_utc(datetime(2026, 9, 27, 10, 0)).hour == 17

See: /docs/roadmap/utc-instants-arc.md § Standing conventions
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest


@contextmanager
def forced_zone(zone: str) -> Iterator[None]:
    """Set the process's local zone to ``zone`` (an IANA name) for the block."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", zone)
        time.tzset()
        try:
            yield
        finally:
            patch.undo()
            time.tzset()
