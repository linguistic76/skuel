"""
The generated create route goes through the request-door primitive
==================================================================

Terminus of the #960→#971 two-door reconciliation, per the 2026-08-07 ruling.

THE LAST DIVERGENT DOOR
-----------------------
``CRUDRouteFactory._register_create_route`` validates the incoming body against
the domain's FULL ``*CreateRequest`` schema — so it ACCEPTS every link field the
request carries — then converted the request to an entity and called
``service.create(entity)``. Anything the entity cannot carry (the list-typed
link fields on Tasks/Habits/Events/Choices) evaporated at that conversion: the
API returned 201 and silently dropped the links it had just accepted. The
"known limit" pins in the edge suites documented that drop; they did not make
it a contract.

THE SETTLED CONTRACT
--------------------
An Activity Domain's generated create route now calls the same request-door
primitive every other door converged on (``create_task``, ``create_goal``, …),
bound by name via ``CRUDRouteConfig.request_create_method`` and resolved
FAIL-FAST at factory construction — a config naming a method the service does
not have is a wiring error, not a runtime fallback. The entity path
(convert + ``service.create(entity)``) remains the default for CRUD consumers
outside the Activity Domains (groups, exercises, form templates, …), which have
no request-only link fields to lose.

What this buys, concretely: one create path per domain (conversion happens in
exactly one place), the request's link fields become admission-guarded edges
from the HTTP door too, and the domain ``*Created`` + embedding events publish
with the same ordered contract the request door already pins.

No Neo4j: the backend is stubbed; what is under test is the route→service
wiring, which is exactly where every defect in this arc lived.
"""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.responses import JSONResponse

from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory
from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.task_events import TaskCreated
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Result

USER_UID = "user_test"  # what FactoryRequest's session carries
PRINCIPLE_UID = "principle:deep-work"
PREREQ_TASK = "task:read-the-paper"


# ============================================================================
# ROUTE-DRIVING INFRASTRUCTURE (same shape as test_adapter_less_crud_routes)
# ============================================================================


class CapturingRT:
    """Records the handlers a factory registers, keyed by path."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        def register(handler):
            self.handlers[path] = handler
            return handler

        return register


class FactoryRequest:
    """Mock request satisfying auth + CSRF + JSON-body needs of real factory handlers."""

    def __init__(self, body: dict | None = None, csrf: str = "tok-123") -> None:
        self.method = "POST"
        self._body = body or {}
        self.session = {"user_uid": USER_UID}
        self.cookies = {"csrf_token": csrf}
        self.headers = {"X-CSRF-Token": csrf, "content-type": "application/json"}
        self.query_params: dict[str, str] = {}
        self.url = SimpleNamespace(path="/api/tasks/create")
        self.state = SimpleNamespace()

    async def json(self) -> dict:
        return self._body


def extract_response(response: JSONResponse) -> tuple[dict, int]:
    body = json.loads(response.body)
    return body, response.status_code


# ============================================================================
# SEAM: which service method does the registered handler call?
# ============================================================================


class RecordingService:
    """Exposes BOTH doors and records which one the route walked through."""

    def __init__(self) -> None:
        self.entity_door: list[Any] = []
        self.request_door: list[tuple[Any, str]] = []

    async def create(self, entity: Any) -> Result[Any]:
        self.entity_door.append(entity)
        return Result.ok(entity)

    async def create_task(self, request: TaskCreateRequest, user_uid: str) -> Result[Task]:
        self.request_door.append((request, user_uid))
        return Result.ok(Task(uid="task:via-primitive", title=request.title, user_uid=user_uid))


def _factory(service: Any, **kwargs: Any) -> CapturingRT:
    rt = CapturingRT()
    CRUDRouteFactory(
        service=service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
        uid_prefix="task",
        **kwargs,
    ).register_routes(None, rt)
    return rt


@pytest.mark.asyncio
class TestCreateRouteBinding:
    async def test_bound_factory_walks_the_request_door(self) -> None:
        """With ``request_create_method`` set, the handler hands the VALIDATED REQUEST
        and the session user to the primitive — it does not convert, does not mint a
        uid, and never touches ``service.create``."""
        service = RecordingService()
        rt = _factory(service, request_create_method="create_task")

        response = await rt.handlers["/api/tasks/create"](
            FactoryRequest(body={"title": "Through the primitive"})
        )
        body, status = extract_response(response)

        assert status == 201
        assert body["uid"] == "task:via-primitive"
        assert service.entity_door == []
        [(request, user_uid)] = service.request_door
        assert isinstance(request, TaskCreateRequest)
        assert request.title == "Through the primitive"
        assert user_uid == USER_UID

    async def test_unbound_factory_keeps_the_entity_path(self) -> None:
        """POSITIVE CONTROL (must pass before AND after): the default factory still
        converts and calls ``service.create(entity)`` — the path every non-activity
        CRUD consumer stays on."""
        service = RecordingService()
        rt = _factory(service)

        response = await rt.handlers["/api/tasks/create"](
            FactoryRequest(body={"title": "Through the entity door"})
        )
        body, status = extract_response(response)

        assert status == 201
        assert service.request_door == []
        [entity] = service.entity_door
        assert isinstance(entity, Task)
        assert body["uid"].startswith("task:")

    async def test_unresolvable_method_name_raises_at_construction(self) -> None:
        """FAIL-FAST WIRING: a config naming a method the service does not expose is
        a bug in the config, and it surfaces when routes are built — not as a 500 on
        the first POST."""
        with pytest.raises(ValueError, match="create_nonexistent"):
            _factory(RecordingService(), request_create_method="create_nonexistent")


# ============================================================================
# BINDINGS: all six Activity Domains name their primitive
# ============================================================================


def _crud(config: Any) -> Any:
    assert config.crud is not None, "activity config lost its CRUD sub-config"
    return config.crud


class TestActivityDomainsAreBound:
    """The six activity configs each bind the create route to their request door.

    Pinned per domain so removing a binding — reopening the silent-drop door —
    cannot land as an incidental edit.
    """

    def test_tasks(self) -> None:
        from adapters.inbound.tasks_routes import TASKS_CONFIG

        assert _crud(TASKS_CONFIG).request_create_method == "create_task"

    def test_goals(self) -> None:
        from adapters.inbound.goals_routes import GOALS_CONFIG

        assert _crud(GOALS_CONFIG).request_create_method == "create_goal"

    def test_habits(self) -> None:
        from adapters.inbound.habits_routes import HABITS_CONFIG

        assert _crud(HABITS_CONFIG).request_create_method == "create_habit"

    def test_events(self) -> None:
        from adapters.inbound.events_routes import EVENTS_CONFIG

        assert _crud(EVENTS_CONFIG).request_create_method == "create_event"

    def test_choices(self) -> None:
        from adapters.inbound.choices_routes import CHOICES_CONFIG

        assert _crud(CHOICES_CONFIG).request_create_method == "create_choice"

    def test_principles(self) -> None:
        from adapters.inbound.principles_routes import PRINCIPLES_CONFIG

        assert _crud(PRINCIPLES_CONFIG).request_create_method == "create_principle"

    def test_every_binding_resolves_on_its_facade(self) -> None:
        """The name each config declares must be a real method on the facade class
        the route will be handed — the same resolution the factory performs against
        the instance, checked here against the class so a rename cannot drift."""
        from adapters.inbound.choices_routes import CHOICES_CONFIG
        from adapters.inbound.events_routes import EVENTS_CONFIG
        from adapters.inbound.goals_routes import GOALS_CONFIG
        from adapters.inbound.habits_routes import HABITS_CONFIG
        from adapters.inbound.principles_routes import PRINCIPLES_CONFIG
        from adapters.inbound.tasks_routes import TASKS_CONFIG
        from core.services.choices_service import ChoicesService
        from core.services.events_service import EventsService
        from core.services.goals_service import GoalsService
        from core.services.habits_service import HabitsService
        from core.services.principles_service import PrinciplesService

        pairs = [
            (TASKS_CONFIG, TasksService),
            (GOALS_CONFIG, GoalsService),
            (HABITS_CONFIG, HabitsService),
            (EVENTS_CONFIG, EventsService),
            (CHOICES_CONFIG, ChoicesService),
            (PRINCIPLES_CONFIG, PrinciplesService),
        ]
        for config, facade_cls in pairs:
            method = getattr(facade_cls, _crud(config).request_create_method, None)
            assert callable(method), (
                f"{facade_cls.__name__} has no '{_crud(config).request_create_method}'"
            )


# ============================================================================
# END TO END: the HTTP door now writes the request's link edges
# ============================================================================


class StubBackend:
    """Round-trips create() like the real backend; records edges; admits by default.

    Same shape as the ``test_task_create_edges`` stub: ``__getattr__`` fails CLOSED
    so any unmodelled backend call is an assertion failure, and admission defaults
    every link target to the SESSION user so the guarded batch writes.
    """

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.batched: list[tuple[str, str, str, dict[str, Any] | None]] = []
        self.trace: list[str] = []

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, Task))

    async def get(self, uid: str) -> Result[Any]:
        return Result.ok(Task(uid=uid, user_uid=USER_UID, title="Existing"))

    async def create_relationships_batch(self, relationships: Any) -> Result[int]:
        edges = list(relationships)
        self.batched.extend(edges)
        self.trace.append("link_edges_written")
        return Result.ok(len(edges))

    async def get_owner_uids_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        return Result.ok({uid: [USER_UID] for uid in uids})

    async def get_node_labels_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        return Result.ok({uid: ["Entity", "Habit", "Ku", "Principle", "Task"] for uid in uids})

    def __getattr__(self, name: str):
        async def _unexpected(*args: Any, **kwargs: Any):
            raise AssertionError(f"backend.{name}() unexpectedly called")

        return _unexpected


class _Inert:
    def __getattr__(self, name: str) -> "_Inert":
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> "_Inert":
        return self


@pytest.mark.asyncio
class TestRouteDoorCarriesLinkFields:
    """The crown proof, over the REAL Tasks facade: link fields that no entity field
    can carry — silently dropped by the route door for as long as it existed — now
    come out of ``POST /api/tasks/create`` as admission-guarded edges, with
    ``TaskCreated`` published after them."""

    async def test_list_link_fields_become_edges_from_the_http_door(self) -> None:
        backend = StubBackend()
        bus = InMemoryEventBus(capture_history=True)
        facade = TasksService(
            backend=backend,
            cross_domain_query=_Inert(),
            graph_intel=_Inert(),
            event_bus=bus,
        )

        def _created(event: TaskCreated) -> None:
            backend.trace.append("task_created_published")

        bus.subscribe(TaskCreated, _created)

        rt = CapturingRT()
        CRUDRouteFactory(
            service=facade,
            domain_name="tasks",
            create_schema=TaskCreateRequest,
            update_schema=TaskUpdateRequest,
            uid_prefix="task",
            request_create_method="create_task",
        ).register_routes(None, rt)

        response = await rt.handlers["/api/tasks/create"](
            FactoryRequest(
                body={
                    "title": "Deep work block",
                    "due_date": (date.today() + timedelta(days=3)).isoformat(),
                    "aligned_principle_uids": [PRINCIPLE_UID],
                    "prerequisite_task_uids": [PREREQ_TASK],
                }
            )
        )
        body, status = extract_response(response)

        assert status == 201
        task_uid = body["uid"]
        written = {(f, t, r) for f, t, r, _ in backend.batched}
        assert (task_uid, PRINCIPLE_UID, RelationshipName.ALIGNED_WITH_PRINCIPLE.value) in written
        assert (task_uid, PREREQ_TASK, RelationshipName.BLOCKED_BY.value) in written
        assert body["user_uid"] == USER_UID
        # The ordered contract the request door pins holds from this door too.
        assert backend.trace.index("link_edges_written") < backend.trace.index(
            "task_created_published"
        )
