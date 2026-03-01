"""
Unit tests for ChoicesService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.choices_service import ChoicesService
from core.utils.result_simplified import Result


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
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def choices_service(mock_backend: Mock, mock_graph_intel: Mock) -> ChoicesService:
    service = ChoicesService(
        backend=mock_backend,
        graph_intelligence_service=mock_graph_intel,
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.search = AsyncMock()
    service.learning = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestChoicesServiceCreate
# ---------------------------------------------------------------------------


class TestChoicesServiceCreate:
    @pytest.mark.asyncio
    async def test_create_choice_delegates_to_core(
        self, choices_service: ChoicesService
    ) -> None:
        """create_choice delegates to core.create_choice with user_uid."""
        mock_choice = Mock()
        choices_service.core.create_choice = AsyncMock(return_value=Result.ok(mock_choice))

        request = Mock()
        user_uid = "user_test"

        await choices_service.create_choice(request, user_uid)

        choices_service.core.create_choice.assert_called_once_with(request, user_uid)

    @pytest.mark.asyncio
    async def test_make_decision_delegates_to_core_with_all_params(
        self, choices_service: ChoicesService
    ) -> None:
        """make_decision passes all params to core.make_decision."""
        mock_choice = Mock()
        choices_service.core.make_decision = AsyncMock(return_value=Result.ok(mock_choice))

        result = await choices_service.make_decision(
            choice_uid="choice_abc",
            selected_option_uid="option_xyz",
            decision_rationale="Best option given constraints",
            confidence=0.85,
        )

        assert result.is_ok
        choices_service.core.make_decision.assert_called_once_with(
            choice_uid="choice_abc",
            selected_option_uid="option_xyz",
            decision_rationale="Best option given constraints",
            confidence=0.85,
        )


# ---------------------------------------------------------------------------
# TestChoicesServiceRelationships
# ---------------------------------------------------------------------------


class TestChoicesServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_choice_to_habit_passes_reinforcement_strength(
        self, choices_service: ChoicesService
    ) -> None:
        """link_choice_to_habit passes reinforcement_strength in relationship properties."""
        choices_service.relationships.create_relationship = AsyncMock(
            return_value=Result.ok(True)
        )

        await choices_service.link_choice_to_habit(
            "choice_abc", "habit_xyz", reinforcement_strength=0.7
        )

        choices_service.relationships.create_relationship.assert_called_once_with(
            "habits",
            "choice_abc",
            "habit_xyz",
            {"reinforcement_strength": 0.7},
        )

    @pytest.mark.asyncio
    async def test_link_choice_to_principle_calls_relationships(
        self, choices_service: ChoicesService
    ) -> None:
        """link_choice_to_principle delegates to relationships.link_to_principle."""
        choices_service.relationships.link_to_principle = AsyncMock(
            return_value=Result.ok(True)
        )

        await choices_service.link_choice_to_principle(
            "choice_abc", "principle_xyz", alignment_score=0.6
        )

        choices_service.relationships.link_to_principle.assert_called_once_with(
            "choice_abc",
            "principle_xyz",
            alignment_score=0.6,
        )

    @pytest.mark.asyncio
    async def test_link_choice_to_goal_calls_relationships(
        self, choices_service: ChoicesService
    ) -> None:
        """link_choice_to_goal delegates to relationships.link_to_goal."""
        choices_service.relationships.link_to_goal = AsyncMock(
            return_value=Result.ok(True)
        )

        await choices_service.link_choice_to_goal(
            "choice_abc", "goal_xyz", contribution_score=0.4
        )

        choices_service.relationships.link_to_goal.assert_called_once_with(
            "choice_abc",
            "goal_xyz",
            contribution_score=0.4,
        )
