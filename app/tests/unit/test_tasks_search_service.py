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
- Curriculum task filtering
"""

from dataclasses import replace
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus, Priority
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
    # get_user_entities returns (entities, total_count) tuple
    backend.get_user_entities = AsyncMock(return_value=Result.ok(([], 0)))
    backend.find_by = AsyncMock()  # Search service uses find_by for filtering
    # Default: No relationships found (empty lists)
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    # Graph-native habit linkage (REINFORCES_HABIT edge)
    backend.get_tasks_reinforcing_habit = AsyncMock(return_value=Result.ok([]))
    backend.get_habit_links_for_tasks = AsyncMock(return_value=Result.ok({}))
    # Graph-native goal linkage (CONTRIBUTES_TO_GOAL edge)
    backend.get_tasks_contributing_to_goal = AsyncMock(return_value=Result.ok([]))
    backend.get_goal_links_for_tasks = AsyncMock(return_value=Result.ok({}))
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
                user_uid="user_demo",
                title="Complete Python module",
                priority=Priority.HIGH.value,
                status=EntityStatus.ACTIVE.value,
                goal_progress_contribution=0.2,
                created_at=now,
            )
        ),
        # reinforces_habit_uid is a DERIVED field (graph edge), set after from_dto.
        replace(
            Task.from_dto(
                TaskDTO(
                    uid="task:2",
                    user_uid="user_demo",
                    title="Daily coding practice",
                    priority=Priority.MEDIUM.value,
                    status=EntityStatus.SCHEDULED.value,
                    created_at=now,
                )
            ),
            reinforces_habit_uid="habit:daily_code",
        ),
        Task.from_dto(
            TaskDTO(
                uid="task:3",
                user_uid="user_demo",
                title="Blocked task - needs prereq",
                priority=Priority.HIGH.value,
                status=EntityStatus.DRAFT.value,
                created_at=now,
            )
        ),
        Task.from_dto(
            TaskDTO(
                uid="task:4",
                user_uid="user_demo",
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
        user_uid="user_123",
        username="test_user",
        mastered_knowledge_uids={"ku.python.basics"},
        completed_task_uids={"task:completed_1", "task:completed_2"},
        active_goal_uids={"goal:learn_python"},
        active_habit_uids={"habit:daily_code"},
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
    """The goal's contributing tasks come from the edge read, highest contribution first."""
    low, high = sample_tasks[1], sample_tasks[0]  # 0.0 and 0.2
    mock_backend.get_tasks_contributing_to_goal.return_value = Result.ok([low, high])

    result = await search_service.get_tasks_for_goal("goal:learn_python", "user.test")

    # The read is the CONTRIBUTES_TO_GOAL traversal, scoped to the viewer
    mock_backend.get_tasks_contributing_to_goal.assert_awaited_once_with(
        "goal:learn_python", "user.test"
    )
    mock_backend.find_by.assert_not_awaited()
    assert result.is_ok
    assert [t.uid for t in result.value] == [high.uid, low.uid]
    assert result.value[0].goal_progress_contribution == 0.2


@pytest.mark.asyncio
async def test_get_tasks_for_goal_empty(search_service, mock_backend):
    """Test retrieval when no tasks exist for goal."""
    mock_backend.get_tasks_contributing_to_goal.return_value = Result.ok([])

    result = await search_service.get_tasks_for_goal("goal:nonexistent", "user.test")

    # Verify
    assert result.is_ok
    assert len(result.value) == 0


# ============================================================================
# HABIT-BASED SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_for_habit_success(search_service, mock_backend, sample_tasks):
    """Test successful retrieval of tasks for a specific habit (graph traversal)."""
    # Setup — service traverses (Task)-[:REINFORCES_HABIT]->(Habit) via the backend.
    habit_tasks = [t for t in sample_tasks if t.uid == "task:2"]
    mock_backend.get_tasks_reinforcing_habit.return_value = Result.ok(habit_tasks)

    # Execute
    result = await search_service.get_tasks_for_habit("habit:daily_code", "user.test")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 1
    assert tasks[0].uid == "task:2"
    mock_backend.get_tasks_reinforcing_habit.assert_awaited_once_with(
        "habit:daily_code", "user.test"
    )


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
    result = await search_service.get_blocked_by_prerequisites("user_123")

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
            user_uid="user_demo",
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
    result = await search_service.get_blocked_by_prerequisites("user_123")

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


@pytest.mark.asyncio
async def test_get_prioritized_scores_with_the_goal_the_edges_name(
    search_service, mock_backend, sample_tasks, user_context
):
    """The goal-alignment scorer reads ``contributes_to_goal_uid``, derived from the edges."""
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))
    mock_backend.get_goal_links_for_tasks.return_value = Result.ok(
        {"task:1": ["goal:someday", "goal:learn_python"]}
    )

    result = await search_service.get_prioritized(user_context, limit=10)

    assert result.is_ok
    by_uid = {t.uid: t for t in result.value}
    # Several goals: the active one is carried
    assert by_uid["task:1"].contributes_to_goal_uid == "goal:learn_python"
    assert by_uid["task:3"].contributes_to_goal_uid is None


@pytest.mark.asyncio
async def test_a_task_contributing_to_an_active_goal_ranks_above_its_twin(
    search_service, mock_backend, user_context
):
    """Two tasks alike in every field the scorer reads but their goal link: only the
    edge-derived goal can order them, so the enrichment must feed the scorer."""
    now = datetime.now()
    twins = [
        TaskDTO(
            uid=uid,
            user_uid="user_demo",
            title="Twin",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            created_at=now,
        ).to_dict()
        for uid in ("task:goalless", "task:aligned")
    ]
    mock_backend.get_user_entities.return_value = Result.ok((twins, len(twins)))
    mock_backend.get_goal_links_for_tasks.return_value = Result.ok(
        {"task:aligned": ["goal:learn_python"]}
    )

    result = await search_service.get_prioritized(user_context, limit=1)

    assert result.is_ok
    assert [t.uid for t in result.value] == ["task:aligned"]


@pytest.mark.asyncio
async def test_enrich_with_goal_links_is_fail_soft(search_service, mock_backend, sample_tasks):
    mock_backend.get_goal_links_for_tasks.return_value = Result.fail(
        Errors.database("get_goal_links_for_tasks", "down")
    )

    enriched = await search_service.enrich_with_goal_links(sample_tasks, ["goal:learn_python"])

    assert enriched == sample_tasks


@pytest.mark.asyncio
async def test_enrich_with_goal_links_takes_the_first_goal_when_none_is_active(
    search_service, mock_backend, sample_tasks
):
    mock_backend.get_goal_links_for_tasks.return_value = Result.ok(
        {"task:1": ["goal:first", "goal:second"]}
    )

    enriched = await search_service.enrich_with_goal_links(sample_tasks, None)

    assert enriched[0].contributes_to_goal_uid == "goal:first"
    assert all(t.contributes_to_goal_uid is None for t in enriched[1:])


# ============================================================================
# LEARNING STEP TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_tasks_for_path_step(search_service, mock_backend, sample_tasks):
    """Test retrieval of tasks for a specific path step."""
    # Setup — the backend answers the scoped read
    step_tasks = [t for t in sample_tasks if t.source_path_step_uid == "ps:python_fundamentals"]
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in step_tasks])

    # Execute
    result = await search_service.get_tasks_for_path_step("ps:python_fundamentals", "user.test")

    # Verify — asked for this step's tasks, for this viewer only
    assert mock_backend.find_by.await_args.kwargs["source_path_step_uid"] == (
        "ps:python_fundamentals"
    )
    assert mock_backend.find_by.await_args.kwargs["user_uid"] == "user.test"
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
    # Setup - the goal search reads the edge; the habit search reads the habit edge
    habit_tasks = [t for t in sample_tasks if t.reinforces_habit_uid == "habit:daily_code"]
    mock_backend.get_tasks_contributing_to_goal.return_value = Result.ok(sample_tasks[:1])

    # Execute goal search
    goal_result = await search_service.get_tasks_for_goal("goal:learn_python", "user.test")
    assert goal_result.is_ok

    # Setup for habit search
    mock_backend.find_by.return_value = Result.ok([t.to_dto().to_dict() for t in habit_tasks])
    habit_result = await search_service.get_tasks_for_habit("habit:daily_code", "user.test")
    assert habit_result.is_ok


@pytest.mark.asyncio
async def test_search_with_backend_error(search_service, mock_backend):
    """Test search operations handle backend errors gracefully."""
    mock_backend.get_tasks_contributing_to_goal.return_value = Result.fail(
        Errors.database("get_tasks_contributing_to_goal", "Database connection error")
    )

    # Execute
    result = await search_service.get_tasks_for_goal("goal:test", "user.test")

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

    result = await search_service.get_upcoming(days_ahead=14, user_uid="user_demo", limit=50)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.upcoming_raw.assert_awaited_once()
    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["date_field"] == "due_date"
    assert kwargs["days_ahead"] == 14
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 50
    # Terminal statuses are excluded by default via temporal_exclude_statuses
    assert set(kwargs["exclude_statuses"]) >= {"completed", "failed", "cancelled", "archived"}


@pytest.mark.asyncio
async def test_get_upcoming_empty(search_service, mock_backend):
    """get_upcoming returns empty list when backend finds nothing."""
    mock_backend.upcoming_raw.return_value = Result.ok([])

    result = await search_service.get_upcoming(user_uid="user_demo")

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

    result = await search_service.get_overdue(user_uid="user_demo", limit=25)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.overdue_raw.assert_awaited_once()
    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["date_field"] == "due_date"
    assert kwargs["user_uid"] == "user_demo"
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

    result = await search_service.get_overdue(user_uid="user_demo")

    assert result.is_error


@pytest.mark.asyncio
async def test_get_active_success(search_service, mock_backend, sample_tasks):
    """get_active delegates to backend.active_raw with terminal exclusions."""
    tasks_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.active_raw.return_value = Result.ok(tasks_data)

    result = await search_service.get_active(user_uid="user_demo", limit=10)

    assert result.is_ok
    assert len(result.value) == len(sample_tasks)
    mock_backend.active_raw.assert_awaited_once()
    kwargs = mock_backend.active_raw.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
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

    result = await search_service.get_active(user_uid="user_demo")

    assert result.is_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
