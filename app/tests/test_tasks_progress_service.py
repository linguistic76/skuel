#!/usr/bin/env python3
"""
TasksProgressService Test Suite
================================

Tests for progress tracking and completion operations in TasksProgressService.

This service handles:
- Task completion with cascading effects
- Prerequisite validation
- Task unblocking
- Task assignment to users
- Progress recording
"""

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.models.enums import KuStatus, Priority
from core.models.ku.ku import Ku as Task
from core.models.ku.ku_dto import KuDTO as TaskDTO
from core.services.tasks.tasks_progress_service import TasksProgressService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

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
        "user_uid": "user:123",
        "title": "Test Task",
        "status": KuStatus.ACTIVE.value,
        "priority": Priority.MEDIUM.value,
        "due_date": None,  # No due date by default
        "created_at": datetime.now(),
    }

    backend.get = AsyncMock(return_value=Result.ok(default_task_dict))
    backend.update = AsyncMock()
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
def mock_analytics_engine() -> Mock:
    """Create a mock analytics engine."""
    return Mock()


@pytest.fixture
def progress_service(mock_backend, mock_analytics_engine) -> TasksProgressService:
    """Create TasksProgressService instance."""
    return TasksProgressService(backend=mock_backend, analytics_engine=mock_analytics_engine)


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task."""
    return Task.from_dto(
        TaskDTO(
            uid="task:123",
            user_uid="user:demo",
            title="Test Task",
            priority=Priority.HIGH.value,
            status=KuStatus.ACTIVE.value,
            fulfills_goal_uid="goal:learn_python",
            reinforces_habit_uid="habit:daily_code",
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
            user_uid="user:demo",
            title="Blocked Task",
            priority=Priority.MEDIUM.value,
            status=KuStatus.DRAFT.value,
            created_at=datetime.now(),
        )
    )


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user:123",
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
    with pytest.raises(ValueError, match="tasks.progress backend is REQUIRED"):
        TasksProgressService(backend=None)


# ============================================================================
# TASK COMPLETION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_complete_task_with_cascade_success(
    progress_service, mock_backend, sample_task, user_context
):
    """Test successful task completion with cascade effects."""
    # Setup
    mock_backend.get.return_value = Result.ok(sample_task.to_dto().to_dict())

    # Setup updated task (completed)
    completed_dto = sample_task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    completed_dto.completion_date = date.today()
    completed_dto.actual_minutes = 90
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade(
        "task:123", user_context, actual_minutes=90, quality_score=4
    )

    # Verify
    assert result.is_ok
    completed_task = result.value
    assert completed_task.status == KuStatus.COMPLETED
    assert completed_task.completion_date == date.today()
    assert completed_task.actual_minutes == 90


@pytest.mark.asyncio
async def test_complete_task_cascade_effects(
    progress_service, mock_backend, sample_task, user_context
):
    """Test that cascade effects are triggered on completion."""
    # Setup
    mock_backend.get.return_value = Result.ok(sample_task.to_dto().to_dict())

    completed_dto = sample_task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:123", user_context)

    # Verify cascade methods would be called
    # (In real implementation, these update goals, habits, knowledge)
    assert result.is_ok


@pytest.mark.asyncio
async def test_complete_task_not_found(progress_service, mock_backend, user_context):
    """Test completion when task doesn't exist."""
    # Setup
    mock_backend.get.return_value = Result.fail(Errors.not_found("Task", "task:999"))

    # Execute
    result = await progress_service.complete_task_with_cascade("task:999", user_context)

    # Verify
    assert result.is_error


# ============================================================================
# RECORD TASK COMPLETION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_record_task_completion_success(progress_service, mock_backend):
    """Test successful recording of task completion by user."""
    # Setup
    mock_backend.record_task_completion_by_user.return_value = Result.ok(True)

    # Execute
    result = await progress_service.record_task_completion(
        task_uid="task:123",
        user_uid="user:123",
        duration_minutes=60,
        quality_score=0.9,
        completion_notes="Great work!",
    )

    # Verify
    assert result.is_ok
    assert result.value is True
    # Note: Service now uses graph relationships (add_relationship) instead of
    # specific backend methods (record_task_completion_by_user)


@pytest.mark.asyncio
async def test_record_task_completion_backend_error(progress_service, mock_backend):
    """Test recording completion with backend error."""
    # Setup
    # Service now uses add_relationship instead of specific backend methods
    mock_backend.add_relationship.return_value = Result.fail(
        Errors.database("add_relationship", "Database error")
    )

    # Execute
    result = await progress_service.record_task_completion("task:123", "user:123")

    # Verify
    assert result.is_error


# ============================================================================
# PREREQUISITE CHECKING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_prerequisites_met(progress_service, mock_backend, sample_task, user_context):
    """Test prerequisite check when all prerequisites are met."""
    # Setup - task with no prerequisites
    simple_task = Task.from_dto(
        TaskDTO(
            uid="task:simple",
            user_uid="user:demo",
            title="Simple Task",
            priority=Priority.MEDIUM.value,
            status=KuStatus.DRAFT.value,
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
            user_uid="user:demo",
            title="Ready Task",
            priority=Priority.HIGH.value,
            status=KuStatus.DRAFT.value,
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
        unblocked_dto.status = KuStatus.SCHEDULED.value
        mock_backend.update.return_value = Result.ok(unblocked_dto.to_dict())

        # Create mock context
        context = UserContext(
            user_uid="user:123",
            username="test_user",
            prerequisites_completed=set(),
            completed_task_uids=set(),
        )

        # Execute
        result = await progress_service.unblock_task_if_ready("task:ready", context)

        # Verify
        assert result.is_ok
        assert result.value is not None
        assert result.value.status == KuStatus.SCHEDULED


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
            user_uid="user:123",
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
        user_uid="user:456",
        assigned_by="user:admin",
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
    result = await progress_service.assign_task_to_user("task:123", "user:456")

    # Verify
    assert result.is_error


# ============================================================================
# CASCADE EFFECT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_complete_task_updates_goal(progress_service, mock_backend, user_context):
    """Test that completing a task triggers goal progress update."""
    # Setup - task that contributes to goal
    goal_task = Task.from_dto(
        TaskDTO(
            uid="task:goal_task",
            user_uid="user:demo",
            title="Goal Task",
            priority=Priority.HIGH.value,
            status=KuStatus.ACTIVE.value,
            fulfills_goal_uid="goal:learn_python",
            goal_progress_contribution=0.3,
            completion_updates_goal=True,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(goal_task.to_dto().to_dict())

    completed_dto = goal_task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:goal_task", user_context)

    # Verify
    assert result.is_ok
    # In real implementation, _update_goal_progress would be called


@pytest.mark.asyncio
async def test_complete_task_reinforces_habit(progress_service, mock_backend, user_context):
    """Test that completing a task reinforces linked habit."""
    # Setup - task that reinforces habit
    habit_task = Task.from_dto(
        TaskDTO(
            uid="task:habit_task",
            user_uid="user:demo",
            title="Habit Task",
            priority=Priority.MEDIUM.value,
            status=KuStatus.ACTIVE.value,
            reinforces_habit_uid="habit:daily_code",
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(habit_task.to_dto().to_dict())

    completed_dto = habit_task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade(
        "task:habit_task", user_context, quality_score=5
    )

    # Verify
    assert result.is_ok
    # In real implementation, _reinforce_habit would be called


@pytest.mark.asyncio
async def test_complete_task_updates_knowledge_mastery(
    progress_service, mock_backend, user_context
):
    """Test that completing a task updates knowledge mastery."""
    # Setup - task that checks knowledge mastery
    mastery_task = Task.from_dto(
        TaskDTO(
            uid="task:mastery_task",
            user_uid="user:demo",
            title="Mastery Task",
            priority=Priority.HIGH.value,
            status=KuStatus.ACTIVE.value,
            knowledge_mastery_check=True,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(mastery_task.to_dto().to_dict())

    completed_dto = mastery_task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:mastery_task", user_context)

    # Verify
    assert result.is_ok
    # In real implementation, _update_knowledge_mastery would be called for each knowledge UID


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_complete_and_unblock_workflow(progress_service, mock_backend, user_context):
    """Test workflow: complete task -> unblock dependent tasks."""
    # Setup - complete a task
    task = Task.from_dto(
        TaskDTO(
            uid="task:prerequisite",
            user_uid="user:demo",
            title="Prerequisite Task",
            priority=Priority.HIGH.value,
            status=KuStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(task.to_dto().to_dict())

    completed_dto = task.to_dto()
    completed_dto.status = KuStatus.COMPLETED.value
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Complete the task
    complete_result = await progress_service.complete_task_with_cascade(
        "task:prerequisite", user_context
    )
    assert complete_result.is_ok

    # Now try to unblock a dependent task
    # (In real scenario, context would be updated with completed task)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
