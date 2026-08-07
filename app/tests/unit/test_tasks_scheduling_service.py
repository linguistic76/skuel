#!/usr/bin/env python3
# mypy: disable-error-code="list-item,dict-item"
"""
TasksSchedulingService Test Suite
==================================

Tests for scheduling and learning path integration in TasksSchedulingService.

This service handles:
- Context-aware task creation
- Learning path integration
- Task suggestions based on learning position
- Curriculum-based task creation
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.task.task_request import TaskCreateRequest
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


async def _echo_create(entity: Any) -> Result[Any]:
    """Persist by echoing the entity, as the real backend returns the created model.

    Round-trip fidelity (fields dropped by the mapper) is pinned in
    ``test_task_create_edges.py``; this suite is about the scheduling flows.
    """
    return Result.ok(entity)


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend."""
    backend = Mock()
    backend.create = AsyncMock(side_effect=_echo_create)
    backend.create_task = AsyncMock()
    # Default: No relationships found (empty lists)
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    backend.create_relationships_batch = AsyncMock(
        return_value=Result.ok(0)
    )  # Batch relationship creation
    # Admission guard reads (keep_permitted_link_edges): every UID resolves, is owned
    # by nobody (shared → linkable), and carries every label the link fields accept.
    backend.get_owner_uids_batch = AsyncMock(return_value=Result.ok({}))

    async def _all_labels(uids: Any) -> Result[dict[str, list[str]]]:
        return Result.ok({uid: ["Entity", "Habit", "Ku", "Principle", "Task"] for uid in uids})

    backend.get_node_labels_batch = AsyncMock(side_effect=_all_labels)
    return backend


@pytest.fixture
def core_service(mock_backend) -> TasksCoreService:
    """THE create primitive both scheduling doors delegate to."""
    return TasksCoreService(backend=mock_backend, event_bus=None)


@pytest.fixture
def scheduling_service(mock_backend, core_service) -> TasksSchedulingService:
    """Create TasksSchedulingService instance."""
    return TasksSchedulingService(backend=mock_backend, core=core_service)


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user_123",
        username="test_user",
        prerequisites_completed={"ku.python.basics", "ku.git.basics"},
        completed_task_uids={"task:completed_1"},
        active_goal_uids={"goal:learn_python"},
        active_habit_uids={"habit:daily_code"},
    )


@pytest.fixture
def task_request() -> TaskCreateRequest:
    """Create sample task creation request."""
    return TaskCreateRequest(
        title="Practice async programming",
        priority=Priority.MEDIUM,
        due_date=date.today() + timedelta(days=7),
        duration_minutes=90,
        project="Python Learning",
        tags=["learning", "python"],
        prerequisite_knowledge_uids=["ku.python.basics"],
        applies_knowledge_uids=["ku.python.async"],
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


def test_init_with_backend(mock_backend, core_service):
    """Test service initialization with required backend."""
    service = TasksSchedulingService(backend=mock_backend, core=core_service)
    assert service.backend == mock_backend
    assert service.core is core_service


def test_init_without_backend():
    """Test service initialization fails without backend."""
    with pytest.raises(ValueError, match=r"tasks\.scheduling backend is REQUIRED"):
        TasksSchedulingService(backend=None, core=Mock())


# ============================================================================
# CONTEXT-AWARE CREATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_with_context_success(
    scheduling_service, mock_backend, task_request, user_context
):
    """Test successful context-aware task creation.

    Runs through TasksCoreService.create_task (THE create primitive), so the persist
    lands on backend.create and the request's link lists go out as guarded edges —
    the wiring itself is pinned in test_task_create_edges.py.
    """
    result = await scheduling_service.create_task_with_context(task_request, user_context)

    # Verify
    assert result.is_ok
    task = result.value
    assert task.title == task_request.title
    mock_backend.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_task_with_context_missing_knowledge_prerequisites(
    scheduling_service, task_request, user_context
):
    """Test task creation fails when knowledge prerequisites are missing."""
    # Setup - request requires knowledge user doesn't have
    task_request.prerequisite_knowledge_uids = ["ku.python.async", "ku.python.advanced"]

    # Execute
    result = await scheduling_service.create_task_with_context(task_request, user_context)

    # Verify
    assert result.is_error  # Should fail validation


@pytest.mark.asyncio
async def test_create_task_with_context_incomplete_task_prerequisites(
    scheduling_service, task_request, user_context
):
    """Test task creation fails when task prerequisites are incomplete."""
    # Setup - request requires incomplete tasks
    task_request.prerequisite_task_uids = ["task:123", "task:456"]

    # Execute
    result = await scheduling_service.create_task_with_context(task_request, user_context)

    # Verify
    assert result.is_error  # Should fail validation


# ============================================================================
# CURRICULUM-BASED TASK CREATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_from_path_step(scheduling_service, mock_backend):
    """Test creating a task from a path step."""
    result = await scheduling_service.create_task_from_path_step(
        step_uid="ps:python_fundamentals",
        task_title="Practice Python fundamentals",
        knowledge_uids=["ku.python.basics"],
        user_uid="user_123",
    )

    # Verify
    assert result.is_ok
    task = result.value
    assert task.source_path_step_uid == "ps:python_fundamentals"
    assert task.knowledge_mastery_check is True
    assert task.status == EntityStatus.DRAFT
    assert task.priority == Priority.MEDIUM
    # applies_knowledge_uids removed - query via UnifiedRelationshipService


@pytest.mark.asyncio
async def test_create_curriculum_task_backend_error(scheduling_service, mock_backend):
    """Test curriculum task creation with backend error."""
    # The primitive's persist seam is backend.create; a failure there propagates.
    mock_backend.create = AsyncMock(
        return_value=Result.fail(Errors.database("create_task", "Database error"))
    )

    # Execute
    result = await scheduling_service.create_task_from_path_step(
        step_uid="ps:test", task_title="Test Task", knowledge_uids=["ku.test"], user_uid="user_123"
    )

    # Verify
    assert result.is_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
