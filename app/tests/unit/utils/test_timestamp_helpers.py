"""Unit tests for core.utils.timestamp_helpers.

Covers month_grid_bounds — the single source of the month view's full
visible range (Monday-start grid, lead-in/tail cells included) — and as_utc,
the one form two instants are compared in. The as_utc tests force the
process zone: CI runs UTC, where a naive value reads the same as UTC by
accident.
"""

import os
import time
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from core.utils.timestamp_helpers import as_utc, month_grid_bounds, now_utc, week_bounds
from tests.helpers.forced_zone import forced_zone


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
