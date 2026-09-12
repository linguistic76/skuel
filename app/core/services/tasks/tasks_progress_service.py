"""
Tasks Progress Service - Prerequisites, Unblocking, Assignment
===============================================================

Completion is not here: the one completion door is ``TasksCoreService.update_task``
(the ADR-087 status chokepoint), and what a completion cascades into runs as
``TaskCompleted`` subscribers — dependent scheduling in ``TaskEventHandlerService``.

**Responsibilities:**
- Prerequisite checking and validation
- Task unblocking when ready
- Task assignment to users

**Dependencies:**
- TasksOperations (backend protocol)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.models.enums import EntityStatus
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.update_contracts import StatusWriteGuard
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.relationship_builder import relate
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result


class TasksProgressService(BaseService["TasksOperations", Task]):
    """
    Prerequisites, unblocking and assignment for tasks.
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
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize progress service with required dependencies.

        Args:
            backend: TasksOperations backend (required)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            TaskCompleted events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend=backend, service_name="tasks.progress")
        self.event_bus = event_bus

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
            return Result.fail(task_result)

        # GRAPH-NATIVE: Fetch prerequisite relationships from graph
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
            return Result.fail(prereq_result)

        if prereq_result.value["can_start"]:
            # Same terminal gate as the dependent scheduler (``TaskEventHandlerService``),
            # and for the same reason: a blind ``status=scheduled`` on an already-COMPLETED task would move it out of
            # COMPLETED while LEAVING ``completion_date`` set, breaking the invariant
            # that the stamp is non-null exactly when the task is completed. Unblocking
            # frees work that is waiting; it never resurrects work that is finished.
            # A CONDITION ON THE WRITE, not a read before it (ADR-087) — the task can be
            # completed between the prerequisite check above and this write.
            update_result = await self.backend.update_with_status_guard(
                task_uid,
                {"status": EntityStatus.SCHEDULED.value},
                StatusWriteGuard(refuse_if_prior_in=EntityStatus.terminal_values()),
            )
            if update_result.is_error:
                return Result.fail(update_result)

            outcome = update_result.value
            if not outcome.applied:
                # A finished task is not "unblocked" — it is nothing this call has left
                # to do, which is the same answer as "still blocked": no task returned.
                self.logger.debug(
                    "Skipped unblocking task %s: already terminal (%s)",
                    task_uid,
                    outcome.prior_status,
                )
                return Result.ok(None)

            unblocked_task = self._to_domain_model(outcome.entity, TaskDTO, Task)

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
        user_uid: UserUID,
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
        properties: dict[str, Any] = {"assigned_at": datetime.now().isoformat()}
        if assigned_by:
            properties["assigned_by"] = assigned_by
        if priority_override:
            properties["priority_override"] = priority_override

        result = await (
            relate(self.backend, task_uid)
            .via(RelationshipName.ASSIGNED_TO)
            .to(user_uid)
            .with_properties(**properties)
            .create()
        )

        if result.is_ok:
            self.logger.info(f"Assigned task {task_uid} to user {user_uid}")

        return result
