"""_SpawnOrchestrator — turns a TemplateBundle into per-student instances.

4-layer canonical spawn order (per project_engage_pathstep_contract.md):

    Layer 1: Choice, Habit, Principle    (no cross-template refs depend on them yet)
    Layer 2: Goal                         (may reference Choice templates)
    Layer 3: Event                        (may reference Habit, Goal)
    Layer 4: Task                         (may reference Goal, Habit, Event)

Within each layer the orchestrator:
1. Pre-allocates an instance UID per template — populates the
   ``template_uid → instance_uid`` map *before* persisting, so later layers
   can resolve their cross-template refs even if their layer-1 dependencies
   are still being created in the same call.
2. Constructs the frozen instance dataclass with:
   - ``user_uid`` = student
   - ``template_uid`` = source template uid
   - ``engagement_state`` = "engaged"
   - All ``*_template_uid`` fields rewritten to ``*_uid`` instance UIDs via the map
   - All ``RelativeOffset`` fields resolved to absolute date/datetime against
     ``engagement_anchor`` (the engagement edge's ``since`` timestamp)
   - All other authoring fields (title, description, scoring weights, etc.)
     copied through unchanged.
3. Persists via the activity backend's ``create_with_spawned_from()`` — an
   atomic Cypher write that creates the instance node AND the
   ``(instance)-[:SPAWNED_FROM {spawned_at}]->(template)`` edge in one
   transaction. The edge is the only back-reference; there is no parallel
   ``template_uid`` property.

Transactional semantics for V1: best-effort. If a layer-N create fails, the
orchestrator returns a failure Result and the facade rolls back by deleting
the already-persisted instances. A true single-transaction spawn would
require a custom multi-statement Cypher block — deferred to a follow-up
once the per-instance backend create surface is stable.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Any, Literal

from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.templates.relative_offset import RelativeOffset
from core.ports import CrudOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

from ._validator import TemplateBundle

if TYPE_CHECKING:
    from datetime import date, datetime

    from core.models.templates.choice_template import ChoiceTemplate
    from core.models.templates.event_template import EventTemplate
    from core.models.templates.goal_template import GoalTemplate
    from core.models.templates.habit_template import HabitTemplate
    from core.models.templates.principle_template import PrincipleTemplate
    from core.models.templates.task_template import TaskTemplate

logger = get_logger(__name__)


# ============================================================================
# Cross-template reference rewrites: template field → instance field name
# ============================================================================
#
# When spawning, each ``*_template_uid`` field on the source template is
# rewritten to the corresponding ``*_uid`` field on the spawned instance,
# with the value translated through the template→instance UID map.

TASK_FIELD_REWRITES: dict[str, str] = {
    "fulfills_goal_template_uid": "fulfills_goal_uid",
    # reinforces_habit_template_uid is NOT rewritten to a property — instead
    # written as a (Task)-[:REINFORCES_HABIT]->(Habit) edge. See TASK_CROSS_EDGES.
    "scheduled_event_template_uid": "scheduled_event_uid",
    # parent_template_uid → parent_uid (intra-domain; resolved within Task layer)
    "parent_template_uid": "parent_uid",
}
GOAL_FIELD_REWRITES: dict[str, str] = {
    "fulfills_goal_template_uid": "fulfills_goal_uid",
    # inspired_by_choice_template_uid is NOT rewritten to a property — instead
    # written as a (Goal)-[:INSPIRED_BY_CHOICE]->(Choice) edge by the spawn
    # orchestrator. See _build_goal cross_edges return.
    "selected_choice_option_template_uid": "selected_choice_option_uid",
}

# ============================================================================
# Cross-template edge writes — relationships written as graph edges, not properties
# ============================================================================
#
# Some template-to-template references are realized at spawn time as graph
# edges between the spawned instances, NOT as `*_uid` properties on the
# instance node. The orchestrator's `_build_*` functions return cross-edge
# specs alongside the instance dataclass; `_persist` writes them after the
# node + SPAWNED_FROM edge.
#
# Format: (template_field_name, instance_edge_type)
GOAL_CROSS_EDGES: list[tuple[str, str]] = [
    ("inspired_by_choice_template_uid", "INSPIRED_BY_CHOICE"),
]
EVENT_CROSS_EDGES: list[tuple[str, str]] = [
    ("milestone_celebration_for_goal_template_uid", "CELEBRATES_GOAL"),
    ("reinforces_habit_template_uid", "REINFORCES_HABIT"),
]
TASK_CROSS_EDGES: list[tuple[str, str]] = [
    ("reinforces_habit_template_uid", "REINFORCES_HABIT"),
]
EVENT_FIELD_REWRITES: dict[str, str] = {
    # Neither reinforces_habit_template_uid nor milestone_celebration_for_goal_template_uid
    # is rewritten to a property — both are written as graph edges
    # ((Event)-[:REINFORCES_HABIT]->(Habit), (Event)-[:CELEBRATES_GOAL]->(Goal)).
    # See EVENT_CROSS_EDGES.
}

# ============================================================================
# RelativeOffset → instance date/datetime field rewrites
# ============================================================================
#
# Per project_template_relative_offset.md: stored-at-spawn. The orchestrator
# resolves each *_offset field on the template against the engagement anchor
# and writes the absolute value to the corresponding instance field. All
# instance fields are date except Choice.decision_deadline (datetime).

# (template_field, instance_field, kind)
OffsetKind = Literal["date", "datetime"]

TASK_OFFSET_REWRITES: list[tuple[str, str, OffsetKind]] = [
    ("due_offset", "due_date", "date"),
    ("scheduled_offset", "scheduled_date", "date"),
    ("recurrence_end_offset", "recurrence_end_date", "date"),
]
GOAL_OFFSET_REWRITES: list[tuple[str, str, OffsetKind]] = [
    ("start_offset", "start_date", "date"),
    ("target_offset", "target_date", "date"),
]
HABIT_OFFSET_REWRITES: list[tuple[str, str, OffsetKind]] = [
    ("recurrence_end_offset", "recurrence_end_date", "date"),
]
EVENT_OFFSET_REWRITES: list[tuple[str, str, OffsetKind]] = [
    ("event_offset", "event_date", "date"),
    ("recurrence_end_offset", "recurrence_end_date", "date"),
]
CHOICE_OFFSET_REWRITES: list[tuple[str, str, OffsetKind]] = [
    ("decision_deadline_offset", "decision_deadline", "datetime"),
]
# PrincipleTemplate has no offsets.


# ============================================================================
# Activity backend protocol (structural — we only need create + delete by uid)
# ============================================================================


@dataclass(frozen=True)
class ActivityBackends:
    """Bundle of the 6 activity instance backends — collected once by the facade."""

    tasks: CrudOperations[Task]
    goals: CrudOperations[Goal]
    habits: CrudOperations[Habit]
    events: CrudOperations[Event]
    choices: CrudOperations[Choice]
    principles: CrudOperations[Principle]


@dataclass
class SpawnResult:
    """Output of a successful spawn — the facade hands these to the engagement."""

    instance_uids: list[str]
    template_to_instance: dict[str, str]


class _SpawnOrchestrator:
    """Spawn a per-student set of instances from a PS's TemplateBundle."""

    def __init__(self, backends: ActivityBackends) -> None:
        self._backends = backends
        self.logger = logger

    async def spawn(
        self,
        student_uid: str,
        ps_uid: str,
        bundle: TemplateBundle,
        engagement_anchor: datetime,
    ) -> Result[SpawnResult]:
        """Run all 4 layers. On any failure, roll back already-created instances."""
        template_to_instance: dict[str, str] = {}
        created_uids: list[tuple[Any, str]] = []  # (backend, instance_uid) for rollback

        # ----- Pre-allocate UIDs across all 6 domains -----
        for ct in bundle.choices:
            template_to_instance[str(ct.uid)] = str(UIDGenerator.generate_uid("choice", ct.title))
        for ht in bundle.habits:
            template_to_instance[str(ht.uid)] = str(UIDGenerator.generate_uid("habit", ht.title))
        for pt in bundle.principles:
            template_to_instance[str(pt.uid)] = str(
                UIDGenerator.generate_uid("principle", pt.title)
            )
        for gt in bundle.goals:
            template_to_instance[str(gt.uid)] = str(UIDGenerator.generate_uid("goal", gt.title))
        for et in bundle.events:
            template_to_instance[str(et.uid)] = str(UIDGenerator.generate_uid("event", et.title))
        for tt in bundle.tasks:
            template_to_instance[str(tt.uid)] = str(UIDGenerator.generate_uid("task", tt.title))

        # ----- Layer 1: Choice, Habit, Principle (no template-level refs) -----
        for ct in bundle.choices:
            choice_inst = _build_choice(
                ct, student_uid, ps_uid, engagement_anchor, template_to_instance
            )
            res = await self._persist(
                self._backends.choices, choice_inst, str(ct.uid), created_uids
            )
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)
        for ht in bundle.habits:
            habit_inst = _build_habit(ht, student_uid, engagement_anchor, template_to_instance)
            res = await self._persist(self._backends.habits, habit_inst, str(ht.uid), created_uids)
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)
        for pt in bundle.principles:
            principle_inst = _build_principle(pt, student_uid, ps_uid, template_to_instance)
            res = await self._persist(
                self._backends.principles, principle_inst, str(pt.uid), created_uids
            )
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)

        # ----- Layer 2: Goal -----
        for gt in bundle.goals:
            goal_inst = _build_goal(
                gt, student_uid, ps_uid, engagement_anchor, template_to_instance
            )
            goal_edges = _compute_cross_edges(gt, GOAL_CROSS_EDGES, template_to_instance)
            res = await self._persist(
                self._backends.goals,
                goal_inst,
                str(gt.uid),
                created_uids,
                cross_edges=goal_edges,
            )
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)

        # ----- Layer 3: Event -----
        for et in bundle.events:
            event_inst = _build_event(et, student_uid, engagement_anchor, template_to_instance)
            event_edges = _compute_cross_edges(et, EVENT_CROSS_EDGES, template_to_instance)
            res = await self._persist(
                self._backends.events,
                event_inst,
                str(et.uid),
                created_uids,
                cross_edges=event_edges,
            )
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)

        # ----- Layer 4: Task -----
        for tt in bundle.tasks:
            task_inst = _build_task(tt, student_uid, engagement_anchor, template_to_instance)
            task_edges = _compute_cross_edges(tt, TASK_CROSS_EDGES, template_to_instance)
            res = await self._persist(
                self._backends.tasks,
                task_inst,
                str(tt.uid),
                created_uids,
                cross_edges=task_edges,
            )
            if res.is_error:
                await self._rollback(created_uids)
                return Result.fail(res)

        return Result.ok(
            SpawnResult(
                instance_uids=[uid for _, uid in created_uids],
                template_to_instance=template_to_instance,
            )
        )

    async def _persist(
        self,
        backend: Any,  # boundary: backends.create_with_spawned_from is on UniversalNeo4jBackend
        instance: Any,
        template_uid: str,
        created_uids: list[tuple[CrudOperations[Any], str]],
        cross_edges: list[tuple[str, str]] | None = None,
    ) -> Result[Any]:
        """Atomic node + SPAWNED_FROM edge create, then any cross-edges.

        ``cross_edges`` is a list of ``(edge_type, target_uid)`` tuples — used
        when a spawned instance also needs outbound edges to other already-
        spawned instances (e.g. ``(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)``).
        Each cross-edge is written via ``backend.create_relationship``, which
        validates against the relationship registry. If any cross-edge fails,
        the node + SPAWNED_FROM are still committed; the rollback layer above
        deletes the node and its edges via ``DETACH DELETE`` on next failure.
        """
        result: Result[Any] = await backend.create_with_spawned_from(instance, template_uid)
        if result.is_error:
            return result
        # Track for rollback BEFORE writing cross-edges so a cross-edge failure
        # still leaves the node deletable.
        created_uids.append((backend, str(instance.uid)))
        for edge_type, target_uid in cross_edges or ():
            edge_result: Result[bool] = await backend.create_relationship(
                from_uid=instance.uid,
                to_uid=target_uid,
                relationship_type=edge_type,
            )
            if edge_result.is_error:
                return edge_result
        return result

    async def _rollback(self, created_uids: list[tuple[CrudOperations[Any], str]]) -> None:
        """Best-effort delete on partial-spawn failure. Logs but doesn't raise."""
        for backend, uid in reversed(created_uids):
            try:
                await backend.delete(uid, cascade=True)
            except Exception as e:  # safety-net: rollback must not mask the original error
                self.logger.error(
                    f"Rollback failed for instance {uid}: {e} — manual cleanup may be required"
                )


# ============================================================================
# Per-domain instance builders
# ============================================================================
#
# Each takes the template, the student/anchor/uid-map context, and returns the
# frozen instance dataclass with all rewrites applied. Builders are pure — no
# I/O — so they can be unit-tested without mocking backends.


def _resolve_offsets(
    template: Any,
    rewrites: list[tuple[str, str, OffsetKind]],
    anchor: datetime,
) -> dict[str, date | datetime | None]:
    """Apply every (template_offset_field → instance_date_field) rewrite."""
    out: dict[str, date | datetime | None] = {}
    for offset_field, instance_field, kind in rewrites:
        offset: RelativeOffset | None = getattr(template, offset_field, None)
        if offset is None:
            out[instance_field] = None
            continue
        if kind == "datetime":
            out[instance_field] = offset.resolve_to_datetime(anchor)
        else:
            out[instance_field] = offset.resolve_to_date(anchor)
    return out


def _resolve_refs(
    template: Any,
    rewrites: dict[str, str],
    template_to_instance: dict[str, str],
) -> dict[str, str | None]:
    """Apply every (template_*_uid_field → instance_*_uid_field) rewrite."""
    out: dict[str, str | None] = {}
    for template_field, instance_field in rewrites.items():
        ref = getattr(template, template_field, None)
        out[instance_field] = template_to_instance.get(ref) if ref else None
    return out


def _compute_cross_edges(
    template: Any,
    cross_edge_specs: list[tuple[str, str]],
    template_to_instance: dict[str, str],
) -> list[tuple[str, str]]:
    """Resolve cross-template refs into (edge_type, target_instance_uid) tuples.

    Used for relationships that are written as graph edges between spawned
    instances rather than as ``*_uid`` properties — e.g.
    ``(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)``. The ``cross_edge_specs`` are
    ``(template_field_name, edge_type)`` pairs; the helper reads the field on
    the template, maps it through ``template_to_instance``, and returns the
    edges the orchestrator should write via ``_persist``.
    """
    edges: list[tuple[str, str]] = []
    for template_field, edge_type in cross_edge_specs:
        ref = getattr(template, template_field, None)
        if not ref:
            continue
        target_uid = template_to_instance.get(ref)
        if target_uid:
            edges.append((edge_type, target_uid))
    return edges


def _copy_through(template: Any, allowed_fields: set[str]) -> dict[str, Any]:
    """Copy authoring-side fields verbatim from template → instance kwargs.

    Filters out any field name that the instance doesn't accept (so the call
    to the instance constructor is safe regardless of which fields the
    template happens to carry).
    """
    out: dict[str, Any] = {}
    for f in fields(template):
        if f.name in allowed_fields:
            out[f.name] = getattr(template, f.name)
    return out


def _instance_field_names(cls: type) -> set[str]:
    return {f.name for f in fields(cls)}


def _build_task(
    template: TaskTemplate,
    student_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> Task:
    """Build a Task instance from a TaskTemplate."""
    instance_fields = _instance_field_names(Task)
    # Authoring fields the template and instance share (title, description,
    # tags, durations, weights, etc.) — copy verbatim.
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            # date fields and *_uid refs are filled by the rewrites below
            *(r[1] for r in TASK_OFFSET_REWRITES),
            *TASK_FIELD_REWRITES.values(),
            "source_path_step_uid",
        },
    )
    return Task(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        **shared,
        **_resolve_offsets(template, TASK_OFFSET_REWRITES, anchor),
        **_resolve_refs(template, TASK_FIELD_REWRITES, template_to_instance),
    )


def _build_goal(
    template: GoalTemplate,
    student_uid: str,
    ps_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> Goal:
    instance_fields = _instance_field_names(Goal)
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            "source_path_step_uid",
            *(r[1] for r in GOAL_OFFSET_REWRITES),
            *GOAL_FIELD_REWRITES.values(),
        },
    )
    return Goal(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        source_path_step_uid=ps_uid,
        **shared,
        **_resolve_offsets(template, GOAL_OFFSET_REWRITES, anchor),
        **_resolve_refs(template, GOAL_FIELD_REWRITES, template_to_instance),
    )


def _build_habit(
    template: HabitTemplate,
    student_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> Habit:
    instance_fields = _instance_field_names(Habit)
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            *(r[1] for r in HABIT_OFFSET_REWRITES),
        },
    )
    return Habit(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        **shared,
        **_resolve_offsets(template, HABIT_OFFSET_REWRITES, anchor),
    )


def _build_event(
    template: EventTemplate,
    student_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> Event:
    instance_fields = _instance_field_names(Event)
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            *(r[1] for r in EVENT_OFFSET_REWRITES),
            *EVENT_FIELD_REWRITES.values(),
        },
    )
    return Event(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        **shared,
        **_resolve_offsets(template, EVENT_OFFSET_REWRITES, anchor),
        **_resolve_refs(template, EVENT_FIELD_REWRITES, template_to_instance),
    )


def _build_choice(
    template: ChoiceTemplate,
    student_uid: str,
    ps_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> Choice:
    instance_fields = _instance_field_names(Choice)
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            "source_path_step_uid",
            *(r[1] for r in CHOICE_OFFSET_REWRITES),
        },
    )
    return Choice(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        source_path_step_uid=ps_uid,
        **shared,
        **_resolve_offsets(template, CHOICE_OFFSET_REWRITES, anchor),
    )


def _build_principle(
    template: PrincipleTemplate,
    student_uid: str,
    ps_uid: str,
    template_to_instance: dict[str, str],
) -> Principle:
    instance_fields = _instance_field_names(Principle)
    shared = _copy_through(
        template,
        instance_fields
        - {
            "uid",
            "user_uid",
            "engagement_state",
            "entity_type",
            "source_path_step_uid",
        },
    )
    return Principle(
        uid=template_to_instance[template.uid],
        user_uid=student_uid,
        engagement_state="engaged",
        source_path_step_uid=ps_uid,
        **shared,
    )


# ``replace`` is re-exported for callers that want to clone an instance with
# overrides; not used internally.
__all__ = [
    "ActivityBackends",
    "SpawnResult",
    "_SpawnOrchestrator",
    "replace",
]
