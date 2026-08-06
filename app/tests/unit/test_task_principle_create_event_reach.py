"""Task and Principle creation: every door must announce the entity it created
==============================================================================

Third and last instalment of the create-path reconciliation. ``#960``
(``test_choice_create_path_parity.py``) settled Choices; ``#963``
(``test_activity_create_validation_reach.py``) settled Goals, Habits and Events and
DELETED the Tasks and Principles creation rules as contradicting live producers.

Because those two domains had no rule left to reach, #963 left them out entirely —
but the defect had two halves, and only the validation half was moot:

  DOOR A — generated CRUD route (``CRUDRouteFactory._register_create_route``)
      ``POST /api/{tasks,principles}/create`` converts the validated body and calls
      ``service.create(entity)`` on the FACADE. ``TasksService`` / ``PrinciplesService``
      hold their core sub-service as the delegated attribute ``self.core`` and do not
      inherit from it, so ``create`` resolved to ``CrudOperationsMixin.create`` and went
      straight to ``backend.create``. It published NOTHING.

  DOOR B — ``create_task`` / ``create_principle``
      Published the ``*Created`` event and the ADR-074 embedding request, but reached
      the backend by its own route (``_create_and_convert`` / ``backend.create``), so
      the two doors shared no primitive that could be fixed once.

Consequence, before this change: a task or principle created through the API
invalidated no user-context cache (``TaskCreated`` / ``PrincipleCreated`` are
subscribed to ``invalidate_context`` in services_bootstrap/_event_wiring.py) and was
never embedded. The fix is the shape the other four domains now use — a core
``create()`` primitive that persists and publishes, plus a facade ``create()``
override delegating into it.

ORDERING IS THE LOAD-BEARING PART (Tasks)
-----------------------------------------
``create_task`` writes graph edges AFTER persisting: the APPLIES_KNOWLEDGE /
REINFORCES_HABIT / REQUIRES_KNOWLEDGE batch, and then a HAS_SUBTASK edge for
``parent_uid``. ``TaskCreated`` triggers a debounced (100ms) user-context rebuild, and
that rebuild reads BOTH ``(task)-[:HAS_SUBTASK]->(subtask)`` and
``(task)-[:APPLIES_KNOWLEDGE]->()`` back out of the graph
(adapters/persistence/neo4j/user_context_queries.py) — then caches the result for
``UserContext.cache_ttl_seconds`` (300s). Publishing before the edges exist caches an
edgeless task for five minutes, and the later KnowledgeAppliedInTask events reach only
substance handlers, so nothing corrects it.

The pre-fix code published ``TaskCreated`` BEFORE writing the subtask edge. That is the
inversion Codex caught on #960 for Choices, live a second time here. So these tests
assert the SEQUENCE via an ordered trace on the stub backend, not merely that both
things happened — "both happened" passes against the bug.

Principles need no such split: ``create_principle`` writes no edges after persisting.

FIELD-CARRIAGE PARITY (was NOT claimed here; now closed)
--------------------------------------------------------
This suite originally recorded two measured divergences it did not fix, so the silence
would not read as parity. Both are now closed:

  - Tasks: the route converter set ``Task.reinforces_habit_uid`` as a node PROPERTY (the
    model documents it as derived-from-edge) while writing no REINFORCES_HABIT edge, and
    ``parent_uid`` was dropped by the mapper with no HAS_SUBTASK edge either. Both are now
    written as edges by the shared create path — see ``test_task_create_edges.py``, which
    also covers the admission guard those request-supplied UIDs needed.
  - Principles: ``create_principle`` merged ``why_important`` into ``description`` while
    the route converter dropped it. Fixed in ``principle_create_to_pure`` and asserted by
    ``TestPrincipleDoorsPersistTheSameDescription`` at the bottom of this file.

What this file still owns is the EVENT half: which door announces what, and in what order.

No Neo4j: the backend is stubbed, so what is under test is the service wiring — which
is exactly where the defect lived.
"""

from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.embedding_events import EmbeddingRequested
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBulkAppliedInTask,
)
from core.events.principle_events import PrincipleCreated
from core.events.task_events import TaskCreated
from core.models.enums import Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle, split_why_important
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.services.conversion_service import ConversionServiceV2
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles_service import PrinciplesService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Errors, Result

USER_UID = "user:reach"


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Records what create() was handed and round-trips it like the real backend.

    Mirrors ``UniversalNeo4jBackend._create_node``: the entity is serialized with
    ``to_neo4j_node`` and the round-tripped DOMAIN ENTITY is returned via
    ``from_neo4j_node``. Returning the input unchanged would let a field-dropping bug
    read as a pass, and returning raw props would not type-check as the Result[T] the
    BackendOperations protocol promises.

    ``trace`` is the ordered log of side effects. Tests assert on its SEQUENCE: an
    assertion that merely finds both an edge write and an event in the log passes
    against the exact inversion this suite guards.
    """

    def __init__(self, model: type) -> None:
        self._model = model
        self.created: list[dict[str, Any]] = []
        self.relationship_batches: list[Any] = []
        self.trace: list[str] = []

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, self._model))

    async def create_relationships_batch(self, relationships: Any) -> Result[bool]:
        self.relationship_batches.append(list(relationships))
        self.trace.append("knowledge_edges_written")
        return Result.ok(True)

    async def create_hierarchy_relationship(
        self, parent_uid: str, child_uid: str, properties: Any = None
    ) -> Result[bool]:
        self.trace.append("subtask_edge_written")
        return Result.ok(True)

    # ------------------------------------------------------------------
    # Added when the create path started writing its request-supplied UIDs
    # through an admission guard. The ``__getattr__`` guard below correctly
    # refused all three calls — a create path reaching an unmodelled backend
    # method is exactly what this stub exists to catch. They are modelled to
    # SUCCEED and permit everything, because this suite is about which events
    # fire and in what order; what the guard REFUSES is asserted in
    # ``test_task_create_edges.py``.
    # ------------------------------------------------------------------

    async def get(self, uid: str) -> Result[Any]:
        """Resolve the hierarchy parent as an entity owned by the same user."""
        return Result.ok(self._model(uid=uid, user_uid=USER_UID, title="Parent"))

    async def get_owner_uids_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """Every link endpoint belongs to the creating user."""
        return Result.ok({uid: [USER_UID] for uid in uids})

    async def get_node_labels_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """Every link endpoint carries whichever kind its field declares."""
        return Result.ok({uid: ["Entity", "Habit", "Ku"] for uid in uids})

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


def record_created_events(bus: InMemoryEventBus, backend: StubBackend) -> None:
    """Append the *Created events to the backend's trace, interleaved with its writes.

    Subscribing is what makes ordering observable: the two halves (edge writes, event
    publishes) are otherwise recorded in different places and cannot be compared.
    """

    def _task(event: TaskCreated) -> None:
        backend.trace.append("task_created_published")

    def _principle(event: PrincipleCreated) -> None:
        backend.trace.append("principle_created_published")

    bus.subscribe(TaskCreated, _task)
    bus.subscribe(PrincipleCreated, _principle)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest.fixture
def tasks_backend() -> StubBackend:
    return StubBackend(Task)


@pytest.fixture
def tasks_core(tasks_backend: StubBackend, event_bus: InMemoryEventBus) -> TasksCoreService:
    """DOOR B's service — TasksCoreService.create_task."""
    return TasksCoreService(backend=tasks_backend, event_bus=event_bus)


@pytest.fixture
def tasks_facade(tasks_backend: StubBackend, event_bus: InMemoryEventBus) -> TasksService:
    """DOOR A's service — the object CRUDRouteFactory calls ``.create(entity)`` on.

    ``services.tasks`` is bound to the TasksService FACADE in
    services_bootstrap/_activity_services.py, so the facade — not the core sub-service —
    is what the generated route reaches.
    """
    return TasksService(
        backend=tasks_backend,
        cross_domain_query=_Inert(),
        graph_intel=_Inert(),
        event_bus=event_bus,
    )


@pytest.fixture
def principles_backend() -> StubBackend:
    return StubBackend(Principle)


@pytest.fixture
def principles_core(
    principles_backend: StubBackend, event_bus: InMemoryEventBus
) -> PrinciplesCoreService:
    """DOOR B's service — PrinciplesCoreService.create_principle."""
    return PrinciplesCoreService(backend=principles_backend, event_bus=event_bus)


@pytest.fixture
def principles_facade(
    principles_backend: StubBackend, event_bus: InMemoryEventBus
) -> PrinciplesService:
    """DOOR A's service — what CRUDRouteFactory calls ``.create(entity)`` on."""
    return PrinciplesService(
        backend=principles_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_task(**overrides: Any) -> Task:
    """A Task entity shaped like the one DOOR A's converter produces."""
    defaults: dict[str, Any] = {
        "uid": "task:door-a",
        "user_uid": USER_UID,
        "title": "Draft the migration plan",
        "description": "Write the AuraDB migration plan and circulate it",
        "priority": Priority.HIGH,
    }
    defaults.update(overrides)
    return Task(**defaults)


def make_task_request(**overrides: Any) -> TaskCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Draft the migration plan",
        "description": "Write the AuraDB migration plan and circulate it",
        "priority": Priority.HIGH,
    }
    defaults.update(overrides)
    return TaskCreateRequest(**defaults)


def make_principle(**overrides: Any) -> Principle:
    """A Principle entity shaped like the one DOOR A's converter produces."""
    defaults: dict[str, Any] = {
        "uid": "principle:door-a",
        "user_uid": USER_UID,
        "title": "Ship small",
        "statement": "Ship small increments",
        "principle_category": PrincipleCategory.PROFESSIONAL,
        "strength": PrincipleStrength.CORE,
    }
    defaults.update(overrides)
    return Principle(**defaults)


def make_principle_request(**overrides: Any) -> PrincipleCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Ship small",
        "statement": "Ship small increments",
        "description": "Prefer many small reversible changes over one large one",
    }
    defaults.update(overrides)
    return PrincipleCreateRequest(**defaults)


def embedding_requests(bus: InMemoryEventBus, entity_type: EntityType) -> list[Any]:
    """The ADR-074 post-persist embedding requests for one entity type."""
    return [
        e
        for e in bus.get_event_history()
        if isinstance(e, EmbeddingRequested) and e.entity_type == entity_type
    ]


# ============================================================================
# TASKS — DOOR A
# ============================================================================


@pytest.mark.asyncio
class TestTasksRouteDoorAnnounces:
    """``TasksService.create(entity)`` is what CRUDRouteFactory calls."""

    async def test_publishes_task_created(
        self, tasks_facade: TasksService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: DOOR A published no event at all.

        TasksCoreService had no ``create`` override, so the facade's inherited
        ``CrudOperationsMixin.create`` went straight to ``backend.create``.
        """
        result = await tasks_facade.create(make_task())

        assert result.is_ok, f"create failed: {result.error}"
        created = [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]
        assert created, (
            "DOOR A published no TaskCreated — a task created through "
            "POST /api/tasks/create invalidated no user-context cache"
        )
        assert created[0].task_uid == "task:door-a"
        assert created[0].user_uid == USER_UID

    async def test_publishes_the_embedding_request(
        self, tasks_facade: TasksService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: an API-created task was never embedded (ADR-074)."""
        await tasks_facade.create(make_task())

        assert embedding_requests(event_bus, EntityType.TASK), (
            "DOOR A published no embedding request — the background worker never sees the task"
        )

    async def test_returns_the_persisted_task(self, tasks_facade: TasksService) -> None:
        """Positive control: publishing must not swallow or replace the result.

        Without this, every assertion above would also pass against a create that
        published events and returned garbage.
        """
        result = await tasks_facade.create(make_task())

        assert result.is_ok, f"create failed: {result.error}"
        assert isinstance(result.value, Task)
        assert result.value.uid == "task:door-a"
        assert result.value.title == "Draft the migration plan"

    async def test_a_failed_persist_publishes_nothing(
        self, tasks_facade: TasksService, tasks_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """The event announces a task that EXISTS — a failed write must stay silent."""

        async def _fail(entity: Any) -> Result[Any]:
            return Result.fail(Errors.database("create", "backend down"))

        tasks_backend.create = _fail  # type: ignore[method-assign]

        result = await tasks_facade.create(make_task())

        assert result.is_error
        assert not [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)], (
            "TaskCreated fired for a task that was never persisted"
        )
        assert not embedding_requests(event_bus, EntityType.TASK)


# ============================================================================
# TASKS — ORDERING
# ============================================================================


@pytest.mark.asyncio
class TestTaskEdgesPrecedeTheEvent:
    """``TaskCreated`` must not fire until every graph edge is written.

    The event triggers a debounced user-context rebuild that reads HAS_SUBTASK and
    APPLIES_KNOWLEDGE back out of the graph and caches the result for 300s. Announcing
    early caches an edgeless task; nothing later corrects it.
    """

    async def test_knowledge_edges_are_written_before_the_event(
        self, tasks_core: TasksCoreService, tasks_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_created_events(event_bus, tasks_backend)

        result = await tasks_core.create_task(
            make_task_request(applies_knowledge_uids=["ku_a", "ku_b"]), USER_UID
        )

        assert result.is_ok, f"create_task failed: {result.error}"
        assert "task_created_published" in tasks_backend.trace, "TaskCreated was never published"
        assert tasks_backend.trace.index("knowledge_edges_written") < tasks_backend.trace.index(
            "task_created_published"
        ), (
            "TaskCreated fired BEFORE the knowledge edges were written — a context "
            f"rebuild would cache a task with no edges. Order was: {tasks_backend.trace}"
        )

    async def test_subtask_edge_is_written_before_the_event(
        self, tasks_core: TasksCoreService, tasks_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: this edge was written AFTER TaskCreated.

        The knowledge batch already preceded the event; the subtask edge did not. The
        rebuild reads ``(task)-[:HAS_SUBTASK]->(subtask)``, so a subtask created through
        ``create_task`` was invisible to the cached context for the full TTL.
        """
        record_created_events(event_bus, tasks_backend)

        result = await tasks_core.create_task(make_task_request(parent_uid="task:parent"), USER_UID)

        assert result.is_ok, f"create_task failed: {result.error}"
        assert "subtask_edge_written" in tasks_backend.trace, (
            "no HAS_SUBTASK edge was written for a request carrying parent_uid"
        )
        assert tasks_backend.trace.index("subtask_edge_written") < tasks_backend.trace.index(
            "task_created_published"
        ), (
            "TaskCreated fired BEFORE the subtask edge was written. Order was: "
            f"{tasks_backend.trace}"
        )

    async def test_every_edge_precedes_the_event(
        self, tasks_core: TasksCoreService, tasks_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """Both edge kinds at once — the shape the API actually sends."""
        record_created_events(event_bus, tasks_backend)

        result = await tasks_core.create_task(
            make_task_request(
                applies_knowledge_uids=["ku_a"],
                prerequisite_knowledge_uids=["ku_b"],
                reinforces_habit_uid="habit:deep-work",
                parent_uid="task:parent",
            ),
            USER_UID,
        )

        assert result.is_ok, f"create_task failed: {result.error}"
        # The two edge writes are unordered WITH RESPECT TO EACH OTHER — nothing reads
        # either until the event triggers the rebuild, so their relative order is an
        # implementation detail (it flipped when the hierarchy write moved onto the shared
        # create path). What is load-bearing is that BOTH precede the announcement, so the
        # assertion pins the boundary rather than the internal order.
        assert tasks_backend.trace[0] == "node_created"
        assert tasks_backend.trace[-1] == "task_created_published"
        assert set(tasks_backend.trace[1:-1]) == {
            "knowledge_edges_written",
            "subtask_edge_written",
        }, f"unexpected create sequence: {tasks_backend.trace}"

    async def test_the_knowledge_batch_still_carries_every_edge(
        self, tasks_core: TasksCoreService, tasks_backend: StubBackend
    ) -> None:
        """Positive control for the reordering: moving the publish must not drop edges."""
        await tasks_core.create_task(
            make_task_request(
                applies_knowledge_uids=["ku_a"],
                prerequisite_knowledge_uids=["ku_b"],
                reinforces_habit_uid="habit:deep-work",
            ),
            USER_UID,
        )

        assert tasks_backend.relationship_batches, "no relationship batch was written"
        edge_names = {rel[2] for rel in tasks_backend.relationship_batches[0]}
        assert edge_names == {"APPLIES_KNOWLEDGE", "REQUIRES_KNOWLEDGE", "REINFORCES_HABIT"}, (
            f"the batch lost an edge kind: {edge_names}"
        )

    async def test_route_door_still_publishes_without_edges(
        self, tasks_facade: TasksService, event_bus: InMemoryEventBus
    ) -> None:
        """Positive control: deferring the publish must not lose it on the door that
        writes no edges at all."""
        result = await tasks_facade.create(make_task())

        assert result.is_ok, f"create failed: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)], (
            "the route door stopped publishing TaskCreated"
        )

    async def test_knowledge_substance_events_survive_the_reordering(
        self, tasks_core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """The substance events moved with the publish — they must still fire.

        They are wired only to substance handlers and do NOT invalidate the context,
        which is precisely why they cannot stand in for TaskCreated's ordering.
        """
        await tasks_core.create_task(
            make_task_request(applies_knowledge_uids=["ku_a", "ku_b"]), USER_UID
        )

        substance = [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask)
        ]
        assert len(substance) == 1, f"expected 1 knowledge substance event, got {len(substance)}"
        assert isinstance(substance[0], KnowledgeBulkAppliedInTask)


# ============================================================================
# TASKS — DOOR B, AND THE TWO DOORS TOGETHER
# ============================================================================


@pytest.mark.asyncio
class TestTasksRequestDoorStillAnnouncesExactlyOnce:
    """Routing DOOR B through the shared primitive must not double-publish."""

    async def test_publishes_exactly_one_task_created(
        self, tasks_core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Guards the fix's own failure mode: ``create_task`` now persists through
        ``_create_validated``, and a stray second publish would fire from both."""
        await tasks_core.create_task(make_task_request(), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]
        assert len(created) == 1, f"expected 1 TaskCreated, got {len(created)}"

    async def test_publishes_exactly_one_embedding_request(
        self, tasks_core: TasksCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await tasks_core.create_task(make_task_request(), USER_UID)

        assert len(embedding_requests(event_bus, EntityType.TASK)) == 1

    async def test_both_doors_reach_the_same_primitive(
        self,
        tasks_core: TasksCoreService,
        tasks_facade: TasksService,
        event_bus: InMemoryEventBus,
    ) -> None:
        """One event and one embedding request per create, whichever door is used.

        Agreement alone would be satisfied by both doors being equally silent — which
        is the pre-fix state for DOOR A — so the count is asserted, not just equality.
        """
        await tasks_facade.create(make_task())
        await tasks_core.create_task(make_task_request(), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, TaskCreated)]
        assert len(created) == 2, (
            f"expected one TaskCreated per door, got {len(created)}: "
            f"{[e.task_uid for e in created]}"
        )
        assert len(embedding_requests(event_bus, EntityType.TASK)) == 2

    async def test_an_undated_critical_task_still_creates(self, tasks_facade: TasksService) -> None:
        """The shape #963's deleted rule would have refused, through the new primitive.

        ``create`` now runs ``_validate_create``; Tasks resolve it to the inherited
        no-op. If someone restores the deleted hook, this breaks here rather than in
        the DSL and GoalTaskGenerator.
        """
        result = await tasks_facade.create(
            make_task(uid="task:dsl", priority=Priority.CRITICAL, due_date=None)
        )

        assert result.is_ok, (
            "an undated CRITICAL task was refused — this is ordinary DSL output "
            f"and GoalTaskGenerator emits it too: {result.error}"
        )


# ============================================================================
# PRINCIPLES
# ============================================================================


@pytest.mark.asyncio
class TestPrinciplesRouteDoorAnnounces:
    """``PrinciplesService.create(entity)`` is what CRUDRouteFactory calls."""

    async def test_publishes_principle_created(
        self, principles_facade: PrinciplesService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: DOOR A published no event at all."""
        result = await principles_facade.create(make_principle())

        assert result.is_ok, f"create failed: {result.error}"
        created = [e for e in event_bus.get_event_history() if isinstance(e, PrincipleCreated)]
        assert created, (
            "DOOR A published no PrincipleCreated — a principle created through "
            "POST /api/principles/create invalidated no user-context cache"
        )
        assert created[0].principle_uid == "principle:door-a"
        assert created[0].principle_label == "Ship small"
        assert created[0].category == PrincipleCategory.PROFESSIONAL.value
        assert created[0].strength == PrincipleStrength.CORE.value

    async def test_publishes_the_embedding_request(
        self, principles_facade: PrinciplesService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: an API-created principle was never embedded (ADR-074)."""
        await principles_facade.create(make_principle())

        assert embedding_requests(event_bus, EntityType.PRINCIPLE), (
            "DOOR A published no embedding request"
        )

    async def test_entity_without_category_or_strength_still_creates(
        self, principles_facade: PrinciplesService, event_bus: InMemoryEventBus
    ) -> None:
        """Both fields are nullable on the MODEL; PrincipleCreated declares both as
        non-optional ``str``.

        ``PrincipleCreateRequest`` defaults them, so building the payload with a bare
        ``principle.principle_category.value`` never bit while only the request door
        published. This primitive runs for hand-built entities too, where it raises
        AttributeError — the same trap ``Choice.domain`` sprang on #960.
        """
        result = await principles_facade.create(
            make_principle(uid="principle:bare", principle_category=None, strength=None)
        )

        assert result.is_ok, f"a bare principle crashed or was rejected: {result.error}"
        created = [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, PrincipleCreated) and e.principle_uid == "principle:bare"
        ]
        assert created, "no event for a principle without category/strength"
        assert created[0].category == ""
        assert created[0].strength == ""

    async def test_returns_the_persisted_principle(
        self, principles_facade: PrinciplesService
    ) -> None:
        """Positive control: publishing must not swallow or replace the result."""
        result = await principles_facade.create(make_principle())

        assert result.is_ok, f"create failed: {result.error}"
        assert isinstance(result.value, Principle)
        assert result.value.uid == "principle:door-a"
        assert result.value.statement == "Ship small increments"

    async def test_a_failed_persist_publishes_nothing(
        self,
        principles_facade: PrinciplesService,
        principles_backend: StubBackend,
        event_bus: InMemoryEventBus,
    ) -> None:
        async def _fail(entity: Any) -> Result[Any]:
            return Result.fail(Errors.database("create", "backend down"))

        principles_backend.create = _fail  # type: ignore[method-assign]

        result = await principles_facade.create(make_principle())

        assert result.is_error
        assert not [e for e in event_bus.get_event_history() if isinstance(e, PrincipleCreated)], (
            "PrincipleCreated fired for a principle that was never persisted"
        )
        assert not embedding_requests(event_bus, EntityType.PRINCIPLE)


@pytest.mark.asyncio
class TestPrinciplesRequestDoorStillAnnouncesExactlyOnce:
    """``create_principle`` now persists through the shared primitive."""

    async def test_publishes_exactly_one_principle_created(
        self, principles_core: PrinciplesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await principles_core.create_principle(make_principle_request(), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, PrincipleCreated)]
        assert len(created) == 1, f"expected 1 PrincipleCreated, got {len(created)}"

    async def test_publishes_exactly_one_embedding_request(
        self, principles_core: PrinciplesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await principles_core.create_principle(make_principle_request(), USER_UID)

        assert len(embedding_requests(event_bus, EntityType.PRINCIPLE)) == 1

    async def test_the_event_still_describes_the_request(
        self, principles_core: PrinciplesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """The payload now reads the PERSISTED entity, not the request.

        Its fields must still carry what the request asked for — a regression here
        would be silent, since every field is a plain string on the event.
        """
        await principles_core.create_principle(
            make_principle_request(
                title="Ship small",
                principle_category=PrincipleCategory.PROFESSIONAL,
                strength=PrincipleStrength.STRONG,
            ),
            USER_UID,
        )

        created = [e for e in event_bus.get_event_history() if isinstance(e, PrincipleCreated)]
        assert len(created) == 1
        assert created[0].principle_label == "Ship small"
        assert created[0].category == PrincipleCategory.PROFESSIONAL.value
        assert created[0].strength == PrincipleStrength.STRONG.value
        assert created[0].user_uid == USER_UID

    async def test_a_short_statement_still_creates(
        self, principles_facade: PrinciplesService
    ) -> None:
        """The shape #963's deleted rules would have refused, through the new primitive."""
        result = await principles_facade.create(
            make_principle(uid="principle:dsl", title="Be kind", statement="Be kind")
        )

        assert result.is_ok, (
            "a short principle statement was refused — PrincipleCreateRequest declares "
            f"min_length=1 and the DSL passes prose straight through: {result.error}"
        )


# ============================================================================
# THE SHAPE ITSELF
# ============================================================================


class TestBothDomainsUseTheSharedShape:
    """The reconciliation is structural: pin it, so a future edit cannot quietly undo it.

    Each assertion names the class that must declare the method. ``vars()`` rather than
    ``hasattr``: the whole defect was a method resolving to an INHERITED implementation,
    which ``hasattr`` reports as present.
    """

    def test_core_services_declare_the_create_primitive(self) -> None:
        for service in (TasksCoreService, PrinciplesCoreService):
            assert "create" in vars(service), (
                f"{service.__name__} no longer declares create() — its domain method "
                "and the generated CRUD route share no publishing primitive again"
            )

    def test_facades_declare_the_create_override(self) -> None:
        for facade in (TasksService, PrinciplesService):
            assert "create" in vars(facade), (
                f"{facade.__name__} no longer declares create() — the generated route "
                "resolves it to CrudOperationsMixin.create and publishes nothing "
                "(the core is the delegated attribute self.core, not a base class)"
            )

    def test_tasks_split_persist_from_publish(self) -> None:
        """Tasks need the split; the ordering guarantee is built on it."""
        assert "_create_validated" in vars(TasksCoreService)
        assert "_publish_created" in vars(TasksCoreService)

    def test_the_core_is_not_a_base_class_of_the_facade(self) -> None:
        """The premise of the whole defect, asserted rather than assumed.

        If a facade ever DID inherit its core, the override above would be redundant —
        and the next reader would be right to delete it.
        """
        assert TasksCoreService not in TasksService.__mro__
        assert PrinciplesCoreService not in PrinciplesService.__mro__


# ============================================================================
# PRINCIPLES — CARRIAGE PARITY
# ============================================================================


@pytest.mark.asyncio
class TestPrincipleDoorsPersistTheSameDescription:
    """``why_important`` must survive BOTH doors, or one request yields two principles.

    ``Principle`` has no ``why_important`` field. ``create_principle`` folds it into
    ``description`` behind the canonical marker (``merge_why_important``), and
    ``split_why_important`` is what recovers it — it is read back by the detail view and
    is one of the four fields Principles search scores over. The route converter dropped
    it outright, because ``create_to_pure`` filters by EXACT field name, so the motivation
    the create form collected was lost the moment the request arrived through JSON.

    Fixed in the CONVERTER, which is the only place it can live: by the time the shared
    create primitive sees an entity, the description is already built.
    """

    async def test_request_door_merges_it_into_the_description(
        self, principles_core: PrinciplesCoreService
    ) -> None:
        """The behaviour the route door had to match — pinned as the reference."""
        result = await principles_core.create_principle(
            make_principle_request(why_important="It keeps blast radius small"), USER_UID
        )

        assert result.is_ok, f"create_principle failed: {result.error}"
        _prose, why = split_why_important(result.value.description)
        assert why == "It keeps blast radius small"

    def test_route_converter_merges_it_too(self) -> None:
        """RED before the fix: the converter dropped ``why_important`` entirely."""
        entity = ConversionServiceV2.principle_create_to_pure(
            make_principle_request(why_important="It keeps blast radius small"),
            "principle:door-a",
            user_uid=USER_UID,
        )

        _prose, why = split_why_important(entity.description)
        assert why == "It keeps blast radius small", (
            "the generated CRUD route's converter dropped why_important, so the two "
            "principle doors persisted different descriptions from one request"
        )

    async def test_both_doors_agree(self, principles_core: PrinciplesCoreService) -> None:
        """Assert AGREEMENT rather than a hand-copied expected string: what matters is
        that one request cannot produce two different principles."""
        request = make_principle_request(why_important="It keeps blast radius small")

        door_b = await principles_core.create_principle(request, USER_UID)
        door_a = ConversionServiceV2.principle_create_to_pure(
            request, "principle:door-a", user_uid=USER_UID
        )

        assert door_a.description == door_b.value.description

    def test_the_prose_is_preserved_alongside_it(self) -> None:
        """A merge, not a replacement — the description the user wrote must survive."""
        request = make_principle_request(
            description="Prefer many small reversible changes over one large one",
            why_important="It keeps blast radius small",
        )

        entity = ConversionServiceV2.principle_create_to_pure(
            request, "principle:door-a", user_uid=USER_UID
        )

        prose, _why = split_why_important(entity.description)
        assert prose == "Prefer many small reversible changes over one large one"

    def test_a_request_without_it_is_untouched(self) -> None:
        """No marker appended when there is nothing to append — otherwise every
        principle's description grows a trailing separator."""
        entity = ConversionServiceV2.principle_create_to_pure(
            make_principle_request(), "principle:door-a", user_uid=USER_UID
        )

        assert entity.description == "Prefer many small reversible changes over one large one"
