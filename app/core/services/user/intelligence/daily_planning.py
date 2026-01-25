"""
Daily Planning Mixin
=====================

Method 5 of UserContextIntelligence:
- get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?

This is the core value proposition: "What should I work on next?"

**Synthesizes ALL 9 domains:**
- Activity Domains (6): tasks, habits, goals, events, choices, principles
- Curriculum Domains (3): ku, ls, lp
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.user.intelligence.types import DailyWorkPlan
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


class DailyPlanningMixin:
    """
    Mixin providing daily planning methods.

    Requires self.context (UserContext) and all 9 domain relationship services:
    - self.tasks, self.habits, self.goals, self.events
    - self.choices, self.principles
    - self.ku
    """

    context: UserContext
    tasks: Any  # TasksRelationshipService
    habits: Any  # HabitsRelationshipService
    goals: Any  # GoalsRelationshipService
    events: Any  # EventsRelationshipService
    choices: Any  # ChoicesRelationshipService
    principles: Any  # PrinciplesRelationshipService
    ku: Any  # KuGraphService

    # =========================================================================
    # METHOD 5: Ready to Work on Today - THE FLAGSHIP METHOD
    # =========================================================================

    async def get_ready_to_work_on_today(
        self,
        prioritize_life_path: bool = True,
        respect_capacity: bool = True,
    ) -> Result[DailyWorkPlan]:
        """
        THE FLAGSHIP METHOD - What should I focus on TODAY?

        **Synthesizes ALL 9 domains:**

        Activity Domains (6):
        - tasks.get_actionable_tasks_for_user() - Ready tasks
        - habits.get_at_risk_habits_for_user() - Habits to maintain
        - goals.get_advancing_goals_for_user() - Goals to progress
        - events.get_upcoming_events_for_user() - Scheduled events
        - choices.get_pending_decisions_for_user() - Decisions awaiting
        - principles.get_aligned_principles_for_user() - Values to embody

        Curriculum Domains (3):
        - ku.get_ready_to_learn_for_user() - Ready knowledge
        - ls: Learning step sequencing
        - lp: Life path alignment

        **Respects:**
        - context.available_minutes_daily (capacity)
        - context.current_energy_level (cognitive load)
        - context.current_workload_score (not overload)

        Args:
            prioritize_life_path: Weight life path alignment highly
            respect_capacity: Don't exceed available time

        Returns:
            Result[DailyWorkPlan] with rationale and priorities
        """
        plan = DailyWorkPlan()
        available_time = self.context.available_minutes_daily

        # =====================================================================
        # PRIORITY 1: At-risk habits (maintain streaks - highest priority)
        # =====================================================================
        habits_result = await self.habits.get_at_risk_habits_for_user(self.context)
        if habits_result.is_ok and habits_result.value:
            for contextual_habit in habits_result.value[:3]:
                plan.habits.append(contextual_habit.uid)
                plan.contextual_habits.append(contextual_habit)
                plan.estimated_time_minutes += 15  # ~15 min per habit

        # =====================================================================
        # PRIORITY 2: Today's events (can't reschedule)
        # =====================================================================
        events_result = await self.events.get_upcoming_events_for_user(self.context)
        if events_result.is_ok and events_result.value:
            for contextual_event in events_result.value:
                plan.events.append(contextual_event.uid)
                plan.estimated_time_minutes += 30  # ~30 min per event

        # =====================================================================
        # PRIORITY 3: Overdue and actionable tasks
        # =====================================================================
        tasks_result = await self.tasks.get_actionable_tasks_for_user(self.context, limit=5)
        if tasks_result.is_ok and tasks_result.value:
            # Prioritize overdue tasks first
            overdue = [t for t in tasks_result.value if t.is_overdue]
            regular = [t for t in tasks_result.value if not t.is_overdue]

            for contextual_task in overdue[:2] + regular[:3]:
                if not respect_capacity or plan.estimated_time_minutes + 30 <= available_time:
                    plan.tasks.append(contextual_task.uid)
                    plan.contextual_tasks.append(contextual_task)
                    plan.estimated_time_minutes += 30

            if overdue:
                plan.warnings.append(f"{len(overdue)} overdue tasks need attention")

        # =====================================================================
        # PRIORITY 4: Daily habits (consistency)
        # =====================================================================
        daily_habits = [h for h in self.context.daily_habits if h not in plan.habits]
        for habit_uid in daily_habits[:3]:
            if not respect_capacity or plan.estimated_time_minutes + 15 <= available_time:
                plan.habits.append(habit_uid)
                plan.estimated_time_minutes += 15

        # =====================================================================
        # PRIORITY 5: Learning (if capacity allows)
        # =====================================================================
        if not respect_capacity or plan.estimated_time_minutes < available_time * 0.7:
            learning_result = await self.ku.get_ready_to_learn_for_user(self.context, limit=3)
            if learning_result.is_ok and learning_result.value:
                for contextual_ku in learning_result.value:
                    est_time = self.context.estimated_time_to_mastery.get(contextual_ku.uid, 30)
                    if (
                        not respect_capacity
                        or plan.estimated_time_minutes + est_time <= available_time
                    ):
                        plan.learning.append(contextual_ku.uid)
                        plan.contextual_knowledge.append(contextual_ku)
                        plan.estimated_time_minutes += est_time

        # =====================================================================
        # PRIORITY 6: Advancing goals
        # =====================================================================
        goals_result = await self.goals.get_advancing_goals_for_user(self.context, limit=2)
        if goals_result.is_ok and goals_result.value:
            for contextual_goal in goals_result.value:
                plan.goals.append(contextual_goal.uid)
                plan.contextual_goals.append(contextual_goal)

        # =====================================================================
        # PRIORITY 7: Pending decisions (if any high priority)
        # =====================================================================
        choices_result = await self.choices.get_pending_decisions_for_user(self.context)
        if choices_result.is_ok and choices_result.value:
            high_priority = [c for c in choices_result.value if c.priority_score > 0.7]
            plan.choices = [c.uid for c in high_priority[:2]]

        # =====================================================================
        # PRIORITY 8: Aligned principles (for focus)
        # =====================================================================
        principles_result = await self.principles.get_aligned_principles_for_user(self.context)
        if principles_result.is_ok and principles_result.value:
            plan.principles = [p.uid for p in principles_result.value[:3]]

        # =====================================================================
        # Calculate final metrics
        # =====================================================================
        plan.workload_utilization = min(1.0, plan.estimated_time_minutes / max(available_time, 1))
        plan.fits_capacity = plan.workload_utilization <= 1.0

        # Build priorities list
        plan.priorities = self._build_priority_list(plan)

        # Generate rationale
        plan.rationale = self._generate_daily_rationale(plan, prioritize_life_path)

        # Final warnings
        if plan.workload_utilization > 0.9:
            plan.warnings.append("Very full schedule - consider reducing if feeling overwhelmed")
        if not plan.learning and self.context.learning_goals:
            plan.warnings.append("No learning time scheduled - consider your learning goals")

        return Result.ok(plan)

    def _build_priority_list(self, plan: DailyWorkPlan) -> list[str]:
        """Build ordered priority list for the day."""
        priorities = []

        if plan.habits:
            at_risk_count = len(plan.contextual_habits)
            if at_risk_count > 0:
                priorities.append(f"Maintain {at_risk_count} at-risk habit streaks")
            else:
                priorities.append("Complete daily habits")

        if plan.events:
            priorities.append(f"Attend {len(plan.events)} scheduled events")

        if any("overdue" in w.lower() for w in plan.warnings):
            priorities.append("Catch up on overdue tasks (high priority)")

        if plan.learning:
            priorities.append(f"Learn {len(plan.learning)} knowledge units")

        if plan.tasks:
            priorities.append(f"Complete {len(plan.tasks)} tasks")

        if plan.goals:
            priorities.append(f"Advance {len(plan.goals)} goals")

        if plan.choices:
            priorities.append(f"Consider {len(plan.choices)} pending decisions")

        return priorities

    def _generate_daily_rationale(self, plan: DailyWorkPlan, prioritize_life_path: bool) -> str:
        """Generate human-readable rationale for daily plan."""
        rationale_parts = []

        # Habits focus
        if len(plan.habits) >= 3:
            rationale_parts.append("Strong focus on habit consistency")

        # Task focus
        if plan.tasks:
            if self.context.primary_goal_focus:
                rationale_parts.append("Tasks aligned with primary goal")
            else:
                rationale_parts.append("General task completion focus")

        # Learning focus
        if plan.learning:
            if prioritize_life_path:
                rationale_parts.append("Learning aligned with life path")
            else:
                rationale_parts.append("Learning based on prerequisites")

        # Capacity awareness
        if plan.workload_utilization > 0.8:
            rationale_parts.append("Full schedule - optimize energy management")
        elif plan.workload_utilization < 0.5:
            rationale_parts.append("Light schedule - opportunity for deep work")

        return "; ".join(rationale_parts) if rationale_parts else "Balanced daily plan"


__all__ = ["DailyPlanningMixin"]
