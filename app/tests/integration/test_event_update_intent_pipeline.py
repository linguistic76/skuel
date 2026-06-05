"""
Integration Test: Event Update Intent pipeline (ADR-066 Phase 3)
===============================================================

Verifies the typed ``EventUpdateIntent`` update path end to end against live Neo4j:

1. ``update_event(intent)`` materializes only the set fields at the single
   ``backend.update`` seam — a partial update does NOT clobber untouched columns.
2. A ``CalendarEventUpdated`` event fires on a plain property update (cache contract).
3. A status transition to COMPLETED expressed as an intent persists and fires
   ``CalendarEventCompleted``.
4. An ``event_date`` change fires ``CalendarEventRescheduled``.
5. ``EventUpdateRequest.to_intent()`` carries exactly the explicitly-set fields
   (``model_fields_set``) — absent fields stay ``UNSET``, enum fields lowered.
6. An **edge-only** update through the facade rewires ``CELEBRATES_GOAL`` /
   ``REINFORCES_HABIT`` and fires ``CalendarEventUpdated`` — without leaking the edge UIDs
   as junk node properties.
7. ``to_intent()`` **drops** ``practices_knowledge_uids`` / ``executes_tasks`` (neither
   node columns nor handled edges on the update path).

Mirrors ``test_goal_update_intent_pipeline.py`` (the reference) for the Events domain,
adding the edge-split coverage Events shares with Tasks.
"""

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import EventsBackend
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
)
from core.models.enums import EntityStatus, Priority, Visibility
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.event.event_request import EventUpdateRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.sentinels import UNSET
from core.services.events.events_core_service import EventsCoreService
from core.services.events_service import EventsService


@pytest.mark.asyncio
class TestEventUpdateIntentPipeline:
    """Live-Neo4j checks for the ADR-066 typed update path (Events)."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def events_backend(self, neo4j_driver, clean_neo4j):
        # Real domain backend (multi-label :Entity:Event) so the facade's learning
        # sub-service binds `get_user_events` and relationship validation sees the
        # source domain label.
        return EventsBackend(neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY)

    @pytest_asyncio.fixture
    async def core_service(self, events_backend, event_bus):
        return EventsCoreService(backend=events_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def facade(self, events_backend, event_bus):
        """Full EventsService facade (real backend + event bus) for the edge-split path.

        graph_intel / cross_domain_query are mocked — the edge-only update path exercises
        only ``self.core`` and ``self.relationships``, both built from the real backend.
        """
        return EventsService(
            backend=events_backend,
            graph_intel=Mock(),
            cross_domain_query=AsyncMock(),
            event_bus=event_bus,
        )

    @pytest_asyncio.fixture
    async def seeded_event(self, core_service):
        """A future-dated event (past-event immutability would block updates otherwise)."""
        event = Event(
            uid="event:intent_pipeline",
            user_uid="user_intent_pipeline",
            title="Original title",
            description="Original description",
            event_date=date.today() + timedelta(days=10),
            start_time=time(10, 0),
            end_time=time(11, 0),
            location="Original location",
            priority=Priority.MEDIUM,
            status=EntityStatus.ACTIVE,
        )
        result = await core_service.create(event)
        assert result.is_ok
        return result.value

    async def test_partial_intent_writes_only_set_fields(
        self, core_service, seeded_event, event_bus
    ) -> None:
        """A partial intent updates title only — description/location/priority survive."""
        event_bus.clear_event_history()
        intent = EventUpdateIntent(title="Updated title")

        result = await core_service.update_event(seeded_event.uid, intent)
        assert result.is_ok
        assert result.value.title == "Updated title"

        # Re-fetch from Neo4j: title changed, the rest is intact (no clobber).
        fetched = await core_service.get_event(seeded_event.uid)
        assert fetched.is_ok
        assert fetched.value.title == "Updated title"
        assert fetched.value.description == "Original description"
        assert fetched.value.location == "Original location"
        assert fetched.value.priority == Priority.MEDIUM

        # CalendarEventUpdated fired on the intent path, naming only the changed field.
        updated_events = [
            e for e in event_bus.get_event_history() if isinstance(e, CalendarEventUpdated)
        ]
        assert updated_events, "expected a CalendarEventUpdated event on the intent path"
        assert updated_events[-1].updated_fields == {"title": "Updated title"}

    async def test_status_transition_intent_persists_and_emits_completed(
        self, core_service, seeded_event, event_bus
    ) -> None:
        """A status transition to COMPLETED persists and fires CalendarEventCompleted."""
        event_bus.clear_event_history()
        intent = EventUpdateIntent(status=EntityStatus.COMPLETED.value)

        result = await core_service.update_event(seeded_event.uid, intent)
        assert result.is_ok
        assert result.value.status == EntityStatus.COMPLETED

        fetched = await core_service.get_event(seeded_event.uid)
        assert fetched.is_ok
        assert fetched.value.status == EntityStatus.COMPLETED

        completed = [
            e for e in event_bus.get_event_history() if isinstance(e, CalendarEventCompleted)
        ]
        assert completed, "transition into COMPLETED must fire CalendarEventCompleted"
        assert completed[-1].event_uid == seeded_event.uid
        # quality_score is not carried on the generic update path (owned by progress/habit).
        assert completed[-1].quality_score is None

    async def test_event_date_change_fires_rescheduled(
        self, core_service, seeded_event, event_bus
    ) -> None:
        """An event_date change fires CalendarEventRescheduled with old/new dates."""
        event_bus.clear_event_history()
        new_date = seeded_event.event_date + timedelta(days=3)
        intent = EventUpdateIntent(event_date=new_date)

        result = await core_service.update_event(seeded_event.uid, intent)
        assert result.is_ok
        assert result.value.event_date == new_date

        rescheduled = [
            e for e in event_bus.get_event_history() if isinstance(e, CalendarEventRescheduled)
        ]
        assert rescheduled, "event_date change must fire CalendarEventRescheduled"
        assert rescheduled[-1].old_date == seeded_event.event_date
        assert rescheduled[-1].new_date == new_date

    async def test_to_intent_carries_only_explicit_fields(self) -> None:
        """to_intent() reflects model_fields_set: provided → set, absent → UNSET."""
        request = EventUpdateRequest(title="Just the title")
        intent = request.to_intent()

        assert intent.title == "Just the title"
        assert intent.status is UNSET
        assert intent.priority is UNSET
        assert intent.description is UNSET
        assert intent.to_changes() == {"title": "Just the title"}

        # Enum fields are lowered to their string value on the intent.
        request2 = EventUpdateRequest(
            priority=Priority.HIGH, status=EntityStatus.ACTIVE, visibility=Visibility.PUBLIC
        )
        intent2 = request2.to_intent()
        assert intent2.priority == Priority.HIGH.value
        assert intent2.status == EntityStatus.ACTIVE.value
        assert intent2.visibility == Visibility.PUBLIC.value
        assert intent2.title is UNSET
        assert intent2.to_changes() == {
            "priority": Priority.HIGH.value,
            "status": EntityStatus.ACTIVE.value,
            "visibility": Visibility.PUBLIC.value,
        }

    async def test_to_intent_drops_non_column_learning_fields(self) -> None:
        """practices_knowledge_uids / executes_tasks are neither columns nor handled edges
        on the update path, so they are never carried as node properties — only the two
        real edge fields and the node property survive."""
        request = EventUpdateRequest(
            title="Edges plus junk",
            practices_knowledge_uids=["ku_x"],
            executes_tasks=["task:y"],
            milestone_celebration_for_goal="goal:z",
            reinforces_habit_uid="habit:w",
        )
        intent = request.to_intent()

        assert intent.to_changes() == {
            "title": "Edges plus junk",
            "milestone_celebration_for_goal": "goal:z",
            "reinforces_habit_uid": "habit:w",
        }

    async def test_edge_only_update_rewires_edges_without_junk_properties(
        self, facade, core_service, seeded_event, event_bus, neo4j_driver
    ) -> None:
        """An edge-only intent rewires CELEBRATES_GOAL / REINFORCES_HABIT through the facade
        and fires CalendarEventUpdated — and writes NO junk node property."""
        event_uid = seeded_event.uid

        # Seed cross-domain target nodes (proper multi-labels for relationship validation).
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (g_old:Entity:Goal {uid: 'goal:edge_old'})
                  ON CREATE SET g_old.entity_type = 'goal', g_old.title = 'Old goal'
                MERGE (g_new:Entity:Goal {uid: 'goal:edge_new'})
                  ON CREATE SET g_new.entity_type = 'goal', g_new.title = 'New goal'
                MERGE (h_old:Entity:Habit {uid: 'habit:edge_old'})
                  ON CREATE SET h_old.entity_type = 'habit', h_old.title = 'Old habit'
                MERGE (h_new:Entity:Habit {uid: 'habit:edge_new'})
                  ON CREATE SET h_new.entity_type = 'habit', h_new.title = 'New habit'
                """
            )

        # Establish the initial edges to the "old" targets.
        assert (
            await facade.relationships.create_relationship(
                "celebrated_goals", event_uid, "goal:edge_old"
            )
        ).is_ok
        assert (
            await facade.relationships.create_relationship("habits", event_uid, "habit:edge_old")
        ).is_ok

        event_bus.clear_event_history()

        # Edge-only intent: no node properties, only the two edge UIDs.
        intent = EventUpdateIntent(
            milestone_celebration_for_goal="goal:edge_new",
            reinforces_habit_uid="habit:edge_new",
        )
        result = await facade.update_event(event_uid, intent)
        assert result.is_ok

        # The edges now point at the new targets only.
        async with neo4j_driver.session() as session:
            goals = await (
                await session.run(
                    """
                    MATCH (e:Entity {uid: $uid})-[:CELEBRATES_GOAL]->(g)
                    RETURN collect(g.uid) AS uids
                    """,
                    uid=event_uid,
                )
            ).single()
            habits = await (
                await session.run(
                    """
                    MATCH (e:Entity {uid: $uid})-[:REINFORCES_HABIT]->(h)
                    RETURN collect(h.uid) AS uids
                    """,
                    uid=event_uid,
                )
            ).single()
            node = await (
                await session.run(
                    "MATCH (e:Entity {uid: $uid}) RETURN properties(e) AS props",
                    uid=event_uid,
                )
            ).single()

        assert goals["uids"] == ["goal:edge_new"]
        assert habits["uids"] == ["habit:edge_new"]

        # The edge UIDs were never written as node properties (the whole point of the split).
        props = node["props"]
        assert "milestone_celebration_for_goal" not in props
        assert "reinforces_habit_uid" not in props

        # CalendarEventUpdated fired so user-context caches invalidate on an edge-only update.
        updated = [e for e in event_bus.get_event_history() if isinstance(e, CalendarEventUpdated)]
        assert updated, "edge-only update must fire CalendarEventUpdated"
        assert updated[-1].updated_fields == {
            "milestone_celebration_for_goal": "goal:edge_new",
            "reinforces_habit_uid": "habit:edge_new",
        }

    @pytest.mark.asyncio
    async def test_clearing_goal_edge_removes_it_in_neo4j(
        self, facade, core_service, seeded_event, event_bus, neo4j_driver
    ) -> None:
        """Clearing the picker (milestone_celebration_for_goal=None) deletes the
        CELEBRATES_GOAL edge in the graph — the edge-clear UX gap fix, proven end-to-end.

        A habit edge left UNSET in the same intent must stay attached, confirming the
        UNSET=untouched / None=clear contract at the persistence boundary.
        """
        event_uid = seeded_event.uid

        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (g:Entity:Goal {uid: 'goal:to_clear'})
                  ON CREATE SET g.entity_type = 'goal', g.title = 'Goal to clear'
                MERGE (h:Entity:Habit {uid: 'habit:keep'})
                  ON CREATE SET h.entity_type = 'habit', h.title = 'Habit to keep'
                """
            )

        # Seed both edges; only the goal edge will be cleared.
        assert (
            await facade.relationships.create_relationship(
                "celebrated_goals", event_uid, "goal:to_clear"
            )
        ).is_ok
        assert (
            await facade.relationships.create_relationship("habits", event_uid, "habit:keep")
        ).is_ok

        event_bus.clear_event_history()

        # Clear ONLY the goal edge; the habit field is absent (UNSET → untouched).
        result = await facade.update_event(
            event_uid, EventUpdateIntent(milestone_celebration_for_goal=None)
        )
        assert result.is_ok

        async with neo4j_driver.session() as session:
            goals = await (
                await session.run(
                    "MATCH (e:Entity {uid: $uid})-[:CELEBRATES_GOAL]->(g) RETURN collect(g.uid) AS uids",
                    uid=event_uid,
                )
            ).single()
            habits = await (
                await session.run(
                    "MATCH (e:Entity {uid: $uid})-[:REINFORCES_HABIT]->(h) RETURN collect(h.uid) AS uids",
                    uid=event_uid,
                )
            ).single()

        # Goal edge gone; the UNSET habit edge untouched.
        assert goals["uids"] == []
        assert habits["uids"] == ["habit:keep"]

        # CalendarEventUpdated reports the cleared field (None), not the untouched habit.
        updated = [e for e in event_bus.get_event_history() if isinstance(e, CalendarEventUpdated)]
        assert updated, "edge clear must fire CalendarEventUpdated"
        assert updated[-1].updated_fields == {"milestone_celebration_for_goal": None}
