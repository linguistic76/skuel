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

from datetime import date, datetime, timedelta
from operator import attrgetter
from typing import Any

from core.events import HabitCompleted, HabitStreakBroken, HabitStreakMilestone, publish_event
from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.ports.domain_protocols import HabitsOperations
from core.ports.query_types import HabitUpdatePayload
from core.services.habits.habit_relationships import HabitRelationships
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
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


    Source Tag: "habits_progress_service_explicit"
    - Format: "habits_progress_service_explicit" for user-created relationships
    - Format: "habits_progress_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from habits_progress metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

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
            relationship_service: HabitsRelationshipService for graph relationships (REQUIRED)
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
        if not user_context.active_habits_rich:
            return None

        for habit_data in user_context.active_habits_rich:
            habit_dict = habit_data.get("habit", {})
            if habit_dict.get("uid") == habit_uid:
                # Convert dict to Habit domain model
                return self._dict_to_habit(habit_dict)

        return None

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
        if not user_context.active_habits_rich:
            return None

        for habit_data in user_context.active_habits_rich:
            habit_dict = habit_data.get("habit", {})
            if habit_dict.get("uid") == habit_uid:
                graph_ctx = habit_data.get("graph_context", {})
                if graph_ctx:
                    return HabitRelationships(
                        linked_goal_uids=[
                            g.get("uid")
                            for g in graph_ctx.get("linked_goals", [])
                            if g and g.get("uid")
                        ],
                        knowledge_reinforcement_uids=[
                            k.get("uid")
                            for k in graph_ctx.get("applied_knowledge", [])
                            if k and k.get("uid")
                        ],
                        # NOTE: prerequisite_habit_uids not in HabitRelationships model
                    )

        return None

    def _dict_to_habit(self, habit_dict: dict[str, Any]) -> Habit:
        """
        Convert a habit dict (from rich context) to Habit domain model.

        Args:
            habit_dict: Habit properties as dict

        Returns:
            Habit domain model instance
        """
        # Create DTO first, then convert to domain model
        # Map old field names to new HabitDTO field names
        dto = HabitDTO(
            uid=habit_dict.get("uid", ""),
            user_uid=habit_dict.get("user_uid", ""),
            title=habit_dict.get("title", habit_dict.get("name", "")),
            description=habit_dict.get("description"),
            # Map 'frequency' to 'recurrence_pattern' (model uses RecurrencePattern enum)
            recurrence_pattern=habit_dict.get(
                "recurrence_pattern", habit_dict.get("frequency", HabitFrequency.DAILY)
            ),
            # Map 'target_count' to 'target_days_per_week' (closest equivalent)
            target_days_per_week=habit_dict.get(
                "target_days_per_week", habit_dict.get("target_count", 7)
            ),
            current_streak=habit_dict.get("current_streak", 0),
            best_streak=habit_dict.get("best_streak", 0),
            total_completions=habit_dict.get("total_completions", 0),
            # NOTE: consistency_30d and is_keystone not in HabitDTO - use success_rate for metrics
            success_rate=habit_dict.get("success_rate", habit_dict.get("consistency_30d", 0.0)),
            last_completed=habit_dict.get("last_completed"),
            status=habit_dict.get("status", "active"),
            cue=habit_dict.get("cue"),
            routine=habit_dict.get("routine"),
            reward=habit_dict.get("reward"),
            created_at=habit_dict.get("created_at"),
            updated_at=habit_dict.get("updated_at"),
        )
        return to_domain_model(dto, HabitDTO, Habit)

    def _get_streak_from_context(self, habit_uid: str, user_context: UserContext) -> int | None:
        """
        Get habit's current streak from UserContext (standard context).

        This is available even without rich context, from the basic
        habit_streaks dict populated by the MEGA-QUERY.

        Args:
            habit_uid: Habit identifier
            user_context: User's context

        Returns:
            Current streak if in context, None otherwise
        """
        return user_context.habit_streaks.get(habit_uid)

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
                return Result.fail(habit_result.expect_error())
            habit = to_domain_model(habit_result.value, HabitDTO, Habit)

        if context_hit:
            self.logger.debug(f"Context-first HIT: habit {habit_uid} from rich context")
        else:
            self.logger.debug(f"Context-first MISS: habit {habit_uid} queried from Neo4j")

        # ====================================================================
        # ALWAYS QUERY: Completion history (not in context - mutable data)
        # ====================================================================

        completions_result = await self._get_habit_completions(habit_uid)
        existing_completions = completions_result.value if completions_result.is_ok else []

        # ====================================================================
        # CALCULATE STREAK
        # ====================================================================

        new_streak = habit.current_streak
        streak_broken = False
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

        updates: HabitUpdatePayload = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "last_completed": datetime.combine(completion_date, datetime.min.time()),
            "total_completions": habit.total_completions + 1,
        }

        # Calculate consistency score (pass completions for calculation)
        consistency = self._calculate_consistency_from_completions(
            habit, existing_completions, completion_date
        )
        updates["consistency_30d"] = consistency

        update_result = await self.backend.update_habit(habit_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

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
            await self._update_goals_from_habit(
                rels.linked_goal_uids, habit_uid, new_streak, user_context
            )

        # 2. Reinforce knowledge if quality is good (from graph relationships)
        if quality_score >= 4 and rels.knowledge_reinforcement_uids:
            await self._reinforce_knowledge(
                rels.knowledge_reinforcement_uids, 0.05
            )  # 5% mastery boost

        # 3. Check keystone habit effects
        if habit.is_keystone and new_streak >= 7:
            await self._trigger_keystone_effects(habit_uid, user_context)

        # Context invalidation happens via HabitCompleted/HabitStreakBroken/HabitStreakMilestone events (event-driven architecture)
        # Event handlers in bootstrap will call user_service.invalidate_context()

        completed_habit = to_domain_model(update_result.value, HabitDTO, Habit)

        # PUBLISH EVENTS

        # 1. Always publish HabitCompleted
        completed_event = HabitCompleted(
            habit_uid=habit_uid,
            user_uid=user_context.user_uid,
            occurred_at=datetime.now(),
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
                occurred_at=datetime.now(),
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
                occurred_at=datetime.now(),
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

        for habit_uid in user_context.at_risk_habits:
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
                return Result.fail(habit_result.expect_error())
            habit = to_domain_model(habit_result.value, HabitDTO, Habit)
            self.logger.debug(f"Context-first MISS: habit {habit_uid} queried for analysis")
        else:
            self.logger.debug(
                f"Context-first HIT: habit {habit_uid} from rich context for analysis"
            )

        # ALWAYS QUERY: Completions (mutable data, not in context)
        completions_result = await self._get_habit_completions(habit_uid)
        completions = completions_result.value if completions_result.is_ok else []

        # Calculate various consistency metrics
        consistency_30d = self._calculate_consistency_from_completions(
            habit, completions, date.today()
        )

        # Get quality trend from recent completions
        recent_quality = 0.0
        if completions:
            recent_completions = completions[-10:]  # Last 10 completions
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
            "streak_risk": habit.current_streak > 0 and habit_uid in user_context.at_risk_habits,
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
        """
        Calculate 30-day consistency score from HabitCompletion records.

        GRAPH-NATIVE: Completions fetched from graph, not from habit.completion_history.
        """
        if not completions:
            return 0.0

        # Count completions in last 30 days
        thirty_days_ago = as_of_date - timedelta(days=30)
        recent_completions = [c for c in completions if c.completed_at.date() >= thirty_days_ago]

        # Calculate expected completions based on frequency
        expected = 30  # Daily
        if habit.recurrence_pattern == HabitFrequency.WEEKLY:
            expected = 4
        elif habit.recurrence_pattern == HabitFrequency.CUSTOM:
            # Use target_days_per_week for custom frequency
            expected = ((habit.target_days_per_week or 0) * 30) // 7  # Scale to month

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

    async def _get_habit_completions(
        self, habit_uid: str, limit: int = 100
    ) -> Result[list[HabitCompletion]]:
        """
        Fetch HabitCompletion records for a habit from graph.

        GRAPH-NATIVE: Completion history is stored as separate HabitCompletion nodes,
        not as a serialized list on the Habit model.

        Args:
            habit_uid: UID of habit to fetch completions for
            limit: Max number of completions to fetch (default 100)

        Returns:
            Result[list[HabitCompletion]] with completions sorted by date (most recent first)
        """
        return await self.completions.get_completions_for_habit(
            habit_uid=habit_uid,
            start_date=None,  # All completions
            end_date=None,
            limit=limit,
        )

    async def _update_goals_from_habit(
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

    async def _reinforce_knowledge(
        self, knowledge_uids: list[str], mastery_increment: float
    ) -> None:
        """Reinforce knowledge through habit completion."""
        # This would call the knowledge service
        self.logger.debug(
            "Would reinforce %d knowledge items by %.2f", len(knowledge_uids), mastery_increment
        )

    async def _trigger_keystone_effects(
        self, keystone_habit_uid: str, _user_context: UserContext
    ) -> None:
        """Trigger positive cascading effects from keystone habit."""
        # This could trigger creation of complementary habits, boost motivation, etc.
        self.logger.debug("Triggering keystone effects for habit %s", keystone_habit_uid)
