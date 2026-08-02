"""Unit tests for calendar arithmetic in core.utils.timestamp_helpers.

Covers month_grid_bounds — the single source of the month view's full
visible range (Monday-start grid, lead-in/tail cells included).
"""

from datetime import date

import pytest

from core.utils.timestamp_helpers import month_grid_bounds, week_bounds


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
