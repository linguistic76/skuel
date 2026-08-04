"""
Which scheduling strategy a habit gets, and what time that produces
===================================================================

``HabitEventScheduler`` turns habits into calendar events. A habit's declared
``preferred_time`` slot is the user's own statement of when it belongs, so it
outranks the keystone / category / tag heuristics — with one exception:
``ANYTIME`` is the explicit *no preference* member, and committing a generated
event to its representative hour would pin the habit to a time the user
specifically declined to choose.
"""

import pytest

from core.models.enums import Priority, RecurrencePattern, TimeOfDay
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.habit_enums import HabitCategory
from core.models.event.event_dto import EventDTO
from core.models.habit.habit import Habit
from core.services.habit_event_scheduler import (
    EventSchedulingConfig,
    HabitEventScheduler,
    SchedulingStrategy,
)


def _habit(**overrides) -> Habit:
    base = {
        "uid": "habit_x",
        "user_uid": "u",
        "title": "Sit",
        "status": EntityStatus.ACTIVE,
        "priority": Priority.MEDIUM,
        "recurrence_pattern": RecurrencePattern.DAILY,
    }
    return Habit(**{**base, **overrides})


@pytest.fixture
def scheduler() -> HabitEventScheduler:
    """The two methods under test read only ``self.config``."""
    instance = HabitEventScheduler.__new__(HabitEventScheduler)
    instance.config = EventSchedulingConfig()
    return instance


class TestStrategySelection:
    @pytest.mark.parametrize(
        "slot",
        [s for s in TimeOfDay if s is not TimeOfDay.ANYTIME],
    )
    def test_a_declared_slot_selects_fixed_time(self, scheduler, slot) -> None:
        assert (
            scheduler._determine_strategy(_habit(preferred_time=slot), None)
            is SchedulingStrategy.FIXED_TIME
        )

    def test_anytime_is_not_a_declared_slot(self, scheduler) -> None:
        """ANYTIME means 'no preference' — it must not become a fixed 09:00."""
        strategy = scheduler._determine_strategy(_habit(preferred_time=TimeOfDay.ANYTIME), None)
        assert strategy is not SchedulingStrategy.FIXED_TIME

    def test_a_slot_outranks_the_category_heuristic(self, scheduler) -> None:
        """Without this the LEARNING rule would overwrite an evening habit with morning."""
        habit = _habit(preferred_time=TimeOfDay.EVENING, habit_category=HabitCategory.LEARNING)
        assert scheduler._determine_strategy(habit, None) is SchedulingStrategy.FIXED_TIME

    def test_a_slot_outranks_the_tag_heuristic(self, scheduler) -> None:
        habit = _habit(preferred_time=TimeOfDay.EVENING, tags=("morning",))
        assert scheduler._determine_strategy(habit, None) is SchedulingStrategy.FIXED_TIME

    def test_no_slot_falls_through_to_the_heuristics(self, scheduler) -> None:
        habit = _habit(preferred_time=None, habit_category=HabitCategory.LEARNING)
        assert scheduler._determine_strategy(habit, None) is SchedulingStrategy.MORNING


class TestAppliedTime:
    @pytest.mark.parametrize(
        ("slot", "hour"),
        [
            (TimeOfDay.EARLY_MORNING, 6),
            (TimeOfDay.MORNING, 9),
            (TimeOfDay.AFTERNOON, 14),
            (TimeOfDay.EVENING, 19),
            (TimeOfDay.NIGHT, 22),
            (TimeOfDay.LATE_NIGHT, 2),
        ],
    )
    def test_the_event_lands_on_the_slots_representative_hour(self, scheduler, slot, hour) -> None:
        events = scheduler._apply_scheduling_strategy(
            [EventDTO(uid="event_x", user_uid="u", title="Sit")], _habit(preferred_time=slot), None
        )
        assert events[0].start_time is not None
        assert events[0].start_time.hour == hour
        assert events[0].start_time.minute == 0

    def test_an_anytime_habit_is_never_pinned_to_a_clock_time(self, scheduler) -> None:
        events = scheduler._apply_scheduling_strategy(
            [EventDTO(uid="event_x", user_uid="u", title="Sit")],
            _habit(preferred_time=TimeOfDay.ANYTIME),
            None,
        )
        assert events[0].start_time != TimeOfDay.ANYTIME.get_representative_time()
