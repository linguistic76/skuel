"""The hold a test module's day stands on (``tests/helpers/run_clock.py``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import time_machine

from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.run_clock import RUN_INSTANT, RUN_TODAY, hold_run_clock


def test_the_hold_stays_on_the_runs_day_when_the_clock_moves_past_midnight() -> None:
    with time_machine.travel(RUN_INSTANT + timedelta(days=1), tick=False):
        assert today_in(current_zone()) == RUN_TODAY + timedelta(days=1)

        with hold_run_clock():
            assert datetime.now(UTC) == RUN_INSTANT
            assert today_in(current_zone()) == RUN_TODAY

        assert today_in(current_zone()) == RUN_TODAY + timedelta(days=1)


def test_a_tests_own_travel_sits_on_the_hold_and_returns_to_it() -> None:
    with hold_run_clock():
        with time_machine.travel(RUN_INSTANT - timedelta(days=10), tick=False):
            assert today_in(current_zone()) == RUN_TODAY - timedelta(days=10)

        assert datetime.now(UTC) == RUN_INSTANT
