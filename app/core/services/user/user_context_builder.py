"""
User Context Builder - Unified Context Building Orchestration
==============================================================

**REFACTORED (December 2025):** Decomposed from 2,102 lines to ~200 lines.

This module orchestrates context building by composing:
- user_context_queries.py - Cypher query definitions and execution
- user_context_extractor.py - Parse query results into structured data
- user_context_populator.py - Populate UserContext fields

Previous Architecture (single file, 2,100+ lines):
- All queries inline
- All extraction logic inline
- All population logic inline
- ~440 lines of deprecated methods

Current Architecture (4 files, ~1,600 lines total):
- user_context_builder.py (THIS FILE) - Orchestration only (~200 lines)
- user_context_queries.py - Query definitions (~700 lines)
- user_context_extractor.py - Data extraction (~400 lines)
- user_context_populator.py - Context population (~300 lines)

Responsibilities:
- Orchestrating context building across modules
- User resolution via UserService
- Error handling and Result[T] wrapping
- Public API surface (build, build_rich, build_user_context, build_rich_user_context)
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import FeedbackTimePeriod
from core.models.user import User
from core.services.user import UserContext
from core.services.user.user_context_extractor import UserContextExtractor
from core.services.user.user_context_populator import UserContextPopulator
from core.services.user.user_context_queries import UserContextQueryExecutor
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user_service import UserService

logger = get_logger(__name__)


class UserContextBuilder:
    """
    Build rich UserContext from Neo4j graph queries.

    This service orchestrates context building across all domains:
    - Tasks: Active, completed, overdue, today's tasks
    - Habits: Active habits, streaks, completion rates
    - Goals: Active, completed goals, progress tracking
    - Learning: Mastered knowledge, enrolled paths, mastery scores
    - Events: Upcoming events, today's events

    The resulting UserContext contains ~240 fields with UIDs,
    relationships, and computed metrics.

    Architecture:
    - Composes QueryExecutor, Extractor, and Populator
    - Returns UserContext (read-only aggregate - mutations via domain services)
    - Used by ProfileHubData generation (Pattern 3C)
    """

    def __init__(
        self,
        executor: Any,
        user_service: "UserService | None" = None,
    ) -> None:
        """
        Initialize context builder with composed modules.

        Args:
            executor: Query executor for graph queries
            user_service: UserService for user resolution (enables simplified build() API)

        Raises:
            ValueError: If executor is None

        Note:
            user_service can be wired post-construction to resolve circular dependencies.
            When user_service is available, use build(user_uid) for the simplified API.
            When user_service is None, use build_user_context(user_uid, user) instead.
        """
        if not executor:
            raise ValueError("QueryExecutor is required for context building")

        self.executor = executor
        self.user_service = user_service

        # Compose modules for separation of concerns
        self._query_executor = UserContextQueryExecutor(executor)
        self._extractor = UserContextExtractor()
        self._populator = UserContextPopulator()

    async def _resolve_user(self, user_uid: str, operation: str) -> Result[User]:
        """
        Resolve user from UserService.

        Internal helper that encapsulates user lookup and error handling,
        eliminating duplication between build() and build_rich().
        """
        if not self.user_service:
            return Result.fail(
                Errors.system(
                    message="UserContextBuilder.user_service not configured. "
                    "Wire user_service post-construction or call the build_* methods "
                    "that accept a User instance.",
                    operation=operation,
                )
            )

        user_result = await self.user_service.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result.expect_error())

        user = user_result.value
        if not user:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        return Result.ok(user)

    def _finalize_context(self, context: UserContext, *, is_rich: bool = False) -> None:
        """
        Apply final derived calculations to context.

        Single choke point for all derived field computation,
        preventing "derived field drift" between standard/rich paths.

        WORKLOAD AUTHORITY: UserContext.calculate_current_workload() is the
        single authority for workload calculation. This method delegates to it
        rather than duplicating the logic. If workload calculation needs to change,
        modify UserContext.calculate_current_workload(), not here.
        """
        # Delegate workload calculation to UserContext (single authority)
        context.current_workload_score = context.calculate_current_workload()
        context.is_rich_context = is_rich

    # ========================================================================
    # SIMPLIFIED API - Builder Owns User Resolution (Preferred)
    # ========================================================================

    async def build(self, user_uid: str) -> Result[UserContext]:
        """
        Build UserContext for user - handles user resolution internally.

        **ARCHITECTURE (November 26, 2025): Builder Owns User Resolution**

        This is the PRIMARY method for building context. It encapsulates:
        1. User resolution (fetching User from UserService)
        2. Context building (graph queries)
        3. Error handling (returns Result[UserContext])

        Benefits:
        - Single responsibility: Builder builds, consumers use
        - No repetitive user lookup in every service method
        - Clean API: Just pass user_uid, get context

        Args:
            user_uid: User identifier

        Returns:
            Result[UserContext] with complete domain awareness (~240 fields)

        Raises:
            Result.fail if user_service not configured or user not found

        Example:
            context_result = await context_builder.build(user_uid)
            if context_result.is_error:
                return context_result
            context = context_result.value
        """
        user_result = await self._resolve_user(user_uid, "build")
        if user_result.is_error:
            return Result.fail(user_result.expect_error())
        return await self.build_user_context(user_uid, user_result.value)

    async def build_rich(
        self,
        user_uid: str,
        min_confidence: float = 0.7,
        time_period: str | None = None,
    ) -> Result[UserContext]:
        """
        Build COMPLETE UserContext with rich fields - handles user resolution internally.

        **ARCHITECTURE (November 26, 2025): Builder Owns User Resolution**

        This is the simplified API for build_rich_user_context(). It encapsulates:
        1. User resolution (fetching User from UserService)
        2. Rich context building (MEGA-QUERY with graph neighborhoods)
        3. Error handling (returns Result[UserContext])

        Use this when you need full entities + graph neighborhoods, not just UIDs.

        Args:
            user_uid: User identifier
            min_confidence: Minimum relationship confidence (default 0.7)
            time_period: Optional activity window ("7d", "14d", "30d", "90d").
                When provided, MEGA-QUERY includes six CALL{} blocks that populate
                context.activity_rich with entities touched in the window.
                When None (default), activity_rich stays empty — no performance impact.

        Returns:
            Result[UserContext] with ALL ~240 fields including rich data.
            context.activity_rich is populated when time_period is provided.

        Example:
            context_result = await context_builder.build_rich(user_uid)
            if context_result.is_error:
                return context_result
            context = context_result.value
            # Access rich data: context.active_tasks_rich, context.active_goals_rich, etc.
            # With time_period: context.activity_rich["tasks"], context.activity_rich["goals"], etc.
        """
        user_result = await self._resolve_user(user_uid, "build_rich")
        if user_result.is_error:
            return Result.fail(user_result.expect_error())
        return await self.build_rich_user_context(
            user_uid, user_result.value, min_confidence, time_period=time_period
        )

    # ========================================================================
    # FULL API - Caller Provides User (Backward Compatibility)
    # ========================================================================

    @with_error_handling("build_user_context", error_type="system", uid_param="user_uid")
    async def build_user_context(self, user_uid: str, user: User) -> Result[UserContext]:
        """
        Build UserContext from domain queries (standard path).

        **PERFORMANCE OPTIMIZATION (November 17, 2025):**
        Uses consolidated single-query approach instead of 5 separate sequential queries.
        This reduces database round trips from 5-9 to 1-2 (3-5x performance improvement).

        This is THE source of truth - contains all UIDs, relationships, and domain awareness.
        ProfileHubData stats are computed FROM this context.

        Args:
            user_uid: User's unique identifier
            user: User entity

        Returns:
            Result[UserContext] with complete domain awareness (~240 fields)

        Process:
            1. Initialize context with user identity
            2. Fetch ALL domain data in single consolidated query (optimized)
            3. Calculate derived fields (workload score, etc.)
        """
        # User.title stores the username (inherited from BaseEntity, see user.py line 101-102)
        # This mapping is intentional: User uses title for username, UserContext exposes it as username
        # Initialize context with user identity
        context = UserContext(
            user_uid=user_uid,
            username=user.title,
            email=user.email,
            display_name=user.display_name or user.title,
        )

        # Execute consolidated query
        query_result = await self._query_executor.execute_consolidated_query(user_uid)
        if query_result.is_error:
            return Result.fail(query_result.expect_error())

        # Populate context from query results
        self._populator.populate_from_consolidated_data(context, query_result.value)

        # Calculate derived fields
        self._finalize_context(context)

        return Result.ok(context)

    @with_error_handling("build_rich_user_context", error_type="system", uid_param="user_uid")
    async def build_rich_user_context(
        self,
        user_uid: str,
        user: User,
        min_confidence: float = 0.7,
        time_period: str | None = None,
    ) -> Result[UserContext]:
        """
        Build COMPLETE UserContext with BOTH standard AND rich fields in ONE query.

        **ARCHITECTURE:** Uses TRUE MEGA-QUERY pattern - single comprehensive query
        that fetches BOTH standard context (UIDs) AND rich context (full entities
        with graph neighborhoods) in ONE database round-trip.

        This single query fetches:
        1. **Standard context fields** (UIDs, relationships, metadata)
           - active_task_uids, active_goal_uids, active_habit_uids
           - habit_streaks, knowledge_mastery, goal_progress
           - tasks_by_goal, overdue_task_uids, etc.

        2. **Rich context fields** (full entities + graph neighborhoods)
           - active_tasks_rich: [{task: {...}, graph_context: {...}}, ...]
           - active_goals_rich, active_habits_rich, knowledge_units_rich
           - cross_domain_insights

        Args:
            user_uid: User's unique identifier
            user: User entity
            min_confidence: Minimum relationship confidence (default 0.7)

        Returns:
            Result[UserContext] with ALL ~240 fields populated

        Performance:
            - ProfileHubData path (old): 1-2 queries
            - Dashboard path (old): 2-3 queries (standard + MEGA-QUERY)
            - Unified path (new): 1 query (TRUE MEGA-QUERY)
        """
        # Validate min_confidence bounds
        if not (0.0 <= min_confidence <= 1.0):
            return Result.fail(
                Errors.validation(
                    message=f"min_confidence must be between 0.0 and 1.0, got {min_confidence}",
                    field="min_confidence",
                )
            )

        # User.title stores the username (inherited from BaseEntity, see user.py line 101-102)
        # This mapping is intentional: User uses title for username, UserContext exposes it as username
        # Initialize context with user identity
        context = UserContext(
            user_uid=user_uid,
            username=user.title,
            email=user.email,
            display_name=user.display_name or user.title,
        )

        # Compute activity window dates when time_period is provided
        window_start: datetime | None = None
        window_end: datetime | None = None
        if time_period:
            days = FeedbackTimePeriod.DAYS.get(time_period, FeedbackTimePeriod.DEFAULT_DAYS)
            window_end = datetime.now()
            window_start = window_end - timedelta(days=days)

        # Execute MEGA-QUERY — fetches UIDs AND rich data in one shot.
        # When window_start is provided, the query also includes six CALL{}
        # subqueries that populate activity_rich with entities touched in
        # the window. When None, activity_rich stays empty (no added cost).
        mega_result = await self._query_executor.execute_mega_query(
            user_uid, min_confidence, window_start=window_start, window_end=window_end
        )
        if mega_result.is_error:
            return Result.fail(mega_result.expect_error())

        mega_data = mega_result.value

        # MEGA_QUERY result shape (see user_context_queries.py MEGA_QUERY):
        # {
        #     "uids": {active_task_uids, completed_task_uids, goal_progress, knowledge_mastery, ...},
        #     "rich": {tasks: [{task, graph_context}], goals, habits, knowledge, principles, choices, ...},
        #     "user_properties": {preferences, role, settings},
        #     "life_path": {uid, alignment_score, dimensions},
        #     "progress_counts": {tasks_completed, habits_maintained, goals_achieved, ...},
        #     "activity_report": {uid, period, period_end, content, user_annotation} or null,
        #     "active_insights_raw": [{uid, type, title, impact, confidence}, ...] (up to 10),
        #     "activity": {tasks, goals, habits, events, choices, principles} (when time_period given)
        # }
        uids_data = mega_data.get("uids", {})
        rich_data = mega_data.get("rich", {})

        # Populate standard context fields (UIDs, relationships, metadata)
        self._populator.populate_standard_fields(context, uids_data)

        # Populate rich context fields (full entities + graph neighborhoods)
        self._populator.populate_rich_fields(context, rich_data)

        # Populate MOC fields from uids section (Priority 3)
        self._populator.populate_moc_fields(context, uids_data)

        # Populate user properties from user_properties section (Priority 1)
        self._populator.populate_user_properties(context, mega_data.get("user_properties", {}))

        # Populate life path fields (Priority 2)
        self._populator.populate_life_path(context, mega_data.get("life_path", {}))

        # Populate activity report + insights from MEGA-QUERY (no separate roundtrip)
        self._populator.populate_activity_report(context, mega_data.get("activity_report"))
        self._populator.populate_cross_domain_insights(context, mega_data.get("active_insights_raw"))

        # Populate progress metrics (Priority 6)
        self._populator.populate_progress_metrics(context, mega_data.get("progress_counts", {}))

        # Extract and populate graph-sourced relationship data
        # This replaces 4 database round-trips with pure Python extraction
        graph_data = self._extractor.extract_graph_sourced_data(
            mega_data, context.mastered_knowledge_uids
        )
        self._populator.populate_graph_sourced_fields(context, graph_data)

        # Populate derived fields (Priority 4: tasks_by_goal, habits_by_goal, etc.)
        self._populator.populate_derived_fields(
            context, rich_data.get("tasks", []), rich_data.get("habits", [])
        )

        # Populate principle-choice integration (Priority 5)
        self._populator.populate_principle_choice_integration(
            context, rich_data.get("principles", []), rich_data.get("choices", [])
        )

        # Populate activity window fields when time_period was requested
        if time_period and window_start and window_end:
            activity_data = mega_data.get("activity", {})
            self._populator.populate_activity_fields(
                context, activity_data, window_start, window_end, time_period
            )

        # Calculate derived fields and mark as rich context
        self._finalize_context(context, is_rich=True)

        return Result.ok(context)
