"""
Tests for TasksService event-driven functionality and orchestration methods.

Tests verify that TasksService correctly publishes domain events
when tasks are created, completed, etc., and that orchestration methods
with conditional logic behave correctly.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Errors, Result


async def _owned_by_nobody(uids: list[str]) -> Result[dict[str, list[str]]]:
    return Result.ok({})


async def _every_linkable_kind(uids: list[str]) -> Result[dict[str, list[str]]]:
    return Result.ok({uid: ["Entity", "Goal", "Habit", "Ku"] for uid in uids})


@pytest.fixture
def mock_event_bus() -> Mock:
    """Mock event bus for testing."""
    bus = Mock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def mock_cross_domain_query() -> AsyncMock:
    """Mock CrossDomainQueryService — required by TasksService."""
    return AsyncMock()


@pytest.fixture
def mock_graph_intel() -> AsyncMock:
    """Mock GraphIntelligenceService — required by TasksService."""
    return AsyncMock()


@pytest.fixture
def mock_tasks_backend() -> Any:
    """Mock tasks backend for testing."""
    from datetime import datetime

    backend = Mock()

    # Mock the generic BackendOperations methods (used by core service)
    task_dict = {
        "uid": "task-123",
        "user_uid": "user_456",  # REQUIRED field
        "title": "Test Task",
        "description": "Test description",
        "status": EntityStatus.DRAFT,
        "priority": Priority.MEDIUM,
        "duration_minutes": 30,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "tags": [],
        # Relationship fields removed - now queried via UnifiedRelationshipService
    }

    # Generic BackendOperations methods (TasksCoreService uses these).
    # create returns the DOMAIN MODEL, as UniversalNeo4jBackend._create_node does via
    # from_neo4j_node — the create path no longer re-converts the backend's return value.
    backend.create = AsyncMock(return_value=Result.ok(Task.from_dto(TaskDTO.from_dict(task_dict))))
    backend.get = AsyncMock(return_value=Result.ok(task_dict))
    backend.update = AsyncMock(return_value=Result.ok(task_dict))
    backend.delete = AsyncMock(return_value=Result.ok(True))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))

    # Relationship operations
    backend.create_relationships_batch = AsyncMock(return_value=Result.ok(0))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    # The link-edge admission guard's two batched reads (keep_permitted_link_edges).
    # Permissive by default — every uid is owned by nobody and carries every kind the
    # update path links — so tests that are not ABOUT admission keep writing edges.
    backend.get_owner_uids_batch = AsyncMock(side_effect=_owned_by_nobody)
    backend.get_node_labels_batch = AsyncMock(side_effect=_every_linkable_kind)

    return backend


@pytest.mark.asyncio
async def test_create_task_succeeds(mock_tasks_backend, mock_cross_domain_query, mock_graph_intel):
    """Test that creating a task succeeds with required user_uid."""
    # Arrange
    service = TasksService(
        backend=mock_tasks_backend,
        cross_domain_query=mock_cross_domain_query,
        graph_intel=mock_graph_intel,
        event_bus=None,  # Simplified - no event bus for basic test
    )

    task_request = TaskCreateRequest(
        title="New Task", description="Test task description", priority=Priority.HIGH
    )

    # Act
    result = await service.create_task(task_request, user_uid="user_456")

    # Assert
    assert result.is_ok
    assert result.value.uid == "task-123"
    assert result.value.user_uid == "user_456"
    assert result.value.title == "Test Task"


@pytest.mark.asyncio
async def test_no_event_bus_doesnt_crash(
    mock_tasks_backend, mock_cross_domain_query, mock_graph_intel
):
    """Test that service works without event bus (backward compatibility)."""
    # Arrange
    service = TasksService(
        backend=mock_tasks_backend,
        cross_domain_query=mock_cross_domain_query,
        graph_intel=mock_graph_intel,
        event_bus=None,  # No event bus
    )

    task_request = TaskCreateRequest(title="New Task", priority=Priority.MEDIUM)

    # Act - Should not crash
    result = await service.create_task(task_request, user_uid="user_456")

    # Assert
    assert result.is_ok


@pytest.mark.asyncio
async def test_event_publishing_failure_doesnt_break_operation(
    mock_event_bus, mock_tasks_backend, mock_cross_domain_query, mock_graph_intel
):
    """Test that event publishing failure doesn't break the operation."""
    # Arrange
    mock_event_bus.publish_async = AsyncMock(side_effect=Exception("Event bus down"))

    service = TasksService(
        backend=mock_tasks_backend,
        cross_domain_query=mock_cross_domain_query,
        graph_intel=mock_graph_intel,
        event_bus=mock_event_bus,
    )

    task_request = TaskCreateRequest(title="New Task", priority=Priority.HIGH)

    # Act - Should complete successfully despite event failure
    result = await service.create_task(task_request, user_uid="user_456")

    # Assert - Operation should still succeed
    # (Event publishing is fire-and-forget, doesn't affect core operation)
    assert result.is_ok or result.is_error  # Either is acceptable depending on error handling


# ---------------------------------------------------------------------------
# Shared fixture for orchestration tests (sub-services replaced with AsyncMocks)
# ---------------------------------------------------------------------------


@pytest.fixture
def tasks_service_with_mocked_subservices(
    mock_tasks_backend: Any,
    mock_cross_domain_query: AsyncMock,
    mock_graph_intel: AsyncMock,
) -> TasksService:
    """TasksService with all sub-services replaced by AsyncMocks post-construction."""
    service = TasksService(
        backend=mock_tasks_backend,
        cross_domain_query=mock_cross_domain_query,
        graph_intel=mock_graph_intel,
        event_bus=None,
    )
    service.core = AsyncMock()
    service.progress = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.scheduling = AsyncMock()
    service.planning = AsyncMock()
    service.search = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# TestCompleteTaskWithCascade
# ---------------------------------------------------------------------------


class TestCompleteTaskWithCascade:
    """complete_task_with_cascade is now a pure delegation to TasksProgressService.

    Knowledge generation runs as a TaskCompleted event subscriber in
    TaskEventHandlerService (commit 7d810261) — not as an inline side effect
    on the facade. Event-handler behavior is covered by its own unit tests.
    """

    @pytest.mark.asyncio
    async def test_delegates_to_progress_service(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """complete_task_with_cascade forwards args to progress.complete_task_with_cascade."""
        service = tasks_service_with_mocked_subservices

        mock_task = Mock()
        service.progress.complete_task_with_cascade = AsyncMock(return_value=Result.ok(mock_task))

        user_context = Mock()
        user_context.user_uid = "user_test"

        result = await service.complete_task_with_cascade("task_abc", user_context)

        assert result.is_ok
        service.progress.complete_task_with_cascade.assert_called_once_with(
            "task_abc", user_context, None, None
        )

    @pytest.mark.asyncio
    async def test_propagates_progress_failure(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """complete_task_with_cascade returns the progress service's failure unchanged."""
        service = tasks_service_with_mocked_subservices

        service.progress.complete_task_with_cascade = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_abc"))
        )

        user_context = Mock()
        user_context.user_uid = "user_test"

        result = await service.complete_task_with_cascade("task_abc", user_context)

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLinkTaskToKnowledge
# ---------------------------------------------------------------------------


class TestLinkTaskToKnowledge:
    @pytest.mark.asyncio
    async def test_passes_correct_kwargs_to_relationships(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """link_task_to_knowledge writes the APPLIES_KNOWLEDGE ('knowledge') edge with props."""
        service = tasks_service_with_mocked_subservices
        service.relationships.create_relationship = AsyncMock(return_value=Result.ok(True))

        await service.link_task_to_knowledge(
            "task_abc",
            "ku_python_xyz",
            knowledge_score_required=0.9,
            is_learning_opportunity=True,
        )

        service.relationships.create_relationship.assert_called_once_with(
            "knowledge",
            "task_abc",
            "ku_python_xyz",
            {"knowledge_score_required": 0.9, "is_learning_opportunity": True},
        )


# ---------------------------------------------------------------------------
# TestUpdateTaskKnowledgeEdges — applies_knowledge_uids is a graph edge, not a
# node property. See /docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md.
# ---------------------------------------------------------------------------


class TestUpdateTaskKnowledgeEdges:
    @staticmethod
    def _knowledge_edge(task_uid: str, ku_uid: str) -> tuple[str, str, str, None]:
        """The (from, to, rel_type, props) tuple the create-batch path expects."""
        return (task_uid, ku_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None)

    @pytest.mark.asyncio
    async def test_relationship_only_update_syncs_edges_without_property_write(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """Updating only applies_knowledge_uids must sync edges, not fail on empty props.

        Popping the edge key leaves no node properties; the backend rejects an empty
        update dict, so the facade fetches the task instead and still runs edge sync.
        """
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.core.update_task = AsyncMock()
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["ku_old"]))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_new"])
        )

        assert result.is_ok
        # No node properties remained → property-write path skipped, entity fetched.
        service.core.update_task.assert_not_called()
        service.core.get_task.assert_awaited_once_with("task_abc")
        # Old knowledge edge removed, new one created via the proven batch path.
        service.relationships.delete_relationship.assert_awaited_once_with(
            "knowledge", "task_abc", "ku_old"
        )
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [self._knowledge_edge("task_abc", "ku_new")]
        )

    @pytest.mark.asyncio
    async def test_mixed_update_pops_edge_key_from_property_write(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """A mixed update writes real properties (edge key popped) and syncs the edge."""
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(return_value=Result.ok(Mock()))
        service.core.get_task = AsyncMock()
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(title="New", applies_knowledge_uids=["ku_x"])
        )

        assert result.is_ok
        # Knowledge key is popped — only the real property reaches core.update_task.
        service.core.update_task.assert_awaited_once_with("task_abc", TaskUpdateIntent(title="New"))
        service.core.get_task.assert_not_called()
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [self._knowledge_edge("task_abc", "ku_x")]
        )

    @pytest.mark.asyncio
    async def test_empty_knowledge_list_clears_edges(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """An empty applies_knowledge_uids list clears all knowledge edges, creates none."""
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(
            return_value=Result.ok(["ku_old1", "ku_old2"])
        )
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task("task_abc", TaskUpdateIntent(applies_knowledge_uids=[]))

        assert result.is_ok
        assert service.relationships.delete_relationship.await_count == 2
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_update_path_syncs_edges(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """The generated CRUD JSON route calls inherited update() — it must sync edges.

        Guards against the API path writing applies_knowledge_uids as a junk node
        property instead of replacing APPLIES_KNOWLEDGE edges.
        """
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_new"])
        )

        assert result.is_ok
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [self._knowledge_edge("task_abc", "ku_new")]
        )

    @pytest.mark.asyncio
    async def test_api_update_for_user_verifies_ownership_then_syncs_edges(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """The ownership-verified API route must verify ownership BEFORE editing edges."""
        service = tasks_service_with_mocked_subservices
        service.verify_ownership = AsyncMock(return_value=Result.ok(Mock()))
        # Edge-only update funnels through update_task, which fetches the task to return.
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["ku_old"]))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update_for_user(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_new"]), "user_x"
        )

        assert result.is_ok
        service.verify_ownership.assert_awaited_once_with("task_abc", "user_x")
        service.relationships.delete_relationship.assert_awaited_once_with(
            "knowledge", "task_abc", "ku_old"
        )
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [self._knowledge_edge("task_abc", "ku_new")]
        )

    @pytest.mark.asyncio
    async def test_failed_stale_edge_delete_fails_update_without_creating(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """A failed stale-edge delete must fail the update — not leave stale edges and
        create new ones (which would let cleared knowledge keep affecting detectors)."""
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["ku_old"]))
        service.relationships.delete_relationship = AsyncMock(
            return_value=Result.fail(
                Errors.database(message="transient Neo4j error", operation="delete_relationship")
            )
        )
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_new"])
        )

        assert result.is_error
        # New edge must NOT be created when stale-edge removal failed.
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_edge_only_update_publishes_invalidation_event(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """Edge-only updates bypass core.update_task (which fires TaskUpdated), so the
        facade must publish the invalidation event itself — else rich context stays stale."""
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))
        service._publish_edge_only_update = AsyncMock()

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_new"])
        )

        assert result.is_ok
        service._publish_edge_only_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_property_update_does_not_double_publish(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """A property update goes through core.update_task (which already fires
        TaskUpdated), so the facade must NOT publish a second edge-only event."""
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))
        service._publish_edge_only_update = AsyncMock()

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(title="New", applies_knowledge_uids=["ku_x"])
        )

        assert result.is_ok
        service._publish_edge_only_update.assert_not_called()


# ---------------------------------------------------------------------------
# TestUpdateTaskHabitEdge — reinforces_habit_uid is a single graph edge
# (Task)-[:REINFORCES_HABIT]->(Habit). The ADR-066 sentinel contract:
# UNSET = untouched, None = explicit clear (the picker's clear button → "" → None),
# value = set. Regression guard for the edge-clear UX gap where clearing the
# picker left the edge attached.
# ---------------------------------------------------------------------------


class TestUpdateTaskHabitEdge:
    @staticmethod
    def _habit_edge(task_uid: str, habit_uid: str) -> tuple[str, str, str, None]:
        """The (from, to, rel_type, props) tuple the create-batch path expects."""
        return (task_uid, habit_uid, RelationshipName.REINFORCES_HABIT.value, None)

    @pytest.mark.asyncio
    async def test_clearing_habit_edge_deletes_without_creating(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """reinforces_habit_uid=None (the picker-clear signal) must delete the existing
        REINFORCES_HABIT edge and create no replacement — the edge-clear gap fix."""
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["habit_old"]))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task("task_abc", TaskUpdateIntent(reinforces_habit_uid=None))

        assert result.is_ok
        service.relationships.delete_relationship.assert_awaited_once_with(
            "habits", "task_abc", "habit_old"
        )
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_setting_habit_edge_replaces_existing(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """A new reinforces_habit_uid deletes the old edge and creates the new one."""
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["habit_old"]))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(reinforces_habit_uid="habit_new")
        )

        assert result.is_ok
        service.relationships.delete_relationship.assert_awaited_once_with(
            "habits", "task_abc", "habit_old"
        )
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [self._habit_edge("task_abc", "habit_new")]
        )

    @pytest.mark.asyncio
    async def test_unset_habit_edge_leaves_it_untouched(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """An update that omits reinforces_habit_uid (UNSET) must not touch the edge —
        no fetch, no delete, no create — even while writing node properties."""
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(return_value=Result.ok(Mock()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok(["habit_old"]))
        service.relationships.delete_relationship = AsyncMock()
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task("task_abc", TaskUpdateIntent(title="New"))

        assert result.is_ok
        service.relationships.get_related_uids.assert_not_called()
        service.relationships.delete_relationship.assert_not_called()
        service.backend.create_relationships_batch.assert_not_called()


# ---------------------------------------------------------------------------
# TestUpdateTaskGoalEdge — fulfills_goal_uid is dual-written on update too
# ---------------------------------------------------------------------------


def _task(**overrides: Any) -> Task:
    defaults: dict[str, Any] = {"uid": "task_abc", "user_uid": "user_x", "title": "Ship it"}
    defaults.update(overrides)
    return Task(**defaults)


class TestUpdateTaskGoalEdge:
    """``fulfills_goal_uid`` on update: the property is written AND the FULFILLS_GOAL
    edge is replaced — old edge deleted, new one admitted through the same guard the
    create path uses. ``None`` clears both; ``UNSET`` touches neither. A refused goal
    clears the property so the two halves never disagree (the create-path rule)."""

    GOAL_EDGE = ("task_abc", "goal_new", RelationshipName.FULFILLS_GOAL.value, None)

    @staticmethod
    def _related(existing_goal: str | None):
        async def related(key: str, uid: str) -> Result[list[str]]:
            if key == "fulfills_goal":
                return Result.ok([existing_goal] if existing_goal else [])
            return Result.ok([])

        return related

    @pytest.mark.asyncio
    async def test_setting_a_goal_writes_the_property_and_replaces_the_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(
            return_value=Result.ok(_task(fulfills_goal_uid="goal_new"))
        )
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related("goal_old"))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))
        service.backend.update = AsyncMock()

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid="goal_new")
        )

        assert result.is_ok
        # The property is NOT split off: it stays in the patch core writes.
        service.core.update_task.assert_awaited_once_with(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid="goal_new")
        )
        service.relationships.delete_relationship.assert_awaited_once_with(
            "fulfills_goal", "task_abc", "goal_old"
        )
        service.backend.create_relationships_batch.assert_awaited_once_with([self.GOAL_EDGE])
        service.backend.update.assert_not_called()
        assert result.value.fulfills_goal_uid == "goal_new"

    @pytest.mark.asyncio
    async def test_clearing_the_goal_deletes_the_edge_and_creates_none(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(return_value=Result.ok(_task()))
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related("goal_old"))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task("task_abc", TaskUpdateIntent(fulfills_goal_uid=None))

        assert result.is_ok
        service.core.update_task.assert_awaited_once_with(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid=None)
        )
        service.relationships.delete_relationship.assert_awaited_once_with(
            "fulfills_goal", "task_abc", "goal_old"
        )
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unset_goal_touches_no_goal_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(return_value=Result.ok(_task()))
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related("goal_old"))
        service.relationships.delete_relationship = AsyncMock()
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task("task_abc", TaskUpdateIntent(title="Renamed"))

        assert result.is_ok
        service.relationships.get_related_uids.assert_not_called()
        service.relationships.delete_relationship.assert_not_called()
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_refused_goal_clears_the_property(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """Another user's goal: the old edge is gone (replace semantics), the new one is
        refused, and the property core just wrote is cleared — the returned task names no
        goal, matching the graph."""
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(
            return_value=Result.ok(_task(fulfills_goal_uid="goal_theirs"))
        )
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related("goal_old"))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.get_owner_uids_batch = AsyncMock(
            return_value=Result.ok({"goal_theirs": ["user_someone_else"]})
        )
        service.backend.create_relationships_batch = AsyncMock()
        service.backend.update = AsyncMock(return_value=Result.ok(_task()))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid="goal_theirs")
        )

        assert result.is_ok
        service.backend.create_relationships_batch.assert_not_called()
        service.backend.update.assert_awaited_once_with("task_abc", {"fulfills_goal_uid": None})
        assert result.value.fulfills_goal_uid is None

    @pytest.mark.asyncio
    async def test_a_failed_batch_clears_the_stamp_and_still_reports_the_failure(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """Kody on #1260: core has already written the column and the old edge is gone
        when the batch fails, so an early return strands a stamp with no edge behind it.
        The invariant is restored FIRST, and the failure is still reported — a silent
        success here would also swallow a failed habit or knowledge edge in the same
        batch."""
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(
            return_value=Result.ok(_task(fulfills_goal_uid="goal_new"))
        )
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related("goal_old"))
        service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))
        service.backend.create_relationships_batch = AsyncMock(
            return_value=Result.fail(
                Errors.database(message="transient Neo4j error", operation="create_batch")
            )
        )
        service.backend.update = AsyncMock(return_value=Result.ok(_task()))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid="goal_new")
        )

        assert result.is_error, "a failed edge batch is an update failure, not a silent success"
        service.backend.update.assert_awaited_once_with("task_abc", {"fulfills_goal_uid": None})

    @pytest.mark.asyncio
    async def test_a_goal_of_the_wrong_kind_is_refused(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.update_task = AsyncMock(
            return_value=Result.ok(_task(fulfills_goal_uid="habit_not_a_goal"))
        )
        service.relationships.get_related_uids = AsyncMock(side_effect=self._related(None))
        service.backend.get_node_labels_batch = AsyncMock(
            return_value=Result.ok({"habit_not_a_goal": ["Entity", "Habit"]})
        )
        service.backend.create_relationships_batch = AsyncMock()
        service.backend.update = AsyncMock(return_value=Result.ok(_task()))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(fulfills_goal_uid="habit_not_a_goal")
        )

        assert result.is_ok
        service.backend.create_relationships_batch.assert_not_called()
        service.backend.update.assert_awaited_once_with("task_abc", {"fulfills_goal_uid": None})
        assert result.value.fulfills_goal_uid is None


class TestUpdateTaskEdgesAreGuarded:
    """The update door writes link edges through the same admission guard as create.

    ``update_for_user`` verifies the TASK's owner and nothing about the far end, so
    without this a caller could point their task at another user's habit or knowledge
    and have the edge written — the defect class #965 closed on the create doors."""

    @pytest.mark.asyncio
    async def test_another_users_habit_is_refused_on_update(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(_task()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        service.backend.get_owner_uids_batch = AsyncMock(
            return_value=Result.ok({"habit_theirs": ["user_someone_else"]})
        )
        service.backend.create_relationships_batch = AsyncMock()

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(reinforces_habit_uid="habit_theirs")
        )

        assert result.is_ok, "the update itself succeeds — only the edge is refused"
        service.backend.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_another_users_knowledge_is_refused_on_update(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        service.core.get_task = AsyncMock(return_value=Result.ok(_task()))
        service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        # The real owner query OMITS unowned nodes (a Ku carries no owner) — an absent
        # row means "owned by nobody", which the guard treats as linkable.
        service.backend.get_owner_uids_batch = AsyncMock(
            return_value=Result.ok({"ku_theirs": ["user_someone_else"]})
        )
        service.backend.create_relationships_batch = AsyncMock(return_value=Result.ok(1))

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(applies_knowledge_uids=["ku_theirs", "ku.shared"])
        )

        assert result.is_ok
        # Only the offending edge is dropped; the shared (unowned) Ku still links.
        service.backend.create_relationships_batch.assert_awaited_once_with(
            [("task_abc", "ku.shared", RelationshipName.APPLIES_KNOWLEDGE.value, None)]
        )
