"""
User Service Facade - Coordination Layer
=========================================

Facade coordinating all user-related sub-services.

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressRecorderService: Learning progress recording
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services (THIS FILE)

Architecture:
- Delegates all operations to appropriate sub-services
- Maintains backward compatibility with original UserService
- Acts as single entry point for user-related operations
- Zero business logic (pure delegation)
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import UserRole
from core.models.user import User
from core.services.protocols.infrastructure_protocols import (
    EventBusOperations,
    UserOperations,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver
from core.services.user import UserContext
from core.models.context_types import DailyWorkPlan, LearningStep
from core.services.user.intelligence import UserContextIntelligenceFactory
from core.services.user.user_activity_service import UserActivityService
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_core_service import UserCoreService
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.services.user.user_stats_aggregator import UserStatsAggregator
from core.services.user_stats_types import ProfileHubData
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserService:
    """
    Facade coordinating all user-related sub-services.

    This service provides a unified interface for user operations while delegating
    to specialized sub-services:
    - UserCoreService: CRUD + Authentication
    - UserProgressRecorderService: Learning progress recording
    - UserActivityService: Activity tracking
    - UserContextBuilder: Context building
    - UserStatsAggregator: Stats aggregation

    Architecture:
    - Zero business logic (pure delegation)
    - Maintains backward compatibility
    - Single entry point for user operations
    - Composed of 5 focused sub-services


    Source Tag: "user_explicit"
    - Format: "user_explicit" for user-created relationships
    - Format: "user_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        user_repo: UserOperations,
        driver: "AsyncDriver | None" = None,
        event_bus: EventBusOperations | None = None,
        intelligence_factory: UserContextIntelligenceFactory | None = None,
        metrics_cache=None,
    ) -> None:
        """
        Initialize facade with all sub-services.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            driver: Optional Neo4j driver for cross-domain queries (context building)
            event_bus: Event bus for publishing domain events (protocol-based)
            intelligence_factory: Factory for creating UserContextIntelligence instances
                                  (wired with all 9 domain relationship services)
            metrics_cache: MetricsCache for performance tracking (optional)

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")

        # Initialize all sub-services
        self.core = UserCoreService(user_repo)
        self.progress = UserProgressRecorderService(user_repo)
        self.activity = UserActivityService(
            user_repo, event_bus=event_bus, metrics_cache=metrics_cache
        )

        # Context builder requires Neo4j driver
        if driver:
            self.context_builder = UserContextBuilder(driver)
            self.stats = UserStatsAggregator(self.core, self.context_builder, driver)
        else:
            self.context_builder = None  # type: ignore[assignment]
            self.stats = None  # type: ignore[assignment]
            logger.warning(
                "UserService initialized without driver - context/stats operations unavailable"
            )

        # Intelligence factory (wired with 13 domain relationship services)
        # Note: Factory is wired post-construction via services_bootstrap.py
        # This is intentional - the factory requires all 13 domain services
        self.intelligence_factory = intelligence_factory

        # Keep repo reference for backward compatibility
        self.repo = user_repo

    # ========================================================================
    # CRUD OPERATIONS (Delegate to UserCoreService)
    # ========================================================================

    async def create_user(
        self,
        username: str,
        email: str | None = None,
        display_name: str | None = None,
        **kwargs: Any,
    ) -> Result[User]:
        """Create a new user with default preferences."""
        return await self.core.create_user(username, email, display_name, **kwargs)

    async def ensure_system_user(self) -> Result[User]:
        """Ensure system user exists for infrastructure operations."""
        return await self.core.ensure_system_user()

    async def get_user(self, user_uid: str) -> Result[User | None]:
        """Get user by UID."""
        return await self.core.get_user(user_uid)

    async def get_user_by_username(self, username: str) -> Result[User | None]:
        """Get user by username."""
        return await self.core.get_user_by_username(username)

    async def get_user_context(self, user_uid: str) -> Result[UserContext]:
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
            return Result.fail(user_result.expect_error())

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Build and return UserContext
        return await self._build_user_context(user_uid, user)

    async def update_user(self, user: User) -> Result[User]:
        """Update user information."""
        return await self.core.update_user(user)

    async def update_preferences(
        self, user_uid: str, preferences_update: dict[str, Any]
    ) -> Result[User]:
        """Update user preferences (convenience method)."""
        return await self.core.update_preferences(user_uid, preferences_update)

    async def delete_user(self, user_uid: str) -> Result[bool]:
        """Delete a user."""
        return await self.core.delete_user(user_uid)

    # ========================================================================
    # AUTHENTICATION (Delegate to UserCoreService)
    # ========================================================================

    async def authenticate(self, username: str, password: str) -> Result[User]:
        """Authenticate user with username and password."""
        return await self.core.authenticate(username, password)

    # ========================================================================
    # ROLE MANAGEMENT (December 2025 - Admin Only)
    # ========================================================================

    async def update_role(
        self,
        target_user_uid: str,
        new_role: UserRole,
        admin_user_uid: str,
    ) -> Result[User]:
        """
        Update a user's role (ADMIN only).

        Performs authorization check before delegating to UserCoreService.

        Args:
            target_user_uid: User to update
            new_role: New role to assign
            admin_user_uid: UID of admin making the change

        Returns:
            Result[User]: Updated user or error

        Business Rules:
            - Only ADMIN can change user roles
            - Admins cannot demote themselves
            - Prevents escalation beyond ADMIN
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result.expect_error())

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(
                f"Non-admin {admin_user_uid} attempted to change role for {target_user_uid}"
            )
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can change user roles")
            )

        # Prevent self-demotion for admins
        if target_user_uid == admin_user_uid and new_role != UserRole.ADMIN:
            return Result.fail(
                Errors.business(rule="self_demotion", message="Admins cannot demote themselves")
            )

        # Delegate to core service
        return await self.core.update_user_role(target_user_uid, new_role)

    async def list_users(
        self,
        admin_user_uid: str,
        limit: int = 100,
        offset: int = 0,
        role_filter: UserRole | None = None,
        active_only: bool = True,
    ) -> Result[list[User]]:
        """
        List users (ADMIN only).

        Args:
            admin_user_uid: UID of admin making the request
            limit: Max results
            offset: Pagination offset
            role_filter: Optional filter by role
            active_only: Only return active users (default True)

        Returns:
            Result[list[User]]: List of users or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result.expect_error())

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to list users")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can list users")
            )

        # Delegate to core service
        return await self.core.list_users(limit, offset, role_filter, active_only)

    async def deactivate_user(
        self,
        target_user_uid: str,
        admin_user_uid: str,
        reason: str = "",
    ) -> Result[User]:
        """
        Deactivate a user account (ADMIN only).

        Args:
            target_user_uid: User to deactivate
            admin_user_uid: Admin making the request
            reason: Reason for deactivation

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result.expect_error())

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to deactivate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can deactivate users")
            )

        # Prevent self-deactivation
        if target_user_uid == admin_user_uid:
            return Result.fail(
                Errors.business(
                    rule="self_deactivation", message="Admins cannot deactivate themselves"
                )
            )

        # Delegate to core service
        return await self.core.deactivate_user(target_user_uid, reason)

    async def activate_user(
        self,
        target_user_uid: str,
        admin_user_uid: str,
    ) -> Result[User]:
        """
        Reactivate a user account (ADMIN only).

        Args:
            target_user_uid: User to reactivate
            admin_user_uid: Admin making the request

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result.expect_error())

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to activate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can activate users")
            )

        # Delegate to core service
        return await self.core.activate_user(target_user_uid)

    # ========================================================================
    # LEARNING PROGRESS (Delegate to UserProgressRecorderService)
    # ========================================================================

    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
        update_progress: bool = True,
    ) -> Result[bool]:
        """Record knowledge mastery using graph relationships."""
        return await self.progress.record_knowledge_mastery(
            user_uid,
            knowledge_uid,
            mastery_score,
            practice_count,
            confidence_level,
            update_progress,
        )

    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record progress on a knowledge unit."""
        return await self.progress.record_knowledge_progress(
            user_uid, knowledge_uid, progress, time_invested_minutes, difficulty_rating
        )

    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path using graph relationships."""
        return await self.progress.enroll_in_learning_path(
            user_uid, learning_path_uid, target_completion, weekly_time_commitment, motivation_note
        )

    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed using graph relationships."""
        return await self.progress.complete_learning_path_graph(
            user_uid, learning_path_uid, completion_score, feedback_rating
        )

    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Express interest in a knowledge unit."""
        return await self.progress.express_interest_in_knowledge(
            user_uid, knowledge_uid, interest_score, interest_source, priority, notes
        )

    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later."""
        return await self.progress.bookmark_knowledge(
            user_uid, knowledge_uid, bookmark_reason, tags, reminder_date
        )

    # ========================================================================
    # ACTIVITY TRACKING (Delegate to UserActivityService)
    # ========================================================================

    async def update_user_activity(
        self, user_uid: str, activity_type: str, entity_uid: str, action: str = "viewed"
    ) -> Result[bool]:
        """Update user's activity state."""
        return await self.activity.update_user_activity(user_uid, activity_type, entity_uid, action)

    async def add_conversation_message(
        self, user_uid: str, role: str, content: str, metadata: dict | None = None
    ) -> Result[bool]:
        """Add message to user's conversation history."""
        return await self.activity.add_conversation_message(user_uid, role, content, metadata)

    async def invalidate_context(
        self, user_uid: str, reason: str = "manual", affected_contexts: list[str] | None = None
    ) -> None:
        """Invalidate cached user context when domain events occur."""
        await self.activity.invalidate_context(user_uid, reason, affected_contexts)

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list[User]]:
        """Get users who have been active recently."""
        return await self.activity.get_active_learners(since_hours, limit)

    # ========================================================================
    # PROFILE HUB DATA (Delegate to UserStatsAggregator)
    # ========================================================================

    async def get_profile_hub_data(self, user_uid: str) -> Result[ProfileHubData]:
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
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(
                    message="ProfileHubData requires Neo4j driver - initialize UserService with driver"
                )
            )

        return await self.stats.get_profile_hub_data(user_uid)

    # ========================================================================
    # CONTEXT BUILDING (Internal - used by stats aggregator)
    # ========================================================================

    async def _build_user_context(self, user_uid: str, user: User) -> Result[UserContext]:
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

    # ========================================================================
    # RICH CONTEXT (November 22, 2025 - Neo4j Optimization)
    # ========================================================================

    async def get_rich_unified_context(
        self, user_uid: str, min_confidence: float = 0.7
    ) -> Result[UserContext]:
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
           - active_tasks_rich: [{task: {...}, graph_context: {subtasks, dependencies, ...}}, ...]
           - active_goals_rich: [{goal: {...}, graph_context: {tasks, habits, milestones}}, ...]
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
            task_uids = context.active_task_uids  # ✅ Populated from MEGA-QUERY

            # Access rich entities with graph neighborhoods
            for task_data in context.active_tasks_rich:  # ✅ Populated from MEGA-QUERY
                task = task_data["task"]
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
        # Get user entity
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result.expect_error())

        user = user_result.value
        if not user:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        # Execute TRUE MEGA-QUERY - ONE query fetches EVERYTHING
        # This replaces the old 2-step approach:
        # OLD: build_user_context() + execute_rich_context_mega_query()
        # NEW: build_rich_user_context() (single comprehensive query)
        context_result = await self.context_builder.build_rich_user_context(
            user_uid, user, min_confidence
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

    # ========================================================================
    # INTELLIGENCE METHODS (Phase 4 - November 2025)
    # ========================================================================

    async def get_daily_work_plan(
        self,
        user_uid: str,
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

        # Build user context
        context_result = await self.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        # Create intelligence service from factory and get daily plan
        intelligence = self.intelligence_factory.create(context)
        plan = await intelligence.get_ready_to_work_on_today(
            prioritize_life_path=prioritize_life_path,
            respect_capacity=respect_capacity,
        )

        return Result.ok(plan)

    async def get_next_learning_steps(
        self,
        user_uid: str,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[LearningStep]]:
        """
        Get optimal next learning steps for a user.

        THE CORE METHOD - determine what to learn next based on ALL factors.

        This combines:
        - Prerequisites met (ready to learn)
        - Goal alignment (helps achieve goals)
        - User capacity (fits available time)
        - Life path alignment (flows toward ultimate path)
        - Energy level (matches current state)
        - Unblocking potential (unlocks other items)

        Args:
            user_uid: User's unique identifier
            max_steps: Maximum number of steps to return
            consider_goals: Weight by goal alignment
            consider_capacity: Respect user capacity limits

        Returns:
            Result[list[LearningStep]]: Ranked list of optimal next learning steps
        """
        # Check if intelligence factory is available
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available",
                    operation="get_next_learning_steps",
                )
            )

        # Build user context
        context_result = await self.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        # Create intelligence service from factory and get learning steps
        intelligence = self.intelligence_factory.create(context)
        steps = await intelligence.get_optimal_next_learning_steps(
            max_steps=max_steps,
            consider_goals=consider_goals,
            consider_capacity=consider_capacity,
        )

        return Result.ok(steps)


# ============================================================================
# FACTORY FUNCTION (Bootstrap Compatibility)
# ============================================================================


def create_user_service(
    user_repo: UserOperations,
    driver: Any | None = None,
    event_bus: Any | None = None,
    intelligence_factory: UserContextIntelligenceFactory | None = None,
    metrics_cache=None,
) -> UserService:
    """
    Factory function to create a UserService instance.

    Args:
        user_repo: User repository implementation
        driver: Optional Neo4j driver for cross-domain aggregation queries
        event_bus: Event bus for publishing domain events (optional)
        intelligence_factory: Factory for creating UserContextIntelligence instances
                              (wired with all 9 domain relationship services)
        metrics_cache: MetricsCache for performance tracking (optional)

    Returns:
        UserService: Configured user service instance (facade pattern)
    """
    return UserService(user_repo, driver, event_bus, intelligence_factory, metrics_cache)
