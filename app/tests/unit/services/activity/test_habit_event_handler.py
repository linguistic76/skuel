"""
Unit tests for HabitEventHandlerService.

Tests cover:
- handle_habit_completed: timing learning, EMA on-time rate
- handle_habit_streak_broken: recovery difficulty, knowledge impact
- handle_habit_missed: difficulty pattern detection, insight persistence
- handle_habit_streak_milestone: badge awarding, duplicate prevention
- Fire-and-forget contract: exceptions logged, never propagated
- Module-level helpers: _calculate_recovery_difficulty, _calculate_miss_severity
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.events.habit_events import (
    HabitCompleted,
    HabitMissed,
    HabitStreakBroken,
    HabitStreakMilestone,
)
from core.services.habits.habit_event_handler_service import (
    HabitEventHandlerService,
    _calculate_miss_severity,
    _calculate_recovery_difficulty,
)
from core.utils.result_simplified import Result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.execute_query = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_relationships() -> AsyncMock:
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


@pytest.fixture
def mock_insight_store() -> AsyncMock:
    store = AsyncMock()
    store.create_insight = AsyncMock(return_value=Result.ok(True))
    return store


@pytest.fixture
def service(mock_backend: Mock) -> HabitEventHandlerService:
    return HabitEventHandlerService(backend=mock_backend)


@pytest.fixture
def service_full(
    mock_backend: Mock, mock_relationships: AsyncMock, mock_insight_store: AsyncMock
) -> HabitEventHandlerService:
    return HabitEventHandlerService(
        backend=mock_backend,
        relationship_service=mock_relationships,
        insight_store=mock_insight_store,
        event_bus=Mock(),
    )


def _make_habit(
    uid: str = "habit_test_abc",
    title: str = "Test Habit",
    completion_hours_json: str | None = None,
    learned_on_time_rate: float | None = None,
    learned_completion_count: int | None = None,
    recurrence_pattern: str | None = "daily",
    current_streak: int = 0,
    success_rate: float = 0.8,
) -> Mock:
    """Create a mock habit with given attributes."""
    habit = Mock()
    habit.uid = uid
    habit.title = title
    habit.completion_hours_json = completion_hours_json
    habit.learned_on_time_rate = learned_on_time_rate
    habit.learned_completion_count = learned_completion_count
    habit.recurrence_pattern = recurrence_pattern
    habit.current_streak = current_streak
    habit.success_rate = success_rate
    return habit


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestCalculateRecoveryDifficulty:
    def test_short_streak_small_gap(self):
        """Short streak + small gap = easy recovery."""
        result = _calculate_recovery_difficulty(3, 1)
        assert 0.0 <= result < 0.3

    def test_long_streak_large_gap(self):
        """Long streak + large gap = hard recovery."""
        result = _calculate_recovery_difficulty(100, 14)
        assert result > 0.6

    def test_zero_values(self):
        """Zero streak and gap produce very low difficulty."""
        result = _calculate_recovery_difficulty(0, 0)
        assert result < 0.1

    def test_capped_at_one(self):
        """Result never exceeds 1.0."""
        result = _calculate_recovery_difficulty(10000, 100)
        assert result <= 1.0

    def test_medium_streak(self):
        """30-day streak with 7-day gap = moderate difficulty."""
        result = _calculate_recovery_difficulty(30, 7)
        assert 0.3 <= result <= 0.7


class TestCalculateMissSeverity:
    def test_low_severity(self):
        assert _calculate_miss_severity(1, 0) == "low"

    def test_medium_severity(self):
        assert _calculate_miss_severity(2, 1) == "medium"

    def test_high_severity(self):
        assert _calculate_miss_severity(5, 2) == "high"

    def test_critical_severity(self):
        assert _calculate_miss_severity(6, 6) == "critical"

    def test_miss_score_capped_at_six(self):
        """Consecutive misses above 6 don't increase score further."""
        result1 = _calculate_miss_severity(6, 0)
        result2 = _calculate_miss_severity(10, 0)
        assert result1 == result2


# ---------------------------------------------------------------------------
# handle_habit_completed tests
# ---------------------------------------------------------------------------


class TestHandleHabitCompleted:
    @pytest.mark.asyncio
    async def test_timing_learning_happy_path(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Completion hour histogram and on-time rate persisted to Habit node."""
        habit = _make_habit()
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            occurred_at=datetime(2026, 3, 20, 14, 30),
            completed_on_time=True,
        )

        await service.handle_habit_completed(event)

        mock_backend.update.assert_called_once()
        call_args = mock_backend.update.call_args
        assert call_args[0][0] == "habit_test_abc"
        state = call_args[0][1]
        assert "completion_hours_json" in state
        assert "learned_preferred_hour" in state
        assert state["learned_preferred_hour"] == 14
        assert "learned_on_time_rate" in state
        assert "learned_completion_count" in state
        assert state["learned_completion_count"] == 1

    @pytest.mark.asyncio
    async def test_not_found_early_return(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """No update when habit not found."""
        mock_backend.get.return_value = Result.ok(None)

        event = HabitCompleted(
            habit_uid="habit_missing",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            completed_on_time=True,
        )

        await service.handle_habit_completed(event)
        mock_backend.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            occurred_at=datetime.now(),
            completed_on_time=True,
        )

        # Should NOT raise
        await service.handle_habit_completed(event)


# ---------------------------------------------------------------------------
# handle_habit_streak_broken tests
# ---------------------------------------------------------------------------


class TestHandleHabitStreakBroken:
    @pytest.mark.asyncio
    async def test_recovery_analysis_happy_path(
        self, service_full: HabitEventHandlerService, mock_backend: Mock
    ):
        """Recovery difficulty persisted to Habit node."""
        habit = _make_habit(title="Morning Run")
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitStreakBroken(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=14,
            days_since_last_completion=3,
            occurred_at=datetime.now(),
            last_completion_date=datetime.now(),
        )

        await service_full.handle_habit_streak_broken(event)

        mock_backend.update.assert_called_once()
        state = mock_backend.update.call_args[0][1]
        assert "learned_recovery_difficulty" in state
        assert "last_streak_length" in state
        assert state["last_streak_length"] == 14
        assert "last_break_date" in state

    @pytest.mark.asyncio
    async def test_knowledge_impact_queried(
        self, service_full: HabitEventHandlerService, mock_backend: Mock, mock_relationships: AsyncMock
    ):
        """Knowledge reinforcement relationships are queried."""
        habit = _make_habit()
        mock_backend.get.return_value = Result.ok(habit)
        mock_relationships.get_related_uids.return_value = Result.ok(["ku_test_1", "ku_test_2"])

        event = HabitStreakBroken(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            days_since_last_completion=2,
            occurred_at=datetime.now(),
            last_completion_date=datetime.now(),
        )

        with patch.object(service_full.logger, "info") as mock_log:
            await service_full.handle_habit_streak_broken(event)
            log_calls = [c for c in mock_log.call_args_list if "Knowledge reinforcement" in str(c)]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_not_found_early_return(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """No update when habit not found."""
        mock_backend.get.return_value = Result.ok(None)

        event = HabitStreakBroken(
            habit_uid="habit_missing",
            user_uid="user_mike",
            streak_length=7,
            days_since_last_completion=2,
            occurred_at=datetime.now(),
            last_completion_date=datetime.now(),
        )

        await service.handle_habit_streak_broken(event)
        mock_backend.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = HabitStreakBroken(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            days_since_last_completion=2,
            occurred_at=datetime.now(),
            last_completion_date=datetime.now(),
        )

        # Should NOT raise
        await service.handle_habit_streak_broken(event)


# ---------------------------------------------------------------------------
# handle_habit_missed tests
# ---------------------------------------------------------------------------


class TestHandleHabitMissed:
    @pytest.mark.asyncio
    async def test_difficulty_detection_happy_path(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Difficulty assessment persisted to Habit node."""
        habit = _make_habit(title="Daily Journal")
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            consecutive_misses=4,
            days_overdue=3,
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
        )

        await service.handle_habit_missed(event)

        mock_backend.update.assert_called_once()
        state = mock_backend.update.call_args[0][1]
        assert state["learned_difficulty_level"] == "difficult"
        assert "miss_pattern_updated_at" in state

    @pytest.mark.asyncio
    async def test_very_difficult_assessment(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """5+ consecutive misses classified as very_difficult."""
        habit = _make_habit()
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            consecutive_misses=6,
            days_overdue=5,
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
        )

        await service.handle_habit_missed(event)

        state = mock_backend.update.call_args[0][1]
        assert state["learned_difficulty_level"] == "very_difficult"

    @pytest.mark.asyncio
    async def test_normal_miss_no_insight(
        self, service_full: HabitEventHandlerService, mock_backend: Mock, mock_insight_store: AsyncMock
    ):
        """Single miss does not persist insight."""
        habit = _make_habit()
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            consecutive_misses=1,
            days_overdue=1,
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
        )

        await service_full.handle_habit_missed(event)

        mock_insight_store.create_insight.assert_not_called()

    @pytest.mark.asyncio
    async def test_difficult_persists_insight(
        self, service_full: HabitEventHandlerService, mock_backend: Mock, mock_insight_store: AsyncMock
    ):
        """3+ consecutive misses persist difficulty insight."""
        habit = _make_habit(title="Morning Meditation")
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            consecutive_misses=4,
            days_overdue=3,
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
        )

        await service_full.handle_habit_missed(event)

        mock_insight_store.create_insight.assert_called_once()

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = HabitMissed(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            consecutive_misses=3,
            days_overdue=2,
            occurred_at=datetime.now(),
            scheduled_date=datetime.now(),
        )

        # Should NOT raise
        await service.handle_habit_missed(event)


# ---------------------------------------------------------------------------
# handle_habit_streak_milestone tests
# ---------------------------------------------------------------------------


class TestHandleHabitStreakMilestone:
    @pytest.mark.asyncio
    async def test_badge_awarded_for_milestone(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Badge is awarded for a valid milestone streak."""
        # _check_badge_already_earned returns False
        mock_backend.execute_query.side_effect = [
            Result.ok([{"already_earned": False}]),  # check query
            Result.ok([{"badge_id": "habit_week_warrior"}]),  # award query
        ]

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        await service.handle_habit_streak_milestone(event)

        # Two execute_query calls: check + award
        assert mock_backend.execute_query.call_count == 2

    @pytest.mark.asyncio
    async def test_non_milestone_ignored(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Non-milestone streak lengths don't trigger badge queries."""
        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=15,
            occurred_at=datetime.now(),
            milestone_name="custom",
        )

        await service.handle_habit_streak_milestone(event)

        mock_backend.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_badge_prevented(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Already-earned badge is not awarded again."""
        mock_backend.execute_query.return_value = Result.ok([{"already_earned": True}])

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        await service.handle_habit_streak_milestone(event)

        # Only the check query, no award query
        assert mock_backend.execute_query.call_count == 1

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.execute_query.side_effect = ServiceUnavailable("connection lost")

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        # Should NOT raise
        await service.handle_habit_streak_milestone(event)
