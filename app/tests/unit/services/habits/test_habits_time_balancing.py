"""
Habit time-slot balancing
=========================

``_analyze_time_distribution`` censuses which ``TimeOfDay`` slots a user's habits
occupy; ``_suggest_best_time`` picks the least-loaded slot for a new one. The
answer reaches real data through ``check_habit_capacity`` →
``create_habit_from_path_step``, which writes it as the new habit's
``preferred_time``.

These are pure functions over a habit list, so they are tested directly on an
un-constructed service — the surrounding facade needs a backend and an event bus
that contribute nothing here.
"""

from types import SimpleNamespace

import pytest

from core.models.enums.scheduling_enums import TimeOfDay
from core.services.habits.habits_scheduling_service import (
    _BALANCEABLE_SLOTS,
    HabitsSchedulingService,
)


def _habit(slot: TimeOfDay | None) -> SimpleNamespace:
    return SimpleNamespace(preferred_time=slot)


@pytest.fixture
def service() -> HabitsSchedulingService:
    """The two methods under test read no instance state."""
    return HabitsSchedulingService.__new__(HabitsSchedulingService)


class TestTimeDistribution:
    def test_every_slot_is_a_key_so_an_unused_slot_reads_as_zero(self, service) -> None:
        distribution = service._analyze_time_distribution([])
        assert set(distribution) == set(TimeOfDay)
        assert set(distribution.values()) == {0}

    def test_habits_land_in_their_own_slot(self, service) -> None:
        distribution = service._analyze_time_distribution(
            [_habit(TimeOfDay.EVENING), _habit(TimeOfDay.EVENING), _habit(TimeOfDay.LATE_NIGHT)]
        )
        assert distribution[TimeOfDay.EVENING] == 2
        assert distribution[TimeOfDay.LATE_NIGHT] == 1
        assert distribution[TimeOfDay.MORNING] == 0

    def test_a_habit_with_no_slot_counts_as_anytime(self, service) -> None:
        distribution = service._analyze_time_distribution([_habit(None), _habit(None)])
        assert distribution[TimeOfDay.ANYTIME] == 2
        assert sum(distribution.values()) == 2, "an unslotted habit must be counted once"


class TestSuggestBestTime:
    def test_no_habits_yet_suggests_morning(self, service) -> None:
        """Ties resolve to MORNING rather than to whichever slot the enum declares first.

        Every count being zero is the *most* common state (a new user), and enum
        declaration order would silently answer EARLY_MORNING — a 06:00 practice
        habit nobody asked for.
        """
        distribution = service._analyze_time_distribution([])
        assert service._suggest_best_time(distribution) is TimeOfDay.MORNING

    def test_only_unslotted_habits_still_suggests_morning(self, service) -> None:
        distribution = service._analyze_time_distribution([_habit(None), _habit(None)])
        assert service._suggest_best_time(distribution) is TimeOfDay.MORNING

    @pytest.mark.parametrize("least_loaded", _BALANCEABLE_SLOTS)
    def test_picks_the_least_loaded_balanceable_slot(self, service, least_loaded) -> None:
        habits = [_habit(slot) for slot in _BALANCEABLE_SLOTS if slot is not least_loaded]
        assert (
            service._suggest_best_time(service._analyze_time_distribution(habits)) is least_loaded
        )

    def test_an_always_empty_fringe_slot_never_wins(self, service) -> None:
        """The fringe slots sit at zero for real schedules; if they were balanceable
        the suggestion would be constant no matter how the day is arranged."""
        loaded = service._analyze_time_distribution(
            [_habit(TimeOfDay.MORNING), _habit(TimeOfDay.AFTERNOON), _habit(TimeOfDay.EVENING)]
        )
        assert loaded[TimeOfDay.EARLY_MORNING] == 0
        assert loaded[TimeOfDay.NIGHT] == 0
        assert service._suggest_best_time(loaded) in _BALANCEABLE_SLOTS

    def test_the_suggestion_is_always_a_real_slot(self, service) -> None:
        for habits in ([], [_habit(TimeOfDay.MORNING)], [_habit(None), _habit(TimeOfDay.NIGHT)]):
            got = service._suggest_best_time(service._analyze_time_distribution(habits))
            assert isinstance(got, TimeOfDay)
            assert got is not TimeOfDay.ANYTIME, "ANYTIME means 'no slot', not a place to schedule"
