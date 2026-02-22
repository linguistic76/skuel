"""
Goal Task Generator Service
============================

Automatically generates tasks from goals based on milestones, knowledge requirements,
and habit dependencies. Uses UserContext for intelligent task creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from core.models.enums import EntityStatus, Priority, RecurrencePattern
from core.models.ku.goal import Goal
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_dto import KuDTO as TaskDTO
from core.services.goals.goal_relationships import GoalRelationships

# Import protocol interfaces
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_task_urgency

if TYPE_CHECKING:
    from core.ports import GoalsOperations, TasksOperations
    from core.services.user import UserContext


@dataclass
class TaskGenerationConfig:
    """Configuration for task generation."""

    generate_milestone_tasks: bool = True
    generate_knowledge_tasks: bool = True
    generate_habit_tasks: bool = True
    generate_check_in_tasks: bool = True
    max_tasks_per_goal: int = 20
    default_task_duration_minutes: int = 60
    knowledge_task_duration_minutes: int = 90
    habit_task_duration_minutes: int = 30
    check_in_frequency_days: int = 7


class GoalTaskGenerator:
    """
    Service that automatically generates tasks from goals.

    This service analyzes goals and creates:
    1. Milestone completion tasks
    2. Knowledge acquisition tasks
    3. Habit reinforcement tasks
    4. Progress check-in tasks
    """

    def __init__(
        self,
        goals_backend: GoalsOperations,
        tasks_backend: TasksOperations,
        relationship_service=None,
        tasks_relationship_service=None,
        config: TaskGenerationConfig | None = None,
    ) -> None:
        """
        Initialize task generator.

        Args:
            goals_backend: Backend for goal operations,
            tasks_backend: Backend for task operations,
            relationship_service: GoalsRelationshipService for fetching goal relationships,
            tasks_relationship_service: TasksRelationshipService for creating task-knowledge relationships,
            config: Generation configuration

        Note:
            Context invalidation now happens via event-driven architecture.
            Created tasks trigger TaskCreated events which invalidate context.
        """
        if not goals_backend:
            raise ValueError("Goals backend is required")
        if not tasks_backend:
            raise ValueError("Tasks backend is required")

        self.goals_backend = goals_backend
        self.tasks_backend = tasks_backend
        self.relationships = relationship_service
        self.tasks_relationships = tasks_relationship_service
        self.config = config or TaskGenerationConfig()
        self.logger = get_logger("skuel.services.goal_task_generator")

    # ========================================================================
    # AUTOMATIC TASK GENERATION
    # ========================================================================

    async def generate_tasks_for_goal(
        self, goal_uid: str, user_context: UserContext, auto_create: bool = False
    ) -> Result[list[TaskDTO]]:
        """
        Generate tasks for a specific goal.

        Args:
            goal_uid: Goal to generate tasks for,
            user_context: User's current context,
            auto_create: If True, automatically create tasks; if False, return templates

        Returns:
            List of created or template tasks
        """
        # Get the goal
        goal_result = await self.goals_backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = to_domain_model(goal_result.value, KuDTO, Goal)

        # GRAPH-NATIVE: Fetch goal relationships from graph
        rels = (
            await GoalRelationships.fetch(goal_uid, self.relationships)
            if self.relationships
            else GoalRelationships()
        )

        generated_tasks = []

        # Generate different types of tasks
        if self.config.generate_milestone_tasks:
            milestone_tasks = await self._generate_milestone_tasks(goal, user_context)
            generated_tasks.extend(milestone_tasks)

        if self.config.generate_knowledge_tasks:
            knowledge_tasks = await self._generate_knowledge_tasks(goal, rels, user_context)
            generated_tasks.extend(knowledge_tasks)

        if self.config.generate_habit_tasks:
            habit_tasks = await self._generate_habit_tasks(goal, user_context)
            generated_tasks.extend(habit_tasks)

        if self.config.generate_check_in_tasks:
            checkin_tasks = await self._generate_checkin_tasks(goal, user_context)
            generated_tasks.extend(checkin_tasks)

        # Limit total tasks
        generated_tasks = generated_tasks[: self.config.max_tasks_per_goal]

        # Create tasks if requested
        created_tasks = []
        if auto_create:
            for task_template in generated_tasks:
                create_result = await self.tasks_backend.create_task(task_template.to_dict())
                if create_result.is_ok:
                    created_dto = to_domain_model(create_result.value, TaskDTO, TaskDTO)
                    created_tasks.append(created_dto)

                    # Create graph relationships for knowledge requirements
                    if self.tasks_relationships:
                        await self._create_task_knowledge_relationships(created_dto)
                else:
                    self.logger.warning(f"Failed to create task: {create_result.error}")

            # Context invalidation happens via TaskCreated events (event-driven architecture)
            # Event handlers in bootstrap will call user_service.invalidate_context()

            self.logger.info(
                "Generated and created %d tasks for goal %s", len(created_tasks), goal_uid
            )

            return Result.ok(created_tasks)

        self.logger.info("Generated %d task templates for goal %s", len(generated_tasks), goal_uid)

        return Result.ok(generated_tasks)

    # ========================================================================
    # BULK GENERATION
    # ========================================================================

    async def generate_tasks_for_all_goals(
        self, user_context: UserContext, auto_create: bool = False
    ) -> Result[dict[str, list[TaskDTO]]]:
        """
        Generate tasks for all active goals.

        Args:
            user_context: User's current context,
            auto_create: If True, automatically create tasks

        Returns:
            Dictionary mapping goal_uid to generated tasks
        """
        all_generated = {}

        for goal_uid in user_context.active_goal_uids:
            # Skip goals that already have sufficient tasks
            existing_tasks = user_context.tasks_by_goal.get(goal_uid, [])
            if len(existing_tasks) >= self.config.max_tasks_per_goal:
                continue

            result = await self.generate_tasks_for_goal(goal_uid, user_context, auto_create)
            if result.is_ok:
                all_generated[goal_uid] = result.value

        self.logger.info("Generated tasks for %d goals", len(all_generated))

        return Result.ok(all_generated)

    # ========================================================================
    # SMART TASK GENERATION
    # ========================================================================

    async def generate_next_critical_tasks(
        self, user_context: UserContext, limit: int = 5
    ) -> Result[list[TaskDTO]]:
        """
        Generate the next critical tasks across all goals.

        Prioritizes:
        1. Overdue milestones
        2. Blocking knowledge prerequisites
        3. At-risk habit reinforcement
        4. Time-sensitive goals
        """
        critical_tasks = []

        # Check each active goal
        for goal_uid in user_context.active_goal_uids:
            goal_result = await self.goals_backend.get_goal(goal_uid)
            if goal_result.is_error:
                continue

            goal = to_domain_model(goal_result.value, KuDTO, Goal)

            # Check if goal is at risk
            if goal.days_remaining() and goal.days_remaining() < 30:
                # Generate urgent milestone tasks
                urgent_tasks = await self._generate_urgent_tasks(goal, user_context)
                critical_tasks.extend(urgent_tasks)

        # Sort by priority and limit (using centralized sort function)
        critical_tasks.sort(key=get_task_urgency)
        critical_tasks = critical_tasks[:limit]

        return Result.ok(critical_tasks)

    # ========================================================================
    # PRIVATE GENERATION METHODS
    # ========================================================================

    async def _generate_milestone_tasks(
        self, goal: Goal, _user_context: UserContext
    ) -> list[TaskDTO]:
        """Generate tasks for goal milestones."""
        tasks: list[TaskDTO] = []

        if not goal.milestones:
            return tasks

        days_remaining = goal.days_remaining() or 365
        days_per_milestone = days_remaining / len(goal.milestones)

        for i, milestone in enumerate(goal.milestones):
            # Skip completed milestones
            if milestone.is_completed:
                continue

            # Calculate due date for milestone
            due_date = date.today() + timedelta(days=int(days_per_milestone * (i + 1)))

            task = TaskDTO.create_task(
                user_uid=goal.user_uid,
                title=f"Complete: {milestone.title}",
                priority=self._calculate_priority(goal, due_date),
                due_date=due_date,
                duration_minutes=self.config.default_task_duration_minutes,
            )

            # Add learning integration
            task.fulfills_goal_uid = goal.uid
            task.goal_progress_contribution = 100.0 / len(goal.milestones)
            task.completion_updates_goal = True
            # Store milestone index in metadata instead
            task.metadata["milestone_index"] = i
            task.metadata["milestone_uid"] = milestone.uid

            # Add knowledge if milestone has required knowledge
            if milestone.required_knowledge_uids:
                # GRAPH-NATIVE: Store knowledge UIDs in metadata for relationship creation after task creation
                task.metadata["required_knowledge_uids"] = milestone.required_knowledge_uids
                task.knowledge_mastery_check = True

            tasks.append(task)

        return tasks

    async def _generate_knowledge_tasks(
        self, goal: Goal, rels: GoalRelationships, user_context: UserContext
    ) -> list[TaskDTO]:
        """
        Generate tasks for acquiring required knowledge.

        GRAPH-NATIVE: Uses GoalRelationships for required_knowledge_uids.
        """
        tasks: list[TaskDTO] = []

        # GRAPH-NATIVE: Access from graph relationships, not goal model
        if not rels.required_knowledge_uids:
            return tasks

        for knowledge_uid in rels.required_knowledge_uids:
            # Skip if already mastered
            if knowledge_uid in user_context.mastered_knowledge_uids:
                continue

            # Check if prerequisites are met
            prereqs_met = True
            if knowledge_uid in user_context.prerequisites_needed:
                missing = (
                    set(user_context.prerequisites_needed[knowledge_uid])
                    - user_context.prerequisites_completed
                )
                prereqs_met = len(missing) == 0

            task = TaskDTO.create_task(
                user_uid=goal.user_uid,
                title=f"Learn: {knowledge_uid}",
                priority=Priority.HIGH if not prereqs_met else Priority.MEDIUM,
                duration_minutes=self.config.knowledge_task_duration_minutes,
            )

            # Add learning integration
            task.fulfills_goal_uid = goal.uid
            # GRAPH-NATIVE: Store knowledge UID in metadata for relationship creation after task creation
            task.metadata["required_knowledge_uid"] = knowledge_uid
            task.metadata["is_learning_opportunity"] = True
            task.knowledge_mastery_check = True

            # Store prerequisites if any
            if not prereqs_met and knowledge_uid in user_context.prerequisites_needed:
                missing = (
                    set(user_context.prerequisites_needed[knowledge_uid])
                    - user_context.prerequisites_completed
                )
                task.metadata["prerequisite_knowledge_uids"] = list(missing)

            # Block task if prerequisites not met
            if not prereqs_met:
                task.status = EntityStatus.BLOCKED
                task.metadata["blocked_reason"] = "Prerequisites not met"

            tasks.append(task)

        return tasks

    async def _generate_habit_tasks(
        self, goal: Goal, user_context: UserContext, rels: GoalRelationships | None = None
    ) -> list[TaskDTO]:
        """Generate tasks for reinforcing supporting habits."""
        tasks: list[TaskDTO] = []

        if not rels or not rels.supporting_habit_uids:
            return tasks

        for habit_uid in rels.supporting_habit_uids:
            # Check if habit needs reinforcement
            current_streak = user_context.habit_streaks.get(habit_uid, 0)

            if current_streak < 7:  # Less than 1 week streak
                # Generate daily tasks for next week
                for day_offset in range(1, 8):
                    task_date = date.today() + timedelta(days=day_offset)

                    task = TaskDTO.create_task(
                        user_uid=goal.user_uid,
                        title=f"Practice habit: {habit_uid}",
                        priority=Priority.MEDIUM,
                        due_date=task_date,
                        duration_minutes=self.config.habit_task_duration_minutes,
                    )

                    # Add habit integration
                    task.fulfills_goal_uid = goal.uid
                    task.reinforces_habit_uid = habit_uid
                    task.habit_streak_maintainer = True
                    task.metadata["recurring"] = True
                    task.recurrence_pattern = RecurrencePattern.DAILY

                    tasks.append(task)

                    # Only generate first task if not creating all
                    break

        return tasks

    async def _generate_checkin_tasks(
        self, goal: Goal, _user_context: UserContext
    ) -> list[TaskDTO]:
        """Generate periodic check-in tasks for goal progress."""
        tasks = []

        # Generate weekly check-ins until goal deadline
        days_remaining = goal.days_remaining() or 90
        check_in_count = min(days_remaining // self.config.check_in_frequency_days, 12)

        for i in range(1, check_in_count + 1):
            check_in_date = date.today() + timedelta(days=i * self.config.check_in_frequency_days)

            task = TaskDTO.create_task(
                user_uid=goal.user_uid,
                title=f"Progress check: {goal.title}",
                priority=Priority.LOW,
                due_date=check_in_date,
                duration_minutes=15,
            )

            # Add goal integration
            task.fulfills_goal_uid = goal.uid
            task.metadata["is_check_in"] = True
            task.metadata["check_in_type"] = "progress_review"

            tasks.append(task)

        return tasks

    async def _generate_urgent_tasks(
        self, goal: Goal, _user_context: UserContext
    ) -> list[TaskDTO]:
        """Generate urgent tasks for at-risk goals."""
        tasks = []

        # Find most critical incomplete milestone
        if goal.milestones:
            for _i, milestone in enumerate(goal.milestones):
                if not milestone.is_completed:
                    task = TaskDTO.create_task(
                        user_uid=goal.user_uid,
                        title=f"URGENT: {milestone.title}",
                        priority=Priority.CRITICAL,
                        due_date=date.today() + timedelta(days=3),
                        duration_minutes=self.config.default_task_duration_minutes * 2,
                    )

                    task.fulfills_goal_uid = goal.uid
                    task.goal_progress_contribution = 100.0 / len(goal.milestones)
                    task.metadata["is_urgent"] = True

                    tasks.append(task)
                    break  # Only one urgent task

        return tasks

    def _calculate_priority(self, goal: Goal, task_due_date: date) -> Priority:
        """Calculate task priority based on goal urgency and due date."""
        days_until_due = (task_due_date - date.today()).days
        goal_days_remaining = goal.days_remaining() or 365

        if days_until_due <= 3 or goal_days_remaining <= 7:
            return Priority.CRITICAL
        elif days_until_due <= 7 or goal_days_remaining <= 30:
            return Priority.HIGH
        elif days_until_due <= 30 or goal_days_remaining <= 90:
            return Priority.MEDIUM
        else:
            return Priority.LOW

    # ========================================================================
    # GRAPH RELATIONSHIP CREATION
    # ========================================================================

    async def _create_task_knowledge_relationships(self, task: TaskDTO) -> None:
        """
        Create graph relationships for task-knowledge connections.

        Reads metadata from task and creates appropriate relationships:
        - required_knowledge_uid (single): REQUIRES_KNOWLEDGE
        - required_knowledge_uids (multiple): REQUIRES_KNOWLEDGE for each
        - prerequisite_knowledge_uids: REQUIRES_PREREQUISITE for each

        Args:
            task: Created task DTO with metadata
        """
        # Handle single required knowledge UID (from knowledge tasks)
        if "required_knowledge_uid" in task.metadata:
            knowledge_uid = task.metadata["required_knowledge_uid"]
            is_learning = task.metadata.get("is_learning_opportunity", False)

            result = await self.tasks_relationships.link_task_to_knowledge(
                task_uid=task.uid,
                knowledge_uid=knowledge_uid,
                is_learning_opportunity=is_learning,
            )

            if result.is_ok:
                self.logger.debug(
                    f"Created REQUIRES_KNOWLEDGE relationship: {task.uid} -> {knowledge_uid}"
                )
            else:
                self.logger.warning(
                    f"Failed to create REQUIRES_KNOWLEDGE relationship: {result.error}"
                )

        # Handle multiple required knowledge UIDs (from milestone tasks)
        if "required_knowledge_uids" in task.metadata:
            knowledge_uids = task.metadata["required_knowledge_uids"]
            for knowledge_uid in knowledge_uids:
                result = await self.tasks_relationships.link_task_to_knowledge(
                    task_uid=task.uid,
                    knowledge_uid=knowledge_uid,
                    is_learning_opportunity=False,
                )

                if result.is_ok:
                    self.logger.debug(
                        f"Created REQUIRES_KNOWLEDGE relationship: {task.uid} -> {knowledge_uid}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to create REQUIRES_KNOWLEDGE relationship: {result.error}"
                    )

        # Handle prerequisite knowledge UIDs
        if "prerequisite_knowledge_uids" in task.metadata:
            prereq_uids = task.metadata["prerequisite_knowledge_uids"]
            for prereq_uid in prereq_uids:
                # Use REQUIRES_KNOWLEDGE for prerequisites too (same relationship type)
                result = await self.tasks_relationships.link_task_to_knowledge(
                    task_uid=task.uid,
                    knowledge_uid=prereq_uid,
                    knowledge_score_required=0.8,  # Higher threshold for prerequisites
                )

                if result.is_ok:
                    self.logger.debug(
                        f"Created prerequisite REQUIRES_KNOWLEDGE: {task.uid} -> {prereq_uid}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to create prerequisite relationship: {result.error}"
                    )

    # ========================================================================
    # TASK TEMPLATE LIBRARY
    # ========================================================================

    def get_task_templates(self, goal: Goal) -> dict[str, TaskDTO]:
        """
        Get library of reusable task templates.

        Args:
            goal: Goal to generate task templates for
        """
        return {
            "milestone": TaskDTO.create_task(
                user_uid=goal.user_uid,
                title="Complete milestone",
                priority=Priority.HIGH,
                duration_minutes=60,
                tags=["milestone", "goal"],
            ),
            "learn_knowledge": TaskDTO.create_task(
                user_uid=goal.user_uid,
                title="Study knowledge area",
                priority=Priority.MEDIUM,
                duration_minutes=90,
                tags=["learning", "knowledge"],
            ),
            "practice_habit": TaskDTO.create_task(
                user_uid=goal.user_uid,
                title="Practice habit",
                priority=Priority.MEDIUM,
                duration_minutes=30,
                tags=["habit", "practice"],
            ),
            "progress_review": TaskDTO.create_task(
                user_uid=goal.user_uid,
                title="Review progress",
                priority=Priority.LOW,
                duration_minutes=15,
                tags=["review", "check-in"],
            ),
        }
