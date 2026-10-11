"""
Orchestration Mixin — GoalsService
====================================

Multi-step orchestration methods that coordinate multiple sub-services:
create_goal_with_context, assess_goal_feasibility.

Part of goals_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    core: GoalsCoreService
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
        3. Goal creation via the core create primitive (events, guarded link edges)
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

        # Gates hold — the core primitive does everything else: builds the frozen
        # Goal, writes the request's link edges through the admission guard, and
        # publishes GoalCreated after they exist. (This step used to run through the
        # learning bridge's dict-based create, which persisted a corrupt uid-less
        # node and then errored — deleted 2026-08-06.)
        result = await self.core.create_goal(goal_data, user_context.user_uid)
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
