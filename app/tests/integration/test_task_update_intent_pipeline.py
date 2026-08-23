"""
Integration Test: Task Update Intent pipeline (ADR-066 Phase 1)
==============================================================

Verifies the typed ``TaskUpdateIntent`` update path end to end against live Neo4j:

1. ``update_task(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``TaskUpdated`` event fires on the intent path (cache invalidation contract).
3. A status transition expressed as an intent persists and fires ``TaskUpdated``.
4. ``TaskUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``) — absent fields stay ``UNSET`` and are not written.
5. The domain rule (``_validate_update`` — overdue-priority protection) runs on that
   path and refuses before the write, since ``update_task`` invokes it explicitly.

These guard the reference implementation the other five Activity Domains copy.
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import TaskUpdated
from core.models.enums import EntityStatus, Priority
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.models.task.task_request import TaskUpdateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestTaskUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"entity_type": "task"}
        )

    @pytest_asyncio.fixture
    async def core_service(self, tasks_backend, event_bus):
        return TasksCoreService(backend=tasks_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def seeded_task(self, core_service):
        task = Task(
            uid="task.intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            description="Original description",
            due_date=date.today() + timedelta(days=5),
            priority=Priority.MEDIUM,
            status=EntityStatus.ACTIVE,
            duration_minutes=60,
        )
        result = await core_service.create(task)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_task, event_bus
    ) -> None:
        """A partial intent updates title only — description/priority survive untouched."""
        intent = TaskUpdateIntent(title="Updated title")

        result = await core_service.update_task(seeded_task.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_task(seeded_task.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.description == "Original description"
        assert fetched.value.priority == Priority.MEDIUM
        assert fetched.value.duration_minutes == 60

        # TaskUpdated fired on the intent path, naming only the changed field.
        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, TaskUpdated)]
        assert updated_events, "expected a TaskUpdated event on the intent path"
        assert updated_events[-1].updated_fields == ["title"]

    async def test_status_transition_intent_persists_and_emits_event(
        self, core_service, seeded_task, event_bus
    ) -> None:
        """A status transition built as an intent persists and fires TaskUpdated."""
        event_bus.clear_event_history()
        intent = TaskUpdateIntent(status=EntityStatus.COMPLETED.value)

        result = await core_service.update_task(seeded_task.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.COMPLETED

        fetched = await core_service.get_task(seeded_task.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.COMPLETED

        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, TaskUpdated)]
        assert updated_events, "status transition must fire TaskUpdated"
        assert "status" in updated_events[-1].updated_fields

    async def test_overdue_priority_rule_refuses_the_write(self, core_service) -> None:
        """The domain rule runs on the live path and nothing reaches Neo4j.

        ``update_task`` calls ``_validate_update`` explicitly — the facade routes the
        generic CRUD here, so the inherited hook never fires for Tasks. Before this was
        wired the rule had no production caller at all.
        """
        overdue = Task(
            uid="task.intent_pipeline_overdue",
            user_uid="user_intent_pipeline",
            title="Overdue task",
            due_date=date.today() - timedelta(days=3),
            priority=Priority.HIGH,
            status=EntityStatus.ACTIVE,
        )
        seeded = await core_service.create(overdue)
        assert seeded.is_ok

        refused = await core_service.update_task(
            overdue.uid, TaskUpdateIntent(priority=Priority.LOW.value)
        )
        assert refused.is_error
        assert "Cannot decrease priority of overdue tasks" in refused.expect_error().message

        # The stored row is untouched — validation ran before the write.
        fetched = await core_service.get_task(overdue.uid)
        assert fetched.is_ok
        assert fetched.value.priority == Priority.HIGH

        # Raising it is still allowed on the same overdue task.
        raised = await core_service.update_task(
            overdue.uid, TaskUpdateIntent(priority=Priority.CRITICAL.value)
        )
        assert raised.is_ok
        assert raised.value.priority == Priority.CRITICAL

    async def test_priority_decrease_allowed_when_not_overdue(
        self, core_service, seeded_task
    ) -> None:
        """The rule is scoped to overdue tasks — ordinary re-planning is untouched."""
        result = await core_service.update_task(
            seeded_task.uid, TaskUpdateIntent(priority=Priority.LOW.value)
        )
        assert result.is_ok

        fetched = await core_service.get_task(seeded_task.uid)
        assert fetched.is_ok
        assert fetched.value.priority == Priority.LOW

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = TaskUpdateRequest(title="Just the title")
        intent = request.to_intent()

        # The one provided field is set (and enum-free here), everything else UNSET.
        assert intent.title == "Just the title"
        assert intent.status is UNSET
        assert intent.priority is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # An enum field is lowered to its string value on the intent.
        request2 = TaskUpdateRequest(priority=Priority.HIGH, status=EntityStatus.ACTIVE)
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.status == EntityStatus.ACTIVE.value
        assert intent2.title is UNSET
        assert intent2.to_changes() == {
            "priority": Priority.HIGH.value,
            "status": EntityStatus.ACTIVE.value,
        }
