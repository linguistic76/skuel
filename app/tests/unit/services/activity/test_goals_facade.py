# mypy: disable-error-code="attr-defined"
"""
Unit tests for GoalsService facade orchestration methods.

Tests focus on explicit orchestration logic (conditional checks, multi-step
sequencing, cross-sub-service coordination) — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.goals_service import GoalsService
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
    # GoalsService uses backend.get_goal in generate_tasks_for_goal
    backend.get_goal = AsyncMock(return_value=Result.ok({}))
    return backend


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def goals_service(mock_backend: Mock, mock_graph_intel: Mock) -> GoalsService:
    service = GoalsService(
        backend=mock_backend,
        graph_intel=mock_graph_intel,
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
    service.recommendations = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestGoalsServiceCreate
# ---------------------------------------------------------------------------


class TestGoalsServiceCreate:
    @pytest.mark.asyncio
    async def test_create_goal_delegates_to_core(self, goals_service: GoalsService) -> None:
        """create_goal delegates to core sub-service."""
        goals_service.core.create_goal = AsyncMock(return_value=Result.ok(Mock()))
        request = Mock()
        user_uid = "user_test"

        await goals_service.create_goal(request, user_uid)

        goals_service.core.create_goal.assert_called_once()


# ---------------------------------------------------------------------------
# TestGoalsServiceOrchestration
# ---------------------------------------------------------------------------


class TestGoalsServiceOrchestration:
    @pytest.mark.asyncio
    async def test_create_goal_with_context_no_prereqs_calls_core_primitive(
        self, goals_service: GoalsService
    ) -> None:
        """create_goal_with_context with no prereqs creates via core.create_goal —
        THE create primitive (events, guarded link edges). The create step used to
        run through the learning bridge's dict-based create, which persisted a
        corrupt uid-less node and then errored (deleted 2026-08-06)."""
        mock_goal = Mock()
        mock_goal.uid = "goal_abc"
        goals_service.core.create_goal = AsyncMock(return_value=Result.ok(mock_goal))

        goal_data = Mock()
        goal_data.required_knowledge_uids = None
        goal_data.supporting_habit_uids = None

        user_context = Mock()
        user_context.mastered_knowledge_uids = set()
        user_context.active_habit_uids = set()
        user_context.user_uid = "user_test"

        result = await goals_service.create_goal_with_context(goal_data, user_context)

        assert result.is_ok
        goals_service.core.create_goal.assert_called_once_with(goal_data, "user_test")

    @pytest.mark.asyncio
    async def test_create_goal_with_context_missing_prereqs_fails_validation(
        self, goals_service: GoalsService
    ) -> None:
        """create_goal_with_context fails when required knowledge not mastered."""
        goal_data = Mock()
        goal_data.required_knowledge_uids = ["ku_python_abc123", "ku_math_def456"]
        goal_data.supporting_habit_uids = None

        user_context = Mock()
        user_context.mastered_knowledge_uids = {"ku_python_abc123"}  # missing ku_math
        user_context.active_habit_uids = set()

        result = await goals_service.create_goal_with_context(goal_data, user_context)

        assert result.is_error
        # The create primitive should NOT be reached
        goals_service.core.create_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_goal_with_context_inactive_habit_fails_validation(
        self, goals_service: GoalsService
    ) -> None:
        """create_goal_with_context fails when supporting habit is inactive."""
        goal_data = Mock()
        goal_data.required_knowledge_uids = None
        goal_data.supporting_habit_uids = ["habit_yoga_abc"]

        user_context = Mock()
        user_context.mastered_knowledge_uids = set()
        user_context.active_habit_uids = set()  # habit not active

        result = await goals_service.create_goal_with_context(goal_data, user_context)

        assert result.is_error
        goals_service.core.create_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_goal_with_context_propagates_create_error(
        self, goals_service: GoalsService
    ) -> None:
        """create_goal_with_context propagates failure from the create primitive."""
        goals_service.core.create_goal = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        goal_data = Mock()
        goal_data.required_knowledge_uids = None
        goal_data.supporting_habit_uids = None

        user_context = Mock()
        user_context.mastered_knowledge_uids = set()
        user_context.active_habit_uids = set()
        user_context.user_uid = "user_test"

        result = await goals_service.create_goal_with_context(goal_data, user_context)

        assert result.is_error


# ---------------------------------------------------------------------------
# TestGoalsServiceRelationships
# ---------------------------------------------------------------------------


class TestGoalsServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_goal_to_habit_passes_weight_and_essentiality(
        self, goals_service: GoalsService
    ) -> None:
        """link_goal_to_habit writes the SUPPORTS_GOAL edge with weight + essentiality tier.

        The essentiality property (not the former ``contribution_type``) is THE key the
        GOAPS_CONFIG tier mappings filter on — see test_goal_habit_essentiality.py.
        """
        goals_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        result = await goals_service.link_goal_to_habit(
            "goal_abc", "habit_xyz", weight=0.7, essentiality="essential"
        )

        assert result.is_ok
        goals_service.relationships.create_relationship.assert_called_once_with(
            "supporting_habits",
            "goal_abc",
            "habit_xyz",
            {"weight": 0.7, "essentiality": "essential"},
        )

    @pytest.mark.asyncio
    async def test_link_goal_to_knowledge_passes_proficiency_params(
        self, goals_service: GoalsService
    ) -> None:
        """link_goal_to_knowledge writes the REQUIRES_KNOWLEDGE ('knowledge') edge with props."""
        goals_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        await goals_service.link_goal_to_knowledge(
            "goal_abc", "ku_python_abc", proficiency_required="advanced", priority=2
        )

        goals_service.relationships.create_relationship.assert_called_once_with(
            "knowledge",
            "goal_abc",
            "ku_python_abc",
            {"proficiency_required": "advanced", "priority": 2},
        )

    @pytest.mark.asyncio
    async def test_link_goal_to_principle_passes_alignment_strength(
        self, goals_service: GoalsService
    ) -> None:
        """link_goal_to_principle writes the GUIDED_BY_PRINCIPLE ('principles') edge."""
        goals_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        await goals_service.link_goal_to_principle(
            "goal_abc", "principle_xyz", alignment_strength=0.9
        )

        goals_service.relationships.create_relationship.assert_called_once_with(
            "principles",
            "goal_abc",
            "principle_xyz",
            {"alignment_strength": 0.9},
        )
