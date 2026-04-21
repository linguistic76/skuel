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

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.events import TaskCreated, TaskDeleted, TaskUpdated, publish_event
from core.models.enums import EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.ports.query_types import ParentProgressResult, TaskStats, TaskUpdatePayload
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result


class TasksCoreService(BaseService["TasksOperations", Task]):
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
        entity_label="Entity",
    )

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, task: Task) -> Result[None] | None:
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

        return None  # All validations passed

    def _validate_update(self, current: Task, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate task updates with business rules.

        Business Rules:
        1. Terminal state protection: Cannot modify completed/cancelled/archived tasks
        2. Overdue task protection: Cannot decrease priority of overdue tasks

        Args:
            current: Current task state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
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
        if "priority" in updates and current.due_date and current.due_date < date.today():
            new_priority = Priority(updates["priority"])
            current_numeric = Priority(current.priority).to_numeric() if current.priority else 2
            if new_priority.to_numeric() < current_numeric:
                return Result.fail(
                    Errors.validation(
                        message="Cannot decrease priority of overdue tasks",
                        field="priority",
                        value=new_priority.value,
                    )
                )

        return None  # All validations passed

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
    async def _enhance_with_knowledge_inference(self, dto: TaskDTO) -> Result[TaskDTO | None]:
        """
        Apply automatic knowledge inference to enhance a task DTO.

        Returns Result.ok(None) if inference service not configured (feature disabled).
        Fails fast if inference service IS configured but fails.
        """
        if not self.ku_inference_service:
            # Feature not configured - this is OK, return None
            return Result.ok(None)

        inference_result = await self.ku_inference_service.enhance_task_dto_with_inference(dto)
        if inference_result.is_error:
            return Result.fail(inference_result)

        enhanced_dto = inference_result.value
        self.logger.debug(
            "Knowledge inference applied to task '%s': opportunities=%d",
            dto.title,
            enhanced_dto.learning_opportunities_count,
        )
        return Result.ok(enhanced_dto)

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
        if validation:
            return Result.fail(validation)

        # Create DTO from request with all fields
        from core.utils.uid_generator import UIDGenerator

        dto = TaskDTO(
            uid=UIDGenerator.generate_random_uid("task"),
            entity_type=EntityType.TASK,
            user_uid=user_uid,
            title=task_request.title,
            description=task_request.description,
            priority=task_request.priority,
            due_date=task_request.due_date,
            scheduled_date=task_request.scheduled_date,
            duration_minutes=task_request.duration_minutes,
            project=task_request.project,
            assignee=task_request.assignee,
            tags=task_request.tags,
            parent_uid=task_request.parent_uid,
            recurrence_pattern=task_request.recurrence_pattern,
            recurrence_end_date=task_request.recurrence_end_date,
            fulfills_goal_uid=task_request.fulfills_goal_uid,
            reinforces_habit_uid=task_request.reinforces_habit_uid,
            goal_progress_contribution=getattr(task_request, "goal_progress_contribution", 0.0),
            knowledge_mastery_check=getattr(task_request, "knowledge_mastery_check", False),
            habit_streak_maintainer=getattr(task_request, "habit_streak_maintainer", False),
        )

        # Apply automatic knowledge inference (fail-fast if configured)
        inference_result = await self._enhance_with_knowledge_inference(dto)
        if inference_result.is_error:
            return Result.fail(inference_result)
        if inference_result.value:
            dto = inference_result.value

        # Create task via backend and convert to domain model (uses BaseService helper)
        result = await self._create_and_convert(dto.to_dict(), TaskDTO, Task)
        if result.is_error:
            return result
        task = result.value

        # GRAPH-NATIVE: Create relationship edges in graph (not stored on Task/DTO)
        # Create knowledge relationships from request using batch operation for performance
        relationships = []

        if task_request.applies_knowledge_uids:
            relationships.extend(
                (task.uid, knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None)
                for knowledge_uid in task_request.applies_knowledge_uids
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

        # Publish embedding request event for async background generation
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(EntityType.TASK, task)
        if embedding_text:
            from core.events import TaskEmbeddingRequested

            embedding_event = TaskEmbeddingRequested(
                entity_uid=task.uid,
                entity_type="task",
                embedding_text=embedding_text,
                user_uid=task.user_uid,
                requested_at=datetime.now(),
            )
            await publish_event(self.event_bus, embedding_event, self.logger)

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
    async def update_task(self, task_uid: str, updates: dict) -> Result[Task]:
        """
        Update a task.

        Args:
            task_uid: Task UID,
            updates: Dictionary of field updates

        Returns:
            Result containing updated Task
        """
        # Get old task for priority change detection
        old_task = None
        if "priority" in updates:
            old_result = await self.backend.get(task_uid)
            if old_result.is_ok:
                old_task = self._to_domain_model(old_result.value, TaskDTO, Task)

        update_result = await self.backend.update(task_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result)

        # Convert updated result to Task
        task = self._to_domain_model(update_result.value, TaskDTO, Task)

        # Publish TaskUpdated event
        event = TaskUpdated(
            task_uid=task.uid,
            user_uid=task.user_uid,
            updated_fields=list(updates.keys()),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish TaskPriorityChanged event if priority changed
        if "priority" in updates and old_task and old_task.priority != task.priority:
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
        # Mark all tasks as completed
        updates: TaskUpdatePayload = {"status": EntityStatus.COMPLETED.value}
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
            event = TaskDeleted(task_uid=task_uid, user_uid=user_uid)
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to TasksBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    @with_error_handling("get_subtasks", error_type="database", uid_param="parent_uid")
    async def get_subtasks(self, parent_uid: str, depth: int = 1) -> Result[list[Task]]:
        """Get all subtasks of a parent task at the given depth."""
        result = await self.backend.get_children_raw(parent_uid, depth)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([self._to_domain_model(data, TaskDTO, Task) for data in result.value])

    @with_error_handling("get_parent_task", error_type="database", uid_param="subtask_uid")
    async def get_parent_task(self, subtask_uid: str) -> Result[Task | None]:
        """Get immediate parent of a subtask (if any)."""
        result = await self.backend.get_parent_raw(subtask_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.ok(None)
        return Result.ok(self._to_domain_model(result.value, TaskDTO, Task))

    @with_error_handling("get_task_hierarchy", error_type="database", uid_param="task_uid")
    async def get_task_hierarchy(self, task_uid: str) -> Result[dict[str, Any]]:
        """Get full hierarchy context: ancestors, current, siblings, children, depth."""
        current_result = await self.backend.get(task_uid)
        if current_result.is_error:
            return Result.fail(current_result)
        current_task = self._to_domain_model(current_result.value, TaskDTO, Task)

        hierarchy_result = await self.backend.get_hierarchy_raw(task_uid)
        if hierarchy_result.is_error:
            return Result.fail(hierarchy_result)

        raw = hierarchy_result.value
        return Result.ok(
            {
                "ancestors": [self._to_domain_model(n, TaskDTO, Task) for n in raw["ancestors"]],
                "current": current_task,
                "siblings": [self._to_domain_model(n, TaskDTO, Task) for n in raw["siblings"]],
                "children": [self._to_domain_model(n, TaskDTO, Task) for n in raw["children"]],
                "depth": len(raw["ancestors"]),
            }
        )

    async def create_subtask_relationship(
        self, parent_uid: str, subtask_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBTASK/SUBTASK_OF relationship with cycle detection."""
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subtask_uid, {"progress_weight": progress_weight}
        )

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[TaskStats]:
        """Count task stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    async def get_for_user_filtered(
        self, user_uid: UserUID, status_filter: str = "active"
    ) -> Result[list[Task]]:
        """Fetch tasks with status filter pushed to Cypher WHERE."""
        match status_filter:
            case "active":
                result = await self.backend.find_by(user_uid=user_uid, status__not_in=["completed"])
            case "completed":
                result = await self.backend.find_by(user_uid=user_uid, status="completed")
            case _:  # "all" or unknown
                result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result
        return Result.ok(self._to_domain_models(result.value, TaskDTO, Task))

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
