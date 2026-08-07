"""Event creation: the request's relationship fields must become graph EDGES
==========================================================================

Sixth in the create-path reconciliation arc, after ``test_choice_create_path_parity.py``
(#960), ``test_activity_create_validation_reach.py`` (#963),
``test_goal_habit_create_edges.py`` (#965), ``test_task_principle_create_event_reach.py``
(#966) and ``test_task_create_edges.py`` (#967). #967 closed Events' PROPERTY leak — the
skip-set entry it added is keyed on the field NAME, so ``POST /api/events/create`` stopped
persisting ``reinforces_habit_uid`` as a junk node property — and recorded the remaining
half in its own commit message: the route door still wrote no edge, so the value went from
dropped messily to dropped cleanly.

WHAT WAS DROPPED (measured 2026-08-06, route door, before this change)
----------------------------------------------------------------------
``reinforces_habit_uid``
    ``ConversionServiceV2.event_create_to_pure`` set it on the ``Event``, the mapper
    skipped it (correctly — it is DERIVED FROM EDGE), and nothing on the route path wrote
    the REINFORCES_HABIT edge: only ``create_event``, the request door, did. The field
    rides on the ``Event``, which is what makes the fix possible — the edge write moves
    onto the shared create primitive (``EventsCoreService._write_link_edges``), exactly as
    Tasks' #967 and Goals' #965.

DOOR ASYMMETRY (deliberate, asserted below)
-------------------------------------------
``milestone_celebration_for_goal`` (→ CELEBRATES_GOAL) reaches no ``Event`` field, so the
converter drops it before the route door reaches ``create(entity)`` — a link the entity
cannot carry is a link that door can never write. It stays request-door-only, forwarded
into the same guarded batch. ``practices_knowledge_uids`` / ``executes_tasks`` are
accepted by the request and have NEVER produced edges from ``create_event``; that stays
true and is pinned here as a known gap rather than a silent one.

ADMISSION (every endpoint is request input)
-------------------------------------------
A user-supplied UID becomes an edge only if it passes ``keep_permitted_link_edges`` on
three counts — it EXISTS, its OWNER is the creator or nobody, and its KIND is one the
field accepts. ``create_event`` previously wrote both of its edges through
``UnifiedRelationshipService`` with NO owner or kind check — the cross-tenant defect
class #965 recorded — and the registry cannot make the kind check for the habit link:
Events' REINFORCES_HABIT spec declares its target label as ``Entity``.

ERROR SEMANTICS (deliberate contract change)
--------------------------------------------
``create_event`` used to PROPAGATE an edge failure (``Result.fail``), so a bad habit UID
killed the event — while the route door, writing no edge, could not fail at all. Both
doors now agree with Tasks/Goals/Habits: a refused or failed link is logged and the
entity is created anyway.

WHY ORDERING IS PART OF THE CONTRACT
------------------------------------
``CalendarEventCreated`` is subscribed to ``invalidate_context``
(services_bootstrap/_event_wiring.py), which rebuilds the user context — and the rebuild
reads ``(event)-[:REINFORCES_HABIT]->(:Habit)`` back out of the graph
(user_context_queries.py), then caches the result. The old request door wrote its edges
AFTER ``create`` had published — the same inversion Codex reported on #960. The tests
assert the SEQUENCE via an ordered trace.

No Neo4j: the backend is stubbed, so what is under test is the service wiring — which is
exactly where the defect lived. The real-graph half is
``tests/integration/test_event_create_edge_roundtrip.py``.
"""

from datetime import date, time, timedelta
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import (
    RELATIONSHIP_SKIP_FIELDS,
    from_neo4j_node,
    to_neo4j_node,
)
from core.events.calendar_event_events import CalendarEventCreated
from core.events.embedding_events import EventEmbeddingRequested
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import EVENTS_CONFIG
from core.services.conversion_service import ConversionServiceV2
from core.services.events.events_core_service import EventsCoreService
from core.services.events_service import EventsService
from core.utils.result_simplified import Errors, Result

USER_UID = "user:event-edges"
OTHER_USER = "user:someone-else"
HABIT_UID = "habit:morning-pages"
GOAL_UID = "goal:launch-milestone"
KU_UID = "ku.python.decorators"
TASK_UID = "task:prepare-agenda"
TOMORROW = date.today() + timedelta(days=1)


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Round-trips create() like the real backend and records every side effect.

    Mirrors ``UniversalNeo4jBackend._create_node``: whatever it receives is serialized
    with ``to_neo4j_node`` and the round-tripped DOMAIN ENTITY is returned via
    ``from_neo4j_node``. That round-trip is load-bearing here: ``reinforces_habit_uid``
    is a skip-set field, so the persisted event CANNOT carry it — a stub returning the
    input unchanged would hide a service reading the habit off the wrong object.

    ``trace`` is an ORDERED log of side effects, so the tests can assert SEQUENCE rather
    than mere occurrence.

    ``__getattr__`` fails CLOSED: any backend call this stub does not model is an
    assertion failure, not a silent mock. That is also what proves the facade's old
    ``UnifiedRelationshipService`` edge writes are GONE — that path would reach backend
    methods this stub refuses.
    """

    def __init__(self, model: type) -> None:
        self._model = model
        self.created: list[dict[str, Any]] = []
        self.trace: list[str] = []
        # (from_uid, to_uid, rel_type, properties) tuples, as handed to the backend
        self.batched: list[tuple[str, str, str, dict[str, Any] | None]] = []
        # uid -> owning user, for the link-target ownership check. A uid absent from
        # this dict resolves to USER_UID (the same user); mapping one elsewhere stages
        # another user's entity. ``shared`` models content carrying no owner at all —
        # the real query omits those rows, so the stub must omit them too.
        self.owners: dict[str, str] = {}
        self.shared: set[str] = set()
        # uid -> Neo4j labels, for the KIND check. Absent uids default to carrying every
        # label these fields accept (habit, goal), so tests that are not ABOUT the kind
        # check are unaffected. ``missing`` stages a UID resolving to NO node.
        self.labels: dict[str, list[str]] = {}
        self.missing: set[str] = set()
        # Force the batch writer to fail, to pin "the event is created anyway".
        self.batch_fails: bool = False

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, self._model))

    async def create_relationships_batch(self, relationships: Any) -> Result[int]:
        edges = list(relationships)
        if self.batch_fails:
            self.trace.append("edge_batch_failed")
            return Result.fail(Errors.database(operation="create", message="batch exploded"))
        self.batched.extend(edges)
        self.trace.append("link_edges_written")
        return Result.ok(len(edges))

    async def get_owner_uids_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """uid -> owning user UIDs, mirroring the real query's contract."""
        return Result.ok(
            {uid: [self.owners.get(uid, USER_UID)] for uid in uids if uid not in self.shared}
        )

    async def get_node_labels_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """uid -> labels, defaulting to every kind these fields accept."""
        return Result.ok(
            {
                uid: self.labels.get(uid, ["Entity", "Habit", "Goal"])
                for uid in uids
                if uid not in self.missing
            }
        )

    def __getattr__(self, name: str):
        async def _unexpected(*args: Any, **kwargs: Any):
            raise AssertionError(f"backend.{name}() unexpectedly called")

        return _unexpected


class _Inert:
    """Collaborator stub for facade construction — never exercised by create."""

    def __getattr__(self, name: str) -> "_Inert":
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> "_Inert":
        return self


def record_calendar_event_created(bus: InMemoryEventBus, backend: StubBackend) -> None:
    """Interleave CalendarEventCreated into the backend's trace so ordering is
    observable. The two halves — edge writes and event publishes — are otherwise
    recorded in different places and cannot be compared."""

    def _created(event: CalendarEventCreated) -> None:
        backend.trace.append("calendar_event_created_published")

    bus.subscribe(CalendarEventCreated, _created)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest.fixture
def backend() -> StubBackend:
    return StubBackend(Event)


@pytest.fixture
def core(backend: StubBackend, event_bus: InMemoryEventBus) -> EventsCoreService:
    """Both doors: ``create`` (route) and ``create_event`` (request) live here."""
    return EventsCoreService(backend=backend, event_bus=event_bus)


@pytest.fixture
def facade(backend: StubBackend, event_bus: InMemoryEventBus) -> EventsService:
    """The object ``CRUDRouteFactory`` calls ``.create(entity)`` on."""
    return EventsService(
        backend=backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_request(**overrides: Any) -> EventCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Weekly review",
        "description": "Look back, then forward",
        "event_date": TOMORROW,
        "start_time": time(9, 0),
        "end_time": time(10, 0),
    }
    defaults.update(overrides)
    return EventCreateRequest(**defaults)


def route_entity(request: EventCreateRequest, uid: str = "event:door-a") -> Event:
    """Build the entity exactly as ``CRUDRouteFactory._register_create_route`` does."""
    return ConversionServiceV2.event_create_to_pure(request, uid, user_uid=USER_UID)


def edges_of(backend: StubBackend, rel: RelationshipName) -> list[tuple[str, str, str, Any]]:
    return [edge for edge in backend.batched if edge[2] == rel.value]


# ============================================================================
# THE HABIT EDGE — entity-carried, so BOTH doors write it
# ============================================================================


@pytest.mark.asyncio
class TestEventHabitEdgeIsWritten:
    """The defect itself: the route door must write REINFORCES_HABIT from the entity."""

    async def test_route_door_writes_the_edge(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """RED before the fix: the route path wrote no edge at all — the value was
        dropped cleanly (post-#967) instead of messily (pre-#967), but dropped."""
        result = await core.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))

        assert result.is_ok, f"create failed: {result.error}"
        written = edges_of(backend, RelationshipName.REINFORCES_HABIT)
        assert written == [(result.value.uid, HABIT_UID, "REINFORCES_HABIT", None)], (
            "POST /api/events/create dropped reinforces_habit_uid — no edge was written"
        )

    async def test_request_door_writes_it_exactly_once(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """``create_event`` now rides the shared path. Writing its own edge as well —
        the old facade behavior on top of the primitive's — would double-write."""
        result = await core.create_event(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok, f"create_event failed: {result.error}"
        written = edges_of(backend, RelationshipName.REINFORCES_HABIT)
        assert len(written) == 1, f"expected exactly one habit edge, got {written}"
        assert written[0][:2] == (result.value.uid, HABIT_UID)

    async def test_the_uid_is_never_a_node_property(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """#967's half of the fix, pinned against the real serializer."""
        assert "reinforces_habit_uid" in RELATIONSHIP_SKIP_FIELDS
        await core.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))
        assert "reinforces_habit_uid" not in backend.created[0], (
            "reinforces_habit_uid persisted as a node property"
        )

    async def test_an_event_without_a_habit_writes_no_edge(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        result = await core.create(route_entity(make_request()))
        assert result.is_ok
        assert backend.batched == []

    async def test_the_edge_agrees_with_the_registry(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """Direction comes from EVENTS_CONFIG, not from a hand-copied table — a rename
        or a direction flip on the READ side must break this test instead of silently
        orphaning the write (#965's lesson). The spec's target label being ``Entity`` is
        also exactly why the KIND check cannot be delegated to the registry."""
        spec = EVENTS_CONFIG.get_relationship_by_method("habits")
        assert spec is not None, "EVENTS_CONFIG has no 'habits' relationship"
        assert spec.relationship == RelationshipName.REINFORCES_HABIT
        assert spec.direction == "outgoing", (
            "the create path writes the event as the edge SOURCE; a non-outgoing spec "
            "means the write and the read now point opposite ways"
        )
        assert spec.target_label == "Entity", (
            "the registry now declares a specific target label for this edge — "
            "revisit whether the guard's kind check is still the only one"
        )

        result = await core.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))
        written = edges_of(backend, spec.relationship)
        assert written and written[0][0] == result.value.uid, "the event must be the edge SOURCE"


# ============================================================================
# THE CELEBRATED-GOAL EDGE — request-door-only, by structure
# ============================================================================


@pytest.mark.asyncio
class TestEventCelebratedGoalEdge:
    """``milestone_celebration_for_goal`` reaches no Event field, so only the request
    door can write CELEBRATES_GOAL — now via the same guarded batch."""

    async def test_request_door_writes_the_edge(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_event(
            make_request(milestone_celebration_for_goal=GOAL_UID), USER_UID
        )

        assert result.is_ok, f"create_event failed: {result.error}"
        written = edges_of(backend, RelationshipName.CELEBRATES_GOAL)
        assert written == [(result.value.uid, GOAL_UID, "CELEBRATES_GOAL", None)]

    async def test_the_edge_agrees_with_the_registry(self) -> None:
        spec = EVENTS_CONFIG.get_relationship_by_method("celebrated_goals")
        assert spec is not None, "EVENTS_CONFIG has no 'celebrated_goals' relationship"
        assert spec.relationship == RelationshipName.CELEBRATES_GOAL
        assert spec.direction == "outgoing"

    async def test_the_route_door_cannot_carry_it(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """The converter filters by exact field name and ``Event`` has no such field —
        pinned as a known limit of the generated route rather than a silent gap."""
        entity = route_entity(make_request(milestone_celebration_for_goal=GOAL_UID))
        result = await core.create(entity)

        assert result.is_ok
        assert edges_of(backend, RelationshipName.CELEBRATES_GOAL) == []

    async def test_both_links_go_out_in_one_batch(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_event(
            make_request(reinforces_habit_uid=HABIT_UID, milestone_celebration_for_goal=GOAL_UID),
            USER_UID,
        )

        assert result.is_ok
        assert backend.trace.count("link_edges_written") == 1, (
            "the two links must share one all-or-nothing batch"
        )
        assert {edge[2] for edge in backend.batched} == {
            "REINFORCES_HABIT",
            "CELEBRATES_GOAL",
        }
        assert all(edge[0] == result.value.uid for edge in backend.batched)


# ============================================================================
# ADMISSION — exists / owner / kind, per #965
# ============================================================================


@pytest.mark.asyncio
class TestEventLinkAdmission:
    """``create_event`` wrote both edges UNGUARDED through UnifiedRelationshipService —
    no existence, owner or kind check. Every refusal below creates the event anyway."""

    async def test_refuses_a_habit_owned_by_another_user(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        backend.owners[HABIT_UID] = OTHER_USER

        result = await core.create_event(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok, "the event itself is the caller's own and must be created"
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == [], (
            "a cross-user REINFORCES_HABIT edge was admitted"
        )

    async def test_refuses_a_goal_owned_by_another_user(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        backend.owners[GOAL_UID] = OTHER_USER

        result = await core.create_event(
            make_request(milestone_celebration_for_goal=GOAL_UID), USER_UID
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.CELEBRATES_GOAL) == [], (
            "a cross-user CELEBRATES_GOAL edge was admitted"
        )

    async def test_refuses_a_uid_that_is_not_a_habit(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """The field name declares the kind; the registry cannot — its Events-side
        REINFORCES_HABIT spec declares the target label as ``Entity``."""
        backend.labels[GOAL_UID] = ["Entity", "Goal"]

        result = await core.create_event(make_request(reinforces_habit_uid=GOAL_UID), USER_UID)

        assert result.is_ok
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == [], (
            "a Goal was linked as the event's reinforced habit"
        )

    async def test_refuses_a_uid_that_is_not_a_goal(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        backend.labels[HABIT_UID] = ["Entity", "Habit"]

        result = await core.create_event(
            make_request(milestone_celebration_for_goal=HABIT_UID), USER_UID
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.CELEBRATES_GOAL) == []

    async def test_a_dangling_habit_does_not_lose_the_goal_link(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """The batch is all-or-nothing and its failure is logged, so without the
        existence check one stale UID would silently discard every valid link."""
        backend.missing.add(HABIT_UID)

        result = await core.create_event(
            make_request(reinforces_habit_uid=HABIT_UID, milestone_celebration_for_goal=GOAL_UID),
            USER_UID,
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == []
        assert edges_of(backend, RelationshipName.CELEBRATES_GOAL) == [
            (result.value.uid, GOAL_UID, "CELEBRATES_GOAL", None)
        ]

    async def test_edge_failure_does_not_fail_the_create(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        """THE deliberate contract change: ``create_event`` used to propagate an edge
        failure (``return Result.fail(edge)``), so a bad habit UID killed the event —
        while the route door could not fail at all. Both doors now agree with the other
        Activity Domains: the failure is logged and the event is created."""
        backend.batch_fails = True

        result = await core.create_event(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok, (
            "an edge failure killed the event — the two doors were reconciled onto "
            "log-and-continue, deliberately"
        )
        assert "edge_batch_failed" in backend.trace


# ============================================================================
# ORDERING — edges precede the announcement
# ============================================================================


@pytest.mark.asyncio
class TestEdgesPrecedeTheEvent:
    """``CalendarEventCreated`` triggers the user-context rebuild, which reads the
    REINFORCES_HABIT edge back out of the graph. The old request door published first
    and wrote edges second — the #960 inversion, live a third time."""

    async def test_request_door_writes_the_edges_first(
        self, core: EventsCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_calendar_event_created(event_bus, backend)

        await core.create_event(
            make_request(reinforces_habit_uid=HABIT_UID, milestone_celebration_for_goal=GOAL_UID),
            USER_UID,
        )

        assert backend.trace == [
            "node_created",
            "link_edges_written",
            "calendar_event_created_published",
        ]

    async def test_route_door_writes_the_edge_first(
        self, core: EventsCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_calendar_event_created(event_bus, backend)

        await core.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))

        assert backend.trace == [
            "node_created",
            "link_edges_written",
            "calendar_event_created_published",
        ]

    async def test_a_linkless_event_still_publishes(
        self, core: EventsCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_calendar_event_created(event_bus, backend)

        await core.create(route_entity(make_request()))

        assert backend.trace == ["node_created", "calendar_event_created_published"]

    async def test_exactly_one_event_and_one_embedding_request_per_create(
        self, core: EventsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await core.create_event(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        history = event_bus.get_event_history()
        assert len([e for e in history if isinstance(e, CalendarEventCreated)]) == 1
        assert len([e for e in history if isinstance(e, EventEmbeddingRequested)]) == 1


# ============================================================================
# THE UNWIRED LISTS — pinned, not silent
# ============================================================================


@pytest.mark.asyncio
class TestRequestListsRemainUnwired:
    """``practices_knowledge_uids`` and ``executes_tasks`` are accepted by the request
    and have never produced edges from ``create_event`` (the update path documents the
    same drop). Wiring them is a contract change this fix deliberately does not make —
    this pin turns the silence into a statement."""

    async def test_neither_list_writes_an_edge(
        self, core: EventsCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_event(
            make_request(practices_knowledge_uids=[KU_UID], executes_tasks=[TASK_UID]),
            USER_UID,
        )

        assert result.is_ok
        assert backend.batched == []


# ============================================================================
# THE FACADE — one create path, no second writer
# ============================================================================


@pytest.mark.asyncio
class TestFacadeDelegates:
    """The facade's ``create_event`` used to build the entity itself and write its edges
    through ``UnifiedRelationshipService`` AFTER core.create had published. It now
    delegates to the core door; the fail-closed backend stub proves the old edge writes
    are gone — that path would reach backend methods the stub refuses."""

    async def test_create_event_writes_the_edges_via_the_primitive(
        self, facade: EventsService, backend: StubBackend
    ) -> None:
        result = await facade.create_event(
            make_request(reinforces_habit_uid=HABIT_UID, milestone_celebration_for_goal=GOAL_UID),
            USER_UID,
        )

        assert result.is_ok, f"create_event failed: {result.error}"
        assert {edge[2] for edge in backend.batched} == {
            "REINFORCES_HABIT",
            "CELEBRATES_GOAL",
        }

    async def test_route_door_create_writes_the_habit_edge(
        self, facade: EventsService, backend: StubBackend
    ) -> None:
        """The full route-door path: ``CRUDRouteFactory`` → ``EventsService.create`` →
        the primitive."""
        result = await facade.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))

        assert result.is_ok
        written = edges_of(backend, RelationshipName.REINFORCES_HABIT)
        assert written == [(result.value.uid, HABIT_UID, "REINFORCES_HABIT", None)]
