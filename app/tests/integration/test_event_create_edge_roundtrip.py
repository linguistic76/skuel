"""Real-Neo4j round-trip for the edges Event creation now writes.

Sibling of ``test_task_create_edge_roundtrip.py`` (#967). The unit suite
(``tests/unit/test_event_create_edges.py``) stubs the backend, so it proves the service
ASKS for the right edges with the right endpoints. It cannot prove the edge is real,
correctly oriented, or visible to the readers that were empty — and "the writer is wired"
was never the interesting half of this bug.

What was broken (measured 2026-08-06, route door)
--------------------------------------------------
``reinforces_habit_uid``  The route converter set it on the ``Event``, the mapper dropped
                          it (#967 put it in RELATIONSHIP_SKIP_FIELDS), and nothing on
                          that path wrote the REINFORCES_HABIT edge — only
                          ``create_event`` did. So ``POST /api/events/create`` dropped
                          the link cleanly instead of messily: no junk property anymore,
                          but still no edge.

The field rides on the ``Event``, so both doors can write it; the edge write therefore
lives on the shared ``create`` primitive. The headline assertions go through the ROUTE
door, which is where the defect was.

Direction matters and is asserted through the real reader:
``get_habit_links_for_events`` resolves the batch map from the edge as declared in
EVENTS_CONFIG. An edge written backwards persists perfectly and reads back empty — the
failure mode a direction-blind assertion would miss.

Ownership and kind are asserted through ``create_event``, NOT the route door — #967's
lesson: a guard test through a door that never wrote the edge passes vacuously against
the unguarded code. ``create_event`` is the door that WAS writing these edges with no
owner or kind check (through UnifiedRelationshipService, which matches on UID alone), so
these tests are RED against the pre-change source for the right reason. The same door
also pins the deliberate error-semantics change: a refused or dangling link used to fail
the whole create; it now logs and the event is created.
"""

from datetime import date, time, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import EventsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.models.relationship_names import RelationshipName
from core.services.conversion_service import ConversionServiceV2
from core.services.events_service import EventsService

OTHER_USER = "user_test_event_edges_victim"
TOMORROW = date.today() + timedelta(days=1)


@pytest_asyncio.fixture
async def event_bus():
    return InMemoryEventBus(capture_history=True)


class _Inert:
    """Collaborator stub for facade construction — never exercised by create."""

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self


@pytest_asyncio.fixture
async def events_backend(neo4j_driver, clean_neo4j):
    # Multi-label (:Event:Entity) to match production — the relationship registry keys
    # its edge validation off the domain label.
    return EventsBackend(neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY)


@pytest_asyncio.fixture
async def events_service(events_backend, event_bus):
    """The FACADE, not the core service: it is the object the routes call, and —
    decisively for the guard tests — ``EventsService.create_event`` is the door that
    existed BEFORE this change and wrote its edges unguarded. Guard tests through a
    door introduced by the change itself would be RED for the wrong reason
    (AttributeError), proving nothing about admission."""
    return EventsService(
        backend=events_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


@pytest_asyncio.fixture
async def test_user_uid(neo4j_driver, clean_neo4j):
    uid = "user_test_event_create_edges"
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
        )
    return uid


def event_request(**overrides):
    defaults = {
        "title": "Weekly review",
        "description": "Look back, then forward",
        "event_date": TOMORROW,
        "start_time": time(9, 0),
        "end_time": time(10, 0),
    }
    defaults.update(overrides)
    return EventCreateRequest(**defaults)


async def _create_node(neo4j_driver, uid, labels, entity_type, title, user_uid=None):
    """Persist a minimal target node so the batch's registry validation passes.

    ``user_uid=None`` leaves the node UNOWNED, which is how shared content looks to the
    admission guard.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            f"MERGE (n:{labels} {{uid: $uid}}) "
            "ON CREATE SET n.entity_type = $entity_type, n.title = $title, "
            "n.user_uid = $user_uid",
            uid=uid,
            entity_type=entity_type,
            title=title,
            user_uid=user_uid,
        )


async def _route_create(service, request, uid, user_uid):
    """DOOR A — build the entity exactly as ``CRUDRouteFactory`` does, then ``create``.

    The defect lived on this door, so the headline assertions go through it rather than
    through ``create_event``.
    """
    entity = ConversionServiceV2.event_create_to_pure(request, uid, user_uid=user_uid)
    return await service.create(entity)


@pytest.mark.asyncio
class TestHabitEdgeRoundTrip:
    """REINFORCES_HABIT must be a real edge, from BOTH doors, and never a property."""

    async def test_route_door_writes_the_edge_correctly_oriented(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """The assertion the whole change exists for: before it, the route door wrote
        no edge at all — the request's habit link simply vanished."""
        await _create_node(
            neo4j_driver, "habit:rt", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        event = await _route_create(
            events_service,
            event_request(reinforces_habit_uid="habit:rt"),
            "event:rt-habit",
            test_user_uid,
        )
        assert event.is_ok, f"create failed: {event.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[:{RelationshipName.REINFORCES_HABIT.value}]->"
                "(h {uid: 'habit:rt'}) RETURN count(*) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 1, (
            "no REINFORCES_HABIT edge — POST /api/events/create dropped the link"
        )

    async def test_the_edge_is_visible_to_the_batch_reader(
        self, events_service, events_backend, neo4j_driver, test_user_uid
    ) -> None:
        """``get_habit_links_for_events`` — what the enrichment that populates the
        derived ``reinforces_habit_uid`` field calls — must resolve it. This is the
        direction proof: an edge written backwards reads back empty here."""
        await _create_node(
            neo4j_driver, "habit:rt2", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        event = await _route_create(
            events_service,
            event_request(reinforces_habit_uid="habit:rt2"),
            "event:rt-habit2",
            test_user_uid,
        )

        links = await events_backend.get_habit_links_for_events([event.value.uid])
        assert links.is_ok, f"get_habit_links_for_events failed: {links.error}"
        assert links.value.get(event.value.uid) == "habit:rt2", (
            "the reader that populates the derived field cannot see the edge"
        )

    async def test_request_door_writes_it_exactly_once(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """``create_event`` rides the same primitive now — its old post-create edge
        write is gone, so one door writing twice would be a regression here."""
        await _create_node(
            neo4j_driver, "habit:rt3", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        event = await events_service.create_event(
            event_request(reinforces_habit_uid="habit:rt3"), test_user_uid
        )
        assert event.is_ok, f"create_event failed: {event.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[r:{RelationshipName.REINFORCES_HABIT.value}]->() "
                "RETURN count(r) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 1

    async def test_the_uid_is_not_a_node_property(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """#967's half, asserted against the real serializer through the route door."""
        await _create_node(
            neo4j_driver, "habit:rt4", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        event = await _route_create(
            events_service,
            event_request(reinforces_habit_uid="habit:rt4"),
            "event:rt-habit4",
            test_user_uid,
        )

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (e {uid: $uid}) RETURN e.reinforces_habit_uid AS habit_uid",
                uid=event.value.uid,
            )
            row = await result.single()

        assert row is not None
        assert row["habit_uid"] is None, "reinforces_habit_uid persisted as a node property"

    async def test_another_users_habit_is_refused(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """Through ``create_event`` — the door that WAS writing this edge unguarded
        (UnifiedRelationshipService matches on UID and label, no owner filter), so this
        is RED against the pre-change source. A route-door version would have passed
        vacuously: that door wrote no edge at all."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=OTHER_USER,
            )
        await _create_node(
            neo4j_driver, "habit:victims", "Habit:Entity", "habit", "Victim's habit", OTHER_USER
        )

        event = await events_service.create_event(
            event_request(reinforces_habit_uid="habit:victims"), test_user_uid
        )

        assert event.is_ok, "the event itself is the caller's own and must still be created"
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[r:{RelationshipName.REINFORCES_HABIT.value}]->() "
                "RETURN count(r) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a cross-user REINFORCES_HABIT edge reached the graph"

    async def test_a_non_habit_target_is_refused(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """The field name declares the kind; the registry cannot — Events'
        REINFORCES_HABIT spec declares its target label as ``Entity``, so a same-user
        Goal UID would validate and then surface as a habit in every edge reader."""
        await _create_node(
            neo4j_driver, "goal:not-a-habit", "Goal:Entity", "goal", "A goal", test_user_uid
        )

        event = await events_service.create_event(
            event_request(reinforces_habit_uid="goal:not-a-habit"), test_user_uid
        )

        assert event.is_ok
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[r:{RelationshipName.REINFORCES_HABIT.value}]->() "
                "RETURN count(r) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a Goal was linked as the event's reinforced habit"


@pytest.mark.asyncio
class TestCelebratedGoalEdgeRoundTrip:
    """CELEBRATES_GOAL — request-door-only by structure, now guarded and non-fatal."""

    async def test_the_edge_is_written_and_correctly_oriented(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        await _create_node(
            neo4j_driver, "goal:launch", "Goal:Entity", "goal", "Ship the beta", test_user_uid
        )

        event = await events_service.create_event(
            event_request(milestone_celebration_for_goal="goal:launch"), test_user_uid
        )
        assert event.is_ok, f"create_event failed: {event.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[:{RelationshipName.CELEBRATES_GOAL.value}]->"
                "(g {uid: 'goal:launch'}) RETURN count(*) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 1, "no CELEBRATES_GOAL edge from the request door"

    async def test_another_users_goal_is_refused(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """RED against the pre-change source: the unguarded write linked the caller's
        event to the victim's goal, and ``get_goal_celebration_stats`` aggregates over
        exactly this edge."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=OTHER_USER,
            )
        await _create_node(
            neo4j_driver, "goal:victims", "Goal:Entity", "goal", "Victim's goal", OTHER_USER
        )

        event = await events_service.create_event(
            event_request(milestone_celebration_for_goal="goal:victims"), test_user_uid
        )

        assert event.is_ok
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (e {{uid: $event}})-[r:{RelationshipName.CELEBRATES_GOAL.value}]->() "
                "RETURN count(r) AS edges",
                event=event.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a cross-user CELEBRATES_GOAL edge reached the graph"

    async def test_a_dangling_goal_kills_neither_the_event_nor_the_habit_link(
        self, events_service, neo4j_driver, test_user_uid
    ) -> None:
        """The deliberate error-semantics change, against real data: the old door
        PROPAGATED the edge failure, so a goal deleted since the form was rendered
        killed the whole create. Now the event is created, the dangling goal link is
        dropped with a log line, and the valid habit link survives the same batch."""
        await _create_node(
            neo4j_driver, "habit:rt5", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        event = await events_service.create_event(
            event_request(
                reinforces_habit_uid="habit:rt5",
                milestone_celebration_for_goal="goal:deleted-since",
            ),
            test_user_uid,
        )

        assert event.is_ok, (
            "a dangling goal UID killed the event — edge failures are logged, not fatal"
        )
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (e {uid: $event})-[r]->(t) "
                "RETURN type(r) AS rel, t.uid AS target ORDER BY rel",
                event=event.value.uid,
            )
            rows = [(record["rel"], record["target"]) async for record in result]

        assert (RelationshipName.REINFORCES_HABIT.value, "habit:rt5") in rows, (
            "the valid habit link was lost along with the dangling goal link"
        )
        assert all(rel != RelationshipName.CELEBRATES_GOAL.value for rel, _ in rows)
