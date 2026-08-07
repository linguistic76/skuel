# mypy: disable-error-code="attr-defined"
"""
Unit tests for HabitsService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.services.habits_service import HabitsService
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_completions_backend() -> Mock:
    backend = Mock()
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    return backend


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def habits_service(
    mock_backend: Mock, mock_completions_backend: Mock, mock_graph_intel: Mock
) -> HabitsService:
    service = HabitsService(
        backend=mock_backend,
        graph_intel=mock_graph_intel,
        completions_backend=mock_completions_backend,
        cross_domain_query=AsyncMock(),
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.progress = AsyncMock()
    service.learning = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.scheduling = AsyncMock()
    service.planning = AsyncMock()
    service.completions = AsyncMock()
    service.achievements = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestHabitsServiceCompletion
# ---------------------------------------------------------------------------


class TestHabitsServiceCompletion:
    @pytest.mark.asyncio
    async def test_track_habit_returns_not_found_when_habit_missing(
        self, habits_service: HabitsService
    ) -> None:
        """track_habit returns not_found error when habit doesn't exist."""
        habits_service.core.get_habit = AsyncMock(return_value=Result.ok(None))

        request = Mock()
        request.habit_uid = "habit_missing"
        request.completion_date = None
        request.value = None
        request.notes = None

        result = await habits_service.track_habit(request)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_track_habit_propagates_core_error(self, habits_service: HabitsService) -> None:
        """track_habit propagates error when core.get_habit fails."""
        habits_service.core.get_habit = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        request = Mock()
        request.habit_uid = "habit_abc"
        request.completion_date = None
        request.value = None
        request.notes = None

        result = await habits_service.track_habit(request)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_track_habit_success_calls_completions_record(
        self, habits_service: HabitsService
    ) -> None:
        """track_habit calls completions.record_completion when habit found."""
        mock_habit = Mock()
        mock_habit.uid = "habit_abc"
        mock_habit.user_uid = "user_test"
        habits_service.core.get_habit = AsyncMock(return_value=Result.ok(mock_habit))
        habits_service.completions.record_completion = AsyncMock(return_value=Result.ok(Mock()))

        request = Mock()
        request.habit_uid = "habit_abc"
        request.completion_date = None  # Will default to now
        request.value = 0.9
        request.notes = "Great session"

        await habits_service.track_habit(request)

        habits_service.completions.record_completion.assert_called_once()
        call_kwargs = habits_service.completions.record_completion.call_args
        assert call_kwargs.kwargs["habit_uid"] == "habit_abc"
        assert call_kwargs.kwargs["user_uid"] == "user_test"
        assert isinstance(call_kwargs.kwargs["completed_at"], datetime)


# ---------------------------------------------------------------------------
# TestHabitsServiceOrchestration
# ---------------------------------------------------------------------------


class TestHabitsServiceOrchestration:
    @pytest.mark.asyncio
    async def test_create_habit_with_context_creates_via_core_primitive(
        self, habits_service: HabitsService
    ) -> None:
        """create_habit_with_context creates via core.create_habit — THE create
        primitive (events, guarded link edges). The create step used to run through
        the learning bridge's dict-based create, which persisted a corrupt uid-less
        node and then errored (deleted 2026-08-06)."""
        mock_habit = Mock()
        mock_habit.uid = "habit_abc"
        habits_service.core.create_habit = AsyncMock(return_value=Result.ok(mock_habit))

        habit_data = Mock()
        habit_data.linked_goal_uids = None
        habit_data.linked_knowledge_uids = None

        user_context = Mock()
        user_context.active_goal_uids = set()
        user_context.user_uid = "user_test"

        result = await habits_service.create_habit_with_context(habit_data, user_context)

        assert result.is_ok
        habits_service.core.create_habit.assert_called_once_with(habit_data, "user_test")

    @pytest.mark.asyncio
    async def test_create_habit_with_context_propagates_create_error(
        self, habits_service: HabitsService
    ) -> None:
        """create_habit_with_context propagates error from the create primitive."""
        habits_service.core.create_habit = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        habit_data = Mock()
        habit_data.linked_goal_uids = None
        habit_data.linked_knowledge_uids = None

        user_context = Mock()
        user_context.active_goal_uids = set()
        user_context.user_uid = "user_test"

        result = await habits_service.create_habit_with_context(habit_data, user_context)

        assert result.is_error


# ---------------------------------------------------------------------------
# TestHabitsServiceRelationships
# ---------------------------------------------------------------------------


class TestHabitsServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_habit_to_knowledge_passes_skill_params(
        self, habits_service: HabitsService
    ) -> None:
        """link_habit_to_knowledge writes the REINFORCES_KNOWLEDGE ('knowledge') edge."""
        habits_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        await habits_service.link_habit_to_knowledge(
            "habit_abc",
            "ku_python_xyz",
            skill_level="intermediate",
            proficiency_gain_rate=0.2,
        )

        habits_service.relationships.create_relationship.assert_called_once_with(
            "knowledge",
            "habit_abc",
            "ku_python_xyz",
            {"skill_level": "intermediate", "proficiency_gain_rate": 0.2},
        )

    @pytest.mark.asyncio
    async def test_link_habit_to_principle_passes_embodiment_strength(
        self, habits_service: HabitsService
    ) -> None:
        """link_habit_to_principle writes the EMBODIES_PRINCIPLE ('principles') edge."""
        habits_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        await habits_service.link_habit_to_principle(
            "habit_abc", "principle_xyz", embodiment_strength=0.8
        )

        habits_service.relationships.create_relationship.assert_called_once_with(
            "principles",
            "habit_abc",
            "principle_xyz",
            {"embodiment_strength": 0.8},
        )
