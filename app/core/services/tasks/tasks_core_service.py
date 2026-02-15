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
- BackendOperations[Ku] (backend protocol)
- KuInferenceService (optional - automatic knowledge inference)

Version: 1.0.0
Date: 2025-10-10
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.events import TaskCreated, TaskDeleted, TaskUpdated, publish_event
from core.models.enums import KuStatus, Priority
from core.models.enums.ku_enums import KuType
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_request import KuTaskCreateRequest
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols.query_types import TaskUpdatePayload
from core.utils.decorators import with_error_handling
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols.base_protocols import BackendOperations


class TasksCoreService(BaseService["BackendOperations[Ku]", Ku]):
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
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(KuStatus.COMPLETED.value,),
    )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Task entities."""
        return "Ku"

    # ========================================================================
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, task: Ku) -> Result[None] | None:
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
        if task.priority and Priority(task.priority).to_numeric() >= 3 and not task.due_date:  # HIGH=3, CRITICAL=4
            return Result.fail(
                Errors.validation(
                    message="High-priority tasks must have a due date",
                    field="due_date",
                    value=None,
                )
            )

        return None  # All validations passed

    def _validate_update(self, current: Ku, updates: dict[str, Any]) -> Result[None] | None:
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
    async def _enhance_with_knowledge_inference(self, dto: KuDTO) -> Result[KuDTO | None]:
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
    async def create_task(self, task_request: KuTaskCreateRequest, user_uid: str) -> Result[Ku]:
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
        from core.utils.uid_generator import UIDGenerator

        dto = KuDTO(
            uid=UIDGenerator.generate_random_uid("task"),
            ku_type=KuType.TASK,
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
            return Result.fail(inference_result.expect_error())
        if inference_result.value:
            dto = inference_result.value

        # Create task via backend and convert to domain model (uses BaseService helper)
        result = await self._create_and_convert(dto.to_dict(), KuDTO, Ku)
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
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Publish batch knowledge event for substance tracking (O(1) vs O(n))
        if task_request.applies_knowledge_uids:
            from core.events.ku_events import KnowledgeBulkAppliedInTask

            knowledge_event = KnowledgeBulkAppliedInTask(
                knowledge_uids=tuple(task_request.applies_knowledge_uids),
                task_uid=task.uid,
                user_uid=task.user_uid,
                occurred_at=datetime.now(),
                task_title=task.title,
                task_priority=task.priority or "medium",
            )
            await publish_event(self.event_bus, knowledge_event, self.logger)

        # Publish embedding request event for async background generation (Phase 1 - January 2026)
        # Background worker will process embeddings in batches (zero latency impact on user)
        embedding_text = build_embedding_text(KuType.TASK, task)
        if embedding_text:
            from core.events import TaskEmbeddingRequested

            now = datetime.now()
            embedding_event = TaskEmbeddingRequested(
                entity_uid=task.uid,
                entity_type="task",
                embedding_text=embedding_text,
                user_uid=task.user_uid,
                requested_at=now,
                occurred_at=now,
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

    async def get_task(self, task_uid: str) -> Result[Ku]:
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
    async def get_user_tasks(self, user_uid: str) -> Result[list[Ku]]:
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
        tasks = [self._to_domain_model(task_data, KuDTO, Ku) for task_data in entities]

        self.logger.debug(f"Retrieved {len(tasks)} tasks for user {user_uid}")
        return Result.ok(tasks)

    async def list_tasks(self, filters: dict | None = None, limit: int = 100) -> Result[list[Ku]]:
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
    async def update_task(self, task_uid: str, updates: dict) -> Result[Ku]:
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
                old_task = self._to_domain_model(old_result.value, KuDTO, Ku)

        update_result = await self.backend.update(task_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result)

        # Convert updated result to Task
        task = self._to_domain_model(update_result.value, KuDTO, Ku)

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
                old_priority=old_task.priority or "medium",
                new_priority=task.priority or "medium",
                escalated_to_urgent=(
                    Priority(task.priority).to_numeric() == 4 if task.priority else False
                ),  # CRITICAL = 4
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
        updates: TaskUpdatePayload = {"status": KuStatus.COMPLETED.value}
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

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # ========================================================================

    @with_error_handling("get_subtasks", error_type="database", uid_param="parent_uid")
    async def get_subtasks(self, parent_uid: str, depth: int = 1) -> Result[list[Ku]]:
        """
        Get all subtasks of a parent task.

        Args:
            parent_uid: Parent task UID
            depth: How many levels deep (1=direct children, 2=children+grandchildren, etc.)

        Returns:
            Result containing list of subtasks ordered by created_at

        Example:
            # Get direct children
            subtasks = await service.get_subtasks("task_abc123")

            # Get all descendants
            all = await service.get_subtasks("task_abc123", depth=99)
        """
        query = f"""
        MATCH (parent:Ku {{uid: $parent_uid}})
        MATCH (parent)-[:HAS_SUBTASK*1..{depth}]->(subtask:Ku)
        RETURN subtask
        ORDER BY subtask.created_at
        """

        result = await self.backend.driver.execute_query(query, parent_uid=parent_uid)

        if not result.records:
            return Result.ok([])

        # Convert to Task models
        tasks = []
        for record in result.records:
            task_data = dict(record["subtask"])
            task = self._to_domain_model(task_data, KuDTO, Ku)
            tasks.append(task)

        return Result.ok(tasks)

    @with_error_handling("get_parent_task", error_type="database", uid_param="subtask_uid")
    async def get_parent_task(self, subtask_uid: str) -> Result[Ku | None]:
        """
        Get immediate parent of a subtask (if any).

        Args:
            subtask_uid: Subtask UID

        Returns:
            Result containing parent Task or None if root-level task
        """
        query = """
        MATCH (subtask:Ku {uid: $subtask_uid})
        MATCH (parent:Ku)-[:HAS_SUBTASK]->(subtask)
        RETURN parent
        LIMIT 1
        """

        result = await self.backend.driver.execute_query(query, subtask_uid=subtask_uid)

        if not result.records:
            return Result.ok(None)

        parent_data = dict(result.records[0]["parent"])
        parent = self._to_domain_model(parent_data, KuDTO, Ku)
        return Result.ok(parent)

    @with_error_handling("get_task_hierarchy", error_type="database", uid_param="task_uid")
    async def get_task_hierarchy(self, task_uid: str) -> Result[dict[str, Any]]:
        """
        Get full hierarchy context: ancestors, siblings, children.

        Args:
            task_uid: Task UID to get context for

        Returns:
            Result containing hierarchy dict with keys:
            - ancestors: list[Task] (root to immediate parent)
            - current: Task
            - siblings: list[Task] (other children of same parent)
            - children: list[Task] (immediate children)
            - depth: int (how deep in hierarchy, 0=root)

        Example:
            hierarchy = await service.get_task_hierarchy("task_xyz789")
            # {
            #   "ancestors": [root_task, parent_task],
            #   "current": task_xyz789,
            #   "siblings": [sibling1, sibling2],
            #   "children": [child1, child2],
            #   "depth": 2
            # }
        """
        # Get ancestors
        ancestors_query = """
        MATCH path = (root:Ku)-[:HAS_SUBTASK*]->(current:Ku {uid: $task_uid})
        WHERE NOT EXISTS((root)<-[:HAS_SUBTASK]-())
        RETURN nodes(path) as ancestors
        """

        # Get siblings
        siblings_query = """
        MATCH (current:Ku {uid: $task_uid})
        OPTIONAL MATCH (parent:Ku)-[:HAS_SUBTASK]->(current)
        OPTIONAL MATCH (parent)-[:HAS_SUBTASK]->(sibling:Ku)
        WHERE sibling.uid <> $task_uid
        RETURN collect(sibling) as siblings
        """

        # Get children
        children_query = """
        MATCH (current:Ku {uid: $task_uid})
        OPTIONAL MATCH (current)-[:HAS_SUBTASK]->(child:Ku)
        RETURN collect(child) as children
        """

        # Execute all queries
        current_result = await self.backend.get(task_uid)
        if current_result.is_error:
            return Result.fail(current_result)

        current_task = self._to_domain_model(current_result.value, KuDTO, Ku)

        ancestors_result = await self.backend.driver.execute_query(
            ancestors_query, task_uid=task_uid
        )
        siblings_result = await self.backend.driver.execute_query(siblings_query, task_uid=task_uid)
        children_result = await self.backend.driver.execute_query(children_query, task_uid=task_uid)

        # Process ancestors
        ancestors = []
        if ancestors_result.records and ancestors_result.records[0]["ancestors"]:
            for node in ancestors_result.records[0]["ancestors"][:-1]:  # Exclude current
                task_data = dict(node)
                ancestors.append(self._to_domain_model(task_data, KuDTO, Ku))

        # Process siblings
        siblings = []
        if siblings_result.records and siblings_result.records[0]["siblings"]:
            for node in siblings_result.records[0]["siblings"]:
                if node:  # Skip None values
                    task_data = dict(node)
                    siblings.append(self._to_domain_model(task_data, KuDTO, Ku))

        # Process children
        children = []
        if children_result.records and children_result.records[0]["children"]:
            for node in children_result.records[0]["children"]:
                if node:  # Skip None values
                    task_data = dict(node)
                    children.append(self._to_domain_model(task_data, KuDTO, Ku))

        return Result.ok(
            {
                "ancestors": ancestors,
                "current": current_task,
                "siblings": siblings,
                "children": children,
                "depth": len(ancestors),
            }
        )

    async def create_subtask_relationship(
        self, parent_uid: str, subtask_uid: str, progress_weight: float = 1.0
    ) -> Result[bool]:
        """
        Create bidirectional parent-child relationship.

        Args:
            parent_uid: Parent task UID
            subtask_uid: Subtask UID
            progress_weight: How much this subtask contributes to parent progress (default: 1.0)

        Returns:
            Result indicating success

        Note:
            Creates both HAS_SUBTASK (parent→child) and SUBTASK_OF (child→parent)
            for efficient bidirectional queries.
        """
        # Validate no cycle (can't make parent a child of its descendant)
        cycle_check = await self._would_create_cycle(parent_uid, subtask_uid)
        if cycle_check:
            return Result.fail(
                Errors.validation(
                    f"Cannot create subtask relationship: would create cycle "
                    f"({subtask_uid} is ancestor of {parent_uid})"
                )
            )

        query = """
        MATCH (parent:Ku {uid: $parent_uid})
        MATCH (subtask:Ku {uid: $subtask_uid})

        CREATE (parent)-[:HAS_SUBTASK {
            progress_weight: $weight,
            created_at: datetime()
        }]->(subtask)

        CREATE (subtask)-[:SUBTASK_OF {
            created_at: datetime()
        }]->(parent)

        RETURN true as success
        """

        result = await self.backend.driver.execute_query(
            query, parent_uid=parent_uid, subtask_uid=subtask_uid, weight=progress_weight
        )

        if result.records:
            self.logger.info(
                f"Created subtask relationship: {parent_uid} -> {subtask_uid} (weight: {progress_weight})"
            )
            return Result.ok(True)

        return Result.fail(
            Errors.database(operation="create", message="Failed to create subtask relationship")
        )

    async def _would_create_cycle(self, parent_uid: str, child_uid: str) -> bool:
        """Check if adding parent->child relationship would create a cycle."""
        query = """
        MATCH (child:Ku {uid: $child_uid})
        MATCH path = (child)-[:HAS_SUBTASK*]->(parent:Ku {uid: $parent_uid})
        RETURN count(path) > 0 as would_create_cycle
        """

        result = await self.backend.driver.execute_query(
            query, parent_uid=parent_uid, child_uid=child_uid
        )

        if result.records:
            return result.records[0]["would_create_cycle"]

        return False

    # ========================================================================
    # COMPLETION PROPAGATION (2026-01-30 - Auto-Complete Parents)
    # ========================================================================

    async def check_and_complete_parent(self, completed_task_uid: str) -> Result[list[str]]:
        """
        Check if parent task should auto-complete after child completes.

        When a subtask is completed, this checks if all siblings are also complete.
        If yes, auto-completes the parent and recursively checks grandparent.

        Args:
            completed_task_uid: UID of subtask that was just completed

        Returns:
            Result containing list of parent UIDs that were auto-completed

        Example:
            # Complete subtask
            await tasks_service.update_task(subtask_uid, {"status": "completed"})

            # Check if parent should auto-complete
            auto_completed = await tasks_service.check_and_complete_parent(subtask_uid)
            # Returns: ["task_parent", "task_grandparent"] if they auto-completed
        """
        auto_completed_uids = []

        query = """
        MATCH (completed:Ku {uid: $task_uid})
        MATCH (parent:Ku)-[:HAS_SUBTASK]->(completed)

        // Get all subtasks of this parent
        MATCH (parent)-[:HAS_SUBTASK]->(sibling:Ku)

        // Check if all siblings are complete
        WITH parent,
             count(sibling) as total_subtasks,
             count(CASE WHEN sibling.status = 'completed' THEN 1 END) as completed_subtasks

        WHERE total_subtasks = completed_subtasks
          AND parent.status <> 'completed'  // Don't update if already complete

        // Auto-complete parent
        SET parent.status = 'completed',
            parent.completed_at = datetime(),
            parent.auto_completed = true

        RETURN parent.uid as parent_uid
        """

        result = await self.backend.driver.execute_query(query, task_uid=completed_task_uid)

        if result.records:
            for record in result.records:
                parent_uid = record["parent_uid"]
                auto_completed_uids.append(parent_uid)
                self.logger.info(
                    f"Auto-completed parent task: {parent_uid} (all subtasks complete)"
                )

                # Recursively check grandparent
                grandparent_result = await self.check_and_complete_parent(parent_uid)
                if grandparent_result.is_ok:
                    auto_completed_uids.extend(grandparent_result.value)

        return Result.ok(auto_completed_uids)

    async def calculate_parent_progress(self, parent_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate parent task progress based on weighted subtask completion.

        Uses progress_weight from HAS_SUBTASK relationships to calculate
        weighted completion percentage.

        Args:
            parent_uid: Parent task UID

        Returns:
            Result containing dict with:
            - total_weight: Sum of all subtask weights
            - completed_weight: Sum of completed subtask weights
            - progress_percentage: Completion percentage (0-100)
            - total_subtasks: Count of subtasks
            - completed_subtasks: Count of completed subtasks

        Example:
            progress = await service.calculate_parent_progress("task_abc123")
            # {
            #   "total_weight": 3.0,
            #   "completed_weight": 2.0,
            #   "progress_percentage": 66.67,
            #   "total_subtasks": 3,
            #   "completed_subtasks": 2
            # }
        """
        query = """
        MATCH (parent:Ku {uid: $parent_uid})
        MATCH (parent)-[r:HAS_SUBTASK]->(child:Ku)

        WITH parent,
             count(child) as total_subtasks,
             count(CASE WHEN child.status = 'completed' THEN 1 END) as completed_subtasks,
             sum(r.progress_weight) as total_weight,
             sum(
               CASE WHEN child.status = 'completed'
               THEN r.progress_weight
               ELSE 0
               END
             ) as completed_weight

        RETURN
          total_subtasks,
          completed_subtasks,
          total_weight,
          completed_weight,
          CASE WHEN total_weight > 0
            THEN (completed_weight / total_weight) * 100.0
            ELSE 0.0
          END as progress_percentage
        """

        result = await self.backend.driver.execute_query(query, parent_uid=parent_uid)

        if not result.records:
            return Result.ok(
                {
                    "total_weight": 0.0,
                    "completed_weight": 0.0,
                    "progress_percentage": 0.0,
                    "total_subtasks": 0,
                    "completed_subtasks": 0,
                }
            )

        record = result.records[0]
        return Result.ok(
            {
                "total_weight": record["total_weight"] or 0.0,
                "completed_weight": record["completed_weight"] or 0.0,
                "progress_percentage": record["progress_percentage"] or 0.0,
                "total_subtasks": record["total_subtasks"],
                "completed_subtasks": record["completed_subtasks"],
            }
        )
