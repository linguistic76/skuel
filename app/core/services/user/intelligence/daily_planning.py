"""
Daily Planning Mixin
=====================

Method 5 of UserContextIntelligence:
- get_ready_to_work_on_today() - THE FLAGSHIP - What's optimal for TODAY?

This is the core value proposition: "What should I work on next?"

Two data sources, kept distinct so callers don't confuse "service queried at
plan time" with "context field already resolved by the MEGA-QUERY":

**Domain service queries (8 required + 1 optional):**
- Activity (6): tasks, habits, goals, events, choices, principles
- Curriculum (2): ps (P5 learning), exercises (P2.3 revisions + P2.5 assignments)
- Optional: vector_search (semantic enhancement of P5 learning recommendations)

Each query returns enriched Contextual* objects with readiness signals —
prerequisite mastery, blocking dependencies, urgency math.

**Already-resolved context fields (read directly, no query):**
- available_minutes_daily, daily_habits, zpd_assessment,
  estimated_time_to_mastery, learning_goals, primary_goal_focus,
  life_path_uid, latest_activity_report_*, active_ps_engagements

These are pre-computed by UserContextBuilder.MEGA-QUERY. The mixin reads
them as-is; it does NOT treat them as "domains" in the service sense.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from core.models.context_types import ContextualExercise, DailyWorkPlan, EngagedPsGroup
from core.services.user.intelligence._base import IntelligenceMixinBase
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.context_types import (
        ContextualGoal,
        ContextualHabit,
        ContextualKnowledge,
        ContextualTask,
    )
    from core.services.ps_engagement.engagement import Engagement
    from core.services.user.unified_user_context import RichUserContext


class DailyPlanningMixin(IntelligenceMixinBase):
    """
    Mixin providing daily planning methods.

    Requires self.context (RichUserContext) and 8 domain services that
    get_ready_to_work_on_today() actually queries:
    - Activity: self.tasks, self.habits, self.goals, self.events,
      self.choices, self.principles
    - Curriculum: self.ps (learning readiness), self.exercises (actionable
      exercises + pending revisions with prerequisite-mastery enrichment)
    Optional: self.vector_search (Neo4jVectorSearchService) for semantic
    enhancement of the P5 learning block.

    Other services on UserContextIntelligence (lp, report, calendar,
    zpd_service) are used by sibling mixins — this mixin does not call them.
    """

    # Forward declarations of TemporalMomentumMixin methods used here. These
    # methods live on a sibling mixin; the composed UserContextIntelligence
    # class brings them in, but mypy needs the surface to type-check call sites
    # inside this file.
    if TYPE_CHECKING:

        def compute_momentum_signals(self) -> dict[str, Any]: ...

        def _momentum_warnings(self, signals: dict[str, Any]) -> list[str]: ...

        def _momentum_rationale(self, signals: dict[str, Any]) -> str | None: ...

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
        - ps.get_ready_to_learn_for_user() - Ready knowledge
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
        # Rich context is compile-time enforced via `context: RichUserContext`.
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
        # PRIORITY 2.3: Pending revised exercises (teacher-created revisions)
        # Higher priority than regular exercises — teacher wrote targeted feedback.
        # Service-routed via ExerciseService: enriches with prereq readiness so
        # blocked revisions surface in warnings.
        # =====================================================================
        revisions_result = await self.exercises.get_pending_revisions_for_user(self.context)
        if revisions_result.is_ok and revisions_result.value:
            for contextual_rev in revisions_result.value:
                if (
                    not respect_capacity
                    or estimated_time + contextual_rev.est_time_minutes <= available_time
                ):
                    exercises_uids.append(contextual_rev.uid)
                    contextual_exercises_list.append(contextual_rev)
                    estimated_time += contextual_rev.est_time_minutes

            total_revisions = len(self.context.pending_revised_exercises)
            if total_revisions > 0:
                warnings_list.append(
                    f"{total_revisions} pending revision{'s' if total_revisions > 1 else ''} from teacher feedback"
                )
            blocked_revs = [r for r in revisions_result.value if r.is_blocked]
            if blocked_revs:
                warnings_list.append(
                    f"{len(blocked_revs)} revision{'s' if len(blocked_revs) > 1 else ''} blocked by unmastered prerequisites"
                )

        # =====================================================================
        # PRIORITY 2.5: Unsubmitted exercises
        # Service-routed via ExerciseService: prereq readiness drives ordering
        # ("blocked by N unmastered KUs") and feeds the blocked-count warning.
        # =====================================================================
        exercises_result = await self.exercises.get_actionable_exercises_for_user(self.context)
        if exercises_result.is_ok and exercises_result.value:
            for contextual_ex in exercises_result.value:
                if (
                    not respect_capacity
                    or estimated_time + contextual_ex.est_time_minutes <= available_time
                ):
                    exercises_uids.append(contextual_ex.uid)
                    contextual_exercises_list.append(contextual_ex)
                    estimated_time += contextual_ex.est_time_minutes

            overdue_count = sum(1 for ex in exercises_result.value if ex.is_overdue)
            if overdue_count:
                warnings_list.append(
                    f"{overdue_count} exercise submission{'s' if overdue_count > 1 else ''} overdue"
                )
            blocked_assignments = sum(1 for ex in exercises_result.value if ex.is_blocked)
            if blocked_assignments:
                warnings_list.append(
                    f"{blocked_assignments} exercise{'s' if blocked_assignments > 1 else ''} blocked by unmastered prerequisites"
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
        # PRIORITY 5: Learning — ZPD-driven when available
        # =====================================================================
        if not respect_capacity or estimated_time < available_time * 0.7:
            zpd = self.context.zpd_assessment
            if zpd is not None and not zpd.is_empty():
                # ZPD gravity well path: use recommended actions
                for action in zpd.top_recommended_actions(3):
                    if action.action_type == "learn":
                        est_time = self.context.estimated_time_to_mastery.get(action.entity_uid, 30)
                        if not respect_capacity or estimated_time + est_time <= available_time:
                            learning_uids.append(action.entity_uid)
                            estimated_time += est_time
            elif self.vector_search and getattr(self.vector_search, "learning_aware_search", None):
                # Fallback: semantic-enhanced search
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
                    # Fallback to standard ps service
                    estimated_time = await self._add_ps_items(
                        learning_uids,
                        contextual_knowledge_list,
                        estimated_time,
                        available_time,
                        respect_capacity,
                    )
            else:
                # Standard path: Use ps service
                estimated_time = await self._add_ps_items(
                    learning_uids,
                    contextual_knowledge_list,
                    estimated_time,
                    available_time,
                    respect_capacity,
                )

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
            high_priority = [c for c in choices_result.value if c.priority_score >= 0.7]
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

        # Domain health warnings — aggregate stats from filtered providers
        if self.filtered_providers:
            domain_warnings = await self._generate_domain_health_warnings()
            warnings_list.extend(domain_warnings)

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

        # ADR-059 bucketing — fold PS engagement state into the plan. The
        # engagement data lives on context.active_ps_engagements (populated
        # by UserContextBuilder via PsEngagementService.list_engaged). When
        # None or empty, the plan is returned with the default empty buckets.
        engagements_map = self.context.active_ps_engagements
        if engagements_map:
            engagements = list(engagements_map.values())
            groups = _build_engaged_groups(plan, engagements)
            available = _compute_available_to_start(self.context, engagements)
            plan = replace(plan, engaged_ps_groups=groups, available_to_start=available)

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
            # Derive counts from the plan itself (subtype field on each
            # ContextualExercise) so totals are internally consistent — the
            # previous version mixed plan counts with full context totals,
            # which made `remaining` potentially negative when context had
            # more revisions than fit in the plan.
            revisions = [e for e in plan.contextual_exercises if e.subtype == "revision"]
            assignments = [e for e in plan.contextual_exercises if e.subtype == "assignment"]
            overdue_ex = [e for e in assignments if e.is_overdue]
            if revisions:
                priorities.append(
                    f"Address {len(revisions)} pending revision{'s' if len(revisions) > 1 else ''} from teacher feedback"
                )
            if overdue_ex:
                priorities.append(
                    f"Submit {len(overdue_ex)} overdue exercise{'s' if len(overdue_ex) > 1 else ''} (teacher assignment)"
                )
            remaining = len(assignments) - len(overdue_ex)
            if remaining > 0:
                priorities.append(
                    f"Complete {remaining} exercise submission{'s' if remaining > 1 else ''}"
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

        # Exercise focus — derived from the plan (subtype on each ContextualExercise)
        if plan.exercises:
            has_revision = any(e.subtype == "revision" for e in plan.contextual_exercises)
            if has_revision:
                rationale_parts.append("Teacher revision feedback to address")
            else:
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
    # Learning Helpers
    # =========================================================================

    async def _add_ps_items(
        self,
        learning_uids: list[str],
        contextual_knowledge_list: list[Any],
        estimated_time: int,
        available_time: int,
        respect_capacity: bool,
        limit: int = 3,
    ) -> int:
        """Fetch path steps ready to learn and add them respecting capacity.

        Mutates *learning_uids* and *contextual_knowledge_list* in place.
        Returns the updated *estimated_time*.
        """
        learning_result = await self.ps.get_ready_to_learn_for_user(self.context, limit=limit)
        if learning_result.is_ok and learning_result.value:
            for contextual_ku in learning_result.value:
                est_time = self.context.estimated_time_to_mastery.get(contextual_ku.uid, 30)
                if not respect_capacity or estimated_time + est_time <= available_time:
                    learning_uids.append(contextual_ku.uid)
                    contextual_knowledge_list.append(contextual_ku)
                    estimated_time += est_time
        return estimated_time

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

    # =========================================================================
    # Domain Health (FilteredContextProvider stats)
    # =========================================================================

    async def _query_domain_stats(self, domain: str) -> dict[str, int | float] | None:
        """Query aggregate stats for a domain via its FilteredContextProvider.

        Returns the stats dict from ListContext["stats"], or None if the domain
        has no provider or the query fails. Callers should treat None as
        "stats unavailable" (not "stats are zero").
        """
        provider = self.filtered_providers.get(domain)
        if provider is None:
            return None
        result = await provider.get_filtered_context(
            user_uid=self.context.user_uid,
            status_filter="all",
        )
        if result.is_error:
            return None
        return result.value.get("stats")

    async def _generate_domain_health_warnings(self) -> list[str]:
        """Generate warnings from per-domain aggregate stats.

        Uses filtered_providers to query domain stats that intelligence methods
        otherwise have no access to. Stats are pre-filter aggregates (totals
        across all statuses), computed by each domain's get_filtered_context().

        All stats dicts include guaranteed ``total`` and ``active`` keys (BaseStats
        contract). Domain-specific keys (``overdue``, ``pending``, ``core``, etc.)
        are used for targeted warnings.
        """
        warnings: list[str] = []

        # --- Single-domain warnings ---

        task_stats = await self._query_domain_stats("tasks")
        if task_stats is not None:
            active = int(task_stats.get("active", 0))
            if active > 30:
                warnings.append(f"{active} active tasks — consider archiving or splitting")

        goal_stats = await self._query_domain_stats("goals")
        if goal_stats is not None and int(goal_stats.get("active", 0)) == 0:
            warnings.append("No active goals — daily work lacks direction")

        habit_stats = await self._query_domain_stats("habits")
        if habit_stats is not None and int(habit_stats.get("total", 0)) == 0:
            warnings.append("No habits tracked — consider adding consistency anchors")

        event_stats = await self._query_domain_stats("events")
        if event_stats is not None:
            today_count = int(event_stats.get("today", 0))
            if today_count >= 5:
                warnings.append(f"{today_count} events today — tight schedule, protect focus time")

        choice_stats = await self._query_domain_stats("choices")
        if choice_stats is not None:
            pending = int(choice_stats.get("pending", 0))
            if pending >= 5:
                warnings.append(
                    f"{pending} pending choices — decision fatigue risk, prioritize or defer"
                )

        principle_stats = await self._query_domain_stats("principles")
        if principle_stats is not None:
            if (
                int(principle_stats.get("total", 0)) > 0
                and int(principle_stats.get("core", 0)) == 0
            ):
                warnings.append(
                    "No core principles — consider strengthening your values foundation"
                )

        # --- Cross-domain balance warnings ---

        if goal_stats is not None and habit_stats is not None:
            goals_active = int(goal_stats.get("active", 0))
            habits_active = int(habit_stats.get("active", 0))
            if goals_active >= 10 and habits_active == 0:
                warnings.append(
                    f"{goals_active} active goals but no habits — missing consistency anchors"
                )

        if task_stats is not None and goal_stats is not None:
            tasks_active = int(task_stats.get("active", 0))
            goals_active = int(goal_stats.get("active", 0))
            if tasks_active > 20 and goals_active == 0:
                warnings.append("Many tasks but no goals — work lacks strategic direction")

        return warnings


# =========================================================================
# ADR-059 Bucketing Helpers — pure data transformations on the assembled
# DailyWorkPlan. Module-level (not methods) so they have no implicit self
# coupling and are trivially testable. Lifted from askesis_service.py
# (where the code was dead — Askesis is uncalled) to live in the mixin
# that actually produces the plan.
# =========================================================================


def _build_engaged_groups(
    plan: DailyWorkPlan,
    engagements: list[Engagement],
) -> tuple[EngagedPsGroup, ...]:
    """Intersect each engagement's spawned UIDs with the plan's per-domain lists."""
    if not engagements:
        return ()

    groups: list[EngagedPsGroup] = []
    for engagement in engagements:
        spawned = set(engagement.spawned_instance_uids)
        if not spawned:
            # Engagement carries no instance UIDs — still surface the
            # engagement itself so the consumer can render "you're engaged
            # with X" even when no spawned activity is on today's plan.
            groups.append(EngagedPsGroup(ps_uid=engagement.ps_uid, engagement=engagement))
            continue
        groups.append(
            EngagedPsGroup(
                ps_uid=engagement.ps_uid,
                engagement=engagement,
                pending_task_uids=tuple(uid for uid in plan.tasks if uid in spawned),
                pending_habit_uids=tuple(uid for uid in plan.habits if uid in spawned),
                pending_event_uids=tuple(uid for uid in plan.events if uid in spawned),
                pending_goal_uids=tuple(uid for uid in plan.goals if uid in spawned),
                pending_choice_uids=tuple(uid for uid in plan.choices if uid in spawned),
                pending_principle_uids=tuple(uid for uid in plan.principles if uid in spawned),
            )
        )
    return tuple(groups)


def _compute_available_to_start(
    user_context: RichUserContext,
    engagements: list[Engagement],
) -> tuple[str, ...]:
    """PS UIDs the user has touched but has not engaged with yet."""
    engaged_ps_uids = {e.ps_uid for e in engagements}
    touched: list[str] = []
    seen: set[str] = set()
    for item in user_context.active_path_steps_rich:
        step = item.get("step") if isinstance(item, dict) else None
        if not isinstance(step, dict):
            continue
        uid = step.get("uid")
        if not isinstance(uid, str) or uid in seen or uid in engaged_ps_uids:
            continue
        seen.add(uid)
        touched.append(uid)
    return tuple(touched)


__all__ = ["DailyPlanningMixin"]
