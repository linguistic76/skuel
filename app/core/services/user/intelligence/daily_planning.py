"""
Daily Planning Mixin
=====================

Method 5 of UserContextIntelligence:
- get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?

This is the core value proposition: "What should I work on next?"

**Synthesizes 10 domains:**
- Activity Domains (6): tasks, habits, goals, events, choices, principles
- Curriculum Domains (3): ku, ls, lp
- Submissions Domain (1): context.unsubmitted_exercises — Priority 2.5
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.context_types import ContextualExercise, DailyWorkPlan
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.context_types import (
        ContextualGoal,
        ContextualHabit,
        ContextualKnowledge,
        ContextualTask,
    )
    from core.services.user.unified_user_context import UserContext


class DailyPlanningMixin:
    """
    Mixin providing daily planning methods.

    Requires self.context (UserContext) and domain relationship services:
    - self.tasks, self.habits, self.goals, self.events
    - self.choices, self.principles
    - self.ku
    - self.feedback  (FeedbackRelationshipService — for unsubmitted exercises)
    Optional: self.vector_search (Neo4jVectorSearchService) for semantic/learning-aware search.
    """

    context: UserContext
    tasks: Any  # TasksRelationshipService
    habits: Any  # HabitsRelationshipService
    goals: Any  # GoalsRelationshipService
    events: Any  # EventsRelationshipService
    choices: Any  # ChoicesRelationshipService
    principles: Any  # PrinciplesRelationshipService
    ku: Any  # KuGraphService

    # Stubs for methods provided by TemporalMomentumMixin in the composed class.
    if TYPE_CHECKING:

        def compute_momentum_signals(self) -> dict[str, Any]: ...

        def _momentum_warnings(self, signals: dict[str, Any]) -> list[str]: ...

        def _momentum_rationale(self, signals: dict[str, Any]) -> str | None: ...

    feedback: Any  # FeedbackRelationshipService
    vector_search: Any = None  # Neo4jVectorSearchService (optional)

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
        available_time = self.context.available_minutes_daily

        # Accumulators for frozen DailyWorkPlan construction
        habits_uids: list[str] = []
        contextual_habits_list: list[ContextualHabit] = []
        events_uids: list[str] = []
        exercises_uids: list[str] = []
        contextual_exercises_list: list[ContextualExercise] = []
        tasks_uids: list[str] = []
        contextual_tasks_list: list[ContextualTask] = []
        learning_uids: list[str] = []
        contextual_knowledge_list: list[ContextualKnowledge] = []
        goals_uids: list[str] = []
        contextual_goals_list: list[ContextualGoal] = []
        choices_uids: list[str] = []
        principles_uids: list[str] = []
        warnings_list: list[str] = []
        estimated_time = 0

        # =====================================================================
        # PRIORITY 1: At-risk habits (maintain streaks - highest priority)
        # =====================================================================
        habits_result = await self.habits.get_at_risk_habits_for_user(self.context)
        if habits_result.is_ok and habits_result.value:
            for contextual_habit in habits_result.value[:3]:
                habits_uids.append(contextual_habit.uid)
                contextual_habits_list.append(contextual_habit)
                estimated_time += 15  # ~15 min per habit

        # =====================================================================
        # PRIORITY 2: Today's events (can't reschedule)
        # =====================================================================
        events_result = await self.events.get_upcoming_events_for_user(self.context)
        if events_result.is_ok and events_result.value:
            for contextual_event in events_result.value:
                events_uids.append(contextual_event.uid)
                estimated_time += 30  # ~30 min per event

        # =====================================================================
        # PRIORITY 2.5: Unsubmitted exercises (from UserContext — no extra query)
        # =====================================================================
        if self.context.unsubmitted_exercises:
            today = date.today()
            overdue_count = 0
            for ex_dict in self.context.unsubmitted_exercises[:3]:
                est_time = 60  # ~60 min to complete an exercise submission
                if not respect_capacity or estimated_time + est_time <= available_time:
                    due_date: date | None = None
                    days_until_due: int | None = None
                    is_overdue = False
                    if ex_dict.get("due_date"):
                        due_date = date.fromisoformat(ex_dict["due_date"])
                        delta = (due_date - today).days
                        days_until_due = delta
                        is_overdue = delta < 0
                        if is_overdue:
                            overdue_count += 1

                    contextual_ex = ContextualExercise(
                        uid=ex_dict["uid"],
                        title=ex_dict.get("title", "Untitled Exercise"),
                        due_date=due_date,
                        is_overdue=is_overdue,
                        days_until_due=days_until_due,
                    )
                    exercises_uids.append(ex_dict["uid"])
                    contextual_exercises_list.append(contextual_ex)
                    estimated_time += est_time

            if overdue_count:
                warnings_list.append(
                    f"{overdue_count} exercise submission{'s' if overdue_count > 1 else ''} overdue"
                )

        # =====================================================================
        # PRIORITY 3: Overdue and actionable tasks
        # =====================================================================
        tasks_result = await self.tasks.get_actionable_tasks_for_user(self.context, limit=5)
        if tasks_result.is_ok and tasks_result.value:
            # Prioritize overdue tasks first
            overdue = [t for t in tasks_result.value if t.is_overdue]
            regular = [t for t in tasks_result.value if not t.is_overdue]

            for contextual_task in overdue[:2] + regular[:3]:
                if not respect_capacity or estimated_time + 30 <= available_time:
                    tasks_uids.append(contextual_task.uid)
                    contextual_tasks_list.append(contextual_task)
                    estimated_time += 30

            if overdue:
                warnings_list.append(f"{len(overdue)} overdue tasks need attention")

        # =====================================================================
        # PRIORITY 4: Daily habits (consistency)
        # =====================================================================
        daily_habits = [h for h in self.context.daily_habits if h not in habits_uids]
        for habit_uid in daily_habits[:3]:
            if not respect_capacity or estimated_time + 15 <= available_time:
                habits_uids.append(habit_uid)
                estimated_time += 15

        # =====================================================================
        # PRIORITY 5: Learning (if capacity allows)
        # =====================================================================
        if not respect_capacity or estimated_time < available_time * 0.7:
            # Try semantic-enhanced search first (if available)
            if self.vector_search and getattr(self.vector_search, "learning_aware_search", None):
                search_query = self._generate_daily_learning_query(goals_uids, tasks_uids)
                vector_result = await self.vector_search.learning_aware_search(
                    label="Entity",
                    text=search_query,
                    user_uid=self.context.user_uid,
                    prefer_unmastered=True,
                    limit=3,
                )

                if vector_result.is_ok and vector_result.value:
                    for result in vector_result.value:
                        node = result["node"]
                        ku_uid = node["uid"]
                        est_time = self.context.estimated_time_to_mastery.get(ku_uid, 30)
                        if not respect_capacity or estimated_time + est_time <= available_time:
                            learning_uids.append(ku_uid)
                            estimated_time += est_time
                else:
                    # Fallback to standard KU service
                    learning_result = await self.ku.get_ready_to_learn_for_user(
                        self.context, limit=3
                    )
                    if learning_result.is_ok and learning_result.value:
                        for contextual_ku in learning_result.value:
                            est_time = self.context.estimated_time_to_mastery.get(
                                contextual_ku.uid, 30
                            )
                            if not respect_capacity or estimated_time + est_time <= available_time:
                                learning_uids.append(contextual_ku.uid)
                                contextual_knowledge_list.append(contextual_ku)
                                estimated_time += est_time
            else:
                # Standard path: Use KU service
                learning_result = await self.ku.get_ready_to_learn_for_user(self.context, limit=3)
                if learning_result.is_ok and learning_result.value:
                    for contextual_ku in learning_result.value:
                        est_time = self.context.estimated_time_to_mastery.get(contextual_ku.uid, 30)
                        if not respect_capacity or estimated_time + est_time <= available_time:
                            learning_uids.append(contextual_ku.uid)
                            contextual_knowledge_list.append(contextual_ku)
                            estimated_time += est_time

        # =====================================================================
        # PRIORITY 6: Advancing goals
        # =====================================================================
        goals_result = await self.goals.get_advancing_goals_for_user(self.context, limit=2)
        if goals_result.is_ok and goals_result.value:
            for contextual_goal in goals_result.value:
                goals_uids.append(contextual_goal.uid)
                contextual_goals_list.append(contextual_goal)

        # =====================================================================
        # PRIORITY 7: Pending decisions (if any high priority)
        # =====================================================================
        choices_result = await self.choices.get_pending_decisions_for_user(self.context)
        if choices_result.is_ok and choices_result.value:
            high_priority = [c for c in choices_result.value if c.priority_score > 0.7]
            choices_uids = [c.uid for c in high_priority[:2]]

        # =====================================================================
        # PRIORITY 8: Aligned principles (for focus)
        # =====================================================================
        principles_result = await self.principles.get_aligned_principles_for_user(self.context)
        if principles_result.is_ok and principles_result.value:
            principles_uids = [p.uid for p in principles_result.value[:3]]

        # =====================================================================
        # Calculate final metrics
        # =====================================================================
        workload_utilization = min(1.0, estimated_time / max(available_time, 1))
        fits_capacity = workload_utilization <= 1.0

        # Final warnings
        if workload_utilization > 0.9:
            warnings_list.append("Very full schedule - consider reducing if feeling overwhelmed")
        if not learning_uids and self.context.learning_goals:
            warnings_list.append("No learning time scheduled - consider your learning goals")

        # Temporal momentum signals — enrich warnings from window-activity data
        momentum = self.compute_momentum_signals()
        warnings_list.extend(self._momentum_warnings(momentum))

        # Construct frozen plan (without priorities/rationale — computed from plan)
        plan = DailyWorkPlan(
            learning=tuple(learning_uids),
            tasks=tuple(tasks_uids),
            habits=tuple(habits_uids),
            events=tuple(events_uids),
            goals=tuple(goals_uids),
            choices=tuple(choices_uids),
            principles=tuple(principles_uids),
            exercises=tuple(exercises_uids),
            contextual_tasks=tuple(contextual_tasks_list),
            contextual_habits=tuple(contextual_habits_list),
            contextual_goals=tuple(contextual_goals_list),
            contextual_knowledge=tuple(contextual_knowledge_list),
            contextual_exercises=tuple(contextual_exercises_list),
            estimated_time_minutes=estimated_time,
            fits_capacity=fits_capacity,
            workload_utilization=workload_utilization,
            warnings=tuple(warnings_list),
        )

        # Build priorities and rationale from the constructed plan
        priorities = self._build_priority_list(plan)
        rationale = self._generate_daily_rationale(plan, prioritize_life_path, momentum)
        plan = replace(plan, priorities=tuple(priorities), rationale=rationale)

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

        if plan.exercises:
            overdue_ex = [e for e in plan.contextual_exercises if e.is_overdue]
            if overdue_ex:
                priorities.append(
                    f"Submit {len(overdue_ex)} overdue exercise{'s' if len(overdue_ex) > 1 else ''} (teacher assignment)"
                )
            else:
                priorities.append(
                    f"Complete {len(plan.exercises)} exercise submission{'s' if len(plan.exercises) > 1 else ''}"
                )

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

    def _generate_daily_rationale(
        self,
        plan: DailyWorkPlan,
        prioritize_life_path: bool,
        momentum: dict[str, Any] | None = None,
    ) -> str:
        """Generate human-readable rationale for daily plan."""
        rationale_parts = []

        # Habits focus
        if len(plan.habits) >= 3:
            rationale_parts.append("Strong focus on habit consistency")

        # Exercise focus
        if plan.exercises:
            rationale_parts.append("Teacher assignment submissions due")

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

        # Activity report awareness — inform rationale when plan draws on recent synthesis
        if self.context.latest_activity_report_uid and self.context.latest_activity_report_period:
            rationale_parts.append(
                f"Plan informed by your {self.context.latest_activity_report_period} activity report"
            )

        # Temporal momentum — append phase signal if meaningful
        if momentum:
            momentum_clause = self._momentum_rationale(momentum)
            if momentum_clause:
                rationale_parts.append(momentum_clause)

        return "; ".join(rationale_parts) if rationale_parts else "Balanced daily plan"

    # =========================================================================
    # Vector Search Helpers
    # =========================================================================

    def _generate_daily_learning_query(self, goals_uids: list[str], tasks_uids: list[str]) -> str:
        """
        Generate semantic search query for daily learning based on current plan context.

        Combines:
        - Active goals
        - Scheduled tasks/events
        - Life path alignment
        """
        query_parts = []

        # Include goal context
        if goals_uids:
            query_parts.append("goal-aligned learning")

        # Include task context
        if tasks_uids:
            query_parts.append("actionable knowledge")

        # Include life path
        if self.context.life_path_uid:
            query_parts.append("life path knowledge")

        # Default
        if not query_parts:
            query_parts.append("daily learning")

        return " ".join(query_parts)


__all__ = ["DailyPlanningMixin"]
