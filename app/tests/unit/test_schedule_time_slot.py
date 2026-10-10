"""
Unit Tests — the slot schedule-aware recommendations are scored for
====================================================================

``ScheduleIntelligenceMixin._get_current_time_slot`` answers with the user's preferred
slot, else the clock's. ``TimeOfDay.ANYTIME`` is the default preference and means "no
preference", so it falls through to the clock — through ``TimeOfDay.from_hour``, the one
hour↔slot mapping. The scorer then has a verdict for every slot ``TimeOfDay`` has.

The free time the recommendations are ranked against comes from the calendar: the
user's events in the horizon take the minutes they overlap it, an overlap counted once.
"""

from datetime import date, datetime, time, timedelta

import pytest
import time_machine

from core.models.enums.scheduling_enums import TimeOfDay
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Errors, Result
from core.utils.zone_context import current_zone

DAY = date(2026, 10, 8)


class _Calendar:
    """The one calendar read the schedule mixin makes, answering with fixed events."""

    def __init__(self, events: list[CalendarItem] | None = None, fails: bool = False) -> None:
        self.events = events or []
        self.fails = fails
        self.asked: list[tuple[str, date, date]] = []

    async def event_items_in_range(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[list[CalendarItem]]:
        self.asked.append((user_uid, start_date, end_date))
        if self.fails:
            return Result.fail(Errors.database("read", "the calendar is down"))
        return Result.ok(self.events)


class _Schedule(ScheduleIntelligenceMixin):
    """The schedule mixin over a context and a calendar — it reads nothing else."""

    def __init__(self, context: RichUserContext, calendar: _Calendar | None = None) -> None:
        self.context = context
        self.calendar = calendar or _Calendar()  # type: ignore[assignment]


def _event(start_hour: float, minutes: int) -> CalendarItem:
    start = datetime.combine(DAY, time()) + timedelta(hours=start_hour)
    return CalendarItem(
        uid=f"event-{start_hour}",
        source_uid=f"event.test.{start_hour}",
        item_type=CalendarItemType.EVENT,
        title="An event",
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
    )


def _at(hour: int) -> time_machine.travel:
    """Freeze the process clock at ``hour`` o'clock in the current zone."""
    instant = datetime.combine(DAY, time(hour=hour), tzinfo=current_zone())
    return time_machine.travel(instant.timestamp(), tick=False)


def _schedule(preferred: TimeOfDay = TimeOfDay.ANYTIME) -> _Schedule:
    context = RichUserContext(user_uid="user_test")
    context.preferred_time = preferred
    return _Schedule(context)


class TestTheSlot:
    def test_the_default_preference_falls_through_to_the_clock(self) -> None:
        with _at(9):
            assert _schedule()._get_current_time_slot() is TimeOfDay.MORNING

    def test_a_stated_preference_wins_over_the_clock(self) -> None:
        with _at(9):
            assert _schedule(TimeOfDay.EVENING)._get_current_time_slot() is TimeOfDay.EVENING

    @pytest.mark.parametrize(
        ("hour", "slot"),
        [
            (6, TimeOfDay.EARLY_MORNING),
            (14, TimeOfDay.AFTERNOON),
            (22, TimeOfDay.NIGHT),
            (2, TimeOfDay.LATE_NIGHT),
        ],
    )
    def test_the_clock_maps_through_the_one_hour_slot_mapping(
        self, hour: int, slot: TimeOfDay
    ) -> None:
        with _at(hour):
            assert _schedule()._get_current_time_slot() is slot


def _fit(entity_type: str, slot: TimeOfDay) -> float:
    score = _schedule()._calculate_schedule_score(
        entity_type=entity_type,
        priority=0.5,
        energy_required="medium",
        current_energy="medium",
        time_slot=slot,
        respect_energy=True,
    )
    return score["schedule_fit"]


class TestEverySlotHasAVerdict:
    @pytest.mark.parametrize(
        ("entity_type", "slot", "fit"),
        [
            ("task", TimeOfDay.MORNING, 0.9),
            ("task", TimeOfDay.EARLY_MORNING, 0.9),
            ("task", TimeOfDay.AFTERNOON, 0.9),
            ("task", TimeOfDay.EVENING, 0.7),
            ("task", TimeOfDay.LATE_NIGHT, 0.5),
            ("knowledge", TimeOfDay.EARLY_MORNING, 0.95),
            ("knowledge", TimeOfDay.MORNING, 0.95),
            ("knowledge", TimeOfDay.AFTERNOON, 0.7),
            ("knowledge", TimeOfDay.LATE_NIGHT, 0.5),
            ("habit", TimeOfDay.LATE_NIGHT, 0.85),
            ("goal", TimeOfDay.MORNING, 0.75),
            ("goal", TimeOfDay.LATE_NIGHT, 0.5),
        ],
    )
    def test_fit(self, entity_type: str, slot: TimeOfDay, fit: float) -> None:
        assert _fit(entity_type, slot) == fit


class TestTheRecommendationCarriesTheSlot:
    @pytest.mark.asyncio
    async def test_a_task_at_nine_with_no_preference_fits_the_morning(self) -> None:
        schedule = _schedule()
        schedule.context.today_task_uids = ["task.test.today"]

        with _at(9):
            recommendations = await schedule.get_schedule_aware_recommendations()

        assert recommendations.is_ok
        (task,) = [r for r in recommendations.value if r.uid == "task.test.today"]
        assert task.schedule_fit_score == 0.9
        assert task.suggested_time_slot == TimeOfDay.MORNING.value


class TestTheFreeTimeComesFromTheCalendar:
    """The horizon is 9:00-13:00; the daily budget is set high so it never caps."""

    async def _available(self, calendar: _Calendar) -> Result[int]:
        context = RichUserContext(user_uid="user_test")
        context.available_minutes_daily = 1000
        with _at(9):
            return await _Schedule(context, calendar)._calculate_available_minutes(4)

    @pytest.mark.asyncio
    async def test_an_event_takes_its_real_duration(self) -> None:
        calendar = _Calendar([_event(10, 90)])

        available = await self._available(calendar)

        assert available.value == 240 - 90
        assert calendar.asked == [("user_test", DAY, DAY)]

    @pytest.mark.asyncio
    async def test_only_the_part_inside_the_horizon_counts(self) -> None:
        # 8:30-9:30 overlaps 30 minutes; 12:30-14:00 overlaps 30; 15:00 is outside.
        available = await self._available(
            _Calendar([_event(8.5, 60), _event(12.5, 90), _event(15, 60)])
        )

        assert available.value == 240 - 60

    @pytest.mark.asyncio
    async def test_overlapping_events_count_once(self) -> None:
        # 10:00-11:00 and 10:30-11:30 take 10:00-11:30.
        available = await self._available(_Calendar([_event(10, 60), _event(10.5, 60)]))

        assert available.value == 240 - 90

    @pytest.mark.asyncio
    async def test_no_events_leave_the_whole_horizon(self) -> None:
        assert (await self._available(_Calendar())).value == 240

    @pytest.mark.asyncio
    async def test_a_failed_calendar_read_fails_the_answer(self) -> None:
        schedule = _schedule()
        schedule.calendar = _Calendar(fails=True)  # type: ignore[assignment]

        with _at(9):
            recommendations = await schedule.get_schedule_aware_recommendations()

        assert recommendations.is_error
