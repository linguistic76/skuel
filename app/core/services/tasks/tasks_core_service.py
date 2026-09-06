"""
Tasks Core Service - CRUD Operations
=====================================

Clean rewrite following CLAUDE.md patterns.
Handles basic task lifecycle management.

**Responsibilities:**
- Create, read, update, delete tasks
- Basic task listing and retrieval
- Automatic knowledge inference on creation
- DTO/Model conversion

**Dependencies:**
- BackendOperations[Task] (backend protocol)
- EntityInferenceService (optional - automatic knowledge inference)
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import TYPE_CHECKING, Any, Final

from core.models.type_hints import Neo4jProperties, UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskReopened,
    TaskUpdated,
    publish_event,
)
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums import EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_inference_result import TaskInferenceResult
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.ports.query_types import ParentProgressResult, TaskStats
from core.services.base_service import BaseService
from core.services.completion_stamp import (
    completion_moment,
    is_completion_transition,
    is_reopen_transition,
    status_transition_guard,
)
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.services.mixins.link_edge_guard import (
    KNOWLEDGE_LABELS,
    EdgeTuple,
    LinkEdge,
    keep_permitted_link_edges,
)
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


@dataclasses.dataclass(frozen=True)
class WrittenLinks:
    """What ``_write_link_edges`` actually put in the graph.

    Everything downstream of the batch is derived from these — the substance
    announcements and the goal-property reconciliation — never from what the request
    asked for, so a refused or dangling link cannot claim an edge that does not exist.

    Attributes:
        applied_knowledge_uids: APPLIES_KNOWLEDGE targets written, deduplicated in order.
        goal_uid: the FULFILLS_GOAL target written, or ``None`` when no goal edge exists.
    """

    applied_knowledge_uids: tuple[str, ...] = ()
    goal_uid: str | None = None

    @classmethod
    def from_edges(cls, relationships: list[EdgeTuple]) -> WrittenLinks:
        # DEDUPED: the batch MERGEs, so a UID repeated in the request yields ONE edge —
        # but the bulk substance event UNWINDs what it is given, crediting the knowledge
        # once per row. dict.fromkeys keeps the order.
        applied = dict.fromkeys(
            target
            for _source, target, rel_type, _props in relationships
            if rel_type == RelationshipName.APPLIES_KNOWLEDGE.value
        )
        goal_uid = next(
            (
                target
                for _source, target, rel_type, _props in relationships
                if rel_type == RelationshipName.FULFILLS_GOAL.value
            ),
            None,
        )
        return cls(applied_knowledge_uids=tuple(applied), goal_uid=goal_uid)


# The HAS_SUBTASK edge's weight when the caller cannot supply one. It is a property of
# the EDGE, not of Task, so the entity door has nothing to pass — same value
# TaskCreateRequest.progress_weight defaults to, so the two doors agree on an unweighted
# subtask. Mirrors GoalsCoreService.DEFAULT_PROGRESS_WEIGHT.
DEFAULT_PROGRESS_WEIGHT: Final = 1.0


class TasksCoreService(
    HierarchyReadMixin["TasksOperations", Task],
    BaseService["TasksOperations", Task, TaskUpdateIntent],
):
    """
    Core CRUD operations for tasks.
    """

    def __init__(
        self,
        backend: TasksOperations,
        ku_inference_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize core service with required dependencies.

        Args:
            backend: TasksOperations backend (required)
            ku_inference_service: EntityInferenceService for knowledge inference (optional)
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend=backend, service_name="tasks.core")
        self.ku_inference_service = ku_inference_service
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        # "active" deliberately means NOT completed (keeps in-progress statuses),
        # not status == "active".
        status_filters={
            "active": {"status__not_in": ["completed"]},
            "completed": {"status": "completed"},
        },
        entity_label="Entity",
    )

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    # No _validate_create hook: Tasks have no creation-time business rule.
    #
    # There was one — "High/Critical priority tasks must have a due date" — but at the
    # time it was deleted (#963) it had never executed: create_task then persisted via
    # _create_and_convert, which bypassed CrudOperationsMixin.create, the hook's only
    # caller. Both doors now run that caller (see ``create`` below), so the hook is
    # reachable and resolves to the inherited no-op BY CHOICE, not by accident — the
    # rule contradicted two live producers of exactly that shape:
    #   - the Activity DSL: @priority(1|2) maps to CRITICAL/HIGH while due_date is set
    #     only when @when() is present, so undated urgent tasks are ordinary DSL output
    #     (core/services/dsl/activity_domain_converters.py)
    #   - GoalTaskGenerator: mints HIGH ("Learn: ...") and CRITICAL tasks with no due date
    #
    # Priority and due_date are independent in this domain. What IS enforced on due_date
    # lives at the request edge (TaskCreateRequest: validate_future_date, and
    # due_date >= scheduled_date), not here.

    def _validate_update(self, current: Task, updates: TaskUpdateIntent) -> Result[None]:
        """
        Validate task updates with the domain's one business rule.

        Business Rule — overdue-priority protection: the priority of an overdue task
        cannot be lowered. Lowering it sweeps a missed deadline under the rug instead
        of facing it; raising it, or lowering it on a task that is not overdue, is
        ordinary re-planning and is allowed.

        ``update_task`` calls this explicitly — it is NOT reached through the inherited
        CRUD hook, because the facade overrides ``update`` / ``update_for_user`` and
        routes both to ``update_task``. That is why the hook had no production caller at
        all until it was wired here (cascade-idempotency arc, correction #14). The
        override is kept so the rule still applies if the generic CRUD is ever entered
        directly. Same shape as Habits (``update_habit`` → ``_validate_habit_update``).

        A second rule — terminal-state protection, refusing *every* change to a
        completed/cancelled/archived task — lived here unreachable and was DELETED
        rather than wired: it would have refused the repeat completion the cascade
        treats as a repair path, refused the status re-post that reopens a task, and
        resurrected for Tasks the achievement immutability #1124 deliberately removed
        for Goals. The only terminal-state gate Tasks has is the cascade's own read in
        ``TasksProgressService._trigger_task``.

        Args:
            current: Current task state
            updates: Typed ``TaskUpdateIntent`` of proposed changes

        Returns:
            Result.ok(None) if valid, Result.fail() with a validation error if not
        """
        changes = updates.to_changes()
        # ``Task.is_overdue()`` is the domain's own definition of overdue and excludes
        # completed tasks. That matters now that terminal tasks are editable: a raw
        # ``due_date < today`` here would invent a NEW prohibition on past-due completed
        # tasks, which the deleted terminal rule had merely made unreachable.
        if "priority" not in changes or not current.is_overdue():
            return Result.ok(None)

        # ``Priority.from_value`` normalizes None/unknown to MEDIUM. The intent allows
        # ``priority=None`` (an explicit clear), so a bare ``Priority(...)`` would raise
        # here — and a cleared priority is still measured (as MEDIUM) rather than
        # skipped, so clearing cannot be used to duck the rule.
        new_priority = Priority.from_value(changes["priority"])
        if new_priority.to_numeric() < Priority.from_value(current.priority).to_numeric():
            return Result.fail(
                Errors.validation(
                    message="Cannot decrease priority of overdue tasks",
                    field="priority",
                    value=changes["priority"],
                )
            )

        return Result.ok(None)

    # ========================================================================
    # READ OPERATIONS WITH GRAPH CONTEXT
    # ========================================================================
    # NOTE: get_with_context() is inherited from BaseService (January 2026)
    #
    # Uses registry-driven query generation from RelationshipRegistry.
    # The TASKS_CONFIG config includes:
    # - subtasks, dependencies, dependents (task hierarchy)
    # - applied_knowledge, required_knowledge (knowledge context)
    # - goal_context, habit_context (single related entities)
    # - related_tasks (shared-neighbor pattern via APPLIES_KNOWLEDGE|FULFILLS_GOAL)
    #
    # See: /core/models/relationship_registry.py - TASKS_CONFIG
    # See: /core/services/base_service.py - get_with_context()
    # ========================================================================

    # ========================================================================
    # CREATE OPERATIONS
    # ========================================================================

    @with_error_handling("knowledge_inference", error_type="system")
    def _enhance_with_knowledge_inference(self, task: Task) -> Result[TaskInferenceResult | None]:
        """Compute knowledge enrichment for a task draft.

        ADR-065: inference returns a typed ``TaskInferenceResult`` and does not
        mutate the input. This method returns ``Result.ok(None)`` when the
        inference service is not configured (feature disabled).
        """
        if not self.ku_inference_service:
            # Feature not configured - this is OK, return None
            return Result.ok(None)

        inference_result = self.ku_inference_service.enhance_task_dto_with_inference(task)
        if inference_result.is_error:
            return Result.fail(inference_result)

        enrichment = inference_result.value
        self.logger.debug(
            "Knowledge inference computed for task '%s': opportunities=%d",
            task.title,
            enrichment.learning_opportunities_count,
        )
        return Result.ok(enrichment)

    async def create(self, entity: Task) -> Result[Task]:
        """Persist, link, then announce — THE create primitive for Tasks.

        Both doors land here: the entity door (``TasksService.create``) and ``create_task``
        below — which the generated CRUD route enters through, since it was bound to
        the request door (``CRUDRouteConfig.request_create_method``). Before this, only ``create_task`` published anything, so a
        task created through ``POST /api/tasks/create`` invalidated no user context and
        was never embedded — the route calls ``service.create(entity)`` on the FACADE,
        which resolved to ``CrudOperationsMixin.create`` and went straight to
        ``backend.create``.

        Tasks declare no ``_validate_create`` hook (see the comment above ``_validate_update``
        — the rule that lived there was deleted in #963 as contradicting the DSL and
        GoalTaskGenerator), so unlike Goals, Habits, Events and Choices there is no
        validation to reach here. What this primitive reconciles is the EVENT half and
        the three ENTITY-CARRIED links.

        ``parent_uid``, ``reinforces_habit_uid`` and ``fulfills_goal_uid`` are written
        here rather than in ``create_task`` because all three ride on the Task, so both
        doors can write them. A link left on the request door alone is a link the entity
        door never writes (``POST /api/tasks/create`` hands the service an entity and no
        request). The first two are edge-only — the mapper keeps them off the node; the
        goal is dual-written, property AND edge (see ``_write_link_edges``).

        Args:
            entity: Task to create

        Returns:
            Result containing created Task

        Events Published:
            - TaskCreated: when the task is successfully created
            - TaskEmbeddingRequested (ADR-074): post-persist embedding refresh
        """
        return await self._create_with_links(entity, progress_weight=DEFAULT_PROGRESS_WEIGHT)

    async def _create_with_links(
        self,
        entity: Task,
        *,
        progress_weight: float,
        request: TaskCreateRequest | None = None,
    ) -> Result[Task]:
        """The one create path: persist, write every edge, then announce.

        ``progress_weight`` is a property of the HAS_SUBTASK EDGE, not of ``Task``, so it
        cannot ride on the entity — only the request door can supply a non-default. It is
        a parameter here rather than a second create path so the edge has exactly one
        write site. ``request`` is likewise present only for the request door: the
        request's link lists (knowledge, principles, prerequisite tasks) are edge-typed
        and reach no ``Task`` field, so the entity door has nothing to pass (``None``,
        and no list edges written).

        Mirrors ``GoalsCoreService._create_with_hierarchy``, with one difference that
        cost a RED test: two of Tasks' entity-carried links (``parent_uid``,
        ``reinforces_habit_uid``) are RELATIONSHIP_SKIP_FIELDS, so they DO NOT SURVIVE THE
        ROUND-TRIP. ``backend.create`` returns ``from_neo4j_node(props, Task)`` over the
        properties it wrote, and the mapper dropped these two on the way in — so
        ``result.value.parent_uid`` is always None. They are read off the INPUT entity and
        passed down explicitly. ``fulfills_goal_uid`` is the third link and a real node
        column, so the persisted task carries it and ``_write_link_edges`` reads it there.
        """
        result: Result[Task] = await self._create_validated(entity)
        if result.is_error:
            return result

        task: Task = result.value
        await self._write_hierarchy_edge(task, entity.parent_uid, progress_weight)
        written = await self._write_link_edges(task, entity.reinforces_habit_uid, request)
        task = await self._reconcile_goal_property(task, written.goal_uid)

        # Every edge is written and the goal stamp agrees with the graph — only now
        # announce the task.
        await self._publish_created(task)
        await self._publish_knowledge_substance(task, list(written.applied_knowledge_uids))
        return Result.ok(task)

    async def _reconcile_goal_property(self, task: Task, written_goal_uid: str | None) -> Task:
        """Keep ``fulfills_goal_uid`` equal to the FULFILLS_GOAL edge target.

        The goal link is dual-written — see ``_write_link_edges``. When the edge was
        refused (missing, another user's, not a Goal) or the batch failed, the property the
        create just persisted names a goal the graph does not connect, so it is CLEARED and
        the returned task says so. A dangling stamp would satisfy no reader anyway: the
        relevance scorer checks it against the user's active goals and the goal-progress
        cascade addresses the goal by it. Runs BEFORE ``_publish_created`` — the
        ``TaskCreated`` rebuild caches the task for 300s.

        A failed clear is logged at ERROR and the task is returned as persisted: the stamp
        is still on the node, and the caller must not be told otherwise.

        ``backend.update`` bypasses ``_validate_update`` by design: that hook reads
        ``priority`` and ``due_date``, neither of which this one-field patch touches.
        """
        if not task.fulfills_goal_uid or written_goal_uid == task.fulfills_goal_uid:
            return task

        cleared = await self.backend.update(task.uid, {"fulfills_goal_uid": None})
        if cleared.is_error:
            self.logger.error(
                "Task %s keeps fulfills_goal_uid=%s with no FULFILLS_GOAL edge behind it — "
                "the clearing write failed: %s",
                task.uid,
                task.fulfills_goal_uid,
                cleared.error,
            )
            return task

        self.logger.warning(
            "Cleared fulfills_goal_uid=%s on task %s: its FULFILLS_GOAL edge was not written",
            task.fulfills_goal_uid,
            task.uid,
        )
        return dataclasses.replace(task, fulfills_goal_uid=None)

    async def _create_validated(self, entity: Task) -> Result[Task]:
        """Persist, publishing NOTHING.

        Split out from ``create`` so ``_create_with_links`` can finish writing the task's
        graph edges before any event announces the task exists — see ``_publish_created``
        for why that ordering is load-bearing. Named for the shape it shares with the other
        five Activity Domains: it is the seam that runs ``_validate_create``, which for
        Tasks resolves to the inherited no-op.
        """
        return await super().create(entity)

    async def _write_hierarchy_edge(
        self, task: Task, parent_uid: str | None, progress_weight: float
    ) -> None:
        """Write (parent)-[:HAS_SUBTASK {progress_weight}]->(task) when the task has a parent.

        ``parent_uid`` is a parameter rather than read off ``task`` because the persisted
        task cannot carry it — see ``_create_with_links``.

        ``Task.parent_uid`` reaches no node property at all: the mapper's
        RELATIONSHIP_SKIP_FIELDS drops it precisely because the hierarchy belongs in the
        graph. Until this write existed on the shared path, only ``create_task`` created
        the edge — so a subtask created through ``POST /api/tasks/create`` had no parent in
        the property AND no parent in the graph, invisible to every hierarchy reader
        (``get_subtasks`` / ``get_parent_task`` / ``get_task_hierarchy`` via
        ``get_children_raw``, and the user-context MEGA-QUERY's HAS_SUBTASK collection).

        OWNERSHIP: the parent must belong to the same user. ``parent_uid`` is
        attacker-controlled request input and ``create_hierarchy_relationship`` matches on
        UID and label alone — no owner filter — so without this check a caller could point
        a new task at ANOTHER user's task and have the edge written. The victim's context
        rebuild starts from the tasks they OWN and traverses HAS_SUBTASK without filtering
        the child's owner, so the attacker's task would surface in the victim's cached
        context. The pre-existing door onto this same write, ``POST /api/tasks/add-child``,
        verifies BOTH endpoints (``_register_add_child_route`` loops over parent and child);
        creation must not be a way around that. Goals' sibling
        ``_write_hierarchy_edge`` makes the same check for the same reason (Codex, #965) —
        Tasks' door was writing this edge unguarded before now.

        A failure is logged, not propagated: the task itself is legitimate and is created
        either way — only the edge is refused.
        """
        if not parent_uid:
            return

        parent_result = await self.get(parent_uid)
        if parent_result.is_error:
            self.logger.warning(
                "Skipping subtask edge for %s: parent %s not found",
                task.uid,
                parent_uid,
            )
            return
        if parent_result.value.user_uid != task.user_uid:
            self.logger.warning(
                "Refusing cross-user subtask edge: task %s (user %s) named parent %s "
                "owned by a different user",
                task.uid,
                task.user_uid,
                parent_uid,
            )
            return

        edge_result = await self.create_subtask_relationship(
            parent_uid=parent_uid,
            subtask_uid=task.uid,
            progress_weight=progress_weight,
        )
        if edge_result.is_error:
            self.logger.warning(
                "Failed to create subtask relationship %s -> %s: %s",
                parent_uid,
                task.uid,
                edge_result.error,
            )

    async def _write_link_edges(
        self, task: Task, habit_uid: str | None, request: TaskCreateRequest | None
    ) -> WrittenLinks:
        """GRAPH-NATIVE: turn the task's cross-domain links into edges, in one batch.

        Six registered relationships, from two sources:

        - ``Task.reinforces_habit_uid`` → REINFORCES_HABIT — from the ENTITY, so BOTH
          doors write it. Passed in as ``habit_uid`` rather than read off ``task``, which
          cannot carry it once persisted (see ``_create_with_links``). Edge-only: the
          mapper's RELATIONSHIP_SKIP_FIELDS keeps the uid off the node, and every reader
          resolves the habit from the edge.
        - ``Task.fulfills_goal_uid`` → FULFILLS_GOAL — from the ENTITY, both doors, read
          off the persisted ``task`` (it is a real node column). DUAL-WRITTEN: the property
          stays, and this edge is written beside it — the same shape as
          ``Exercise.path_step_uid`` + HAS_EXERCISE, and ADR-086's ``user_uid`` + ``:OWNS``.
          The property serves the readers that hold the task in hand (the relevance
          scorer, the completion → goal-progress cascade, the edit form's picker); the
          edge serves every graph reader — the goal's open-task count that gates
          ``cancel_goal``, the goals-for-tasks batch behind daily planning, the
          MEGA-QUERY's ``goal_context`` and ``goal_tasks``, goal-aligned traversals. The
          invariant, held by ``_reconcile_goal_property``: property == edge target,
          wherever both exist — a refused edge clears the property.
        - ``applies_knowledge_uids``   → APPLIES_KNOWLEDGE  (request only)
        - ``prerequisite_knowledge_uids`` → REQUIRES_KNOWLEDGE (request only)
        - ``aligned_principle_uids``   → ALIGNED_WITH_PRINCIPLE (request only)
        - ``prerequisite_task_uids``   → BLOCKED_BY (request only)

        All six are declared ``outgoing`` from the task, so the task is the source of
        every tuple. Edge properties are ``None``, matching the update path's
        ``_sync_relationship_edges``, so a task linked at creation is indistinguishable
        from one linked afterwards.

        ``create_relationships_batch`` validates every tuple against the registry and is
        all-or-nothing — one refused tuple loses every edge in the batch, as a logged
        warning on a create that reports success. That is why every UID is admitted
        first (below) rather than handed to the batch raw.

        ADMISSION: every one of these UIDs is request input, so each is checked for
        existence, OWNER and KIND before it becomes an edge — ``keep_permitted_link_edges``.
        The declared kinds come from the field names: ``reinforces_habit_uid`` means a
        Habit, ``fulfills_goal_uid`` a Goal (goals are OWNER_ONLY, and the goal readers do
        not filter the task's owner — a cross-user edge would count the caller's task in
        another user's goal progress), the knowledge lists mean Kus (KNOWLEDGE_LABELS —
        see there for why the atom and not the PathStep), ``aligned_principle_uids``
        Principles, and ``prerequisite_task_uids`` the caller's own Tasks.

        Returns:
            The edges actually WRITTEN, as ``WrittenLinks`` — the caller announces
            substance and reconciles the goal stamp from these, never from what was
            requested, so a refused or dangling link cannot claim an edge that does not
            exist. Empty when the batch failed: it is all-or-nothing, so NOTHING was
            written.

        A failure is logged, not propagated — the task itself is created.
        """
        candidates: list[LinkEdge] = []

        if habit_uid:
            candidates.append(
                LinkEdge(
                    (
                        task.uid,
                        habit_uid,
                        RelationshipName.REINFORCES_HABIT.value,
                        None,
                    ),
                    other_uid=habit_uid,
                    allowed_labels=frozenset({NeoLabel.HABIT.value}),
                )
            )

        if task.fulfills_goal_uid:
            candidates.append(
                LinkEdge(
                    (
                        task.uid,
                        task.fulfills_goal_uid,
                        RelationshipName.FULFILLS_GOAL.value,
                        None,
                    ),
                    other_uid=task.fulfills_goal_uid,
                    allowed_labels=frozenset({NeoLabel.GOAL.value}),
                )
            )

        if request is not None:
            candidates.extend(
                LinkEdge(
                    (task.uid, knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None),
                    other_uid=knowledge_uid,
                    allowed_labels=KNOWLEDGE_LABELS,
                )
                for knowledge_uid in request.applies_knowledge_uids
            )
            candidates.extend(
                LinkEdge(
                    (task.uid, knowledge_uid, RelationshipName.REQUIRES_KNOWLEDGE.value, None),
                    other_uid=knowledge_uid,
                    allowed_labels=KNOWLEDGE_LABELS,
                )
                for knowledge_uid in request.prerequisite_knowledge_uids
            )
            candidates.extend(
                LinkEdge(
                    (task.uid, principle_uid, RelationshipName.ALIGNED_WITH_PRINCIPLE.value, None),
                    other_uid=principle_uid,
                    allowed_labels=frozenset({NeoLabel.PRINCIPLE.value}),
                )
                for principle_uid in request.aligned_principle_uids
            )
            candidates.extend(
                LinkEdge(
                    (task.uid, prerequisite_uid, RelationshipName.BLOCKED_BY.value, None),
                    other_uid=prerequisite_uid,
                    allowed_labels=frozenset({NeoLabel.TASK.value}),
                )
                for prerequisite_uid in request.prerequisite_task_uids
            )

        if not candidates:
            return WrittenLinks()

        relationships = await keep_permitted_link_edges(
            self.backend,
            candidates=candidates,
            subject_uid=task.uid,
            owner_uid=task.user_uid,
            logger=self.logger,
        )
        if not relationships:
            return WrittenLinks()

        batch_result = await self.backend.create_relationships_batch(relationships)
        if batch_result.is_error:
            self.logger.warning(
                "Failed to create %d link relationships for task %s: %s",
                len(relationships),
                task.uid,
                batch_result.error,
            )
            # The batch is all-or-nothing, so a failure means NOTHING was written.
            # Reporting the admitted uids here would announce substance for edges that
            # do not exist.
            return WrittenLinks()

        return WrittenLinks.from_edges(relationships)

    async def _publish_created(self, task: Task) -> None:
        """Announce a newly created task: TaskCreated, TaskCompleted when it was born
        completed, and the ADR-074 embedding refresh.

        ORDERING: call this only once the task's graph edges are written. ``TaskCreated``
        is subscribed to ``invalidate_context`` (services_bootstrap/_event_wiring.py),
        which debounces 100ms and then rebuilds the user context — and the rebuild reads
        both ``(task)-[:HAS_SUBTASK]->(subtask)`` and ``(task)-[:APPLIES_KNOWLEDGE]->()``
        back out of the graph (adapters/persistence/neo4j/user_context_queries.py).
        Publishing before ``_write_hierarchy_edge`` and ``_write_link_edges``
        finish lets the rebuild observe a task with no
        edges and cache that empty result for the full 300s TTL
        (``UserContext.cache_ttl_seconds``). The later KnowledgeAppliedInTask events are
        wired only to substance handlers and do NOT invalidate the context, so nothing
        corrects it. (Same inversion Codex reported on #960.)
        """
        event = TaskCreated(
            task_uid=task.uid,
            user_uid=task.user_uid,
            title=task.title,
            priority=task.priority or "medium",
            # NOTE: Task domain not stored - could infer from related goal/knowledge
            domain=None,
        )
        await publish_event(self.event_bus, event, self.logger)

        await self._publish_born_completed(task)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.TASK, task, self.logger)

    async def _publish_born_completed(self, task: Task) -> None:
        """Publish ``TaskCompleted`` for a task that was CREATED already completed.

        A DSL ``- [x]`` line and an API create carrying ``status=completed`` both persist
        a task that never passes through ``update_task``, so every ``TaskCompleted``
        subscriber — goal progress, PS engagement auto-complete, duration calibration,
        productivity analytics, context invalidation — used to be skipped for it. A
        create has no prior status, so this is unambiguously a transition INTO completed:
        ``is_repeat`` is False and no prior-status machinery is needed.

        ``occurred_at`` carries the task's own ``completion_date`` (CLAUDE.md's sanctioned
        case: a derived event about a source occurrence), so an ingested historical ``✅``
        date reports the day it happened rather than the ingest moment.

        ``was_overdue`` is measured against that same completion moment, not against
        today: the update chokepoint compares to ``date.today()`` because there the two
        are the same day, while here a backfilled task completed on time in March would
        otherwise be announced overdue purely because March is now in the past — and the
        overdue branch APPENDS a ``PersistedInsight`` (``TaskEventHandlerService``).
        """
        if task.status is not EntityStatus.COMPLETED:
            return

        completed_at = completion_moment(task.completion_date)
        await publish_event(
            self.event_bus,
            TaskCompleted(
                task_uid=task.uid,
                user_uid=task.user_uid,
                completion_time_seconds=(
                    task.actual_minutes * 60 if task.actual_minutes is not None else None
                ),
                was_overdue=task.due_date < completed_at.date() if task.due_date else False,
                is_repeat=False,
                occurred_at=completed_at,
            ),
            self.logger,
        )

    async def _publish_knowledge_substance(self, task: Task, knowledge_uids: list[str]) -> None:
        """Announce applied knowledge: single-item for 1 Ku, bulk for 2+.

        Driven by the uids ``_write_link_edges`` actually WROTE, never by what the request
        asked for. The substance pipeline credits knowledge per uid it is handed, so
        announcing a refused, dangling or cross-user link would claim a task applied
        knowledge that no APPLIES_KNOWLEDGE edge backs. (Habits' sibling, #965.)

        Published AFTER ``TaskCreated``, as before: these reach only substance handlers
        and do not invalidate the user context, so they carry no ordering constraint of
        their own — but they must not precede the announcement of the task they describe.
        """
        if not knowledge_uids:
            return

        from core.events.knowledge_substance_events import (
            KnowledgeAppliedInTask,
            KnowledgeBulkAppliedInTask,
        )

        knowledge_event: KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask
        if len(knowledge_uids) == 1:
            knowledge_event = KnowledgeAppliedInTask(
                knowledge_uid=knowledge_uids[0],
                task_uid=task.uid,
                user_uid=task.user_uid,
                task_title=task.title,
                task_priority=task.priority or "medium",
            )
        else:
            knowledge_event = KnowledgeBulkAppliedInTask(
                knowledge_uids=tuple(knowledge_uids),
                task_uid=task.uid,
                user_uid=task.user_uid,
                task_title=task.title,
                task_priority=task.priority or "medium",
            )
        await publish_event(self.event_bus, knowledge_event, self.logger)

    @with_error_handling("create_task", error_type="database")
    async def create_task(self, task_request: TaskCreateRequest, user_uid: UserUID) -> Result[Task]:
        """
        Create a task with automatic knowledge inference.

        Builds the entity, then hands it to the one create primitive. ``progress_weight``
        and the request's four link lists (two knowledge, principles, prerequisite tasks)
        are forwarded because only this door has the request: all five are EDGE-shaped,
        so none rides an entity and the entity door cannot carry them. Since the
        generated route was bound here, every external create comes through this door.
        The HAS_SUBTASK, REINFORCES_HABIT and FULFILLS_GOAL edges, whose endpoints DO ride
        on the entity, are written by the shared path for both doors — writing them here
        as well would double-write them.

        Args:
            task_request: Task creation request
            user_uid: User UID (REQUIRED - fail-fast on None)

        Returns:
            Result containing created Task with knowledge enhancement
        """
        # Validate user_uid (uses BaseService helper)
        validation = self._validate_required_user_uid(user_uid, "task creation")
        if validation.is_error:
            return Result.fail(validation)

        # Build a frozen Task from the request and apply inference enrichment
        # functionally (ADR-065 — typed TaskInferenceResult, no DTO mutation
        # inside intelligence services).
        task_draft = Task.from_request(task_request, user_uid=user_uid)

        if self.ku_inference_service:
            inference_result = self._enhance_with_knowledge_inference(task_draft)
            if inference_result.is_error:
                return Result.fail(inference_result)
            enrichment = inference_result.value
            if enrichment is not None:
                task_draft = dataclasses.replace(task_draft, **enrichment.as_kwargs())

        result = await self._create_with_links(
            task_draft,
            progress_weight=task_request.progress_weight,
            request=task_request,
        )
        if result.is_error:
            return result

        # Log creation with knowledge enhancement
        explicit_knowledge_count = len(task_request.applies_knowledge_uids) + len(
            task_request.prerequisite_knowledge_uids
        )

        self.logger.info(
            "Created task '%s' with knowledge enhancement: explicit=%d",
            result.value.title,
            explicit_knowledge_count,
        )

        return result

    # ========================================================================
    # READ OPERATIONS
    # ========================================================================

    async def get_task(self, task_uid: str) -> Result[Task]:
        """
        Get a specific task by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            task_uid: Task UID

        Returns:
            Result[Task] - success contains Task, not found is an error
        """
        return await self.get(task_uid)

    @with_error_handling("get_user_tasks", error_type="database", uid_param="user_uid")
    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """
        Get all tasks for a user, including learning relationships.

        Args:
            user_uid: User UID

        Returns:
            Result containing list of Tasks
        """
        result = await self.backend.get_user_entities(user_uid)
        if result.is_error:
            return Result.fail(result)

        # Unpack tuple (entities, total_count) from get_user_entities
        entities, _total = result.value

        # Convert to enriched Task models
        tasks = [self._to_domain_model(task_data, TaskDTO, Task) for task_data in entities]

        self.logger.debug(f"Retrieved {len(tasks)} tasks for user {user_uid}")
        return Result.ok(tasks)

    async def list_tasks(self, filters: dict | None = None, limit: int = 100) -> Result[list[Task]]:
        """
        List tasks with optional filters.

        Uses BaseService.list() which delegates to BackendOperations.list().

        Args:
            filters: Optional filter criteria,
            limit: Maximum number of tasks to return

        Returns:
            Result containing list of Tasks
        """
        result = await self.list(limit=limit, filters=filters)
        if result.is_error:
            return Result.fail(result)
        # list() returns (items, total_count) tuple
        items, _ = result.value
        return Result.ok(items)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 40 lines of duplicate code

    # ========================================================================
    # UPDATE OPERATIONS
    # ========================================================================

    @with_error_handling("update_task", error_type="database", uid_param="task_uid")
    async def update_task(self, task_uid: str, intent: TaskUpdateIntent) -> Result[Task]:
        """
        Update a task's node properties (ADR-066 typed update contract).

        The intent is materialized to a partial patch and written exactly once, at the
        single ``backend.update`` seam. Relationship-typed fields (habit / knowledge
        edges) are split off by the facade and never reach this method as properties.
        The domain rule (``_validate_update`` — overdue-priority protection) runs here,
        explicitly: the facade routes the generic CRUD to this method, so the inherited
        hook never fires for Tasks (cascade-idempotency arc, correction #14).
        Status transitions are validated against the Task lifecycle and completion
        stamping (``completion_date``) is applied here — the domain's one update
        chokepoint (``core.services.completion_stamp``). A transition INTO
        completed also publishes ``TaskCompleted`` (always ``is_repeat=False`` —
        the gate is the transition), so completing a task from the status
        control runs the same cascade as the explicit-complete doors, and the
        mirror transition OUT of completed publishes ``TaskReopened``.

        Both verdicts are derived from the status the WRITE observed under the node's
        lock, not from a status read beforehand (ADR-087). That closes the vector this
        door is most exposed to: Today's Undo posts its reopen through here while the
        complete may still be in flight, and under the old read-then-write shape a
        complete serialized after a reopen could see a stale "already completed" prior
        and write ``status=completed`` with no stamp — breaking the invariant that the
        stamp is non-null exactly when the task is completed.

        Args:
            task_uid: Task UID,
            intent: Typed ``TaskUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Task
        """
        changes = intent.to_changes()
        # The event reports what the update meant to change, so name the intended fields
        # rather than anything the write adds (the backend stamps updated_at onto its own
        # copy of the patch, and the completion stamp now rides the guard, not ``changes``).
        updated_fields = list(changes.keys())

        # Advisory pre-read — for the overdue-priority rule and the priority-change event
        # only. The status verdicts used to need it too; they now come from the write
        # itself, so a status-only update reads nothing before writing.
        old_task = None
        if "priority" in changes:
            old_result = await self.backend.get(task_uid)
            if old_result.is_error:
                # Fail fast: a failed read must not be silently read as "no rule applies"
                # — the overdue-priority rule below is gated on the prior priority/due_date.
                return Result.fail(old_result)
            if old_result.value:
                old_task = self._to_domain_model(old_result.value, TaskDTO, Task)

        # Domain validation BEFORE the write. Called explicitly because the facade
        # routes ``update`` / ``update_for_user`` to this method, so the inherited CRUD
        # hook that would otherwise run it is unreachable for Tasks — the reason its one
        # rule was dead until now (cascade-idempotency arc, correction #14). Only a
        # priority change can fail it, and ``old_task`` is in hand for exactly that case.
        if old_task is not None:
            validation = self._validate_update(old_task, intent)
            if validation.is_error:
                return Result.fail(validation)

        # Status-target validation + completion stamping, expressed as conditions the
        # WRITE evaluates against the prior it reads under the node's lock (ADR-087).
        # The refusal on an illegal status target is the same one the Python-side helper
        # made; what changed is that the stamp decision is no longer taken from a status
        # a concurrent writer may already have moved.
        guard = status_transition_guard(EntityType.TASK, changes)
        if guard.is_error:
            return Result.fail(guard)

        update_result = await self.backend.update_with_status_guard(task_uid, changes, guard.value)
        if update_result.is_error:
            return Result.fail(update_result)

        # This guard refuses nothing (``refuse_if_prior_in`` is empty), so the write
        # always applied; only the prior it returned is news.
        outcome = update_result.value
        task = self._to_domain_model(outcome.entity, TaskDTO, Task)

        # The verdicts, from the status the write actually saw. The same two pure helpers
        # as before — only their ``old_status`` argument is now exact.
        is_transition = is_completion_transition(outcome.prior_status, changes)
        is_reopen = is_reopen_transition(outcome.prior_status, changes)

        # Publish TaskUpdated event
        event = TaskUpdated(
            task_uid=task.uid,
            user_uid=task.user_uid,
            updated_fields=updated_fields,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish TaskCompleted when this update is a genuine transition INTO
        # completed. The status chokepoint (POST /api/tasks/{uid}/status) is a
        # real completion door and used to publish TaskUpdated only, so every
        # TaskCompleted subscriber — goal progress, PS engagement auto-complete,
        # duration calibration, analytics, context invalidation — was silently
        # skipped for tasks completed from a status control.
        #
        # ``is_repeat`` is always False here: the gate IS the transition, so a
        # re-post of ``completed`` never reaches this publish (unlike the
        # explicit-complete doors, which deliberately re-run their cascade as a
        # repair path and report the repeat). See TaskCompleted's docstring.
        #
        # Zero extra queries: the prior comes back from the write itself, and the
        # post-write ``task`` carries due_date/actual_minutes.
        if is_transition:
            completed_event = TaskCompleted(
                task_uid=task.uid,
                user_uid=task.user_uid,
                completion_time_seconds=(
                    task.actual_minutes * 60 if task.actual_minutes is not None else None
                ),
                was_overdue=task.due_date < date.today() if task.due_date else False,
                is_repeat=False,
            )
            await publish_event(self.event_bus, completed_event, self.logger)

        # Publish TaskReopened on the mirror transition — OUT of completed.
        # This chokepoint is the only door that reopens a task (Today's Undo
        # posts the prior status through it), and without a signal here the
        # productivity counter could only ever go up: a complete → Undo →
        # complete sequence is two genuine transitions INTO completed, so an
        # increment would count one task twice. The subscriber recomputes the
        # count from the graph instead, and this is what tells it to.
        if is_reopen:
            await publish_event(
                self.event_bus,
                TaskReopened(task_uid=task.uid, user_uid=task.user_uid),
                self.logger,
            )

        # Publish TaskPriorityChanged event if priority changed
        if "priority" in changes and old_task and old_task.priority != task.priority:
            from core.events import TaskPriorityChanged

            priority_event = TaskPriorityChanged(
                task_uid=task.uid,
                user_uid=task.user_uid,
                old_priority=old_task.priority or "medium",
                new_priority=task.priority or "medium",
                escalated_to_urgent=(
                    Priority(task.priority).to_numeric() == 4 if task.priority else False
                ),  # CRITICAL = 4
            )
            await publish_event(self.event_bus, priority_event, self.logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.TASK, task, self.logger, changed_fields=updated_fields
        )

        return Result.ok(task)

    @with_error_handling("complete_tasks_bulk", error_type="database")
    async def complete_tasks_bulk(self, task_uids: list[str], user_uid: UserUID) -> Result[int]:
        """
        Complete multiple tasks in a batch operation.

        Publishes ``TaskCompleted`` per row for the rows that actually
        transitioned, plus one ``TasksBulkCompleted`` for the batch. "Actually
        transitioned" is decided by each row's own write, from the status it
        captured under that node's lock (ADR-087) — so a row completed by another
        writer between this call's start and its write is reported as the re-post
        it is, not as a completion this batch made.

        Args:
            task_uids: List of task UIDs to complete
            user_uid: User UID (for event publishing)

        Returns:
            Result containing count of tasks completed
        """
        # raw-write: deliberate backend-boundary bulk status flip. This bypasses the
        # validated/event-firing service contract (TaskUpdateIntent → update_task) on
        # purpose — it is a system batch write, so it names the patch it sends rather
        # than materializing an intent for it.
        #
        # It does NOT bypass the cascade: every door to COMPLETED cascades, so the
        # rows that genuinely transition fan out one TaskCompleted each (ruled
        # 2026-08-22). TasksBulkCompleted stays alongside them because its handler
        # classifies the *batch* (size + time of day), which per-row events cannot
        # express. Rows that were already completed publish nothing — not a repeat
        # flag: a bulk call is not a repair path, and a re-post is not a completion.
        written_uids: list[str] = []
        completion_events: list[TaskCompleted] = []

        # Every row gets the same patch and therefore the same guard, so both are
        # built once: the stamp conditions are a property of the TARGET status, which
        # is constant across the batch, and one build means one date for the batch
        # rather than a per-row ``date.today()`` that could straddle midnight. An
        # illegal target would fail identically for every row, so it fails the call.
        updates: Neo4jProperties = {"status": EntityStatus.COMPLETED.value}
        guard = status_transition_guard(EntityType.TASK, updates)
        if guard.is_error:
            return Result.fail(guard)

        for task_uid in task_uids:
            # The transition gate is evaluated by the WRITE, against the status it
            # captures under the node's lock (ADR-087) — a bulk list may contain
            # already-completed tasks (retry, mixed selection) whose original
            # completion_date must survive, and the pre-read this loop used to do
            # could be stale by the time the write landed. A row that cannot be
            # written — not found, or a transient failure — is skipped and not
            # counted, exactly as an unreadable row was.
            result = await self.backend.update_with_status_guard(task_uid, updates, guard.value)
            if result.is_error:
                continue

            # The guard refuses nothing, so a row that was written is a row that
            # applied; ``outcome.entity`` is the post-write node, and the patch
            # touches status + stamp only, so it still carries this row's
            # due_date / actual_minutes.
            outcome = result.value
            written_uids.append(task_uid)
            if not is_completion_transition(outcome.prior_status, updates):
                continue

            task = self._to_domain_model(outcome.entity, TaskDTO, Task)
            completion_events.append(
                TaskCompleted(
                    task_uid=task_uid,
                    user_uid=user_uid,
                    completion_time_seconds=(
                        task.actual_minutes * 60 if task.actual_minutes is not None else None
                    ),
                    was_overdue=(task.due_date < date.today() if task.due_date else False),
                    is_repeat=False,
                )
            )

        # Fan out after every write lands, so a subscriber never reads the graph
        # mid-batch.
        for completion_event in completion_events:
            await publish_event(self.event_bus, completion_event, self.logger)

        # Publish TasksBulkCompleted event. The uids are the rows that were
        # actually written — the former ``task_uids[:completed_count]`` slice
        # named the wrong rows whenever a row in the middle was skipped.
        if written_uids:
            from core.events import TasksBulkCompleted

            event = TasksBulkCompleted(
                task_uids=written_uids,
                user_uid=user_uid,
            )
            await publish_event(self.event_bus, event, self.logger)

        return Result.ok(len(written_uids))

    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================

    @with_error_handling("delete_task", error_type="database", uid_param="task_uid")
    async def delete_task(self, task_uid: str) -> Result[bool]:
        """
        Delete a task.

        Args:
            task_uid: Task UID

        Returns:
            Result indicating success
        """
        # Get task details before deletion for event publishing
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result)

        task_data = task_result.value
        user_uid = (
            task_data.get("user_uid")
            if isinstance(task_data, dict)
            else getattr(task_data, "user_uid", None)
        )

        result = await self.backend.delete(task_uid, cascade=True)

        # Publish TaskDeleted event if deletion succeeded
        if result.is_ok:
            event = TaskDeleted(task_uid=task_uid, user_uid=UserUID(str(user_uid or "")))
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to TasksBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subtask_relationship(
        self, parent_uid: str, subtask_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBTASK/SUBTASK_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subtask_uid, {"progress_weight": progress_weight}
        )

    async def remove_subtask_relationship(self, parent_uid: str, subtask_uid: str) -> Result[bool]:
        """Remove bidirectional HAS_SUBTASK/SUBTASK_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subtask_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[TaskStats]:
        """Count task stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.

    async def calculate_parent_progress(self, parent_uid: str) -> Result[ParentProgressResult]:
        """Calculate parent task progress based on weighted subtask completion."""
        return await self.backend.calculate_parent_progress(parent_uid)
