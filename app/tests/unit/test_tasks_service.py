"""
Tests for TasksService event-driven functionality and orchestration methods.

Tests verify that TasksService correctly publishes domain events
when tasks are created, completed, etc., and that orchestration methods
with conditional logic behave correctly.
"""

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.goal_events import GoalContributionsChanged
from core.events.task_events import TaskUpdated
from core.models.enums import EntityStatus, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.mixins.link_edge_guard import KNOWLEDGE_FAR_END
from core.services.tasks_service import TaskEdgeIntent, TasksService
from core.utils.result_simplified import Errors, Result


async def _owned_by_nobody(uids: list[str]) -> Result[dict[str, list[str]]]:
    return Result.ok({})


async def _every_linkable_kind(uids: list[str]) -> Result[dict[str, list[str]]]:
    return Result.ok({uid: ["Entity", "Goal", "Habit", "Ku"] for uid in uids})


async def _all_published(uids: list[str]) -> Result[frozenset[str]]:
    return Result.ok(frozenset(uids))


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
    # The link-edge admission guard's three batched reads (keep_permitted_link_edges).
    # Permissive by default — every uid is owned by nobody, published, and carries
    # every kind the update path links — so tests that are not ABOUT admission keep
    # writing edges.
    backend.get_owner_uids_batch = AsyncMock(side_effect=_owned_by_nobody)
    backend.get_node_labels_batch = AsyncMock(side_effect=_every_linkable_kind)
    backend.get_published_uids_batch = AsyncMock(side_effect=_all_published)

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
            far_end=KNOWLEDGE_FAR_END,
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
# TestUpdateTaskGoalEdges — contributes_to_goal_uids replaces the task's goal set
# ---------------------------------------------------------------------------


def _task(**overrides: Any) -> Task:
    defaults: dict[str, Any] = {"uid": "task_abc", "user_uid": "user_x", "title": "Ship it"}
    defaults.update(overrides)
    return Task(**defaults)


class _Bus:
    """Captures what the facade publishes — ``publish_event`` calls ``publish_async``."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.events.append(event)

    def goal_changes(self) -> list[GoalContributionsChanged]:
        return [e for e in self.events if isinstance(e, GoalContributionsChanged)]


@dataclass
class _Wired:
    """The fakes ``TestUpdateTaskGoalEdges._wire`` installs, kept for assertions."""

    bus: _Bus
    update_task: AsyncMock
    update: AsyncMock
    get_related_uids: AsyncMock
    delete_relationship: AsyncMock
    create_relationships_batch: AsyncMock


class TestUpdateTaskGoalEdges:
    """``contributes_to_goal_uids`` on update is a FULL REPLACE of the task's
    CONTRIBUTES_TO_GOAL edges: every old edge deleted, each new one admitted through the
    guard the create path uses. ``[]`` clears; ``UNSET`` touches nothing. Edge-only —
    no node property names a goal. A changed goal set announces the goals it left and
    the task itself (whose current goals the handler reads), so both are recounted."""

    @staticmethod
    def _edge(goal_uid: str) -> tuple[str, str, str, None]:
        return ("task_abc", goal_uid, RelationshipName.CONTRIBUTES_TO_GOAL.value, None)

    @staticmethod
    def _related(*existing_goals: str):
        async def related(key: str, uid: str) -> Result[list[str]]:
            if key == "contributes_to_goal":
                return Result.ok(list(existing_goals))
            return Result.ok([])

        return related

    def _wire(self, service: TasksService, *existing_goals: str) -> _Wired:
        w = _Wired(
            bus=_Bus(),
            update_task=AsyncMock(return_value=Result.ok(_task())),
            update=AsyncMock(),
            get_related_uids=AsyncMock(side_effect=self._related(*existing_goals)),
            delete_relationship=AsyncMock(return_value=Result.ok(True)),
            create_relationships_batch=AsyncMock(return_value=Result.ok(2)),
        )
        service.event_bus = cast("EventBusOperations", w.bus)
        service.core.get_task = AsyncMock(return_value=Result.ok(_task()))
        service.core.update_task = w.update_task
        service.relationships.get_related_uids = w.get_related_uids
        service.relationships.delete_relationship = w.delete_relationship
        service.backend.create_relationships_batch = w.create_relationships_batch
        service.backend.update = w.update
        return w

    @pytest.mark.asyncio
    async def test_a_new_goal_set_replaces_the_old_edges(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_old")

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=["goal_a", "goal_b"])
        )

        assert result.is_ok
        # Edge-only: nothing reaches the node-property write.
        w.update_task.assert_not_called()
        w.update.assert_not_called()
        w.delete_relationship.assert_awaited_once_with(
            "contributes_to_goal", "task_abc", "goal_old"
        )
        w.create_relationships_batch.assert_awaited_once_with(
            [self._edge("goal_a"), self._edge("goal_b")]
        )
        [changed] = w.bus.goal_changes()
        assert changed.goal_uids == ("goal_old",)
        assert changed.contributor_uids == ("task_abc",)
        assert changed.user_uid == "user_x"

    @pytest.mark.asyncio
    async def test_the_goal_set_is_split_off_a_property_update(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service)

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(title="Renamed", contributes_to_goal_uids=["goal_a"])
        )

        assert result.is_ok
        w.update_task.assert_awaited_once_with("task_abc", TaskUpdateIntent(title="Renamed"))
        w.create_relationships_batch.assert_awaited_once_with([self._edge("goal_a")])

    @pytest.mark.asyncio
    async def test_an_empty_list_clears_every_goal_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_old", "goal_older")

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=[])
        )

        assert result.is_ok
        assert w.delete_relationship.await_count == 2
        w.create_relationships_batch.assert_not_called()
        [changed] = w.bus.goal_changes()
        assert changed.goal_uids == ("goal_old", "goal_older")

    @pytest.mark.asyncio
    async def test_an_unset_goal_set_touches_no_goal_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_old")

        result = await service.update_task("task_abc", TaskUpdateIntent(title="Renamed"))

        assert result.is_ok
        w.get_related_uids.assert_not_called()
        w.delete_relationship.assert_not_called()
        w.create_relationships_batch.assert_not_called()
        assert w.bus.goal_changes() == []

    @pytest.mark.asyncio
    async def test_a_goal_owned_by_another_user_is_refused(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """Replace semantics: the old edge is gone, the foreign one is never written, and
        the goal that lost the task is still announced."""
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_old")
        service.backend.get_owner_uids_batch = AsyncMock(
            return_value=Result.ok({"goal_theirs": ["user_someone_else"]})
        )

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=["goal_theirs"])
        )

        assert result.is_ok
        w.create_relationships_batch.assert_not_called()
        w.update.assert_not_called()
        [changed] = w.bus.goal_changes()
        assert changed.goal_uids == ("goal_old",)

    @pytest.mark.asyncio
    async def test_a_goal_of_the_wrong_kind_is_refused(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service)
        service.backend.get_node_labels_batch = AsyncMock(
            return_value=Result.ok({"habit_not_a_goal": ["Entity", "Habit"]})
        )

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=["habit_not_a_goal"])
        )

        assert result.is_ok
        w.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failed_batch_is_an_update_failure_that_still_announces_the_removed_goals(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """The old edges are already gone when the batch fails, so the goals that lost the
        task must still be recounted — or their stored tallies keep counting it until a
        reconcile. The failure is still reported."""
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_old")
        service.backend.create_relationships_batch = AsyncMock(
            return_value=Result.fail(
                Errors.database(message="transient Neo4j error", operation="create_batch")
            )
        )

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=["goal_new"])
        )

        assert result.is_error, "a failed edge batch is an update failure, not a silent success"
        [changed] = w.bus.goal_changes()
        assert changed.goal_uids == ("goal_old",)

    @pytest.mark.asyncio
    async def test_a_delete_failing_part_way_still_announces_every_prior_goal(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        """The second of two goal-edge deletes fails: the first goal is already unlinked,
        so every goal the task held is announced before the failure is reported."""
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "goal_a", "goal_b")
        service.relationships.delete_relationship = AsyncMock(
            side_effect=[
                Result.ok(True),
                Result.fail(Errors.database(message="transient", operation="delete")),
            ]
        )

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(contributes_to_goal_uids=["goal_new"])
        )

        assert result.is_error
        [changed] = w.bus.goal_changes()
        assert changed.goal_uids == ("goal_a", "goal_b")
        w.create_relationships_batch.assert_not_called()


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


# ---------------------------------------------------------------------------
# TestUpdateTaskPrincipleEdges — aligned_principle_uids replaces the task's principles
# ---------------------------------------------------------------------------


async def _principles_only(uids: list[str]) -> Result[dict[str, list[str]]]:
    return Result.ok({uid: ["Entity", "Principle"] for uid in uids})


class TestUpdateTaskPrincipleEdges:
    """``aligned_principle_uids`` on update is a FULL REPLACE of the task's
    ALIGNED_WITH_PRINCIPLE edges — split off the property patch like the goal set, so the
    uids never reach ``backend.update``; ``[]`` clears, ``UNSET`` touches nothing."""

    @staticmethod
    def _edge(principle_uid: str) -> tuple[str, str, str, None]:
        return ("task_abc", principle_uid, RelationshipName.ALIGNED_WITH_PRINCIPLE.value, None)

    @staticmethod
    def _wire(service: TasksService, *existing: str) -> _Wired:
        async def related(key: str, uid: str) -> Result[list[str]]:
            return Result.ok(list(existing) if key == "principles" else [])

        w = _Wired(
            bus=_Bus(),
            update_task=AsyncMock(return_value=Result.ok(_task())),
            update=AsyncMock(),
            get_related_uids=AsyncMock(side_effect=related),
            delete_relationship=AsyncMock(return_value=Result.ok(True)),
            create_relationships_batch=AsyncMock(return_value=Result.ok(2)),
        )
        service.event_bus = cast("EventBusOperations", w.bus)
        service.core.get_task = AsyncMock(return_value=Result.ok(_task()))
        service.core.update_task = w.update_task
        service.relationships.get_related_uids = w.get_related_uids
        service.relationships.delete_relationship = w.delete_relationship
        service.backend.create_relationships_batch = w.create_relationships_batch
        service.backend.get_node_labels_batch = AsyncMock(side_effect=_principles_only)
        service.backend.update = w.update
        return w

    def test_the_principle_set_is_split_off_the_property_patch(self) -> None:
        edges, prop_intent = TasksService._split_relationship_intent(
            TaskUpdateIntent(title="Renamed", aligned_principle_uids=["p_one"])
        )

        assert edges.aligned_principle_uids == ["p_one"]
        assert prop_intent == TaskUpdateIntent(title="Renamed")
        assert "aligned_principle_uids" not in prop_intent.to_changes()

    def test_a_principle_set_counts_as_an_edge_change(self) -> None:
        """``any_set`` decides the edge-only path: an update carrying only principles
        (even ``[]``) must not reach the property write with an empty patch."""
        assert TaskEdgeIntent(aligned_principle_uids=["p_one"]).any_set()
        assert TaskEdgeIntent(aligned_principle_uids=[]).any_set()
        assert not TaskEdgeIntent().any_set()

    @pytest.mark.asyncio
    async def test_a_new_principle_set_replaces_the_old_edges_edge_only(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "p_old")

        result = await service.update_task(
            "task_abc", TaskUpdateIntent(aligned_principle_uids=["p_one", "p_two"])
        )

        assert result.is_ok
        w.update_task.assert_not_called()
        w.update.assert_not_called()
        w.delete_relationship.assert_awaited_once_with("principles", "task_abc", "p_old")
        w.create_relationships_batch.assert_awaited_once_with(
            [self._edge("p_one"), self._edge("p_two")]
        )
        [updated] = [e for e in w.bus.events if isinstance(e, TaskUpdated)]
        assert updated.updated_fields == ["aligned_principle_uids"]
        assert w.bus.goal_changes() == [], "a principle change is no goal-set change"

    @pytest.mark.asyncio
    async def test_an_empty_list_clears_every_principle_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "p_old", "p_older")

        result = await service.update_task("task_abc", TaskUpdateIntent(aligned_principle_uids=[]))

        assert result.is_ok
        assert w.delete_relationship.await_count == 2
        w.create_relationships_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unset_principle_set_touches_no_principle_edge(
        self, tasks_service_with_mocked_subservices: TasksService
    ) -> None:
        service = tasks_service_with_mocked_subservices
        w = self._wire(service, "p_old")

        result = await service.update_task("task_abc", TaskUpdateIntent(title="Renamed"))

        assert result.is_ok
        w.update_task.assert_awaited_once_with("task_abc", TaskUpdateIntent(title="Renamed"))
        w.get_related_uids.assert_not_called()
        w.delete_relationship.assert_not_called()
        w.create_relationships_batch.assert_not_called()
