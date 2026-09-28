"""The process clock pin, and the driver factory's refusal of an unpinned process.

The test process is pinned by ``tests/conftest.py`` before anything else runs, as
every entry point pins itself. A test of the unpinned case forces a zone for its
own block (``forced_zone``), which puts the pin back when it exits.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import pytest

from adapters.persistence.neo4j.graph_driver import ProcessClockNotPinnedError, open_async_driver
from core.utils.process_clock import (
    PINNED_ZONE,
    pin_process_clock_to_utc,
    process_clock_is_pinned,
)
from tests.helpers.forced_zone import forced_zone


def test_the_test_process_is_pinned_before_any_test_runs() -> None:
    assert os.environ["TZ"] == PINNED_ZONE
    assert process_clock_is_pinned()
    assert datetime.now().astimezone().utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_a_forced_zone_unpins_and_its_exit_restores_the_pin() -> None:
    with forced_zone("America/Vancouver"):
        assert not process_clock_is_pinned()
    assert process_clock_is_pinned()


def test_the_pin_moves_a_process_started_elsewhere_onto_utc() -> None:
    with forced_zone("Asia/Bangkok"):
        assert datetime.now().astimezone().utcoffset().total_seconds() == 7 * 3600  # type: ignore[union-attr]
        pin_process_clock_to_utc()
        assert process_clock_is_pinned()
        assert datetime.now().astimezone().utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_tz_set_without_tzset_is_not_the_pin() -> None:
    """``TZ=UTC`` that the C library has not applied leaves the old clock running."""
    with forced_zone("America/Vancouver"), pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", PINNED_ZONE)
        assert time.timezone != 0
        assert not process_clock_is_pinned()


def test_the_factory_refuses_an_unpinned_process() -> None:
    with forced_zone("America/Vancouver"), pytest.raises(ProcessClockNotPinnedError):
        open_async_driver("bolt://localhost:7687", auth=("neo4j", "unused"))


async def test_the_factory_builds_a_driver_in_a_pinned_process() -> None:
    driver = open_async_driver("bolt://localhost:7687", auth=("neo4j", "unused"))
    await driver.close()
