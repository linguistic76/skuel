"""
Unit tests for Habits adaptive learning loop (ADR-048).

A habit's learning state is stored on its node and read raw — the ``Habit`` model
declares none of it. Tests cover:
- Hour histogram tracking and mode calculation
- On-time rate EMA
- Completion count accumulating across completions
- A streak break writes nothing to the habit
- A miss persists the difficulty level
- Performance analytics count the learned state read raw per habit
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.habit_events import HabitCompleted, HabitMissed, HabitStreakBroken
from core.models.habit.habit import Habit
from core.models.habit.learning_state import (
    habit_learning_state,
    plan_completion_timing,
)
from core.services.habits.habit_event_handler_service import HabitEventHandlerService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.utils.result_simplified import Errors, Result
from tests.helpers.habit_learning_fake import HabitLearningStore
from tests.helpers.laptop_clock import laptop_wall

HABIT = "habit_test_abc"


def _make_habit(uid=HABIT, title="Test Habit"):
    """Create a mock Habit with common defaults."""
    habit = MagicMock(spec=Habit)
    habit.uid = uid
    habit.title = title
    habit.is_active = True
    habit.success_rate = 0.8
    habit.current_streak = 5
    habit.best_streak = 10
    habit.recurrence_pattern = "daily"
    return habit


def _make_backend(**stored: object):
    """A mock backend whose learning writes land in a ``HabitLearningStore`` holding HABIT."""
    backend = AsyncMock()
    backend.get = AsyncMock(return_value=Result.ok(_make_habit()))
    backend.update = AsyncMock(return_value=Result.ok(True))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.learning = HabitLearningStore(HABIT)
    backend.learning.states[HABIT].update(stored)
    backend.update_habit_learning_state = backend.learning.update_habit_learning_state
    return backend


def _make_relationships():
    """Create a mock relationship service."""
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


def _make_event_handler(backend):
    return HabitEventHandlerService(backend=backend, relationship_service=_make_relationships())


def _make_intelligence_service(backend):
    return HabitsIntelligenceService(
        backend=backend,
        relationship_service=_make_relationships(),
        cross_domain_query=AsyncMock(),
    )


def _completed(occurred_at: datetime, *, on_time: bool = True) -> HabitCompleted:
    return HabitCompleted(
        habit_uid=HABIT, user_uid="user_123", occurred_at=occurred_at, completed_on_time=on_time
    )


class TestLearnFromCompletion:
    """Test handle_habit_completed event handler."""

    @pytest.mark.usefixtures("laptop_zone")
    @pytest.mark.asyncio
    async def test_tracks_completion_hour(self):
        """Records completion hour in histogram."""
        backend = _make_backend()

        await _make_event_handler(backend).handle_habit_completed(
            _completed(laptop_wall(2026, 3, 9, 14, 30))  # 2:30 PM
        )

        state = backend.learning.states[HABIT]
        assert json.loads(state["completion_hours_json"]) == {"14": 1}
        assert state["learned_preferred_hour"] == 14
        backend.update.assert_not_called()

    @pytest.mark.usefixtures("laptop_zone")
    @pytest.mark.asyncio
    async def test_builds_histogram_over_time(self):
        """Histogram and count accumulate across completions."""
        backend = _make_backend()
        service = _make_event_handler(backend)

        await service.handle_habit_completed(_completed(laptop_wall(2026, 3, 9, 8, 0)))
        await service.handle_habit_completed(_completed(laptop_wall(2026, 3, 10, 8, 0)))

        state = backend.learning.states[HABIT]
        assert json.loads(state["completion_hours_json"]) == {"8": 2}
        assert state["learned_preferred_hour"] == 8
        assert state["learned_completion_count"] == 2

    @pytest.mark.asyncio
    async def test_preferred_hour_is_mode(self):
        """Preferred hour is the most frequent completion hour."""
        backend = _make_backend(
            completion_hours_json=json.dumps({"8": 3, "14": 5}), learned_completion_count=8
        )

        await _make_event_handler(backend).handle_habit_completed(
            _completed(datetime(2026, 3, 9, 14, 0))
        )

        assert backend.learning.states[HABIT]["learned_preferred_hour"] == 14

    @pytest.mark.asyncio
    async def test_on_time_rate_ema(self):
        """On-time rate uses EMA."""
        backend = _make_backend(learned_on_time_rate=0.8)

        await _make_event_handler(backend).handle_habit_completed(
            _completed(datetime.now(), on_time=False)
        )

        # EMA = 0.2 * 0.0 + 0.8 * 0.8 = 0.64
        assert abs(backend.learning.states[HABIT]["learned_on_time_rate"] - 0.64) < 0.01

    @pytest.mark.asyncio
    async def test_on_time_rate_cold_start_on_time(self):
        """A habit's first completion sets the on-time rate outright."""
        backend = _make_backend()

        await _make_event_handler(backend).handle_habit_completed(_completed(datetime.now()))

        assert backend.learning.states[HABIT]["learned_on_time_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_increments_completion_count(self):
        """Completion count increments."""
        backend = _make_backend(learned_completion_count=5)

        await _make_event_handler(backend).handle_habit_completed(_completed(datetime.now()))

        assert backend.learning.states[HABIT]["learned_completion_count"] == 6

    @pytest.mark.asyncio
    async def test_a_refused_write_is_logged_not_raised(self):
        """A learning write the backend refuses is logged; no badge check follows."""
        backend = _make_backend()
        backend.update_habit_learning_state = AsyncMock(
            return_value=Result.fail(Errors.not_found("Habit", HABIT))
        )
        backend.get_user_badge_stats = AsyncMock()

        await _make_event_handler(backend).handle_habit_completed(_completed(datetime.now()))

        backend.get_user_badge_stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_is_swallowed(self):
        """Errors don't propagate."""
        from neo4j.exceptions import ServiceUnavailable

        backend = _make_backend()
        backend.update_habit_learning_state = AsyncMock(side_effect=ServiceUnavailable("DB down"))

        # Should not raise
        await _make_event_handler(backend).handle_habit_completed(_completed(datetime.now()))


class TestLearningStatePlanner:
    """The pure read and plan the handler and the analytics share."""

    def test_an_unwritten_habit_reads_empty(self):
        assert habit_learning_state({}) == {
            "completion_hours": {},
            "learned_preferred_hour": None,
            "learned_on_time_rate": None,
            "learned_completion_count": 0,
            "learned_difficulty_level": None,
        }

    def test_the_plan_writes_only_the_timing_properties(self):
        written = plan_completion_timing({}, hour=7, completed_on_time=True)
        assert set(written) == {
            "completion_hours_json",
            "learned_preferred_hour",
            "learned_on_time_rate",
            "learned_completion_count",
        }


class TestStreakBrokenWritesNothing:
    """A streak break is analysed and logged; nothing reads a stored record of it."""

    @pytest.mark.asyncio
    async def test_writes_nothing_to_the_habit(self):
        backend = _make_backend()

        await _make_event_handler(backend).handle_habit_streak_broken(
            HabitStreakBroken(
                habit_uid=HABIT,
                user_uid="user_123",
                occurred_at=datetime(2026, 3, 9),
                streak_length=14,
                last_completion_date=datetime(2026, 3, 5),
                days_since_last_completion=4,
            )
        )

        backend.update.assert_not_called()
        assert backend.learning.writes == []


class TestMissedPersistence:
    """Test that handle_habit_missed persists difficulty level."""

    @pytest.mark.parametrize(("misses", "level"), [(4, "difficult"), (1, "normal")])
    @pytest.mark.asyncio
    async def test_persists_difficulty_level(self, misses: int, level: str):
        backend = _make_backend()

        await _make_event_handler(backend).handle_habit_missed(
            HabitMissed(
                habit_uid=HABIT,
                user_uid="user_123",
                occurred_at=datetime.now(),
                scheduled_date=datetime.now(),
                consecutive_misses=misses,
                days_overdue=2,
            )
        )

        assert backend.learning.writes == [(HABIT, {"learned_difficulty_level": level})]


def _real_habit(uid: str) -> Habit:
    """A real Habit (the analytics hydrate it with ``dataclasses.replace``)."""
    return Habit(uid=uid, user_uid="user_123", title=f"Habit {uid}")


def _analytics_backend(habits: list[Habit], raw_states: dict[str, dict[str, object]]):
    backend = _make_backend()
    backend.find_by.return_value = Result.ok(habits)
    backend.get_habit_window_completions.return_value = Result.ok(
        {habit.uid: [] for habit in habits}
    )
    backend.get_habit_learning_states = AsyncMock(return_value=Result.ok(raw_states))
    return backend


class TestPerformanceAnalyticsLearnedInsights:
    """get_performance_analytics counts the learned state, read raw per habit."""

    @pytest.mark.asyncio
    async def test_includes_learned_insights(self):
        habits = [_real_habit("h1"), _real_habit("h2"), _real_habit("h3")]
        backend = _analytics_backend(
            habits,
            {
                "h1": {
                    "learned_difficulty_level": "difficult",
                    "learned_preferred_hour": 8,
                    "learned_on_time_rate": 0.85,
                },
                "h2": {"learned_preferred_hour": 14, "learned_on_time_rate": 0.92},
                "h3": {},
                # A habit outside the analytics' own set is not counted.
                "h_other": {"learned_preferred_hour": 3, "learned_on_time_rate": 0.1},
            },
        )

        result = await _make_intelligence_service(backend).get_performance_analytics("user_123")

        assert result.is_ok
        backend.get_habit_learning_states.assert_awaited_once_with("user_123")
        insights = result.value["learned_insights"]
        assert insights["habits_with_difficulty"] == 1
        assert insights["habits_with_timing_data"] == 2
        assert abs(insights["avg_on_time_rate"] - 0.885) < 0.01

    @pytest.mark.asyncio
    async def test_no_learned_data(self):
        backend = _analytics_backend([_real_habit("h1")], {"h1": {}})

        result = await _make_intelligence_service(backend).get_performance_analytics("user_123")

        assert result.is_ok
        assert result.value["learned_insights"] == {
            "habits_with_difficulty": 0,
            "habits_with_timing_data": 0,
            "avg_on_time_rate": None,
        }

    @pytest.mark.asyncio
    async def test_a_failed_learning_read_fails_the_analytics(self):
        backend = _analytics_backend([_real_habit("h1")], {})
        backend.get_habit_learning_states = AsyncMock(
            return_value=Result.fail(Errors.database(operation="read", message="down"))
        )

        result = await _make_intelligence_service(backend).get_performance_analytics("user_123")

        assert result.is_error
