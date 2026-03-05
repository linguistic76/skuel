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
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.models.type_hints import Metadata
from core.ports.domain_protocols import HabitsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score
from core.utils.timestamp_helpers import get_frequency_window_days


class HabitSearchService(BaseService[HabitsOperations, Habit]):
    """
    Habit search and discovery operations.

    Implements DomainSearchOperations[Habit] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by EntityStatus
    - get_by_domain() - Filter by Domain enum
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Habits due within N days (based on frequency)
    - get_overdue() - Overdue habits

    Habit-Specific Methods:
    - get_by_frequency() - Filter by HabitFrequency (daily, weekly, monthly)
    - get_needing_attention() - Habits with low/broken streaks
    - get_supporting_goal() - Habits that support a specific goal
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
    # - search(), get_by_status(), get_by_domain(), get_by_category(),
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
    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Habit]]:
        """
        Get habits prioritized for the user's current context.

        Uses Cypher WHERE clause to filter at database level for efficiency.
        Then applies UserContext-aware scoring in Python.

        Uses UserContext to determine relevance:
        - Streak status (at-risk habits get priority)
        - Goal alignment
        - Time since last completion
        - Frequency requirements

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing habits sorted by priority/relevance
        """
        # Use Cypher to filter active habits at database level
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(h:Habit)
        WHERE NOT h.status IN $terminal_statuses
        RETURN h
        ORDER BY
            CASE WHEN h.current_streak > 0 AND h.last_completed < date() THEN 0 ELSE 1 END,
            h.current_streak DESC,
            h.created_at DESC
        LIMIT $fetch_limit
        """

        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_context.user_uid,
                "terminal_statuses": list(self._TERMINAL_STATUSES),
                "fetch_limit": limit * 2,  # Fetch extra for scoring refinement
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        habits = []
        for record in result.value:
            dto = HabitDTO.from_dict(record["h"])
            habits.append(Habit.from_dto(dto))

        # Apply fine-grained scoring that uses UserContext
        scored_habits = []
        for habit in habits:
            score = self._calculate_priority_score(habit, user_context)
            scored_habits.append((habit, score))

        # Sort by score descending
        scored_habits.sort(key=get_result_score, reverse=True)

        # Return top N
        prioritized = [habit for habit, _ in scored_habits[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} habits for user {user_context.user_uid}")
        return Result.ok(prioritized)

    def _calculate_priority_score(self, habit: Habit, user_context: UserContext) -> float:
        """
        Calculate priority score for a habit based on user context.

        Factors:
        - Streak at risk (highest priority if about to break)
        - Time since last completion
        - Goal support (supporting active goals)
        - Frequency alignment
        """
        score = 0.0
        today = date.today()

        # Streak at risk (0-40 points)
        if habit.current_streak and habit.current_streak > 0:
            if habit.last_completed:
                # last_completed is typed as datetime | None, so .date() is safe here
                last_date = habit.last_completed.date()
                days_since = (today - last_date).days

                # Daily habits at risk after 1 day
                if days_since >= 1:
                    score += 40  # At risk - highest priority
                elif habit.current_streak >= 7:
                    score += 30  # Protect long streaks
                elif habit.current_streak >= 3:
                    score += 20
                else:
                    score += 10
            else:
                score += 35  # Never completed but has streak data - priority

        # Time since last completion (0-25 points)
        if habit.last_completed:
            # last_completed is typed as datetime | None, so .date() is safe here
            last_date = habit.last_completed.date()
            days_since = (today - last_date).days
            if days_since >= 3:
                score += 25  # Overdue
            elif days_since >= 2:
                score += 20
            elif days_since >= 1:
                score += 15
            else:
                score += 5  # Done today
        else:
            score += 20  # Never done - needs attention

        # Goal support (0-20 points)
        # Habits supporting active goals get priority
        if user_context.active_goal_uids and habit.uid:
            # Check if habit supports any active goals via context
            habit_streaks = user_context.habit_streaks or {}
            if habit.uid in habit_streaks:
                score += 15  # Tracked habit supporting goals

        # Frequency alignment (0-15 points)
        # recurrence_pattern is stored as plain string
        if habit.recurrence_pattern:
            freq_value = habit.recurrence_pattern
            if freq_value == "daily":
                score += 15  # Daily habits need daily attention
            elif freq_value == "weekly":
                score += 10
            else:
                score += 5

        return score

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_due_soon", error_type="database")
    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Habit]]:
        """
        Get habits due within specified number of days based on frequency.

        For habits, "due soon" means habits that need completion based on their
        frequency pattern within the time window.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing habits due soon
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Get active habits - use user_uid filter if provided
        filters = {"user_uid": user_uid} if user_uid else {}
        result = await self.backend.find_by(limit=limit * 5, **filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits due within window
        due_soon = []
        for habit in habits:
            # Skip inactive (including paused)
            if not self._is_active(habit):
                continue

            # Check if due based on frequency
            is_due = self._is_habit_due_in_window(habit, today, end_date)
            if is_due:
                due_soon.append(habit)

            if len(due_soon) >= limit:
                break

        self.logger.debug(f"Found {len(due_soon)} habits due within {days_ahead} days")
        return Result.ok(due_soon)

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
        user_uid: str | None = None,
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
            return Result.fail(result.expect_error())

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
        from core.ports import get_enum_value

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
            return Result.fail(result.expect_error())

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

    @with_error_handling("get_supporting_goal", error_type="database", uid_param="goal_uid")
    async def get_supporting_goal(self, goal_uid: str) -> Result[list[Habit]]:
        """
        Get habits that support a specific goal.

        Query: (Habit)-[:SUPPORTS_GOAL]->(Goal)

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing habits supporting the goal
        """
        return await self.get_by_relationship(
            related_uid=goal_uid,
            relationship_type=RelationshipName.SUPPORTS_GOAL,
            direction="incoming",
        )

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
    async def get_user_due_today(self, user_uid: str) -> Result[list[Habit]]:
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
        return await self._filter_due_today(result, f"user {user_uid}")

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
        return await self._filter_due_today(result, "all users")

    async def _filter_due_today(
        self, result: Result[list[Metadata]], context: str
    ) -> Result[list[Habit]]:
        """
        Filter habits to those due today.

        Shared logic for get_user_due_today and get_all_due_today.
        """
        if result.is_error:
            return Result.fail(result.expect_error())

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

    @with_error_handling(
        "get_reinforcing_knowledge", error_type="database", uid_param="knowledge_uid"
    )
    async def get_reinforcing_knowledge(self, knowledge_uid: str) -> Result[list[Habit]]:
        """
        Get habits that reinforce specific knowledge.

        Query: (Habit)-[:REINFORCES_KNOWLEDGE]->(KnowledgeUnit)

        Args:
            knowledge_uid: Knowledge unit UID

        Returns:
            Result containing habits reinforcing the knowledge
        """
        return await self.get_by_relationship(
            related_uid=knowledge_uid,
            relationship_type=RelationshipName.REINFORCES_KNOWLEDGE,
            direction="incoming",
        )

    @with_error_handling("get_active_habits", error_type="database", uid_param="user_uid")
    async def get_active_habits(self, user_uid: str) -> Result[list[Habit]]:
        """
        Get active (non-archived, non-completed) habits for a user.

        Args:
            user_uid: User identifier

        Returns:
            Result with list of active habits
        """
        # Get all user habits
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return result

        habits = self._to_domain_models(result.value, HabitDTO, Habit)

        # Filter to active habits (exclude archived, completed, cancelled but include paused)
        active_habits = [h for h in habits if self._is_active(h, include_paused=True)]

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

    @with_error_handling("intelligent_search", error_type="database")
    async def intelligent_search(
        self, query: str, user_uid: str | None = None, limit: int = 50
    ) -> Result[tuple[list[Habit], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "daily health habits at risk" to extract:
        - Frequency filters (daily → DAILY)
        - Status filters (active → ACTIVE)
        - Domain filters (health → HEALTH)
        - Streak state filters (at risk, broken, strong)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (habits, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("weekly habits at risk")
            >>> habits, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)
        query_lower = query.lower()

        # Build filters from parsed query
        filters: dict[str, object] = {}

        # Habit-specific: Frequency extraction
        frequency_keywords = {
            "daily": HabitFrequency.DAILY,
            "weekly": HabitFrequency.WEEKLY,
            "monthly": HabitFrequency.MONTHLY,
            "quarterly": HabitFrequency.QUARTERLY,
            "yearly": HabitFrequency.YEARLY,
            "annual": HabitFrequency.YEARLY,
        }
        for keyword, frequency in frequency_keywords.items():
            if keyword in query_lower:
                filters["recurrence_pattern"] = frequency.value
                break

        # Apply status filter from parsed query (use first status if multiple)
        if parsed.statuses:
            filters["status"] = parsed.statuses[0].value

        # Apply domain filter from parsed query (use first domain if multiple)
        if parsed.domains:
            filters["domain"] = parsed.domains[0].value

        # Execute base search
        if filters:
            # Use filtered search via backend
            result = await self.backend.find_by(limit=limit, **filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            habits = self._to_domain_models(result.value, HabitDTO, Habit)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result.expect_error())
            habits = result.value

        # Filter by user ownership if provided
        if user_uid and habits:
            habits = [h for h in habits if getattr(h, "user_uid", None) == user_uid]

        # Habit-specific: Streak state filtering (post-filter in Python)
        if "broken" in query_lower or "lost" in query_lower:
            # Broken streak: best_streak > 0 but current_streak = 0
            habits = [
                h for h in habits if (h.best_streak or 0) > 0 and (h.current_streak or 0) == 0
            ]
        elif "at risk" in query_lower or "at-risk" in query_lower:
            # At risk: has streak but hasn't been completed recently
            today = date.today()
            at_risk_habits = []
            for habit in habits:
                if habit.current_streak and habit.current_streak > 0:
                    if habit.last_completed:
                        days_since = (today - habit.last_completed.date()).days
                        if days_since >= 1:  # Risk threshold
                            at_risk_habits.append(habit)
            habits = at_risk_habits
        elif "strong" in query_lower or "healthy" in query_lower:
            # Strong streak: current_streak >= 7
            habits = [h for h in habits if (h.current_streak or 0) >= 7]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(habits),
        )

        return Result.ok((habits, parsed))
