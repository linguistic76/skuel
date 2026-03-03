"""
Unit tests for EventsService facade orchestration methods.

Tests focus on explicit orchestration logic — NOT pure delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
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
        graph_intelligence_service=mock_graph_intel,
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
# TestEventsServiceGoalSupport
# ---------------------------------------------------------------------------


class TestEventsServiceGoalSupport:
    @pytest.mark.asyncio
    async def test_get_events_supporting_goal_returns_empty_when_no_uids(
        self, events_service: EventsService, mock_backend: Mock
    ) -> None:
        """get_events_supporting_goal returns empty list when no related event UIDs."""
        events_service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))

        result = await events_service.get_events_supporting_goal("goal_abc", "user_test")

        assert result.is_ok
        assert result.value == []
        # backend.get_many should NOT be called
        mock_backend.get_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_events_supporting_goal_filters_by_user_uid(
        self, events_service: EventsService, mock_backend: Mock
    ) -> None:
        """get_events_supporting_goal filters events to only those owned by user."""
        events_service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["event_abc", "event_def"])
        )

        # Two events: one owned by the requesting user, one by someone else
        user_event = Mock()
        user_event.uid = "event_abc"
        user_event.user_uid = "user_test"

        other_event = Mock()
        other_event.uid = "event_def"
        other_event.user_uid = "user_other"

        mock_backend.get_many = AsyncMock(return_value=Result.ok([user_event, other_event]))

        result = await events_service.get_events_supporting_goal("goal_abc", "user_test")

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].uid == "event_abc"

    @pytest.mark.asyncio
    async def test_get_events_supporting_goal_propagates_relationship_error(
        self, events_service: EventsService
    ) -> None:
        """get_events_supporting_goal propagates error from relationships service."""
        events_service.relationships.get_related_uids = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        result = await events_service.get_events_supporting_goal("goal_abc", "user_test")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestEventsServiceStatusManagement
# ---------------------------------------------------------------------------


class TestEventsServiceStatusManagement:
    @pytest.mark.asyncio
    async def test_update_event_status_no_notes_calls_core_update_directly(
        self, events_service: EventsService
    ) -> None:
        """update_event_status with no notes/reason calls core.update without fetching event."""
        mock_event = Mock()
        events_service.core.update = AsyncMock(return_value=Result.ok(mock_event))

        request = Mock()
        request.event_uid = "event_abc"
        request.status = EntityStatus.COMPLETED
        request.notes = None
        request.cancellation_reason = None

        result = await events_service.update_event_status(request)

        assert result.is_ok
        # core.get should NOT be called (no metadata to merge)
        events_service.core.get.assert_not_called()
        events_service.core.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_event_status_with_notes_fetches_event_for_metadata_merge(
        self, events_service: EventsService
    ) -> None:
        """update_event_status with notes fetches current event to merge metadata."""
        mock_current_event = Mock()
        mock_current_event.metadata = {"existing_key": "existing_val"}
        events_service.core.get = AsyncMock(return_value=Result.ok(mock_current_event))

        mock_updated_event = Mock()
        events_service.core.update = AsyncMock(return_value=Result.ok(mock_updated_event))

        request = Mock()
        request.event_uid = "event_abc"
        request.status = EntityStatus.CANCELLED
        request.notes = "Cancelled due to conflict"
        request.cancellation_reason = None

        result = await events_service.update_event_status(request)

        assert result.is_ok
        # core.get IS called to fetch current metadata
        events_service.core.get.assert_called_once_with(request.event_uid)
        # core.update is called with merged metadata
        update_call = events_service.core.update.call_args
        updates = update_call[0][1]  # second positional arg
        assert "metadata" in updates
        assert updates["metadata"]["existing_key"] == "existing_val"
        assert updates["metadata"]["status_change_notes"] == "Cancelled due to conflict"
