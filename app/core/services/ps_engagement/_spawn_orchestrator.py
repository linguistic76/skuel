"""_SpawnOrchestrator — turns a TemplateBundle into per-student instances.

When a student engages a PathStep, each Activity Template attached to it spawns
one user-owned instance. The per-domain recipe for that transform lives in
``SPAWN_REGISTRY`` — one ``DomainSpawnSpec`` per Activity Domain. Adding a 7th
domain is a single registry entry; the orchestrator itself is domain-agnostic.

Each spec carries:

- ``layer`` — dependency order (1..4). Lower layers spawn first so later layers
  can resolve cross-references to instances created earlier in the same call:

      Layer 1: Choice, Habit, Principle    (nothing depends on them yet)
      Layer 2: Goal                         (may reference Choice)
      Layer 3: Event                        (may reference Habit, Goal)
      Layer 4: Task                         (may reference Goal, Habit, Event)

- ``offset_rewrites`` — ``RelativeOffset`` template fields resolved to absolute
  date/datetime instance fields against the engagement anchor.
- ``field_rewrites`` — ``*_template_uid`` template fields rewritten to ``*_uid``
  instance properties, values translated through the template→instance UID map.
- ``cross_edges`` — template refs realised as graph edges between spawned
  instances (e.g. ``(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)``) rather than
  properties.

The orchestrator:

1. Pre-allocates an instance UID per template *before* persisting, so a later
   layer can resolve a cross-reference even to an instance not yet written.
2. Builds each frozen instance via ``_build`` with ``user_uid`` = student,
   ``engagement_state`` = ``EngagementState.ENGAGED``, ``source_path_step_uid`` = ps_uid, all
   offsets/refs resolved, and every other authoring field copied through.
3. Persists via the backend's ``create_with_spawned_from()`` — an atomic write
   of the instance node AND the ``(instance)-[:SPAWNED_FROM {spawned_at}]->(template)``
   edge. That edge is the template back-reference; there is no ``template_uid``
   property.

Transactional semantics for V1: best-effort. If a layer-N create fails, the
orchestrator returns a failure Result and rolls back by deleting the already-
persisted instances. A true single-transaction spawn would require a custom
multi-statement Cypher block — deferred to a follow-up once the per-instance
backend create surface is stable.

See: ``docs/decisions/ADR-061-spawn-layer-consolidation.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, replace
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from core.models.choice.choice import Choice
from core.models.entity import Entity
from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.models.user_owned_entity import UserOwnedEntity
from core.ports import CrudOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

from ._template_bundle import TemplateBundle

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date, datetime

logger = get_logger(__name__)

OffsetKind = Literal["date", "datetime"]

# The instance type a spec produces (Task, Goal, …). Parameterising
# DomainSpawnSpec over it keeps _build's return concrete: _build(TASK_SPEC, …)
# is statically a Task, so callers and tests see the real attributes.
InstanceT = TypeVar("InstanceT", bound=UserOwnedEntity)


# ============================================================================
# Pure transform helpers (domain-agnostic — driven by per-spec rewrite tables)
# ============================================================================


def _resolve_offsets(
    template: Any,
    rewrites: Sequence[tuple[str, str, OffsetKind]],
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
    cross_edge_specs: Sequence[tuple[str, RelationshipName]],
    template_to_instance: dict[str, str],
) -> list[tuple[RelationshipName, str]]:
    """Resolve cross-template refs into (edge_type, target_instance_uid) tuples.

    Used for relationships written as graph edges between spawned instances
    rather than as ``*_uid`` properties — e.g. ``(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)``.
    Each spec is a ``(template_field_name, edge_type)`` pair; the helper reads
    the field on the template, maps it through ``template_to_instance``, and
    returns the edges the orchestrator should write via ``_persist``.
    """
    edges: list[tuple[RelationshipName, str]] = []
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

    Filters out any field name the instance doesn't accept, so the constructor
    call is safe regardless of which fields the template happens to carry.
    """
    out: dict[str, Any] = {}
    for f in fields(template):
        if f.name in allowed_fields:
            out[f.name] = getattr(template, f.name)
    return out


def _field_names(cls: type) -> set[str]:
    """Field names of any (template or instance) frozen dataclass."""
    return {f.name for f in fields(cls)}


# ============================================================================
# Backend bundle + spawn result
# ============================================================================


@dataclass(frozen=True)
class ActivityBackends:
    """Bundle of the 6 activity instance backends — collected once by the facade.

    Attribute names match ``DomainSpawnSpec.collection_attr`` so the orchestrator
    can resolve a domain's backend by ``getattr(self._backends, spec.collection_attr)``.
    """

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


# ============================================================================
# DomainSpawnSpec registry — the single source of per-domain spawn behaviour
# ============================================================================


@dataclass(frozen=True)
class DomainSpawnSpec(Generic[InstanceT]):
    """One Activity Domain's spawn recipe (see the module docstring for fields).

    Generic in the instance type, so ``TASK_SPEC`` is a ``DomainSpawnSpec[Task]``
    and ``_build(TASK_SPEC, …)`` returns a ``Task``. Adding a 7th activity domain
    is a single entry in ``SPAWN_REGISTRY`` — the orchestrator reads everything
    it needs from these fields, so there is no per-domain builder, pre-allocate
    clause, or spawn block to add.
    """

    instance_cls: type[InstanceT]
    template_cls: type[Entity]
    layer: int
    collection_attr: str  # attribute name on both TemplateBundle and ActivityBackends
    uid_prefix: str  # UIDGenerator prefix for spawned instance UIDs
    offset_rewrites: tuple[tuple[str, str, OffsetKind], ...] = ()
    field_rewrites: dict[str, str] = field(default_factory=dict)
    cross_edges: tuple[tuple[str, RelationshipName], ...] = ()


CHOICE_SPEC = DomainSpawnSpec(
    instance_cls=Choice,
    template_cls=ChoiceTemplate,
    layer=1,
    collection_attr="choices",
    uid_prefix="choice",
    offset_rewrites=(("decision_deadline_offset", "decision_deadline", "datetime"),),
)
HABIT_SPEC = DomainSpawnSpec(
    instance_cls=Habit,
    template_cls=HabitTemplate,
    layer=1,
    collection_attr="habits",
    uid_prefix="habit",
    offset_rewrites=(("recurrence_end_offset", "recurrence_end_date", "date"),),
)
PRINCIPLE_SPEC = DomainSpawnSpec(
    instance_cls=Principle,
    template_cls=PrincipleTemplate,
    layer=1,
    collection_attr="principles",
    uid_prefix="principle",
)
GOAL_SPEC = DomainSpawnSpec(
    instance_cls=Goal,
    template_cls=GoalTemplate,
    layer=2,
    collection_attr="goals",
    uid_prefix="goal",
    offset_rewrites=(
        ("start_offset", "start_date", "date"),
        ("target_offset", "target_date", "date"),
    ),
    field_rewrites={
        "fulfills_goal_template_uid": "fulfills_goal_uid",
        "selected_choice_option_template_uid": "selected_choice_option_uid",
    },
    # inspired_by_choice_template_uid → (Goal)-[:INSPIRED_BY_CHOICE]->(Choice) edge
    cross_edges=(("inspired_by_choice_template_uid", RelationshipName.INSPIRED_BY_CHOICE),),
)
EVENT_SPEC = DomainSpawnSpec(
    instance_cls=Event,
    template_cls=EventTemplate,
    layer=3,
    collection_attr="events",
    uid_prefix="event",
    offset_rewrites=(
        ("event_offset", "event_date", "date"),
        ("recurrence_end_offset", "recurrence_end_date", "date"),
    ),
    # Both refs are written as graph edges, not properties:
    #   (Event)-[:CELEBRATES_GOAL]->(Goal), (Event)-[:REINFORCES_HABIT]->(Habit)
    cross_edges=(
        ("milestone_celebration_for_goal_template_uid", RelationshipName.CELEBRATES_GOAL),
        ("reinforces_habit_template_uid", RelationshipName.REINFORCES_HABIT),
    ),
)
TASK_SPEC = DomainSpawnSpec(
    instance_cls=Task,
    template_cls=TaskTemplate,
    layer=4,
    collection_attr="tasks",
    uid_prefix="task",
    offset_rewrites=(
        ("due_offset", "due_date", "date"),
        ("scheduled_offset", "scheduled_date", "date"),
        ("recurrence_end_offset", "recurrence_end_date", "date"),
    ),
    field_rewrites={
        "fulfills_goal_template_uid": "fulfills_goal_uid",
        "scheduled_event_template_uid": "scheduled_event_uid",
        "parent_template_uid": "parent_uid",
    },
    # reinforces_habit_template_uid → (Task)-[:REINFORCES_HABIT]->(Habit) edge
    cross_edges=(("reinforces_habit_template_uid", RelationshipName.REINFORCES_HABIT),),
)

# Declaration order is the UID pre-allocation order; build order is by ``layer``.
SPAWN_REGISTRY: tuple[DomainSpawnSpec[Any], ...] = (
    CHOICE_SPEC,
    HABIT_SPEC,
    PRINCIPLE_SPEC,
    GOAL_SPEC,
    EVENT_SPEC,
    TASK_SPEC,
)

# Stable sort: within a layer, declaration order is preserved.
_BUILD_ORDER: tuple[DomainSpawnSpec[Any], ...] = tuple(
    sorted(SPAWN_REGISTRY, key=attrgetter("layer"))
)


def _build(
    spec: DomainSpawnSpec[InstanceT],
    template: Any,
    student_uid: str,
    ps_uid: str,
    anchor: datetime,
    template_to_instance: dict[str, str],
) -> InstanceT:
    """Build one activity instance from its template, per ``spec``.

    Pure — no I/O — so it unit-tests without backends. Replaces the six former
    ``_build_*`` functions; all per-domain variation now lives in the spec.
    ``entity_type`` is left out of the copy-through so the instance keeps its own
    class default (``Task`` not ``TaskTemplate``).
    """
    managed = {
        "uid",
        "user_uid",
        "engagement_state",
        "entity_type",
        "source_path_step_uid",
        *(dst for _src, dst, _kind in spec.offset_rewrites),
        *spec.field_rewrites.values(),
    }
    # boundary: spawn kwargs span all six domains — heterogeneous by construction
    kwargs: dict[str, Any] = {
        "uid": template_to_instance[template.uid],
        "user_uid": student_uid,
        "engagement_state": EngagementState.ENGAGED,
        "source_path_step_uid": ps_uid,
        **_copy_through(template, _field_names(spec.instance_cls) - managed),
        **_resolve_offsets(template, spec.offset_rewrites, anchor),
        **_resolve_refs(template, spec.field_rewrites, template_to_instance),
    }
    return spec.instance_cls(**kwargs)


def _class_name_to_entity_type(cls: type) -> EntityType | None:
    """Map a PascalCase class name to its EntityType (e.g. TaskTemplate → TASK_TEMPLATE)."""
    snake = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", cls.__name__).lower()
    try:
        return EntityType(snake)
    except ValueError:
        return None


def _validate_spawn_registry(registry: tuple[DomainSpawnSpec[Any], ...]) -> None:
    """Fail-fast at import: every spec's rewrite/edge fields must resolve.

    Mirrors ADR-056's factory-time validation — a typo in a rewrite table, a
    bad ``collection_attr``, or an unknown edge type surfaces at module load,
    not at first spawn. Also cross-checks each spec's template/instance class
    pair against ``EntityType.instance_type()`` to catch mis-wired registry
    entries that would silently spawn the wrong instance type.
    """
    bundle_fields = _field_names(TemplateBundle)
    backend_fields = _field_names(ActivityBackends)
    for spec in registry:
        tmpl = spec.template_cls.__name__
        inst = spec.instance_cls.__name__
        where = f"{inst} spawn spec"
        tmpl_fields = _field_names(spec.template_cls)
        inst_fields = _field_names(spec.instance_cls)
        # Cross-check template/instance pair against EntityType.instance_type().
        tmpl_et = _class_name_to_entity_type(spec.template_cls)
        inst_et = _class_name_to_entity_type(spec.instance_cls)
        if tmpl_et is not None and tmpl_et.is_activity_template():
            expected_inst_et = tmpl_et.instance_type()
            if inst_et != expected_inst_et:
                raise ValueError(
                    f"{where}: {tmpl}.instance_type() is {expected_inst_et!r} "
                    f"but spec.instance_cls maps to {inst_et!r}"
                )
        if spec.collection_attr not in bundle_fields:
            raise ValueError(
                f"{where}: collection_attr '{spec.collection_attr}' is not a TemplateBundle field"
            )
        if spec.collection_attr not in backend_fields:
            raise ValueError(
                f"{where}: collection_attr '{spec.collection_attr}' is not an ActivityBackends field"
            )
        for src, dst, _kind in spec.offset_rewrites:
            if src not in tmpl_fields:
                raise ValueError(f"{where}: offset source '{src}' not on {tmpl}")
            if dst not in inst_fields:
                raise ValueError(f"{where}: offset target '{dst}' not on {inst}")
        for src, dst in spec.field_rewrites.items():
            if src not in tmpl_fields:
                raise ValueError(f"{where}: ref source '{src}' not on {tmpl}")
            if dst not in inst_fields:
                raise ValueError(f"{where}: ref target '{dst}' not on {inst}")
        for src, edge_type in spec.cross_edges:
            if src not in tmpl_fields:
                raise ValueError(f"{where}: cross-edge source '{src}' not on {tmpl}")
            # The field is typed RelationshipName, but mypy's arg-type is globally
            # disabled — so this import-time isinstance check is the real fail-fast
            # guard against a non-enum edge type slipping in (ADR-056).
            if not isinstance(edge_type, RelationshipName):
                raise ValueError(
                    f"{where}: cross-edge type '{edge_type}' is not a RelationshipName"
                )


_validate_spawn_registry(SPAWN_REGISTRY)


# ============================================================================
# Orchestrator
# ============================================================================


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
        """Pre-allocate UIDs, then build + persist every instance in layer order.

        On any failure, roll back the already-created instances.
        """
        template_to_instance: dict[str, str] = {}
        created_uids: list[tuple[Any, str]] = []  # (backend, instance_uid) for rollback

        # Pre-allocate an instance UID per template across all domains, so a
        # later layer can resolve a cross-reference to an instance whose node is
        # not yet written.
        for spec in SPAWN_REGISTRY:
            for tmpl in getattr(bundle, spec.collection_attr):
                template_to_instance[str(tmpl.uid)] = str(
                    UIDGenerator.generate_uid(spec.uid_prefix, tmpl.title)
                )

        # Build + persist in dependency-layer order
        # (Choice/Habit/Principle → Goal → Event → Task).
        for spec in _BUILD_ORDER:
            backend = getattr(self._backends, spec.collection_attr)
            for tmpl in getattr(bundle, spec.collection_attr):
                instance = _build(
                    spec, tmpl, student_uid, ps_uid, engagement_anchor, template_to_instance
                )
                cross_edges = _compute_cross_edges(tmpl, spec.cross_edges, template_to_instance)
                res = await self._persist(
                    backend, instance, str(tmpl.uid), created_uids, cross_edges=cross_edges
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
        cross_edges: list[tuple[RelationshipName, str]] | None = None,
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


# ``replace`` is re-exported for callers that want to clone an instance with
# overrides; not used internally.
__all__ = [
    "SPAWN_REGISTRY",
    "ActivityBackends",
    "DomainSpawnSpec",
    "SpawnResult",
    "_SpawnOrchestrator",
    "replace",
]
