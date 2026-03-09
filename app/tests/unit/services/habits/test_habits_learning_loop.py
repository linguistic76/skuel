"""
Unit tests for Habits adaptive learning loop (ADR-048).

Tests timing/scheduling learning and persisted difficulty:
- Hour histogram tracking and mode calculation
- On-time rate EMA
- Streak broken persists recovery difficulty
- Missed persists difficulty level
- Performance analytics includes learned insights
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from core.constants import LearningLoop
from core.events.habit_events import HabitCompleted, HabitMissed, HabitStreakBroken
from core.models.habit.habit import Habit
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.utils.result_simplified import Result


def _make_habit(uid="habit_test_abc", title="Test Habit", **kwargs):
    """Create a mock Habit with common defaults."""
    habit = MagicMock(spec=Habit)
    habit.uid = uid
    habit.title = title
    habit.is_active = True
    habit.success_rate = 0.8
    habit.current_streak = 5
    habit.best_streak = 10
    habit.recurrence_pattern = "daily"
    habit.completion_hours_json = None
    habit.learned_on_time_rate = None
    habit.learned_completion_count = None
    habit.learned_preferred_hour = None
    habit.learned_difficulty_level = None
    habit.learned_recovery_difficulty = None
    for k, v in kwargs.items():
        setattr(habit, k, v)
    return habit


def _make_backend():
    """Create a mock backend."""
    backend = AsyncMock()
    backend.get = AsyncMock()
    backend.update = AsyncMock(return_value=Result.ok(True))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    return backend


def _make_relationships():
    """Create a mock relationship service."""
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


def _make_service(backend=None, relationships=None):
    """Create HabitsIntelligenceService with mocks."""
    if backend is None:
        backend = _make_backend()
    if relationships is None:
        relationships = _make_relationships()
    return HabitsIntelligenceService(
        backend=backend,
        relationship_service=relationships,
    )


class TestLearnFromCompletion:
    """Test learn_from_completion event handler."""

    @pytest.mark.asyncio
    async def test_tracks_completion_hour(self):
        """Records completion hour in histogram."""
        backend = _make_backend()
        habit = _make_habit()
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime(2026, 3, 9, 14, 30),  # 2:30 PM
        )

        await service.learn_from_completion(event)

        update_call = backend.update.call_args[0]
        assert update_call[0] == "habit_test_abc"
        props = update_call[1]
        hours_hist = json.loads(props["completion_hours_json"])
        assert hours_hist["14"] == 1
        assert props["learned_preferred_hour"] == 14

    @pytest.mark.asyncio
    async def test_builds_histogram_over_time(self):
        """Histogram accumulates across completions."""
        backend = _make_backend()
        service = _make_service(backend)

        # First completion at 8 AM
        habit1 = _make_habit()
        backend.get.return_value = Result.ok(habit1)
        event1 = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime(2026, 3, 9, 8, 0),
        )
        await service.learn_from_completion(event1)

        # Second completion at 8 AM (with existing histogram)
        hist_after_first = backend.update.call_args[0][1]["completion_hours_json"]
        habit2 = _make_habit(completion_hours_json=hist_after_first, learned_completion_count=1)
        backend.get.return_value = Result.ok(habit2)
        event2 = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime(2026, 3, 10, 8, 0),
        )
        await service.learn_from_completion(event2)

        props = backend.update.call_args[0][1]
        hours_hist = json.loads(props["completion_hours_json"])
        assert hours_hist["8"] == 2
        assert props["learned_preferred_hour"] == 8

    @pytest.mark.asyncio
    async def test_preferred_hour_is_mode(self):
        """Preferred hour is the most frequent completion hour."""
        backend = _make_backend()
        # Simulate existing histogram: 8 AM=3, 14 PM=5
        existing_hist = json.dumps({"8": 3, "14": 5})
        habit = _make_habit(completion_hours_json=existing_hist, learned_completion_count=8)
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        # Complete at 14:00 again
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime(2026, 3, 9, 14, 0),
        )
        await service.learn_from_completion(event)

        props = backend.update.call_args[0][1]
        assert props["learned_preferred_hour"] == 14

    @pytest.mark.asyncio
    async def test_on_time_rate_ema(self):
        """On-time rate uses EMA."""
        backend = _make_backend()
        habit = _make_habit(learned_on_time_rate=0.8)
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        # Complete late
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
            completed_on_time=False,
        )
        await service.learn_from_completion(event)

        # EMA = 0.2 * 0.0 + 0.8 * 0.8 = 0.64
        props = backend.update.call_args[0][1]
        assert abs(props["learned_on_time_rate"] - 0.64) < 0.01

    @pytest.mark.asyncio
    async def test_on_time_rate_cold_start_on_time(self):
        """Cold-start on-time rate for on-time completion."""
        backend = _make_backend()
        habit = _make_habit()
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
            completed_on_time=True,
        )
        await service.learn_from_completion(event)

        # Cold start: old_rate = 1.0, EMA = 0.2 * 1.0 + 0.8 * 1.0 = 1.0
        props = backend.update.call_args[0][1]
        assert abs(props["learned_on_time_rate"] - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_increments_completion_count(self):
        """Completion count increments."""
        backend = _make_backend()
        habit = _make_habit(learned_completion_count=5)
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
        )
        await service.learn_from_completion(event)

        props = backend.update.call_args[0][1]
        assert props["learned_completion_count"] == 6

    @pytest.mark.asyncio
    async def test_error_is_swallowed(self):
        """Errors don't propagate."""
        backend = _make_backend()
        backend.get.side_effect = Exception("DB down")

        service = _make_service(backend)
        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
        )
        # Should not raise
        await service.learn_from_completion(event)


class TestStreakBrokenPersistence:
    """Test that handle_habit_streak_broken persists recovery difficulty."""

    @pytest.mark.asyncio
    async def test_persists_recovery_difficulty(self):
        backend = _make_backend()
        habit = _make_habit()
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitStreakBroken(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime(2026, 3, 9),
            streak_length=14,
            last_completion_date=datetime(2026, 3, 5),
            days_since_last_completion=4,
        )

        await service.handle_habit_streak_broken(event)

        # Should have called update with learning state
        update_calls = backend.update.call_args_list
        # Find the call with learned_recovery_difficulty
        learning_call = None
        for call in update_calls:
            props = call[0][1]
            if "learned_recovery_difficulty" in props:
                learning_call = props
                break

        assert learning_call is not None
        assert 0.0 <= learning_call["learned_recovery_difficulty"] <= 1.0
        assert learning_call["last_streak_length"] == 14
        assert learning_call["last_break_date"] == "2026-03-09T00:00:00"


class TestMissedPersistence:
    """Test that handle_habit_missed persists difficulty level."""

    @pytest.mark.asyncio
    async def test_persists_difficulty_level(self):
        backend = _make_backend()
        habit = _make_habit()
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
            consecutive_misses=4,
            days_overdue=2,
        )

        await service.handle_habit_missed(event)

        # Should persist difficulty assessment
        update_calls = backend.update.call_args_list
        learning_call = None
        for call in update_calls:
            props = call[0][1]
            if "learned_difficulty_level" in props:
                learning_call = props
                break

        assert learning_call is not None
        assert learning_call["learned_difficulty_level"] == "difficult"
        assert "miss_pattern_updated_at" in learning_call

    @pytest.mark.asyncio
    async def test_persists_normal_difficulty_for_single_miss(self):
        backend = _make_backend()
        habit = _make_habit()
        backend.get.return_value = Result.ok(habit)

        service = _make_service(backend)
        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_123",
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
            consecutive_misses=1,
            days_overdue=0,
        )

        await service.handle_habit_missed(event)

        update_calls = backend.update.call_args_list
        learning_call = None
        for call in update_calls:
            props = call[0][1]
            if "learned_difficulty_level" in props:
                learning_call = props
                break

        assert learning_call is not None
        assert learning_call["learned_difficulty_level"] == "normal"


class TestPerformanceAnalyticsLearnedInsights:
    """Test that get_performance_analytics includes learned insights."""

    @pytest.mark.asyncio
    async def test_includes_learned_insights(self):
        backend = _make_backend()
        habits = [
            _make_habit(uid="h1", learned_difficulty_level="difficult", learned_preferred_hour=8, learned_on_time_rate=0.85),
            _make_habit(uid="h2", learned_difficulty_level=None, learned_preferred_hour=14, learned_on_time_rate=0.92),
            _make_habit(uid="h3", learned_difficulty_level=None, learned_preferred_hour=None, learned_on_time_rate=None),
        ]
        backend.find_by.return_value = Result.ok(habits)

        service = _make_service(backend)
        result = await service.get_performance_analytics("user_123")

        assert result.is_ok
        insights = result.value["learned_insights"]
        assert insights["habits_with_difficulty"] == 1
        assert insights["habits_with_timing_data"] == 2
        assert abs(insights["avg_on_time_rate"] - 0.885) < 0.01

    @pytest.mark.asyncio
    async def test_no_learned_data(self):
        backend = _make_backend()
        habits = [_make_habit(uid="h1")]
        backend.find_by.return_value = Result.ok(habits)

        service = _make_service(backend)
        result = await service.get_performance_analytics("user_123")

        assert result.is_ok
        insights = result.value["learned_insights"]
        assert insights["habits_with_difficulty"] == 0
        assert insights["habits_with_timing_data"] == 0
        assert insights["avg_on_time_rate"] is None
