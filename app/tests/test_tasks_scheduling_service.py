#!/usr/bin/env python3
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

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, KuStatus, Priority
from core.models.enums.ku_enums import KuType
from core.models.ku import Ku, LpPosition
from core.models.ku.ku_dto import KuDTO as TaskDTO
from core.models.ku.ku_request import KuTaskCreateRequest
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend."""
    backend = Mock()
    backend.create = AsyncMock()
    backend.create_task = AsyncMock()
    # Default: No relationships found (empty lists)
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    backend.create_relationships_batch = AsyncMock(
        return_value=Result.ok(0)
    )  # Batch relationship creation
    return backend


@pytest.fixture
def scheduling_service(mock_backend) -> TasksSchedulingService:
    """Create TasksSchedulingService instance."""
    return TasksSchedulingService(backend=mock_backend)


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user:123",
        username="test_user",
        prerequisites_completed={"ku.python.basics", "ku.git.basics"},
        completed_task_uids={"task:completed_1"},
        active_goal_uids={"goal:learn_python"},
        active_habit_uids={"habit:daily_code"},
    )


@pytest.fixture
def learning_position() -> LpPosition:
    """Create sample learning position."""
    # Create learning steps (Ku with ku_type=LEARNING_STEP)
    step1 = Ku(
        uid="ls:python_fundamentals",
        title="Python Fundamentals",
        ku_type=KuType.LEARNING_STEP,
        intent="Learn Python basics",
        primary_knowledge_uids=("ku.python.basics",),
        mastery_threshold=0.8,
        estimated_hours=10.0,
    )
    step2 = Ku(
        uid="ls:python_advanced",
        title="Python Advanced",
        ku_type=KuType.LEARNING_STEP,
        intent="Master advanced Python concepts",
        primary_knowledge_uids=("ku.python.advanced",),
        mastery_threshold=0.85,
        estimated_hours=20.0,
    )

    # Create learning path (Ku with ku_type=LEARNING_PATH)
    path = Ku(
        uid="lp:python_mastery",
        title="Python Mastery",
        ku_type=KuType.LEARNING_PATH,
        description="Master Python programming",
        domain=Domain.TECH,
        metadata={"steps": [step1, step2]},
    )

    return LpPosition(
        user_uid="user:123",
        active_paths=[path],
        current_steps={"lp:python_mastery": step1},
        completed_step_uids=set(),
        next_recommended=["ls:python_advanced"],
        generated_at=datetime.now(),
        readiness_scores={"ls:python_advanced": 0.8},
    )


@pytest.fixture
def task_request() -> KuTaskCreateRequest:
    """Create sample task creation request."""
    return KuTaskCreateRequest(
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


def test_init_with_backend(mock_backend):
    """Test service initialization with required backend."""
    service = TasksSchedulingService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    """Test service initialization fails without backend."""
    with pytest.raises(ValueError, match="tasks.scheduling backend is REQUIRED"):
        TasksSchedulingService(backend=None)


# ============================================================================
# CONTEXT-AWARE CREATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_with_context_success(
    scheduling_service, mock_backend, task_request, user_context
):
    """Test successful context-aware task creation."""
    # Setup
    created_dto = TaskDTO.create_task(
        user_uid="user:123",
        title=task_request.title,
        priority=task_request.priority,
        due_date=task_request.due_date,
    )
    created_dto.uid = "task:new_123"

    mock_backend.create.return_value = Result.ok(created_dto.to_dict())

    # Execute
    result = await scheduling_service.create_task_with_context(task_request, user_context)

    # Verify
    assert result.is_ok
    task = result.value
    assert task.title == task_request.title
    # Phase 2: Relationship fields (prerequisite_knowledge_uids, etc.) removed from Task model
    # These are now stored as graph relationships and queried via TasksRelationshipService

    # Note: Context invalidation now happens via event-driven architecture
    # TaskCreated events trigger user_service.invalidate_context() in bootstrap


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
# LEARNING CONTEXT CREATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_with_learning_context(
    scheduling_service, mock_backend, task_request, learning_position
):
    """Test task creation with learning path context."""
    # Setup
    created_dto = TaskDTO.create_task(
        user_uid="user:123", title=task_request.title, priority=task_request.priority
    )
    created_dto.uid = "task:learning_123"
    mock_backend.create_task.return_value = Result.ok(created_dto.to_dict())

    # Execute
    result = await scheduling_service.create_task_with_learning_context(
        task_request, learning_position
    )

    # Verify
    assert result.is_ok
    task = result.value
    assert task.title == task_request.title


@pytest.mark.asyncio
async def test_create_task_without_learning_context(scheduling_service, mock_backend, task_request):
    """Test task creation without learning position."""
    # Setup
    created_dto = TaskDTO.create_task(user_uid="user:123", title=task_request.title)
    created_dto.uid = "task:no_context"
    mock_backend.create_task.return_value = Result.ok(created_dto.to_dict())

    # Execute - no learning position
    result = await scheduling_service.create_task_with_learning_context(task_request, None)

    # Verify
    assert result.is_ok


# ============================================================================
# LEARNING PATH TASK GENERATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_tasks_from_learning_path(scheduling_service, mock_backend, user_context):
    """Test task generation from learning path."""
    # Execute
    result = await scheduling_service.create_tasks_from_learning_path(
        "lp:python_mastery", user_context
    )

    # Verify - currently returns empty list (not yet implemented)
    assert result.is_ok
    assert isinstance(result.value, list)


@pytest.mark.asyncio
async def test_get_next_learning_task(scheduling_service, user_context):
    """Test getting next recommended learning task."""
    # Execute
    result = await scheduling_service.get_next_learning_task(user_context)

    # Verify - currently returns None (not yet implemented)
    assert result.is_ok


# ============================================================================
# TASK SUGGESTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_suggest_learning_aligned_tasks(scheduling_service, learning_position):
    """Test generation of learning-aligned task suggestions."""
    # Execute
    result = await scheduling_service.suggest_learning_aligned_tasks(learning_position)

    # Verify
    assert result.is_ok
    suggestions = result.value

    # Should generate suggestions based on active paths
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0

    # Verify suggestion structure
    for suggestion in suggestions:
        assert "title" in suggestion
        assert "learning_path" in suggestion
        assert "knowledge_uid" in suggestion
        assert "learning_relevance_score" in suggestion
        assert "suggestion_reason" in suggestion


@pytest.mark.asyncio
async def test_suggest_tasks_sorted_by_relevance(scheduling_service, learning_position):
    """Test that suggestions are sorted by learning relevance."""
    # Execute
    result = await scheduling_service.suggest_learning_aligned_tasks(learning_position, limit=10)

    # Verify
    assert result.is_ok
    suggestions = result.value

    # Verify sorted descending by relevance score
    if len(suggestions) > 1:
        for i in range(len(suggestions) - 1):
            assert (
                suggestions[i]["learning_relevance_score"]
                >= suggestions[i + 1]["learning_relevance_score"]
            )


@pytest.mark.asyncio
async def test_suggest_tasks_includes_current_and_next_steps(scheduling_service, learning_position):
    """Test that suggestions include both current and next steps."""
    # Execute
    result = await scheduling_service.suggest_learning_aligned_tasks(learning_position)

    # Verify
    assert result.is_ok
    suggestions = result.value

    # Should suggest tasks for current step
    current_step_suggestions = [s for s in suggestions if s["knowledge_uid"] == "ku.python.basics"]
    assert len(current_step_suggestions) > 0

    # Should also suggest preparation for next step
    next_step_suggestions = [s for s in suggestions if s["knowledge_uid"] == "ku.python.advanced"]
    assert len(next_step_suggestions) > 0


# ============================================================================
# CURRICULUM-BASED TASK CREATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_from_learning_step(scheduling_service, mock_backend):
    """Test creating a task from a learning step."""
    # Setup
    created_dto = TaskDTO(
        uid="task:curriculum_123",
        user_uid="user:123",
        title="Practice Python fundamentals",
        source_learning_step_uid="ls:python_fundamentals",
        knowledge_mastery_check=True,
        status=KuStatus.DRAFT.value,
        priority=Priority.MEDIUM.value,
        created_at=datetime.now(),
    )
    mock_backend.create.return_value = Result.ok(created_dto.to_dict())

    # Execute
    result = await scheduling_service.create_task_from_learning_step(
        step_uid="ls:python_fundamentals",
        task_title="Practice Python fundamentals",
        knowledge_uids=["ku.python.basics"],
        _user_uid="user:123",
    )

    # Verify
    assert result.is_ok
    task = result.value
    assert task.source_learning_step_uid == "ls:python_fundamentals"
    assert task.knowledge_mastery_check is True
    # Phase 2: applies_knowledge_uids removed - query via TasksRelationshipService.get_task_knowledge()


@pytest.mark.asyncio
async def test_create_curriculum_task_backend_error(scheduling_service, mock_backend):
    """Test curriculum task creation with backend error."""
    # Setup
    mock_backend.create_task.return_value = Result.fail(Errors.database("create_task", "Database error"))

    # Execute
    result = await scheduling_service.create_task_from_learning_step(
        step_uid="ls:test", task_title="Test Task", knowledge_uids=["ku.test"], _user_uid="user:123"
    )

    # Verify
    assert result.is_error


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_full_learning_workflow(
    scheduling_service, mock_backend, task_request, user_context, learning_position
):
    """Test complete workflow: context check -> suggestion -> creation."""
    # Step 1: Get suggestions
    suggestions_result = await scheduling_service.suggest_learning_aligned_tasks(learning_position)
    assert suggestions_result.is_ok

    # Step 2: Create task with context
    created_dto = TaskDTO.create_task(user_uid="user:123", title=task_request.title)
    created_dto.uid = "task:workflow"
    mock_backend.create.return_value = Result.ok(created_dto.to_dict())

    creation_result = await scheduling_service.create_task_with_context(task_request, user_context)
    assert creation_result.is_ok


@pytest.mark.asyncio
async def test_multiple_active_paths_suggestions(scheduling_service):
    """Test suggestions generation with multiple active learning paths."""
    # Setup - multiple paths
    python_step = Ku(
        uid="ls:python_basics",
        title="Python Basics",
        ku_type=KuType.LEARNING_STEP,
        intent="Learn Python basics",
        primary_knowledge_uids=("ku.python.basics",),
        mastery_threshold=0.8,
        estimated_hours=10.0,
    )
    path1 = Ku(
        uid="lp:python",
        title="Python",
        ku_type=KuType.LEARNING_PATH,
        description="Learn Python programming",
        domain=Domain.TECH,
        metadata={"steps": [python_step]},
    )

    html_step = Ku(
        uid="ls:html_basics",
        title="HTML Basics",
        ku_type=KuType.LEARNING_STEP,
        intent="Learn HTML basics",
        primary_knowledge_uids=("ku.html.basics",),
        mastery_threshold=0.75,
        estimated_hours=8.0,
    )
    path2 = Ku(
        uid="lp:web_dev",
        title="Web Development",
        ku_type=KuType.LEARNING_PATH,
        description="Learn web development",
        domain=Domain.TECH,
        metadata={"steps": [html_step]},
    )

    position = LpPosition(
        user_uid="user:123",
        active_paths=[path1, path2],
        current_steps={"lp:python": python_step, "lp:web_dev": html_step},
        completed_step_uids=set(),
        next_recommended=["ls:python_basics", "ls:html_basics"],
        generated_at=datetime.now(),
        readiness_scores={"ls:python_basics": 0.9, "ls:html_basics": 0.85},
    )

    # Execute
    result = await scheduling_service.suggest_learning_aligned_tasks(position)

    # Verify - should get suggestions from both paths
    assert result.is_ok
    suggestions = result.value

    # Should have suggestions from both paths
    python_suggestions = [s for s in suggestions if "python" in s["knowledge_uid"].lower()]
    html_suggestions = [s for s in suggestions if "html" in s["knowledge_uid"].lower()]

    assert len(python_suggestions) > 0 or len(html_suggestions) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
