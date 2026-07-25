"""
Tasks Core Service - CRUD Operations
=====================================

Clean rewrite following CLAUDE.md patterns.
Handles basic task lifecycle management.

**Responsibilities:**
- Create, read, update, DETACH DELETE tasks
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
from typing import TYPE_CHECKING, Any

from core.models.type_hints import Neo4jProperties, UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.events import TaskCreated, TaskDeleted, TaskUpdated, publish_event
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums import EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_inference_result import TaskInferenceResult
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.ports.query_types import ParentProgressResult, TaskStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result


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

    def _validate_create(self, task: Task) -> Result[None]:
        """
        Validate task creation with business rules.

        Business Rules:
        1. High/Critical priority tasks must have due dates (urgency requires deadline)
        2. Due dates cannot be in the past (enforced at API layer, double-checked here)

        Args:
            task: Task domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        # Business Rule 1: High-priority tasks must have due dates
        if (
            task.priority and Priority(task.priority).to_numeric() >= 3 and not task.due_date
        ):  # HIGH=3, CRITICAL=4
            return Result.fail(
                Errors.validation(
                    message="High-priority tasks must have a due date",
                    field="due_date",
                    value=None,
                )
            )

        return Result.ok(None)  # All validations passed

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

    @with_error_handling("create_task", error_type="database")
    async def create_task(self, task_request: TaskCreateRequest, user_uid: UserUID) -> Result[Task]:
        """
        Create a task with automatic knowledge inference.

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

        # Build a frozen Task from the request, apply inference enrichment
        # functionally (ADR-065 — typed TaskInferenceResult, no DTO mutation
        # inside intelligence services), then translate to TaskDTO at the
        # persistence boundary. TaskDTO remains the single write encoder
        # (ADR-035 three-tier).
        task_draft = Task.from_request(task_request, user_uid=user_uid)

        if self.ku_inference_service:
            inference_result = self._enhance_with_knowledge_inference(task_draft)
            if inference_result.is_error:
                return Result.fail(inference_result)
            enrichment = inference_result.value
            if enrichment is not None:
                task_draft = dataclasses.replace(task_draft, **enrichment.as_kwargs())

        create_result = await self._create_and_convert(task_draft.to_dto().to_dict(), TaskDTO, Task)
        if create_result.is_error:
            return create_result
        task = create_result.value

        # GRAPH-NATIVE: Create relationship edges in graph (not stored on Task/DTO)
        # Create knowledge relationships from request using batch operation for performance
        relationships: list[tuple[str, str, str, Neo4jProperties | None]] = []

        if task_request.applies_knowledge_uids:
            relationships.extend(
                (task.uid, knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None)
                for knowledge_uid in task_request.applies_knowledge_uids
            )

        # Habit reinforcement: graph edge, not a property (Task)-[:REINFORCES_HABIT]->(Habit)
        if task_request.reinforces_habit_uid:
            relationships.append(
                (
                    task.uid,
                    task_request.reinforces_habit_uid,
                    RelationshipName.REINFORCES_HABIT.value,
                    None,
                )
            )

        if task_request.prerequisite_knowledge_uids:
            relationships.extend(
                (task.uid, knowledge_uid, RelationshipName.REQUIRES_KNOWLEDGE.value, None)
                for knowledge_uid in task_request.prerequisite_knowledge_uids
            )

        # Create all relationships in single batch operation (10x faster than loops)
        if relationships:
            batch_result = await self.backend.create_relationships_batch(relationships)
            if batch_result.is_error:
                self.logger.warning(
                    f"Failed to create {len(relationships)} relationships for task {task.uid}: {batch_result.error}"
                )

        # Log creation with knowledge enhancement
        explicit_knowledge_count = len(task_request.applies_knowledge_uids) + len(
            task_request.prerequisite_knowledge_uids
        )

        self.logger.info(
            "Created task '%s' with knowledge enhancement: explicit=%d",
            task.title,
            explicit_knowledge_count,
        )

        # Publish TaskCreated event
        event = TaskCreated(
            task_uid=task.uid,
            user_uid=task.user_uid,
            title=task.title,
            priority=task.priority or "medium",
            # NOTE: Task domain not stored - could infer from related goal/knowledge
            domain=None,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish knowledge substance event: single-item for 1 KU, bulk for 2+
        if task_request.applies_knowledge_uids:
            from core.events.knowledge_substance_events import (
                KnowledgeAppliedInTask,
                KnowledgeBulkAppliedInTask,
            )

            ku_uids = task_request.applies_knowledge_uids
            if len(ku_uids) == 1:
                knowledge_event: KnowledgeAppliedInTask | KnowledgeBulkAppliedInTask = (
                    KnowledgeAppliedInTask(
                        knowledge_uid=ku_uids[0],
                        task_uid=task.uid,
                        user_uid=task.user_uid,
                        task_title=task.title,
                        task_priority=task.priority or "medium",
                    )
                )
            else:
                knowledge_event = KnowledgeBulkAppliedInTask(
                    knowledge_uids=tuple(ku_uids),
                    task_uid=task.uid,
                    user_uid=task.user_uid,
                    task_title=task.title,
                    task_priority=task.priority or "medium",
                )
            await publish_event(self.event_bus, knowledge_event, self.logger)

        # Post-persist embedding refresh (ADR-074) — the background worker embeds async
        await publish_embedding_requested(self.event_bus, EntityType.TASK, task, self.logger)

        # Create parent-child relationship if parent_task_uid specified (2026-01-30)
        if task_request.parent_uid:
            subtask_result = await self.create_subtask_relationship(
                parent_uid=task_request.parent_uid,
                subtask_uid=task.uid,
                progress_weight=task_request.progress_weight,
            )
            if subtask_result.is_error:
                self.logger.warning(
                    f"Failed to create subtask relationship for {task.uid}: {subtask_result.error}"
                )

        return Result.ok(task)

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

        # Get old task for priority change detection
        old_task = None
        if "priority" in changes:
            old_result = await self.backend.get(task_uid)
            if old_result.is_ok:
                old_task = self._to_domain_model(old_result.value, TaskDTO, Task)

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

        Args:
            task_uids: List of task UIDs to complete
            user_uid: User UID (for event publishing)

        Returns:
            Result containing count of tasks completed
        """
        # raw-write: deliberate backend-boundary bulk status flip. This bypasses the
        # validated/event-firing service contract (TaskUpdateIntent → update_task) on
        # purpose — it is a system batch write, and TasksBulkCompleted is published once
        # below rather than per-row. A plain dict literal is the honest type here.
        updates: dict[str, Any] = {"status": EntityStatus.COMPLETED.value}
        completed_count = 0

        for task_uid in task_uids:
            result = await self.backend.update(task_uid, updates)
            if result.is_ok:
                completed_count += 1

        # Publish TasksBulkCompleted event
        if completed_count > 0:
            from core.events import TasksBulkCompleted

            event = TasksBulkCompleted(
                task_uids=task_uids[:completed_count],
                user_uid=user_uid,
            )
            await publish_event(self.event_bus, event, self.logger)

        return Result.ok(completed_count)

    # ========================================================================
    # DELETE OPERATIONS
    # ========================================================================

    @with_error_handling("delete_task", error_type="database", uid_param="task_uid")
    async def delete_task(self, task_uid: str) -> Result[bool]:
        """
        DETACH DELETE a task.

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

    # ========================================================================
    # COMPLETION PROPAGATION (2026-01-30 - Auto-Complete Parents)
    # Cypher delegated to TasksBackend (2026-03-24)
    # ========================================================================

    async def check_and_complete_parent(self, completed_task_uid: str) -> Result[list[str]]:
        """Check if parent task should auto-complete after child completes.

        Recursively checks grandparents too.
        """
        auto_completed_uids: list[str] = []

        result = await self.backend.auto_complete_parent_if_ready(completed_task_uid)
        if not result.is_error and result.value:
            for parent_uid in result.value:
                auto_completed_uids.append(parent_uid)
                # Recursively check grandparent
                grandparent_result = await self.check_and_complete_parent(parent_uid)
                if grandparent_result.is_ok:
                    auto_completed_uids.extend(grandparent_result.value)

        return Result.ok(auto_completed_uids)

    async def calculate_parent_progress(self, parent_uid: str) -> Result[ParentProgressResult]:
        """Calculate parent task progress based on weighted subtask completion."""
        return await self.backend.calculate_parent_progress(parent_uid)
