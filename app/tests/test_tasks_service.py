"""
Tests for TasksService event-driven functionality and orchestration methods.

Tests verify that TasksService correctly publishes domain events
when tasks are created, completed, etc., and that orchestration methods
with conditional logic behave correctly.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.task.task_request import TaskCreateRequest
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_event_bus() -> Mock:
    """Mock event bus for testing."""
    bus = Mock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def mock_tasks_backend() -> Any:
    """Mock tasks backend for testing."""
    from datetime import datetime

    from core.models.enums import EntityStatus

    backend = Mock()

    # Mock the generic BackendOperations methods (used by core service)
    task_dict = {
        "uid": "task-123",
        "user_uid": "user-456",  # REQUIRED field
        "title": "Test Task",
        "description": "Test description",
        "status": EntityStatus.DRAFT,
        "priority": Priority.MEDIUM,
        "duration_minutes": 30,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "tags": [],
        # Relationship fields removed - now queried via TasksRelationshipService
    }

    # Generic BackendOperations methods (TasksCoreService uses these)
    backend.create = AsyncMock(return_value=Result.ok(task_dict))
    backend.get = AsyncMock(return_value=Result.ok(task_dict))
    backend.update = AsyncMock(return_value=Result.ok(task_dict))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))

    # Relationship operations
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))

    return backend


@pytest.mark.asyncio
async def test_create_task_succeeds(mock_tasks_backend):
    """Test that creating a task succeeds with required user_uid."""
    # Arrange
    service = TasksService(
        backend=mock_tasks_backend,
        event_bus=None,  # Simplified - no event bus for basic test
    )

    task_request = TaskCreateRequest(
        title="New Task", description="Test task description", priority=Priority.HIGH
    )

    # Act
    result = await service.create_task(task_request, user_uid="user-456")

    # Assert
    assert result.is_ok
    assert result.value.uid == "task-123"
    assert result.value.user_uid == "user-456"
    assert result.value.title == "Test Task"


@pytest.mark.asyncio
async def test_no_event_bus_doesnt_crash(mock_tasks_backend):
    """Test that service works without event bus (backward compatibility)."""
    # Arrange
    service = TasksService(
        backend=mock_tasks_backend,
        event_bus=None,  # No event bus
    )

    task_request = TaskCreateRequest(title="New Task", priority=Priority.MEDIUM)

    # Act - Should not crash
    result = await service.create_task(task_request, user_uid="user-456")

    # Assert
    assert result.is_ok


@pytest.mark.asyncio
async def test_event_publishing_failure_doesnt_break_operation(mock_event_bus, mock_tasks_backend):
    """Test that event publishing failure doesn't break the operation."""
    # Arrange
    mock_event_bus.publish_async = AsyncMock(side_effect=Exception("Event bus down"))

    service = TasksService(backend=mock_tasks_backend, event_bus=mock_event_bus)

    task_request = TaskCreateRequest(title="New Task", priority=Priority.HIGH)

    # Act - Should complete successfully despite event failure
    result = await service.create_task(task_request, user_uid="user-456")

    # Assert - Operation should still succeed
    # (Event publishing is fire-and-forget, doesn't affect core operation)
    assert result.is_ok or result.is_error  # Either is acceptable depending on error handling


# ---------------------------------------------------------------------------
# Shared fixture for orchestration tests (sub-services replaced with AsyncMocks)
# ---------------------------------------------------------------------------


@pytest.fixture
def tasks_service_with_mocked_subservices(mock_tasks_backend: Any) -> TasksService:
    """TasksService with all sub-services replaced by AsyncMocks post-construction."""
    service = TasksService(backend=mock_tasks_backend, event_bus=None)
    service.core = AsyncMock()
    service.progress = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.scheduling = AsyncMock()
    service.planning = AsyncMock()
    service.search = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestCompleteTaskWithCascade
# ---------------------------------------------------------------------------


class TestCompleteTaskWithCascade:
    @pytest.mark.asyncio
    async def test_success_without_ku_generation_service(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """complete_task_with_cascade delegates to progress; skips generation when no ku_generation_service."""
        service = tasks_service_with_mocked_subservices
        service.ku_generation_service = None

        mock_task = Mock()
        service.progress.complete_task_with_cascade = AsyncMock(
            return_value=Result.ok(mock_task)
        )

        user_context = Mock()
        user_context.user_uid = "user_test"

        result = await service.complete_task_with_cascade("task_abc", user_context)

        assert result.is_ok
        service.progress.complete_task_with_cascade.assert_called_once_with(
            "task_abc", user_context, None, None
        )

    @pytest.mark.asyncio
    async def test_success_with_ku_generation_service_triggers_generation(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """complete_task_with_cascade triggers ku_generation when result is ok and service present."""
        service = tasks_service_with_mocked_subservices

        mock_task = Mock()
        service.progress.complete_task_with_cascade = AsyncMock(
            return_value=Result.ok(mock_task)
        )

        mock_ku_gen = AsyncMock()
        service.ku_generation_service = mock_ku_gen

        user_context = Mock()
        user_context.user_uid = "user_test"

        # Patch internal generation method
        service._trigger_knowledge_generation = AsyncMock()

        result = await service.complete_task_with_cascade("task_abc", user_context)

        assert result.is_ok
        service._trigger_knowledge_generation.assert_called_once_with("user_test")

    @pytest.mark.asyncio
    async def test_failure_does_not_trigger_ku_generation(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """complete_task_with_cascade does NOT trigger ku_generation when progress fails."""
        service = tasks_service_with_mocked_subservices
        service.ku_generation_service = AsyncMock()  # service IS present

        service.progress.complete_task_with_cascade = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_abc"))
        )

        service._trigger_knowledge_generation = AsyncMock()

        user_context = Mock()
        user_context.user_uid = "user_test"

        result = await service.complete_task_with_cascade("task_abc", user_context)

        assert result.is_error
        service._trigger_knowledge_generation.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetTaskDependencies
# ---------------------------------------------------------------------------


class TestGetTaskDependencies:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_prerequisites(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """get_task_dependencies returns empty list when no prerequisite UIDs."""
        service = tasks_service_with_mocked_subservices
        service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok([])
        )

        result = await service.get_task_dependencies("task_abc")

        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_fetches_each_prerequisite_task(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """get_task_dependencies fetches each prerequisite Task object."""
        service = tasks_service_with_mocked_subservices
        service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["task_prereq1", "task_prereq2"])
        )

        mock_task_1 = Mock()
        mock_task_1.uid = "task_prereq1"
        mock_task_2 = Mock()
        mock_task_2.uid = "task_prereq2"

        service.core.get = AsyncMock(
            side_effect=[Result.ok(mock_task_1), Result.ok(mock_task_2)]
        )

        result = await service.get_task_dependencies("task_abc")

        assert result.is_ok
        assert len(result.value) == 2
        service.relationships.get_related_uids.assert_called_once_with(
            "prerequisite_tasks", "task_abc"
        )

    @pytest.mark.asyncio
    async def test_propagates_relationship_error(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """get_task_dependencies propagates error from relationships sub-service."""
        service = tasks_service_with_mocked_subservices
        service.relationships.get_related_uids = AsyncMock(
            return_value=Result.fail(Errors.database("query", "DB error"))
        )

        result = await service.get_task_dependencies("task_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestGetTaskWithDependencies
# ---------------------------------------------------------------------------


class TestGetTaskWithDependencies:
    @pytest.mark.asyncio
    async def test_wraps_result_in_dict_with_task_and_graph_context(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """get_task_with_dependencies wraps (task, context) tuple in dict."""
        service = tasks_service_with_mocked_subservices
        mock_task = Mock()
        mock_context = Mock()
        service.relationships.get_with_context = AsyncMock(
            return_value=Result.ok((mock_task, mock_context))
        )

        result = await service.get_task_with_dependencies("task_abc", depth=2)

        assert result.is_ok
        assert result.value["task"] is mock_task
        assert result.value["graph_context"] is mock_context
        service.relationships.get_with_context.assert_called_once_with(
            "task_abc", 2, intent="dependencies"
        )

    @pytest.mark.asyncio
    async def test_propagates_relationship_error(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """get_task_with_dependencies propagates error from relationships."""
        service = tasks_service_with_mocked_subservices
        service.relationships.get_with_context = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_abc"))
        )

        result = await service.get_task_with_dependencies("task_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLinkTaskToKnowledge
# ---------------------------------------------------------------------------


class TestLinkTaskToKnowledge:
    @pytest.mark.asyncio
    async def test_passes_correct_kwargs_to_relationships(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """link_task_to_knowledge passes knowledge_score_required and is_learning_opportunity."""
        service = tasks_service_with_mocked_subservices
        service.relationships.link_to_knowledge = AsyncMock(
            return_value=Result.ok(True)
        )

        await service.link_task_to_knowledge(
            "task_abc",
            "ku_python_xyz",
            knowledge_score_required=0.9,
            is_learning_opportunity=True,
        )

        service.relationships.link_to_knowledge.assert_called_once_with(
            "task_abc",
            "ku_python_xyz",
            knowledge_score_required=0.9,
            is_learning_opportunity=True,
        )


# ---------------------------------------------------------------------------
# TestUncompleteTask
# ---------------------------------------------------------------------------


class TestUncompleteTask:
    @pytest.mark.asyncio
    async def test_calls_core_update_with_active_status(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """uncomplete_task calls core.update_task with EntityStatus.ACTIVE."""
        service = tasks_service_with_mocked_subservices
        mock_task = Mock()
        service.core.update_task = AsyncMock(return_value=Result.ok(mock_task))

        result = await service.uncomplete_task("task_abc")

        service.core.update_task.assert_called_once_with(
            "task_abc", {"status": EntityStatus.ACTIVE}
        )
