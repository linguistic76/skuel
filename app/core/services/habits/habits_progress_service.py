"""
Habits Progress Service
========================

Handles habit progress tracking, streaks, consistency, and keystone habits.

Responsibilities:
- Habit completion with quality tracking
- Streak and consistency analysis
- At-risk habit detection
- Keystone habit management
- Progress cascade effects
"""

from datetime import date, datetime
from operator import attrgetter
from typing import Any

from core.constants import HabitConsistencyWindow
from core.events import HabitCompleted, HabitStreakBroken, HabitStreakMilestone, publish_event
from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.ports.domain_protocols import HabitsOperations
from core.services.habits.habit_relationships import HabitRelationships
from core.services.user import UserContext
from core.services.user.rich_context import (
    find_rich_graph_context,
    get_model_from_rich_context,
    rich_graph_uids,
)
from core.utils.dto_converters import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

# Type alias for rich habit data from UserContext
RichHabitData = dict[str, Any]


class HabitsProgressService:
    """
    Progress tracking service for habits.

    Handles:
    - Habit completion with quality scores
    - Streak calculation and maintenance
    - Consistency analysis
    - Keystone habit identification
    - Progress cascade effects
    """

    def __init__(
        self,
        backend: HabitsOperations,
        completions_service,
        relationship_service,
        event_bus=None,
    ) -> None:
        """
        Initialize habits progress service.

        Args:
            backend: Protocol-based backend for habit operations (REQUIRED)
            completions_service: HabitsCompletionService for fetching completion records (REQUIRED)
            relationship_service: UnifiedRelationshipService for graph relationships (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (January 2026 - Fail-Fast):
            Made completions_service and relationship_service REQUIRED.
        """
        self.backend = backend
        self.completions = completions_service
        self.relationships = relationship_service
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits.progress")

    # ========================================================================
    # CONTEXT-FIRST PATTERN HELPERS (November 26, 2025)
    # ========================================================================
    #
    # These methods implement the Context-First Pattern:
    # - UserContext is THE source of truth for user state
    # - Services CONSUME context, they don't rebuild it
    # - Only query what context doesn't have
    #
    # Benefits:
    # - 3 queries → 1 query per habit completion (when rich context available)
    # - Single source of truth (no race conditions)
    # - Architectural consistency
    #
    # ========================================================================

    def _get_habit_from_rich_context(
        self, habit_uid: str, user_context: UserContext
    ) -> Habit | None:
        """
        Try to get Habit entity from UserContext rich data.

        Context-First Pattern: Use context data when available to avoid
        unnecessary Neo4j queries.

        Args:
            habit_uid: Habit identifier
            user_context: User's context (may contain rich habit data)

        Returns:
            Habit if found in rich context, None otherwise
        """
        return get_model_from_rich_context(user_context, "habits", habit_uid, HabitDTO, Habit)

    def _get_relationships_from_rich_context(
        self, habit_uid: str, user_context: UserContext
    ) -> HabitRelationships | None:
        """
        Try to get HabitRelationships from UserContext rich data.

        Context-First Pattern: Graph neighborhoods are often included in
        rich context, avoiding separate relationship queries.

        Args:
            habit_uid: Habit identifier
            user_context: User's context (may contain graph neighborhoods)

        Returns:
            HabitRelationships if found in rich context, None otherwise
        """
        graph_ctx = find_rich_graph_context(user_context, "habits", habit_uid)
        if graph_ctx is None:
            return None
        return HabitRelationships(
            linked_goal_uids=rich_graph_uids(graph_ctx, "linked_goals"),
            knowledge_reinforcement_uids=rich_graph_uids(graph_ctx, "applied_knowledge"),
            # NOTE: prerequisite_habit_uids not in HabitRelationships model
        )

    # ========================================================================
    # HABIT COMPLETION AND STREAK MANAGEMENT
    # ========================================================================

    async def complete_habit_with_quality(
        self,
        habit_uid: str,
        user_context: UserContext,
        quality_score: int = 4,  # 1-5 scale,
        completion_date: date | None = None,
    ) -> Result[Habit]:
        """
        Complete a habit with quality tracking and cascade effects.

        **CONTEXT-FIRST PATTERN (November 26, 2025):**
        This method implements the Context-First Pattern:
        1. Try to get habit data from UserContext (zero queries)
        2. Fallback to Neo4j query only if not in context
        3. Always query completion history (not in context)

        Benefits:
        - 3 queries → 1 query when rich context available
        - Single source of truth (UserContext)
        - Consistent with SKUEL architecture

        This method:
        1. Updates habit streak
        2. Records quality score
        3. Updates linked goals
        4. Reinforces knowledge if applicable
        5. Publishes events (context invalidated via event handlers)
        """
        completion_date = completion_date or date.today()

        # ====================================================================
        # CONTEXT-FIRST: Try to get habit from context before querying
        # ====================================================================

        habit = self._get_habit_from_rich_context(habit_uid, user_context)
        context_hit = habit is not None

        if habit is None:
            # Fallback: Query Neo4j
            habit_result = await self.backend.get_habit(habit_uid)
            if habit_result.is_error:
                return Result.fail(habit_result)
            habit = to_domain_model(habit_result.value, HabitDTO, Habit)

        if context_hit:
            self.logger.debug(f"Context-first HIT: habit {habit_uid} from rich context")
        else:
            self.logger.debug(f"Context-first MISS: habit {habit_uid} queried from Neo4j")

        # ====================================================================
        # ALWAYS QUERY: Completion history (not in context - mutable data)
        # ====================================================================

        # Scoped to the consistency window, which is all the one consumer below
        # needs — the streak arithmetic reads habit.last_completed, not this list.
        existing_completions = await self._consistency_window_completions(habit_uid, date.today())

        # ====================================================================
        # CALCULATE STREAK
        # ====================================================================

        new_streak = habit.current_streak
        streak_broken = False
        days_since = 0
        if habit.last_completed:
            days_since = (completion_date - habit.last_completed.date()).days
            if days_since == 1:
                new_streak += 1
            elif days_since > 1:
                streak_broken = True
                new_streak = 1  # Streak broken, restart
        else:
            new_streak = 1  # First completion

        # ====================================================================
        # UPDATE HABIT (Always goes to Neo4j - mutation)
        # ====================================================================

        # raw-write: system streak/stat propagation from a habit completion. Bypasses the
        # validated/event-firing service contract (HabitUpdateIntent → update_habit) on
        # purpose — this completion path publishes its own provenance-bearing HabitCompleted /
        # HabitStreakBroken / HabitStreakMilestone events (with streak context) that the
        # generic update_habit cannot express. A plain dict literal is the honest type here.
        updates: dict[str, Any] = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "last_completed": datetime.combine(completion_date, datetime.min.time()),
            "total_completions": habit.total_completions + 1,
        }

        # Calculate consistency score (pass completions for calculation).
        # Persisted as success_rate — the canonical Habit/HabitDTO field every
        # reader consumes (a legacy consistency_30d property was write-only:
        # scripts/migrate_activity_completion_aliases.py renames old nodes).
        # Anchored at TODAY, not at ``completion_date``. ``success_rate`` is a
        # current property of the habit, so the window it is measured over must
        # end at the present regardless of which day this call records. Every
        # production caller reaches here with today (the facade's
        # ``completion_date`` parameter has no live user), so this changes no
        # reading today — it closes the trap: anchoring at the completed day
        # would persist an as-of-then number, stale for a backfill and
        # not-yet-true for a future occurrence.
        consistency = self._calculate_consistency_from_completions(
            habit, existing_completions, date.today()
        )
        updates["success_rate"] = consistency

        update_result = await self.backend.update_habit(habit_uid, dict(updates))
        if update_result.is_error:
            return Result.fail(update_result)

        # ====================================================================
        # CONTEXT-FIRST: Try to get relationships from context
        # ====================================================================

        rels = self._get_relationships_from_rich_context(habit_uid, user_context)
        rels_context_hit = rels is not None

        if rels is None:
            # Fallback: Query relationships from Neo4j
            rels = await HabitRelationships.fetch(habit_uid, self.relationships)

        if rels_context_hit:
            self.logger.debug(f"Context-first HIT: relationships for {habit_uid} from rich context")
        else:
            self.logger.debug(
                f"Context-first MISS: relationships for {habit_uid} queried from Neo4j"
            )

        # CASCADE EFFECTS

        # 1. Update linked goals (from graph relationships)
        if rels.linked_goal_uids:
            self._update_goals_from_habit(
                rels.linked_goal_uids, habit_uid, new_streak, user_context
            )

        # 2. Reinforce knowledge if quality is good (from graph relationships)
        if quality_score >= 4 and rels.knowledge_reinforcement_uids:
            self._reinforce_knowledge(rels.knowledge_reinforcement_uids, 0.05)  # 5% mastery boost

        # 3. Check keystone habit effects
        if habit.is_keystone and new_streak >= 7:
            self._trigger_keystone_effects(habit_uid, user_context)

        # Context invalidation happens via HabitCompleted/HabitStreakBroken/HabitStreakMilestone events (event-driven architecture)
        # Event handlers in bootstrap will call user_service.invalidate_context()

        completed_habit = to_domain_model(update_result.value, HabitDTO, Habit)

        # PUBLISH EVENTS

        # 1. Always publish HabitCompleted
        completed_event = HabitCompleted(
            habit_uid=habit_uid,
            user_uid=user_context.user_uid,
            current_streak=new_streak,
            is_new_streak_record=(new_streak == habit.best_streak),
            completed_late=(completion_date < date.today()),
        )
        await publish_event(self.event_bus, completed_event, self.logger)

        # 2. Publish HabitStreakBroken if streak was broken
        if streak_broken:
            broken_event = HabitStreakBroken(
                habit_uid=habit_uid,
                user_uid=user_context.user_uid,
                streak_length=habit.current_streak,
                last_completion_date=habit.last_completed if habit.last_completed else None,
                days_since_last_completion=days_since,
            )
            await publish_event(self.event_bus, broken_event, self.logger)

        # 3. Publish HabitStreakMilestone if milestone reached
        milestone_values = {7: "one_week", 30: "one_month", 100: "one_hundred", 365: "one_year"}
        if new_streak in milestone_values:
            milestone_event = HabitStreakMilestone(
                habit_uid=habit_uid,
                user_uid=user_context.user_uid,
                streak_length=new_streak,
                milestone_name=milestone_values[new_streak],
            )
            await publish_event(self.event_bus, milestone_event, self.logger)

        self.logger.info(
            "Completed habit %s with quality %d, streak now %d",
            habit_uid,
            quality_score,
            new_streak,
        )

        return Result.ok(completed_habit)

    # ========================================================================
    # CONSISTENCY AND RISK ANALYSIS
    # ========================================================================

    async def get_at_risk_habits(
        self, user_context: UserContext, _risk_threshold_days: int = 3
    ) -> Result[list[Habit]]:
        """
        Get habits at risk of breaking their streaks.

        **CONTEXT-FIRST PATTERN:** Uses rich context when available.
        """
        at_risk = []
        context_hits = 0
        context_misses = 0

        # at_risk_habits is rich-context only; empty at standard depth
        at_risk_uids = user_context.at_risk_habits_or_empty()
        for habit_uid in at_risk_uids:
            # CONTEXT-FIRST: Try rich context first
            habit = self._get_habit_from_rich_context(habit_uid, user_context)

            if habit is not None:
                context_hits += 1
                at_risk.append(habit)
            else:
                # Fallback: Query Neo4j
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_ok:
                    context_misses += 1
                    habit = to_domain_model(habit_result.value, HabitDTO, Habit)
                    at_risk.append(habit)

        if context_hits > 0 or context_misses > 0:
            self.logger.debug(
                f"Context-first stats for at_risk_habits: {context_hits} hits, {context_misses} misses"
            )

        # Sort by streak value (higher streaks = more to lose)
        at_risk.sort(key=attrgetter("current_streak"), reverse=True)

        return Result.ok(at_risk)

    async def analyze_habit_consistency(
        self, habit_uid: str, user_context: UserContext, _days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Analyze habit consistency over a period.

        **CONTEXT-FIRST PATTERN:** Uses rich context when available.
        """
        # ====================================================================
        # CONTEXT-FIRST: Try to get habit from context
        # ====================================================================

        habit = self._get_habit_from_rich_context(habit_uid, user_context)

        if habit is None:
            # Fallback: Query Neo4j
            habit_result = await self.backend.get_habit(habit_uid)
            if habit_result.is_error:
                return Result.fail(habit_result)
            habit = to_domain_model(habit_result.value, HabitDTO, Habit)
            self.logger.debug(f"Context-first MISS: habit {habit_uid} queried for analysis")
        else:
            self.logger.debug(
                f"Context-first HIT: habit {habit_uid} from rich context for analysis"
            )

        # ALWAYS QUERY: Completions (mutable data, not in context)
        completions = await self._consistency_window_completions(habit_uid, date.today())

        # Calculate various consistency metrics
        consistency_30d = self._calculate_consistency_from_completions(
            habit, completions, date.today()
        )

        # Quality trend over the same window, so every figure in this analysis
        # describes one period. The list is most-recent-first, so the ten most
        # recent are the HEAD — this took the TAIL, which is the ten OLDEST, off
        # a page that was itself in no guaranteed order.
        recent_quality = 0.0
        if completions:
            recent_completions = completions[:10]
            quality_scores = [c.quality for c in recent_completions if c.quality is not None]
            if quality_scores:
                recent_quality = sum(quality_scores) / len(quality_scores)

        # ====================================================================
        # CONTEXT-FIRST: Try to get relationships from context
        # ====================================================================

        rels = self._get_relationships_from_rich_context(habit_uid, user_context)

        if rels is None:
            # Fallback: Query relationships from Neo4j
            rels = await HabitRelationships.fetch(habit_uid, self.relationships)
            self.logger.debug(
                f"Context-first MISS: relationships for {habit_uid} queried for analysis"
            )
        else:
            self.logger.debug(f"Context-first HIT: relationships for {habit_uid} from rich context")

        analysis = {
            "habit_uid": habit_uid,
            "habit_name": habit.title,
            "current_streak": habit.current_streak,
            "best_streak": habit.best_streak,
            "consistency_30d": consistency_30d,
            "total_completions": habit.total_completions,
            "average_quality": recent_quality,
            "is_keystone": habit.is_keystone,
            "streak_risk": habit.current_streak > 0
            and habit_uid in user_context.at_risk_habits_or_empty(),
            "supports_goals": len(rels.linked_goal_uids),
            "reinforces_knowledge": len(rels.knowledge_reinforcement_uids),
        }

        # Determine trend
        if habit.current_streak > 7:
            analysis["trend"] = "strong"
        elif habit.current_streak > 3:
            analysis["trend"] = "building"
        elif habit.current_streak == 0:
            analysis["trend"] = "broken"
        else:
            analysis["trend"] = "starting"

        return Result.ok(analysis)

    def _calculate_consistency_from_completions(
        self, habit: Habit, completions: list[HabitCompletion], as_of_date: date
    ) -> float:
        """Adherence over the trailing consistency window, anchored at ``as_of_date``.

        The habit's completions inside the window divided by the number its own
        frequency expects there, clamped to 1.0 — a *ratio*, not the
        completions-per-week *rate*
        ``CrossDomainAnalyticsService.get_habit_consistency`` reports over the
        same span. Both read :class:`HabitConsistencyWindow`, so "the last thirty
        days" means one thing wherever the app says it.

        **Bounded at both ends.** Completing a *future* habit occurrence is
        legitimate behaviour — the calendar's day-scoped complete door admits any
        genuine occurrence day and ``TrackHabitRequest`` takes any ISO date — so
        a lower-bound-only filter counted work that has not happened yet toward
        present adherence, and went on counting it every day until its date
        arrived. A window that ends where the anchor does is what makes the
        numerator answer the same question the denominator asks.

        The span and ``expected`` now derive from one constant, and they have to:
        ``expected`` is a count of days (or of weekly targets scaled to them), so
        a window even one day wider lets the numerator outgrow what the
        denominator asks for. It was a day wider — ``as_of_date - 30`` with
        ``>=`` spans thirty-*one* days against an expectation of thirty.

        ⚠️ The anchor decides the window, so a caller passing anything other than
        today gets an as-of-*then* reading. That is right for analysis and wrong
        to persist: see the note at the ``success_rate`` write in
        :meth:`complete_habit_with_quality`.

        GRAPH-NATIVE: Completions fetched from graph, not from habit.completion_history.
        """
        if not completions:
            return 0.0

        window_start = HabitConsistencyWindow.start_date(as_of_date)
        window_end = HabitConsistencyWindow.end_date(as_of_date)
        recent_completions = [
            c for c in completions if window_start <= c.completed_at.date() <= window_end
        ]

        # Expected completions across the window, per the habit's own frequency.
        expected = HabitConsistencyWindow.DAYS  # Daily
        if habit.recurrence_pattern == HabitFrequency.WEEKLY:
            expected = HabitConsistencyWindow.DAYS // 7
        elif habit.recurrence_pattern == HabitFrequency.CUSTOM:
            # Use target_days_per_week for custom frequency, scaled to the window
            expected = ((habit.target_days_per_week or 0) * HabitConsistencyWindow.DAYS) // 7

        if expected == 0:
            return 0.0

        return min(1.0, len(recent_completions) / expected)

    # ========================================================================
    # KEYSTONE HABIT MANAGEMENT
    # ========================================================================

    async def get_keystone_habits(self, user_context: UserContext) -> Result[list[Habit]]:
        """
        Get user's keystone habits - habits that trigger other positive behaviors.
        """
        keystone_habits = []

        for habit_uid in user_context.keystone_habits:
            habit_result = await self.backend.get_habit(habit_uid)
            if habit_result.is_ok:
                habit = to_domain_model(habit_result.value, HabitDTO, Habit)
                keystone_habits.append(habit)

        return Result.ok(keystone_habits)

    async def identify_potential_keystone_habits(
        self, user_context: UserContext
    ) -> Result[list[Habit]]:
        """
        Identify habits that could become keystone habits based on their impact.
        """
        potential_keystones = []

        for habit_uid in user_context.active_habit_uids:
            if habit_uid not in user_context.keystone_habits:
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_ok:
                    habit = to_domain_model(habit_result.value, HabitDTO, Habit)

                    # GRAPH-NATIVE: Fetch relationships to check impact
                    rels = await HabitRelationships.fetch(habit_uid, self.relationships)

                    # Check if habit has high impact characteristics
                    if (
                        len(rels.linked_goal_uids) >= 2
                        or len(rels.knowledge_reinforcement_uids) >= 3
                        or habit.is_identity_habit  # Identity habits are high-impact
                    ):
                        potential_keystones.append(habit)

        return Result.ok(potential_keystones)

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    async def _consistency_window_completions(
        self, habit_uid: str, as_of_date: date
    ) -> list[HabitCompletion]:
        """This habit's completions inside the consistency window ending at ``as_of_date``.

        Bounded in the QUERY, not after it. ``find_by`` caps at its limit and
        says nothing about having done so, so an unbounded fetch of a habit with
        more completions than the cap returns only part of its history — and a
        habit kept daily for four months, or one carrying a run of legitimate
        future pre-completions, can have the window's own rows fall outside that
        part. Filtering afterwards then computes adherence from the wrong sample
        and persists it: a confident wrong ``success_rate``, never an error.
        Pushing both bounds into the query means the cap can only truncate rows
        that were going to count, and a thirty-day window cannot realistically
        reach it.

        GRAPH-NATIVE: Completion history is stored as separate HabitCompletion
        nodes, not as a serialized list on the Habit model.

        A failed read degrades to an empty list, which is what both callers did
        with the Result they no longer have to unpack: adherence over no known
        completions is 0.0, the same reading a habit with none at all gets.
        """
        result = await self.completions.get_completions_for_habit(
            habit_uid=habit_uid,
            start_date=HabitConsistencyWindow.start_date(as_of_date),
            end_date=HabitConsistencyWindow.end_date(as_of_date),
        )
        return result.value if result.is_ok else []

    def _update_goals_from_habit(
        self,
        goal_uids: list[str],
        habit_uid: str,
        new_streak: int,
        _user_context: UserContext,
    ) -> None:
        """Update linked goals based on habit progress."""
        # This would call the goals service to update progress
        self.logger.debug(
            "Would update %d goals from habit %s with streak %d",
            len(goal_uids),
            habit_uid,
            new_streak,
        )

    def _reinforce_knowledge(self, knowledge_uids: list[str], mastery_increment: float) -> None:
        """Reinforce knowledge through habit completion."""
        # This would call the knowledge service
        self.logger.debug(
            "Would reinforce %d knowledge items by %.2f", len(knowledge_uids), mastery_increment
        )

    def _trigger_keystone_effects(
        self, keystone_habit_uid: str, _user_context: UserContext
    ) -> None:
        """Trigger positive cascading effects from keystone habit."""
        # This could trigger creation of complementary habits, boost motivation, etc.
        self.logger.debug("Triggering keystone effects for habit %s", keystone_habit_uid)
