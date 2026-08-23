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

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.enums import EntityStatus, EntityType, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import Neo4jProperties
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
        "user_uid": "user_123",
        "title": "Test Task",
        "status": EntityStatus.ACTIVE.value,
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
async def test_complete_task_with_cascade_success(
    progress_service, mock_backend, sample_task, user_context
):
    """Test successful task completion with cascade effects."""
    # Setup
    mock_backend.get.return_value = Result.ok(sample_task.to_dto().to_dict())

    # Setup updated task (completed)
    completed_dto = sample_task.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
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
    assert completed_task.status == EntityStatus.COMPLETED
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
    completed_dto.status = EntityStatus.COMPLETED
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:123", user_context)

    # Verify cascade methods would be called
    # (In real implementation, these update goals, habits, knowledge)
    assert result.is_ok


# ----------------------------------------------------------------------------
# actual_minutes: the completion patch must not erase what it was not told
# ----------------------------------------------------------------------------


def _patch_sent_to_backend(mock_backend) -> dict[str, Any]:
    """The materialized patch handed to ``backend.update`` by the cascade."""
    assert mock_backend.update.await_args is not None, "cascade never wrote"
    return mock_backend.update.await_args.args[1]


@pytest.mark.asyncio
async def test_complete_without_minutes_omits_actual_minutes(
    progress_service, mock_backend, user_context
):
    """An unsupplied ``actual_minutes`` must not appear in the patch at all.

    ``SET n += $updates`` REMOVES a property set to null, so a null in the patch
    would erase a value the task already carries on every completion.
    """
    recorded = Task.from_dto(
        TaskDTO(
            uid="task:recorded",
            user_uid="user_demo",
            title="Recorded Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            actual_minutes=45,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(recorded.to_dto().to_dict())
    completed_dto = recorded.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    result = await progress_service.complete_task_with_cascade("task:recorded", user_context)

    assert result.is_ok
    patch = _patch_sent_to_backend(mock_backend)
    assert "actual_minutes" not in patch
    assert patch["status"] == EntityStatus.COMPLETED.value
    # The stored value survives the completion untouched.
    assert result.value.actual_minutes == 45


@pytest.mark.asyncio
async def test_complete_with_minutes_writes_them(progress_service, mock_backend, user_context):
    """An explicit ``actual_minutes`` is still written."""
    mock_backend.get.return_value = Result.ok(
        Task.from_dto(
            TaskDTO(
                uid="task:timed",
                user_uid="user_demo",
                title="Timed Task",
                priority=Priority.MEDIUM.value,
                status=EntityStatus.ACTIVE.value,
                created_at=datetime.now(),
            )
        )
        .to_dto()
        .to_dict()
    )
    mock_backend.update.return_value = Result.ok(
        {"uid": "task:timed", "user_uid": "user_demo", "title": "Timed Task"}
    )

    result = await progress_service.complete_task_with_cascade(
        "task:timed", user_context, actual_minutes=90
    )

    assert result.is_ok
    assert _patch_sent_to_backend(mock_backend)["actual_minutes"] == 90


@pytest.mark.asyncio
async def test_zero_minutes_is_stored_and_reported_not_dropped(
    progress_service, mock_backend, user_context
):
    """0 is a reported duration, not a missing one — node and event must agree.

    ``ge=0`` makes 0 a legal value at the boundary, and the patch guard is
    ``is not None``, so 0 reaches the node. A truthiness check when building
    ``TaskCompleted`` would have stored 0 while telling subscribers the
    duration was never reported.
    """
    published: list[Any] = []

    class _Bus:
        async def publish_async(self, event: Any) -> None:
            published.append(event)

    service = TasksProgressService(backend=mock_backend, event_bus=_Bus())
    zero = Task.from_dto(
        TaskDTO(
            uid="task:zero",
            user_uid="user_demo",
            title="Zero Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(zero.to_dto().to_dict())
    mock_backend.update.return_value = Result.ok(
        {"uid": "task:zero", "user_uid": "user_demo", "title": "Zero Task"}
    )

    result = await service.complete_task_with_cascade("task:zero", user_context, actual_minutes=0)

    assert result.is_ok
    assert _patch_sent_to_backend(mock_backend)["actual_minutes"] == 0
    assert published[-1].completion_time_seconds == 0


@pytest.mark.asyncio
async def test_completion_date_gate_still_holds_without_minutes(
    progress_service, mock_backend, user_context
):
    """#1125's transition gate is unchanged by the omitted-minutes patch.

    A first completion stamps ``completion_date``; re-posting the complete on an
    already-completed task is not a transition and must not re-date it.
    """
    active = Task.from_dto(
        TaskDTO(
            uid="task:gate",
            user_uid="user_demo",
            title="Gate Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(active.to_dto().to_dict())
    mock_backend.update.return_value = Result.ok(
        {"uid": "task:gate", "user_uid": "user_demo", "title": "Gate Task"}
    )

    first = await progress_service.complete_task_with_cascade("task:gate", user_context)
    assert first.is_ok
    assert _patch_sent_to_backend(mock_backend)["completion_date"] == date.today().isoformat()

    already = active.to_dto()
    already.status = EntityStatus.COMPLETED
    mock_backend.get.return_value = Result.ok(already.to_dict())
    mock_backend.update.reset_mock()

    repeat = await progress_service.complete_task_with_cascade("task:gate", user_context)

    assert repeat.is_ok
    assert "completion_date" not in _patch_sent_to_backend(mock_backend)


@pytest.mark.asyncio
async def test_is_repeat_is_the_inverse_of_the_stamp_gate(mock_backend, user_context):
    """One transition evaluation feeds both the stamp and ``TaskCompleted.is_repeat``.

    A first complete is a transition: it stamps ``completion_date`` and publishes
    ``is_repeat=False``. Re-posting the complete on an already-completed task is
    not a transition: no re-stamp, and ``is_repeat=True`` so the counting
    subscribers can decline to count it twice. The cascade and the write run
    either way — a repeat complete stays a real complete (the repair path).
    """
    published: list[Any] = []

    class _Bus:
        async def publish_async(self, event: Any) -> None:
            published.append(event)

    service = TasksProgressService(backend=mock_backend, event_bus=_Bus())
    active = Task.from_dto(
        TaskDTO(
            uid="task:repeat",
            user_uid="user_demo",
            title="Repeat Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )
    mock_backend.get.return_value = Result.ok(active.to_dto().to_dict())
    mock_backend.update.return_value = Result.ok(
        {"uid": "task:repeat", "user_uid": "user_demo", "title": "Repeat Task"}
    )

    first = await service.complete_task_with_cascade("task:repeat", user_context)

    assert first.is_ok
    assert _patch_sent_to_backend(mock_backend)["completion_date"] == date.today().isoformat()
    assert published[-1].is_repeat is False

    already = active.to_dto()
    already.status = EntityStatus.COMPLETED
    mock_backend.get.return_value = Result.ok(already.to_dict())
    mock_backend.update.reset_mock()

    repeat = await service.complete_task_with_cascade("task:repeat", user_context)

    assert repeat.is_ok
    # The write still happens — the cascade is deliberately re-run as a repair path.
    patch_sent = _patch_sent_to_backend(mock_backend)
    assert patch_sent["status"] == EntityStatus.COMPLETED.value
    assert "completion_date" not in patch_sent
    assert published[-1].is_repeat is True
    assert len(published) == 2


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
        user_uid="user_123",
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
    result = await progress_service.record_task_completion("task:123", "user_123")

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


@pytest.mark.asyncio
async def test_complete_task_updates_goal(progress_service, mock_backend, user_context):
    """Test that completing a task triggers goal progress update."""
    # Setup - task that contributes to goal
    goal_task = Task.from_dto(
        TaskDTO(
            uid="task:goal_task",
            user_uid="user_demo",
            title="Goal Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.ACTIVE.value,
            fulfills_goal_uid="goal:learn_python",
            goal_progress_contribution=0.3,
            completion_updates_goal=True,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(goal_task.to_dto().to_dict())

    completed_dto = goal_task.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:goal_task", user_context)

    # Verify
    assert result.is_ok
    # In real implementation, _update_goal_progress would be called


@pytest.mark.asyncio
async def test_complete_task_reinforces_habit(progress_service, mock_backend, user_context):
    """Completing a task reinforces its linked habit via the REINFORCES_HABIT edge."""
    from core.models.relationship_names import RelationshipName

    # Setup - task that reinforces a habit (linkage is the graph edge, not a property)
    habit_task = Task.from_dto(
        TaskDTO(
            uid="task:habit_task",
            user_uid="user_demo",
            title="Habit Task",
            priority=Priority.MEDIUM.value,
            status=EntityStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(habit_task.to_dto().to_dict())

    completed_dto = habit_task.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # The completion handler queries the REINFORCES_HABIT edge for the linked habit.
    async def _related(uid, relationship, direction="outgoing"):
        if relationship == RelationshipName.REINFORCES_HABIT:
            return Result.ok(["habit:daily_code"])
        return Result.ok([])

    mock_backend.get_related_uids = AsyncMock(side_effect=_related)

    # Execute
    result = await progress_service.complete_task_with_cascade(
        "task:habit_task", user_context, quality_score=5
    )

    # Verify the habit edge was queried (reinforcement path fired)
    assert result.is_ok
    habit_calls = [
        c
        for c in mock_backend.get_related_uids.await_args_list
        if c.args[1] == RelationshipName.REINFORCES_HABIT
    ]
    assert habit_calls, "completion should query the REINFORCES_HABIT edge"


@pytest.mark.asyncio
async def test_complete_task_updates_knowledge_mastery(
    progress_service, mock_backend, user_context
):
    """Test that completing a task updates knowledge mastery."""
    # Setup - task that checks knowledge mastery
    mastery_task = Task.from_dto(
        TaskDTO(
            uid="task:mastery_task",
            user_uid="user_demo",
            title="Mastery Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.ACTIVE.value,
            knowledge_mastery_check=True,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(mastery_task.to_dto().to_dict())

    completed_dto = mastery_task.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
    mock_backend.update.return_value = Result.ok(completed_dto.to_dict())

    # Execute
    result = await progress_service.complete_task_with_cascade("task:mastery_task", user_context)

    # Verify
    assert result.is_ok
    # In real implementation, _update_knowledge_mastery would be called for each knowledge UID


# ----------------------------------------------------------------------------
# _trigger_task: the cascade schedules dependents, it never reopens finished ones
# ----------------------------------------------------------------------------
#
# Latent on the live graph today (0 TRIGGERS_ON_COMPLETION edges), so these tests
# carry the whole proof.

_TASK_STATUSES = EntityType.TASK.valid_statuses()

#: Derived from the enum, never typed out: the service decides the skip with
#: ``EntityStatus.is_terminal()``, and an inline ``== COMPLETED`` literal would
#: pass the completed case while failing cancelled and failed.
_TERMINAL_DEPENDENT_STATUSES = [s for s in EntityStatus if s in _TASK_STATUSES and s.is_terminal()]
_LIVE_DEPENDENT_STATUSES = [s for s in EntityStatus if s in _TASK_STATUSES and not s.is_terminal()]


def _task(uid: str, status: EntityStatus, **fields: Any) -> Task:
    """Build a Task the way a backend read does — status as the enum.

    ``**fields`` is forwarded verbatim to ``TaskDTO``, whose ~40 optional fields
    span dates, ints, strings and enums — genuinely heterogeneous, which is the
    one thing ``Any`` is for.
    """  # boundary: dto-kwargs
    return Task.from_dto(
        TaskDTO(
            uid=uid,
            user_uid="user_demo",
            title=f"Task {uid}",
            priority=Priority.MEDIUM.value,
            status=status,
            created_at=datetime.now(),
            **fields,
        )
    )


class _FakeTaskGraph:
    """A node store with Neo4j write semantics that hands back domain models.

    Two fidelity points the plain dict-returning fixture above does not carry,
    both load-bearing here:

    * ``UniversalNeo4jBackend.get``/``update`` return ``from_neo4j_node`` domain
      models, not property dicts — and ``_trigger_task`` reads ``Task.status``
      straight off the Result of ``self.get`` (which casts rather than converts).
    * ``SET n += $updates`` REMOVES a property set to null and leaves untouched
      keys alone — the invariant under test is about a property surviving (or
      not surviving) a write.
    """

    def __init__(self, *tasks: Task) -> None:
        self.nodes: dict[str, Neo4jProperties] = {t.uid: t.to_dto().to_dict() for t in tasks}
        self.writes: list[tuple[str, Neo4jProperties]] = []

    def snapshot(self, uid: str) -> Neo4jProperties:
        """The stored properties of one node, detached from the store."""
        return dict(self.nodes[uid])

    async def get(self, uid: str) -> Result[Task | None]:
        node = self.nodes.get(uid)
        return Result.ok(from_neo4j_node(dict(node), Task) if node is not None else None)

    async def update(self, uid: str, changes: Neo4jProperties) -> Result[Task]:
        self.writes.append((uid, dict(changes)))
        node = self.nodes[uid]
        for key, value in changes.items():
            if value is None:
                node.pop(key, None)
            else:
                node[key] = value
        return Result.ok(from_neo4j_node(dict(node), Task))


def _wire_trigger_cascade(mock_backend: Mock, dependent: Task) -> tuple[Task, _FakeTaskGraph]:
    """Wire an upstream task that TRIGGERS_ON_COMPLETION the given dependent."""
    upstream = _task("task:upstream", EntityStatus.ACTIVE)
    graph = _FakeTaskGraph(upstream, dependent)
    mock_backend.get = AsyncMock(side_effect=graph.get)
    mock_backend.update = AsyncMock(side_effect=graph.update)

    async def _related(
        uid: str, relationship: RelationshipName, direction: str = "outgoing"
    ) -> Result[list[str]]:
        if uid == upstream.uid and relationship == RelationshipName.TRIGGERS_ON_COMPLETION:
            return Result.ok([dependent.uid])
        return Result.ok([])

    mock_backend.get_related_uids = AsyncMock(side_effect=_related)
    return upstream, graph


@pytest.mark.asyncio
async def test_trigger_task_leaves_completed_dependent_and_its_stamp_untouched(
    progress_service, mock_backend, user_context
):
    """A completed dependent keeps BOTH its status and its ``completion_date``.

    The cascade writes through the generic CRUD, which does not run the
    six-chokepoint completion stamping, so a blind ``status=scheduled`` would
    move a completed dependent out of COMPLETED while leaving the stamp behind —
    breaking the invariant that ``completion_date`` is non-null exactly when the
    task is completed. This fires on a FIRST completion of the upstream task, so
    ``TaskCompleted.is_repeat`` does not cover it.
    """
    dependent = _task("task:dependent", EntityStatus.COMPLETED, completion_date=date(2026, 8, 1))
    upstream, graph = _wire_trigger_cascade(mock_backend, dependent)
    before = graph.snapshot(dependent.uid)

    result = await progress_service.complete_task_with_cascade(upstream.uid, user_context)

    assert result.is_ok
    assert [uid for uid, _ in graph.writes] == [upstream.uid], "the dependent must not be written"
    assert graph.snapshot(dependent.uid) == before
    assert graph.nodes[dependent.uid]["status"] == EntityStatus.COMPLETED.value
    assert graph.nodes[dependent.uid]["completion_date"] == before["completion_date"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal",
    _TERMINAL_DEPENDENT_STATUSES,
    ids=[s.value for s in _TERMINAL_DEPENDENT_STATUSES],
)
async def test_trigger_task_skips_every_terminal_dependent(
    progress_service, mock_backend, user_context, terminal
):
    """The gate is ``is_terminal()``, not a COMPLETED literal.

    Cancelled and failed dependents are equally not this cascade's to resurrect,
    and keying on the enum's own predicate means a new terminal status is honored
    without editing the service.
    """
    dependent = _task("task:dependent", terminal)
    upstream, graph = _wire_trigger_cascade(mock_backend, dependent)

    result = await progress_service.complete_task_with_cascade(upstream.uid, user_context)

    assert result.is_ok
    assert [uid for uid, _ in graph.writes] == [upstream.uid]
    assert graph.nodes[dependent.uid]["status"] == terminal.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "live",
    _LIVE_DEPENDENT_STATUSES,
    ids=[s.value for s in _LIVE_DEPENDENT_STATUSES],
)
async def test_trigger_task_still_schedules_non_terminal_dependent(
    progress_service, mock_backend, user_context, live
):
    """The cascade still does its job — nothing but a terminal state is skipped."""
    dependent = _task("task:dependent", live)
    upstream, graph = _wire_trigger_cascade(mock_backend, dependent)

    result = await progress_service.complete_task_with_cascade(upstream.uid, user_context)

    assert result.is_ok
    dependent_writes = [changes for uid, changes in graph.writes if uid == dependent.uid]
    assert dependent_writes == [{"status": EntityStatus.SCHEDULED.value}]
    assert graph.nodes[dependent.uid]["status"] == EntityStatus.SCHEDULED.value


@pytest.mark.asyncio
async def test_trigger_task_survives_a_dangling_dependent_edge(
    progress_service, mock_backend, user_context
):
    """A TRIGGERS_ON_COMPLETION edge pointing at nothing fails the read, not the cascade."""
    dependent = _task("task:dependent", EntityStatus.ACTIVE)
    upstream, graph = _wire_trigger_cascade(mock_backend, dependent)
    del graph.nodes[dependent.uid]

    result = await progress_service.complete_task_with_cascade(upstream.uid, user_context)

    assert result.is_ok
    assert [uid for uid, _ in graph.writes] == [upstream.uid]


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
            user_uid="user_demo",
            title="Prerequisite Task",
            priority=Priority.HIGH.value,
            status=EntityStatus.ACTIVE.value,
            created_at=datetime.now(),
        )
    )

    mock_backend.get.return_value = Result.ok(task.to_dto().to_dict())

    completed_dto = task.to_dto()
    completed_dto.status = EntityStatus.COMPLETED
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
