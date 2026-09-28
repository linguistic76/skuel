"""
The Process Clock Pin — every naive clock read is UTC
=====================================================

The UTC Instants arc's bridge (ADR-089, R1): until every writer stamps an aware
UTC ``datetime``, the process clock itself is pinned to UTC, so a naive
``datetime.now()`` — and every default factory built on it — is the UTC wall
clock, and every naive writer writes UTC into the graph.

- **The pin** is ``pin_process_clock_to_utc()``: ``TZ=UTC`` and ``time.tzset()``.
  Each entry point calls it before it reads a clock or imports what might —
  ``main.py``, every script that opens the graph, ``tests/conftest.py`` — and
  ``./dev`` exports ``TZ=UTC`` for every target it runs. There is no shared
  import chokepoint to do it once: ``core`` is a namespace package.
- **The check** is ``process_clock_is_pinned()``. The one graph driver factory
  (``adapters/persistence/neo4j/graph_driver.py``) refuses to open a driver in a
  process that is not pinned, so a forgotten pin fails loudly at the door rather
  than writing a local wall clock into a UTC corpus.

The pin is removed at the end of the arc, once no writer is naive (R8).

See: /docs/roadmap/utc-instants-arc.md § The bridge
"""

from __future__ import annotations

import os
import time

#: The value of ``TZ`` the pin sets.
PINNED_ZONE = "UTC"


def pin_process_clock_to_utc() -> None:
    """Pin the process's local zone to UTC — the arc's bridge, called by every entry point."""
    os.environ["TZ"] = PINNED_ZONE
    time.tzset()


def process_clock_is_pinned() -> bool:
    """Whether the process's local zone is the pin's: ``TZ=UTC``, applied by ``time.tzset()``.

    Both halves are read: ``TZ`` set without ``tzset()`` has not yet moved the
    C library's clock, and a UTC offset reached some other way is not the pin.
    """
    return (
        os.environ.get("TZ") == PINNED_ZONE
        and time.timezone == 0
        and time.altzone == 0
        and time.daylight == 0
    )
