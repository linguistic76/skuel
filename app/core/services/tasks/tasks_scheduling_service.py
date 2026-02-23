"""
Tasks Scheduling Service - Scheduling and Recurrence
=====================================================

Clean rewrite following CLAUDE.md patterns.
Handles task scheduling, context-aware creation, and learning path integration.

**Responsibilities:**
- Context-aware task creation
- Learning path integration
- Task suggestions and generation
- Curriculum-based task creation

**Dependencies:**
- TasksOperations (backend protocol)
- UserContextOperations (optional protocol - for context-aware operations)
"""

from __future__ import annotations

from datetime import date, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import BackendOperations

from core.models.enums import Domain, EntityStatus, Priority
from core.models.ku.ku_request import TaskCreateRequest
from core.models.ku.lp_position import LpPosition
from core.models.ku.task import Task
from core.models.ku.task_dto import TaskDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import PrerequisiteHelper
from core.services.infrastructure.learning_alignment_helper import LearningAlignmentHelper
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

# ========================================================================
# CUSTOM VALIDATOR FOR TASKS DOMAIN
# ========================================================================


def _validate_task_prerequisites(
    request: TaskCreateRequest, context: UserContext | None
) -> Result[None]:
    """
    Validate task prerequisites against user's completed knowledge/tasks.

    Delegates to PrerequisiteHelper for unified logic.

    Args:
        request: Task creation request
        context: User context with completed_ku_uids and completed_task_uids

    Returns:
        Result.ok() if valid, Result.fail() with missing prerequisites
    """
    # Extract prerequisite UIDs from request
    applies_knowledge_uids = getattr(request, "applies_knowledge_uids", None)
    prerequisite_task_uids = getattr(request, "prerequisite_task_uids", None)

    return PrerequisiteHelper.validate_prerequisites(
        required_knowledge_uids=list(applies_knowledge_uids) if applies_knowledge_uids else None,
        required_task_uids=list(prerequisite_task_uids) if prerequisite_task_uids else None,
        context=context,
    )


class TasksSchedulingService(BaseService["BackendOperations[Task]", Task]):
    """
    Task scheduling and learning path integration.


    Source Tag: "tasks_scheduling_service_explicit"
    - Format: "tasks_scheduling_service_explicit" for user-created relationships
    - Format: "tasks_scheduling_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from tasks_scheduling metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

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
        entity_label="Ku",
    )

    def __init__(self, backend: BackendOperations[Task]) -> None:
        """
        Initialize scheduling service with required dependencies.

        Args:
            backend: TasksOperations backend (required)

        Note:
            Context invalidation now happens via event-driven architecture.
            TaskCreated events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend=backend, service_name="tasks.scheduling")

        # Initialize LearningAlignmentHelper with prerequisite validator (Phase 6)
        self.learning_helper = LearningAlignmentHelper[Task, TaskDTO, TaskCreateRequest](
            service=self,
            backend_get_method="get",
            backend_get_user_method="list_user_tasks",
            backend_create_method="create_task",
            dto_class=TaskDTO,
            model_class=Task,
            domain=Domain.TECH,  # Default domain for tasks
            entity_name="task",
            prerequisite_validator=_validate_task_prerequisites,
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Task entities."""
        return "Ku"

    # ========================================================================
    # CONTEXT-AWARE CREATION
    # ========================================================================

    @with_error_handling("create_task_with_context", error_type="database")
    async def create_task_with_context(
        self, task_data: TaskCreateRequest, user_context: UserContext
    ) -> Result[Task]:
        """
        Create a task with full context awareness.

        Pattern 1 (Graph-Aware Models): Prerequisite validation using context fields.

        This method:
        1. Checks prerequisites from context using set operations (O(1))
        2. Sets up bidirectional relationships via UID fields
        3. Updates context after creation

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

        # Create DTO from request
        dto = TaskDTO.create_task(
            user_uid=user_context.user_uid,
            title=task_data.title,
            priority=task_data.priority,
            due_date=task_data.due_date,
            duration_minutes=task_data.duration_minutes,
            project=task_data.project,
            tags=task_data.tags,
        )

        # Add learning integration fields (single UID properties only)
        dto.fulfills_goal_uid = task_data.fulfills_goal_uid
        dto.reinforces_habit_uid = task_data.reinforces_habit_uid
        dto.goal_progress_contribution = getattr(task_data, "goal_progress_contribution", 0.0)
        dto.knowledge_mastery_check = getattr(task_data, "knowledge_mastery_check", False)
        dto.habit_streak_maintainer = getattr(task_data, "habit_streak_maintainer", False)

        # Create task in backend
        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        task = self._to_domain_model(create_result.value, TaskDTO, Task)

        # GRAPH-NATIVE: Create relationship edges in graph (not stored on Task/DTO)
        # Collect all relationships for batch creation (10x faster)
        relationships = []

        # Knowledge application relationships
        if task_data.applies_knowledge_uids:
            relationships.extend(
                (task.uid, knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None)
                for knowledge_uid in task_data.applies_knowledge_uids
            )

        # Principle alignment relationships
        if task_data.aligned_principle_uids:
            relationships.extend(
                (task.uid, principle_uid, "ALIGNED_WITH", None)
                for principle_uid in task_data.aligned_principle_uids
            )

        # Prerequisite knowledge relationships
        if task_data.prerequisite_knowledge_uids:
            relationships.extend(
                (task.uid, knowledge_uid, RelationshipName.REQUIRES_KNOWLEDGE.value, None)
                for knowledge_uid in task_data.prerequisite_knowledge_uids
            )

        # Prerequisite task relationships
        if task_data.prerequisite_task_uids:
            relationships.extend(
                (task.uid, prereq_uid, "BLOCKED_BY", None)
                for prereq_uid in task_data.prerequisite_task_uids
            )

        # Create all relationships in single batch operation
        if relationships:
            batch_result = await self.backend.create_relationships_batch(relationships)
            if batch_result.is_error:
                self.logger.warning(
                    f"Failed to create {len(relationships)} relationships for task {task.uid}: {batch_result.error}"
                )

        # Context invalidation happens via TaskCreated event (event-driven architecture)
        # Note: TaskCreated event is published by TasksCoreService
        # Event handlers in bootstrap will call user_service.invalidate_context()

        self.logger.info(
            "Created task %s with context: goal=%s, habit=%s, knowledge=%s",
            task.uid,
            task.fulfills_goal_uid,
            task.reinforces_habit_uid,
            len(task_data.applies_knowledge_uids),
        )

        return Result.ok(task)

    @with_error_handling("create_task_with_learning_context", error_type="database")
    async def create_task_with_learning_context(
        self,
        task_request: TaskCreateRequest,
        learning_position: LpPosition | None = None,
        context: UserContext | None = None,
    ) -> Result[Task]:
        """
        Create a task enhanced with learning path position context.

        Uses LearningAlignmentHelper with prerequisite validation.

        Args:
            task_request: Task creation request,
            learning_position: User's learning path position context,
            context: User context for prerequisite validation

        Returns:
            Result containing created Task with learning path enhancement
        """
        # Use LearningAlignmentHelper with prerequisite validator (Phase 6 consolidation)
        return await self.learning_helper.create_with_learning_alignment(
            request=task_request, learning_position=learning_position, context=context
        )

    # ========================================================================
    # LEARNING PATH INTEGRATION
    # ========================================================================

    async def create_tasks_from_learning_path(
        self, learning_path_uid: str, _user_context: UserContext
    ) -> Result[list[Task]]:
        """
        Create tasks from a learning path.

        This generates tasks for each knowledge unit in the path,
        respecting prerequisites and sequencing.

        Args:
            learning_path_uid: Learning path UID,
            user_context: User context

        Returns:
            Result containing list of created tasks
        """
        # This would get the learning path and create tasks
        # For now, return empty list
        self.logger.debug(
            f"Create tasks from learning path {learning_path_uid} - not yet implemented"
        )
        return Result.ok([])

    @with_error_handling("get_next_learning_task", error_type="database")
    async def get_next_learning_task(self, user_context: UserContext) -> Result[Task | None]:
        """
        Get the next recommended learning task based on context.

        Args:
            user_context: User context

        Returns:
            Result containing next learning task (or None)
        """
        # Find tasks that:
        # 1. Apply knowledge user is ready to learn
        # 2. Have prerequisites met
        # 3. Are not blocked

        ready_knowledge = user_context.get_ready_to_learn()
        if not ready_knowledge:
            return Result.ok(None)

        # Look for tasks that apply this knowledge
        # This would need proper implementation with knowledge service
        self.logger.debug(
            f"Get next learning task - found {len(ready_knowledge)} ready knowledge areas"
        )
        return Result.ok(None)

    # ========================================================================
    # TASK SUGGESTIONS
    # ========================================================================

    @with_error_handling("suggest_learning_aligned_tasks", error_type="database")
    async def suggest_learning_aligned_tasks(
        self, learning_position: LpPosition, _task_domain: str | None = None, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest new tasks aligned with learning path progression.

        Args:
            learning_position: User's learning path position,
            task_domain: Optional domain filter

        Returns:
            Result containing suggested tasks with learning context
        """
        suggestions = []

        # Generate suggestions based on current learning steps
        for path in learning_position.active_paths:
            current_step = learning_position.current_steps.get(path.uid)
            if current_step:
                # Use first primary knowledge UID for suggestions
                ku_uid = (
                    current_step.primary_knowledge_uids[0]
                    if current_step.primary_knowledge_uids
                    else current_step.title
                )

                # Suggest practice tasks for current step
                suggestion = {
                    "title": f"Practice {ku_uid}",
                    "description": f"Apply {ku_uid} knowledge from {path.title}",
                    "learning_path": path.title,
                    "knowledge_uid": ku_uid,
                    "estimated_minutes": int(
                        (current_step.estimated_hours or 0) * 60 / 3
                    ),  # Break into smaller tasks
                    "priority": Priority.MEDIUM.value,
                    "learning_relevance_score": 0.9,  # High relevance for current step
                    "suggestion_reason": f"Aligns with current step in {path.title}",
                }
                suggestions.append(suggestion)

                # Suggest preparation for next step (find step that comes after current in sequence)
                # Steps stored in path.metadata["steps"] (unified Ku model)
                path_steps = path.metadata.get("steps", []) if path.metadata else []
                try:
                    current_index = path_steps.index(current_step)
                    # Get next step in sequence (not just next ready step)
                    if current_index + 1 < len(path_steps):
                        next_step = path_steps[current_index + 1]
                        next_ku_uid = (
                            next_step.primary_knowledge_uids[0]
                            if next_step.primary_knowledge_uids
                            else next_step.title
                        )
                        prep_suggestion = {
                            "title": f"Prepare for {next_ku_uid}",
                            "description": f"Research and prepare for upcoming {next_ku_uid} in {path.title}",
                            "learning_path": path.title,
                            "knowledge_uid": next_ku_uid,
                            "estimated_minutes": 30,  # Short preparation task
                            "priority": Priority.LOW.value,
                            "learning_relevance_score": 0.7,
                            "suggestion_reason": f"Preparation for next step in {path.title}",
                        }
                        suggestions.append(prep_suggestion)
                except ValueError:
                    # Current step not found in path - skip next step suggestion
                    pass

        # Sort by learning relevance
        suggestions.sort(key=itemgetter("learning_relevance_score"), reverse=True)

        self.logger.info(
            "Generated %d learning-aligned task suggestions from %d active paths",
            len(suggestions),
            len(learning_position.active_paths),
        )

        return Result.ok(suggestions[:limit])  # Return top suggestions

    # ========================================================================
    # CURRICULUM-BASED TASK CREATION
    # ========================================================================

    @with_error_handling("create_task_from_learning_step", error_type="database")
    async def create_task_from_learning_step(
        self,
        step_uid: str,
        task_title: str,
        knowledge_uids: list[str],
        _user_uid: str,
    ) -> Result[Task]:
        """
        Create a practice task for a learning step.

        DEFERRED IMPLEMENTATION (Graph-Native):
        ==================================
        Parameter accepted but unused pending relationship creation implementation.

        Why Deferred:
        - Graph-native migration removed applies_knowledge_uids from TaskDTO
        - Need to create graph relationships after task creation
        - Requires calling self.relationships.add_task_knowledge() for each UID
        - Better ROI focusing on other refactorings first

        Future Implementation:
        1. Create task (current behavior - working)
        2. Loop through knowledge_uids
        3. Call self.relationships.add_task_knowledge(task.uid, ku_uid) for each
        4. Create (Task)-[:APPLIES_KNOWLEDGE]->(Knowledge) relationships in graph

        Args:
            step_uid: LearningStep UID,
            task_title: Task title,
            knowledge_uids: Knowledge UIDs to link (currently unused - see deferral note)
            user_uid: User identifier

        Returns:
            Result containing created task (without knowledge relationships yet)
        """
        # Create task with curriculum linkage
        task_dto = TaskDTO.create_task(
            user_uid=_user_uid,
            title=task_title,
            source_learning_step_uid=step_uid,
            # DEFERRED: Knowledge relationship creation (see docstring)
            knowledge_mastery_check=True,
            scheduled_date=date.today() + timedelta(days=1),
            status=EntityStatus.DRAFT.value,
            priority=Priority.MEDIUM.value,
        )

        # Create via backend
        create_result = await self.backend.create(task_dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        task = self._to_domain_model(create_result.value, TaskDTO, Task)

        self.logger.info(f"Created curriculum task {task.uid} for step {step_uid}")
        return Result.ok(task)
