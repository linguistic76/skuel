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

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.events import TaskCompleted, TaskCreated, TaskDeleted, TaskUpdated, publish_event
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
from core.services.completion_stamp import completion_transition_patch, is_completion_transition
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.services.mixins.link_edge_guard import (
    KNOWLEDGE_LABELS,
    LinkEdge,
    keep_permitted_link_edges,
)
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

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
        Validate task updates with business rules.

        Business Rules:
        1. Terminal state protection: Cannot modify completed/cancelled/archived tasks
        2. Overdue task protection: Cannot decrease priority of overdue tasks

        Args:
            current: Current task state
            updates: Typed ``TaskUpdateIntent`` of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        changes = updates.to_changes()
        # Business Rule 1: Terminal state protection
        # Prevent modification of tasks in terminal states (preserves historical accuracy)
        if current.status.is_terminal():
            return Result.fail(
                Errors.validation(
                    message=f"Cannot modify tasks in {current.status.value} state",
                    field="status",
                    value=current.status.value,
                )
            )

        # Business Rule 2: Overdue task priority protection
        # Cannot decrease priority of overdue tasks (prevents "sweeping under rug")
        if "priority" in changes and current.due_date and current.due_date < date.today():
            new_priority = Priority(changes["priority"])
            current_numeric = Priority(current.priority).to_numeric() if current.priority else 2
            if new_priority.to_numeric() < current_numeric:
                return Result.fail(
                    Errors.validation(
                        message="Cannot decrease priority of overdue tasks",
                        field="priority",
                        value=new_priority.value,
                    )
                )

        return Result.ok(None)  # All validations passed

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
        validation to reach here. What this primitive reconciles is the EVENT half — and,
        since #966, the two ENTITY-CARRIED links below.

        ``parent_uid`` and ``reinforces_habit_uid`` are written here rather than in
        ``create_task`` because both ride on the Task, so both doors can write them.
        Leaving them on the request door alone is what made ``POST /api/tasks/create``
        lose them entirely: the mapper skips ``parent_uid``, so a subtask created through
        the API had no parent at ALL, and ``reinforces_habit_uid`` landed as a node
        property no reader consults instead of an edge (both measured 2026-08-05).

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
        cost a RED test: BOTH of Tasks' entity-carried links are RELATIONSHIP_SKIP_FIELDS,
        so they DO NOT SURVIVE THE ROUND-TRIP. ``backend.create`` returns
        ``from_neo4j_node(props, Task)`` over the properties it wrote, and the mapper
        dropped these two on the way in — so ``result.value.parent_uid`` is always None.
        They are read off the INPUT entity and passed down explicitly. Goals is not a
        guide here: ``Goal.fulfills_goal_uid`` is a real node column, so its round-trip
        keeps it.
        """
        result: Result[Task] = await self._create_validated(entity)
        if result.is_error:
            return result

        task: Task = result.value
        await self._write_hierarchy_edge(task, entity.parent_uid, progress_weight)
        written_knowledge_uids = await self._write_link_edges(
            task, entity.reinforces_habit_uid, request
        )

        # Every edge is written — only now announce the task.
        await self._publish_created(task)
        await self._publish_knowledge_substance(task, written_knowledge_uids)
        return result

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
    ) -> list[str]:
        """GRAPH-NATIVE: turn the task's cross-domain links into edges, in one batch.

        Five registered relationships, from two different sources:

        - ``Task.reinforces_habit_uid`` → REINFORCES_HABIT — from the ENTITY, so BOTH
          doors write it. Passed in as ``habit_uid`` rather than read off ``task``,
          which cannot carry it once persisted (see ``_create_with_links``). The route
          converter was setting this field and the mapper was
          persisting it as a node PROPERTY, which no reader consults: every reader of the
          name resolves it from the edge (``get_habit_links_for_tasks`` for Tasks, the
          registry's ``habit_context``). It is now skipped by the mapper and written here.
        - ``applies_knowledge_uids``   → APPLIES_KNOWLEDGE  (request only)
        - ``prerequisite_knowledge_uids`` → REQUIRES_KNOWLEDGE (request only)
        - ``aligned_principle_uids``   → ALIGNED_WITH_PRINCIPLE (request only)
        - ``prerequisite_task_uids``   → BLOCKED_BY (request only)

        All five are declared ``outgoing`` from the task, so the task is the source of
        every tuple. Edge properties are ``None``, matching both the pre-existing create
        writes and the update path's ``_sync_relationship_edges``, so a task linked at
        creation is indistinguishable from one linked afterwards.

        The last two joined when ``create_task_with_context`` was routed through this
        primitive: ``create_task`` had silently DROPPED both request lists, and the
        context door — the one writer they had — spelled the principle edge with the
        raw string ``"ALIGNED_WITH"``, a name the relationship registry does not know.
        ``create_relationships_batch`` validates every tuple against the registry and
        is all-or-nothing, so any request naming a principle lost its habit, knowledge
        and prerequisite-task edges along with it, as a logged warning on a create that
        reported success. Every reader resolves principles from ALIGNED_WITH_PRINCIPLE
        (the user-context MEGA-QUERY, the registry's ``aligned_principles``).

        ADMISSION: every one of these UIDs is request input, so each is checked for
        existence, OWNER and KIND before it becomes an edge — see
        ``keep_permitted_link_edges``. The knowledge lists were previously written
        unguarded, which #965 recorded as the same defect class it fixed for Goals and
        Habits; they are guarded here because they share this batch. The declared labels
        come from the field names: ``reinforces_habit_uid`` means a Habit, the knowledge
        lists mean Kus (KNOWLEDGE_LABELS — see there for why the atom and not the
        PathStep), ``aligned_principle_uids`` means Principles, and
        ``prerequisite_task_uids`` means the caller's own Tasks.

        Returns:
            The APPLIES_KNOWLEDGE uids actually WRITTEN — the caller announces substance
            from these, never from what was requested, so a refused or dangling link
            cannot claim knowledge was applied when no edge exists.

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
            return []

        relationships = await keep_permitted_link_edges(
            self.backend,
            candidates=candidates,
            subject_uid=task.uid,
            owner_uid=task.user_uid,
            logger=self.logger,
        )
        if not relationships:
            return []

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
            return []

        # DEDUPED: the batch MERGEs, so a UID repeated in the request yields ONE edge —
        # but the bulk substance event UNWINDs what it is given, crediting the knowledge
        # once per row. dict.fromkeys keeps the order. (Habits' sibling, #965.)
        return list(
            dict.fromkeys(
                target_uid
                for _src, target_uid, rel_type, _props in relationships
                if rel_type == RelationshipName.APPLIES_KNOWLEDGE.value
            )
        )

    async def _publish_created(self, task: Task) -> None:
        """Announce a newly created task: TaskCreated + the ADR-074 embedding refresh.

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

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.TASK, task, self.logger)

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
        generated route was bound here, every external create comes through this door. The HAS_SUBTASK
        and REINFORCES_HABIT edges, whose endpoints DO ride on the entity, are written by
        the shared path for both doors — writing them here as well would double-write
        them.

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

        The intent is materialized to a partial patch exactly once, at the single
        ``backend.update`` seam. Relationship-typed fields (habit / knowledge edges)
        are split off by the facade and never reach this method as properties.
        Status transitions are validated against the Task lifecycle and completion
        stamping (``completion_date``) is applied here — the domain's one update
        chokepoint (``core.services.completion_stamp``). A transition INTO
        completed also publishes ``TaskCompleted`` (always ``is_repeat=False`` —
        the gate is the transition), so completing a task from the status
        control runs the same cascade as the explicit-complete doors.

        Args:
            task_uid: Task UID,
            intent: Typed ``TaskUpdateIntent`` — only its set fields are written

        Returns:
            Result containing updated Task
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend mutates its argument in place
        # (stamps updated_at), so reading changes.keys() after the call would leak that
        # bump into the event. The event reports what the update meant to change.
        updated_fields = list(changes.keys())

        # Fetch the prior task when a transition needs old-vs-new (priority change
        # event, completion-stamp gating).
        old_task = None
        if "priority" in changes or "status" in changes:
            old_result = await self.backend.get(task_uid)
            if old_result.is_error and "status" in changes:
                # Fail fast: the stamp is transition-gated on the prior status, and a
                # failed read must not be read as "not completed" — a transient error
                # plus a completed re-post would re-date the original stamp.
                return Result.fail(old_result)
            if old_result.is_ok and old_result.value:
                old_task = self._to_domain_model(old_result.value, TaskDTO, Task)

        # Status-target validation + completion stamping (transition-gated).
        # The transition is decided ONCE, before the write, and feeds two
        # consumers: the stamp below and the TaskCompleted publish at the end of
        # this method. Deciding it here also keeps it honest — ``changes`` is
        # mutated by the stamp merge and again by the backend (updated_at).
        old_status = old_task.status if old_task else None
        is_transition = is_completion_transition(old_status, changes)
        stamp = completion_transition_patch(EntityType.TASK, old_status, changes)
        if stamp.is_error:
            return Result.fail(stamp)
        changes.update(stamp.value)

        update_result = await self.backend.update(task_uid, changes)
        if update_result.is_error:
            return Result.fail(update_result)

        # Convert updated result to Task
        task = self._to_domain_model(update_result.value, TaskDTO, Task)

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
        # Zero extra queries: ``old_task`` was already fetched for the stamp
        # gate, and the post-write ``task`` carries due_date/actual_minutes.
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
        transitioned, plus one ``TasksBulkCompleted`` for the batch.

        Args:
            task_uids: List of task UIDs to complete
            user_uid: User UID (for event publishing)

        Returns:
            Result containing count of tasks completed
        """
        # raw-write: deliberate backend-boundary bulk status flip. This bypasses the
        # validated/event-firing service contract (TaskUpdateIntent → update_task) on
        # purpose — it is a system batch write. A plain dict literal is the honest
        # type here.
        #
        # It does NOT bypass the cascade: every door to COMPLETED cascades, so the
        # rows that genuinely transition fan out one TaskCompleted each (ruled
        # 2026-08-22). TasksBulkCompleted stays alongside them because its handler
        # classifies the *batch* (size + time of day), which per-row events cannot
        # express. Rows that were already completed publish nothing — not a repeat
        # flag: a bulk call is not a repair path, and a re-post is not a completion.
        written_uids: list[str] = []
        completion_events: list[TaskCompleted] = []

        for task_uid in task_uids:
            # Transition-gate the stamp per row via the shared helper: a bulk list
            # may contain already-completed tasks (retry, mixed selection) whose
            # original completion_date must survive — unconditional stamping is the
            # re-dating bug this arc removes. A row whose state cannot be read is
            # skipped (not counted): a failed read must not pass as "not completed".
            current_result = await self.backend.get(task_uid)
            if current_result.is_error:
                continue
            old_task = None
            if current_result.value:
                old_task = self._to_domain_model(current_result.value, TaskDTO, Task)

            updates: dict[str, Any] = {"status": EntityStatus.COMPLETED.value}
            old_status = old_task.status if old_task else None
            is_transition = is_completion_transition(old_status, updates)
            stamp = completion_transition_patch(EntityType.TASK, old_status, updates)
            if stamp.is_ok:
                updates.update(stamp.value)

            result = await self.backend.update(task_uid, updates)
            if result.is_ok:
                written_uids.append(task_uid)
                if is_transition:
                    # The pre-update read is the only source for these two: the
                    # bulk write touches status + stamp only, so old_task still
                    # describes the row's due_date / actual_minutes.
                    completion_events.append(
                        TaskCompleted(
                            task_uid=task_uid,
                            user_uid=user_uid,
                            completion_time_seconds=(
                                old_task.actual_minutes * 60
                                if old_task is not None and old_task.actual_minutes is not None
                                else None
                            ),
                            was_overdue=(
                                old_task.due_date < date.today()
                                if old_task is not None and old_task.due_date
                                else False
                            ),
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
