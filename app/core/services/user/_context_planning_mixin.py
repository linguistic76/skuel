"""
Context & Planning Mixin — UserService
========================================

The context/planning bridge: UserContext building, the rich-context cache
orchestration (peek / build-and-cache), the profile-hub statistical view,
and the daily-work-plan intelligence entry point.

Part of user_service.py decomposition (July 2026).
See: /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.context_types import DailyWorkPlan
    from core.models.type_hints import UserUID
    from core.models.user import User
    from core.services.user.intelligence import UserContextIntelligenceFactory
    from core.services.user.unified_user_context import RichUserContext, UserContext
    from core.services.user.user_activity_service import UserActivityService
    from core.services.user.user_context_builder import UserContextBuilder
    from core.services.user.user_stats_aggregator import UserStatsAggregator
    from core.services.user_stats_types import ProfileHubData

logger = get_logger(__name__)


class _ContextPlanningMixin:
    """
    Context building, caching, and planning-intelligence methods for UserService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by UserService.__init__
    stats: UserStatsAggregator | None
    context_builder: UserContextBuilder | None
    activity: UserActivityService
    intelligence_factory: UserContextIntelligenceFactory | None
    get_user: Any  # delegation method on UserService

    async def get_user_context(self, user_uid: UserUID) -> Result[UserContext]:
        """
        Get UserContext for a user (public API for Askesis and other services).

        This method exposes the internal _build_user_context() functionality
        for services that need rich user context (like Askesis AI assistant).

        Args:
            user_uid: User's unique identifier

        Returns:
            Result containing UserContext with all domain activity data

        Note:
            For statistical views, use get_profile_hub_data() instead.
            For rich entity details, use get_rich_unified_context() instead.
        """
        # Get user first
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Build and return UserContext
        return await self._build_user_context(user_uid, user)

    async def get_profile_hub_data(self, user_uid: UserUID) -> Result[ProfileHubData]:
        """
        Get aggregated data for user profile hub.

        Pattern 3C + UserContext Integration:
        - Builds UserContext from domain queries (single source of truth)
        - Uses ProfileHubData.from_context() to compute statistical view
        - Returns strongly-typed ProfileHubData with full context

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[ProfileHubData]: Strongly-typed profile hub data with frozen dataclasses

        Raises:
            ValueError: If stats aggregator not initialized (driver required)
        """
        if not self.stats:
            return Result.fail(
                Errors.system(
                    message="ProfileHubData requires Neo4j driver - initialize UserService with driver"
                )
            )

        return await self.stats.get_profile_hub_data(user_uid)

    async def _build_user_context(self, user_uid: UserUID, user: User) -> Result[UserContext]:
        """
        Build UserContext from domain queries.

        INTERNAL METHOD: Used by UserStatsAggregator.

        Args:
            user_uid: User's unique identifier
            user: User entity

        Returns:
            Result[UserContext] with complete domain awareness (~240 fields)
        """
        if not self.context_builder:
            return Result.fail(Errors.system(message="Context building requires Neo4j driver"))

        return await self.context_builder.build_user_context(user_uid, user)

    def peek_cached_context(self, user_uid: UserUID) -> RichUserContext | None:
        """Cache-hit-only context access — NEVER builds (no MEGA-QUERY, ever).

        For latency-sensitive surfaces (the keystroke-driven /search path)
        that want to enrich opportunistically when a rich context is already
        warm, and silently do without one when it isn't. Use
        ``get_rich_unified_context`` when you need a context unconditionally.
        """
        if self.activity is None:
            return None
        return self.activity.get_valid_context(user_uid)

    async def get_rich_unified_context(
        self, user_uid: UserUID, min_confidence: float = 0.7
    ) -> Result[RichUserContext]:
        """
        Get COMPLETE UserContext with BOTH standard AND rich fields.

        **PERFORMANCE OPTIMIZATION (February 6, 2026):**
        Now uses UserContextCache (5-minute TTL) with event-driven invalidation.
        - Cache hit (~80% of requests): Returns instantly without database query
        - Cache miss: Builds context with MEGA-QUERY and caches result
        - Auto-invalidation: Domain events (TaskCompleted, GoalAchieved, etc.) clear cache

        **ARCHITECTURE REFACTOR (November 24, 2025):**
        This now uses the TRUE MEGA-QUERY that fetches EVERYTHING in a single database query.

        **Before:** 2-3 queries (standard context + MEGA-QUERY)
        **After:** 1 query (TRUE MEGA-QUERY) with caching

        This single comprehensive query fetches:
        1. **Standard context fields** (UIDs, relationships, metadata)
           - active_task_uids, active_goal_uids, active_habit_uids
           - habit_streaks, knowledge_mastery, goal_progress
           - tasks_by_goal, overdue_task_uids, etc.

        2. **Rich context fields** (full entities + graph neighborhoods)
           - entities_rich: {"tasks": [{entity: {...}, graph_context: {...}}, ...], "goals": [...], ...}
           - knowledge_units_rich: {uid: {ku: {...}, graph_context: {prerequisites, dependents}}, ...}

        Args:
            user_uid: User's unique identifier
            min_confidence: Minimum relationship confidence (default 0.7)

        Returns:
            Result[UserContext] with ALL ~240 fields populated

        Performance:
            - Cache hit: ~1-5ms (no database query)
            - Cache miss: ~800ms-2s (MEGA-QUERY runs)
            - Expected cache hit rate: ~80% during active user sessions

        Usage:
            # Dashboard view - needs full entity data
            context_result = await user_service.get_rich_unified_context(user_uid)
            context = context_result.value

            # Access lightweight UIDs (standard context)
            task_uids = context.active_task_uids # ✅ Populated from MEGA-QUERY

            # Access rich entities with graph neighborhoods
            for task_data in context.entities_rich.get("tasks", []):  # ✅ Populated from MEGA-QUERY
                task = task_data["entity"]
                graph_context = task_data["graph_context"]

                # Use subtasks, dependencies, applied knowledge, etc.
                subtasks = graph_context["subtasks"]
                dependencies = graph_context["dependencies"]
                knowledge = graph_context["applied_knowledge"]
        """
        if not self.context_builder:
            return Result.fail(Errors.system(message="Rich context building requires Neo4j driver"))

        # ========================================================================
        # STEP 1: Check cache first (5-minute TTL with event-driven invalidation)
        # ========================================================================
        if self.activity:
            cached_context = self.activity.get_valid_context(user_uid)
            if cached_context:
                logger.debug(
                    "Rich context cache HIT", extra={"user_uid": user_uid, "cache_age_seconds": 0}
                )
                return Result.ok(cached_context)

            logger.debug(
                "Rich context cache MISS - building from database", extra={"user_uid": user_uid}
            )

        # ========================================================================
        # STEP 2: Cache miss - build from database (MEGA_QUERY)
        # ========================================================================
        # Use builder-owned user resolution to avoid duplicating lookup/error handling
        # and keep MEGA_QUERY orchestration in a single place.
        context_result = await self.context_builder.build_rich(
            user_uid, min_confidence=min_confidence
        )

        if context_result.is_error:
            return context_result

        # ========================================================================
        # STEP 3: Cache the freshly-built context
        # ========================================================================
        context = context_result.value
        if self.activity:
            self.activity.cache_context(user_uid, context)
            logger.debug(
                "Rich context cached",
                extra={"user_uid": user_uid, "cache_ttl_seconds": 300},  # 5 minutes
            )

        return Result.ok(context)

    async def get_daily_work_plan(
        self,
        user_uid: UserUID,
        prioritize_life_path: bool = True,
        respect_capacity: bool = True,
    ) -> Result[DailyWorkPlan]:
        """
        Get optimal daily work plan for a user.

        🎯 THE FLAGSHIP METHOD - What should I focus on TODAY?

        This synthesizes across ALL domains to create an optimal daily plan:
        - Learning: Knowledge ready to learn + aligned with goals
        - Tasks: Today's tasks + high-impact tasks + overdue tasks
        - Habits: Daily habits + at-risk habits (maintain streaks)
        - Goals: Goals nearing deadline + primary goal focus
        - Events: Today's events

        Considers:
        - User capacity (available_minutes_daily)
        - Energy level (current_energy_level)
        - Workload (current_workload_score)
        - Life path alignment (if prioritize_life_path=True)

        Args:
            user_uid: User's unique identifier
            prioritize_life_path: Weight life path alignment highly
            respect_capacity: Don't exceed available time

        Returns:
            Result[DailyWorkPlan]: Complete daily plan with rationale and priorities
        """
        # Check if intelligence factory is available
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available",
                    operation="get_daily_work_plan",
                )
            )

        # Build rich user context — intelligence methods consume rich-only fields.
        context_result = await self.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)

        context = context_result.value

        # Create intelligence service from factory and get daily plan
        intelligence = self.intelligence_factory.create(context)
        return await intelligence.get_ready_to_work_on_today(
            prioritize_life_path=prioritize_life_path,
            respect_capacity=respect_capacity,
        )
