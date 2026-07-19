"""
Orchestration Mixin — GoalsService
====================================

Multi-step orchestration methods that coordinate multiple sub-services:
create_goal_with_context, generate_tasks_for_goal, assess_goal_feasibility.

Part of goals_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import Priority
from core.utils.dto_converters import to_domain_model
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.goal.goal import Goal
    from core.models.goal.goal_request import GoalCreateRequest
    from core.services.goals.goals_core_service import GoalsCoreService
    from core.services.goals_types import GoalFeasibilityAssessment
    from core.services.user import UserContext


class _OrchestrationMixin:
    """
    Multi-step orchestration for GoalsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsService.__init__ / BaseService
    backend: Any
    core: GoalsCoreService
    learning: Any
    relationships: Any
    logger: Any

    async def create_goal_with_context(
        self, goal_data: GoalCreateRequest, user_context: UserContext
    ) -> Result[Goal]:
        """
        Create a goal with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Knowledge prerequisites validation
        2. Habit availability validation
        3. Goal creation via learning service
        4. Context invalidation
        """
        # Check knowledge prerequisites
        if goal_data.required_knowledge_uids:
            missing_prereqs = (
                set(goal_data.required_knowledge_uids) - user_context.mastered_knowledge_uids
            )
            if missing_prereqs:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal without required knowledge prerequisites",
                        field="required_knowledge_uids",
                        value=list(missing_prereqs),
                        user_message=f"Please master these knowledge areas first: {', '.join(missing_prereqs)}",
                    )
                )

        # Validate habit availability
        if goal_data.supporting_habit_uids:
            inactive_habits = [
                habit_uid
                for habit_uid in goal_data.supporting_habit_uids
                if habit_uid not in user_context.active_habit_uids
            ]
            if inactive_habits:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal with inactive supporting habits",
                        field="supporting_habit_uids",
                        value=inactive_habits,
                        user_message=f"Please activate these habits first: {', '.join(inactive_habits)}",
                    )
                )

        # Create goal through learning service (handles DTO creation)
        result = await self.learning.create_goal_with_learning_integration(goal_data, None)
        if result.is_error:
            return result

        # Note: User context invalidation now happens via event-driven architecture
        # GoalCreated event -> invalidate_context_on_goal_event() -> user_service.invalidate_context()

        goal = result.value
        # GRAPH-NATIVE: Get counts from goal_data (input) since relationships stored in graph
        habit_count = len(goal_data.supporting_habit_uids) if goal_data.supporting_habit_uids else 0
        knowledge_count = (
            len(goal_data.required_knowledge_uids) if goal_data.required_knowledge_uids else 0
        )
        self.logger.info(
            "Created goal %s with %d habits, %d knowledge requirements",
            goal.uid,
            habit_count,
            knowledge_count,
        )

        return Result.ok(goal)

    async def generate_tasks_for_goal(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate task suggestions for achieving a goal (orchestration method).

        This combines goal data with user context to generate:
        - Milestone tasks
        - Knowledge acquisition tasks
        - Habit reinforcement tasks
        """
        from core.models.goal.goal import Goal
        from core.models.goal.goal_dto import GoalDTO

        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # GRAPH-NATIVE: Fetch relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        task_suggestions = []

        # Generate milestone tasks
        if goal.milestones:
            for i, milestone in enumerate(goal.milestones):
                if not milestone.is_completed:
                    task = {
                        "title": f"Complete: {milestone.title}",
                        "description": milestone.description or "",
                        "fulfills_goal_uid": goal_uid,
                        "goal_progress_contribution": 100.0 / len(goal.milestones),
                        "priority": Priority.HIGH
                        if goal.days_remaining() < 30
                        else Priority.MEDIUM,
                        "tags": ["goal", f"milestone-{i + 1}"],
                    }
                    task_suggestions.append(task)

        # Generate knowledge acquisition tasks
        if rels.required_knowledge_uids:
            for knowledge_uid in rels.required_knowledge_uids:
                if knowledge_uid not in user_context.mastered_knowledge_uids:
                    task = {
                        "title": f"Learn: {knowledge_uid}",
                        "fulfills_goal_uid": goal_uid,
                        "applies_knowledge_uids": [knowledge_uid],
                        "knowledge_mastery_check": True,
                        "priority": Priority.HIGH,
                        "tags": ["learning", "goal"],
                    }
                    task_suggestions.append(task)

        # Generate habit reinforcement tasks
        if rels.supporting_habit_uids:
            for habit_uid in rels.supporting_habit_uids:
                if user_context.habit_streaks.get(habit_uid, 0) < 7:
                    task = {
                        "title": f"Strengthen habit: {habit_uid}",
                        "reinforces_habit_uid": habit_uid,
                        "fulfills_goal_uid": goal_uid,
                        "habit_streak_maintainer": True,
                        "priority": Priority.MEDIUM,
                        "recurring": True,
                        "tags": ["habit", "goal"],
                    }
                    task_suggestions.append(task)

        self.logger.info(
            "Generated %d task suggestions for goal %s", len(task_suggestions), goal_uid
        )

        return Result.ok(task_suggestions)

    async def assess_goal_feasibility(
        self, goal: Goal, user_context: UserContext
    ) -> Result[GoalFeasibilityAssessment]:
        """
        Assess if a goal is feasible given user's context (orchestration method).

        Combines checks across:
        - Knowledge prerequisites
        - Habit support
        - Current workload
        """
        # GRAPH-NATIVE: Fetch goal relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships
        from core.services.goals_types import (
            GoalFeasibilityAssessment as _GoalFeasibilityAssessment,
        )

        rels = await GoalRelationships.fetch(goal.uid, self.relationships)

        # Mutable accumulation variables
        is_feasible_flag = True
        confidence_score = 0.8
        blockers_list: list[str] = []
        enablers_list: list[str] = []
        estimated_date = None

        # Check knowledge prerequisites (from graph relationships)
        if rels.required_knowledge_uids:
            missing = set(rels.required_knowledge_uids) - user_context.mastered_knowledge_uids
            if missing:
                blockers_list.append(f"Missing {len(missing)} knowledge prerequisites")
                is_feasible_flag = False
                confidence_score *= 0.5

        # Check habit support (from graph relationships)
        if rels.supporting_habit_uids:
            active_habits = [
                h for h in rels.supporting_habit_uids if h in user_context.active_habit_uids
            ]
            if len(active_habits) < len(rels.supporting_habit_uids) / 2:
                blockers_list.append("Insufficient habit support")
                confidence_score *= 0.7
            else:
                enablers_list.append(f"{len(active_habits)} supporting habits active")

        # Check workload
        current_workload = user_context.current_workload_score
        if current_workload > 0.8:
            blockers_list.append("Current workload too high")
            is_feasible_flag = False

        # Estimate completion
        if is_feasible_flag and goal.target_date:
            estimated_date = goal.target_date

        # Build immutable result using frozen dataclass
        assessment = _GoalFeasibilityAssessment(
            is_feasible=is_feasible_flag,
            confidence=confidence_score,
            blockers=blockers_list,
            enablers=enablers_list,
            estimated_completion_date=estimated_date,
        )

        return Result.ok(assessment)
