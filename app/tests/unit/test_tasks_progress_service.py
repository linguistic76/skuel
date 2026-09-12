#!/usr/bin/env python3
"""
TasksProgressService Test Suite
================================

Prerequisite validation, unblocking and assignment. Completion is not here: the
one completion door is ``TasksCoreService.update_task`` (pinned in
``tests/unit/services/tasks/test_task_completed_publishers.py``), and dependent
scheduling is a ``TaskCompleted`` subscriber
(``tests/unit/services/tasks/test_task_dependency_scheduling.py``).
"""

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.services.tasks.tasks_progress_service import TasksProgressService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result
from tests.helpers.status_guarded_backend import (
    echoing_guarded_write,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend."""
    backend = Mock()

    # Default task data for get_task - None means not found
    default_task_dict = {
        "uid": "task:123",
        "user_uid": "user_123",
        "title": "Test Task",
        "status": EntityStatus.ACTIVE.value,
        "priority": Priority.MEDIUM.value,
        "due_date": None,  # No due date by default
        "created_at": datetime.now(),
    }

    backend.get = AsyncMock(return_value=Result.ok(default_task_dict))
    backend.update = AsyncMock()
    # The completion doors write through the ADR-087 primitive, answered here from
    # whatever ``get``/``update`` are currently configured to return (see the helper).
    backend.update_with_status_guard = echoing_guarded_write(backend)
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    # Default: No relationships found (empty lists)
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    backend.add_relationship = AsyncMock(return_value=Result.ok(True))
    return backend


@pytest.fixture
def mock_context_service() -> Any:
    """Create a mock user context service."""
    service = Mock()
    service.invalidate_context = AsyncMock()
    return service


@pytest.fixture
def progress_service(mock_backend) -> TasksProgressService:
    """Create TasksProgressService instance."""
    return TasksProgressService(backend=mock_backend)


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task."""
    return Task.from_dto(
        TaskDTO(
            uid="task:123",
            user_uid="user_demo",
            title="Test Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.ACTIVE.value,
            fulfills_goal_uid="goal:learn_python",
            goal_progress_contribution=0.2,
            completion_updates_goal=True,
            knowledge_mastery_check=True,
            created_at=datetime.now(),
        )
    )


@pytest.fixture
def blocked_task() -> Task:
    """Create a task with prerequisites."""
    return Task.from_dto(
        TaskDTO(
            uid="task:blocked",
            user_uid="user_demo",
            title="Blocked Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.DRAFT.value,
            created_at=datetime.now(),
        )
    )


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user_123",
        username="test_user",
        prerequisites_completed={"ku.python.basics"},
        completed_task_uids={"task:completed_1"},
        active_goal_uids={"goal:learn_python"},
        active_habit_uids={"habit:daily_code"},
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


def test_init_with_backend(mock_backend):
    """Test service initialization with required backend."""
    service = TasksProgressService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    """Test service initialization fails without backend."""
    with pytest.raises(ValueError, match=r"tasks\.progress backend is REQUIRED"):
        TasksProgressService(backend=None)


# ============================================================================
# TASK COMPLETION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_prerequisites_met(progress_service, mock_backend, sample_task, user_context):
    """Test prerequisite check when all prerequisites are met."""
    # Setup - task with no prerequisites
    simple_task = Task.from_dto(
        TaskDTO(
            uid="task:simple",
            user_uid="user_demo",
            title="Simple Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.DRAFT.value,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(simple_task.to_dto().to_dict())

    # Execute
    result = await progress_service.check_prerequisites("task:simple", user_context)

    # Verify
    assert result.is_ok
    prereq_status = result.value
    assert prereq_status["can_start"] is True
    assert len(prereq_status["missing_knowledge"]) == 0
    assert len(prereq_status["incomplete_tasks"]) == 0


@pytest.mark.asyncio
async def test_check_prerequisites_missing_knowledge(
    progress_service, mock_backend, blocked_task, user_context
):
    """Test prerequisite check when knowledge prerequisites are missing."""
    # Setup
    mock_backend.get.return_value = Result.ok(blocked_task.to_dto().to_dict())

    # Mock prerequisite knowledge relationships (user doesn't have ku.python.async)
    async def mock_get_related(uid, rel_type, direction):
        if rel_type == "REQUIRES_KNOWLEDGE":
            return Result.ok(["ku.python.async"])
        return Result.ok([])

    mock_backend.get_related_uids = AsyncMock(side_effect=mock_get_related)

    # Execute
    result = await progress_service.check_prerequisites("task:blocked", user_context)

    # Verify
    assert result.is_ok
    prereq_status = result.value
    assert prereq_status["can_start"] is False
    assert "ku.python.async" in prereq_status["missing_knowledge"]


@pytest.mark.asyncio
async def test_check_prerequisites_incomplete_tasks(
    progress_service, mock_backend, blocked_task, user_context
):
    """Test prerequisite check when task prerequisites are incomplete."""
    # Setup
    mock_backend.get.return_value = Result.ok(blocked_task.to_dto().to_dict())

    # Mock prerequisite task relationships (user hasn't completed task:123)
    async def mock_get_related(uid, rel_type, direction):
        if rel_type == "BLOCKED_BY":
            return Result.ok(["task:123"])
        return Result.ok([])

    mock_backend.get_related_uids = AsyncMock(side_effect=mock_get_related)

    # Execute
    result = await progress_service.check_prerequisites("task:blocked", user_context)

    # Verify
    assert result.is_ok
    prereq_status = result.value
    assert prereq_status["can_start"] is False
    assert "task:123" in prereq_status["incomplete_tasks"]


# ============================================================================
# TASK UNBLOCKING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unblock_task_if_ready_success(progress_service, mock_backend):
    """Test unblocking a task when prerequisites are met."""
    # Setup - task with all prerequisites met
    ready_task = Task.from_dto(
        TaskDTO(
            uid="task:ready",
            user_uid="user_demo",
            title="Ready Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.DRAFT.value,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(ready_task.to_dto().to_dict())

    # Mock successful prerequisite check
    with patch.object(
        progress_service,
        "check_prerequisites",
        return_value=Result.ok(
            {"can_start": True, "missing_knowledge": [], "incomplete_tasks": []}
        ),
    ):
        # Setup unblocked task
        unblocked_dto = ready_task.to_dto()
        unblocked_dto.status = EntityStatus.SCHEDULED
        mock_backend.update.return_value = Result.ok(unblocked_dto.to_dict())

        # Create mock context
        context = UserContext(
            user_uid="user_123",
            username="test_user",
            prerequisites_completed=set(),
            completed_task_uids=set(),
        )

        # Execute
        result = await progress_service.unblock_task_if_ready("task:ready", context)

        # Verify
        assert result.is_ok
        assert result.value is not None
        assert result.value.status == EntityStatus.SCHEDULED


@pytest.mark.asyncio
async def test_unblock_refuses_to_resurrect_a_finished_task(progress_service, mock_backend):
    """A COMPLETED task is not unblocked, and its ``completion_date`` is not stranded.

    Unblocking writes ``status=scheduled`` with no domain rule of its own behind it, so
    before ADR-087 PR-4 a task that finished while its prerequisites were being checked
    would have been dragged back out of COMPLETED with its stamp left behind — breaking
    the invariant that the stamp is non-null exactly when the task is completed. The
    terminal set is a ``refuse_if_prior_in`` on the write, so it is decided against the
    status the node holds, not the one the prerequisite check saw.
    """
    finished_task = Task.from_dto(
        TaskDTO(
            uid="task:finished",
            user_uid="user_demo",
            title="Finished Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.COMPLETED.value,
            completion_date=date(2026, 4, 2),
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(finished_task.to_dto().to_dict())
    mock_backend.update.return_value = Result.ok(finished_task.to_dto().to_dict())

    with patch.object(
        progress_service,
        "check_prerequisites",
        return_value=Result.ok(
            {"can_start": True, "missing_knowledge": [], "incomplete_tasks": []}
        ),
    ):
        context = UserContext(
            user_uid="user_123",
            username="test_user",
            prerequisites_completed=set(),
            completed_task_uids=set(),
        )

        result = await progress_service.unblock_task_if_ready("task:finished", context)

    assert result.is_ok
    assert result.value is None, "a finished task was reported as freshly unblocked"

    _uid, _updates, guard = mock_backend.update_with_status_guard.await_args.args
    assert EntityStatus.COMPLETED.value in guard.refuse_if_prior_in
    # Every terminal status, not COMPLETED alone — cancelled / failed / archived tasks
    # are equally not this door's to resurrect.
    assert guard.refuse_if_prior_in == frozenset(
        status.value for status in EntityStatus if status.is_terminal()
    )


@pytest.mark.asyncio
async def test_unblock_task_still_blocked(progress_service, mock_backend, blocked_task):
    """Test unblocking when task is still blocked."""
    # Setup
    mock_backend.get.return_value = Result.ok(blocked_task.to_dto().to_dict())

    # Mock failed prerequisite check
    with patch.object(
        progress_service,
        "check_prerequisites",
        return_value=Result.ok(
            {
                "can_start": False,
                "missing_knowledge": ["ku.python.async"],
                "incomplete_tasks": ["task:123"],
            }
        ),
    ):
        context = UserContext(
            user_uid="user_123",
            username="test_user",
            prerequisites_completed=set(),
            completed_task_uids=set(),
        )

        # Execute
        result = await progress_service.unblock_task_if_ready("task:blocked", context)

        # Verify
        assert result.is_ok
        assert result.value is None  # Still blocked


# ============================================================================
# TASK ASSIGNMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_assign_task_to_user_success(progress_service, mock_backend):
    """Test successful task assignment to user."""
    # Setup
    mock_backend.assign_task_to_user.return_value = Result.ok(True)

    # Execute
    result = await progress_service.assign_task_to_user(
        task_uid="task:123",
        user_uid="user_456",
        assigned_by="user_admin",
        priority_override=Priority.HIGH.value,
    )

    # Verify
    assert result.is_ok
    assert result.value is True
    # Note: Service now uses graph relationships (add_relationship) instead of
    # specific backend methods (assign_task_to_user)


@pytest.mark.asyncio
async def test_assign_task_backend_error(progress_service, mock_backend):
    """Test task assignment with backend error."""
    # Setup
    # Service now uses add_relationship instead of specific backend methods
    mock_backend.add_relationship.return_value = Result.fail(
        Errors.database("add_relationship", "Assignment failed")
    )

    # Execute
    result = await progress_service.assign_task_to_user("task:123", "user_456")

    # Verify
    assert result.is_error


# ============================================================================
# CASCADE EFFECT TESTS
# ============================================================================
