# mypy: disable-error-code="attr-defined"
"""
Unit tests for EventsService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.event.event_update_intent import EventUpdateIntent
from core.services.events_service import EventsService
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
    backend.get_many = AsyncMock(return_value=Result.ok([]))
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def events_service(mock_backend: Mock, mock_graph_intel: Mock) -> EventsService:
    service = EventsService(
        backend=mock_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=AsyncMock(),
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.search = AsyncMock()
    service.habits = AsyncMock()
    service.learning = AsyncMock()
    service.progress = AsyncMock()
    service.scheduling = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestEventsServiceRelationships
# ---------------------------------------------------------------------------


class TestEventsServiceRelationships:
    @pytest.mark.asyncio
    async def test_link_event_to_knowledge_converts_count_to_bool_true(
        self, events_service: EventsService
    ) -> None:
        """link_event_to_knowledge converts Result[int] → Result[bool] (True when count > 0)."""
        events_service.relationships.create_relationships_batch = AsyncMock(
            return_value=Result.ok(2)  # 2 relationships created
        )

        result = await events_service.link_event_to_knowledge(
            "event_abc", ["ku_python_xyz", "ku_math_abc"]
        )

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_link_event_to_knowledge_converts_zero_count_to_false(
        self, events_service: EventsService
    ) -> None:
        """link_event_to_knowledge returns False when no relationships were created."""
        events_service.relationships.create_relationships_batch = AsyncMock(
            return_value=Result.ok(0)  # 0 relationships created
        )

        result = await events_service.link_event_to_knowledge("event_abc", [])

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_link_event_to_knowledge_propagates_error(
        self, events_service: EventsService
    ) -> None:
        """link_event_to_knowledge propagates error from relationships sub-service."""
        events_service.relationships.create_relationships_batch = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        result = await events_service.link_event_to_knowledge("event_abc", ["ku_abc"])

        assert result.is_error


# ---------------------------------------------------------------------------
# TestUpdateEventEdges — milestone_celebration_for_goal / reinforces_habit_uid
# are single graph edges (CELEBRATES_GOAL / REINFORCES_HABIT). ADR-066 sentinel
# contract: UNSET = untouched, None = explicit clear (the picker's clear button
# → "" → None), value = set. Regression guard for the edge-clear UX gap.
# ---------------------------------------------------------------------------


class TestUpdateEventEdges:
    @pytest.mark.asyncio
    async def test_clearing_goal_edge_deletes_without_creating(
        self, events_service: EventsService
    ) -> None:
        """milestone_celebration_for_goal=None (picker-clear) must delete the existing
        CELEBRATES_GOAL edge and create no replacement — the edge-clear gap fix."""
        events_service.core.get_event = AsyncMock(return_value=Result.ok(Mock()))
        events_service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["goal_old"])
        )
        events_service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        events_service.relationships.create_relationship = AsyncMock()

        result = await events_service.update_event(
            "event_abc", EventUpdateIntent(milestone_celebration_for_goal=None)
        )

        assert result.is_ok
        events_service.relationships.delete_relationship.assert_awaited_once_with(
            "celebrated_goals", "event_abc", "goal_old"
        )
        events_service.relationships.create_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_setting_goal_edge_replaces_existing(self, events_service: EventsService) -> None:
        """A new milestone_celebration_for_goal deletes the old edge and creates the new."""
        events_service.core.get_event = AsyncMock(return_value=Result.ok(Mock()))
        events_service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["goal_old"])
        )
        events_service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        events_service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        result = await events_service.update_event(
            "event_abc", EventUpdateIntent(milestone_celebration_for_goal="goal_new")
        )

        assert result.is_ok
        events_service.relationships.delete_relationship.assert_awaited_once_with(
            "celebrated_goals", "event_abc", "goal_old"
        )
        events_service.relationships.create_relationship.assert_awaited_once_with(
            "celebrated_goals", "event_abc", "goal_new"
        )

    @pytest.mark.asyncio
    async def test_unset_edges_leave_them_untouched(self, events_service: EventsService) -> None:
        """An update that omits both edge fields (UNSET) must not touch either edge —
        no fetch, no delete, no create — even while writing node properties."""
        events_service.core.update_event = AsyncMock(return_value=Result.ok(Mock()))
        events_service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["goal_old"])
        )
        events_service.relationships.delete_relationship = AsyncMock()
        events_service.relationships.create_relationship = AsyncMock()

        result = await events_service.update_event("event_abc", EventUpdateIntent(title="New"))

        assert result.is_ok
        events_service.relationships.get_related_uids.assert_not_called()
        events_service.relationships.delete_relationship.assert_not_called()
        events_service.relationships.create_relationship.assert_not_called()
