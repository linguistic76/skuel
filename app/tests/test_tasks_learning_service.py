#!/usr/bin/env python3
# mypy: disable-error-code="list-item,dict-item"
"""
TasksLearningService Test Suite
================================

Tests for learning path integration in TasksLearningService.

This service handles:
- Learning-relevant task discovery
- Next recommended learning task
- Learning-aligned task suggestions
- Task generation from a learning path
"""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, EntityStatus, Priority
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.lp_position import LpPosition
from core.models.pathways.path_step import PathStep
from core.models.task.task import Task
from core.services.tasks.tasks_learning_service import TasksLearningService
from core.services.user import UserContext
from core.utils.result_simplified import Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend."""
    backend = Mock()
    backend.get_user_entities = AsyncMock(return_value=Result.ok(([], 0)))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def learning_service(mock_backend) -> TasksLearningService:
    """Create TasksLearningService instance."""
    return TasksLearningService(backend=mock_backend)


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


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Create sample tasks for relevance tests."""
    return [
        Task(
            uid=f"task:{i}", user_uid="user:123", title=f"Task {i}", priority=Priority.MEDIUM.value
        )
        for i in range(5)
    ]


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    """Service initializes with a backend."""
    service = TasksLearningService(backend=mock_backend)
    assert service.backend is mock_backend


# ============================================================================
# LEARNING-RELEVANT TASKS
# ============================================================================


@pytest.mark.asyncio
async def test_get_learning_relevant_tasks(
    learning_service, mock_backend, sample_tasks, learning_position
):
    """Retrieves tasks relevant to learning position."""
    task_data = [t.to_dto().to_dict() for t in sample_tasks]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    result = await learning_service.get_learning_relevant_tasks(
        "user:123", learning_position, limit=3
    )

    assert result.is_ok
    assert len(result.value) <= 3


@pytest.mark.asyncio
async def test_get_learning_relevant_tasks_skips_completed(
    learning_service, mock_backend, learning_position
):
    """Completed tasks are excluded from relevance results."""
    completed = Task(
        uid="task:done",
        user_uid="user:123",
        title="Done",
        priority=Priority.MEDIUM.value,
        status=EntityStatus.COMPLETED.value,
    )
    active = Task(
        uid="task:active",
        user_uid="user:123",
        title="Active",
        priority=Priority.MEDIUM.value,
    )
    task_data = [completed.to_dto().to_dict(), active.to_dto().to_dict()]
    mock_backend.get_user_entities.return_value = Result.ok((task_data, len(task_data)))

    result = await learning_service.get_learning_relevant_tasks("user:123", learning_position)

    assert result.is_ok
    returned_uids = {t.uid for t in result.value}
    assert "task:done" not in returned_uids


# ============================================================================
# NEXT LEARNING TASK
# ============================================================================


@pytest.mark.asyncio
async def test_get_next_learning_task(learning_service, user_context):
    """Returns next recommended learning task (stub returns None)."""
    result = await learning_service.get_next_learning_task(user_context)
    assert result.is_ok


# ============================================================================
# LEARNING-ALIGNED SUGGESTIONS
# ============================================================================


@pytest.mark.asyncio
async def test_suggest_learning_aligned_tasks(learning_service, learning_position):
    """Generates learning-aligned task suggestions via LearningAlignmentBridge."""
    result = await learning_service.suggest_learning_aligned_tasks(learning_position)

    assert result.is_ok
    suggestions = result.value
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0

    for suggestion in suggestions:
        assert "title" in suggestion
        assert "supporting_path" in suggestion
        assert "learning_alignment_score" in suggestion
        assert "suggestion_reason" in suggestion


@pytest.mark.asyncio
async def test_suggest_tasks_sorted_by_alignment(learning_service, learning_position):
    """Suggestions are sorted descending by learning alignment score."""
    result = await learning_service.suggest_learning_aligned_tasks(learning_position, limit=10)

    assert result.is_ok
    suggestions = result.value
    if len(suggestions) > 1:
        for i in range(len(suggestions) - 1):
            assert (
                suggestions[i]["learning_alignment_score"]
                >= suggestions[i + 1]["learning_alignment_score"]
            )


@pytest.mark.asyncio
async def test_suggest_tasks_covers_active_path(learning_service, learning_position):
    """Suggestions reference the user's active learning path."""
    result = await learning_service.suggest_learning_aligned_tasks(learning_position)

    assert result.is_ok
    suggestions = result.value
    path_names = {s["supporting_path"] for s in suggestions}
    assert "Python Mastery" in path_names


@pytest.mark.asyncio
async def test_multiple_active_paths_suggestions(learning_service):
    """Suggestions are generated across multiple active paths."""
    python_step = PathStep(
        uid="ps:python_basics",
        title="Python Basics",
        intent="Learn Python basics",
        knowledge_uids=("ku.python.basics",),
        mastery_threshold=0.8,
        estimated_hours=10.0,
    )
    path1 = LearningPath(
        uid="lp:python",
        title="Python",
        description="Learn Python programming",
        domain=Domain.TECH,
        metadata={"steps": [python_step]},
    )
    html_step = PathStep(
        uid="ps:html_basics",
        title="HTML Basics",
        intent="Learn HTML basics",
        knowledge_uids=("ku.html.basics",),
        mastery_threshold=0.75,
        estimated_hours=8.0,
    )
    path2 = LearningPath(
        uid="lp:web_dev",
        title="Web Development",
        description="Learn web development",
        domain=Domain.TECH,
        metadata={"steps": [html_step]},
    )
    position = LpPosition(
        user_uid="user:123",
        active_paths=[path1, path2],
        current_steps={"lp:python": python_step, "lp:web_dev": html_step},
        completed_step_uids=set(),
        next_recommended=["ps:python_basics", "ps:html_basics"],
        generated_at=datetime.now(),
        readiness_scores={"ps:python_basics": 0.9, "ps:html_basics": 0.85},
    )

    result = await learning_service.suggest_learning_aligned_tasks(position)

    assert result.is_ok
    suggestions = result.value
    supporting_paths = {s["supporting_path"] for s in suggestions}
    assert "Python" in supporting_paths
    assert "Web Development" in supporting_paths


# ============================================================================
# LEARNING PATH TASK GENERATION
# ============================================================================


@pytest.mark.asyncio
async def test_create_tasks_from_learning_path(learning_service, user_context):
    """Stub returns empty list pending full implementation."""
    result = await learning_service.create_tasks_from_learning_path(
        "lp:python_mastery", user_context
    )
    assert result.is_ok
    assert result.value == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
