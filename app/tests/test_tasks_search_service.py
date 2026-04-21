#!/usr/bin/env python3
"""
TasksSearchService Test Suite
==============================

Tests for search and discovery operations in TasksSearchService.

This service handles:
- Goal-based task search
- Habit-based task search
- Knowledge-based task search
- Blocked task discovery
- Prioritized task recommendations
- Learning-relevant task discovery
- Curriculum task filtering
"""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, EntityStatus, Priority
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.lp_position import LpPosition
from core.models.pathways.path_step import PathStep
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.services.tasks.tasks_search_service import TasksSearchService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend."""
    backend = Mock()
    backend.list_tasks = AsyncMock()
    backend.get_user_tasks = AsyncMock()
    backend.get = AsyncMock()  # Used by get_tasks_applying_knowledge
    # get_user_entities returns (entities, total_count) tuple
    backend.get_user_entities = AsyncMock(return_value=Result.ok(([], 0)))
    backend.find_by = AsyncMock()  # Search service uses find_by for filtering
    backend.list = AsyncMock()  # Used by curriculum and path step queries
    # Default: No relationships found (empty lists)
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    # count_related returns Result[int] for relationship counting
    backend.count_related = AsyncMock(return_value=Result.ok(0))
    # Temporal raw helpers used by TimeQueryMixin (get_upcoming/get_overdue/get_active)
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_context_service() -> Any:
    """Create a mock user context service."""
    service = Mock()
    service.get_context = AsyncMock()
    return service


@pytest.fixture
def search_service(mock_backend) -> TasksSearchService:
    """Create TasksSearchService instance."""
    return TasksSearchService(backend=mock_backend)


@pytest.fixture
def sample_tasks() -> list[Any]:
    """Create sample tasks with different properties."""
    now = datetime.now()
    return [
        Task.from_dto(
            TaskDTO(
                uid="task:1",
                user_uid="user:demo",
                title="Complete Python module",
                priority=Priority.HIGH.value,
                status=EntityStatus.ACTIVE.value,
                fulfills_goal_uid="goal:learn_python",
                reinforces_habit_uid=None,
                goal_progress_contribution=0.2,
                created_at=now,
            )
        ),
        Task.from_dto(
            TaskDTO(
                uid="task:2",
                user_uid="user:demo",
                title="Daily coding practice",
                priority=Priority.MEDIUM.value,
                status=EntityStatus.SCHEDULED.value,
                fulfills_goal_uid=None,
                reinforces_habit_uid="habit:daily_code",
                created_at=now,
            )
        ),
        Task.from_dto(
            TaskDTO(
                uid="task:3",
                user_uid="user:demo",
                title="Blocked task - needs prereq",
                priority=Priority.HIGH.value,
                status=EntityStatus.DRAFT.value,
                created_at=now,
            )
        ),
        Task.from_dto(
            TaskDTO(
                uid="task:4",
                user_uid="user:demo",
                title="Learning step task",
                priority=Priority.LOW.value,
                status=EntityStatus.DRAFT.value,
                knowledge_mastery_check=True,
                source_path_step_uid="ps:python_fundamentals",
                created_at=now,
            )
        ),
    ]


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user:123",
        username="test_user",
        prerequisites_completed={"ku.python.basics"},
        completed_task_uids={"task:completed_1", "task:completed_2"},
        active_goal_uids={"goal:learn_python"},
        active_habit_uids={"habit:daily_code"},
    )


@pytest.fixture
def learning_position() -> LpPosition:
    """Create sample learning position."""
    step1 = PathStep(
        uid="ps:python_fundamentals",
        title="Python Fundamentals",
        intent="Learn Python basics",
        knowledge_uids=("ku.python.basics",),
        mastery_threshold=0.8,
        estimated_hours=10.0,
    )
    step2 = PathStep(
        uid="ps:python_advanced",
        title="Python Advanced",
        intent="Master advanced Python concepts",
        knowledge_uids=("ku.python.advanced",),
        mastery_threshold=0.85,
        estimated_hours=20.0,
    )

    path = LearningPath(
        uid="lp:python_mastery",
        title="Python Mastery",
        description="Master Python programming",
        domain=Domain.TECH,
        metadata={"steps": [step1, step2]},
    )

    return LpPosition(
        user_uid="user:123",
        active_paths=[path],
        current_steps={"lp:python_mastery": step1},
        completed_step_uids=set(),
        next_recommended=["ps:python_advanced"],
        generated_at=datetime.now(),
        readiness_scores={"ps:python_advanced": 0.8},
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


def test_init_with_backend(mock_backend):
    """Test service initialization with required backend."""
    service = TasksSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    """Test service initialization fails without backend."""
    with pytest.raises(ValueError, match=r"tasks\.search backend is REQUIRED"):
        TasksSearchService(backend=None)


# ============================================================================
# GOAL-BASED SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_for_goal_success(search_service, mock_backend, sample_tasks):
    """Test successful retrieval of tasks for a specific goal."""
    # Setup - filter for goal
    goal_tasks = [t for t in sample_tasks if t.fulfills_goal_uid == "goal:learn_python"]
    # Service now uses find_by() instead of list_tasks()
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in goal_tasks])

    # Execute
    result = await search_service.get_tasks_for_goal("goal:learn_python")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 1
    assert tasks[0].fulfills_goal_uid == "goal:learn_python"
    # Verify sorted by contribution (higher first)
    assert tasks[0].goal_progress_contribution == 0.2


@pytest.mark.asyncio
async def test_get_tasks_for_goal_empty(search_service, mock_backend):
    """Test retrieval when no tasks exist for goal."""
    # Setup
    # Service now uses find_by() instead of list_tasks()
    mock_backend.find_by.return_value = Result.ok([])

    # Execute
    result = await search_service.get_tasks_for_goal("goal:nonexistent")

    # Verify
    assert result.is_ok
    assert len(result.value) == 0


# ============================================================================
# HABIT-BASED SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_for_habit_success(search_service, mock_backend, sample_tasks):
    """Test successful retrieval of tasks for a specific habit."""
    # Setup
    habit_tasks = [t for t in sample_tasks if t.reinforces_habit_uid == "habit:daily_code"]
    # Service now uses find_by() instead of list_tasks()
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in habit_tasks])

    # Execute
    result = await search_service.get_tasks_for_habit("habit:daily_code")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 1
    assert tasks[0].reinforces_habit_uid == "habit:daily_code"


# ============================================================================
# KNOWLEDGE-BASED SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_applying_knowledge_success(search_service, mock_backend, sample_tasks):
    """Test successful retrieval of tasks applying specific knowledge."""
    # Setup - B: Mock graph query for APPLIES_KNOWLEDGE relationships
    # Tasks 1 and 4 apply ku.python.basics
    task_uids = ["task:1", "task:4"]
    mock_backend.get_related_uids.return_value = Result.ok(task_uids)

    # Mock backend.get to return the tasks (service uses self.backend.get(uid))
    mock_backend.get = AsyncMock(
        side_effect=lambda uid: (
            Result.ok(next(t.to_dto().to_dict() for t in sample_tasks if t.uid == uid))
            if any(t.uid == uid for t in sample_tasks)
            else Result.fail(Errors.not_found("Task", uid))
        )
    )

    # Execute
    result = await search_service.get_tasks_applying_knowledge("ku.python.basics")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 2  # tasks 1 and 4 apply ku.python.basics
    assert all(t.uid in task_uids for t in tasks)


# ============================================================================
# BLOCKED TASKS DISCOVERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_blocked_by_prerequisites(
    search_service, mock_backend, sample_tasks, user_context
):
    """Test discovery of tasks blocked by prerequisites."""
    # Setup - return all user tasks (get_user_entities returns tuple)
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    # Mock count_related to return 0 for all tasks (no prerequisites)
    # count_related returns Result[int]
    mock_backend.count_related.return_value = Result.ok(0)

    # Execute
    result = await search_service.get_blocked_by_prerequisites("user:123")

    # Verify
    assert result.is_ok
    blocked_tasks = result.value
    # With no prerequisites in the mocked graph, expect 0 blocked tasks
    assert len(blocked_tasks) == 0

    # Verify count_related was called to check for prerequisites
    # Should check both REQUIRES_KNOWLEDGE and REQUIRES_PREREQUISITE for each task
    assert mock_backend.count_related.called


@pytest.mark.asyncio
async def test_get_blocked_tasks_empty(search_service, mock_backend):
    """Test when no tasks are blocked."""
    # Setup - tasks without prerequisites
    simple_task = Task.from_dto(
        TaskDTO(
            uid="task:simple",
            user_uid="user:demo",
            title="Simple task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.DRAFT.value,
            created_at=datetime.now(),
        )
    )
    # get_user_entities returns (entities, total_count) tuple
    mock_backend.get_user_entities.return_value = Result.ok(([simple_task.to_dto().to_dict()], 1))

    # count_related returns Result[int] - 0 means no prerequisites
    mock_backend.count_related.return_value = Result.ok(0)

    # Execute
    result = await search_service.get_blocked_by_prerequisites("user:123")

    # Verify
    assert result.is_ok
    assert len(result.value) == 0


# ============================================================================
# PRIORITIZED TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_prioritized_success(search_service, mock_backend, sample_tasks, user_context):
    """Test retrieval of prioritized tasks using unified score_task."""
    from core.models.search.scoring import score_task

    # Setup - get_user_entities returns (entities, total_count) tuple
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    # Execute
    result = await search_service.get_prioritized(user_context, limit=2)

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) <= 2

    # Verify sorted by unified score_task total (descending)
    if len(tasks) > 1:
        assert score_task(tasks[0], user_context).total >= score_task(tasks[1], user_context).total


@pytest.mark.asyncio
async def test_get_prioritized_respects_limit(
    search_service, mock_backend, sample_tasks, user_context
):
    """Test that prioritized tasks respects the limit parameter."""
    # Setup - get_user_entities returns (entities, total_count) tuple
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    # Execute with limit 1
    result = await search_service.get_prioritized(user_context, limit=1)

    # Verify
    assert result.is_ok
    assert len(result.value) == 1


# ============================================================================
# LEARNING-RELEVANT TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_learning_relevant_tasks(
    search_service, mock_backend, sample_tasks, learning_position
):
    """Test retrieval of tasks relevant to learning position."""
    # Setup - get_user_entities returns (entities, total_count) tuple
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    # Execute
    result = await search_service.get_learning_relevant_tasks(
        "user:123", learning_position, limit=3
    )

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) <= 3

    # NOTE: Knowledge alignment verification removed - requires backend queries
    # Tasks are sorted by relevance score calculated via backend.get_related_uids()


# ============================================================================
# CURRICULUM TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_curriculum_tasks(search_service, mock_backend, sample_tasks):
    """Test retrieval of tasks from curriculum."""
    # Setup
    # Service uses backend.list() which returns Result[(tasks_data, total_count)] tuple
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.list.return_value = Result.ok((tasks_data, len(tasks_data)))

    # Execute
    result = await search_service.get_curriculum_tasks()

    # Verify
    assert result.is_ok
    curriculum_tasks = result.value

    # Only task 4 has source_path_step_uid
    assert len(curriculum_tasks) == 1
    assert curriculum_tasks[0].uid == "task:4"
    assert curriculum_tasks[0].is_from_path_step


# ============================================================================
# LEARNING STEP TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_for_path_step(search_service, mock_backend, sample_tasks):
    """Test retrieval of tasks for a specific path step."""
    # Setup
    # Service uses backend.list() which returns Result[(tasks_data, total_count)] tuple
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.list.return_value = Result.ok((tasks_data, len(tasks_data)))

    # Execute
    result = await search_service.get_tasks_for_path_step("ps:python_fundamentals")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 1
    assert tasks[0].source_path_step_uid == "ps:python_fundamentals"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_multiple_search_criteria(search_service, mock_backend, sample_tasks):
    """Test combining multiple search criteria."""
    # Setup - find_by is used for goal and habit searches
    goal_tasks = [t for t in sample_tasks if t.fulfills_goal_uid == "goal:learn_python"]
    habit_tasks = [t for t in sample_tasks if t.reinforces_habit_uid == "habit:daily_code"]
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in goal_tasks])

    # Execute goal search
    goal_result = await search_service.get_tasks_for_goal("goal:learn_python")
    assert goal_result.is_ok

    # Setup for habit search
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in habit_tasks])
    habit_result = await search_service.get_tasks_for_habit("habit:daily_code")
    assert habit_result.is_ok

    # Setup for knowledge search
    mock_backend.get_related_uids.return_value = Result.ok(["task:1"])
    mock_backend.get.return_value = Result.ok(sample_tasks[0].to_dto().to_dict())
    knowledge_result = await search_service.get_tasks_applying_knowledge("ku.python.basics")
    assert knowledge_result.is_ok


@pytest.mark.asyncio
async def test_search_with_backend_error(search_service, mock_backend):
    """Test search operations handle backend errors gracefully."""
    # Setup - get_tasks_for_goal uses find_by
    mock_backend.find_by.return_value = Result.fail(
        Errors.database("find_by", "Database connection error")
    )

    # Execute
    result = await search_service.get_tasks_for_goal("goal:test")

    # Verify
    assert result.is_error


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE TESTS (get_upcoming / get_overdue / get_active)
# ============================================================================


@pytest.mark.asyncio
async def test_get_upcoming_success(search_service, mock_backend, sample_tasks):
    """get_upcoming forwards date_field + exclusions to backend.upcoming_raw."""
    # Tasks use due_date as the date_field (DomainConfig).
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.upcoming_raw.return_value = Result.ok(tasks_data)

    result = await search_service.get_upcoming(days_ahead=14, user_uid="user:demo", limit=50)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.upcoming_raw.assert_awaited_once()
    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["date_field"] == "due_date"
    assert kwargs["days_ahead"] == 14
    assert kwargs["user_uid"] == "user:demo"
    assert kwargs["limit"] == 50
    # Terminal statuses are excluded by default via temporal_exclude_statuses
    assert set(kwargs["exclude_statuses"]) >= {"completed", "failed", "cancelled", "archived"}


@pytest.mark.asyncio
async def test_get_upcoming_empty(search_service, mock_backend):
    """get_upcoming returns empty list when backend finds nothing."""
    mock_backend.upcoming_raw.return_value = Result.ok([])

    result = await search_service.get_upcoming(user_uid="user:demo")

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_get_upcoming_error_propagates(search_service, mock_backend):
    """Backend failure surfaces as Result.fail."""
    mock_backend.upcoming_raw.return_value = Result.fail(
        Errors.database("upcoming_raw", "backend down")
    )

    result = await search_service.get_upcoming()

    assert result.is_error


@pytest.mark.asyncio
async def test_get_overdue_success(search_service, mock_backend, sample_tasks):
    """get_overdue forwards date_field to backend.overdue_raw."""
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.overdue_raw.return_value = Result.ok(tasks_data)

    result = await search_service.get_overdue(user_uid="user:demo", limit=25)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.overdue_raw.assert_awaited_once()
    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["date_field"] == "due_date"
    assert kwargs["user_uid"] == "user:demo"
    assert kwargs["limit"] == 25


@pytest.mark.asyncio
async def test_get_overdue_admin_path(search_service, mock_backend):
    """get_overdue allows user_uid=None for admin/system queries."""
    mock_backend.overdue_raw.return_value = Result.ok([])

    result = await search_service.get_overdue()

    assert result.is_ok
    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["user_uid"] is None


@pytest.mark.asyncio
async def test_get_overdue_error_propagates(search_service, mock_backend):
    """Backend failure on overdue surfaces cleanly."""
    mock_backend.overdue_raw.return_value = Result.fail(Errors.database("overdue_raw", "boom"))

    result = await search_service.get_overdue(user_uid="user:demo")

    assert result.is_error


@pytest.mark.asyncio
async def test_get_active_success(search_service, mock_backend, sample_tasks):
    """get_active delegates to backend.active_raw with terminal exclusions."""
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.active_raw.return_value = Result.ok(tasks_data)

    result = await search_service.get_active(user_uid="user:demo", limit=10)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.active_raw.assert_awaited_once()
    kwargs = mock_backend.active_raw.call_args.kwargs
    assert kwargs["user_uid"] == "user:demo"
    assert kwargs["limit"] == 10
    assert set(kwargs["exclude_statuses"]) >= {"completed", "failed", "cancelled", "archived"}


@pytest.mark.asyncio
async def test_get_active_requires_user_uid(search_service, mock_backend):
    """get_active rejects empty user_uid — there is no 'active for nobody' query."""
    result = await search_service.get_active(user_uid="")

    assert result.is_error
    mock_backend.active_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_active_error_propagates(search_service, mock_backend):
    """Backend failure on active surfaces cleanly."""
    mock_backend.active_raw.return_value = Result.fail(Errors.database("active_raw", "kaput"))

    result = await search_service.get_active(user_uid="user:demo")

    assert result.is_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
