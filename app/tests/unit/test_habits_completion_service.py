"""
Tests for Habits Completion Tracking Service
=============================================

Comprehensive tests for the HabitsCompletionService including:
- Recording completions
- Calculating statistics
- Badge progress tracking
- Export functionality

Version: 1.0.0
Date: 2025-10-14
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from core.models.enums import Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.enums.entity_enums import EntityType
from core.models.habit.completion import HabitCompletion
from core.models.habit.completion_dto import HabitCompletionDTO
from core.models.habit.habit import Habit as Habit
from core.models.habit.habit_dto import HabitDTO
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_habits_backend() -> AsyncMock:
    """Create mock habits backend."""
    backend = AsyncMock()
    # ✅ Provide default return values to avoid unawaited coroutine warnings
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_completions_backend() -> AsyncMock:
    """Create mock completions backend."""
    backend = AsyncMock()
    # ✅ Provide default return values to avoid unawaited coroutine warnings
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def completion_service(mock_habits_backend, mock_completions_backend) -> HabitsCompletionService:
    """Create completion service with mocked backends."""
    return HabitsCompletionService(
        habits_backend=mock_habits_backend, completions_backend=mock_completions_backend
    )


@pytest.fixture
def sample_habit() -> Habit:
    """Create sample habit."""
    return Habit(
        uid="habit.test.1",
        user_uid="user_mike",  # REQUIRED - habit ownership
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
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _habit(uid: str) -> Habit:
    """Minimal owned Habit — the shape ``find_by`` actually returns."""
    return Habit(
        uid=uid,
        user_uid="user_mike",
        title=f"Habit {uid}",
        entity_type=EntityType.HABIT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_habit_dto(sample_habit):
    """Create sample habit DTO."""
    return sample_habit.to_dto()


@pytest.fixture
def sample_completion() -> HabitCompletion:
    """Create sample completion."""
    return HabitCompletion(
        uid="hc.user.mike.habit.test.1.1729000000",
        habit_uid="habit.test.1",
        user_uid="user_mike",
        completed_at=datetime.now(),
        quality=5,
        duration_actual=35,
        notes="Felt great!",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestServiceInitialization:
    """Test service initialization."""

    def test_requires_habits_backend(self, mock_completions_backend):
        """Test that habits_backend is required."""
        with pytest.raises(ValueError, match="habits_backend is required"):
            HabitsCompletionService(
                habits_backend=None, completions_backend=mock_completions_backend
            )

    def test_requires_completions_backend(self, mock_habits_backend):
        """Test that completions_backend is required."""
        with pytest.raises(ValueError, match="completions_backend is required"):
            HabitsCompletionService(habits_backend=mock_habits_backend, completions_backend=None)

    def test_successful_initialization(self, completion_service):
        """Test successful service initialization."""
        assert completion_service is not None
        assert completion_service.habits_backend is not None
        assert completion_service.completions_backend is not None


class TestRecordCompletion:
    """Test completion recording."""

    @pytest.mark.asyncio
    async def test_record_basic_completion(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """Test recording a basic completion."""
        # Setup mocks - backend.get() returns Habit model, not dict
        mock_habits_backend.get.return_value = Result.ok(sample_habit)
        mock_completions_backend.create.return_value = Result.ok({})
        mock_habits_backend.update.return_value = Result.ok(sample_habit)

        # Record completion
        result = await completion_service.record_completion(
            habit_uid="habit.test.1", user_uid="user_mike"
        )

        # Verify
        assert result.is_ok
        assert isinstance(result.value, HabitCompletion)
        assert result.value.habit_uid == "habit.test.1"

        # Verify habits backend was called (implementation may call get multiple times)
        mock_habits_backend.get.assert_called_with("habit.test.1")
        mock_completions_backend.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_completion_with_quality(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """Test recording completion with quality rating."""
        # Setup mocks - backend.get() returns Habit model, not dict
        mock_habits_backend.get.return_value = Result.ok(sample_habit)
        mock_completions_backend.create.return_value = Result.ok({})
        mock_habits_backend.update.return_value = Result.ok(sample_habit)

        # Record completion
        result = await completion_service.record_completion(
            habit_uid="habit.test.1",
            user_uid="user_mike",
            quality=5,
            duration_actual=35,
            notes="Excellent session!",
        )

        # Verify
        assert result.is_ok
        completion = result.value
        assert completion.quality == 5
        assert completion.duration_actual == 35
        assert completion.notes == "Excellent session!"

    @pytest.mark.asyncio
    async def test_record_completion_habit_not_found(self, completion_service, mock_habits_backend):
        """Test recording completion for non-existent habit."""
        # Setup mock to return not found
        mock_habits_backend.get.return_value = Result.fail(
            {"code": "NOT_FOUND", "message": "Habit not found"}
        )

        # Record completion
        result = await completion_service.record_completion(
            habit_uid="habit.nonexistent", user_uid="user_mike"
        )

        # Verify
        assert result.is_error

    @pytest.mark.asyncio
    async def test_streak_calculation_consecutive_day(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """Test streak increments on consecutive day."""
        # Set last completion to yesterday
        yesterday = datetime.now() - timedelta(days=1)
        habit_with_yesterday = Habit(**{**sample_habit.__dict__, "last_completed": yesterday})

        # Setup mocks — record_completion fetches the habit ONCE (domain model)
        # and computes stats before persisting anything.
        mock_habits_backend.get.return_value = Result.ok(habit_with_yesterday)
        mock_completions_backend.create.return_value = Result.ok({})
        mock_habits_backend.update.return_value = Result.ok({})

        # Record completion today
        await completion_service.record_completion(habit_uid="habit.test.1", user_uid="user_mike")

        # Verify streak was incremented
        update_call = mock_habits_backend.update.call_args
        updates = update_call[0][1]
        assert updates["current_streak"] == 6  # Was 5, now 6

    @pytest.mark.asyncio
    async def test_streak_broken_after_gap(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """Test streak resets after gap."""
        # Set last completion to 3 days ago
        three_days_ago = datetime.now() - timedelta(days=3)
        habit_with_gap = Habit(**{**sample_habit.__dict__, "last_completed": three_days_ago})

        # Setup mocks — record_completion fetches the habit ONCE (domain model)
        # and computes stats before persisting anything.
        mock_habits_backend.get.return_value = Result.ok(habit_with_gap)
        mock_completions_backend.create.return_value = Result.ok({})
        mock_habits_backend.update.return_value = Result.ok({})

        # Record completion today
        await completion_service.record_completion(habit_uid="habit.test.1", user_uid="user_mike")

        # Verify streak was reset
        update_call = mock_habits_backend.update.call_args
        updates = update_call[0][1]
        assert updates["current_streak"] == 1  # Reset to 1

    @pytest.mark.asyncio
    async def test_backfill_compute_failure_persists_nothing(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """Stats are computed BEFORE any write: if the backfill history read
        fails, no completion node is created — otherwise the day-idempotent
        calendar retry could never repair the stranded partial write."""
        habit = Habit(**{**sample_habit.__dict__, "last_completed": datetime.now()})
        mock_habits_backend.get.return_value = Result.ok(habit)
        # The backfill history read (completions find_by) fails.
        mock_completions_backend.find_by.return_value = Result.fail(
            {"code": "DATABASE", "message": "boom"}
        )

        result = await completion_service.record_completion(
            habit_uid="habit.test.1",
            user_uid="user_mike",
            completed_at=datetime.now() - timedelta(days=2),
        )

        assert result.is_error
        mock_completions_backend.create.assert_not_called()
        mock_habits_backend.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_backfill_compute_failure_persists_nothing(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """The bulk helper has the same write order as record_completion:
        stats compute before any write."""
        habit = Habit(**{**sample_habit.__dict__, "last_completed": datetime.now()})
        mock_habits_backend.get.return_value = Result.ok(habit)
        mock_completions_backend.find_by.return_value = Result.fail(
            {"code": "DATABASE", "message": "boom"}
        )

        result = await completion_service._record_completion_no_event(
            "habit.test.1", "user_mike", datetime.now() - timedelta(days=2)
        )

        assert result.is_error
        mock_completions_backend.create.assert_not_called()
        mock_habits_backend.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_helper_reports_every_crossed_milestone(
        self, completion_service, mock_habits_backend, mock_completions_backend, sample_habit
    ):
        """A jump across a threshold reports the interior milestones too —
        exact-equality would skip the 7-day tier on a 5 → 8 jump... here the
        in-order +1 case and a crossing are both pinned via streak 6 → 7."""
        yesterday = datetime.now() - timedelta(days=1)
        habit = Habit(
            **{
                **sample_habit.__dict__,
                "last_completed": yesterday,
                "current_streak": 6,
                "best_streak": 6,
            }
        )
        mock_habits_backend.get.return_value = Result.ok(habit)
        mock_completions_backend.create.return_value = Result.ok({})
        mock_habits_backend.update.return_value = Result.ok({})

        result = await completion_service._record_completion_no_event(
            "habit.test.1", "user_mike", datetime.now()
        )

        assert result.is_ok
        _completion, is_new_record, milestones = result.value
        assert is_new_record is True
        assert milestones == [("habit.test.1", 7)]  # the crossed TIER, not the raw streak


class TestCompletionQueries:
    """Test completion query methods."""

    @pytest.mark.asyncio
    async def test_get_completions_for_habit(
        self, completion_service, mock_completions_backend, sample_completion
    ):
        """Test getting completions for a habit."""
        # Setup mock
        mock_completions_backend.find_by.return_value = Result.ok([sample_completion])

        # Query completions
        result = await completion_service.get_completions_for_habit(
            habit_uid="habit.test.1",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
        )

        # Verify
        assert result.is_ok
        assert len(result.value) == 1
        assert isinstance(result.value[0], HabitCompletion)

    @pytest.mark.asyncio
    async def test_get_today_completions(
        self,
        completion_service,
        mock_completions_backend,
        mock_habits_backend,
        sample_completion,
        sample_habit_dto,
    ):
        """Test getting today's completions."""
        # Setup mocks — completions are user-scoped in ONE query, then each
        # distinct habit_uid is resolved for the response.
        mock_habits_backend.get.return_value = Result.ok(Habit.from_dto(sample_habit_dto))
        mock_completions_backend.find_by.return_value = Result.ok([sample_completion])

        # Query today's completions
        result = await completion_service.get_today_completions(user_uid="user_mike")

        # Verify
        assert result.is_ok
        assert len(result.value) > 0
        assert result.value[0]["habit"] is not None
        assert result.value[0]["completed"] is True

    @pytest.mark.asyncio
    async def test_calculate_completed_today_count(
        self,
        completion_service,
        mock_completions_backend,
        mock_habits_backend,
        sample_completion,
        sample_habit_dto,
    ):
        """Test calculating today's completion count."""
        # Setup mocks — completions are user-scoped in ONE query, then each
        # distinct habit_uid is resolved for the response.
        mock_habits_backend.get.return_value = Result.ok(Habit.from_dto(sample_habit_dto))
        mock_completions_backend.find_by.return_value = Result.ok([sample_completion])

        # Calculate count
        result = await completion_service.calculate_completed_today_count(user_uid="user_mike")

        # Verify
        assert result.is_ok
        assert result.value == 1


class TestCompletionScoping:
    """:HabitCompletion is user-owned — user-scoped reads filter on user_uid."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method",
        ["get_today_completions", "get_badge_progress", "export_completion_history"],
    )
    async def test_user_scoped_reads_filter_by_user_uid(
        self,
        completion_service,
        mock_completions_backend,
        mock_habits_backend,
        sample_habit_dto,
        method,
    ):
        """Every user-scoped read must scope the completions query by user_uid.

        `HabitCompletion` carries `user_uid`, so the property is written AND
        `_create_node` writes the `(User)-[:OWNS]->` edge with it. Before that
        field existed these reads had to walk the user's habits; that workaround
        is gone, and reverting to it would reintroduce an N+1 for no reason.
        """
        mock_habits_backend.find_by.return_value = Result.ok([Habit.from_dto(sample_habit_dto)])
        mock_habits_backend.get.return_value = Result.ok(Habit.from_dto(sample_habit_dto))
        mock_completions_backend.find_by.return_value = Result.ok([])

        result = await getattr(completion_service, method)(user_uid="user_mike")
        assert result.is_ok

        assert mock_completions_backend.find_by.await_count > 0, (
            f"{method} never queried the completions backend"
        )
        for call in mock_completions_backend.find_by.await_args_list:
            assert call.kwargs.get("user_uid") == "user_mike", (
                f"{method} must scope :HabitCompletion by user_uid"
            )

    @pytest.mark.asyncio
    async def test_recorded_completion_carries_its_owner(
        self,
        completion_service,
        mock_completions_backend,
        mock_habits_backend,
        sample_habit,
    ):
        """The owner must reach the node, or no :OWNS edge is written.

        `_create_node` writes `(User)-[:OWNS]->(entity)` only for entities
        carrying a `user_uid`. A completion persisted without one is reachable
        by no owner-scoped read and by no GDPR cascade.
        """
        mock_habits_backend.get.return_value = Result.ok(sample_habit)
        mock_completions_backend.find_by.return_value = Result.ok([])
        mock_completions_backend.create.side_effect = lambda entity: Result.ok(entity)
        mock_habits_backend.update.return_value = Result.ok(sample_habit)

        result = await completion_service.record_completion(
            habit_uid=sample_habit.uid, user_uid="user_mike"
        )

        assert result.is_ok
        assert result.value.user_uid == "user_mike"
        persisted = mock_completions_backend.create.await_args.args[0]
        assert persisted.user_uid == "user_mike", "completion persisted with no owner"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method",
        ["get_today_completions", "get_badge_progress", "export_completion_history"],
    )
    async def test_backend_error_propagates_instead_of_partial_result(
        self,
        completion_service,
        mock_completions_backend,
        mock_habits_backend,
        sample_habit_dto,
        method,
    ):
        """A failed completions read must fail the call, not return a partial answer.

        Restored deliberately: these reads used to loop over the user's habits
        and `continue` past a failed one, which produced an export missing a
        habit's history or a badge count silently short — indistinguishable from
        the real answer. The loops are gone, but the contract they violated is
        the one worth pinning.
        """
        mock_habits_backend.find_by.return_value = Result.ok([Habit.from_dto(sample_habit_dto)])
        mock_habits_backend.get.return_value = Result.ok(Habit.from_dto(sample_habit_dto))
        mock_completions_backend.find_by.return_value = Result.fail(
            Errors.database("find_by", "transient Neo4j failure")
        )

        result = await getattr(completion_service, method)(user_uid="user_mike")

        assert result.is_error, f"{method} swallowed a backend error and returned a partial result"


class TestAnalytics:
    """Test analytics methods."""

    @pytest.mark.asyncio
    async def test_get_completion_stats(self, completion_service, mock_completions_backend):
        """Test getting completion statistics."""
        # Create multiple completions
        completions = []
        for i in range(10):
            comp = HabitCompletion(
                uid=f"hc.user.mike.habit.test.1.{i}",
                habit_uid="habit.test.1",
                user_uid="user_mike",
                completed_at=datetime.now() - timedelta(days=i),
                quality=4 + (i % 2),  # Alternating 4 and 5
                duration_actual=30,
                notes=f"Completion {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            completions.append(comp)

        mock_completions_backend.find_by.return_value = Result.ok(completions)

        # Get stats
        result = await completion_service.get_completion_stats(habit_uid="habit.test.1", days=30)

        # Verify
        assert result.is_ok
        stats = result.value
        assert stats["total_completions"] == 10
        assert stats["completion_rate"] > 0
        assert stats["average_quality"] == 4.5
        assert stats["high_quality_count"] == 10  # All 4 or 5

    @pytest.mark.asyncio
    async def test_get_badge_progress(
        self, completion_service, mock_habits_backend, mock_completions_backend
    ):
        """Test getting badge progress."""
        # Create habits with streaks
        habit1_dto = HabitDTO(
            uid="habit.1",
            user_uid="user_mike",  # REQUIRED - habit ownership
            title="Habit 1",
            current_streak=10,
            best_streak=15,
            total_completions=50,
            total_attempts=55,
            success_rate=0.9,
            identity_votes_cast=25,
            is_identity_habit=True,
            reinforces_identity="I am consistent",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_habits_backend.find_by.return_value = Result.ok([Habit.from_dto(habit1_dto)])

        # Create high-quality completions
        completions = []
        for i in range(15):
            comp_dto = HabitCompletionDTO(
                uid=f"hc.{i}",
                habit_uid="habit.1",
                user_uid="user_mike",
                completed_at=datetime.now() - timedelta(days=i),
                quality=5,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            completions.append(HabitCompletion.from_dto(comp_dto))

        mock_completions_backend.find_by.return_value = Result.ok(completions)

        # Get badge progress
        result = await completion_service.get_badge_progress(user_uid="user_mike")

        # Verify
        assert result.is_ok
        progress = result.value

        # Check streak badges
        assert progress["streaks"]["current_max_streak"] == 10
        assert progress["streaks"]["week_warrior"]["unlocked"] is True

        # Check completion badges
        assert progress["completions"]["total_completions"] == 50

        # Check identity badges
        assert progress["identity"]["total_identity_votes"] == 25


class TestExport:
    """Test export functionality."""

    @pytest.mark.asyncio
    async def test_export_csv(
        self, completion_service, mock_habits_backend, mock_completions_backend
    ):
        """Test CSV export."""
        # Create completions
        completions = []
        for i in range(3):
            comp = HabitCompletion(
                uid=f"hc.{i}",
                habit_uid=f"habit.{i}",
                user_uid="user_mike",
                completed_at=datetime(2025, 10, i + 1, 10, 0, 0),
                quality=4,
                duration_actual=30,
                notes=f"Note {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            completions.append(comp)

        mock_habits_backend.find_by.return_value = Result.ok(
            [_habit(f"habit.{i}") for i in range(3)]
        )
        mock_completions_backend.find_by.return_value = Result.ok(completions)

        # Export as CSV
        result = await completion_service.export_completion_history(
            user_uid="user_mike", format="csv"
        )

        # Verify
        assert result.is_ok
        csv_data = result.value
        assert "Completion ID" in csv_data
        assert "hc.0" in csv_data
        assert "habit.0" in csv_data

    @pytest.mark.asyncio
    async def test_export_json(
        self, completion_service, mock_habits_backend, mock_completions_backend
    ):
        """Test JSON export."""
        # Create completions
        completions = []
        for i in range(3):
            comp = HabitCompletion(
                uid=f"hc.{i}",
                habit_uid=f"habit.{i}",
                user_uid="user_mike",
                completed_at=datetime(2025, 10, i + 1, 10, 0, 0),
                quality=4,
                duration_actual=30,
                notes=f"Note {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            completions.append(comp)

        mock_habits_backend.find_by.return_value = Result.ok(
            [_habit(f"habit.{i}") for i in range(3)]
        )
        mock_completions_backend.find_by.return_value = Result.ok(completions)

        # Export as JSON
        result = await completion_service.export_completion_history(
            user_uid="user_mike", format="json"
        )

        # Verify
        assert result.is_ok
        json_data = result.value
        assert '"uid": "hc.0"' in json_data
        assert '"habit_uid": "habit.0"' in json_data

    @pytest.mark.asyncio
    async def test_export_invalid_format(self, completion_service, mock_completions_backend):
        """Test export with invalid format."""
        mock_completions_backend.find_by.return_value = Result.ok([])

        # Export with invalid format
        result = await completion_service.export_completion_history(
            user_uid="user_mike", format="xml"
        )

        # Verify
        assert result.is_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
