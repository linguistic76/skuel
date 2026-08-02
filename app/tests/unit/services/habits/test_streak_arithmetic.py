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
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.models.enums import Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.enums.entity_enums import EntityType
from core.models.habit.habit import Habit
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.utils.result_simplified import Errors, Result

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
        # Raw-formula behavior: a completion dated BEFORE last_completed
        # produces a negative days_since and falls into the reset branch.
        # Backfilled completions never reach this formula in the live paths —
        # _streak_and_last_completed routes them to the history recompute
        # (TestBackfilledCompletion below).
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 10, 8, 0, 0))
        new_streak = streak_service._calculate_new_streak(habit, datetime(2026, 7, 9, 8, 0, 0))
        assert new_streak == 1


class TestBackfilledCompletion:
    """_streak_and_last_completed: out-of-order completions are backfill-safe.

    A completion dated before last_completed (the calendar's per-day Mark
    Complete on an earlier pending day) must never regress last_completed nor
    break the streak — the streak is recomputed from stored history, so a
    backfill can bridge two runs into one.
    """

    @pytest.mark.asyncio
    async def test_backfill_bridges_gap_and_keeps_last_completed(
        self, streak_service, sample_habit
    ):
        last = datetime(2026, 7, 10, 8, 0, 0)
        habit = replace(sample_habit, last_completed=last, current_streak=1)
        # Stored history AFTER the backfill write: Jul 8, Jul 9 (backfilled), Jul 10.
        history = [
            SimpleNamespace(completed_at=datetime(2026, 7, 8, 8, 0)),
            SimpleNamespace(completed_at=datetime(2026, 7, 9, 8, 0)),
            SimpleNamespace(completed_at="2026-07-10T08:00:00"),  # string-writer split
        ]
        streak_service.get_completions_for_habit = AsyncMock(return_value=Result.ok(history))

        result = await streak_service._streak_and_last_completed(
            habit, habit.uid, datetime(2026, 7, 9, 8, 0, 0)
        )

        assert result.is_ok
        new_streak, last_completed, best_candidate = result.value
        assert new_streak == 3  # the backfill bridged Jul 8 and Jul 10 into one run
        assert last_completed == last  # never regressed
        assert best_candidate == 3
        # Recompute window reaches the current tail, over stored history.
        args = streak_service.get_completions_for_habit.await_args
        assert args.kwargs["end_date"] == last.date()

    @pytest.mark.asyncio
    async def test_in_order_completion_uses_delta_formula(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 9, 8, 0, 0))
        streak_service.get_completions_for_habit = AsyncMock()  # must not be consulted

        result = await streak_service._streak_and_last_completed(
            habit, habit.uid, datetime(2026, 7, 10, 8, 0, 0)
        )

        assert result.is_ok
        assert result.value == (6, datetime(2026, 7, 10, 8, 0, 0), 6)
        streak_service.get_completions_for_habit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backfill_never_lowers_current_streak(self, streak_service, sample_habit):
        """The recompute is bounded to a 365-day window (and stored history can
        predate completion nodes) — a backfill must preserve a longer live
        streak, never truncate it to what the window can see."""
        last = datetime(2026, 7, 10, 8, 0, 0)
        habit = replace(sample_habit, last_completed=last, current_streak=400)
        # Window-truncated history: only the anchor day is visible.
        streak_service.get_completions_for_habit = AsyncMock(
            return_value=Result.ok([SimpleNamespace(completed_at=last)])
        )

        result = await streak_service._streak_and_last_completed(
            habit, habit.uid, datetime(2026, 7, 9, 8, 0, 0)
        )

        assert result.is_ok
        assert result.value == (400, last, 400)

    @pytest.mark.asyncio
    async def test_backfill_into_historical_run_updates_best_candidate(
        self, streak_service, sample_habit
    ):
        """A backfill can bridge two OLD runs that never reach the current
        tail: the current streak stays put, but best_candidate must carry the
        bridged historical run so best_streak sees it."""
        last = datetime(2026, 1, 20, 8, 0, 0)
        habit = replace(sample_habit, last_completed=last, current_streak=1, best_streak=10)
        # History AFTER backfilling Jan 7: Jan 1-6 + Jan 7 + Jan 8-13, and the
        # lone current-run day Jan 20.
        history = [
            SimpleNamespace(completed_at=datetime(2026, 1, d, 8, 0)) for d in range(1, 14)
        ] + [SimpleNamespace(completed_at=last)]
        streak_service.get_completions_for_habit = AsyncMock(return_value=Result.ok(history))

        result = await streak_service._streak_and_last_completed(
            habit, habit.uid, datetime(2026, 1, 7, 8, 0, 0)
        )

        assert result.is_ok
        new_streak, last_completed, best_candidate = result.value
        assert new_streak == 1  # the current run is untouched
        assert last_completed == last
        assert best_candidate == 13  # Jan 1-13, bridged by the backfill

    @pytest.mark.asyncio
    async def test_backfill_history_error_propagates(self, streak_service, sample_habit):
        habit = replace(sample_habit, last_completed=datetime(2026, 7, 10, 8, 0, 0))
        streak_service.get_completions_for_habit = AsyncMock(
            return_value=Result.fail(Errors.database("habits.completions", "boom"))
        )
        result = await streak_service._streak_and_last_completed(
            habit, habit.uid, datetime(2026, 7, 9, 8, 0, 0)
        )
        assert result.is_error


class TestMilestonesCrossedByJump:
    """_check_streak_milestones publishes every threshold a jump crosses.

    In-order completions step +1 (exact crossings), but a bridging backfill can
    jump several days at once — the old exact-equality match silently skipped
    milestones inside the jump.
    """

    @pytest.mark.asyncio
    async def test_jump_publishes_each_crossed_milestone(self, streak_service, sample_habit):
        streak_service.event_bus = AsyncMock()
        habit = replace(sample_habit, current_streak=3)

        await streak_service._check_streak_milestones(habit, 10, "user_mike")

        published = [
            call.args[0] for call in streak_service.event_bus.publish_async.await_args_list
        ]
        assert [e.streak_length for e in published] == [7]
        assert published[0].milestone_name == "one_week"

    @pytest.mark.asyncio
    async def test_jump_crossing_two_thresholds_publishes_both(self, streak_service, sample_habit):
        streak_service.event_bus = AsyncMock()
        habit = replace(sample_habit, current_streak=5)

        await streak_service._check_streak_milestones(habit, 31, "user_mike")

        published = [
            call.args[0] for call in streak_service.event_bus.publish_async.await_args_list
        ]
        assert sorted(e.streak_length for e in published) == [7, 30]

    @pytest.mark.asyncio
    async def test_exact_single_step_crossing_still_publishes_once(
        self, streak_service, sample_habit
    ):
        streak_service.event_bus = AsyncMock()
        habit = replace(sample_habit, current_streak=6)

        await streak_service._check_streak_milestones(habit, 7, "user_mike")

        assert streak_service.event_bus.publish_async.await_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
