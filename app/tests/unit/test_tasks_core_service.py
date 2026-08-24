#!/usr/bin/env python3
"""
TasksCoreService Test Suite
===========================

Tests for core CRUD operations in TasksCoreService.

This service handles:
- Task creation with automatic knowledge inference
- Task retrieval (single and multiple)
- Task updates
- Task deletion
- Task listing with filters
"""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.task.task import Task as Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_inference_result import TaskInferenceResult
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Errors, Result
from tests.helpers.status_guarded_backend import echoing_guarded_write

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock tasks backend.

    TasksOperations protocol supports BOTH patterns:
    1. Generic BackendOperations: get(), create(), update(), delete(), list()
    2. Domain entry points: get_task(), create_task(), update_task(), delete_task()

    TasksCoreService mixes both:
    - get_task() -> calls self.get() -> uses backend.get()
    - update_task() -> calls backend.get_task() AND backend.update_task()
    - list_tasks() -> calls self.list() -> uses backend.list()
    """
    backend = Mock()

    # ✅ Generic BackendOperations methods (per base_protocols.py)
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.update = AsyncMock(return_value=Result.ok({}))
    # ADR-087: the status chokepoint writes through the guarded primitive. This
    # answers it from the same ``get``/``update`` return values the tests configure,
    # so the prior it reports and the entity it returns stay consistent with them.
    backend.update_with_status_guard = echoing_guarded_write(backend)
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))  # Returns (items, count) tuple

    # ✅ Domain-specific entry points (also in TasksOperations protocol)
    backend.create_task = AsyncMock(return_value=Result.ok({}))
    backend.get_task = AsyncMock(return_value=Result.ok(None))
    backend.update_task = AsyncMock(return_value=Result.ok({}))
    backend.delete_task = AsyncMock(return_value=Result.ok(True))
    backend.get_user_tasks = AsyncMock(return_value=Result.ok([]))
    # get_user_entities returns (entities, total_count) tuple
    backend.get_user_entities = AsyncMock(return_value=Result.ok(([], 0)))

    # ✅ Relationship operations
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.create_relationship = AsyncMock(return_value=Result.ok(True))
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))

    return backend


@pytest.fixture
def mock_ku_inference_service() -> Any:
    """Create a mock knowledge inference service.

    ADR-065: inference now returns ``Result[TaskInferenceResult]`` carrying
    only the enrichment fields. The default mock returns an empty result
    (no enrichment) so passthrough callers see the input task unchanged.
    Tests can override this to assert specific enrichment is applied.
    """
    service = Mock()
    # enhance_task_dto_with_inference is sync (pure in-memory inference, SKUEL029) —
    # a plain Mock returns the Result directly; callers no longer await it.
    service.enhance_task_dto_with_inference = Mock(return_value=Result.ok(TaskInferenceResult()))
    return service


@pytest.fixture
def core_service(mock_backend, mock_ku_inference_service) -> TasksCoreService:
    """Create TasksCoreService instance with mocked dependencies."""
    return TasksCoreService(backend=mock_backend, ku_inference_service=mock_ku_inference_service)


@pytest.fixture
def sample_task_dto() -> TaskDTO:
    """Create a sample TaskDTO."""
    return TaskDTO(
        uid="task:123",
        user_uid="user_demo",
        title="Test Task",
        priority=Priority.HIGH.value,
        status=EntityStatus.DRAFT.value,
        due_date=date.today() + timedelta(days=7),
        duration_minutes=60,
        project="Test Project",
        tags=["test", "sample"],
        created_at=datetime.now(),
    )


@pytest.fixture
def sample_task_request() -> TaskCreateRequest:
    """Create a sample TaskCreateRequest."""
    return TaskCreateRequest(
        title="New Test Task",
        priority=Priority.MEDIUM,
        due_date=date.today() + timedelta(days=3),
        duration_minutes=90,
        project="Sample Project",
        tags=["new", "test"],
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


def test_init_with_backend(mock_backend):
    """Test service initialization with required backend."""
    service = TasksCoreService(backend=mock_backend)
    assert service.backend == mock_backend
    assert service.ku_inference_service is None


def test_init_without_backend():
    """Test service initialization fails without backend."""
    with pytest.raises(ValueError, match=r"tasks\.core backend is REQUIRED"):
        TasksCoreService(backend=None)


def test_init_with_optional_services(mock_backend, mock_ku_inference_service):
    """Test service initialization with optional services."""
    service = TasksCoreService(backend=mock_backend, ku_inference_service=mock_ku_inference_service)
    assert service.ku_inference_service == mock_ku_inference_service


# ============================================================================
# CREATE TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_task_success(
    core_service, mock_backend, sample_task_request, sample_task_dto
):
    """Test successful task creation."""
    # Setup - service calls backend.create() (generic BackendOperations method), which
    # returns the DOMAIN MODEL: UniversalNeo4jBackend._create_node ends in
    # from_neo4j_node(props, entity_class). Returning raw props here would only work
    # because the old create path re-converted them via _create_and_convert.
    mock_backend.create.return_value = Result.ok(Task.from_dto(sample_task_dto))

    # Execute
    result = await core_service.create_task(sample_task_request, user_uid="user_demo")

    # Verify
    assert result.is_ok
    task = result.value
    assert isinstance(task, Task)
    assert task.title == sample_task_dto.title
    mock_backend.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_with_knowledge_inference(
    core_service, mock_backend, mock_ku_inference_service, sample_task_request, sample_task_dto
):
    """Test task creation with knowledge inference applied.

    ADR-065: inference returns a typed TaskInferenceResult; the service
    applies it via dataclasses.replace before persistence. We assert the
    enrichment fields land on the persisted task.
    """
    # Setup - inference produces enrichment for the task draft
    enrichment = TaskInferenceResult(
        knowledge_confidence_scores={"ku.programming.python": 0.85},
        knowledge_inference_metadata={"inference_version": "2.4_advanced"},
        learning_opportunities_count=2,
    )
    mock_ku_inference_service.enhance_task_dto_with_inference.return_value = Result.ok(enrichment)

    # The backend echoes back whatever the service sent; we read the payload
    # the service actually wrote so the assertions reflect the applied
    # enrichment, not a hard-coded sample.
    def _echo_create(payload):
        return Result.ok(payload)

    mock_backend.create.side_effect = _echo_create

    # Execute
    result = await core_service.create_task(sample_task_request, user_uid="user_demo")

    # Verify
    assert result.is_ok
    task = result.value
    assert task.learning_opportunities_count == 2
    assert task.knowledge_confidence_scores == {"ku.programming.python": 0.85}
    mock_ku_inference_service.enhance_task_dto_with_inference.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_inference_failure_is_fail_fast(
    core_service, mock_backend, mock_ku_inference_service, sample_task_request, sample_task_dto
):
    """Test task creation fails when knowledge inference fails (fail-fast pattern).

    SKUEL follows fail-fast architecture: if inference is configured but fails,
    the entire operation fails. This prevents silent degradation.
    """
    # Setup - inference service raises exception
    mock_ku_inference_service.enhance_task_dto_with_inference.side_effect = Exception(
        "Inference failed"
    )
    mock_backend.create.return_value = Result.ok(sample_task_dto.to_dict())

    # Execute
    result = await core_service.create_task(sample_task_request, user_uid="user_demo")

    # Verify - fail-fast: inference failure → create failure
    assert result.is_error
    # Backend create should NOT have been called since inference failed first
    mock_backend.create.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_backend_error(core_service, mock_backend, sample_task_request):
    """Test task creation with backend error."""
    # Setup
    mock_backend.create.return_value = Result.fail(Errors.database("create", "Database error"))

    # Execute
    result = await core_service.create_task(sample_task_request, user_uid="user_demo")

    # Verify
    assert result.is_error


# ============================================================================
# GET TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_success(core_service, mock_backend, sample_task_dto):
    """Test successful task retrieval."""
    # Setup - UniversalNeo4jBackend.get() returns Result[Task], not dict
    sample_task = Task.from_dto(sample_task_dto)
    mock_backend.get.return_value = Result.ok(sample_task)

    # Execute
    result = await core_service.get_task("task:123")

    # Verify
    assert result.is_ok
    task = result.value
    assert task.uid == "task:123"
    assert task.title == sample_task_dto.title
    mock_backend.get.assert_called_once_with("task:123")


@pytest.mark.asyncio
async def test_get_task_not_found(core_service, mock_backend):
    """Test task retrieval when task doesn't exist."""
    # Setup
    mock_backend.get.return_value = Result.ok(None)

    # Execute
    result = await core_service.get_task("task:999")

    # Verify
    assert result.is_error


@pytest.mark.asyncio
async def test_get_task_backend_error(core_service, mock_backend):
    """Test task retrieval with backend error."""
    # Setup
    mock_backend.get.return_value = Result.fail(Errors.database("get", "Connection error"))

    # Execute
    result = await core_service.get_task("task:123")

    # Verify
    assert result.is_error


# ============================================================================
# GET USER TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_tasks_success(core_service, mock_backend, sample_task_dto):
    """Test successful retrieval of all user tasks."""
    # Setup - return multiple tasks
    # get_user_entities returns (entities, total_count) tuple
    task_data_list = [
        sample_task_dto.to_dict(),
        {**sample_task_dto.to_dict(), "uid": "task:124", "title": "Task 2"},
        {**sample_task_dto.to_dict(), "uid": "task:125", "title": "Task 3"},
    ]
    mock_backend.get_user_entities.return_value = Result.ok((task_data_list, 3))

    # Execute
    result = await core_service.get_user_tasks("user_123")

    # Verify
    assert result.is_ok
    tasks = result.value
    assert len(tasks) == 3
    assert all(isinstance(t, Task) for t in tasks)
    assert tasks[1].title == "Task 2"


@pytest.mark.asyncio
async def test_get_user_tasks_empty(core_service, mock_backend):
    """Test retrieval when user has no tasks."""
    # Setup - get_user_entities returns (entities, total_count) tuple
    mock_backend.get_user_entities.return_value = Result.ok(([], 0))

    # Execute
    result = await core_service.get_user_tasks("user_999")

    # Verify
    assert result.is_ok
    assert len(result.value) == 0


# ============================================================================
# LIST TASKS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_no_filters(core_service, mock_backend, sample_task_dto):
    """Test listing tasks without filters."""
    # Setup - backend.list() returns (items, total_count) tuple
    task_list = [sample_task_dto.to_dict() for _ in range(5)]
    mock_backend.list.return_value = Result.ok((task_list, 5))

    # Execute
    result = await core_service.list_tasks()

    # Verify
    assert result.is_ok
    assert len(result.value) == 5
    mock_backend.list.assert_called_once()


@pytest.mark.asyncio
async def test_list_tasks_with_filters(core_service, mock_backend, sample_task_dto):
    """Test listing tasks with filters."""
    # Setup - backend.list() returns (items, total_count) tuple
    filters = {"priority": Priority.HIGH.value, "status": EntityStatus.DRAFT.value}
    filtered_tasks = [sample_task_dto.to_dict()]
    mock_backend.list.return_value = Result.ok((filtered_tasks, 1))

    # Execute
    result = await core_service.list_tasks(filters=filters, limit=50)

    # Verify
    assert result.is_ok
    assert len(result.value) == 1
    mock_backend.list.assert_called_once()


# ============================================================================
# UPDATE TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_success(core_service, mock_backend, sample_task_dto):
    """Test successful task update."""
    # Setup
    intent = TaskUpdateIntent(title="Updated Title", priority=Priority.LOW.value)
    updated_dto = TaskDTO.from_dict(sample_task_dto.to_dict())
    updated_dto.title = "Updated Title"
    updated_dto.priority = Priority.LOW.value

    # update_task calls get() for priority change detection, then update()
    mock_backend.get.return_value = Result.ok(sample_task_dto.to_dict())
    mock_backend.update.return_value = Result.ok(updated_dto.to_dict())

    # Execute
    result = await core_service.update_task("task:123", intent)

    # Verify
    assert result.is_ok
    task = result.value
    assert task.title == "Updated Title"
    assert task.priority == Priority.LOW
    # The intent is materialized to a partial patch at the single write seam. No
    # status key, so the guard carries no conditional patches (ADR-087).
    (uid, changes, guard) = mock_backend.update_with_status_guard.call_args.args
    assert uid == "task:123"
    assert changes == {"title": "Updated Title", "priority": Priority.LOW.value}
    assert guard.has_patches() is False


@pytest.mark.asyncio
async def test_update_task_not_found(core_service, mock_backend):
    """Test update when task doesn't exist."""
    # Setup - service calls backend.update() (generic BackendOperations method)
    mock_backend.update.return_value = Result.fail(Errors.not_found("Task", "task:999"))

    # Execute
    result = await core_service.update_task("task:999", TaskUpdateIntent(title="New Title"))

    # Verify
    assert result.is_error


# ============================================================================
# UPDATE VALIDATION TESTS (overdue-priority protection)
# ============================================================================
#
# The rule lives on ``TasksCoreService._validate_update`` but is NOT reached
# through the inherited CRUD hook: the facade routes ``update`` /
# ``update_for_user`` to ``update_task``, which calls the hook explicitly. These
# tests therefore all drive ``update_task`` — the live path — and assert the
# write did or did not happen, not that the hook returned something.

_YESTERDAY = date.today() - timedelta(days=1)
_TOMORROW = date.today() + timedelta(days=1)


def _stored_task(
    *,
    priority: str | None,
    due_date: date | None,
    status: str = EntityStatus.ACTIVE.value,
) -> dict[str, Any]:
    """A prior-state row as ``backend.get`` returns it (dict, not a model)."""
    return TaskDTO(
        uid="task:123",
        user_uid="user_demo",
        title="Test Task",
        priority=priority,
        status=status,
        due_date=due_date,
    ).to_dict()


@pytest.mark.asyncio
async def test_update_task_refuses_priority_decrease_on_overdue_task(core_service, mock_backend):
    """The live path enforces the rule: an overdue task's priority cannot be lowered."""
    mock_backend.get.return_value = Result.ok(
        _stored_task(priority=Priority.HIGH.value, due_date=_YESTERDAY)
    )

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(priority=Priority.LOW.value)
    )

    assert result.is_error
    assert "Cannot decrease priority of overdue tasks" in result.expect_error().message
    mock_backend.update.assert_not_called()  # validation runs BEFORE the write


@pytest.mark.asyncio
async def test_update_task_refuses_priority_clear_on_overdue_task(core_service, mock_backend):
    """Clearing the priority is measured as MEDIUM, not skipped — it cannot duck the rule."""
    mock_backend.get.return_value = Result.ok(
        _stored_task(priority=Priority.CRITICAL.value, due_date=_YESTERDAY)
    )

    result = await core_service.update_task("task:123", TaskUpdateIntent(priority=None))

    assert result.is_error
    mock_backend.update_with_status_guard.assert_not_called()


@pytest.mark.asyncio
async def test_update_task_allows_priority_decrease_when_not_overdue(core_service, mock_backend):
    """Lowering the priority of a task that is not overdue is ordinary re-planning."""
    mock_backend.get.return_value = Result.ok(
        _stored_task(priority=Priority.HIGH.value, due_date=_TOMORROW)
    )
    mock_backend.update.return_value = Result.ok(
        _stored_task(priority=Priority.LOW.value, due_date=_TOMORROW)
    )

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(priority=Priority.LOW.value)
    )

    assert result.is_ok
    mock_backend.update_with_status_guard.assert_called_once_with(
        "task:123", {"priority": Priority.LOW.value}, ANY
    )


@pytest.mark.asyncio
async def test_update_task_allows_priority_increase_on_overdue_task(core_service, mock_backend):
    """The rule is one-directional — raising an overdue task's priority is the point."""
    mock_backend.get.return_value = Result.ok(
        _stored_task(priority=Priority.LOW.value, due_date=_YESTERDAY)
    )
    mock_backend.update.return_value = Result.ok(
        _stored_task(priority=Priority.CRITICAL.value, due_date=_YESTERDAY)
    )

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(priority=Priority.CRITICAL.value)
    )

    assert result.is_ok
    mock_backend.update_with_status_guard.assert_called_once_with(
        "task:123", {"priority": Priority.CRITICAL.value}, ANY
    )


@pytest.mark.asyncio
async def test_update_task_allows_priority_decrease_on_completed_past_due_task(
    core_service, mock_backend
):
    """``Task.is_overdue()`` excludes completed tasks — a finished task is not overdue.

    Guards the deliberate narrowing: with terminal-state protection deleted, a raw
    ``due_date < today`` predicate would have invented a NEW prohibition on past-due
    completed tasks that the deleted rule had merely made unreachable.
    """
    mock_backend.get.return_value = Result.ok(
        _stored_task(
            priority=Priority.HIGH.value,
            due_date=_YESTERDAY,
            status=EntityStatus.COMPLETED.value,
        )
    )
    mock_backend.update.return_value = Result.ok(
        _stored_task(
            priority=Priority.LOW.value,
            due_date=_YESTERDAY,
            status=EntityStatus.COMPLETED.value,
        )
    )

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(priority=Priority.LOW.value)
    )

    assert result.is_ok
    mock_backend.update_with_status_guard.assert_called_once_with(
        "task:123", {"priority": Priority.LOW.value}, ANY
    )


@pytest.mark.asyncio
async def test_update_task_reopens_a_completed_task(core_service, mock_backend):
    """Terminal is not frozen: no rule refuses a change to a completed task.

    The deleted terminal-state rule would have blocked exactly this — the status
    re-post that reopens a just-completed task.
    """
    mock_backend.get.return_value = Result.ok(
        _stored_task(
            priority=Priority.HIGH.value, due_date=_TOMORROW, status=EntityStatus.COMPLETED.value
        )
    )
    mock_backend.update.return_value = Result.ok(
        _stored_task(
            priority=Priority.HIGH.value, due_date=_TOMORROW, status=EntityStatus.ACTIVE.value
        )
    )

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(status=EntityStatus.ACTIVE.value)
    )

    assert result.is_ok
    (_uid, written, guard) = mock_backend.update_with_status_guard.call_args.args
    assert written["status"] == EntityStatus.ACTIVE.value
    # The reopen clear is now a CONDITION the write evaluates against the prior it
    # captures under the node lock, not a value resolved from a read beforehand.
    assert guard.patch_if_prior_in == (frozenset({"completed"}), {"completion_date": None})


@pytest.mark.asyncio
async def test_update_task_without_priority_change_skips_the_rule(core_service, mock_backend):
    """A non-priority update on an overdue task is unaffected — and reads nothing."""
    mock_backend.update.return_value = Result.ok(
        _stored_task(priority=Priority.HIGH.value, due_date=_YESTERDAY)
    )

    result = await core_service.update_task("task:123", TaskUpdateIntent(title="Updated Title"))

    assert result.is_ok
    mock_backend.get.assert_not_called()  # no prior state needed, so none is fetched
    mock_backend.update_with_status_guard.assert_called_once_with(
        "task:123", {"title": "Updated Title"}, ANY
    )


@pytest.mark.asyncio
async def test_update_task_fails_fast_when_the_prior_read_fails(core_service, mock_backend):
    """A failed prior read is never silently read as 'no rule applies'."""
    mock_backend.get.return_value = Result.fail(Errors.database("get", "connection lost"))

    result = await core_service.update_task(
        "task:123", TaskUpdateIntent(priority=Priority.LOW.value)
    )

    assert result.is_error
    mock_backend.update_with_status_guard.assert_not_called()


# ============================================================================
# DELETE TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_task_success(core_service, mock_backend, sample_task_dto):
    """Test successful task deletion."""
    # Setup - delete_task calls get() first, then delete() with cascade=True
    mock_backend.get.return_value = Result.ok(sample_task_dto.to_dict())
    mock_backend.delete.return_value = Result.ok(True)

    # Execute
    result = await core_service.delete_task("task:123")

    # Verify
    assert result.is_ok
    assert result.value is True
    mock_backend.delete.assert_called_once_with("task:123", cascade=True)


@pytest.mark.asyncio
async def test_delete_task_not_found(core_service, mock_backend):
    """Test deletion when task doesn't exist."""
    # Setup - delete_task calls get() first, which fails for non-existent task
    mock_backend.get.return_value = Result.fail(Errors.not_found("Task", "task:999"))

    # Execute
    result = await core_service.delete_task("task:999")

    # Verify
    assert result.is_error


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_update_delete_workflow(
    core_service, mock_backend, sample_task_request, sample_task_dto
):
    """Test complete workflow: create, update, delete."""
    # Create - service uses backend.create(), which returns the domain model
    mock_backend.create.return_value = Result.ok(Task.from_dto(sample_task_dto))
    create_result = await core_service.create_task(sample_task_request, user_uid="user_demo")
    assert create_result.is_ok
    task_uid = create_result.value.uid

    # Update - service uses backend.update()
    updated_dto = TaskDTO.from_dict(sample_task_dto.to_dict())
    updated_dto.title = "Modified Title"
    mock_backend.update.return_value = Result.ok(updated_dto.to_dict())
    update_result = await core_service.update_task(
        task_uid, TaskUpdateIntent(title="Modified Title")
    )
    assert update_result.is_ok
    assert update_result.value.title == "Modified Title"

    # Delete - service uses backend.get() then backend.delete(cascade=True)
    mock_backend.get.return_value = Result.ok(sample_task_dto.to_dict())
    mock_backend.delete.return_value = Result.ok(True)
    delete_result = await core_service.delete_task(task_uid)
    assert delete_result.is_ok


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
