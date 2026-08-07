"""
Goal and Habit creation: the request's link fields must become graph EDGES
==========================================================================

Third in the create-path reconciliation arc, after
``test_choice_create_path_parity.py`` (#960, Choices) and
``test_activity_create_validation_reach.py`` (#963, the other five domains).
Those two settled which RULES run and which request fields reach the NODE. This
one covers the fields that were never node columns at all: they name graph edges,
and nothing at creation time wrote them.

WHAT WAS DROPPED
----------------
Goals
    ``parent_goal_uid`` reached the node as the ``Goal.fulfills_goal_uid``
    PROPERTY (#963 hand-mapped the rename, because ``create_to_pure`` filters by
    exact field name and was dropping it entirely). But every hierarchy READER
    goes to the EDGE, not that property:

      - ``GET /api/goals/children`` / ``/parent`` / ``/hierarchy`` traverse
        HAS_SUBGOAL via ``get_children_raw`` / ``get_parent_raw``
      - the user-context MEGA-QUERY collects ``sub_goals`` from
        ``(goal)-[:HAS_SUBGOAL]->(subgoal)``
      - GOAPS_CONFIG resolves ``parent_goal`` and ``sub_goals`` from SUBGOAL_OF

    So a goal created through the create form's own Hierarchy section — which
    ships an ``EntityPicker`` for ``parent_goal_uid`` and a ``progress_weight``
    box — was a subgoal that no hierarchy read could see.

    ``progress_weight`` was dropped by both doors: it is not a ``Goal`` field. It
    is a property of the HAS_SUBGOAL edge, which ``create_subgoal_relationship``
    writes and ``POST /api/goals/hierarchy/child`` already accepts.

    ``required_knowledge_uids``, ``guiding_principle_uids`` and
    ``supporting_habit_uids`` were dropped by both doors for the same reason, and
    name read relationships GOAPS_CONFIG declares: the MEGA-QUERY collects
    ``required_knowledge`` from ``(goal)-[:REQUIRES_KNOWLEDGE]->()``, and the habit
    tiers (``contributing_habits`` plus the essentiality-filtered buckets) resolve
    from SUPPORTS_GOAL. Their direction is NOT uniform — SUPPORTS_GOAL is declared
    incoming, so the habit is the source and the goal the target.

Habits
    ``linked_knowledge_uids``, ``linked_principle_uids``, ``linked_goal_uids`` and
    ``prerequisite_habit_uids`` were dropped by both doors — none is a ``Habit``
    field and nothing converted them to edges. All four name relationships that
    HABITS_CONFIG declares and that live code READS:
    ``HabitRelationships.fetch`` pulls ``supported_goals`` and ``knowledge``,
    ``PrinciplesAlignmentService`` reads EMBODIES_PRINCIPLE, and the prerequisite
    checker reads ``prerequisite_habits``. ``prerequisite_habit_uids`` is the
    sharpest case: ``HabitsSchedulingService`` VALIDATES it at creation (refusing
    a habit whose prerequisite lacks an established streak) and then discards it.

    They are therefore graph-native edges with readers, not unused fields — so
    One Path Forward says write them, not delete them.

WHY ORDERING IS PART OF THE CONTRACT
------------------------------------
``GoalCreated`` and ``HabitCreated`` are both subscribed to ``invalidate_context``
(services_bootstrap/_event_wiring.py), which rebuilds the user context — and the
rebuild reads these very edges back out of the graph (``sub_goals``,
``habit_linked_goals`` via SUPPORTS_GOAL, ``habit_applied_knowledge`` via
REINFORCES_KNOWLEDGE). Publishing before the edges are written lets the rebuild
observe an entity with no edges and cache that for the full 300s TTL, with no
later event to correct it. Regression guard for the inversion Codex caught on
#960, now asserted for two more domains.

ADMISSION (every link endpoint is request input)
------------------------------------------------
A user-supplied UID becomes an edge only if it passes ``keep_permitted_link_edges``
on three counts — it EXISTS, its OWNER is the creator or nobody, and its KIND is
one the field accepts.

Ownership is expressed against the DATA rather than a list of user-owned types,
and reads all three spellings the graph uses (``user_uid`` on UserOwnedEntity,
``owner_uid`` on Exercise and Group, the ``OWNS`` edge). "Owned by nobody" means
shared content and is ALLOWED — that is what keeps the knowledge lists working,
and a blunt "every endpoint must be mine" rule would break them.

Kind is declared per field and is mandatory: ``supporting_habit_uids`` means
Habits, the knowledge lists mean Ku or PathStep. An optional check is an opt-out,
and an opt-out is what let an arbitrary Entity through twice.

Existence matters because ``create_relationships_batch`` is all-or-nothing and its
failure is logged, not propagated: one stale UID would otherwise discard every
valid link in the same request while the create still reported success.

DOOR ASYMMETRY (deliberate, asserted below)
-------------------------------------------
Goals' hierarchy edge is written on the SHARED path, so both doors write it:
``fulfills_goal_uid`` rides on the entity. The seven LINK lists (three on Goals,
four on Habits) cannot work that way — none is a field of its domain model, so
the converter drops them before the generated CRUD route ever reaches
``create(entity)``. ``create_goal`` / ``create_habit`` are the only doors that
still hold them, pinned by ``TestGoalLinkEdgesAreWritten.test_entity_door_writes_
no_link_edges`` and ``TestHabitEntityDoorCannotCarryLinks`` as a structural limit of
the entity door rather than a silent gap (the generated route now enters through the
request door, which carries them).

No Neo4j: the backend is stubbed, so what is under test is the service wiring —
which is exactly where the defect lived.
"""

from datetime import date, timedelta
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.goal_events import GoalCreated
from core.events.habit_events import HabitCreated
from core.models.enums import Domain, MeasurementType, Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import GOAPS_CONFIG, HABITS_CONFIG
from core.services.goals import goals_core_service as goals_module
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals_service import GoalsService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits_service import HabitsService
from core.utils.result_simplified import Result

USER_UID = "user:edges"
TODAY = date.today()
PARENT_GOAL = "goal:parent"


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Round-trips create() like the real backend and records every side effect.

    Mirrors ``UniversalNeo4jBackend._create_node``: whatever it receives is
    serialized with ``to_neo4j_node`` and the round-tripped DOMAIN ENTITY is
    returned via ``from_neo4j_node``. Returning the input unchanged would let a
    field-dropping bug read as a pass.

    ``trace`` is an ORDERED log of side effects, so the tests can assert
    SEQUENCE rather than mere occurrence — the edges-before-event ordering is
    load-bearing, and a test that only checked "both happened" would pass against
    the inverted order that caused the bug.
    """

    def __init__(self, model: type) -> None:
        self._model = model
        self.created: list[dict[str, Any]] = []
        self.trace: list[str] = []
        # (from_uid, to_uid, rel_type, properties) tuples, as handed to the backend
        self.batched: list[tuple[str, str, str, dict[str, Any] | None]] = []
        # (parent_uid, child_uid, forward_props) as handed to the hierarchy writer
        self.hierarchy: list[tuple[str, str, dict[str, Any] | None]] = []
        # uid -> owning user, for the link-target ownership check. A uid absent from
        # this dict resolves to USER_UID (the same user); mapping one elsewhere stages
        # another user's entity. ``shared`` models content that carries no user_uid at
        # all (Ku, PathStep, LP) — the real query omits those rows via
        # `n.user_uid IS NOT NULL`, so the stub must omit them too rather than report
        # a None owner, which would read as "owned by nobody" and be refused.
        self.owners: dict[str, str] = {}
        self.shared: set[str] = set()
        # uid -> Neo4j labels, for the link-target KIND check. Absent uids default to
        # carrying every label the link lists accept, so tests that are not ABOUT the
        # kind check are unaffected by it. ``missing`` stages a UID that resolves to NO
        # node — the real labels query simply omits those, and the guard reads that
        # absence as "does not exist".
        self.labels: dict[str, list[str]] = {}
        self.missing: set[str] = set()

    async def create(self, entity: Any) -> Result[Any]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, self._model))

    async def get(self, uid: str) -> Result[Any]:
        """Resolve any UID to an entity owned by ``USER_UID``.

        Goals read the parent here to check ownership before writing the hierarchy
        edge. Same-user is the DEFAULT so the edge tests exercise the linking path;
        ``TestGoalHierarchyEdgeChecksOwnership`` overrides this to return a
        different owner, which is the case the guard exists for.
        """
        return Result.ok(self._model(uid=uid, user_uid=USER_UID, title="Existing"))

    async def create_relationships_batch(self, relationships: Any) -> Result[int]:
        self.batched.extend(relationships)
        self.trace.append("edges_written")
        return Result.ok(len(list(relationships)))

    async def get_owner_uids_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """uid -> owning user UIDs, mirroring the real query's contract.

        Create paths check link endpoints through this before batching. Same-user is
        the DEFAULT so the edge tests exercise the writing path; tests populate
        ``owners`` to stage another user's entity and ``shared`` to stage content that
        no ownership property or OWNS edge reaches.
        """
        return Result.ok(
            {uid: [self.owners.get(uid, USER_UID)] for uid in uids if uid not in self.shared}
        )

    async def get_node_labels_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        """uid -> labels. Every UID carries whatever ``labels`` says, defaulting to the
        four kinds the link lists accept, so the KIND check passes unless a test stages
        a specific wrong one."""
        return Result.ok(
            {
                uid: self.labels.get(uid, ["Entity", "Habit", "Goal", "Principle", "Ku"])
                for uid in uids
                if uid not in self.missing
            }
        )

    async def create_hierarchy_relationship(
        self, parent_uid: str, child_uid: str, forward_props: dict[str, Any] | None = None
    ) -> Result[bool]:
        self.hierarchy.append((parent_uid, child_uid, forward_props))
        self.trace.append("edges_written")
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
# GOALS — fixtures
# ============================================================================


@pytest.fixture
def goal_backend() -> StubBackend:
    return StubBackend(Goal)


@pytest.fixture
def goal_core(goal_backend: StubBackend, event_bus: InMemoryEventBus) -> GoalsCoreService:
    """DOOR B — the UI form's door (``goals_service.core.create_goal``)."""
    return GoalsCoreService(backend=goal_backend, event_bus=event_bus)


@pytest.fixture
def goal_facade(goal_backend: StubBackend, event_bus: InMemoryEventBus) -> GoalsService:
    """DOOR A — the ENTITY door (``.create(entity)``); the generated route entered
    here until it was bound to the request door (``request_create_method``)."""
    return GoalsService(
        backend=goal_backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_goal_request(**overrides: Any) -> GoalCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Ship the ingestion rewrite",
        "description": "Land the new pipeline end to end",
        "measurement_type": MeasurementType.NUMERIC,
        "target_value": 500.0,
        "priority": Priority.HIGH,
        "domain": Domain.TECH,
        "start_date": TODAY,
        "target_date": TODAY + timedelta(days=30),
    }
    defaults.update(overrides)
    return GoalCreateRequest(**defaults)


# ============================================================================
# GOALS — the hierarchy edge
# ============================================================================


@pytest.mark.asyncio
class TestGoalHierarchyEdgeIsWritten:
    """``parent_goal_uid`` must produce the edge every hierarchy reader traverses."""

    async def test_request_door_writes_the_edge(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """RED before the fix: the property was set and no edge was ever created."""
        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid=PARENT_GOAL), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert goal_backend.hierarchy, (
            "no HAS_SUBGOAL edge was written — parent_goal_uid set only the "
            "Goal.fulfills_goal_uid property, which no hierarchy reader consults"
        )
        parent_uid, child_uid, _props = goal_backend.hierarchy[0]
        assert parent_uid == PARENT_GOAL
        assert child_uid == result.value.uid

    async def test_entity_door_writes_the_edge_too(
        self, goal_facade: GoalsService, goal_backend: StubBackend
    ) -> None:
        """Both doors, or the parity #963 closed re-opens on the next field.

        ``fulfills_goal_uid`` rides on the ENTITY, so the generated CRUD route can
        write this edge — unlike Habits' link lists, which the converter drops.
        """
        from core.services.conversion_service import ConversionServiceV2

        entity = ConversionServiceV2.goal_create_to_pure(
            make_goal_request(parent_goal_uid=PARENT_GOAL),
            "goal:door-a",
            user_uid=USER_UID,
            status=EntityStatus.ACTIVE,
        )
        result = await goal_facade.create(entity)

        assert result.is_ok, f"DOOR A create failed: {result.error}"
        assert goal_backend.hierarchy, (
            "the generated CRUD route created a subgoal with no HAS_SUBGOAL edge"
        )
        assert goal_backend.hierarchy[0][0] == PARENT_GOAL

    async def test_progress_weight_lands_on_the_edge(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """RED before the fix: progress_weight was dropped by both doors.

        It is not a ``Goal`` field — it is a property of the HAS_SUBGOAL edge,
        which is why asserting on the persisted node would prove nothing.
        """
        await goal_core.create_goal(
            make_goal_request(parent_goal_uid=PARENT_GOAL, progress_weight=0.25), USER_UID
        )

        assert goal_backend.hierarchy, "no hierarchy edge written"
        _parent, _child, props = goal_backend.hierarchy[0]
        assert props == {"progress_weight": 0.25}, (
            f"progress_weight did not reach the edge: {props!r}"
        )

    async def test_a_parentless_goal_writes_no_edge(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Positive control: without this, a create that ALWAYS wrote an edge —
        including a self-edge to an empty parent — would pass every test above."""
        result = await goal_core.create_goal(make_goal_request(), USER_UID)

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert goal_backend.hierarchy == [], (
            f"a goal with no parent still wrote a hierarchy edge: {goal_backend.hierarchy}"
        )

    async def test_entity_door_default_weight_matches_the_request_model(self) -> None:
        """The two doors must agree on the weight for an unset ``progress_weight``.

        The entity door receives a ready ``Goal``, and ``progress_weight`` rides on
        no Goal field — so this door cannot know what a client asked for; it stamps
        ``DEFAULT_PROGRESS_WEIGHT``. Asserted against the request model's own
        default rather than a hand-copied ``1.0``, so drifting either one breaks
        here instead of silently splitting the doors.

        Resolved off the module rather than imported at the top of this file so
        that the suite still COLLECTS against a tree without the constant — a
        collection error would fail every test here for the wrong reason.
        """
        entity_door_default = getattr(goals_module, "DEFAULT_PROGRESS_WEIGHT", None)
        request_default = GoalCreateRequest.model_fields["progress_weight"].default

        assert entity_door_default == request_default, (
            f"the entity door stamps {entity_door_default!r} but GoalCreateRequest "
            f"defaults to {request_default!r} — the two create doors would disagree"
        )

    async def test_edge_failure_does_not_fail_the_create(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """A refused edge (e.g. the cycle guard) must not lose the goal itself.

        ``create_hierarchy_relationship`` fails validation on a cycle. The goal is
        already persisted at that point, so propagating would report failure for a
        goal that exists.
        """

        async def _refuse(*_args: Any, **_kwargs: Any) -> Result[bool]:
            goal_backend.trace.append("edges_refused")
            return Result.fail("would create cycle")

        goal_backend.create_hierarchy_relationship = _refuse  # type: ignore[method-assign]

        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid=PARENT_GOAL), USER_UID
        )

        assert result.is_ok, f"a refused hierarchy edge failed the whole create: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, GoalCreated)], (
            "GoalCreated was swallowed when the edge write failed"
        )


@pytest.mark.asyncio
class TestGoalLinkEdgesAreWritten:
    """``GoalCreateRequest``'s three link lists must become edges too.

    Same defect as the Habit lists, and the same census: each names a registered,
    read relationship. ``required_knowledge`` is collected by the user-context
    MEGA-QUERY off ``(goal)-[:REQUIRES_KNOWLEDGE]->()``, and the GOAPS habit tiers
    resolve from SUPPORTS_GOAL. (Codex, #965.)
    """

    @pytest.mark.parametrize(
        ("field", "relationship", "method_key", "expected_props"),
        [
            (
                "required_knowledge_uids",
                RelationshipName.REQUIRES_KNOWLEDGE,
                "knowledge",
                {"proficiency_required": "intermediate", "priority": 1},
            ),
            (
                "guiding_principle_uids",
                RelationshipName.GUIDED_BY_PRINCIPLE,
                "principles",
                {"alignment_strength": 1.0},
            ),
            (
                "supporting_habit_uids",
                RelationshipName.SUPPORTS_GOAL,
                "supporting_habits",
                {"weight": 1.0, "essentiality": "supporting"},
            ),
        ],
    )
    async def test_list_becomes_edges_in_the_registry_direction(
        self,
        goal_core: GoalsCoreService,
        goal_backend: StubBackend,
        field: str,
        relationship: RelationshipName,
        method_key: str,
        expected_props: dict[str, Any],
    ) -> None:
        """RED before the fix: all three lists were dropped by both doors.

        Direction is read off GOAPS_CONFIG rather than hand-asserted, because it is
        NOT uniform here: SUPPORTS_GOAL is declared incoming, so for that list the
        habit is the edge SOURCE and the goal the target. Writing it like the other
        two would persist an edge every reader misses.
        """
        spec = GOAPS_CONFIG.get_relationship_by_method(method_key)
        assert spec is not None, f"GOAPS_CONFIG has no '{method_key}' relationship"
        assert spec.relationship == relationship

        result = await goal_core.create_goal(
            make_goal_request(**{field: ["target:one", "target:two"]}), USER_UID
        )
        assert result.is_ok, f"create_goal failed: {result.error}"

        written = [t for t in goal_backend.batched if t[2] == relationship.value]
        assert len(written) == 2, (
            f"{field} produced {len(written)} {relationship.value} edges, expected 2 — "
            f"batched: {goal_backend.batched}"
        )
        assert all(t[3] == expected_props for t in written), (
            f"{relationship.value} properties differ from the single-link writer's "
            f"defaults {expected_props!r}: {[t[3] for t in written]}"
        )

        goal_uid = result.value.uid
        if spec.direction == "incoming":
            assert {t[0] for t in written} == {"target:one", "target:two"}
            assert {t[1] for t in written} == {goal_uid}, (
                f"'{method_key}' is declared incoming, so the goal must be the edge "
                "TARGET — writing it as the source orphans the edge"
            )
        else:
            assert {t[0] for t in written} == {goal_uid}
            assert {t[1] for t in written} == {"target:one", "target:two"}

    async def test_refuses_cross_user_link_targets(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Including on the INCOMING list, where the supplied UID is the edge source."""
        goal_backend.owners["habit:victims"] = "user:victim"
        goal_backend.owners["principle:victims"] = "user:victim"

        result = await goal_core.create_goal(
            make_goal_request(
                supporting_habit_uids=["habit:victims"],
                guiding_principle_uids=["principle:victims"],
            ),
            USER_UID,
        )

        assert result.is_ok, "the caller's own goal is legitimate and should be created"
        assert goal_backend.batched == [], (
            f"cross-user link edges were written: {goal_backend.batched}"
        )

    async def test_shared_knowledge_is_still_linkable(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Positive control: a Ku is owned by nobody and is a Ku, not a Habit/Goal.

        Both halves of the guard must let it through — ``required_knowledge_uids``
        declares no required label precisely because it reaches Kus and PathSteps.
        """
        goal_backend.shared.add("ku:shared")
        goal_backend.labels["ku:shared"] = ["Entity", "Ku"]

        result = await goal_core.create_goal(
            make_goal_request(required_knowledge_uids=["ku:shared"]), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert [t for t in goal_backend.batched if t[2] == "REQUIRES_KNOWLEDGE"], (
            "a shared Ku was refused as a goal's required knowledge"
        )

    async def test_a_non_knowledge_uid_is_refused(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """``required_knowledge_uids`` accepts Ku and PathStep — not any Entity.

        The knowledge lists take a SET of kinds rather than opting out of the check,
        because "several kinds are valid" is not "anything is". A same-user Task here
        would be reported as required knowledge by goal context and planning.
        (Codex, #965.)
        """
        goal_backend.labels["task:not-knowledge"] = ["Entity", "Task"]

        result = await goal_core.create_goal(
            make_goal_request(required_knowledge_uids=["task:not-knowledge"]), USER_UID
        )

        assert result.is_ok, "the caller's own goal is legitimate and should be created"
        assert [t for t in goal_backend.batched if t[2] == "REQUIRES_KNOWLEDGE"] == [], (
            "a non-knowledge UID was written as required knowledge"
        )

    async def test_a_ku_is_accepted_as_knowledge(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Positive control: the atom is what a knowledge list is for."""
        goal_backend.labels["ku:one"] = ["Entity", "Ku"]
        goal_backend.shared.add("ku:one")

        result = await goal_core.create_goal(
            make_goal_request(required_knowledge_uids=["ku:one"]), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert [t for t in goal_backend.batched if t[2] == "REQUIRES_KNOWLEDGE"], (
            "a Ku was refused as required knowledge"
        )

    async def test_a_pathstep_is_not_accepted_as_knowledge(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """The create doors write the ATOM, not the composition.

        A PathStep target reads back fine — the rich-context query expands it through
        ``TRAINS_KU|USES_KU`` — but the substance pipeline has no inverse:
        ``increment_substance`` credits the node it is given and fans OUT to composing
        PathSteps, so a PathStep would be credited while every atom it teaches stayed
        untouched, contradicting what the reader reports. Narrowing the WRITE keeps the
        two halves agreeing; edges written by other paths still resolve. (Codex, #965.)
        """
        goal_backend.labels["ps:composed"] = ["Entity", "PathStep"]
        goal_backend.shared.add("ps:composed")

        result = await goal_core.create_goal(
            make_goal_request(required_knowledge_uids=["ps:composed"]), USER_UID
        )

        assert result.is_ok, "the caller's own goal is legitimate and should be created"
        assert [t for t in goal_backend.batched if t[2] == "REQUIRES_KNOWLEDGE"] == [], (
            "a PathStep was written as required knowledge — the substance pipeline "
            "cannot resolve it to the atoms the reader would report"
        )

    async def test_a_dangling_uid_does_not_lose_the_valid_links(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """A UID that resolves to no node must be dropped, not batched.

        ``create_relationships_batch`` validates ALL before creating ANY, and its
        failure here is logged rather than propagated — so one stale UID would take
        every valid link in the same request down with it while the create still
        reported success. (Codex, #965.)
        """
        goal_backend.missing.add("ku:deleted")
        goal_backend.labels["ku:real"] = ["Entity", "Ku"]
        goal_backend.shared.add("ku:real")

        result = await goal_core.create_goal(
            make_goal_request(required_knowledge_uids=["ku:deleted", "ku:real"]), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        targets = {t[1] for t in goal_backend.batched if t[2] == "REQUIRES_KNOWLEDGE"}
        assert targets == {"ku:real"}, (
            f"expected only the live UID to be batched, got {targets} — a dangling UID "
            "in the batch fails it wholesale and silently loses the valid links"
        )

    async def test_a_non_habit_supporting_uid_is_refused(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """``supporting_habit_uids`` must hold Habits, even same-user ones.

        The registry cannot enforce this: the supplied UID becomes the edge's SOURCE,
        and the batch validator keys its target rule off the source's own config — so a
        same-user Goal there validates, and then reports as a habit under
        ``supporting_habits``, corrupting planning and progress context. (Codex, #965.)
        """
        goal_backend.labels["goal:not-a-habit"] = ["Entity", "Goal"]

        result = await goal_core.create_goal(
            make_goal_request(supporting_habit_uids=["goal:not-a-habit"]), USER_UID
        )

        assert result.is_ok, "the caller's own goal is legitimate and should be created"
        assert [t for t in goal_backend.batched if t[2] == "SUPPORTS_GOAL"] == [], (
            "a non-Habit UID was written under supporting_habit_uids"
        )

    async def test_a_real_habit_still_supports_the_goal(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Positive control for the kind check on the INCOMING list."""
        goal_backend.labels["habit:mine"] = ["Entity", "Habit"]

        result = await goal_core.create_goal(
            make_goal_request(supporting_habit_uids=["habit:mine"]), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        written = [t for t in goal_backend.batched if t[2] == "SUPPORTS_GOAL"]
        assert written, "a genuine Habit was refused as a supporting habit"
        assert written[0][0] == "habit:mine", "the habit must be the edge SOURCE"

    async def test_link_edges_precede_the_event(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """Same ordering contract as the hierarchy edge — the context rebuild reads
        ``required_knowledge`` straight back out of the graph."""

        def _record(_event: GoalCreated) -> None:
            goal_backend.trace.append("goal_created_published")

        event_bus.subscribe(GoalCreated, _record)

        await goal_core.create_goal(make_goal_request(required_knowledge_uids=["ku:a"]), USER_UID)

        assert goal_backend.trace.index("edges_written") < goal_backend.trace.index(
            "goal_created_published"
        ), f"GoalCreated fired before the link edges. Order was: {goal_backend.trace}"

    async def test_entity_door_writes_no_link_edges(
        self, goal_facade: GoalsService, goal_backend: StubBackend
    ) -> None:
        """The entity door has no request to read them from — documented, not silent.

        Unlike the hierarchy edge (whose parent rides on the entity), these three are
        edge-typed and reach no ``Goal`` field, so the converter drops them first.
        """
        from core.services.conversion_service import ConversionServiceV2

        entity = ConversionServiceV2.goal_create_to_pure(
            make_goal_request(required_knowledge_uids=["ku:a"]),
            "goal:door-a",
            user_uid=USER_UID,
            status=EntityStatus.ACTIVE,
        )
        result = await goal_facade.create(entity)

        assert result.is_ok, f"DOOR A create failed: {result.error}"
        assert goal_backend.batched == [], (
            "the entity door wrote link edges — if the converter now carries the lists, "
            "this suite's asymmetry note is stale"
        )


@pytest.mark.asyncio
class TestGoalHierarchyEdgeChecksOwnership:
    """``parent_goal_uid`` is attacker-controlled input; the edge must not cross users.

    The hierarchy backend matches on UID and label alone, and the victim's context
    rebuild starts from the goals they OWN and traverses HAS_SUBGOAL without filtering
    the child's owner — so a cross-user edge injects the attacker's goal into the
    victim's cached context. The one pre-existing door onto this write,
    ``POST /api/goals/add-child``, already verifies BOTH endpoints; creation must not
    be a way around it. (Codex, #965.)
    """

    async def test_refuses_a_parent_owned_by_another_user(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        async def _other_users_goal(uid: str) -> Result[Goal]:
            return Result.ok(Goal(uid=uid, user_uid="user:victim", title="Victim's goal"))

        goal_backend.get = _other_users_goal  # type: ignore[method-assign]

        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid="goal:victims"), USER_UID
        )

        assert result.is_ok, "the attacker's own goal is legitimate and should be created"
        assert goal_backend.hierarchy == [], (
            "a cross-user HAS_SUBGOAL edge was written — the attacker's goal would "
            "surface in the victim's user context"
        )

    async def test_still_links_when_the_parent_is_the_same_user(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """Positive control: the guard must not refuse the legitimate case.

        Without this, an ownership check that refused EVERY parent would pass the
        test above.
        """

        async def _own_goal(uid: str) -> Result[Goal]:
            return Result.ok(Goal(uid=uid, user_uid=USER_UID, title="My other goal"))

        goal_backend.get = _own_goal  # type: ignore[method-assign]

        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid=PARENT_GOAL), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert goal_backend.hierarchy, "the owner's own parent was refused"
        assert goal_backend.hierarchy[0][0] == PARENT_GOAL

    async def test_missing_parent_writes_no_edge_and_still_creates(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend
    ) -> None:
        """A dangling parent UID is refused as an edge, not as a create."""

        async def _not_found(uid: str) -> Result[Goal]:
            return Result.fail("not found")

        goal_backend.get = _not_found  # type: ignore[method-assign]

        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid="goal:ghost"), USER_UID
        )

        assert result.is_ok, f"a dangling parent failed the whole create: {result.error}"
        assert goal_backend.hierarchy == []


@pytest.mark.asyncio
class TestGoalEdgePrecedesTheEvent:
    """``GoalCreated`` must not fire until the hierarchy edge is written.

    ``GoalCreated`` is subscribed to ``invalidate_context``, and the rebuild
    collects ``sub_goals`` by traversing ``(goal)-[:HAS_SUBGOAL]->(subgoal)``.
    Announcing first lets the rebuild cache a parent missing this subgoal for the
    full 300s TTL. Same inversion Codex caught on #960 for Choices.
    """

    async def test_edge_is_written_before_goal_created(
        self, goal_core: GoalsCoreService, goal_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        def _record(_event: GoalCreated) -> None:
            goal_backend.trace.append("goal_created_published")

        event_bus.subscribe(GoalCreated, _record)

        result = await goal_core.create_goal(
            make_goal_request(parent_goal_uid=PARENT_GOAL), USER_UID
        )

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert "goal_created_published" in goal_backend.trace, "GoalCreated was never published"
        assert goal_backend.trace.index("edges_written") < goal_backend.trace.index(
            "goal_created_published"
        ), (
            "GoalCreated fired BEFORE the hierarchy edge was written — a context "
            f"rebuild would cache a parent with no subgoal. Order was: {goal_backend.trace}"
        )

    async def test_parentless_goal_still_publishes(
        self, goal_core: GoalsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Positive control: deferring the publish must not lose it on the path
        that writes no edge at all."""
        result = await goal_core.create_goal(make_goal_request(), USER_UID)

        assert result.is_ok, f"create_goal failed: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, GoalCreated)], (
            "a parentless goal stopped publishing GoalCreated"
        )

    async def test_exactly_one_event_per_create(
        self, goal_core: GoalsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Guards the fix's own failure mode: splitting create() into
        _create_validated + _publish_created must not double-publish."""
        await goal_core.create_goal(make_goal_request(parent_goal_uid=PARENT_GOAL), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, GoalCreated)]
        assert len(created) == 1, f"expected 1 GoalCreated, got {len(created)}"


# ============================================================================
# HABITS — fixtures
# ============================================================================


@pytest.fixture
def habit_backend() -> StubBackend:
    return StubBackend(Habit)


@pytest.fixture
def habit_core(habit_backend: StubBackend, event_bus: InMemoryEventBus) -> HabitsCoreService:
    """DOOR B — the UI form's door (``HabitsService.create_habit``)."""
    return HabitsCoreService(backend=habit_backend, event_bus=event_bus)


@pytest.fixture
def habit_facade(habit_backend: StubBackend, event_bus: InMemoryEventBus) -> HabitsService:
    """DOOR A — the ENTITY door (``.create(entity)``); the generated route entered
    here until it was bound to the request door (``request_create_method``)."""
    return HabitsService(
        backend=habit_backend,
        graph_intel=_Inert(),
        completions_backend=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_habit_request(**overrides: Any) -> HabitCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Morning deep work",
        "description": "Ninety minutes before email",
        "recurrence_pattern": RecurrencePattern.DAILY,
        "target_days_per_week": 7,
        "priority": Priority.HIGH,
    }
    defaults.update(overrides)
    return HabitCreateRequest(**defaults)


def edges_of(backend: StubBackend, rel: RelationshipName) -> list[tuple[str, str, str, Any]]:
    return [tuple_ for tuple_ in backend.batched if tuple_[2] == rel.value]


# ============================================================================
# HABITS — the four link edges
# ============================================================================


@pytest.mark.asyncio
class TestHabitLinkEdgesAreWritten:
    """Each of the four link lists must become the edge its readers traverse."""

    @pytest.mark.parametrize(
        ("field", "relationship", "method_key"),
        [
            ("linked_knowledge_uids", RelationshipName.REINFORCES_KNOWLEDGE, "knowledge"),
            ("linked_principle_uids", RelationshipName.EMBODIES_PRINCIPLE, "principles"),
            ("linked_goal_uids", RelationshipName.SUPPORTS_GOAL, "supported_goals"),
            (
                "prerequisite_habit_uids",
                RelationshipName.REQUIRES_PREREQUISITE_HABIT,
                "prerequisite_habits",
            ),
        ],
    )
    async def test_list_becomes_edges(
        self,
        habit_core: HabitsCoreService,
        habit_backend: StubBackend,
        field: str,
        relationship: RelationshipName,
        method_key: str,
    ) -> None:
        """RED before the fix: all four lists were dropped by both doors."""
        result = await habit_core.create_habit(
            make_habit_request(**{field: ["target:one", "target:two"]}), USER_UID
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        written = edges_of(habit_backend, relationship)
        assert len(written) == 2, (
            f"{field} produced {len(written)} {relationship.value} edges, expected 2 — "
            f"batched: {habit_backend.batched}"
        )
        assert {tuple_[1] for tuple_ in written} == {"target:one", "target:two"}
        # Habit is the SOURCE of all four (every spec is declared outgoing).
        assert {tuple_[0] for tuple_ in written} == {result.value.uid}

    @pytest.mark.parametrize(
        ("field", "method_key"),
        [
            ("linked_knowledge_uids", "knowledge"),
            ("linked_principle_uids", "principles"),
            ("linked_goal_uids", "supported_goals"),
            ("prerequisite_habit_uids", "prerequisite_habits"),
        ],
    )
    async def test_edge_agrees_with_the_registry(
        self,
        habit_core: HabitsCoreService,
        habit_backend: StubBackend,
        field: str,
        method_key: str,
    ) -> None:
        """The written edge must match HABITS_CONFIG, not a hand-copied table.

        The create path names its relationships literally. Asserting them against
        a second hand-written list would just duplicate the guess; asserting
        against the registry means a rename or a direction flip on the READ side
        breaks this test instead of silently orphaning the write.
        """
        spec = HABITS_CONFIG.get_relationship_by_method(method_key)
        assert spec is not None, f"HABITS_CONFIG has no '{method_key}' relationship"

        result = await habit_core.create_habit(
            make_habit_request(**{field: ["target:one"]}), USER_UID
        )
        assert result.is_ok, f"create_habit failed: {result.error}"

        written = edges_of(habit_backend, spec.relationship)
        assert written, (
            f"{field} wrote no {spec.relationship.value} edge — the registry reads "
            f"'{method_key}' from that relationship"
        )
        assert spec.direction == "outgoing", (
            f"'{method_key}' is declared {spec.direction}; the create path writes the "
            "habit as the edge SOURCE, so a non-outgoing spec means the write and the "
            "read now point opposite ways"
        )
        assert written[0][0] == result.value.uid

    @pytest.mark.parametrize(
        ("field", "relationship", "expected_props"),
        [
            (
                "linked_knowledge_uids",
                RelationshipName.REINFORCES_KNOWLEDGE,
                {"skill_level": "beginner", "proficiency_gain_rate": 0.1},
            ),
            (
                "linked_principle_uids",
                RelationshipName.EMBODIES_PRINCIPLE,
                {"embodiment_strength": 1.0},
            ),
            (
                "linked_goal_uids",
                RelationshipName.SUPPORTS_GOAL,
                {"weight": 1.0, "essentiality": "supporting"},
            ),
            ("prerequisite_habit_uids", RelationshipName.REQUIRES_PREREQUISITE_HABIT, None),
        ],
    )
    async def test_edge_properties_match_the_single_link_writers(
        self,
        habit_core: HabitsCoreService,
        habit_backend: StubBackend,
        field: str,
        relationship: RelationshipName,
        expected_props: dict[str, Any] | None,
    ) -> None:
        """A habit linked at creation must be indistinguishable from one linked later.

        These are the defaults of ``link_habit_to_knowledge`` /
        ``link_habit_to_principle`` / ``link_goal_to_habit``. ``essentiality`` is
        the load-bearing one: GOAPS_CONFIG resolves the essential / critical /
        optional habit tiers by filtering SUPPORTS_GOAL on that exact property, and
        an unstamped edge reads back only through the unfiltered catch-all.
        """
        await habit_core.create_habit(make_habit_request(**{field: ["target:one"]}), USER_UID)

        written = edges_of(habit_backend, relationship)
        assert written, f"{field} wrote no {relationship.value} edge"
        assert written[0][3] == expected_props, (
            f"{relationship.value} properties {written[0][3]!r} differ from the "
            f"single-link writer's defaults {expected_props!r}"
        )

    async def test_all_four_lists_go_out_in_one_batch(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """One batch, not four round trips — and one all-or-nothing transaction."""
        await habit_core.create_habit(
            make_habit_request(
                linked_knowledge_uids=["ku:a"],
                linked_principle_uids=["principle:a"],
                linked_goal_uids=["goal:a"],
                prerequisite_habit_uids=["habit:a"],
            ),
            USER_UID,
        )

        assert habit_backend.trace.count("edges_written") == 1, (
            f"expected a single batched write, got {habit_backend.trace}"
        )
        assert len(habit_backend.batched) == 4

    async def test_a_linkless_habit_writes_no_edges(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """Positive control: the batch must be skipped, not sent empty."""
        result = await habit_core.create_habit(make_habit_request(), USER_UID)

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert habit_backend.batched == []
        assert "edges_written" not in habit_backend.trace

    async def test_edge_failure_does_not_fail_the_create(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """The habit is already persisted when the batch runs; a failed batch must
        not report failure for a habit that exists."""

        async def _refuse(*_args: Any, **_kwargs: Any) -> Result[int]:
            return Result.fail("batch validation failed")

        habit_backend.create_relationships_batch = _refuse  # type: ignore[method-assign]

        result = await habit_core.create_habit(
            make_habit_request(linked_goal_uids=["goal:a"]), USER_UID
        )

        assert result.is_ok, f"a failed edge batch failed the whole create: {result.error}"


@pytest.mark.asyncio
class TestHabitLinkEdgesCheckOwnership:
    """Every link target is request input; none may cross a user boundary.

    ``create_relationships_batch`` validates LABELS, not ownership. Without this
    guard a caller could link their habit to another user's goal — whose title their
    own context read would then return — or to another user's principle, which the
    victim's alignment reads (incoming EMBODIES_PRINCIPLE) would pick the caller's
    habit up from. Sibling of the HAS_SUBGOAL check on Goals. (Codex, #965.)
    """

    @pytest.mark.parametrize(
        ("field", "relationship"),
        [
            ("linked_goal_uids", RelationshipName.SUPPORTS_GOAL),
            ("linked_principle_uids", RelationshipName.EMBODIES_PRINCIPLE),
            ("prerequisite_habit_uids", RelationshipName.REQUIRES_PREREQUISITE_HABIT),
        ],
    )
    async def test_refuses_a_target_owned_by_another_user(
        self,
        habit_core: HabitsCoreService,
        habit_backend: StubBackend,
        field: str,
        relationship: RelationshipName,
    ) -> None:
        habit_backend.owners["target:victims"] = "user:victim"

        result = await habit_core.create_habit(
            make_habit_request(**{field: ["target:victims"]}), USER_UID
        )

        assert result.is_ok, "the caller's own habit is legitimate and should be created"
        assert edges_of(habit_backend, relationship) == [], (
            f"{field} wrote a cross-user {relationship.value} edge"
        )

    async def test_shared_knowledge_is_still_linkable(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """Kus carry no ``user_uid`` — an owner-absent target must NOT be refused.

        This is the case a "check every target belongs to me" rule gets wrong: Ku is
        shared content, and refusing it would break the single most common link.
        """
        habit_backend.shared.add("ku:shared")

        result = await habit_core.create_habit(
            make_habit_request(linked_knowledge_uids=["ku:shared"]), USER_UID
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert edges_of(habit_backend, RelationshipName.REINFORCES_KNOWLEDGE), (
            "a shared Ku was refused as a link target — user_uid lives on "
            "UserOwnedEntity, so shared content legitimately has no owner"
        )

    async def test_only_the_offending_edge_is_dropped(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """One bad target must not cost the caller their legitimate links."""
        habit_backend.owners["goal:victims"] = "user:victim"

        result = await habit_core.create_habit(
            make_habit_request(
                linked_goal_uids=["goal:victims", "goal:mine"],
                linked_knowledge_uids=["ku:mine"],
            ),
            USER_UID,
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        goal_targets = {t[1] for t in edges_of(habit_backend, RelationshipName.SUPPORTS_GOAL)}
        assert goal_targets == {"goal:mine"}, f"expected only the owned goal, got {goal_targets}"
        assert edges_of(habit_backend, RelationshipName.REINFORCES_KNOWLEDGE), (
            "an unrelated, legitimate knowledge link was dropped too"
        )

    async def test_owner_lookup_failure_writes_nothing(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend
    ) -> None:
        """Fail CLOSED: an unreadable owner map must not fall through to an unchecked write."""

        async def _fail(*_args: Any, **_kwargs: Any) -> Result[dict[str, list[str]]]:
            return Result.fail("owner lookup unavailable")

        habit_backend.get_owner_uids_batch = _fail  # type: ignore[method-assign]

        result = await habit_core.create_habit(
            make_habit_request(linked_goal_uids=["goal:mine"]), USER_UID
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert habit_backend.batched == [], (
            "edges were written unchecked after the ownership lookup failed"
        )


@pytest.mark.asyncio
class TestHabitKnowledgeSubstance:
    """Writing REINFORCES_KNOWLEDGE must also announce the substance it represents.

    ``KnowledgeBuiltIntoHabit`` / its bulk variant are the ONLY path to
    ``PsService.handle_knowledge_built_into_habit``, which increments
    ``times_built_into_habits``. ``create_task`` and ``create_choice`` publish their
    equivalents; until ``create_habit`` started writing these edges the omission was
    free, because there were no edges for the metric to disagree with. (Codex, #965.)
    """

    async def test_single_knowledge_link_publishes_the_single_event(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        from core.events.knowledge_substance_events import KnowledgeBuiltIntoHabit

        result = await habit_core.create_habit(
            make_habit_request(linked_knowledge_uids=["ku:a"]), USER_UID
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        published = [
            e for e in event_bus.get_event_history() if isinstance(e, KnowledgeBuiltIntoHabit)
        ]
        assert len(published) == 1, f"expected 1 KnowledgeBuiltIntoHabit, got {len(published)}"
        assert published[0].knowledge_uid == "ku:a"
        assert published[0].habit_uid == result.value.uid

    async def test_multiple_links_publish_the_bulk_event(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        from core.events.knowledge_substance_events import (
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkBuiltIntoHabit,
        )

        await habit_core.create_habit(
            make_habit_request(linked_knowledge_uids=["ku:a", "ku:b"]), USER_UID
        )

        history = event_bus.get_event_history()
        bulk = [e for e in history if isinstance(e, KnowledgeBulkBuiltIntoHabit)]
        singles = [e for e in history if isinstance(e, KnowledgeBuiltIntoHabit)]
        assert len(bulk) == 1, f"expected 1 bulk event, got {len(bulk)}"
        assert set(bulk[0].knowledge_uids) == {"ku:a", "ku:b"}
        assert singles == [], "the bulk path must not also fire per-item events"

    async def test_a_refused_link_announces_no_substance(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """Substance follows the WRITTEN edges, never the requested ones.

        A link the guard refuses leaves no edge, so claiming knowledge was built into
        a habit would make ``times_built_into_habits`` disagree with the graph — the
        exact staleness this event exists to prevent.
        """
        from core.events.knowledge_substance_events import (
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkBuiltIntoHabit,
        )

        habit_backend.labels["task:not-knowledge"] = ["Entity", "Task"]

        result = await habit_core.create_habit(
            make_habit_request(linked_knowledge_uids=["task:not-knowledge"]), USER_UID
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeBuiltIntoHabit | KnowledgeBulkBuiltIntoHabit)
        ] == [], "substance was announced for a link that was never written"

    async def test_a_failed_batch_announces_no_substance(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """The batch is all-or-nothing: a failure means nothing was written."""
        from core.events.knowledge_substance_events import (
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkBuiltIntoHabit,
        )

        async def _refuse(*_args: Any, **_kwargs: Any) -> Result[int]:
            return Result.fail("batch validation failed")

        habit_backend.create_relationships_batch = _refuse  # type: ignore[method-assign]

        await habit_core.create_habit(make_habit_request(linked_knowledge_uids=["ku:a"]), USER_UID)

        assert [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeBuiltIntoHabit | KnowledgeBulkBuiltIntoHabit)
        ] == [], "substance was announced although the batch wrote nothing"

    async def test_a_repeated_uid_is_counted_once(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """A UID repeated in the request must not credit the same knowledge twice.

        The batch MERGEs, so the graph holds ONE edge — but the bulk event UNWINDs
        whatever it is given and ``batch_increment_substance`` increments once per row,
        so one habit would count several times for a single connection. (Codex, #965.)
        """
        from core.events.knowledge_substance_events import (
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkBuiltIntoHabit,
        )

        await habit_core.create_habit(
            make_habit_request(linked_knowledge_uids=["ku:a", "ku:a"]), USER_UID
        )

        history = event_bus.get_event_history()
        bulk = [e for e in history if isinstance(e, KnowledgeBulkBuiltIntoHabit)]
        singles = [e for e in history if isinstance(e, KnowledgeBuiltIntoHabit)]

        assert bulk == [], f"a single distinct UID must not take the bulk path: {bulk}"
        assert len(singles) == 1, f"expected 1 substance event, got {len(singles)}"
        assert singles[0].knowledge_uid == "ku:a"

    async def test_a_linkless_habit_announces_nothing(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Positive control: no knowledge links, no substance event."""
        from core.events.knowledge_substance_events import (
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkBuiltIntoHabit,
        )

        await habit_core.create_habit(make_habit_request(), USER_UID)

        assert [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeBuiltIntoHabit | KnowledgeBulkBuiltIntoHabit)
        ] == []


@pytest.mark.asyncio
class TestHabitEdgesPrecedeTheEvent:
    """``HabitCreated`` must not fire until the link edges are written.

    ``HabitCreated`` is subscribed to ``invalidate_context``, and the rebuild reads
    ``habit_linked_goals`` (SUPPORTS_GOAL) and ``habit_applied_knowledge``
    (REINFORCES_KNOWLEDGE) straight back out of the graph.
    """

    async def test_edges_are_written_before_habit_created(
        self, habit_core: HabitsCoreService, habit_backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        def _record(_event: HabitCreated) -> None:
            habit_backend.trace.append("habit_created_published")

        event_bus.subscribe(HabitCreated, _record)

        result = await habit_core.create_habit(
            make_habit_request(linked_goal_uids=["goal:a"], linked_knowledge_uids=["ku:a"]),
            USER_UID,
        )

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert "habit_created_published" in habit_backend.trace, "HabitCreated was never published"
        assert habit_backend.trace.index("edges_written") < habit_backend.trace.index(
            "habit_created_published"
        ), (
            "HabitCreated fired BEFORE the link edges were written — a context rebuild "
            f"would cache a habit with no links. Order was: {habit_backend.trace}"
        )

    async def test_linkless_habit_still_publishes(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Positive control for the deferred publish."""
        result = await habit_core.create_habit(make_habit_request(), USER_UID)

        assert result.is_ok, f"create_habit failed: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, HabitCreated)], (
            "a linkless habit stopped publishing HabitCreated"
        )

    async def test_entity_door_still_publishes(
        self, habit_facade: HabitsService, event_bus: InMemoryEventBus
    ) -> None:
        """The entity door writes no link edges; it must still announce the habit."""
        result = await habit_facade.create(
            Habit(uid="habit:door-a", user_uid=USER_UID, title="Route-created")
        )

        assert result.is_ok, f"DOOR A create failed: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, HabitCreated)], (
            "the route door stopped publishing HabitCreated"
        )

    async def test_exactly_one_event_per_create(
        self, habit_core: HabitsCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Guards the fix's own failure mode: the create()/_create_validated split
        must not publish HabitCreated twice."""
        await habit_core.create_habit(make_habit_request(linked_goal_uids=["goal:a"]), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, HabitCreated)]
        assert len(created) == 1, f"expected 1 HabitCreated, got {len(created)}"


@pytest.mark.asyncio
class TestHabitEntityDoorCannotCarryLinks:
    """The generated CRUD route structurally cannot write the four link edges.

    Not an oversight to fix by mirroring Goals: ``CRUDRouteFactory`` converts the
    request to a ``Habit`` and calls ``create(entity)``, and none of the four lists
    is a ``Habit`` field — the converter drops them at that boundary. Closing this
    would take a request-carrying create route or promoting the lists onto the
    entity, both of which are larger decisions than this change.

    Pinned so that a future edit which DOES put them on the entity is noticed here,
    rather than leaving the two doors silently divergent again.
    """

    async def test_habit_model_carries_none_of_the_link_lists(self) -> None:
        link_fields = {
            "linked_knowledge_uids",
            "linked_goal_uids",
            "linked_principle_uids",
            "prerequisite_habit_uids",
        }
        habit_fields = {f.name for f in Habit.__dataclass_fields__.values()}

        assert link_fields.isdisjoint(habit_fields), (
            f"Habit now carries {link_fields & habit_fields} — the generated CRUD "
            "route can write those edges too, and create() should be updated to do so "
            "(as GoalsCoreService.create does for fulfills_goal_uid)"
        )

    async def test_entity_door_writes_no_link_edges(
        self, habit_facade: HabitsService, habit_backend: StubBackend
    ) -> None:
        """Documents the current, asserted limit — not an endorsement of it."""
        from core.services.conversion_service import ConversionServiceV2

        entity = ConversionServiceV2.habit_create_to_pure(
            make_habit_request(linked_goal_uids=["goal:a"], linked_knowledge_uids=["ku:a"]),
            "habit:door-a",
            user_uid=USER_UID,
            status=EntityStatus.ACTIVE,
        )
        result = await habit_facade.create(entity)

        assert result.is_ok, f"DOOR A create failed: {result.error}"
        assert habit_backend.batched == [], (
            "the entity door wrote link edges — if the converter now carries the "
            "lists, this suite's asymmetry note is stale"
        )
