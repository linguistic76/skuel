"""
Tasks Search Service - Search and Filtering
============================================

*Last updated: 2026-01-04*

Clean rewrite following CLAUDE.md patterns.
Handles advanced task search and discovery operations.

**Responsibilities:**
- Search tasks by relationships (goal, habit, knowledge)
- Smart task prioritization
- Semantic knowledge search
- Curriculum task filtering
- Graph-aware faceted search ()

**Dependencies:**
- TasksOperations (backend protocol)
- UserContextService (optional - for context-aware operations)
"""

from __future__ import annotations

from operator import attrgetter
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations

from core.constants import QueryLimit
from core.models.enums import EntityStatus
from core.models.relationship_names import RelationshipName
from core.models.search.scoring import score_task
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


class TasksSearchService(BaseService["TasksOperations", Task]):
    """
    Advanced search and discovery for tasks.
    """

    # DomainConfig consolidation (January 2026)
    # All configuration in one place, using centralized relationship registry
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )

    def __init__(self, backend: TasksOperations) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="tasks.search")

    # ========================================================================
    # RELATIONSHIP-BASED SEARCH
    # ========================================================================

    @with_error_handling("get_tasks_for_goal", error_type="database", uid_param="goal_uid")
    async def get_tasks_for_goal(self, goal_uid: str) -> Result[list[Task]]:
        """
        Get all tasks that fulfill a specific goal.

        Reads the ``fulfills_goal_uid`` node column — the property half of the
        dual-written goal link (property == FULFILLS_GOAL edge target on every door; see
        ``TasksCoreService._write_link_edges``), so vault-ingested tasks are found too.

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing tasks fulfilling this goal, sorted by contribution
        """
        # Query backend for tasks with this goal
        result = await self.backend.find_by(fulfills_goal_uid=goal_uid)

        if result.is_error:
            return result

        tasks = self._to_domain_models(result.value, TaskDTO, Task)

        # Sort by contribution percentage
        tasks.sort(key=attrgetter("goal_progress_contribution"), reverse=True)

        self.logger.debug(f"Found {len(tasks)} tasks for goal {goal_uid}")
        return Result.ok(tasks)

    @with_error_handling("get_tasks_for_habit", error_type="database", uid_param="habit_uid")
    async def get_tasks_for_habit(self, habit_uid: str) -> Result[list[Task]]:
        """
        Get all tasks that reinforce a specific habit.

        Graph-native: traverses the (Task)-[:REINFORCES_HABIT]->(Habit) edge
        rather than reading a property.

        Args:
            habit_uid: Habit UID

        Returns:
            Result containing tasks reinforcing this habit
        """
        result = await self.backend.get_tasks_reinforcing_habit(habit_uid)

        if result.is_error:
            return Result.fail(result)

        tasks = self._to_domain_models(result.value, TaskDTO, Task)

        self.logger.debug(f"Found {len(tasks)} tasks for habit {habit_uid}")
        return Result.ok(tasks)

    @with_error_handling(
        "get_tasks_applying_knowledge", error_type="database", uid_param="knowledge_uid"
    )
    async def get_tasks_applying_knowledge(self, knowledge_uid: str) -> Result[list[Task]]:
        """
        Get all tasks that apply specific knowledge.

        GRAPH-NATIVE: Query graph for APPLIES_KNOWLEDGE relationships.

        Args:
            knowledge_uid: Knowledge UID

        Returns:
            Result containing tasks applying this knowledge
        """
        # GRAPH-NATIVE: Query graph for tasks with APPLIES_KNOWLEDGE relationship to this knowledge
        task_uids_result = await self.backend.get_related_uids(
            knowledge_uid, RelationshipName.APPLIES_KNOWLEDGE, direction="incoming"
        )
        if task_uids_result.is_error:
            return Result.fail(task_uids_result)

        task_uids = task_uids_result.value

        # Fetch task details for each UID
        tasks = []
        for task_uid in task_uids:
            task_result = await self.backend.get(task_uid)
            if task_result.is_ok and task_result.value:
                task = self._to_domain_model(task_result.value, TaskDTO, Task)
                tasks.append(task)

        self.logger.debug(f"Found {len(tasks)} tasks applying knowledge {knowledge_uid}")
        return Result.ok(tasks)

    @with_error_handling(
        "get_blocked_by_prerequisites", error_type="database", uid_param="user_uid"
    )
    async def get_blocked_by_prerequisites(self, user_uid: UserUID) -> Result[list[Task]]:
        """
        Get tasks blocked by missing prerequisites.

        A task is considered blocked if it has prerequisites (knowledge or tasks)
        that need to be satisfied before it can be started.

        Uses graph-native relationship queries.

        Args:
            user_uid: User UID

        Returns:
            Result containing blocked tasks
        """
        # Get user's tasks
        tasks_result = await self.backend.get_user_entities(user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        # Unpack tuple (entities, total_count) from get_user_entities
        entities, _total = tasks_result.value

        # Filter tasks that have any prerequisites (using graph relationships)
        all_tasks = self._to_domain_models(entities, TaskDTO, Task)
        blocked_tasks = []

        for task in all_tasks:
            # Check for knowledge prerequisites
            knowledge_prereqs_result = await self.backend.count_related(
                uid=task.uid,
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            )
            has_knowledge_prereqs = (
                knowledge_prereqs_result.is_ok and knowledge_prereqs_result.value > 0
            )

            # Check for task prerequisites
            task_prereqs_result = await self.backend.count_related(
                uid=task.uid,
                relationship_type=RelationshipName.REQUIRES_PREREQUISITE,
                direction="outgoing",
            )
            has_task_prereqs = task_prereqs_result.is_ok and task_prereqs_result.value > 0

            # Task is blocked if it has any prerequisites
            if has_knowledge_prereqs or has_task_prereqs:
                blocked_tasks.append(task)

        self.logger.debug(f"Found {len(blocked_tasks)} blocked tasks for user {user_uid}")
        return Result.ok(blocked_tasks)

    # ========================================================================
    # SMART PRIORITIZATION
    # ========================================================================

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Task]]:
        """
        Get prioritized tasks using the unified cross-domain scorer.

        Delegates to ``score_task`` in ``core.models.search.scoring``, which
        blends deadline proximity, priority level, goal alignment (Goals),
        habit streak protection (Habits), knowledge-gap coverage (KU),
        learning-path alignment, and the user's current focus.

        Args:
            user_context: User context for prioritization
            limit: Maximum tasks to return

        Returns:
            Result containing prioritized tasks (highest score first)
        """
        tasks_result = await self.backend.get_user_entities(user_context.user_uid)
        if tasks_result.is_error:
            return Result.fail(tasks_result)

        entities, _total = tasks_result.value
        all_tasks = self._to_domain_models(entities, TaskDTO, Task)
        tasks = [task for task in all_tasks if task.status != EntityStatus.COMPLETED]

        # Populate the derived reinforces_habit_uid field from the REINFORCES_HABIT
        # edge so the pure streak-protection scorer can read it (graph is the
        # source of truth; the field is never persisted).
        links = await self.backend.get_habit_links_for_tasks([t.uid for t in tasks])
        if links.is_ok and links.value:
            from dataclasses import replace

            tasks = [
                replace(task, reinforces_habit_uid=links.value[task.uid])
                if task.uid in links.value
                else task
                for task in tasks
            ]

        scored = [(task, score_task(task, user_context).total) for task in tasks]
        scored.sort(key=get_result_score, reverse=True)
        prioritized = [task for task, _ in scored[:limit]]

        self.logger.debug(f"Prioritized {len(prioritized)} tasks for user {user_context.user_uid}")
        return Result.ok(prioritized)

    # ========================================================================
    # CURRICULUM TASK DISCOVERY
    # ========================================================================

    @with_error_handling("get_curriculum_tasks", error_type="database")
    async def get_curriculum_tasks(self) -> Result[list[Task]]:
        """
        Get all tasks that originated from the curriculum.

        Uses Task.is_from_path_step() to filter curriculum-driven tasks.

        Returns:
            Result containing list of tasks linked to path steps
        """
        # Get all tasks
        all_tasks_result = await self.backend.list(QueryLimit.COMPREHENSIVE)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result)

        # Unpack tuple: backend.list() returns (tasks, total_count)
        tasks_data, _ = all_tasks_result.value

        # Filter using model method
        all_tasks = self._to_domain_models(tasks_data, TaskDTO, Task)
        curriculum_tasks = [task for task in all_tasks if task.is_from_path_step]

        self.logger.info(f"Found {len(curriculum_tasks)} curriculum-driven tasks")
        return Result.ok(curriculum_tasks)

    @with_error_handling("get_tasks_for_path_step", error_type="database", uid_param="step_uid")
    async def get_tasks_for_path_step(self, step_uid: str) -> Result[list[Task]]:
        """
        Get all tasks linked to a specific path step.

        Args:
            step_uid: PathStep UID

        Returns:
            Result containing list of tasks for this path step
        """
        # Get all tasks
        all_tasks_result = await self.backend.list(QueryLimit.COMPREHENSIVE)
        if all_tasks_result.is_error:
            return Result.fail(all_tasks_result)

        # Unpack tuple: backend.list() returns (tasks, total_count)
        tasks_data, _ = all_tasks_result.value

        # Filter using model method
        all_tasks = self._to_domain_models(tasks_data, TaskDTO, Task)
        step_tasks = [task for task in all_tasks if task.source_path_step_uid == step_uid]

        self.logger.info(f"Found {len(step_tasks)} tasks for path step {step_uid}")
        return Result.ok(step_tasks)

    # ========================================================================
    # GRAPH-BASED SEARCH
    # ========================================================================
    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_user_assigned_tasks", error_type="database", uid_param="user_uid")
    async def get_user_assigned_tasks(
        self, user_uid: UserUID, include_completed: bool = False, limit: int = 100
    ) -> Result[list[Task]]:
        """
        Get tasks assigned to user via graph traversal.

        Query: (Task)-[:ASSIGNED_TO]->(User)

        Args:
            user_uid: User UID,
            include_completed: Whether to include completed tasks,
            limit: Maximum number of tasks

        Returns:
            Result containing assigned tasks
        """
        result = await self.backend.get_assigned_tasks(
            user_uid=user_uid, include_completed=include_completed, limit=limit
        )
        if result.is_error:
            return Result.fail(result)

        tasks = self._to_domain_models(result.value, TaskDTO, Task)

        self.logger.debug(f"Found {len(tasks)} assigned tasks for user {user_uid}")
        return Result.ok(tasks)

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================
