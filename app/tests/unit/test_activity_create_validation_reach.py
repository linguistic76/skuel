"""
Activity Domain creation: the rules must be reachable from every door
======================================================================

Sibling of ``test_choice_create_path_parity.py`` (#960), which settled Choices.
This suite covers the five Activity Domains that PR deferred.

THE STRUCTURAL DEFECT (all five)
--------------------------------
``CrudOperationsMixin.create()`` is the ONLY caller of ``_validate_create``. The
domains declare their creation rules on the CORE sub-service
(``GoalsCoreService``, ``HabitsCoreService``, ...), but the generated CRUD route
(``CRUDRouteFactory._register_create_route``) calls ``service.create(entity)`` on
the FACADE, and a facade holds its core as the delegated ATTRIBUTE ``self.core``
— it does not inherit from it. The override was therefore never in the facade's
MRO, and ``create()`` resolved ``_validate_create`` to the mixin's no-op.

Consequence, before this change: ``POST /api/{goals,habits,events}/create``
persisted entities without running a single domain rule, and published neither
the domain's ``*Created`` event nor the ADR-074 embedding request.

The second door (``create_goal`` / ``create_habit``) missed the rules a different
way — it bypassed ``create()`` altogether via ``_create_and_convert``, which goes
straight to ``backend.create``.

THE SETTLED SEMANTICS (per domain — the rules are NOT uniform)
--------------------------------------------------------------
  Goals   — target_date must not PRECEDE start_date. Equal is legal: the request
            model validates the same pair with ``allow_equal=True`` and defaults
            ``start_date`` to today, so a same-day goal is a shape the API
            deliberately accepts. The hook said ``<=`` and would have started
            refusing it the moment it became reachable.
  Habits  — DAILY habits cannot target > 7 days/week.
  Events  — duration 5..720 minutes. ``EventCreateRequest`` carries no
            ``duration_minutes`` field at all, so no door can set it at creation;
            the rule is live on the UPDATE path and inert here. Pinned so that
            adding the field to the request cannot quietly land unvalidated.
  Tasks   — rule DELETED. "High/Critical priority must have a due date"
            contradicted two live producers (the DSL, GoalTaskGenerator).
  Principles — rules DELETED. statement >= 10 / description >= 20 were stricter
            than ``PrincipleCreateRequest``'s deliberate ``min_length=1``.

WHAT THE SURVIVING HOOKS ACTUALLY BACKSTOP
------------------------------------------
All three guard the ENTITY, and each sits behind a STRICTER request edge:
``GoalCreateRequest`` rejects a past target date and enforces the same ordering,
``HabitCreateRequest`` bounds its field at ``ge=1, le=7``, and
``EventCreateRequest`` has no duration field to set. So none of them fires for an
HTTP caller — Pydantic refuses those bodies with a 422 before the service is
reached. What they backstop is every caller that hands ``create(entity)`` an
entity it assembled itself — in-process callers today; the generated route did
this too, after conversion, until it was bound to the request door
(``request_create_method``).

The tests below therefore drive the entity door. That is a statement about where
the MRO hole cost something, NOT a claim that the API ever accepted bad JSON.

The deletions are pinned too (``TestDeletedRulesStayDeleted``): a test that only
covered the surviving rules would let someone "restore" the deleted ones without
noticing they break the DSL.

No Neo4j: the backend is stubbed, so what is under test is the service wiring —
which is exactly where the defect lived.
"""

from datetime import date, timedelta
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.calendar_event_events import CalendarEventCreated
from core.events.goal_events import GoalCreated
from core.events.habit_events import HabitCreated
from core.models.enums import Domain, MeasurementType, Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.services.events_service import EventsService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals_service import GoalsService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits_service import HabitsService
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.utils.result_simplified import Result

USER_UID = "user:reach"
TODAY = date.today()


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Records what create() was handed and round-trips it like the real backend.

    Mirrors ``UniversalNeo4jBackend._create_node``: whatever it receives (entity or
    property dict) is serialized with ``to_neo4j_node`` and the round-tripped DOMAIN
    ENTITY is returned via ``from_neo4j_node``. Returning the input unchanged would
    let a field-dropping bug read as a pass.
    """

    def __init__(self, model: type) -> None:
        self._model = model
        self.created: list[dict[str, Any]] = []
        self.hierarchy: list[tuple[str, str, dict[str, Any] | None]] = []

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        return Result.ok(from_neo4j_node(props, self._model))

    async def create_relationships_batch(self, relationships: Any) -> Result[bool]:
        return Result.ok(True)

    async def get(self, uid: str) -> Result[Any]:
        """Resolve any UID to an entity owned by ``USER_UID``.

        Goals read the parent through this before writing the hierarchy edge, to
        refuse a cross-user link. Same-user keeps this suite on the linking path;
        the refusal itself is asserted in ``test_goal_habit_create_edges.py``.
        """
        return Result.ok(self._model(uid=uid, user_uid=USER_UID, title="Existing"))

    async def create_hierarchy_relationship(
        self, parent_uid: str, child_uid: str, forward_props: dict[str, Any] | None = None
    ) -> Result[bool]:
        """Goals now write the HAS_SUBGOAL edge as part of creation.

        Added when that write landed: the ``__getattr__`` guard below correctly
        refused the new call, since a create path reaching an unmodelled backend
        method is exactly what this stub exists to catch. What the EDGE must
        contain is asserted in ``test_goal_habit_create_edges.py``; this suite
        only needs the call to succeed so the rules under test stay in view.
        """
        self.hierarchy.append((parent_uid, child_uid, forward_props))
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


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


# ============================================================================
# GOALS
# ============================================================================


def make_goal_request(**overrides: Any) -> GoalCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Ship the ingestion rewrite",
        "description": "Land the new pipeline end to end",
        "why_important": "Unblocks the whole curriculum backlog",
        "success_criteria": "all vault files ingest with no manual fixups",
        "potential_obstacles": ["Neo4j migration window"],
        "strategies": ["ship behind a flag"],
        "unit_of_measurement": "files",
        # NUMERIC, not the PERCENTAGE default — the request model bounds a percentage
        # target at 0..100 and would refuse this fixture.
        "measurement_type": MeasurementType.NUMERIC,
        "target_value": 500.0,
        "tags": ["infra", "q3"],
        "priority": Priority.HIGH,
        "domain": Domain.TECH,
        "start_date": TODAY,
        "target_date": TODAY + timedelta(days=30),
    }
    defaults.update(overrides)
    return GoalCreateRequest(**defaults)


def make_goal(**overrides: Any) -> Goal:
    """A Goal entity shaped like the one the route's converter produces."""
    defaults: dict[str, Any] = {
        "uid": "goal:door-a",
        "user_uid": USER_UID,
        "title": "Ship the ingestion rewrite",
        "start_date": TODAY,
        "target_date": TODAY + timedelta(days=30),
    }
    defaults.update(overrides)
    return Goal(**defaults)


@pytest.fixture
def goals_backend() -> StubBackend:
    return StubBackend(Goal)


@pytest.fixture
def goals_core(goals_backend: StubBackend, event_bus: InMemoryEventBus) -> GoalsCoreService:
    return GoalsCoreService(backend=goals_backend, event_bus=event_bus)


@pytest.fixture
def goals_facade(goals_backend: StubBackend, event_bus: InMemoryEventBus) -> GoalsService:
    """The ENTITY door (``.create(entity)``).

    ``services.goals`` is bound to the GoalsService FACADE in
    services_bootstrap/_activity_services.py, so the facade — not the core
    sub-service — is what the generated route reached until it was bound to the
    request door (``request_create_method``); the entity door remains live for
    in-process callers.
    """
    return GoalsService(
        backend=goals_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


@pytest.mark.asyncio
class TestGoalsEntityDoorValidates:
    """DOOR A — the generated CRUD route, reached via the facade."""

    async def test_inverted_timeline_is_refused(self, goals_facade: GoalsService) -> None:
        """RED before the fix: the facade resolved _validate_create to the no-op."""
        result = await goals_facade.create(
            make_goal(start_date=TODAY, target_date=TODAY - timedelta(days=1))
        )

        assert result.is_error, (
            "the route door persisted a goal whose target date precedes its start "
            "date — GoalsCoreService._validate_create was not in the facade's MRO"
        )
        assert result.expect_error().details["field"] == "target_date"

    async def test_valid_timeline_is_accepted(self, goals_facade: GoalsService) -> None:
        """Positive control: the guard refuses the bad shape, not every shape."""
        result = await goals_facade.create(make_goal())
        assert result.is_ok, f"route door refused a valid goal: {result.error}"

    async def test_same_day_goal_is_accepted(self, goals_facade: GoalsService) -> None:
        """The settled bound: equal dates are legal (request model allow_equal=True)."""
        result = await goals_facade.create(make_goal(start_date=TODAY, target_date=TODAY))
        assert result.is_ok, (
            "a same-day goal was refused — the service rule is stricter than "
            f"GoalCreateRequest's allow_equal=True: {result.error}"
        )


class TestGoalsRuleAgreesWithItsRequestEdge:
    """The hook's BOUND, tested directly rather than through a door.

    ``test_same_day_goal_is_accepted`` above cannot prove this: before the fix it
    passed because no validation ran at all, and after the fix it passes because
    the rule permits equal dates. Same verdict, different reason — so it does not
    discriminate the ``<=`` -> ``<`` change. Calling the hook directly does.
    """

    def test_equal_dates_pass_the_hook(self, goals_core: GoalsCoreService) -> None:
        """RED before the fix: the hook said ``<=`` and refused a same-day goal.

        Reachability and correctness are separate defects. Wiring the hook up
        without this change would have made the service start refusing a shape
        ``GoalCreateRequest`` explicitly accepts (``allow_equal=True``).
        """
        verdict = goals_core._validate_create(make_goal(start_date=TODAY, target_date=TODAY))

        assert verdict.is_ok, (
            "the creation hook refuses equal start/target dates while the request "
            "model accepts them — the two layers disagree on the same rule"
        )

    def test_inverted_dates_still_fail_the_hook(self, goals_core: GoalsCoreService) -> None:
        """Positive control: relaxing the bound must not disarm the rule."""
        verdict = goals_core._validate_create(
            make_goal(start_date=TODAY, target_date=TODAY - timedelta(days=1))
        )

        assert verdict.is_error, "the hook stopped catching an inverted timeline"

    async def test_entity_door_publishes_goal_created(
        self, goals_facade: GoalsService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: the route door published nothing at all."""
        result = await goals_facade.create(make_goal())

        assert result.is_ok
        published = [e for e in event_bus.get_event_history() if isinstance(e, GoalCreated)]
        assert len(published) == 1, (
            "route-created goals published no GoalCreated event, so user-context "
            "caches never invalidated for them"
        )


@pytest.mark.asyncio
class TestGoalsFacadeDoorValidates:
    """DOOR B — ``create_goal``, which bypassed create() via _create_and_convert.

    No inverted-timeline case here: ``GoalCreateRequest`` cannot express one (it
    refuses a past target date and enforces the ordering itself), so the only
    honest assertion about this door is that it now routes THROUGH the primitive.
    That is pinned by the agreement test below — if ``create_goal`` went back to
    building its own DTO, the two doors would diverge again.
    """

    async def test_valid_request_is_accepted(self, goals_core: GoalsCoreService) -> None:
        result = await goals_core.create_goal(make_goal_request(), USER_UID)
        assert result.is_ok, f"create_goal refused a valid request: {result.error}"

    async def test_both_doors_persist_the_same_goal(
        self,
        goals_core: GoalsCoreService,
        goals_facade: GoalsService,
        goals_backend: StubBackend,
    ) -> None:
        """The two doors must agree, field for field, on one request.

        RED before the fix: the hand-listed DTO carried 13 fields while the route's
        converter carried the rest, so the same request produced two different goals.
        """
        from core.services.conversion_service import ConversionServiceV2

        request = make_goal_request()

        await goals_core.create_goal(request, USER_UID)
        await goals_facade.create(
            ConversionServiceV2.goal_create_to_pure(
                request, "goal:door-a", user_uid=USER_UID, status=EntityStatus.ACTIVE
            )
        )

        door_b, door_a = goals_backend.created
        # uid is per-door by construction; everything else must match.
        ignored = {"uid", "created_at", "updated_at"}
        differing = {
            k
            for k in set(door_a) | set(door_b)
            if k not in ignored and door_a.get(k) != door_b.get(k)
        }
        assert not differing, (
            f"the two create doors persisted different goals from one request: {differing}"
        )


@pytest.mark.asyncio
class TestGoalsDoorBCarriesRequestFields:
    """``create_goal`` hand-listed 13 fields and dropped the rest in silence."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("why_important", "Unblocks the whole curriculum backlog"),
            ("success_criteria", "all vault files ingest with no manual fixups"),
            ("potential_obstacles", ("Neo4j migration window",)),
            ("strategies", ("ship behind a flag",)),
            ("unit_of_measurement", "files"),
            ("tags", ("infra", "q3")),
        ],
    )
    async def test_field_is_carried(
        self, goals_core: GoalsCoreService, field: str, expected: Any
    ) -> None:
        """RED before the fix: each of these was absent from the hand-built GoalDTO."""
        result = await goals_core.create_goal(make_goal_request(), USER_UID)

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert getattr(result.value, field) == expected, (
            f"create_goal dropped '{field}' — the hand-listed DTO did not name it, "
            "so the two doors persisted different goals from the same request"
        )

    async def test_parent_goal_uid_survives_the_rename(self, goals_core: GoalsCoreService) -> None:
        """``parent_goal_uid`` (request) is ``fulfills_goal_uid`` (model).

        RED for the ROUTE door before the fix: ``create_to_pure`` filters by exact
        field name, so the generic converter dropped the parent link entirely.
        """
        result = await goals_core.create_goal(
            make_goal_request(parent_goal_uid="goal:parent"), USER_UID
        )

        assert result.is_ok
        assert result.value.fulfills_goal_uid == "goal:parent", (
            "the request's parent_goal_uid did not reach Goal.fulfills_goal_uid"
        )

    async def test_status_is_active(self, goals_core: GoalsCoreService) -> None:
        """The door's own contribution — the request carries no status field."""
        result = await goals_core.create_goal(make_goal_request(), USER_UID)
        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE


# ============================================================================
# HABITS
# ============================================================================


def make_habit_request(**overrides: Any) -> HabitCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Morning review",
        "description": "Review the day's plan before starting",
        "recurrence_pattern": RecurrencePattern.DAILY,
        "target_days_per_week": 7,
        "priority": Priority.HIGH,
        "tags": ["morning", "review"],
        "cue": "After coffee",
    }
    defaults.update(overrides)
    return HabitCreateRequest(**defaults)


@pytest.fixture
def habits_backend() -> StubBackend:
    return StubBackend(Habit)


@pytest.fixture
def habits_core(habits_backend: StubBackend, event_bus: InMemoryEventBus) -> HabitsCoreService:
    return HabitsCoreService(backend=habits_backend, event_bus=event_bus)


@pytest.fixture
def habits_facade(habits_backend: StubBackend, event_bus: InMemoryEventBus) -> HabitsService:
    return HabitsService(
        backend=habits_backend,
        graph_intel=_Inert(),
        completions_backend=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


@pytest.mark.asyncio
class TestHabitsEntityDoorValidates:
    """DOOR A — the route hand-builds the entity, so the edge's le=7 does not apply."""

    async def test_impossible_daily_target_is_refused(self, habits_facade: HabitsService) -> None:
        """RED before the fix: the facade resolved _validate_create to the no-op.

        ``HabitCreateRequest`` bounds this field at ``le=7``, but the route door
        converts to an ENTITY and the hook guards the entity — which is the only
        reason this rule has anything to catch.
        """
        result = await habits_facade.create(
            Habit(
                uid="habit:door-a",
                user_uid=USER_UID,
                title="Morning review",
                recurrence_pattern=RecurrencePattern.DAILY,
                target_days_per_week=9,
            )
        )

        assert result.is_error, (
            "the route door persisted a DAILY habit targeting 9 days/week — "
            "HabitsCoreService._validate_create was not in the facade's MRO"
        )
        assert result.expect_error().details["field"] == "target_days_per_week"

    async def test_valid_habit_is_accepted(self, habits_facade: HabitsService) -> None:
        """Positive control."""
        result = await habits_facade.create(
            Habit(
                uid="habit:door-a",
                user_uid=USER_UID,
                title="Morning review",
                recurrence_pattern=RecurrencePattern.DAILY,
                target_days_per_week=7,
            )
        )
        assert result.is_ok, f"route door refused a valid habit: {result.error}"

    async def test_entity_door_publishes_habit_created(
        self, habits_facade: HabitsService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: the route door published nothing at all."""
        result = await habits_facade.create(
            Habit(uid="habit:door-a", user_uid=USER_UID, title="Morning review")
        )

        assert result.is_ok
        published = [e for e in event_bus.get_event_history() if isinstance(e, HabitCreated)]
        assert len(published) == 1, "route-created habits published no HabitCreated event"


@pytest.mark.asyncio
class TestHabitsDoorBCarriesRequestFields:
    """``create_habit`` hand-listed its fields and dropped priority + tags."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("priority", Priority.HIGH),
            ("tags", ("morning", "review")),
        ],
    )
    async def test_field_is_carried(
        self, habits_core: HabitsCoreService, field: str, expected: Any
    ) -> None:
        """RED before the fix: neither field was named in the hand-built HabitDTO."""
        result = await habits_core.create_habit(make_habit_request(), USER_UID)

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert getattr(result.value, field) == expected, (
            f"create_habit dropped '{field}' — the two doors persisted different "
            "habits from the same request"
        )

    async def test_status_is_active(self, habits_core: HabitsCoreService) -> None:
        result = await habits_core.create_habit(make_habit_request(), USER_UID)
        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE


# ============================================================================
# EVENTS
# ============================================================================


@pytest.fixture
def events_backend() -> StubBackend:
    return StubBackend(Event)


@pytest.fixture
def events_facade(events_backend: StubBackend, event_bus: InMemoryEventBus) -> EventsService:
    return EventsService(
        backend=events_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


@pytest.mark.asyncio
class TestEventsEntityDoorValidates:
    """DOOR A — ``create_event`` already routed through core; the route door did not."""

    @pytest.mark.parametrize("duration", [1, 4, 721, 2000])
    async def test_insane_duration_is_refused(
        self, events_facade: EventsService, duration: int
    ) -> None:
        """RED before the fix: the facade resolved _validate_create to the no-op.

        No door can currently SET duration_minutes at creation (EventCreateRequest
        has no such field), so this pins the wiring rather than a live rejection —
        adding the field to the request must not land unvalidated.
        """
        result = await events_facade.create(
            Event(
                uid="event:door-a",
                user_uid=USER_UID,
                title="Planning session",
                event_date=TODAY,
                duration_minutes=duration,
            )
        )

        assert result.is_error, (
            f"the route door persisted a {duration}-minute event — "
            "EventsCoreService._validate_create was not in the facade's MRO"
        )
        assert result.expect_error().details["field"] == "duration_minutes"

    @pytest.mark.parametrize("duration", [5, 60, 720, None])
    async def test_sane_duration_is_accepted(
        self, events_facade: EventsService, duration: int | None
    ) -> None:
        """Positive control, including the None the live doors actually produce."""
        result = await events_facade.create(
            Event(
                uid="event:door-a",
                user_uid=USER_UID,
                title="Planning session",
                event_date=TODAY,
                duration_minutes=duration,
            )
        )
        assert result.is_ok, f"route door refused a {duration}-minute event: {result.error}"

    async def test_entity_door_publishes_calendar_event_created(
        self, events_facade: EventsService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: the route door published nothing at all."""
        result = await events_facade.create(
            Event(
                uid="event:door-a",
                user_uid=USER_UID,
                title="Planning session",
                event_date=TODAY,
            )
        )

        assert result.is_ok
        published = [
            e for e in event_bus.get_event_history() if isinstance(e, CalendarEventCreated)
        ]
        assert len(published) == 1, "route-created events published no CalendarEventCreated event"


# ============================================================================
# THE DELETED RULES
# ============================================================================


class TestDeletedRulesStayDeleted:
    """Tasks and Principles must NOT grow a creation hook back.

    Both rules were unreachable AND contradicted live producers. Restoring either
    would start refusing input the app generates itself, so pin the deletion at the
    class level — the failure mode is someone "fixing" the missing hook.
    """

    def test_tasks_declare_no_create_hook(self) -> None:
        assert "_validate_create" not in vars(TasksCoreService), (
            "TasksCoreService grew a _validate_create back. The deleted rule "
            "('High/Critical priority must have a due date') is contradicted by the "
            "Activity DSL (@priority(1|2) without @when()) and by GoalTaskGenerator, "
            "both of which create undated high-priority tasks on purpose."
        )

    def test_principles_declare_no_create_hook(self) -> None:
        assert "_validate_create" not in vars(PrinciplesCoreService), (
            "PrinciplesCoreService grew a _validate_create back. The deleted rules "
            "(statement >= 10, description >= 20) are stricter than "
            "PrincipleCreateRequest's deliberate min_length=1, and the DSL sets "
            "statement to the whole activity description — short principle lines "
            "would start being refused."
        )

    def test_deleted_rules_leave_the_inherited_no_op(self) -> None:
        """Positive control: the hook still RESOLVES, it just does not gate.

        Guards against the deletion having been done by removing the mixin's
        declaration too, which would break ``create()`` for every domain.
        """
        for service in (TasksCoreService, PrinciplesCoreService):
            assert callable(service._validate_create), (
                f"{service.__name__}._validate_create no longer resolves at all"
            )


@pytest.mark.asyncio
class TestDeletedRulesAdmitTheLiveShapes:
    """The shapes the deleted rules would have refused must still be creatable."""

    async def test_undated_critical_task_is_accepted(self, event_bus: InMemoryEventBus) -> None:
        """The exact shape the DSL emits for '@priority(1)' with no '@when()'."""
        backend = StubBackend(Task)
        core = TasksCoreService(backend=backend, event_bus=event_bus)

        result = await core.create(
            Task(
                uid="task:dsl",
                user_uid=USER_UID,
                title="Call the bank",
                priority=Priority.CRITICAL,
                due_date=None,
            )
        )

        assert result.is_ok, (
            "an undated CRITICAL task was refused — this is ordinary DSL output "
            f"and GoalTaskGenerator emits it too: {result.error}"
        )

    async def test_short_principle_statement_is_accepted(self, event_bus: InMemoryEventBus) -> None:
        """The exact shape the DSL emits for a short '@context(principle)' line."""
        backend = StubBackend(Principle)
        core = PrinciplesCoreService(backend=backend, event_bus=event_bus)

        result = await core.create(
            Principle(
                uid="principle:dsl",
                user_uid=USER_UID,
                title="Be kind",
                statement="Be kind",
            )
        )

        assert result.is_ok, (
            "a short principle statement was refused — PrincipleCreateRequest "
            f"declares min_length=1 and the DSL passes prose straight through: {result.error}"
        )
