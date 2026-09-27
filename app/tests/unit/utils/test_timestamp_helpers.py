"""Unit tests for core.utils.timestamp_helpers.

Covers month_grid_bounds — the single source of the month view's full
visible range (Monday-start grid, lead-in/tail cells included) — as_utc,
the one form two instants are compared in, as_host_clock (its inverse for a
naive value), and the zone helpers (now_in, wall_clock_in, today_in, day_of,
local_day_bounds), each of which takes its zone. The as_utc
and zone tests force the process zone: CI runs UTC, where a naive value reads
the same as UTC by accident, and a helper that read the host's zone instead of
the one it is given would pass there.
"""

import os
import time
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core.utils import timestamp_helpers
from core.utils.timestamp_helpers import (
    as_host_clock,
    as_utc,
    day_of,
    local_day_bounds,
    month_grid_bounds,
    now_in,
    now_utc,
    today_in,
    wall_clock_in,
    week_bounds,
)
from tests.helpers.forced_zone import forced_zone

VANCOUVER = ZoneInfo("America/Vancouver")
BANGKOK = ZoneInfo("Asia/Bangkok")

# 02:00Z on 2026-09-28 is 19:00 on the 27th in Vancouver (PDT, UTC-7) and
# 09:00 on the 28th in Bangkok (UTC+7): one moment, two calendar days.
_FROZEN = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)


class _FrozenClock(datetime):
    """``datetime`` whose ``now`` is ``_FROZEN`` — patched into the module under test."""

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return _FROZEN.astimezone().replace(tzinfo=None)
        return _FROZEN.astimezone(tz)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timestamp_helpers, "datetime", _FrozenClock)


class TestMonthGridBounds:
    def test_month_starting_mid_week(self) -> None:
        # August 2026: the 1st is a Saturday, the 31st a Monday.
        grid_start, grid_end = month_grid_bounds(2026, 8)
        assert grid_start == date(2026, 7, 27)  # Monday before Aug 1
        assert grid_end == date(2026, 9, 6)  # Sunday after Aug 31

    def test_month_ending_on_sunday_keeps_last_day(self) -> None:
        # May 2026 ends on a Sunday — no tail cells past the 31st.
        grid_start, grid_end = month_grid_bounds(2026, 5)
        assert grid_start == date(2026, 4, 27)
        assert grid_end == date(2026, 5, 31)

    def test_month_starting_on_monday_keeps_first_day(self) -> None:
        # June 2026 starts on a Monday — no lead-in cells.
        grid_start, grid_end = month_grid_bounds(2026, 6)
        assert grid_start == date(2026, 6, 1)
        assert grid_end == date(2026, 7, 5)

    def test_year_boundary(self) -> None:
        # January 2026: the 1st is a Thursday — lead-in reaches into 2025.
        grid_start, grid_end = month_grid_bounds(2026, 1)
        assert grid_start == date(2025, 12, 29)
        assert grid_end == date(2026, 2, 1)

    @pytest.mark.parametrize("month", range(1, 13))
    def test_bounds_are_week_aligned_and_cover_the_month(self, month: int) -> None:
        grid_start, grid_end = month_grid_bounds(2026, month)
        assert grid_start.weekday() == 0  # Monday
        assert grid_end.weekday() == 6  # Sunday
        assert grid_start <= date(2026, month, 1) <= grid_end
        # Whole weeks only.
        assert ((grid_end - grid_start).days + 1) % 7 == 0
        # The grid is exactly the union of the weeks containing the month.
        assert week_bounds(date(2026, month, 1))[0] == grid_start


class TestAsUtc:
    """An instant as aware UTC: aware values converted, naive ones read in the process zone."""

    def test_a_naive_value_is_read_in_the_process_zone(self) -> None:
        # 2026-09-27 is PDT (UTC-7) in Vancouver and UTC+7 all year in Bangkok.
        wall = datetime(2026, 9, 27, 10, 0)
        with forced_zone("America/Vancouver"):
            assert as_utc(wall) == datetime(2026, 9, 27, 17, 0, tzinfo=UTC)
        with forced_zone("Asia/Bangkok"):
            assert as_utc(wall) == datetime(2026, 9, 27, 3, 0, tzinfo=UTC)
        with forced_zone("UTC"):
            assert as_utc(wall) == datetime(2026, 9, 27, 10, 0, tzinfo=UTC)

    def test_an_aware_value_keeps_its_instant_whatever_the_process_zone(self) -> None:
        bangkok_evening = datetime(2026, 9, 27, 20, 0, tzinfo=timezone(timedelta(hours=7)))
        with forced_zone("America/Vancouver"):
            converted = as_utc(bangkok_evening)
        assert converted == datetime(2026, 9, 27, 13, 0, tzinfo=UTC)
        assert converted.utcoffset() == timedelta(0)

    def test_the_result_is_aware_utc(self) -> None:
        with forced_zone("America/Vancouver"):
            result = as_utc(datetime(2026, 9, 27, 10, 0))
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_naive_and_aware_stamps_of_one_moment_subtract_to_zero(self) -> None:
        """The arithmetic the goal events and insight recency do: no TypeError, no skew."""
        with forced_zone("America/Vancouver"):
            local_wall = datetime.now()
            aware = now_utc()
            assert abs((as_utc(aware) - as_utc(local_wall)).total_seconds()) < 5

    def test_the_forced_zone_is_restored(self) -> None:
        tz_before, names_before = os.environ.get("TZ"), time.tzname
        with forced_zone("Asia/Bangkok"):
            assert os.environ["TZ"] == "Asia/Bangkok"
            assert time.tzname == ("+07", "+07")
        assert os.environ.get("TZ") == tz_before
        assert time.tzname == names_before


class TestNowAndTodayIn:
    """Now and today in a given zone — never the host's zone."""

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_today_is_the_zones_day_whatever_the_host_zone(self, frozen_clock, host: str) -> None:
        with forced_zone(host):
            assert today_in(VANCOUVER) == date(2026, 9, 27)
            assert today_in(BANGKOK) == date(2026, 9, 28)
            assert today_in(UTC) == date(2026, 9, 28)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_now_is_the_zones_wall_clock_at_the_same_instant(self, frozen_clock, host: str) -> None:
        with forced_zone(host):
            vancouver, bangkok = now_in(VANCOUVER), now_in(BANGKOK)
        assert (vancouver.hour, vancouver.utcoffset()) == (19, timedelta(hours=-7))
        assert (bangkok.hour, bangkok.utcoffset()) == (9, timedelta(hours=7))
        assert vancouver == bangkok == _FROZEN

    def test_unfrozen_now_in_is_the_current_instant(self) -> None:
        assert abs((now_in(BANGKOK) - now_utc()).total_seconds()) < 5

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_the_wall_clock_is_the_zones_hands_with_no_zone(self, frozen_clock, host: str) -> None:
        with forced_zone(host):
            vancouver, bangkok = wall_clock_in(VANCOUVER), wall_clock_in(BANGKOK)
        assert vancouver == datetime(2026, 9, 27, 19, 0)
        assert bangkok == datetime(2026, 9, 28, 9, 0)
        assert vancouver.tzinfo is None and bangkok.tzinfo is None


class TestAsHostClock:
    """An instant as the naive reading the host clock stamps — the inverse of as_utc."""

    def test_an_instant_reads_in_the_host_zone(self) -> None:
        with forced_zone("America/Vancouver"):
            assert as_host_clock(_FROZEN) == datetime(2026, 9, 27, 19, 0)
        with forced_zone("UTC"):
            assert as_host_clock(_FROZEN) == datetime(2026, 9, 28, 2, 0)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_it_round_trips_through_as_utc(self, host: str) -> None:
        with forced_zone(host):
            naive = as_host_clock(_FROZEN)
            assert naive.tzinfo is None
            assert as_utc(naive) == _FROZEN

    def test_a_day_widened_on_the_laptop_is_its_midnight(self) -> None:
        # The laptop's case: host and zone agree, so a day's first instant reads
        # as its own midnight — the digits a naive stamp of that day carried.
        start, end = local_day_bounds(date(2026, 9, 27), VANCOUVER)
        with forced_zone("America/Vancouver"):
            assert as_host_clock(start) == datetime(2026, 9, 27, 0, 0)
            assert as_host_clock(end) == datetime(2026, 9, 28, 0, 0)
        # Under a UTC host (the pinned app) the same day starts at 07:00.
        with forced_zone("UTC"):
            assert as_host_clock(start) == datetime(2026, 9, 27, 7, 0)


class TestDayOf:
    """The calendar day an instant falls on in a zone."""

    def test_an_aware_instant_has_one_day_per_zone(self) -> None:
        assert day_of(_FROZEN, VANCOUVER) == date(2026, 9, 27)
        assert day_of(_FROZEN, BANGKOK) == date(2026, 9, 28)
        with forced_zone("Asia/Bangkok"):
            assert day_of(_FROZEN, VANCOUVER) == date(2026, 9, 27)

    def test_a_naive_instant_is_read_through_as_utc(self) -> None:
        # 23:30 naive: under a Bangkok process that is 16:30Z (still the 27th in
        # Bangkok); under a UTC process it is 23:30Z (06:30 on the 28th in Bangkok).
        naive = datetime(2026, 9, 27, 23, 30)
        with forced_zone("Asia/Bangkok"):
            assert day_of(naive, BANGKOK) == date(2026, 9, 27)
        with forced_zone("UTC"):
            assert day_of(naive, BANGKOK) == date(2026, 9, 28)


class TestLocalDayBounds:
    """A calendar day in a zone as the UTC instants it spans: [start, end)."""

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_bounds_are_the_zones_midnights_in_utc(self, host: str) -> None:
        with forced_zone(host):
            vancouver = local_day_bounds(date(2026, 9, 27), VANCOUVER)
            bangkok = local_day_bounds(date(2026, 9, 27), BANGKOK)
        assert vancouver == (
            datetime(2026, 9, 27, 7, 0, tzinfo=UTC),
            datetime(2026, 9, 28, 7, 0, tzinfo=UTC),
        )
        assert bangkok == (
            datetime(2026, 9, 26, 17, 0, tzinfo=UTC),
            datetime(2026, 9, 27, 17, 0, tzinfo=UTC),
        )

    def test_bounds_are_aware_utc(self) -> None:
        start, end = local_day_bounds(date(2026, 9, 27), BANGKOK)
        assert start.utcoffset() == end.utcoffset() == timedelta(0)

    def test_a_daylight_saving_day_spans_23_or_25_hours(self) -> None:
        spring_start, spring_end = local_day_bounds(date(2025, 3, 9), VANCOUVER)
        fall_start, fall_end = local_day_bounds(date(2025, 11, 2), VANCOUVER)
        assert spring_end - spring_start == timedelta(hours=23)
        assert fall_end - fall_start == timedelta(hours=25)

    @pytest.mark.parametrize("zone", [VANCOUVER, BANGKOK])
    def test_the_bounds_hold_exactly_the_instants_of_that_day(self, zone: ZoneInfo) -> None:
        day = date(2026, 9, 27)
        start, end = local_day_bounds(day, zone)
        assert day_of(start, zone) == day
        assert day_of(end - timedelta(microseconds=1), zone) == day
        assert day_of(start - timedelta(microseconds=1), zone) == day - timedelta(days=1)
        assert day_of(end, zone) == day + timedelta(days=1)
