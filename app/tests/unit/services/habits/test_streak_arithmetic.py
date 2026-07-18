"""
Tests for HabitsCompletionService._calculate_new_streak
========================================================

Direct, deterministic unit tests for the streak arithmetic in
core/services/habits/habits_completion_service.py (_calculate_new_streak).

Testing-gap roadmap item 4: the streak math had no direct tests. The
consecutive-day and gap paths have indirect coverage through the mocked
record_completion flow in tests/unit/test_habits_completion_service.py
(test_streak_calculation_consecutive_day ~line 197, test_streak_broken_after_gap
~line 223), but all four branches are covered here directly because the method
is synchronous and pure — it reads only habit.last_completed and
habit.current_streak, never touching backends or the wall clock.

Mock-free: the service is constructed with inert sentinel objects for the
required backends (the constructor only checks truthiness and stores them;
_calculate_new_streak never uses them).
"""

from dataclasses import replace
from datetime import datetime

import pytest

from core.models.enums import Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.enums.entity_enums import EntityType
from core.models.habit.habit import Habit
from core.services.habits.habits_completion_service import HabitsCompletionService

FIXED_NOW = datetime(2026, 7, 10, 8, 0, 0)


@pytest.fixture
def streak_service() -> HabitsCompletionService:
    """Service with sentinel backends — _calculate_new_streak is pure computation."""
    return HabitsCompletionService(habits_backend=object(), completions_backend=object())


@pytest.fixture
def sample_habit() -> Habit:
    """Minimal habit (construction copied from tests/unit/test_habits_completion_service.py)."""
    return Habit(
        uid="habit.test.1",
        user_uid="user_mike",
        title="Morning Exercise",
        entity_type=EntityType.HABIT,
        description="30 minutes of exercise",
        recurrence_pattern=RecurrencePattern.DAILY,
        target_days_per_week=7,
        duration_minutes=30,
        current_streak=5,
        best_streak=10,
        total_completions=15,
        total_attempts=20,
        success_rate=0.75,
        status=HabitStatus.ACTIVE,
        priority=Priority.HIGH,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


class TestFirstCompletion:
    """Branch 1: no last_completed -> streak starts at 1."""

    def test_no_last_completed_starts_streak_at_one(self, streak_service, sample_habit):
        # current_streak is 5 on the fixture, but with no last_completed the
        # method treats this as a first completion and returns 1.
        assert sample_habit.last_completed is None
        new_streak = streak_service._calculate_new_streak(
            sample_habit, datetime(2026, 7, 10, 9, 0, 0)
        )
        assert new_streak == 1


class TestSameDayCompletion:
    """Branch 2: same calendar day -> streak unchanged."""

    def test_same_day_keeps_current_streak(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 10, 7, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 10, 22, 0, 0))
        assert new_streak == 5


class TestConsecutiveDayCompletion:
    """Branch 3: exactly one calendar day later -> streak + 1."""

    def test_next_day_increments_streak(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 9, 8, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 10, 8, 0, 0))
        assert new_streak == 6

    def test_calendar_day_arithmetic_not_24_hour_window(self, streak_service, sample_habit):
        # 23:59 -> 00:01 next day is only 2 minutes apart but crosses a date
        # boundary, so it counts as a consecutive day and increments.
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 9, 23, 59, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 10, 0, 1, 0))
        assert new_streak == 6


class TestBrokenStreak:
    """Branch 4: gap greater than one day -> streak resets to 1."""

    def test_two_day_gap_resets_streak(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 8, 8, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 10, 8, 0, 0))
        assert new_streak == 1

    def test_long_gap_resets_streak(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 6, 10, 8, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 10, 8, 0, 0))
        assert new_streak == 1

    def test_backdated_completion_resets_streak(self, streak_service, sample_habit):
        # Actual behavior: a completion dated BEFORE last_completed produces a
        # negative days_since and falls into the reset branch (returns 1).
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 10, 8, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 9, 8, 0, 0))
        assert new_streak == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
