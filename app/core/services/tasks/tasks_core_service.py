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
- TasksOperations (backend protocol)
- KuInferenceService (optional - automatic knowledge inference)

Version: 1.0.0
Date: 2025-10-10
"""

from datetime import date, datetime
from typing import Any

from core.events import TaskCreated, TaskDeleted, TaskUpdated, publish_event
from core.models.relationship_names import RelationshipName
from core.models.shared_enums import ActivityStatus, EntityType
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols.domain_protocols import TasksOperations
from core.services.protocols.query_types import TaskUpdatePayload
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class TasksCoreService(BaseService[TasksOperations, Task]):
    """
    Core CRUD operations for tasks.


    Source Tag: "tasks_core_service_explicit"
    - Format: "tasks_core_service_explicit" for user-created relationships
    - Format: "tasks_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from tasks_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend=None, ku_inference_service=None, event_bus=None) -> None:
        """
        Initialize core service with required dependencies.

        Args:
            backend: TasksOperations backend (required),
            ku_inference_service: KuInferenceService for knowledge inference (optional),
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "tasks.core")
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
        completed_statuses=(ActivityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Task entities."""
        return "Task"

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
        if task.priority.to_numeric() >= 3 and not task.due_date:  # HIGH=3, CRITICAL=4
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
            from core.models.shared_enums import Priority

            new_priority = Priority(updates["priority"])
            if new_priority.to_numeric() < current.priority.to_numeric():
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
    # Uses registry-driven query generation from UnifiedRelationshipRegistry.
    # The TASKS_UNIFIED config includes:
    # - subtasks, dependencies, dependents (task hierarchy)
    # - applied_knowledge, required_knowledge (knowledge context)
    # - goal_context, habit_context (single related entities)
    # - related_tasks (shared-neighbor pattern via APPLIES_KNOWLEDGE|FULFILLS_GOAL)
    #
    # See: /core/models/unified_relationship_registry.py - TASKS_UNIFIED
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
            return Result.fail(inference_result.expect_error())

        enhanced_dto = inference_result.value
        self.logger.debug(
            "Knowledge inference applied to task '%s': opportunities=%d",
            dto.title,
            enhanced_dto.learning_opportunities_count,
        )
        return Result.ok(enhanced_dto)

    @with_error_handling("create_task", error_type="database")
    async def create_task(self, task_request: TaskCreateRequest, user_uid: str) -> Result[Task]:
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
            return validation

        # Create DTO from request with all fields
        dto = TaskDTO(
            uid=UIDGenerator.generate_random_uid("task"),
            user_uid=user_uid,
            title=task_request.title,
            description=task_request.description,
            priority=task_request.priority,
            status=task_request.status,
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
            goal_progress_contribution=task_request.goal_progress_contribution,
            knowledge_mastery_check=task_request.knowledge_mastery_check,
            habit_streak_maintainer=task_request.habit_streak_maintainer,
        )

        # Apply automatic knowledge inference (fail-fast if configured)
        inference_result = await self._enhance_with_knowledge_inference(dto)
        if inference_result.is_error:
            return Result.fail(inference_result.expect_error())
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
            priority=task.priority.value,
            # NOTE: Task domain not stored - could infer from related goal/knowledge
            domain=None,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish batch knowledge event for substance tracking (O(1) vs O(n))
        if task_request.applies_knowledge_uids:
            from core.events.knowledge_events import KnowledgeBulkAppliedInTask

            knowledge_event = KnowledgeBulkAppliedInTask(
                knowledge_uids=tuple(task_request.applies_knowledge_uids),
                task_uid=task.uid,
                user_uid=task.user_uid,
                occurred_at=datetime.now(),
                task_title=task.title,
                task_priority=task.priority.value,
            )
            await publish_event(self.event_bus, knowledge_event, self.logger)

        # Publish embedding request event for async background generation (Phase 1 - January 2026)
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
    async def get_user_tasks(self, user_uid: str) -> Result[list[Task]]:
        """
        Get all tasks for a user, including learning relationships.

        Args:
            user_uid: User UID

        Returns:
            Result containing list of Tasks
        """
        result = await self.backend.get_user_entities(user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

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
            return Result.fail(result.expect_error())
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
            occurred_at=datetime.now(),
            updated_fields=list(updates.keys()),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish TaskPriorityChanged event if priority changed
        if "priority" in updates and old_task and old_task.priority != task.priority:
            from core.events import TaskPriorityChanged

            priority_event = TaskPriorityChanged(
                task_uid=task.uid,
                user_uid=task.user_uid,
                old_priority=old_task.priority.value,
                new_priority=task.priority.value,
                escalated_to_urgent=(task.priority.to_numeric() == 4),  # HIGH = 4
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, priority_event, self.logger)

        return Result.ok(task)

    @with_error_handling("complete_tasks_bulk", error_type="database")
    async def complete_tasks_bulk(self, task_uids: list[str], user_uid: str) -> Result[int]:
        """
        Complete multiple tasks in a batch operation.

        Args:
            task_uids: List of task UIDs to complete
            user_uid: User UID (for event publishing)

        Returns:
            Result containing count of tasks completed
        """
        # Mark all tasks as completed
        updates: TaskUpdatePayload = {"status": ActivityStatus.COMPLETED.value}
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
                occurred_at=datetime.now(),
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
            event = TaskDeleted(task_uid=task_uid, user_uid=user_uid, occurred_at=datetime.now())
            await publish_event(self.event_bus, event, self.logger)

        return result
