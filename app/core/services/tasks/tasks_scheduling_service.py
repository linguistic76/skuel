"""
Tasks Scheduling Service - Scheduling and Recurrence
=====================================================

Clean rewrite following CLAUDE.md patterns.
Handles task scheduling and context-aware creation.

**Responsibilities:**
- Context-aware task creation
- Curriculum-based task creation

**Dependencies:**
- TasksOperations (backend protocol)
- TasksCoreService (THE create primitive — both create doors here hand off to it)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations
    from core.services.tasks.tasks_core_service import TasksCoreService

from core.models.enums import EntityStatus, EntityType, Priority
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_request import TaskCreateRequest
from core.models.type_hints import EntityUID, UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class TasksSchedulingService(BaseService["TasksOperations", Task]):
    """
    Task scheduling and context-aware creation.
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

    def __init__(self, backend: TasksOperations, core: TasksCoreService) -> None:
        """
        Initialize scheduling service with required dependencies.

        Args:
            backend: TasksOperations backend (required)
            core: TasksCoreService — THE create primitive. Both create doors here
                delegate to it so every task, however created, gets the same edges,
                admission guard, ordering, TaskCreated event and ADR-074 embedding
                request. (Same sibling-injection shape as
                ``HabitsPatternService(habits_core=...)``.)
        """
        super().__init__(backend=backend, service_name="tasks.scheduling")
        self.core = core

    # ========================================================================
    # CONTEXT-AWARE CREATION
    # ========================================================================

    @with_error_handling("create_task_with_context", error_type="database")
    async def create_task_with_context(
        self, task_data: TaskCreateRequest, user_context: UserContext
    ) -> Result[Task]:
        """
        Create a task after checking its prerequisites against the user's context.

        Pattern 1 (Graph-Aware Models): prerequisite validation using context fields —
        set membership against ``prerequisites_completed`` / ``completed_task_uids``,
        O(1) per UID with no graph round-trip. That gate is ALL this door adds; the
        create itself is ``TasksCoreService.create_task``, THE create primitive's
        request door, so the task gets the same guarded link edges, write-then-announce
        ordering, ``TaskCreated`` event and ADR-074 embedding request as every other
        create.

        Args:
            task_data: Task creation request,
            user_context: User context for prerequisite validation

        Returns:
            Result containing created task
        """
        # Check knowledge prerequisites
        if task_data.prerequisite_knowledge_uids:
            missing_prereqs = (
                set(task_data.prerequisite_knowledge_uids) - user_context.prerequisites_completed
            )
            if missing_prereqs:
                return Result.fail(
                    Errors.validation(
                        f"Missing knowledge prerequisites: {', '.join(missing_prereqs)}"
                    )
                )

        # Check task prerequisites
        if task_data.prerequisite_task_uids:
            incomplete_tasks = (
                set(task_data.prerequisite_task_uids) - user_context.completed_task_uids
            )
            if incomplete_tasks:
                return Result.fail(
                    Errors.validation(
                        f"Prerequisite tasks not completed: {', '.join(incomplete_tasks)}"
                    )
                )

        # Prerequisites hold — the primitive does the rest (see the docstring).
        return await self.core.create_task(task_data, user_context.user_uid)

    # ========================================================================
    # CURRICULUM-BASED TASK CREATION
    # ========================================================================

    @with_error_handling("create_task_from_path_step", error_type="database")
    async def create_task_from_path_step(
        self,
        step_uid: str,
        task_title: str,
        knowledge_uids: list[str],
        user_uid: UserUID,
    ) -> Result[Task]:
        """
        Create a practice task for a path step.

        The entity is hand-built because the curriculum linkage rides on
        ``source_path_step_uid``, a persisted Task field no create request carries —
        then handed to ``TasksCoreService.create``, THE create primitive's entity
        door, so the task is announced like every other (``TaskCreated`` → context
        invalidation, then the ADR-074 embedding request). It used to reach
        ``backend.create`` directly, which published neither: a curriculum task the
        user's cached context could not see for its full 300s TTL, and that was never
        embedded.

        DEFERRED IMPLEMENTATION (Graph-Native):
        ``knowledge_uids`` is accepted but unused. The primitive writes guarded
        APPLIES_KNOWLEDGE edges only from a create REQUEST's
        ``applies_knowledge_uids`` — the list is edge-typed and rides on no Task
        field, and this door builds an entity. Completing this means handing the
        primitive the list through its request door without losing
        ``source_path_step_uid``.

        Args:
            step_uid: PathStep UID,
            task_title: Task title,
            knowledge_uids: Knowledge UIDs to link (currently unused - see deferral note)
            user_uid: User identifier

        Returns:
            Result containing created task (without knowledge relationships yet)
        """
        # Build the frozen Task with curriculum linkage (ADR-035/ADR-065).
        task_model = Task(
            uid=EntityUID(UIDGenerator.generate_random_uid("task")),
            entity_type=EntityType.TASK,
            user_uid=user_uid,
            title=task_title,
            source_path_step_uid=step_uid,
            # DEFERRED: Knowledge relationship creation (see docstring)
            knowledge_mastery_check=True,
            scheduled_date=date.today() + timedelta(days=1),
            status=EntityStatus.DRAFT,
            priority=Priority.MEDIUM,
        )

        result = await self.core.create(task_model)
        if result.is_error:
            return result

        self.logger.info("Created curriculum task %s for step %s", result.value.uid, step_uid)
        return result
