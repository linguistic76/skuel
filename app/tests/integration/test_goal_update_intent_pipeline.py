"""
Integration Test: Goal Update Intent pipeline (ADR-066 Phase 2)
==============================================================

Verifies the typed ``GoalUpdateIntent`` update path end to end against live Neo4j:

1. ``update_goal(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``GoalUpdated`` event fires on the intent path (cache invalidation contract).
3. A status transition to COMPLETED expressed as an intent persists and fires
   ``GoalUpdated`` + ``GoalAchieved``.
4. ``GoalUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``) — absent fields stay ``UNSET`` and are not written, and the
   cross-domain edge UIDs are never carried as node properties.

Mirrors ``test_task_update_intent_pipeline.py`` (the reference) for the Goals domain.
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import GoalAchieved, GoalUpdated
from core.models.enums import EntityStatus, Priority
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalUpdateRequest
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.sentinels import UNSET
from core.services.goals.goals_core_service import GoalsCoreService


@pytest.mark.asyncio
class TestGoalUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path (Goals)."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        return UniversalNeo4jBackend[Goal](
            neo4j_driver, "Entity", Goal, default_filters={"entity_type": "goal"}
        )

    @pytest_asyncio.fixture
    async def core_service(self, goals_backend, event_bus):
        return GoalsCoreService(backend=goals_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def seeded_goal(self, core_service):
        goal = Goal(
            uid="goal.intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            description="Original description",
            target_date=date.today() + timedelta(days=30),
            target_value=100.0,
            priority=Priority.MEDIUM,
            status=EntityStatus.ACTIVE,
        )
        result = await core_service.create(goal)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_goal, event_bus
    ) -> None:
        """A partial intent updates title only — description/priority/target survive."""
        event_bus.clear_event_history()
        intent = GoalUpdateIntent(title="Updated title")

        result = await core_service.update_goal(seeded_goal.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_goal(seeded_goal.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.description == "Original description"
        assert fetched.value.priority == Priority.MEDIUM
        assert fetched.value.target_value == 100.0

        # GoalUpdated fired on the intent path, naming only the changed field.
        updated_events = [e for e in event_bus.get_event_history() if isinstance(e, GoalUpdated)]
        assert updated_events, "expected a GoalUpdated event on the intent path"
        assert updated_events[-1].updated_fields == ["title"]

    async def test_status_transition_intent_persists_and_emits_events(
        self, core_service, seeded_goal, event_bus
    ) -> None:
        """A status transition to COMPLETED persists and fires GoalUpdated + GoalAchieved."""
        event_bus.clear_event_history()
        intent = GoalUpdateIntent(status=EntityStatus.COMPLETED.value)

        result = await core_service.update_goal(seeded_goal.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.COMPLETED

        fetched = await core_service.get_goal(seeded_goal.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.COMPLETED

        history = event_bus.get_event_history()
        updated_events = [e for e in history if isinstance(e, GoalUpdated)]
        assert updated_events, "status transition must fire GoalUpdated"
        assert "status" in updated_events[-1].updated_fields

        achieved_events = [e for e in history if isinstance(e, GoalAchieved)]
        assert achieved_events, "transition into COMPLETED must fire GoalAchieved"
        assert achieved_events[-1].goal_uid == seeded_goal.uid

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = GoalUpdateRequest(title="Just the title")
        intent = request.to_intent()

        # The one provided field is set, everything else UNSET.
        assert intent.title == "Just the title"
        assert intent.status is UNSET
        assert intent.priority is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # Enum fields are lowered to their string value on the intent.
        request2 = GoalUpdateRequest(priority=Priority.HIGH, status=EntityStatus.ACTIVE)
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.status == EntityStatus.ACTIVE.value
        assert intent2.title is UNSET
        assert intent2.to_changes() == {
            "priority": Priority.HIGH.value,
            "status": EntityStatus.ACTIVE.value,
        }

    async def test_to_intent_drops_cross_domain_edge_uids(self) -> None:
        """Edge-UID request fields are graph edges, never carried as node properties."""
        request = GoalUpdateRequest(
            title="Edges plus a prop",
            supporting_habit_uids=["habit_x"],
            required_knowledge_uids=["ku_y"],
            guiding_principle_uids=["principle_z"],
        )
        intent = request.to_intent()

        # Only the node property survives; the three edge fields are not on the intent.
        assert intent.to_changes() == {"title": "Edges plus a prop"}
