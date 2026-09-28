"""Unit tests for core.utils.timestamp_helpers.

Covers month_grid_bounds — the single source of the month view's full
visible range (Monday-start grid, lead-in/tail cells included) — as_utc,
the one form two instants are compared in, the readers built on it (instant_of,
instant_key, span_days), as_stored_clock (its inverse for a naive value), and
the zone helpers (now_in, wall_clock_in, today_in, day_of,
hour_of, local_day_bounds, stored_day_bounds, from_wall_clock, to_wall_clock), each of which
takes its zone, and the type rule (is_instant_field). The as_utc
and zone tests force the process zone: CI runs UTC, where a naive value reads
the same as UTC by accident, and a helper that read the host's zone instead of
the one it is given would pass there.
"""

import os
import time
from datetime import UTC, date, datetime, timedelta, timezone
from functools import partial
from zoneinfo import ZoneInfo

import pytest
from neo4j.time import Date as Neo4jDate
from neo4j.time import DateTime as Neo4jDateTime

from core.utils import timestamp_helpers
from core.utils.timestamp_helpers import (
    EARLIEST_INSTANT,
    LATEST_INSTANT,
    age_of,
    as_stored_clock,
    as_utc,
    day_of,
    from_wall_clock,
    hour_of,
    instant_key,
    instant_of,
    is_instant_field,
    local_day_bounds,
    month_grid_bounds,
    now_in,
    now_utc,
    shown_in,
    span_days,
    stored_day_bounds,
    to_wall_clock,
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


@pytest.fixture
def stored_clock_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """The host-zone reading the helpers keep: an offset-less stored stamp in the process zone."""
    monkeypatch.setattr(timestamp_helpers, "STORED_INSTANT_CLOCK", None)


def test_the_stored_clock_is_utc() -> None:
    assert timestamp_helpers.STORED_INSTANT_CLOCK is UTC


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

    def test_a_naive_value_is_read_in_the_process_zone(self, stored_clock_host) -> None:
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
        """The arithmetic the goal events and insight recency do: no TypeError, no skew.

        The process is pinned to UTC, so a naive ``datetime.now()`` is the UTC wall
        clock — the digits the stored clock reads.
        """
        naive_wall = datetime.now()
        aware = now_utc()
        assert abs((as_utc(aware) - as_utc(naive_wall)).total_seconds()) < 5

    def test_on_the_host_clock_a_local_wall_and_an_aware_stamp_subtract_to_zero(
        self, stored_clock_host
    ) -> None:
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


class TestAsStoredClock:
    """An instant as the naive reading of the stored clock — the inverse of as_utc."""

    def test_an_instant_reads_in_the_host_zone(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            assert as_stored_clock(_FROZEN) == datetime(2026, 9, 27, 19, 0)
        with forced_zone("UTC"):
            assert as_stored_clock(_FROZEN) == datetime(2026, 9, 28, 2, 0)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_it_round_trips_through_as_utc(self, host: str) -> None:
        with forced_zone(host):
            naive = as_stored_clock(_FROZEN)
            assert naive.tzinfo is None
            assert as_utc(naive) == _FROZEN

    def test_a_day_widened_on_the_laptop_is_its_midnight(self, stored_clock_host) -> None:
        # The laptop's case: host and zone agree, so a day's first instant reads
        # as its own midnight — the digits a naive stamp of that day carried.
        start, end = local_day_bounds(date(2026, 9, 27), VANCOUVER)
        with forced_zone("America/Vancouver"):
            assert as_stored_clock(start) == datetime(2026, 9, 27, 0, 0)
            assert as_stored_clock(end) == datetime(2026, 9, 28, 0, 0)
        # Under a UTC host (the pinned app) the same day starts at 07:00.
        with forced_zone("UTC"):
            assert as_stored_clock(start) == datetime(2026, 9, 27, 7, 0)


class TestDayOf:
    """The calendar day an instant falls on in a zone."""

    def test_an_aware_instant_has_one_day_per_zone(self) -> None:
        assert day_of(_FROZEN, VANCOUVER) == date(2026, 9, 27)
        assert day_of(_FROZEN, BANGKOK) == date(2026, 9, 28)
        with forced_zone("Asia/Bangkok"):
            assert day_of(_FROZEN, VANCOUVER) == date(2026, 9, 27)

    def test_a_naive_instant_is_read_through_as_utc(self, stored_clock_host) -> None:
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


class TestTheStoredClockIsUtc:
    """On the UTC stored clock a naive stored stamp is UTC, whatever zone the process runs in."""

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_as_utc_reads_a_naive_value_as_utc(self, host: str) -> None:
        with forced_zone(host):
            assert as_utc(datetime(2026, 9, 27, 10, 0)) == datetime(2026, 9, 27, 10, 0, tzinfo=UTC)

    def test_an_aware_value_is_untouched_by_the_stored_clock(self) -> None:
        bangkok_evening = datetime(2026, 9, 27, 20, 0, tzinfo=timezone(timedelta(hours=7)))
        with forced_zone("America/Vancouver"):
            assert as_utc(bangkok_evening) == datetime(2026, 9, 27, 13, 0, tzinfo=UTC)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_as_stored_clock_is_the_utc_digits(self, host: str) -> None:
        with forced_zone(host):
            naive = as_stored_clock(_FROZEN)
            assert naive == datetime(2026, 9, 28, 2, 0)
            assert as_utc(naive) == _FROZEN

    def test_a_day_widened_is_its_first_instant_in_utc_digits(self) -> None:
        start, _ = local_day_bounds(date(2026, 9, 27), VANCOUVER)
        with forced_zone("America/Vancouver"):
            assert as_stored_clock(start) == datetime(2026, 9, 27, 7, 0)

    @pytest.mark.parametrize("host", ["America/Vancouver", "Asia/Bangkok"])
    def test_day_of_reads_a_naive_value_as_utc(self, host: str) -> None:
        # 23:30 stored is 23:30Z: 16:30 on the 27th in Vancouver, 06:30 on the 28th in Bangkok.
        naive = datetime(2026, 9, 27, 23, 30)
        with forced_zone(host):
            assert day_of(naive, VANCOUVER) == date(2026, 9, 27)
            assert day_of(naive, BANGKOK) == date(2026, 9, 28)


class TestShownIn:
    """How a stored instant is shown in a zone — a naive wall clock."""

    def test_on_the_laptop_a_naive_stamp_shows_its_digits(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            assert shown_in(datetime(2026, 9, 27, 23, 30), VANCOUVER) == datetime(
                2026, 9, 27, 23, 30
            )

    def test_a_naive_stamp_is_read_in_the_host_zone_and_shown_in_the_zone(self) -> None:
        # Under a UTC host a naive 23:30 is 23:30Z: 06:30 on the 28th in Bangkok.
        with forced_zone("UTC"):
            assert shown_in(datetime(2026, 9, 27, 23, 30), BANGKOK) == datetime(2026, 9, 28, 6, 30)

    @pytest.mark.parametrize("zone", [VANCOUVER, BANGKOK, UTC])
    def test_an_aware_stamp_shows_as_stored_on_the_host_clock(
        self, stored_clock_host, zone
    ) -> None:
        stored = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)
        with forced_zone("America/Vancouver"):
            shown = shown_in(stored, zone)
        assert shown == datetime(2026, 9, 28, 2, 0)
        assert shown.tzinfo is None

    def test_an_offset_string_shows_its_own_digits_on_the_host_clock(
        self, stored_clock_host
    ) -> None:
        stored = datetime.fromisoformat("2026-09-27T20:00:00+07:00")
        assert shown_in(stored, VANCOUVER) == datetime(2026, 9, 27, 20, 0)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_on_the_utc_clock_a_naive_stamp_is_utc_shown_in_the_zone(self, host: str) -> None:
        with forced_zone(host):
            naive = datetime(2026, 9, 28, 2, 0)
            assert shown_in(naive, VANCOUVER) == datetime(2026, 9, 27, 19, 0)
            assert shown_in(naive, BANGKOK) == datetime(2026, 9, 28, 9, 0)

    def test_on_the_utc_clock_an_aware_stamp_is_shown_in_the_zone(self) -> None:
        shown = shown_in(_FROZEN, BANGKOK)
        assert shown == datetime(2026, 9, 28, 9, 0)
        assert shown.tzinfo is None

    def test_on_the_utc_clock_naive_and_aware_stamps_of_one_moment_show_alike(self) -> None:
        naive, native = datetime(2026, 9, 28, 2, 0), _FROZEN
        assert shown_in(naive, VANCOUVER) == shown_in(native, VANCOUVER)


class TestAgeOf:
    """How long ago a stored instant was."""

    def test_a_naive_stamps_age_is_not_told_on_the_host_clock(
        self, stored_clock_host, frozen_clock
    ) -> None:
        with forced_zone("America/Vancouver"):
            assert age_of(datetime(2026, 9, 27, 18, 0)) is None

    def test_an_aware_stamps_age_is_told(self, frozen_clock) -> None:
        assert age_of(_FROZEN - timedelta(hours=3)) == timedelta(hours=3)
        # An L-nat share — the host's 19:00 wall clock stored as 19:00Z — reads
        # seven hours old until the migration moves its digits.
        assert age_of(datetime(2026, 9, 27, 19, 0, tzinfo=UTC)) == timedelta(hours=7)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_on_the_utc_clock_a_naive_stamp_is_aged_as_utc(self, frozen_clock, host: str) -> None:
        with forced_zone(host):
            assert age_of(datetime(2026, 9, 28, 1, 0)) == timedelta(hours=1)


class TestHourOf:
    """The hour an instant falls in on a zone's clock."""

    def test_an_aware_instant_has_one_hour_per_zone(self) -> None:
        assert hour_of(_FROZEN, VANCOUVER) == 19
        assert hour_of(_FROZEN, BANGKOK) == 9

    def test_a_naive_instant_is_read_through_as_utc(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            assert hour_of(datetime(2026, 9, 27, 19, 0), VANCOUVER) == 19
            assert hour_of(datetime(2026, 9, 27, 19, 0), BANGKOK) == 9

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_on_the_utc_clock_a_naive_stamp_is_utc(self, host: str) -> None:
        with forced_zone(host):
            assert hour_of(datetime(2026, 9, 28, 2, 0), VANCOUVER) == 19


class TestStoredDayBounds:
    """A span of local days as the half-open instants a stored stamp is compared with."""

    def test_on_the_laptop_a_day_is_its_midnights(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            start, end = stored_day_bounds(date(2026, 9, 27), date(2026, 9, 27), VANCOUVER)
        assert (start, end) == (datetime(2026, 9, 27), datetime(2026, 9, 28))

    def test_a_bangkok_day_on_the_laptops_clock(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            start, end = stored_day_bounds(date(2026, 9, 27), date(2026, 9, 28), BANGKOK)
        # Bangkok's midnights are 10:00 the previous day on a Vancouver clock.
        assert (start, end) == (datetime(2026, 9, 26, 10, 0), datetime(2026, 9, 28, 10, 0))

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver", "Asia/Bangkok"])
    def test_on_the_utc_clock_the_bounds_are_utc_digits(self, host: str) -> None:
        with forced_zone(host):
            start, end = stored_day_bounds(date(2026, 9, 27), date(2026, 9, 27), VANCOUVER)
        assert (start, end) == (datetime(2026, 9, 27, 7, 0), datetime(2026, 9, 28, 7, 0))

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_a_stamp_is_inside_exactly_on_its_zones_day(self, host: str) -> None:
        """20:00 on the 27th in Vancouver is 03:00Z on the 28th: inside the 27th's
        bounds whatever the host, and outside the 28th's."""
        moment = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
        with forced_zone(host):
            stamp = as_stored_clock(moment)
            first = stored_day_bounds(date(2026, 9, 27), date(2026, 9, 27), VANCOUVER)
            second = stored_day_bounds(date(2026, 9, 28), date(2026, 9, 28), VANCOUVER)
        assert first[0] <= stamp < first[1]
        assert not second[0] <= stamp < second[1]


class TestFromWallClock:
    """A client's offset-less datetime is a wall clock in the user's zone."""

    def test_on_the_laptop_a_default_users_wall_clock_is_unchanged(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            assert from_wall_clock(datetime(2026, 9, 27, 17, 0), VANCOUVER) == datetime(
                2026, 9, 27, 17, 0
            )

    def test_a_bangkok_wall_clock_on_the_laptops_clock(self, stored_clock_host) -> None:
        with forced_zone("America/Vancouver"):
            assert from_wall_clock(datetime(2026, 9, 27, 17, 0), BANGKOK) == datetime(
                2026, 9, 27, 3, 0
            )

    def test_an_aware_value_keeps_its_instant(self) -> None:
        aware = datetime(2026, 9, 27, 17, 0, tzinfo=BANGKOK)
        assert from_wall_clock(aware, VANCOUVER) is aware

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_on_the_utc_clock_the_stored_form_is_utc(self, host: str) -> None:
        with forced_zone(host):
            assert from_wall_clock(datetime(2026, 9, 27, 17, 0), BANGKOK) == datetime(
                2026, 9, 27, 10, 0
            )

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    def test_it_is_shown_in_the_inverse(self, host: str) -> None:
        wall = datetime(2026, 9, 27, 17, 0)
        with forced_zone(host):
            assert shown_in(from_wall_clock(wall, BANGKOK), BANGKOK) == wall


class TestIsInstantField:
    """The type rule: a ``datetime`` field holds an instant, a ``date`` field a day."""

    def test_the_rule_reads_the_models_field_types(self) -> None:
        from core.models.choice.choice import Choice
        from core.models.habit.habit import Habit
        from core.models.task.task import Task

        assert is_instant_field(Choice, "decision_deadline")  # datetime | None
        assert is_instant_field(Habit, "created_at")  # datetime
        assert not is_instant_field(Task, "due_date")  # date | None
        assert not is_instant_field(Task, "title")
        assert not is_instant_field(Task, "no_such_field")
        assert not is_instant_field(dict, "created_at")  # not a dataclass


class TestToWallClock:
    """A stored instant as the wall clock that names it — the inverse of from_wall_clock."""

    def test_an_aware_instant_is_the_instant_it_names_not_its_digits(
        self, stored_clock_host
    ) -> None:
        # Unlike shown_in on the host clock, which holds an aware value's digits.
        assert to_wall_clock(_FROZEN, BANGKOK) == datetime(2026, 9, 28, 9, 0)
        assert shown_in(_FROZEN, BANGKOK) == datetime(2026, 9, 28, 2, 0)

    @pytest.mark.parametrize("host", ["UTC", "America/Vancouver"])
    @pytest.mark.parametrize("zone", [VANCOUVER, BANGKOK])
    def test_an_unchanged_round_trip_keeps_the_instant(self, host: str, zone: ZoneInfo) -> None:
        with forced_zone(host):
            for stamp in (datetime(2026, 9, 27, 17, 0), _FROZEN):
                back = from_wall_clock(to_wall_clock(stamp, zone), zone)
                assert as_utc(back) == as_utc(stamp)

    @pytest.mark.parametrize("zone", [VANCOUVER, BANGKOK])
    def test_on_the_utc_clock_the_round_trip_keeps_the_instant(self, zone: ZoneInfo) -> None:
        with forced_zone("America/Vancouver"):
            for stamp in (datetime(2026, 9, 27, 17, 0), _FROZEN):
                back = from_wall_clock(to_wall_clock(stamp, zone), zone)
                assert as_utc(back) == as_utc(stamp)


class TestInstantOf:
    """A stored stamp in any shape, read as the instant it names — aware UTC."""

    @pytest.mark.parametrize(
        "stamp",
        [
            "2026-09-28T02:00:00",  # offset-less, UTC digits (a naive writer's string)
            "2026-09-28T02:00:00Z",
            "2026-09-28T09:00:00+07:00",
            datetime(2026, 9, 28, 2, 0),
            datetime(2026, 9, 28, 9, 0, tzinfo=BANGKOK),
            Neo4jDateTime(2026, 9, 28, 2, 0, 0, tzinfo=UTC),
        ],
    )
    def test_every_shape_of_one_moment_is_that_moment(self, stamp: object) -> None:
        with forced_zone("America/Vancouver"):  # the process zone plays no part
            moment = instant_of(stamp, VANCOUVER)
        assert moment == _FROZEN
        assert moment is not None and moment.utcoffset() == timedelta(0)

    @pytest.mark.parametrize("day", [date(2026, 9, 27), "2026-09-27", Neo4jDate(2026, 9, 27)])
    def test_a_bare_day_is_its_first_instant_in_the_zone(self, day: object) -> None:
        assert instant_of(day, VANCOUVER) == datetime(2026, 9, 27, 7, 0, tzinfo=UTC)
        assert instant_of(day, BANGKOK) == datetime(2026, 9, 26, 17, 0, tzinfo=UTC)

    @pytest.mark.parametrize("stamp", [None, "", "not-a-date", "2026-13-45", 42])
    def test_an_absent_or_unreadable_stamp_is_none(self, stamp: object) -> None:
        assert instant_of(stamp, VANCOUVER) is None


class TestInstantKey:
    """A sort key that puts naive, aware and absent instants in one order."""

    _EARLY_NAIVE = datetime(2026, 9, 27, 23, 0)  # UTC digits
    _LATE_AWARE = datetime(2026, 9, 28, 9, 0, tzinfo=BANGKOK)  # 02:00Z

    def test_the_mix_cannot_be_sorted_raw(self) -> None:
        with pytest.raises(TypeError):
            sorted([self._LATE_AWARE, self._EARLY_NAIVE])

    def test_naive_aware_and_absent_sort_together(self) -> None:
        stamps = [self._LATE_AWARE, None, self._EARLY_NAIVE]
        assert sorted(stamps, key=instant_key) == [None, self._EARLY_NAIVE, self._LATE_AWARE]

    def test_an_absent_instant_sorts_last_against_the_latest(self) -> None:
        stamps = [None, self._LATE_AWARE, self._EARLY_NAIVE]
        keyed = sorted(stamps, key=partial(instant_key, missing=LATEST_INSTANT))
        assert keyed == [self._EARLY_NAIVE, self._LATE_AWARE, None]

    def test_the_sentinels_are_aware(self) -> None:
        assert EARLIEST_INSTANT.utcoffset() == LATEST_INSTANT.utcoffset() == timedelta(0)
        assert instant_key(None) == EARLIEST_INSTANT


class TestSpanDays:
    def test_whole_days_between_the_earliest_and_the_latest_in_any_order(self) -> None:
        stamps = [
            datetime(2026, 9, 20, 2, 0, tzinfo=UTC),
            datetime(2026, 9, 10, 1, 0),  # naive, UTC digits: the earliest
            datetime(2026, 9, 15, 12, 0, tzinfo=BANGKOK),
        ]
        assert span_days(stamps) == 10
