"""Task creation: the request's relationship fields must become graph EDGES
==========================================================================

Fourth in the create-path reconciliation arc, after
``test_choice_create_path_parity.py`` (#960), ``test_activity_create_validation_reach.py``
(#963), ``test_goal_habit_create_edges.py`` (#965) and
``test_task_principle_create_event_reach.py`` (#966). #966 routed both Task doors through
one create primitive and explicitly did NOT claim field-carriage parity — it recorded the
two divergences below in its own docstring so the silence would not read as parity. This
suite closes them.

WHAT WAS DROPPED (measured 2026-08-05, both doors, before this change)
----------------------------------------------------------------------
``parent_uid``
    ``ConversionServiceV2.task_create_to_pure`` set it on the ``Task``, and the mapper's
    RELATIONSHIP_SKIP_FIELDS then dropped it — correctly, because the hierarchy belongs in
    the graph. But nothing on the route path wrote the edge either: only ``create_task``
    called ``create_subtask_relationship``. So a subtask created through
    ``POST /api/tasks/create`` had no parent in the property AND no parent in the graph.
    It was invisible to ``get_subtasks`` / ``get_parent_task`` / ``get_task_hierarchy``
    and to the user-context MEGA-QUERY's HAS_SUBTASK collection — a subtask with no
    parent at all.

``reinforces_habit_uid``
    The exact inverse: the converter set it and the mapper did NOT skip it, so it
    persisted as a node PROPERTY — while no REINFORCES_HABIT edge was written. Nothing
    reads that property. Every reader of the name resolves it from the edge
    (``get_habit_links_for_tasks``, the registry's ``habit_context``), and the update path
    already split the field off the property patch
    (``TasksService._split_relationship_intent``). The model documented the field as
    "never persisted ... absent from TaskDTO so it is never written to Neo4j" — true of
    the DTO, false of this door, which persists the ENTITY.

Both fields ride on the ``Task``, which is what makes the fix possible at all: the
generated CRUD route hands the service an entity and no request, so a link the entity
cannot carry is a link that door can never write. They are therefore written by the
SHARED path, exactly as Goals writes HAS_SUBGOAL from ``fulfills_goal_uid`` (#965).

DOOR ASYMMETRY (deliberate, asserted below)
-------------------------------------------
``progress_weight`` and the two knowledge lists (``applies_knowledge_uids``,
``prerequisite_knowledge_uids``) cannot work that way — none is a ``Task`` field, so the
converter drops them before the route reaches ``create(entity)``. ``create_task`` is the
only door that still holds them, pinned by ``TestTaskModelCarriesNoLists`` and
``TestTaskEntityDoorCannotCarryLists`` as a structural limit of the entity door (the
generated route now enters through the request door, which carries them) rather than
a silent gap.

ADMISSION (every endpoint is request input)
-------------------------------------------
A user-supplied UID becomes an edge only if it passes ``keep_permitted_link_edges`` on
three counts — it EXISTS, its OWNER is the creator or nobody, and its KIND is one the
field accepts. The knowledge lists were previously written UNGUARDED; #965 recorded that
as the same defect class it had just fixed for Goals and Habits, and they are guarded here
because they share the batch with the new habit edge.

The hierarchy edge needs its own check rather than the batch guard, because it goes
through ``create_hierarchy_relationship``, whose Cypher matches on UID and label with no
owner filter. ``create_task`` was writing it unguarded before now.

WHY ORDERING IS PART OF THE CONTRACT
------------------------------------
``TaskCreated`` is subscribed to ``invalidate_context``
(services_bootstrap/_event_wiring.py), which rebuilds the user context — and the rebuild
reads BOTH ``(task)-[:HAS_SUBTASK]->(subtask)`` and ``(task)-[:APPLIES_KNOWLEDGE]->()``
back out of the graph, then caches the result for 300s. Publishing before the edges exist
caches an edgeless task, and the later substance events reach only substance handlers, so
nothing corrects it. The tests assert the SEQUENCE via an ordered trace: an assertion that
merely finds both an edge write and an event passes against the inversion.

THE SCHEDULING DOORS (fifth chapter)
------------------------------------
``TasksSchedulingService`` held the last two create paths that reached ``backend.create``
directly: ``create_task_with_context`` (DOOR C) and ``create_task_from_path_step``
(DOOR D). Neither published ``TaskCreated`` (no user-context invalidation — the comment
in DOOR C claiming "TaskCreated event is published by TasksCoreService" was FALSE for
that path) nor the ADR-074 embedding request; DOOR C wrote its edges with NO admission
guard and spelled the principle edge with the raw string ``"ALIGNED_WITH"`` — a name the
registry does not know, so the all-or-nothing batch refused every edge in any request
naming a principle. Both doors now delegate to the primitive; DOOR C keeps only its
context-prerequisite gate.

Routing DOOR C through the primitive is also what forced the request's last two link
lists — ``aligned_principle_uids`` → ALIGNED_WITH_PRINCIPLE and
``prerequisite_task_uids`` → BLOCKED_BY — into ``_write_link_edges``, which closes a
second silent gap: ``create_task`` (DOOR B) had been DROPPING both lists entirely.

No Neo4j: the backend is stubbed, so what is under test is the service wiring — which is
exactly where the defect lived.
"""

from datetime import date, time
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import (
    RELATIONSHIP_SKIP_FIELDS,
    from_neo4j_node,
    to_neo4j_node,
)
from core.events.embedding_events import TaskEmbeddingRequested
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBulkAppliedInTask,
)
from core.events.task_events import TaskCreated
from core.models.enums import Priority
from core.models.event.event_request import EventCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import TASKS_CONFIG
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.services.conversion_service import ConversionServiceV2
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.tasks_service import TasksService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

USER_UID = "user:edges"
OTHER_USER = "user:someone-else"
PARENT_TASK = "task:parent"
HABIT_UID = "habit:morning-pages"
KU_ONE = "ku.python.decorators"
KU_TWO = "ku.python.generators"
PRINCIPLE_UID = "principle:deep-work"
PREREQ_TASK = "task:read-the-paper"


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Round-trips create() like the real backend and records every side effect.

    Mirrors ``UniversalNeo4jBackend._create_node``: whatever it receives is serialized
    with ``to_neo4j_node`` and the round-tripped DOMAIN ENTITY is returned via
    ``from_neo4j_node``. Returning the input unchanged would let a field-dropping bug read
    as a pass — and the property half of this suite reads ``created`` directly, so the
    serialization must be the real one.

    ``trace`` is an ORDERED log of side effects, so the tests can assert SEQUENCE rather
    than mere occurrence.

    ``__getattr__`` fails CLOSED: any backend call this stub does not model is an
    assertion failure, not a silent mock. That is what caught each new backend call the
    guard added on #965 — teach it, never loosen it.
    """

    def __init__(self, model: type) -> None:
        self._model = model
        self.created: list[dict[str, Any]] = []
        self.trace: list[str] = []
        # (from_uid, to_uid, rel_type, properties) tuples, as handed to the backend
        self.batched: list[tuple[str, str, str, dict[str, Any] | None]] = []
        # (parent_uid, child_uid, forward_props) as handed to the hierarchy writer
        self.hierarchy: list[tuple[str, str, dict[str, Any] | None]] = []
        # uid -> owning user, for the link-target ownership check. A uid absent from this
        # dict resolves to USER_UID (the same user); mapping one elsewhere stages another
        # user's entity. ``shared`` models content carrying no owner at all (Ku,
        # PathStep) — the real query omits those rows, so the stub must omit them too
        # rather than report a None owner, which would read as a refusal.
        self.owners: dict[str, str] = {}
        self.shared: set[str] = set()
        # uid -> Neo4j labels, for the KIND check. Absent uids default to carrying every
        # label these fields accept (habit, knowledge, principle, prerequisite-task), so
        # tests that are not ABOUT the kind check are unaffected. ``missing`` stages a
        # UID resolving to NO node.
        self.labels: dict[str, list[str]] = {}
        self.missing: set[str] = set()
        # Owner reported by ``get`` for the hierarchy parent, and whether it resolves.
        self.parent_owner: str = USER_UID
        self.parent_found: bool = True
        # Force the two writers to fail, to pin "the task is created anyway".
        self.batch_fails: bool = False
        self.hierarchy_fails: bool = False

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, self._model))

    async def get(self, uid: str) -> Result[Any]:
        """Resolve the hierarchy parent. Same-user and found by DEFAULT, so the edge
        tests exercise the writing path; ``TestTaskHierarchyEdgeChecksOwnership`` flips
        both flags, which is the case the guard exists for."""
        if not self.parent_found:
            return Result.fail(Errors.not_found("Task", uid))
        return Result.ok(self._model(uid=uid, user_uid=self.parent_owner, title="Existing"))

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
                uid: self.labels.get(uid, ["Entity", "Habit", "Ku", "Principle", "Task"])
                for uid in uids
                if uid not in self.missing
            }
        )

    async def create_hierarchy_relationship(
        self, parent_uid: str, child_uid: str, forward_props: dict[str, Any] | None = None
    ) -> Result[bool]:
        if self.hierarchy_fails:
            self.trace.append("hierarchy_edge_failed")
            return Result.fail(Errors.database(operation="create", message="cycle"))
        self.hierarchy.append((parent_uid, child_uid, forward_props))
        self.trace.append("hierarchy_edge_written")
        return Result.ok(True)

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


def record_task_created(bus: InMemoryEventBus, backend: StubBackend) -> None:
    """Interleave TaskCreated into the backend's trace so ordering is observable.

    The two halves — edge writes and event publishes — are otherwise recorded in
    different places and cannot be compared.
    """

    def _created(event: TaskCreated) -> None:
        backend.trace.append("task_created_published")

    bus.subscribe(TaskCreated, _created)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest.fixture
def backend() -> StubBackend:
    return StubBackend(Task)


@pytest.fixture
def core(backend: StubBackend, event_bus: InMemoryEventBus) -> TasksCoreService:
    """DOOR B — the UI/request door (``tasks_service.create_task``)."""
    return TasksCoreService(backend=backend, event_bus=event_bus)


@pytest.fixture
def facade(backend: StubBackend, event_bus: InMemoryEventBus) -> TasksService:
    """DOOR A — the ENTITY door (``.create(entity)``); the generated route entered
    here until it was bound to the request door (``request_create_method``)."""
    return TasksService(
        backend=backend,
        cross_domain_query=_Inert(),
        graph_intel=_Inert(),
        event_bus=event_bus,
    )


@pytest.fixture
def scheduling(backend: StubBackend, core: TasksCoreService) -> TasksSchedulingService:
    """DOORS C and D — the context-gated and curriculum creates, primitive-routed."""
    return TasksSchedulingService(backend=backend, core=core)


def make_context(**overrides: Any) -> UserContext:
    """A user context that PASSES DOOR C's prerequisite gate for these fixtures."""
    defaults: dict[str, Any] = {
        "user_uid": USER_UID,
        "prerequisites_completed": {KU_ONE, KU_TWO},
        "completed_task_uids": {PREREQ_TASK},
    }
    defaults.update(overrides)
    return UserContext(**defaults)


def make_request(**overrides: Any) -> TaskCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Draft the migration plan",
        "description": "One page, decisions only",
        "priority": Priority.HIGH,
    }
    defaults.update(overrides)
    return TaskCreateRequest(**defaults)


def route_entity(request: TaskCreateRequest, uid: str = "task:door-a") -> Task:
    """Build the entity exactly as ``CRUDRouteFactory._register_create_route`` does."""
    return ConversionServiceV2.task_create_to_pure(request, uid, user_uid=USER_UID)


def edges_of(backend: StubBackend, rel: RelationshipName) -> list[tuple[str, str, str, Any]]:
    return [edge for edge in backend.batched if edge[2] == rel.value]


# ============================================================================
# THE HIERARCHY EDGE
# ============================================================================


@pytest.mark.asyncio
class TestTaskHierarchyEdgeIsWritten:
    """``parent_uid`` must produce the edge every hierarchy reader traverses."""

    async def test_request_door_writes_the_edge(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert result.is_ok, f"create_task failed: {result.error}"
        assert backend.hierarchy, "no HAS_SUBTASK edge was written"
        parent_uid, child_uid, _props = backend.hierarchy[0]
        assert parent_uid == PARENT_TASK
        assert child_uid == result.value.uid

    async def test_entity_door_writes_the_edge_too(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """RED before the fix: the route door wrote NO edge and the mapper dropped the
        property, so a subtask created through the API had no parent at all."""
        entity = route_entity(make_request(parent_uid=PARENT_TASK))
        result = await facade.create(entity)

        assert result.is_ok, f"create failed: {result.error}"
        assert backend.hierarchy, (
            "no HAS_SUBTASK edge was written by the generated CRUD route — parent_uid is "
            "dropped by RELATIONSHIP_SKIP_FIELDS, so this task has no parent anywhere"
        )
        parent_uid, child_uid, _props = backend.hierarchy[0]
        assert parent_uid == PARENT_TASK
        assert child_uid == entity.uid

    async def test_parent_uid_is_never_a_node_property(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """The edge REPLACES the property — it does not join it."""
        await facade.create(route_entity(make_request(parent_uid=PARENT_TASK)))

        assert "parent_uid" not in backend.created[0]

    async def test_progress_weight_lands_on_the_edge(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """``progress_weight`` is a property of the EDGE, not of Task — only the request
        door can supply a non-default, which is why it is a parameter and not a field."""
        await core.create_task(make_request(parent_uid=PARENT_TASK, progress_weight=0.25), USER_UID)

        _parent, _child, props = backend.hierarchy[0]
        assert props == {"progress_weight": 0.25}

    async def test_entity_door_default_weight_matches_the_request_model(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """The entity door has no weight to pass, so its default must equal the one the
        request model would have produced — otherwise the same subtask counts differently
        depending on which door created it."""
        await facade.create(route_entity(make_request(parent_uid=PARENT_TASK)))

        _parent, _child, props = backend.hierarchy[0]
        assert props is not None
        assert props["progress_weight"] == TaskCreateRequest.model_fields["progress_weight"].default

    async def test_a_parentless_task_writes_no_edge(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_task(make_request(), USER_UID)

        assert result.is_ok
        assert backend.hierarchy == []

    async def test_edge_failure_does_not_fail_the_create(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """The task itself is legitimate — a refused edge must not lose it."""
        backend.hierarchy_fails = True

        result = await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert result.is_ok, "a failed hierarchy edge must not fail the create"
        assert "hierarchy_edge_failed" in backend.trace


@pytest.mark.asyncio
class TestTaskHierarchyEdgeChecksOwnership:
    """``parent_uid`` is attacker-controlled and the hierarchy Cypher has no owner filter.

    Without this check a caller could point a new task at ANOTHER user's task: the
    victim's context rebuild starts from the tasks they own and traverses HAS_SUBTASK
    without filtering the child's owner, so the attacker's task would surface in the
    victim's cached context.
    """

    async def test_refuses_a_parent_owned_by_another_user(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.parent_owner = OTHER_USER

        result = await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert result.is_ok, "the task itself is the caller's own and must still be created"
        assert backend.hierarchy == [], "wrote a cross-user HAS_SUBTASK edge"

    async def test_still_links_when_the_parent_is_the_same_user(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """The complement: a guard that refused everything would pass the test above."""
        backend.parent_owner = USER_UID

        await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert len(backend.hierarchy) == 1

    async def test_a_missing_parent_writes_no_edge_and_still_creates(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.parent_found = False

        result = await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert result.is_ok
        assert backend.hierarchy == []

    async def test_the_entity_door_is_guarded_too(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """Both doors reach one write site, so both inherit the check — the point of
        putting the write on the shared path rather than in ``create_task``."""
        backend.parent_owner = OTHER_USER

        result = await facade.create(route_entity(make_request(parent_uid=PARENT_TASK)))

        assert result.is_ok
        assert backend.hierarchy == []


# ============================================================================
# THE HABIT EDGE
# ============================================================================


@pytest.mark.asyncio
class TestTaskHabitEdgeIsWritten:
    """``reinforces_habit_uid`` must be an edge, and must never be a node property."""

    async def test_request_door_writes_the_edge(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_task(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok
        habit_edges = edges_of(backend, RelationshipName.REINFORCES_HABIT)
        assert habit_edges == [(result.value.uid, HABIT_UID, "REINFORCES_HABIT", None)]

    async def test_entity_door_writes_the_edge_too(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """RED before the fix: the route door wrote a node PROPERTY and no edge."""
        entity = route_entity(make_request(reinforces_habit_uid=HABIT_UID))
        result = await facade.create(entity)

        assert result.is_ok
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == [
            (entity.uid, HABIT_UID, "REINFORCES_HABIT", None)
        ], "the generated CRUD route wrote no REINFORCES_HABIT edge"

    async def test_the_uid_is_never_a_node_property(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        """RED before the fix. The model documents this field as edge-backed; the claim
        rested on the field's absence from TaskDTO, and this door persists the ENTITY."""
        await facade.create(route_entity(make_request(reinforces_habit_uid=HABIT_UID)))

        assert "reinforces_habit_uid" not in backend.created[0], (
            "reinforces_habit_uid was written as a node property — no reader consults it, "
            "and it contradicts the model's own DERIVED FROM EDGE contract"
        )

    async def test_the_skip_set_is_what_enforces_it(self) -> None:
        """Pin the mechanism, not just the outcome: the property is kept off the node by
        the mapper's skip-set, so any future create path inherits the guarantee."""
        assert "reinforces_habit_uid" in RELATIONSHIP_SKIP_FIELDS

    async def test_both_doors_carry_the_field_on_the_entity(self) -> None:
        """The edge can only be written from the shared path if BOTH doors put the value
        on the Task. ``from_request`` did not, which is why the route door's converter was
        the only one setting it — in the wrong place."""
        request = make_request(reinforces_habit_uid=HABIT_UID)

        assert Task.from_request(request, user_uid=USER_UID).reinforces_habit_uid == HABIT_UID
        assert route_entity(request).reinforces_habit_uid == HABIT_UID

    async def test_a_task_without_a_habit_writes_no_edge(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_task(make_request(), USER_UID)

        assert result.is_ok
        assert backend.batched == []

    async def test_refuses_a_habit_owned_by_another_user(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.owners[HABIT_UID] = OTHER_USER

        result = await core.create_task(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == []

    async def test_refuses_a_uid_that_is_not_a_habit(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """The field name is what declares the kind — the registry cannot: its Task-side
        REINFORCES_HABIT spec declares the target label as ``Entity``."""
        backend.labels[HABIT_UID] = ["Entity", "Goal"]

        result = await core.create_task(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok
        assert edges_of(backend, RelationshipName.REINFORCES_HABIT) == []

    async def test_refuses_a_habit_uid_that_resolves_to_no_node(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.missing.add(HABIT_UID)

        result = await core.create_task(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)

        assert result.is_ok
        assert backend.batched == []


class TestEventHabitUidIsNotAProperty:
    """``Event`` carries the same field name with the same DERIVED FROM EDGE contract, and
    ``POST /api/events/create`` had the identical property leak. Adding the field to
    RELATIONSHIP_SKIP_FIELDS fixes both — this pins the second one, since a skip-set entry
    is global and its blast radius is the census, not the domain that motivated it.

    The Events ROUTE door has since been wired to write the edge too — its create
    primitive mirrors Tasks' (``EventsCoreService._write_link_edges``), covered by
    ``test_event_create_edges.py``.
    """

    def test_the_route_converter_no_longer_persists_it(self) -> None:
        request = EventCreateRequest(
            title="Morning pages",
            event_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            reinforces_habit_uid=HABIT_UID,
        )
        entity = ConversionServiceV2.event_create_to_pure(request, "event:x", user_uid=USER_UID)

        assert entity.reinforces_habit_uid == HABIT_UID, "the converter still carries it"
        assert "reinforces_habit_uid" not in to_neo4j_node(entity), (
            "Event.reinforces_habit_uid persisted as a node property"
        )

    def test_only_task_and_event_carry_the_field(self) -> None:
        """The census that licensed the skip-set entry, as an assertion.

        A skip-set entry is keyed on the NAME, so it reaches every dataclass with that
        field. Both are documented DERIVED FROM EDGE, so both want the entry — but a
        third, persisted, carrier would have made this change silently lossy.
        """
        import importlib
        import inspect
        import pkgutil
        from dataclasses import fields, is_dataclass

        import core.models

        carriers: set[str] = set()
        for module_info in pkgutil.walk_packages(core.models.__path__, "core.models."):
            module = importlib.import_module(module_info.name)
            for obj in vars(module).values():
                if not (inspect.isclass(obj) and is_dataclass(obj)):
                    continue
                if obj.__module__ != module.__name__:
                    continue
                if any(f.name == "reinforces_habit_uid" for f in fields(obj)):
                    carriers.add(obj.__qualname__)

        # The two UpdateIntents are not persisted through to_neo4j_node at all — the
        # update path splits this field off the property patch before it is written
        # (TasksService._split_relationship_intent, EventsService._split_relationship_intent).
        assert carriers == {"Task", "Event", "TaskUpdateIntent", "EventUpdateIntent"}


# ============================================================================
# THE KNOWLEDGE LISTS
# ============================================================================


@pytest.mark.asyncio
class TestTaskKnowledgeLinks:
    """The two request-only lists, and the admission guard they had been missing."""

    async def test_every_list_goes_out_in_one_batch(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_task(
            make_request(
                reinforces_habit_uid=HABIT_UID,
                applies_knowledge_uids=[KU_ONE],
                prerequisite_knowledge_uids=[KU_TWO],
                aligned_principle_uids=[PRINCIPLE_UID],
                prerequisite_task_uids=[PREREQ_TASK],
            ),
            USER_UID,
        )

        assert result.is_ok
        assert backend.trace.count("link_edges_written") == 1, "more than one batch"
        assert {edge[2] for edge in backend.batched} == {
            RelationshipName.APPLIES_KNOWLEDGE.value,
            RelationshipName.REQUIRES_KNOWLEDGE.value,
            RelationshipName.REINFORCES_HABIT.value,
            RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
            RelationshipName.BLOCKED_BY.value,
        }

    @pytest.mark.parametrize(
        ("field", "method_key"),
        [
            ("applies_knowledge_uids", "knowledge"),
            ("prerequisite_knowledge_uids", "prerequisite_knowledge"),
            ("aligned_principle_uids", "principles"),
            ("prerequisite_task_uids", "blocked_by"),
        ],
    )
    async def test_edge_agrees_with_the_registry(
        self, core: TasksCoreService, backend: StubBackend, field: str, method_key: str
    ) -> None:
        """Direction comes from TASKS_CONFIG, not from a hand-copied table.

        The create path names its relationships literally, and every assertion above
        spells the tuple out as ``(task, target, REL, None)`` — which is a second copy of
        the same guess. #965's Habits sibling learned this the hard way: direction is NOT
        uniform within a domain (Goals' ``supporting_habits`` is declared INCOMING), and
        an edge written backwards persists perfectly and reads back empty. Deriving the
        expectation from the registry means a rename or a direction flip on the READ side
        breaks this test instead of silently orphaning the write.
        """
        spec = TASKS_CONFIG.get_relationship_by_method(method_key)
        assert spec is not None, f"TASKS_CONFIG has no '{method_key}' relationship"

        result = await core.create_task(make_request(**{field: [KU_ONE]}), USER_UID)
        assert result.is_ok, f"create_task failed: {result.error}"

        written = edges_of(backend, spec.relationship)
        assert written, (
            f"{field} wrote no {spec.relationship.value} edge — the registry reads "
            f"'{method_key}' from that relationship"
        )
        assert spec.direction == "outgoing", (
            f"'{method_key}' is declared {spec.direction}; the create path writes the "
            "task as the edge SOURCE, so a non-outgoing spec means the write and the "
            "read now point opposite ways"
        )
        assert written[0][0] == result.value.uid

    async def test_habit_edge_agrees_with_the_registry(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """Same, for the entity-carried habit link. Its Task-side spec declares the target
        label as ``Entity``, which is exactly why the KIND check cannot be delegated to
        the registry — but the DIRECTION is the registry's to declare."""
        spec = TASKS_CONFIG.get_relationship_by_method("habits")
        assert spec is not None, "TASKS_CONFIG has no 'habits' relationship"
        assert spec.relationship == RelationshipName.REINFORCES_HABIT
        assert spec.direction == "outgoing"

        result = await core.create_task(make_request(reinforces_habit_uid=HABIT_UID), USER_UID)
        assert result.is_ok

        written = edges_of(backend, spec.relationship)
        assert written, "no REINFORCES_HABIT edge"
        assert written[0][0] == result.value.uid, "the task must be the edge SOURCE"
        assert written[0][1] == HABIT_UID

    async def test_shared_knowledge_is_still_linkable(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """ "Owned by nobody" must mean ALLOWED — a Ku carries no owner, and a blunt
        "every endpoint must be mine" rule would break every knowledge list."""
        backend.shared.add(KU_ONE)

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert len(edges_of(backend, RelationshipName.APPLIES_KNOWLEDGE)) == 1

    async def test_refuses_knowledge_owned_by_another_user(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.owners[KU_ONE] = OTHER_USER

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert edges_of(backend, RelationshipName.APPLIES_KNOWLEDGE) == []

    async def test_a_non_knowledge_uid_is_refused(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.labels[KU_ONE] = ["Entity", "Habit"]

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert edges_of(backend, RelationshipName.APPLIES_KNOWLEDGE) == []

    async def test_only_the_offending_edge_is_dropped(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """The batch is all-or-nothing at the DATABASE, so the guard must filter before
        it — otherwise one bad UID costs every valid link in the same request."""
        backend.owners[KU_TWO] = OTHER_USER

        await core.create_task(
            make_request(reinforces_habit_uid=HABIT_UID, applies_knowledge_uids=[KU_ONE, KU_TWO]),
            USER_UID,
        )

        applied = edges_of(backend, RelationshipName.APPLIES_KNOWLEDGE)
        assert [edge[1] for edge in applied] == [KU_ONE]
        assert len(edges_of(backend, RelationshipName.REINFORCES_HABIT)) == 1

    async def test_a_dangling_uid_does_not_lose_the_valid_links(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """Not an attack — a Ku deleted since the form was rendered does this."""
        backend.missing.add(KU_TWO)

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE, KU_TWO]), USER_UID)

        assert [edge[1] for edge in edges_of(backend, RelationshipName.APPLIES_KNOWLEDGE)] == [
            KU_ONE
        ]

    async def test_batch_failure_does_not_fail_the_create(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.batch_fails = True

        result = await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert result.is_ok
        assert "edge_batch_failed" in backend.trace


@pytest.mark.asyncio
class TestTaskPrincipleAndPrerequisiteTaskLinks:
    """The request's last two link lists, which DOOR B had been dropping entirely.

    ``aligned_principle_uids`` and ``prerequisite_task_uids`` are request fields the
    update path already treats as edges, yet ``create_task`` wrote neither. Their one
    writer was ``create_task_with_context`` — unguarded, and spelling the principle
    edge ``"ALIGNED_WITH"``, which no registry entry and no reader knows. They join
    the shared batch here with the same admission checks as the rest.
    """

    async def test_a_principle_owned_by_another_user_is_refused(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.owners[PRINCIPLE_UID] = OTHER_USER

        result = await core.create_task(
            make_request(aligned_principle_uids=[PRINCIPLE_UID]), USER_UID
        )

        assert result.is_ok, "the task itself is the caller's own and must still be created"
        assert edges_of(backend, RelationshipName.ALIGNED_WITH_PRINCIPLE) == []

    async def test_a_prerequisite_task_owned_by_another_user_is_refused(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        """The same cross-tenant class #965 closed for Goals and Habits: an unchecked
        BLOCKED_BY edge would let a caller chain their task onto a victim's."""
        backend.owners[PREREQ_TASK] = OTHER_USER

        result = await core.create_task(
            make_request(prerequisite_task_uids=[PREREQ_TASK]), USER_UID
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.BLOCKED_BY) == []

    async def test_a_uid_that_is_not_a_principle_is_refused(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.labels[PRINCIPLE_UID] = ["Entity", "Goal"]

        result = await core.create_task(
            make_request(aligned_principle_uids=[PRINCIPLE_UID]), USER_UID
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.ALIGNED_WITH_PRINCIPLE) == []

    async def test_a_uid_that_is_not_a_task_is_refused(
        self, core: TasksCoreService, backend: StubBackend
    ) -> None:
        backend.labels[PREREQ_TASK] = ["Entity", "Goal"]

        result = await core.create_task(
            make_request(prerequisite_task_uids=[PREREQ_TASK]), USER_UID
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.BLOCKED_BY) == []

    async def test_neither_list_announces_knowledge_substance(
        self, core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Alignment and blocking are not knowledge application — only
        APPLIES_KNOWLEDGE credits substance."""
        await core.create_task(
            make_request(
                aligned_principle_uids=[PRINCIPLE_UID],
                prerequisite_task_uids=[PREREQ_TASK],
            ),
            USER_UID,
        )

        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]


class TestTaskModelCarriesNoLists:
    """The structural limit of the ENTITY door, pinned so it is not silent — the
    generated route left this door when it was bound to ``create_task``.

    ``progress_weight`` and the two knowledge lists are not ``Task`` fields, so the
    converter drops them and no entity can carry them. Unlike the two fields this change
    fixed, there is nothing on the entity to write them FROM.
    """

    def test_task_carries_neither_knowledge_list(self) -> None:
        from dataclasses import fields

        field_names = {f.name for f in fields(Task)}
        assert "applies_knowledge_uids" not in field_names
        assert "prerequisite_knowledge_uids" not in field_names
        assert "progress_weight" not in field_names


@pytest.mark.asyncio
class TestTaskEntityDoorCannotCarryLists:
    """The route door's half of the limit above, at the wiring level."""

    async def test_entity_door_writes_no_knowledge_edges(
        self, facade: TasksService, backend: StubBackend
    ) -> None:
        entity = route_entity(
            make_request(applies_knowledge_uids=[KU_ONE], prerequisite_knowledge_uids=[KU_TWO])
        )
        result = await facade.create(entity)

        assert result.is_ok
        assert backend.batched == []


# ============================================================================
# KNOWLEDGE SUBSTANCE
# ============================================================================


@pytest.mark.asyncio
class TestKnowledgeSubstanceFollowsTheEdges:
    """Substance is announced from the uids WRITTEN, never from those requested."""

    async def test_single_link_publishes_the_single_event(
        self, core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        applied = [
            e for e in event_bus.get_event_history() if isinstance(e, KnowledgeAppliedInTask)
        ]
        assert len(applied) == 1
        assert applied[0].knowledge_uid == KU_ONE
        assert not [
            e for e in event_bus.get_event_history() if isinstance(e, KnowledgeBulkAppliedInTask)
        ]

    async def test_multiple_links_publish_the_bulk_event(
        self, core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE, KU_TWO]), USER_UID)

        bulk = [
            e for e in event_bus.get_event_history() if isinstance(e, KnowledgeBulkAppliedInTask)
        ]
        assert len(bulk) == 1
        assert bulk[0].knowledge_uids == (KU_ONE, KU_TWO)

    async def test_a_refused_link_announces_no_substance(
        self, core: TasksCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """RED against the old code, which published from ``task_request``: a link the
        guard refuses would have credited knowledge that no edge backs."""
        backend.owners[KU_ONE] = OTHER_USER

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]

    async def test_a_failed_batch_announces_no_substance(
        self, core: TasksCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        backend.batch_fails = True

        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE]), USER_UID)

        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]

    async def test_a_repeated_uid_is_counted_once(
        self, core: TasksCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """The batch MERGEs (one edge) but the bulk event UNWINDs (one credit per row)."""
        await core.create_task(make_request(applies_knowledge_uids=[KU_ONE, KU_ONE]), USER_UID)

        applied = [
            e for e in event_bus.get_event_history() if isinstance(e, KnowledgeAppliedInTask)
        ]
        assert len(applied) == 1, "a repeated uid announced substance twice"
        assert applied[0].knowledge_uid == KU_ONE

    async def test_prerequisite_knowledge_announces_no_applied_substance(
        self, core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """REQUIRES_KNOWLEDGE is not application — only APPLIES_KNOWLEDGE credits."""
        await core.create_task(make_request(prerequisite_knowledge_uids=[KU_TWO]), USER_UID)

        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]


# ============================================================================
# ORDERING
# ============================================================================


@pytest.mark.asyncio
class TestEdgesPrecedeTheEvent:
    """``TaskCreated`` drives a debounced context rebuild that reads these very edges and
    caches the result for 300s. The assertions are on SEQUENCE — "both happened" passes
    against the inversion this guards.
    """

    async def test_request_door_writes_every_edge_first(
        self, core: TasksCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_task_created(event_bus, backend)

        await core.create_task(
            make_request(
                parent_uid=PARENT_TASK,
                reinforces_habit_uid=HABIT_UID,
                applies_knowledge_uids=[KU_ONE],
            ),
            USER_UID,
        )

        assert backend.trace == [
            "node_created",
            "hierarchy_edge_written",
            "link_edges_written",
            "task_created_published",
        ]

    async def test_entity_door_writes_every_edge_first(
        self, facade: TasksService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_task_created(event_bus, backend)

        await facade.create(
            route_entity(make_request(parent_uid=PARENT_TASK, reinforces_habit_uid=HABIT_UID))
        )

        assert backend.trace == [
            "node_created",
            "hierarchy_edge_written",
            "link_edges_written",
            "task_created_published",
        ]

    async def test_exactly_one_event_per_create(
        self, core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Routing ``create_task`` through the shared primitive must not double-publish."""
        await core.create_task(make_request(parent_uid=PARENT_TASK), USER_UID)

        assert len([e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]) == 1

    async def test_a_linkless_task_still_publishes(
        self, facade: TasksService, event_bus: InMemoryEventBus
    ) -> None:
        await facade.create(route_entity(make_request()))

        assert len([e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]) == 1


# ============================================================================
# THE SCHEDULING DOORS
# ============================================================================


@pytest.mark.asyncio
class TestContextDoorReachesThePrimitive:
    """DOOR C — ``create_task_with_context``: the context-prerequisite gate, then the
    primitive. Before this change it reached ``backend.create`` directly: no
    ``TaskCreated`` (its own comment claiming TasksCoreService published it was false
    for this path), no embedding request, no admission guard, and a principle edge
    spelled ``"ALIGNED_WITH"`` — unknown to the registry, so the all-or-nothing batch
    refused every edge in any request naming a principle.
    """

    async def test_every_edge_precedes_the_event(
        self, scheduling: TasksSchedulingService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_task_created(event_bus, backend)

        result = await scheduling.create_task_with_context(
            make_request(
                reinforces_habit_uid=HABIT_UID,
                applies_knowledge_uids=[KU_ONE],
                aligned_principle_uids=[PRINCIPLE_UID],
                prerequisite_task_uids=[PREREQ_TASK],
            ),
            make_context(),
        )

        assert result.is_ok, f"create_task_with_context failed: {result.error}"
        assert backend.trace == [
            "node_created",
            "link_edges_written",
            "task_created_published",
        ]

    async def test_the_principle_edge_bears_the_registered_name(
        self, scheduling: TasksSchedulingService, backend: StubBackend
    ) -> None:
        """RED before the fix twice over: the old door wrote ``"ALIGNED_WITH"``, which
        no reader resolves (every consumer matches ALIGNED_WITH_PRINCIPLE) — and which
        the registry-validating batch would have refused wholesale at runtime."""
        result = await scheduling.create_task_with_context(
            make_request(aligned_principle_uids=[PRINCIPLE_UID]), make_context()
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.ALIGNED_WITH_PRINCIPLE) == [
            (result.value.uid, PRINCIPLE_UID, "ALIGNED_WITH_PRINCIPLE", None)
        ]
        assert "ALIGNED_WITH" not in {edge[2] for edge in backend.batched}

    async def test_prerequisite_tasks_become_blocked_by_edges(
        self, scheduling: TasksSchedulingService, backend: StubBackend
    ) -> None:
        result = await scheduling.create_task_with_context(
            make_request(prerequisite_task_uids=[PREREQ_TASK]), make_context()
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.BLOCKED_BY) == [
            (result.value.uid, PREREQ_TASK, "BLOCKED_BY", None)
        ]

    async def test_the_task_is_announced_and_embedding_requested(
        self, scheduling: TasksSchedulingService, event_bus: InMemoryEventBus
    ) -> None:
        """The two announcements this door never made: TaskCreated drives the user's
        context invalidation, TaskEmbeddingRequested (ADR-074) gets the task embedded."""
        await scheduling.create_task_with_context(make_request(), make_context())

        history = event_bus.get_event_history()
        assert len([e for e in history if isinstance(e, TaskCreated)]) == 1
        assert len([e for e in history if isinstance(e, TaskEmbeddingRequested)]) == 1

    async def test_a_cross_user_link_is_refused_but_the_task_created(
        self, scheduling: TasksSchedulingService, backend: StubBackend
    ) -> None:
        """The admission guard this door lacked — its edges were written from request
        UIDs with no exists/owner/kind check."""
        backend.owners[PRINCIPLE_UID] = OTHER_USER

        result = await scheduling.create_task_with_context(
            make_request(aligned_principle_uids=[PRINCIPLE_UID]), make_context()
        )

        assert result.is_ok
        assert edges_of(backend, RelationshipName.ALIGNED_WITH_PRINCIPLE) == []

    async def test_a_missing_knowledge_prerequisite_blocks_the_create(
        self, scheduling: TasksSchedulingService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """The gate is what this door ADDS to the primitive — it must still hold, and
        it must refuse BEFORE anything persists or publishes."""
        result = await scheduling.create_task_with_context(
            make_request(prerequisite_knowledge_uids=[KU_ONE]),
            make_context(prerequisites_completed=set()),
        )

        assert result.is_error
        assert backend.trace == [], "a refused create persisted something"
        assert not [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]

    async def test_an_incomplete_task_prerequisite_blocks_the_create(
        self, scheduling: TasksSchedulingService, backend: StubBackend
    ) -> None:
        result = await scheduling.create_task_with_context(
            make_request(prerequisite_task_uids=[PREREQ_TASK]),
            make_context(completed_task_uids=set()),
        )

        assert result.is_error
        assert backend.trace == []

    async def test_substance_follows_the_written_uids(
        self, scheduling: TasksSchedulingService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """Inherited from the primitive: a refused knowledge link announces nothing."""
        backend.owners[KU_ONE] = OTHER_USER

        await scheduling.create_task_with_context(
            make_request(applies_knowledge_uids=[KU_ONE]), make_context()
        )

        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]


@pytest.mark.asyncio
class TestCurriculumDoorReachesThePrimitive:
    """DOOR D — ``create_task_from_path_step``: hand-builds the entity (curriculum
    linkage rides on ``source_path_step_uid``, which no request carries) and hands it
    to the primitive's entity door. Before this change it reached ``backend.create``
    directly: a curriculum task invisible to the user's cached context for its full
    300s TTL, and never embedded.
    """

    async def test_the_task_is_announced_after_persist(
        self, scheduling: TasksSchedulingService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_task_created(event_bus, backend)

        result = await scheduling.create_task_from_path_step(
            step_uid="ps.python.decorators",
            task_title="Practice: decorators",
            knowledge_uids=[KU_ONE],
            user_uid=USER_UID,
        )

        assert result.is_ok, f"create_task_from_path_step failed: {result.error}"
        assert backend.trace == ["node_created", "task_created_published"]

    async def test_embedding_is_requested(
        self, scheduling: TasksSchedulingService, event_bus: InMemoryEventBus
    ) -> None:
        await scheduling.create_task_from_path_step(
            step_uid="ps.python.decorators",
            task_title="Practice: decorators",
            knowledge_uids=[],
            user_uid=USER_UID,
        )

        history = event_bus.get_event_history()
        assert len([e for e in history if isinstance(e, TaskEmbeddingRequested)]) == 1

    async def test_the_curriculum_linkage_is_a_node_property(
        self, scheduling: TasksSchedulingService, backend: StubBackend
    ) -> None:
        """``source_path_step_uid`` is the reason this door builds an entity at all."""
        await scheduling.create_task_from_path_step(
            step_uid="ps.python.decorators",
            task_title="Practice: decorators",
            knowledge_uids=[],
            user_uid=USER_UID,
        )

        assert backend.created[0]["source_path_step_uid"] == "ps.python.decorators"

    async def test_knowledge_uids_write_no_edges_yet(
        self, scheduling: TasksSchedulingService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """The documented deferral, pinned so its closure is a deliberate change: the
        primitive writes knowledge edges only from a create REQUEST, and this door has
        none — so the list must produce neither edges nor substance."""
        await scheduling.create_task_from_path_step(
            step_uid="ps.python.decorators",
            task_title="Practice: decorators",
            knowledge_uids=[KU_ONE, KU_TWO],
            user_uid=USER_UID,
        )

        assert backend.batched == []
        assert not [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]
