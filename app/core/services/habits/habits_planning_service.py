"""
Habits Planning Service - Context-First User Planning
=====================================================

Extracted following TasksPlanningService pattern (January 2026).

**Purpose:** Context-aware planning methods that leverage UserContext (~240 fields)
to provide personalized, filtered, and ranked habit queries.

**Pattern:** Context-First - "Filter by readiness, rank by relevance, enrich with insights"

**Habits-Specific Adaptations:**
- Prerequisites: Prerequisite habits established (streak >= 7 days)
- Readiness: Right day for frequency pattern (daily, weekly, etc.)
- Urgency: Streak at risk of breaking
- Relevance: Goal + identity + principle alignment

**Methods:**
- get_habit_priorities_for_user: Habits ranked by urgency/importance
- get_actionable_habits_for_user: Habits due today user should do
- get_learning_habits_for_user: Habits that reinforce knowledge
- get_goal_supporting_habits_for_user: Habits contributing to active goals
- get_habit_readiness_for_user: Calculate readiness per habit

**Static Helpers:**
- _calculate_readiness_score: Check prerequisites and frequency
- _calculate_relevance_score: Check goal and identity alignment
- _calculate_urgency_score: Check streak risk
- _identify_blocking_reasons: What's preventing engagement
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.enums import RecurrencePattern
from core.models.enums.ku_enums import HabitCategory
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_habit import HabitKu
from core.services.base_planning_service import BasePlanningService
from core.ports.domain_protocols import HabitsOperations
from core.utils.decorators import with_error_handling
from core.utils.dto_helpers import to_domain_model
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_priority_score

if TYPE_CHECKING:
    from core.models.context_types import ContextualDependencies, ContextualHabit
    from core.services.user.unified_user_context import UserContext


# Default threshold for considering a habit "established" (ready as prerequisite)
ESTABLISHED_STREAK_THRESHOLD = 7  # 7 days = habit formation baseline


class HabitsPlanningService(BasePlanningService[HabitsOperations, HabitKu]):
    """
    Context-aware habit planning service.

    Provides personalized habit recommendations based on user context.
    All methods use UserContext (~240 fields) for filtering and ranking.

    **Naming Convention:** *_for_user() suffix indicates context-awareness

    **Habits-Specific Scoring:**
    - Urgency: Based on streak risk (at-risk habits are high priority)
    - Readiness: Based on frequency pattern (should do today?)
    - Relevance: Based on goal support, identity alignment, principle alignment

    Inherits from BasePlanningService:
    - Constructor with backend + relationship_service
    - set_relationship_service() for post-construction wiring
    - _get_entities_by_uids() for batch entity fetching
    - _get_related_uids() for relationship queries
    """

    _domain_name = "Habits"

    # ========================================================================
    # PRIVATE HELPER METHODS (Domain-Specific)
    # ========================================================================

    async def _get_habits_by_uids(self, uids: list[str]) -> list[HabitKu]:
        """Alias for base class method with domain-specific naming."""
        return await self._get_entities_by_uids(uids)

    async def _get_related_habit_uids(self, relationship_key: str, entity_uid: str) -> list[str]:
        """Alias for base class method with domain-specific naming."""
        return await self._get_related_uids(relationship_key, entity_uid)

    def _get_habit_from_rich_context(self, habit_uid: str, context: UserContext) -> HabitKu | None:
        """
        Try to get Habit entity from UserContext rich data.

        Context-First Pattern: Use context data when available to avoid
        unnecessary Neo4j queries.

        Args:
            habit_uid: Habit identifier
            context: User's context (may contain rich habit data)

        Returns:
            Habit if found in rich context, None otherwise
        """
        if not context.active_habits_rich:
            return None

        for habit_data in context.active_habits_rich:
            habit_dict = habit_data.get("habit", {})
            if habit_dict.get("uid") == habit_uid:
                return self._dict_to_habit(habit_dict)

        return None

    def _dict_to_habit(self, habit_dict: dict[str, Any]) -> HabitKu:
        """
        Convert a habit dict (from rich context) to Habit domain model.

        Args:
            habit_dict: Habit properties as dict

        Returns:
            Habit domain model instance
        """
        dto = KuDTO(
            uid=habit_dict.get("uid", ""),
            user_uid=habit_dict.get("user_uid", ""),
            title=habit_dict.get("title", habit_dict.get("name", "")),
            description=habit_dict.get("description"),
            recurrence_pattern=habit_dict.get(
                "recurrence_pattern", habit_dict.get("frequency", RecurrencePattern.DAILY)
            ),
            target_days_per_week=habit_dict.get(
                "target_days_per_week", habit_dict.get("target_count", 7)
            ),
            current_streak=habit_dict.get("current_streak", 0),
            best_streak=habit_dict.get("best_streak", 0),
            total_completions=habit_dict.get("total_completions", 0),
            success_rate=habit_dict.get("success_rate", habit_dict.get("consistency_30d", 0.0)),
            last_completed=habit_dict.get("last_completed"),
            status=habit_dict.get("status", "active"),
            cue=habit_dict.get("cue"),
            routine=habit_dict.get("routine"),
            reward=habit_dict.get("reward"),
            created_at=habit_dict.get("created_at") or datetime.now(),
            updated_at=habit_dict.get("updated_at") or datetime.now(),
        )
        return to_domain_model(dto, KuDTO, HabitKu)

    # ========================================================================
    # CONTEXT-FIRST METHODS
    # ========================================================================
    # These methods leverage UserContext to provide personalized,
    # filtered, and ranked relationship queries.
    #
    # Naming Convention: *_for_user() suffix indicates context-awareness
    #
    # Philosophy: "Filter by readiness, rank by relevance, enrich with insights"

    @with_error_handling("get_habit_priorities_for_user", error_type="database")
    async def get_habit_priorities_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[ContextualHabit]]:
        """
        Get habits ranked by urgency and importance.

        **THE KEY METHOD** for daily habit prioritization - returns habits:
        1. At-risk habits first (streak about to break)
        2. Identity habits second (voting for who you want to become)
        3. Keystone habits third (trigger other positive behaviors)
        4. All other habits ranked by goal support

        **Context Fields Used:**
        - at_risk_habits: Habits with streaks at risk
        - active_habit_uids: User's current habits
        - active_habits_rich: Rich habit data with graph_context (preferred)
        - keystone_habits: High-impact habits
        - active_goal_uids: For relevance calculation

        Args:
            context: User's complete context (~240 fields)
            limit: Maximum habits to return

        Returns:
            Result[list[ContextualHabit]] - sorted by priority (highest first)
        """
        from core.models.context_types import ContextualHabit

        prioritized = []

        for habit_uid in context.active_habit_uids:
            # CONTEXT-FIRST: Try rich context first
            habit = self._get_habit_from_rich_context(habit_uid, context)
            graph_ctx = {}

            if habit is None:
                # Fallback: Query Neo4j
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_error or not habit_result.value:
                    continue
                habit = to_domain_model(habit_result.value, KuDTO, HabitKu)
            else:
                # Extract graph context if available
                for habit_data in context.active_habits_rich:
                    if habit_data.get("habit", {}).get("uid") == habit_uid:
                        graph_ctx = habit_data.get("graph_context", {})
                        break

            # Get goal associations from graph context
            goal_uids = [g.get("uid") for g in graph_ctx.get("linked_goals", []) if g.get("uid")]
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("applied_knowledge", []) if k.get("uid")
            ]

            contextual = ContextualHabit.from_entity_and_context(
                uid=habit_uid,
                title=habit.title,
                context=context,
                supported_goal_uids=goal_uids,
                applied_knowledge_uids=knowledge_uids,
                current_streak=habit.current_streak,
                completion_rate=habit.success_rate,
                days_since_last=self._days_since_last_completion(habit),
                best_streak=habit.best_streak,
                weights=(0.3, 0.3, 0.4),
            )
            prioritized.append(contextual)

        # Sort by priority (highest first)
        prioritized.sort(key=get_priority_score, reverse=True)

        self.logger.info(
            f"Found {len(prioritized)} prioritized habits for user "
            f"(at_risk={len(context.at_risk_habits)}, keystone={len(context.keystone_habits)})"
        )

        return Result.ok(prioritized[:limit])

    @with_error_handling("get_actionable_habits_for_user", error_type="database")
    async def get_actionable_habits_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[ContextualHabit]]:
        """
        Get habits user should do today, ranked by priority.

        **FAIL-FAST PATTERN:** Uses rich context when available.

        Returns habits that:
        1. Are scheduled for today (based on frequency pattern)
        2. Haven't been completed today yet
        3. Are not paused or archived

        **Context Fields Used:**
        - active_habit_uids: User's current habits
        - active_habits_rich: Rich habit data (preferred)
        - at_risk_habits: Urgency boost

        Args:
            context: User's complete context
            limit: Maximum habits to return

        Returns:
            Result[list[ContextualHabit]] - sorted by priority (highest first)
        """
        from core.models.context_types import ContextualHabit

        today = date.today()
        actionable = []

        for habit_uid in context.active_habit_uids:
            # CONTEXT-FIRST: Try rich context first
            habit = self._get_habit_from_rich_context(habit_uid, context)
            graph_ctx = {}

            if habit is None:
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_error or not habit_result.value:
                    continue
                habit = to_domain_model(habit_result.value, KuDTO, HabitKu)
            else:
                for habit_data in context.active_habits_rich:
                    if habit_data.get("habit", {}).get("uid") == habit_uid:
                        graph_ctx = habit_data.get("graph_context", {})
                        break

            # Check if should do today
            if not habit.should_do_today():
                continue

            # Check if already completed today
            if habit.last_completed and habit.last_completed.date() == today:
                continue

            goal_uids = [g.get("uid") for g in graph_ctx.get("linked_goals", []) if g.get("uid")]
            is_keystone = habit_uid in context.keystone_habits

            # Compute urgency + relevance for custom weighting
            is_at_risk = habit_uid in context.at_risk_habits
            urgency = self._calculate_urgency_score(habit, is_at_risk)
            relevance = self._calculate_relevance_score(
                goal_uids, habit.is_identity_habit, is_keystone, context
            )
            priority = (urgency * 0.5) + (relevance * 0.3) + (0.2 if is_keystone else 0.1)

            contextual = ContextualHabit.from_entity_and_context(
                uid=habit_uid,
                title=habit.title,
                context=context,
                supported_goal_uids=goal_uids,
                is_due_today=True,
                current_streak=habit.current_streak,
                completion_rate=habit.success_rate,
                days_since_last=self._days_since_last_completion(habit),
                best_streak=habit.best_streak,
                readiness_override=1.0,
                relevance_override=relevance,
                priority_override=priority,
            )
            actionable.append(contextual)

        actionable.sort(key=get_priority_score, reverse=True)

        self.logger.info(
            f"Found {len(actionable)} actionable habits for user today "
            f"(from {len(context.active_habit_uids)} active)"
        )

        return Result.ok(actionable[:limit])

    @with_error_handling("get_learning_habits_for_user", error_type="database")
    async def get_learning_habits_for_user(
        self,
        context: UserContext,
        knowledge_focus: list[str] | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualHabit]]:
        """
        Get habits that reinforce knowledge user is learning.

        **Philosophy:** "Practice makes permanent" - find habits that reinforce learning.

        Returns habits that:
        1. Practice knowledge units the user is actively learning
        2. Are in the LEARNING category
        3. Come from curriculum (learning step/path source)

        **Context Fields Used:**
        - in_progress_knowledge_uids: Knowledge being learned
        - knowledge_mastery: Current mastery levels
        - active_habit_uids: User's current habits

        Args:
            context: User's complete context
            knowledge_focus: Specific knowledge to find habits for (optional)
            limit: Maximum habits to return

        Returns:
            List of ContextualHabit that reinforce learning knowledge
        """
        from core.models.context_types import ContextualHabit

        learning_ku = knowledge_focus or list(context.in_progress_knowledge_uids)

        # If no knowledge in progress, suggest knowledge with partial mastery
        if not learning_ku:
            learning_ku = [
                ku_uid
                for ku_uid, mastery in context.knowledge_mastery.items()
                if 0.3 <= mastery < 0.8  # Building but not mastered
            ][:10]

        learning_habits = []
        seen_uids: set[str] = set()

        for habit_uid in context.active_habit_uids:
            if habit_uid in seen_uids:
                continue

            # CONTEXT-FIRST: Try rich context first
            habit = self._get_habit_from_rich_context(habit_uid, context)
            graph_ctx = {}

            if habit is None:
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_error or not habit_result.value:
                    continue
                habit = to_domain_model(habit_result.value, KuDTO, HabitKu)
            else:
                for habit_data in context.active_habits_rich:
                    if habit_data.get("habit", {}).get("uid") == habit_uid:
                        graph_ctx = habit_data.get("graph_context", {})
                        break

            # Get knowledge UIDs this habit practices
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("applied_knowledge", []) if k.get("uid")
            ]

            # Check if habit reinforces learning knowledge
            is_learning_habit = (
                habit.habit_category == HabitCategory.LEARNING
                or habit.source_learning_step_uid is not None
                or habit.source_learning_path_uid is not None
                or any(ku in learning_ku for ku in knowledge_uids)
            )

            if not is_learning_habit:
                continue

            seen_uids.add(habit_uid)

            # Calculate learning impact
            learning_overlap = len([k for k in knowledge_uids if k in learning_ku])
            learning_impact = min(1.0, learning_overlap * 0.3 + 0.4)

            contextual = ContextualHabit.from_entity_and_context(
                uid=habit_uid,
                title=habit.title,
                context=context,
                applied_knowledge_uids=knowledge_uids,
                current_streak=habit.current_streak,
                completion_rate=habit.success_rate,
                readiness_override=0.8,
                relevance_override=learning_impact,
                priority_override=learning_impact,
            )
            learning_habits.append(contextual)

        # Sort by learning impact
        learning_habits.sort(key=get_priority_score, reverse=True)

        self.logger.info(f"Found {len(learning_habits)} learning habits for user")
        return Result.ok(learning_habits[:limit])

    @with_error_handling("get_goal_supporting_habits_for_user", error_type="database")
    async def get_goal_supporting_habits_for_user(
        self,
        context: UserContext,
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualHabit]]:
        """
        Get habits that contribute to active goals.

        Returns habits that support user's goals, optionally filtered
        to a specific goal.

        **Context Fields Used:**
        - active_goal_uids: User's active goals
        - active_habit_uids: User's habits
        - active_habits_rich: Rich habit data with goal links

        Args:
            context: User's complete context
            goal_uid: Optional specific goal to filter by
            limit: Maximum habits to return

        Returns:
            List of ContextualHabit that support goals
        """
        from core.models.context_types import ContextualHabit

        goal_habits = []

        for habit_uid in context.active_habit_uids:
            # CONTEXT-FIRST: Try rich context first
            habit = self._get_habit_from_rich_context(habit_uid, context)
            graph_ctx = {}

            if habit is None:
                habit_result = await self.backend.get_habit(habit_uid)
                if habit_result.is_error or not habit_result.value:
                    continue
                habit = to_domain_model(habit_result.value, KuDTO, HabitKu)
            else:
                for habit_data in context.active_habits_rich:
                    if habit_data.get("habit", {}).get("uid") == habit_uid:
                        graph_ctx = habit_data.get("graph_context", {})
                        break

            # Get goal UIDs this habit supports
            supported_goals = [
                g.get("uid") for g in graph_ctx.get("linked_goals", []) if g.get("uid")
            ]

            # Filter by specific goal if provided
            if goal_uid:
                if goal_uid not in supported_goals:
                    continue
            else:
                # Check if supports any active goal
                if not any(g in context.active_goal_uids for g in supported_goals):
                    continue

            # Calculate goal support score
            active_goal_support = len([g for g in supported_goals if g in context.active_goal_uids])
            goal_support_score = min(1.0, active_goal_support * 0.3 + 0.4)

            contextual = ContextualHabit.from_entity_and_context(
                uid=habit_uid,
                title=habit.title,
                context=context,
                supported_goal_uids=supported_goals,
                is_due_today=habit.should_do_today(),
                current_streak=habit.current_streak,
                completion_rate=habit.success_rate,
                relevance_override=goal_support_score,
                priority_override=goal_support_score,
            )
            goal_habits.append(contextual)

        goal_habits.sort(key=get_priority_score, reverse=True)

        self.logger.info(
            f"Found {len(goal_habits)} goal-supporting habits for user"
            f"{f' (filtered to {goal_uid})' if goal_uid else ''}"
        )
        return Result.ok(goal_habits[:limit])

    @with_error_handling(
        "get_habit_readiness_for_user", error_type="database", uid_param="habit_uid"
    )
    async def get_habit_readiness_for_user(
        self,
        habit_uid: str,
        context: UserContext,
    ) -> Result[ContextualDependencies]:
        """
        Get habit readiness with blocking reasons.

        **Context-First Pattern:** Returns dependencies enriched with:
        - Readiness scores (frequency match, prerequisites established?)
        - Relevance scores (goal alignment)
        - Blocking reasons (what's preventing engagement?)
        - Recommendations (what to do next)

        **Habit Prerequisites:**
        Unlike tasks which require knowledge mastery, habits require
        *prerequisite habits* to be established (streak >= 7 days).

        Args:
            habit_uid: Habit to check readiness for
            context: User's complete context

        Returns:
            ContextualDependencies with enriched readiness data
        """
        from core.models.context_types import ContextualDependencies, ContextualHabit

        # Get the habit
        habit = self._get_habit_from_rich_context(habit_uid, context)
        if habit is None:
            habit_result = await self.backend.get_habit(habit_uid)
            if habit_result.is_error:
                return Result.fail(habit_result.expect_error())
            if not habit_result.value:
                return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))
            habit = to_domain_model(habit_result.value, KuDTO, HabitKu)

        # Get prerequisite habit UIDs
        prereq_uids = await self._get_related_uids("prerequisite_habits", habit_uid)

        # Check prerequisite habits
        ready_deps = []
        blocked_deps = []
        blocking_reasons = []

        for prereq_uid in prereq_uids:
            prereq_streak = context.habit_streaks.get(prereq_uid, 0)
            prereq_habit = self._get_habit_from_rich_context(prereq_uid, context)

            if prereq_habit is None:
                prereq_result = await self.backend.get_habit(prereq_uid)
                if prereq_result.is_error or not prereq_result.value:
                    continue
                prereq_habit = to_domain_model(prereq_result.value, KuDTO, HabitKu)

            is_established = prereq_streak >= ESTABLISHED_STREAK_THRESHOLD

            contextual_prereq = ContextualHabit.from_entity_and_context(
                uid=prereq_uid,
                title=prereq_habit.title,
                context=context,
                current_streak=prereq_streak,
                completion_rate=prereq_habit.success_rate,
                readiness_override=1.0
                if is_established
                else prereq_streak / ESTABLISHED_STREAK_THRESHOLD,
                relevance_override=0.8,
                priority_override=0.9 if not is_established else 0.5,
            )

            if is_established:
                ready_deps.append(contextual_prereq)
            else:
                blocked_deps.append(contextual_prereq)
                blocking_reasons.append(
                    f"Prerequisite habit '{prereq_habit.title}' needs {ESTABLISHED_STREAK_THRESHOLD - prereq_streak} more days to establish"
                )

        # Check frequency readiness
        today = date.today()
        should_do = habit.should_do_today()
        if not should_do:
            blocking_reasons.append(f"Not scheduled for today ({today.strftime('%A')})")

        # Generate recommendation
        recommendation = ""
        if blocked_deps:
            highest = blocked_deps[0]
            recommendation = f"Establish prerequisite habit '{highest.title}' first (need {ESTABLISHED_STREAK_THRESHOLD}-day streak)"
        elif not should_do:
            recommendation = "This habit is scheduled for different days. Focus on today's habits."
        else:
            recommendation = "All prerequisites met - proceed with this habit!"

        return Result.ok(
            ContextualDependencies(
                entity_uid=habit_uid,
                entity_type="Habit",
                ready_dependencies=tuple(ready_deps),
                blocked_dependencies=tuple(blocked_deps),
                habit_requirements=tuple(ready_deps + blocked_deps),
                total_blocking_items=len(blocked_deps) + (0 if should_do else 1),
                recommended_next_action=recommendation,
            )
        )

    # ========================================================================
    # CONTEXT-FIRST HELPER METHODS (Habit-Specific)
    # ========================================================================

    @staticmethod
    def _calculate_readiness_score(
        habit: HabitKu,
        as_of_date: date,
    ) -> float:
        """
        Calculate readiness based on frequency pattern.

        Habits are "ready" if scheduled for today.

        Args:
            habit: Habit to check
            as_of_date: Date to check against

        Returns:
            1.0 if should do today, 0.0 otherwise
        """
        return 1.0 if habit.should_do_today() else 0.0

    @staticmethod
    def _calculate_urgency_score(
        habit: HabitKu,
        is_at_risk: bool,
    ) -> float:
        """
        Calculate urgency based on streak risk.

        **Habits-Specific:** Urgency is based on:
        - Streak length (longer streaks = more to lose)
        - At-risk status (about to break = urgent)

        Formula: urgency = (streak_factor * 0.3) + (at_risk_factor * 0.7)

        Args:
            habit: Habit to score
            is_at_risk: Whether streak is at risk

        Returns:
            Urgency score 0.0-1.0
        """
        # Streak factor: longer streaks are more valuable to protect
        streak_factor = min(1.0, habit.current_streak / 30)  # Cap at 30-day streak

        # At-risk factor: urgent if about to break
        at_risk_factor = 1.0 if is_at_risk else 0.0

        return (streak_factor * 0.3) + (at_risk_factor * 0.7)

    @staticmethod
    def _calculate_relevance_score(
        goal_uids: list[str],
        is_identity_habit: bool,
        is_keystone: bool,
        context: UserContext,
    ) -> float:
        """
        Calculate relevance based on goal and identity alignment.

        **Habits-Specific:** Relevance includes:
        - Goal support (habits supporting active goals)
        - Identity alignment (voting for who you want to become)
        - Keystone status (triggers other positive behaviors)

        Args:
            goal_uids: Goals this habit supports
            is_identity_habit: Whether this reinforces identity
            is_keystone: Whether this is a keystone habit
            context: User context for active goals

        Returns:
            Relevance score 0.0-1.0
        """
        score = 0.0

        # Goal alignment (up to 0.5)
        if goal_uids:
            aligned = len([g for g in goal_uids if g in context.active_goal_uids])
            score += min(0.5, aligned * 0.15)

        # Identity alignment boost (+0.2)
        if is_identity_habit:
            score += 0.2

        # Keystone boost (+0.2)
        if is_keystone:
            score += 0.2

        # Base relevance if no other factors (0.3)
        if score == 0.0:
            score = 0.3

        return min(1.0, score)

    @staticmethod
    def _days_since_last_completion(habit: HabitKu) -> int:
        """Calculate days since last completion."""
        if not habit.last_completed:
            return 999  # Never completed
        return (datetime.now() - habit.last_completed).days
