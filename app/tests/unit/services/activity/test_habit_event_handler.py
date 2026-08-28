"""
Unit tests for HabitEventHandlerService.

Tests cover:
- handle_habit_completed: timing learning, EMA on-time rate, aggregate badges
- handle_habit_streak_broken: recovery difficulty, knowledge impact
- handle_habit_missed: difficulty pattern detection, insight persistence
- handle_habit_streak_milestone: badge awarding, duplicate prevention
- _check_aggregate_badges: completion, quality, identity badge awarding
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
    backend.get_user_badges = AsyncMock(return_value=Result.ok([]))
    backend.get_habit_badges = AsyncMock(return_value=Result.ok([]))
    backend.check_badge_already_earned = AsyncMock(return_value=Result.ok(False))
    backend.award_badge = AsyncMock(return_value=Result.ok(True))
    # Aggregate badge methods
    backend.get_user_badge_stats = AsyncMock(
        return_value=Result.ok(
            {
                "total_completions": 0,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )
    )
    backend.check_user_badge_earned = AsyncMock(return_value=Result.ok(False))
    backend.award_user_badge = AsyncMock(return_value=Result.ok(True))
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
    event_bus = AsyncMock()
    return HabitEventHandlerService(
        backend=mock_backend,
        relationship_service=mock_relationships,
        insight_store=mock_insight_store,
        event_bus=event_bus,
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
        self,
        service_full: HabitEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
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
        self,
        service_full: HabitEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
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
        self,
        service_full: HabitEventHandlerService,
        mock_backend: Mock,
        mock_insight_store: AsyncMock,
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
        mock_backend.check_badge_already_earned.return_value = Result.ok(False)
        mock_backend.award_badge.return_value = Result.ok(True)

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        await service.handle_habit_streak_milestone(event)

        mock_backend.check_badge_already_earned.assert_called_once()
        mock_backend.award_badge.assert_called_once()

    @pytest.mark.asyncio
    async def test_badge_row_and_event_agree_on_when_it_was_earned(
        self, service_full: HabitEventHandlerService, mock_backend: Mock
    ):
        """The persisted badge and the published event must name the same moment.

        ``_award_badge`` writes the milestone's own ``occurred_at`` to the badge row. If
        ``AchievementEarned`` lets ``occurred_at`` default instead, the row and the event
        disagree by however long the handler took to run — invisible when the milestone is
        processed immediately, wrong on a backfill or under delayed processing.

        The source time is deliberately backdated: with ``datetime.now()`` both halves would
        agree by accident and the test could not fail.
        """
        milestone_time = datetime(2026, 3, 20, 14, 30)
        mock_backend.check_badge_already_earned.return_value = Result.ok(False)
        mock_backend.award_badge.return_value = Result.ok(True)

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=milestone_time,
            milestone_name="one_week",
        )

        await service_full.handle_habit_streak_milestone(event)

        # The persisted half.
        persisted = mock_backend.award_badge.call_args.kwargs["occurred_at"]
        assert persisted == milestone_time.isoformat()

        # The published half must name that same moment, not the handler's run time.
        published = service_full.event_bus.publish_async.call_args.args[0]
        assert published.occurred_at == milestone_time, (
            "AchievementEarned must carry the milestone's occurred_at, so the badge row "
            "and the badge event agree on when the badge was earned"
        )

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

        mock_backend.check_badge_already_earned.assert_not_called()
        mock_backend.award_badge.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_badge_prevented(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Already-earned badge is not awarded again."""
        mock_backend.check_badge_already_earned.return_value = Result.ok(True)

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        await service.handle_habit_streak_milestone(event)

        mock_backend.check_badge_already_earned.assert_called_once()
        mock_backend.award_badge.assert_not_called()

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: HabitEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.check_badge_already_earned.side_effect = ServiceUnavailable("connection lost")

        event = HabitStreakMilestone(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        # Should NOT raise
        await service.handle_habit_streak_milestone(event)


# ---------------------------------------------------------------------------
# _check_aggregate_badges tests
# ---------------------------------------------------------------------------


class TestCheckAggregateBadges:
    """Tests for _check_aggregate_badges — completion, quality, identity badges."""

    @pytest.mark.asyncio
    async def test_awards_getting_started_at_10_completions(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 12,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        # Should award getting_started (threshold 10) but not habit_builder (threshold 50)
        awarded_ids = [
            call.kwargs["badge_id"] for call in mock_backend.award_user_badge.call_args_list
        ]
        assert "getting_started" in awarded_ids
        assert "habit_builder" not in awarded_ids

    @pytest.mark.asyncio
    async def test_awards_multiple_completion_badges(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 55,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        awarded_ids = [
            call.kwargs["badge_id"] for call in mock_backend.award_user_badge.call_args_list
        ]
        assert "getting_started" in awarded_ids
        assert "habit_builder" in awarded_ids
        assert "habit_master" not in awarded_ids

    @pytest.mark.asyncio
    async def test_awards_quality_badge_at_100(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 0,
                "high_quality_completions": 105,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        awarded_ids = [
            call.kwargs["badge_id"] for call in mock_backend.award_user_badge.call_args_list
        ]
        assert "quality_focused" in awarded_ids

    @pytest.mark.asyncio
    async def test_awards_identity_badges(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 0,
                "high_quality_completions": 0,
                "max_identity_votes": 210,
                "established_identity_count": 3,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        awarded_ids = [
            call.kwargs["badge_id"] for call in mock_backend.award_user_badge.call_args_list
        ]
        assert "identity_established" in awarded_ids
        assert "identity_master" in awarded_ids
        assert "multi_identity" in awarded_ids

    @pytest.mark.asyncio
    async def test_skips_already_earned_badges(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 15,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )
        # getting_started already earned
        mock_backend.check_user_badge_earned.return_value = Result.ok(True)

        await service_full._check_aggregate_badges("user_mike")

        mock_backend.award_user_badge.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_achievement_earned_event(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 15,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        # Event bus should have been called
        service_full.event_bus.publish_async.assert_called()
        published_event = service_full.event_bus.publish_async.call_args[0][0]
        assert published_event.badge_id == "getting_started"
        assert published_event.badge_category == "completion"
        assert published_event.threshold_value == 10

    @pytest.mark.asyncio
    async def test_no_awards_below_threshold(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 5,
                "high_quality_completions": 0,
                "max_identity_votes": 0,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        mock_backend.award_user_badge.assert_not_called()

    @pytest.mark.asyncio
    async def test_stats_error_does_not_raise(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        mock_backend.get_user_badge_stats.return_value = Result.fail(
            {"message": "connection error"}
        )

        # Fire-and-forget: should NOT raise
        await service_full._check_aggregate_badges("user_mike")

        mock_backend.award_user_badge.assert_not_called()

    @pytest.mark.asyncio
    async def test_badge_category_in_event(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        """Identity badges should have badge_category='identity'."""
        mock_backend.get_user_badge_stats.return_value = Result.ok(
            {
                "total_completions": 0,
                "high_quality_completions": 0,
                "max_identity_votes": 60,
                "established_identity_count": 0,
            }
        )

        await service_full._check_aggregate_badges("user_mike")

        awarded = mock_backend.award_user_badge.call_args
        assert awarded.kwargs["badge_category"] == "identity"


class TestHandleHabitCompletedCallsAggregateBadges:
    """Verify handle_habit_completed triggers aggregate badge checking."""

    @pytest.mark.asyncio
    async def test_calls_check_aggregate_badges(
        self, mock_backend: Mock, service_full: HabitEventHandlerService
    ):
        habit = _make_habit(learned_completion_count=5)
        mock_backend.get.return_value = Result.ok(habit)

        event = HabitCompleted(
            habit_uid="habit_test_abc",
            user_uid="user_mike",
            occurred_at=datetime(2026, 3, 26, 14, 30),
        )

        await service_full.handle_habit_completed(event)

        # Should have called get_user_badge_stats (from _check_aggregate_badges)
        mock_backend.get_user_badge_stats.assert_called_once_with("user_mike")
