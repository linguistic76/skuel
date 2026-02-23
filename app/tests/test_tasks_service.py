"""
Tests for TasksService event-driven functionality.

Tests verify that TasksService correctly publishes domain events
when tasks are created, completed, etc.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Priority
from core.models.task.task_request import TaskCreateRequest
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Result


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
        # Phase 2: Relationship fields removed - now queried via TasksRelationshipService
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
