"""
Tasks Progress Service - Progress Tracking and Completion
==========================================================

Clean rewrite following CLAUDE.md patterns.
Handles task completion, progress tracking, and cascade effects.

**Responsibilities:**
- Task completion with cascading updates
- Prerequisite checking and validation
- Task unblocking when ready
- Progress updates to goals, habits, knowledge
- Knowledge unlocking

**Dependencies:**
- TasksOperations (backend protocol)
- UserContextOperations (optional protocol - for context invalidation)
- AnalyticsEngine (optional - for analytics)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.events import TaskCompleted, publish_event
from core.models.enums import Domain, EntityStatus, Priority
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.tasks.task_relationships import TaskRelationships
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

# Type alias for rich task data from UserContext
RichTaskData = dict[str, Any]


class TasksProgressService(BaseService["TasksOperations", Task]):
    """
    Progress tracking and completion for tasks.
    """

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

    def __init__(
        self,
        backend: TasksOperations,
        analytics_engine: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize progress service with required dependencies.

        Args:
            backend: TasksOperations backend (required)
            analytics_engine: AnalyticsEngine for analytics (optional)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            TaskCompleted events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend=backend, service_name="tasks.progress")
        self.analytics_engine = analytics_engine
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Task entities."""
        return "Entity"

    # ========================================================================
    # CONTEXT-FIRST PATTERN HELPERS (November 26, 2025)
    # ========================================================================
    #
    # These methods implement the Context-First Pattern:
    # - UserContext is THE source of truth for user state
    # - Services CONSUME context, they don't rebuild it
    # - Only query what context doesn't have
    #
    # Benefits:
    # - 4 queries → 1 query per task completion (when rich context available)
    # - Single source of truth (no race conditions)
    # - Architectural consistency
    #
    # ========================================================================

    def _get_task_from_rich_context(self, task_uid: str, user_context: UserContext) -> Task | None:
        """
        Try to get Task entity from UserContext rich data.

        Context-First Pattern: Use context data when available to avoid
        unnecessary Neo4j queries.

        Args:
            task_uid: Task identifier
            user_context: User's context (may contain rich task data)

        Returns:
            Task if found in rich context, None otherwise
        """
        for task_data in user_context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            if task_dict.get("uid") == task_uid:
                # Convert dict to Task domain model
                return self._dict_to_task(task_dict)

        return None

    def _get_relationships_from_rich_context(
        self, task_uid: str, user_context: UserContext
    ) -> TaskRelationships | None:
        """
        Try to get TaskRelationships from UserContext rich data.

        Context-First Pattern: Graph neighborhoods are often included in
        rich context from MEGA-QUERY.

        Args:
            task_uid: Task identifier
            user_context: User's context with potential graph neighborhoods

        Returns:
            TaskRelationships if found in rich context, None otherwise
        """
        for task_data in user_context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            if task_dict.get("uid") == task_uid:
                graph_ctx = task_data.get("graph_context", {})
                if graph_ctx:
                    return TaskRelationships(
                        applies_knowledge_uids=[
                            k.get("uid")
                            for k in graph_ctx.get("applied_knowledge", [])
                            if k and k.get("uid")
                        ],
                        prerequisite_task_uids=[
                            t.get("uid")
                            for t in graph_ctx.get("dependencies", [])
                            if t and t.get("uid")
                        ],
                        subtask_uids=[
                            s.get("uid")
                            for s in graph_ctx.get("subtasks", [])
                            if s and s.get("uid")
                        ],
                    )
        return None

    def _dict_to_task(self, task_dict: dict[str, Any]) -> Task:
        """
        Convert a task dictionary from MEGA-QUERY to Task domain model.

        Args:
            task_dict: Dict with task properties from Neo4j

        Returns:
            Task domain model
        """
        # Parse date fields
        due_date = task_dict.get("due_date")
        if due_date and isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)
        elif due_date and not isinstance(due_date, date):
            # Neo4j date objects
            due_date = date(due_date.year, due_date.month, due_date.day) if due_date else None

        completion_date = task_dict.get("completion_date")
        if completion_date and isinstance(completion_date, str):
            completion_date = date.fromisoformat(completion_date)
        elif completion_date and not isinstance(completion_date, date):
            completion_date = (
                date(completion_date.year, completion_date.month, completion_date.day)
                if completion_date
                else None
            )

        # Parse datetime fields
        created_at = task_dict.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = task_dict.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        # Parse enums
        status_val = task_dict.get("status", "pending")
        status = EntityStatus(status_val) if isinstance(status_val, str) else status_val

        priority_val = task_dict.get("priority", "medium")
        priority = Priority(priority_val) if isinstance(priority_val, str) else priority_val

        domain_val = task_dict.get("domain")
        Domain(domain_val) if domain_val and isinstance(domain_val, str) else domain_val

        # Convert tags list to tuple for frozen dataclass
        tags_list = task_dict.get("tags", [])
        tags_tuple = tuple(tags_list) if isinstance(tags_list, list) else tags_list

        return Task(
            uid=task_dict.get("uid", ""),
            user_uid=task_dict.get("user_uid", ""),
            title=task_dict.get("title", ""),
            description=task_dict.get("description"),
            status=status,
            priority=priority,
            due_date=due_date,
            completion_date=completion_date,
            duration_minutes=task_dict.get(
                "duration_minutes", task_dict.get("estimated_minutes", 30)
            ),
            actual_minutes=task_dict.get("actual_minutes"),
            fulfills_goal_uid=task_dict.get("fulfills_goal_uid"),
            reinforces_habit_uid=task_dict.get("reinforces_habit_uid"),
            completion_updates_goal=task_dict.get("completion_updates_goal", False),
            goal_progress_contribution=task_dict.get("goal_progress_contribution", 0.0),
            knowledge_mastery_check=task_dict.get("knowledge_mastery_check", False),
            parent_uid=task_dict.get("parent_uid", task_dict.get("parent_task_uid")),
            tags=tags_tuple,
            metadata=task_dict.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _get_completion_triggers_from_context(
        self, task_uid: str, user_context: UserContext
    ) -> list[str]:
        """
        Get completion trigger task UIDs from rich context.

        Args:
            task_uid: Task identifier
            user_context: User's context

        Returns:
            List of task UIDs that should be triggered on completion
        """
        for task_data in user_context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            if task_dict.get("uid") == task_uid:
                graph_ctx = task_data.get("graph_context", {})
                triggers = graph_ctx.get("completion_triggers", [])
                return [t.get("uid") for t in triggers if t and t.get("uid")]

        return []

    def _get_unlocks_knowledge_from_context(
        self, task_uid: str, user_context: UserContext
    ) -> list[str]:
        """
        Get knowledge UIDs that completing this task unlocks.

        Args:
            task_uid: Task identifier
            user_context: User's context

        Returns:
            List of knowledge UIDs that should be unlocked on completion
        """
        for task_data in user_context.entities_rich.get("tasks", []):
            task_dict = task_data.get("entity", {})
            if task_dict.get("uid") == task_uid:
                graph_ctx = task_data.get("graph_context", {})
                unlocks = graph_ctx.get("unlocks_knowledge", [])
                return [k.get("uid") for k in unlocks if k and k.get("uid")]

        return []

    # ========================================================================
    # TASK COMPLETION
    # ========================================================================

    @with_error_handling("complete_task_with_cascade", error_type="database", uid_param="task_uid")
    async def complete_task_with_cascade(
        self,
        task_uid: str,
        user_context: UserContext,
        actual_minutes: int | None = None,
        quality_score: int | None = None,
    ) -> Result[Task]:
        """
        Complete a task and cascade updates through the system.

        This method:
        1. Marks task as complete
        2. Updates goal progress if linked
        3. Reinforces habit if linked
        4. Updates knowledge mastery if checking
        5. Triggers dependent tasks if configured
        6. Invalidates user context

        **CONTEXT-FIRST PATTERN (November 26, 2025):**
        This method now uses the Context-First Pattern:
        - First tries to get task from user_context.entities_rich["tasks"]
        - First tries to get relationships from rich context graph_context
        - Only falls back to Neo4j queries if not in context
        - Reduces from 4 queries to 1 when context is available

        Args:
            task_uid: Task UID,
            user_context: User context for cascade effects,
            actual_minutes: Actual time spent on task,
            quality_score: Completion quality score

        Returns:
            Result containing completed task
        """
        # CONTEXT-FIRST: Try to get task from rich context before querying Neo4j
        task = self._get_task_from_rich_context(task_uid, user_context)
        context_hit = task is not None

        if task is None:
            # Fallback: Query Neo4j directly
            task_result = await self.backend.get(task_uid)
            if task_result.is_error:
                return Result.fail(task_result.expect_error())
            task = self._to_domain_model(task_result.value, TaskDTO, Task)
            self.logger.debug(f"Task {task_uid} fetched from Neo4j (not in rich context)")
        else:
            self.logger.debug(f"Task {task_uid} found in rich context (no Neo4j query needed)")

        # CONTEXT-FIRST: Try to get relationships from rich context
        from core.models.relationship_names import RelationshipName

        rels = self._get_relationships_from_rich_context(task_uid, user_context)
        if rels is not None:
            applies_knowledge_uids = rels.applies_knowledge_uids
            self.logger.debug(
                f"Task relationships from rich context: {len(applies_knowledge_uids)} knowledge"
            )
        else:
            # Fallback: Query Neo4j for relationships
            applies_knowledge_result = await self.backend.get_related_uids(
                task_uid, RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
            )
            applies_knowledge_uids = (
                applies_knowledge_result.value if applies_knowledge_result.is_ok else []
            )
            self.logger.debug(
                f"Task relationships from Neo4j: {len(applies_knowledge_uids)} knowledge"
            )

        # CONTEXT-FIRST: Try to get completion triggers from rich context
        completion_triggers_tasks = self._get_completion_triggers_from_context(
            task_uid, user_context
        )
        if not completion_triggers_tasks:
            # Fallback: Query Neo4j
            triggers_result = await self.backend.get_related_uids(
                task_uid, RelationshipName.TRIGGERS_ON_COMPLETION, direction="outgoing"
            )
            completion_triggers_tasks = triggers_result.value if triggers_result.is_ok else []

        # CONTEXT-FIRST: Try to get knowledge unlocks from rich context
        completion_unlocks_knowledge = self._get_unlocks_knowledge_from_context(
            task_uid, user_context
        )
        if not completion_unlocks_knowledge:
            # Fallback: Query Neo4j
            unlocks_result = await self.backend.get_related_uids(
                task_uid, RelationshipName.UNLOCKS_KNOWLEDGE, direction="outgoing"
            )
            completion_unlocks_knowledge = unlocks_result.value if unlocks_result.is_ok else []

        # Log context efficiency
        if context_hit:
            self.logger.info(
                f"Context-first: Task {task_uid} completion used rich context (saved queries)"
            )

        # Update task to completed
        updates = {
            "status": EntityStatus.COMPLETED.value,
            "completion_date": date.today(),
            "actual_minutes": actual_minutes,
        }

        update_result = await self.backend.update(task_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        # CASCADE EFFECTS

        # 1. Update goal progress if linked
        if task.fulfills_goal_uid and task.completion_updates_goal:
            await self._update_goal_progress(
                task.fulfills_goal_uid, task.goal_progress_contribution, user_context
            )

        # 2. Reinforce habit if linked
        if task.reinforces_habit_uid:
            await self._reinforce_habit(task.reinforces_habit_uid, quality_score or 4)

        # 3. Update knowledge mastery if checking
        if task.knowledge_mastery_check and applies_knowledge_uids:
            for knowledge_uid in applies_knowledge_uids:
                await self._update_knowledge_mastery(knowledge_uid, 0.1)  # Increase by 10%

        # 4. Trigger dependent tasks
        if completion_triggers_tasks:
            for trigger_task_uid in completion_triggers_tasks:
                await self._trigger_task(trigger_task_uid)

        # 5. Unlock knowledge
        if completion_unlocks_knowledge:
            for knowledge_uid in completion_unlocks_knowledge:
                await self._unlock_knowledge(knowledge_uid, user_context.user_uid)

        # Context invalidation happens via TaskCompleted event (event-driven architecture)
        # Event handlers in bootstrap will call user_service.invalidate_context()

        # Return updated task
        completed_task = self._to_domain_model(update_result.value, TaskDTO, Task)

        self.logger.info(
            "Completed task %s with cascading effects: goal=%s, habit=%s, knowledge=%d",
            task_uid,
            task.fulfills_goal_uid,
            task.reinforces_habit_uid,
            len(applies_knowledge_uids),
        )

        # Publish TaskCompleted event
        event = TaskCompleted(
            task_uid=task_uid,
            user_uid=user_context.user_uid,
            occurred_at=datetime.now(),
            completion_time_seconds=actual_minutes * 60 if actual_minutes else None,
            was_overdue=task.due_date and task.due_date < date.today() if task.due_date else False,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(completed_task)

    @with_error_handling("record_task_completion", error_type="database", uid_param="task_uid")
    async def record_task_completion(
        self,
        task_uid: str,
        user_uid: str,
        duration_minutes: int = 0,
        quality_score: float = 1.0,
        completion_notes: str = "",
    ) -> Result[bool]:
        """
        Record task completion by user with graph relationship.

        Creates: (User)-[:COMPLETED_TASK]->(Task)

        Args:
            task_uid: Task UID,
            user_uid: User who completed the task,
            duration_minutes: Time spent on task,
            quality_score: Completion quality (0.0-1.0),
            completion_notes: Optional notes

        Returns:
            Result indicating success
        """
        # Create relationship: (User)-[:COMPLETED_TASK]->(Task)
        from core.models.relationship_names import RelationshipName

        result = await self.backend.add_relationship(
            from_uid=user_uid,
            to_uid=task_uid,
            relationship_type=RelationshipName.COMPLETED_TASK,
            properties={
                "duration_minutes": duration_minutes,
                "quality_score": quality_score,
                "completion_notes": completion_notes,
                "completed_at": datetime.now().isoformat(),
            },
        )

        if result.is_ok:
            self.logger.info(f"Recorded completion of task {task_uid} by user {user_uid}")

            # Publish TaskCompleted event
            # Get task to check if it was overdue
            task_result = await self.backend.get(task_uid)
            was_overdue = False
            if task_result.is_ok and task_result.value:
                task_data = task_result.value
                due_date = (
                    task_data.get("due_date")
                    if isinstance(task_data, dict)
                    else getattr(task_data, "due_date", None)
                )
                was_overdue = due_date and due_date < date.today() if due_date else False

            event = TaskCompleted(
                task_uid=task_uid,
                user_uid=user_uid,
                occurred_at=datetime.now(),
                completion_time_seconds=duration_minutes * 60,
                was_overdue=was_overdue,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # PREREQUISITE MANAGEMENT
    # ========================================================================

    @with_error_handling("check_prerequisites", error_type="database", uid_param="task_uid")
    async def check_prerequisites(
        self, task_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """
        Check if all prerequisites for a task are met.

        Pattern 1 (Graph-Aware Models): Instant prerequisite validation using UID fields.

        Returns dict with:
        - can_start: bool
        - missing_knowledge: list of knowledge UIDs
        - incomplete_tasks: list of task UIDs

        Args:
            task_uid: Task UID,
            user_context: User context for prerequisite checking

        Returns:
            Result containing prerequisite check status
        """
        task_result = await self.backend.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        # GRAPH-NATIVE: Fetch prerequisite relationships from graph
        from core.models.relationship_names import RelationshipName

        prereq_knowledge_result = await self.backend.get_related_uids(
            task_uid, RelationshipName.REQUIRES_KNOWLEDGE, direction="outgoing"
        )
        prerequisite_knowledge_uids = (
            prereq_knowledge_result.value if prereq_knowledge_result.is_ok else []
        )

        prereq_tasks_result = await self.backend.get_related_uids(
            task_uid, RelationshipName.BLOCKED_BY, direction="outgoing"
        )
        prerequisite_task_uids = prereq_tasks_result.value if prereq_tasks_result.is_ok else []

        # Check knowledge prerequisites
        missing_knowledge = []
        if prerequisite_knowledge_uids:
            missing_knowledge = [
                k
                for k in prerequisite_knowledge_uids
                if k not in user_context.prerequisites_completed
            ]

        # Check task prerequisites
        incomplete_tasks = []
        if prerequisite_task_uids:
            incomplete_tasks = [
                t for t in prerequisite_task_uids if t not in user_context.completed_task_uids
            ]

        can_start = len(missing_knowledge) == 0 and len(incomplete_tasks) == 0

        self.logger.debug(f"Prerequisite check for task {task_uid}: can_start={can_start}")

        return Result.ok(
            {
                "can_start": can_start,
                "missing_knowledge": missing_knowledge,
                "incomplete_tasks": incomplete_tasks,
            }
        )

    @with_error_handling("unblock_task_if_ready", error_type="database", uid_param="task_uid")
    async def unblock_task_if_ready(
        self, task_uid: str, user_context: UserContext
    ) -> Result[Task | None]:
        """
        Unblock a task if all prerequisites are met.

        Pattern 1 (Graph-Aware Models): Uses check_prerequisites() for fast validation.

        Args:
            task_uid: Task UID,
            user_context: User context

        Returns:
            Result containing unblocked task (or None if still blocked)
        """
        prereq_result = await self.check_prerequisites(task_uid, user_context)
        if prereq_result.is_error:
            return Result.fail(prereq_result.expect_error())

        if prereq_result.value["can_start"]:
            # Unblock the task
            update_result = await self.backend.update(
                task_uid, {"status": EntityStatus.SCHEDULED.value}
            )
            if update_result.is_error:
                return Result.fail(update_result.expect_error())

            unblocked_task = self._to_domain_model(update_result.value, TaskDTO, Task)

            self.logger.info(f"Unblocked task {task_uid}")
            return Result.ok(unblocked_task)

        return Result.ok(None)  # Still blocked

    # ========================================================================
    # TASK ASSIGNMENT
    # ========================================================================

    @with_error_handling("assign_task_to_user", error_type="database", uid_param="task_uid")
    async def assign_task_to_user(
        self,
        task_uid: str,
        user_uid: str,
        assigned_by: str | None = None,
        priority_override: str | None = None,
    ) -> Result[bool]:
        """
        Assign task to user using graph relationship.

        Creates: (Task)-[:ASSIGNED_TO]->(User)

        Args:
            task_uid: Task UID,
            user_uid: User UID to assign to,
            assigned_by: UID of user who assigned (optional),
            priority_override: Priority override for this assignment

        Returns:
            Result indicating success
        """
        # Create relationship: (Task)-[:ASSIGNED_TO]->(User)
        from core.models.relationship_names import RelationshipName

        properties: dict[str, Any] = {"assigned_at": datetime.now().isoformat()}
        if assigned_by:
            properties["assigned_by"] = assigned_by
        if priority_override:
            properties["priority_override"] = priority_override

        result = await self.backend.add_relationship(
            from_uid=task_uid,
            to_uid=user_uid,
            relationship_type=RelationshipName.ASSIGNED_TO,
            properties=properties,
        )

        if result.is_ok:
            self.logger.info(f"Assigned task {task_uid} to user {user_uid}")

        return result

    # ========================================================================
    # PRIVATE CASCADE METHODS
    # ========================================================================

    async def _update_goal_progress(
        self, goal_uid: str, contribution: float, user_context: UserContext
    ) -> None:
        """Update goal progress based on task completion."""
        # This would call goal service
        # For now, log the action
        self.logger.debug(
            "Would update goal %s progress by %.2f for user %s",
            goal_uid,
            contribution,
            user_context.user_uid,
        )

    async def _reinforce_habit(self, habit_uid: str, quality: int) -> None:
        """Reinforce a habit with completion quality."""
        # This would call habit service
        self.logger.debug("Would reinforce habit %s with quality %d", habit_uid, quality)

    async def _update_knowledge_mastery(self, knowledge_uid: str, increment: float) -> None:
        """Update knowledge mastery level."""
        # This would call knowledge service
        self.logger.debug("Would increase knowledge %s mastery by %.2f", knowledge_uid, increment)

    async def _trigger_task(self, task_uid: str) -> None:
        """Trigger a dependent task."""
        # Unblock the triggered task
        try:
            await self.backend.update(task_uid, {"status": EntityStatus.SCHEDULED.value})
            self.logger.debug(f"Triggered task {task_uid}")
        except Exception as e:
            self.logger.warning(f"Failed to trigger task {task_uid}: {e}")

    async def _unlock_knowledge(self, knowledge_uid: str, user_uid: str) -> None:
        """Unlock knowledge for a user."""
        # This would call knowledge service
        self.logger.debug("Would unlock knowledge %s for user %s", knowledge_uid, user_uid)
