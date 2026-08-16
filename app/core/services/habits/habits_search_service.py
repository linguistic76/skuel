"""
Habit Search Service - Search and Discovery Operations
=======================================================

Handles search and discovery operations for habits.
Implements DomainSearchOperations[Habit] protocol plus habit-specific methods.

**Responsibilities:**
- Text search on title/description
- Filter by status, domain/category, frequency
- Time-based queries (due today, overdue, at risk)
- Context-aware prioritization
- Graph-based relationship queries

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md
"""

from datetime import date, timedelta
from typing import ClassVar

from core.models.enums import EntityStatus
from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.search.scoring import score_habit
from core.models.type_hints import UserUID
from core.ports.domain_protocols import HabitsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.habits._goal_links import enrich_habits_with_goal_links
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score
from core.utils.timestamp_helpers import get_frequency_window_days


class HabitsSearchService(BaseService[HabitsOperations, Habit]):
    """
    Habit search and discovery operations.

    Implements DomainSearchOperations[Habit] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by EntityStatus
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_upcoming() - Habits due within N days (based on frequency)
    - get_overdue() - Overdue habits

    Habit-Specific Methods:
    - get_by_frequency() - Filter by HabitFrequency (daily, weekly, monthly)
    - get_needing_attention() - Habits with low/broken streaks
    - get_at_risk() - Habits at risk of breaking streak
    - get_due_today() - Habits due today based on frequency
    - get_by_category() - Filter by category string
    - list_categories() - Get all unique habit categories

    Semantic Types Used:
    - SUPPORTS_GOAL: Habit supports goal achievement
    - REINFORCES_KNOWLEDGE: Habit reinforces knowledge retention
    - INSPIRED_BY_PRINCIPLE: Habit inspired by guiding principle
    - TRACKED_BY: Habit tracked by user
    """

    # DomainConfig consolidation (January 2026)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        entity_label="Entity",
        domain_name="habits",
        date_field="created_at",  # Habits don't have due_date, use created_at
        completed_statuses=(EntityStatus.COMPLETED.value,),
        category_field="habit_category",  # Habits store category as 'habit_category'
    )

    # Status filtering constants - eliminates duplication across methods
    # INACTIVE includes PAUSED (fully inactive habits)
    _INACTIVE_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {
            EntityStatus.ARCHIVED.value,
            EntityStatus.COMPLETED.value,
            EntityStatus.CANCELLED.value,
            EntityStatus.PAUSED.value,
        }
    )

    # TERMINAL excludes PAUSED (for get_prioritized and get_needing_attention)
    _TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {
            EntityStatus.ARCHIVED.value,
            EntityStatus.COMPLETED.value,
            EntityStatus.CANCELLED.value,
        }
    )

    # Inherited from BaseService (December 2025):
    # - search(), get_by_status(), get_by_category(),
    # - list_categories(), get_by_relationship()

    def _is_active(self, habit: Habit, include_paused: bool = False) -> bool:
        """
        Check if habit is active (not in inactive/terminal state).

        Args:
            habit: Habit to check
            include_paused: If True, treats PAUSED as active (use TERMINAL_STATUSES)

        Returns:
            True if habit is active
        """
        inactive = self._TERMINAL_STATUSES if include_paused else self._INACTIVE_STATUSES
        return not habit.status or habit.status.value not in inactive

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Habit]]:
        """
        Get habits prioritized for the user's current context.

        Uses Cypher WHERE clause to filter terminal statuses at the database
        level, then delegates to the unified ``score_habit`` scorer.

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing habits sorted by priority/relevance
        """
        result = await self.backend.get_active_habits_prioritized(
            user_uid=user_context.user_uid,
            terminal_statuses=list(self._TERMINAL_STATUSES),
            limit=limit * 2,  # Fetch extra for scoring refinement
        )
        if result.is_error:
            return Result.fail(result)

        habits = self._to_domain_models(result.value, HabitDTO, Habit)
        habits = await enrich_habits_with_goal_links(
            self.backend, habits, user_context.active_goal_uids
        )
        scored = [(habit, score_habit(habit, user_context).total) for habit in habits]
        scored.sort(key=get_result_score, reverse=True)
        prioritized = [habit for habit, _ in scored[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} habits for user {user_context.user_uid}")
        return Result.ok(prioritized)

    async def enrich_with_goal_links(  # skuel-lint: disable=SKUEL005 -- fail-soft enrichment by design: a backend error returns the habits unchanged, never an error
        self, habits: list[Habit], active_goal_uids: list[str] | None = None
    ) -> list[Habit]:
        """Populate each habit's derived ``supports_goal_uid`` from its SUPPORTS_GOAL edge.

        The reusable half of ``get_prioritized``'s enrichment step, exposed for
        callers that score an arbitrary habit list (SearchRouter's cross-domain
        result scoring). Habits with no edge come back unchanged.
        """
        return await enrich_habits_with_goal_links(self.backend, habits, active_goal_uids)

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_upcoming", error_type="database")
    async def get_upcoming(
        self,
        days_ahead: int = 7,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Habit]]:
        """
        Get habits upcoming within specified number of days based on frequency.

        For habits, "upcoming" means habits that need completion based on their
        frequency pattern within the time window.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing habits upcoming
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Get active habits - use user_uid filter if provided
        filters = {"user_uid": user_uid} if user_uid else {}
        result = await self.backend.find_by(limit=limit * 5, **filters)
        if result.is_error:
            return Result.fail(result)

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits upcoming within window
        upcoming = []
        for habit in habits:
            # Skip inactive (including paused)
            if not self._is_active(habit):
                continue

            # Check if due based on frequency
            is_due = self._is_habit_due_in_window(habit, today, end_date)
            if is_due:
                upcoming.append(habit)

            if len(upcoming) >= limit:
                break

        self.logger.debug(f"Found {len(upcoming)} habits upcoming within {days_ahead} days")
        return Result.ok(upcoming)

    def _is_habit_due_in_window(self, habit: Habit, start_date: date, _end_date: date) -> bool:
        """Check if habit is due within the date window based on frequency."""
        if not habit.last_completed:
            return True  # Never completed - due

        last_date = habit.last_completed.date()
        window_days = get_frequency_window_days(habit.recurrence_pattern)
        days_since = (start_date - last_date).days
        return days_since >= window_days

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Habit]]:
        """
        Get habits that are overdue based on their frequency.

        A habit is overdue if it hasn't been completed within its frequency window.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue habits
        """
        today = date.today()

        # Get active habits - use user_uid filter if provided
        filters = {"user_uid": user_uid} if user_uid else {}
        result = await self.backend.find_by(limit=limit * 2, **filters)  # Fetch extra for filtering
        if result.is_error:
            return Result.fail(result)

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active overdue habits
        overdue = []
        for habit in habits:
            # Skip inactive (including paused)
            if not self._is_active(habit):
                continue

            # Check if overdue based on frequency
            if self._is_habit_overdue(habit, today):
                overdue.append(habit)

            if len(overdue) >= limit:
                break

        self.logger.debug(f"Found {len(overdue)} overdue habits")
        return Result.ok(overdue)

    def _is_habit_overdue(self, habit: Habit, today: date) -> bool:
        """Check if habit is overdue based on frequency."""
        if not habit.last_completed:
            # Never completed - check if created > 1 day ago
            if habit.created_at:
                created_date = habit.created_at.date()
                return (today - created_date).days > 1
            return True

        last_date = habit.last_completed.date()
        days_since = (today - last_date).days
        window_days = get_frequency_window_days(habit.recurrence_pattern)
        return days_since > window_days

    # ========================================================================
    # HABIT-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_by_frequency", error_type="database")
    async def get_by_frequency(
        self, frequency: HabitFrequency, limit: int = 100
    ) -> Result[list[Habit]]:
        """
        Get habits filtered by frequency.

        Args:
            frequency: HabitFrequency enum (DAILY, WEEKLY, MONTHLY, etc.)
            limit: Maximum results to return

        Returns:
            Result containing habits with matching frequency
        """
        from core.utils.type_converters import get_enum_value

        frequency_value = get_enum_value(frequency)
        result = await self.backend.find_by(frequency=frequency_value, limit=limit)
        if result.is_error:
            return result

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        self.logger.debug(f"Found {len(habits)} {frequency_value} habits")
        return Result.ok(habits)

    @with_error_handling("get_needing_attention", error_type="database")
    async def get_needing_attention(
        self, streak_threshold: int = 3, limit: int = 50
    ) -> Result[list[Habit]]:
        """
        Get habits that need attention based on streak status.

        Habits needing attention:
        - Broken streaks (was > streak_threshold, now 0)
        - Low streaks (< streak_threshold)
        - Never completed

        Args:
            streak_threshold: Minimum streak to be considered "healthy" (default 3)
            limit: Maximum results to return

        Returns:
            Result containing habits needing attention
        """
        # Get all habits
        result = await self.backend.find_by(limit=limit * 2)
        if result.is_error:
            return Result.fail(result)

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits needing attention (include_paused=True to check paused habits too)
        needing_attention = []
        for habit in habits:
            # Skip terminal habits (archived/completed/cancelled), but check paused habits
            if not self._is_active(habit, include_paused=True):
                continue

            current_streak = habit.current_streak or 0
            best_streak = habit.best_streak or 0

            # Needs attention if:
            # 1. Had a good streak but lost it
            # 2. Low current streak
            # 3. Never completed
            if best_streak >= streak_threshold and current_streak < streak_threshold:
                needing_attention.append(habit)  # Lost streak
            elif current_streak < streak_threshold:
                needing_attention.append(habit)  # Low streak
            elif not habit.last_completed:
                needing_attention.append(habit)  # Never done

            if len(needing_attention) >= limit:
                break

        self.logger.debug(f"Found {len(needing_attention)} habits needing attention")
        return Result.ok(needing_attention)

    @with_error_handling("get_at_risk", error_type="database")
    async def get_at_risk(
        self, user_context: UserContext, risk_threshold_days: int = 2
    ) -> Result[list[Habit]]:
        """
        Get habits at risk of breaking their streaks.

        A habit is at risk if:
        - Has a streak > 0
        - Hasn't been completed within risk_threshold_days

        Args:
            user_context: User's current context
            risk_threshold_days: Days without completion to be considered at risk

        Returns:
            Result containing at-risk habits
        """
        today = date.today()

        # Get user's habits
        result = await self.backend.find_by(user_uid=user_context.user_uid)
        if result.is_error:
            return result

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits at risk
        at_risk = []
        for habit in habits:
            # Skip inactive (including paused)
            if not self._is_active(habit):
                continue

            # Must have a streak to be at risk
            if not habit.current_streak or habit.current_streak == 0:
                continue

            # Check days since last completion
            if habit.last_completed:
                # last_completed is typed as datetime | None, so .date() is safe here
                last_date = habit.last_completed.date()
                days_since = (today - last_date).days

                if days_since >= risk_threshold_days:
                    at_risk.append(habit)

        # Sort by streak (highest first - most to lose)
        def get_current_streak(habit: Habit) -> int:
            """Get current streak for sorting, defaulting to 0."""
            return habit.current_streak or 0

        at_risk.sort(key=get_current_streak, reverse=True)

        self.logger.info(f"Found {len(at_risk)} at-risk habits for user {user_context.user_uid}")
        return Result.ok(at_risk)

    @with_error_handling("get_user_due_today", error_type="database")
    async def get_user_due_today(self, user_uid: UserUID) -> Result[list[Habit]]:
        """
        Get habits due today for a specific user.

        Returns habits that:
        - Are active (not archived/paused)
        - Haven't been completed today
        - Are scheduled for today based on frequency

        Args:
            user_uid: Required user identifier

        Returns:
            Result with list of habits due today for this user
        """
        result = await self.backend.find_by(user_uid=user_uid, limit=500)
        return self._filter_due_today(result, f"user {user_uid}")

    @with_error_handling("get_all_due_today", error_type="database")
    async def get_all_due_today(self) -> Result[list[Habit]]:
        """
        Get all habits due today across all users (admin use).

        Returns habits that:
        - Are active (not archived/paused)
        - Haven't been completed today
        - Are scheduled for today based on frequency

        Returns:
            Result with list of all habits due today
        """
        result = await self.backend.find_by(limit=500)
        return self._filter_due_today(result, "all users")

    def _filter_due_today(self, result: Result[list[Habit]], context: str) -> Result[list[Habit]]:
        """
        Filter habits to those due today.

        Shared logic for get_user_due_today and get_all_due_today.
        """
        if result.is_error:
            return Result.fail(result)

        habits = self._to_domain_models(result.value, HabitDTO, Habit)
        today = date.today()

        # Filter to active habits not completed today
        due_today = []
        for habit in habits:
            # Skip inactive (including paused)
            if not self._is_active(habit):
                continue

            # Check if already completed today
            if habit.last_completed:
                # last_completed is typed as datetime | None, so .date() is safe here
                last_date = habit.last_completed.date()
                if last_date == today:
                    continue
            else:
                last_date = None

            # Check frequency against window
            window_days = get_frequency_window_days(habit.recurrence_pattern)
            if not last_date or (today - last_date).days >= window_days:
                due_today.append(habit)

        self.logger.debug(f"Found {len(due_today)} habits due today for {context}")
        return Result.ok(due_today)

    # get_by_category() and list_categories() - inherited from BaseService

    @with_error_handling("get_active", error_type="database", uid_param="user_uid")
    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Habit]]:
        """
        Get active (non-archived, non-completed) habits for a user.

        Override of TimeQueryMixin.get_active — habits include paused entries
        (paused habits are still "alive", just temporarily suspended).

        Args:
            user_uid: User identifier
            limit: Maximum results to return

        Returns:
            Result with list of active habits
        """
        # Get all user habits
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits (exclude archived, completed, cancelled but include paused)
        active_habits = [h for h in habits if self._is_active(h, include_paused=True)][:limit]

        self.logger.debug(f"Found {len(active_habits)} active habits for user {user_uid}")
        return Result.ok(active_habits)

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================
