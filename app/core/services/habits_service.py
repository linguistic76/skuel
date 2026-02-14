"""
Enhanced Habits Service - Facade Pattern
==========================================

Habits service facade that delegates to specialized sub-services.
This service provides a unified interface while maintaining clean separation of concerns.

Version: 7.0.0
- v7.0.0: Added HabitsPlanningService and HabitsSchedulingService (January 2026)
- v6.2.0: Typed Request Objects pattern - explicit API contracts (November 29, 2025)
- v6.1.0: Added HabitSearchService for search/discovery (November 28, 2025)
- v6.0.0: Facade pattern implementation with 6 specialized sub-services (October 13, 2025)
- v5.0.0: Phase 1-4 integration with pure Cypher graph intelligence (October 3, 2025)
- v4.0.0: Enhanced with learning integration and UserContext awareness
- v3.0.0: Base implementation with protocol interfaces

Sub-Services:
- HabitsCoreService: CRUD operations
- HabitSearchService: Search and discovery (DomainSearchOperations[Habit] protocol)
- HabitsProgressService: Streaks, consistency, keystone habits
- HabitsLearningService: Learning path integration
- HabitsPlanningService: Context-aware habit recommendations (January 2026)
- HabitsSchedulingService: Smart scheduling and capacity management (January 2026)
- UnifiedRelationshipService (HABITS_CONFIG): Graph relationships and semantic connections
- HabitsIntelligenceService: pure Cypher analytics
- HabitsEventIntegrationService: Cross-domain event scheduling integration
- HabitAchievementService: Achievement badge awarding (Phase 4)

Architecture: Zero breaking changes - all existing code continues to work unchanged.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import ActivityStatus
from core.models.habit.completion import HabitCompletion
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services and mixins
from core.services.habits import (
    HabitsEventIntegrationService,
    HabitsLearningService,
    HabitsPlanningService,
    HabitsProgressService,
    HabitsSchedulingService,
)
from core.services.habits.habit_achievement_service import HabitAchievementService
from core.services.habits.habits_ai_service import HabitsAIService
from core.services.habits.habits_completion_service import HabitsCompletionService

# Unified relationship service (replaces HabitsRelationshipService)
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import (
    FacadeDelegationMixin,
    create_relationship_delegations,
    merge_delegations,
)
from core.services.protocols.base_protocols import BackendOperations
from core.services.protocols.domain_protocols import HabitsOperations
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.habit.habit_request import (
        ArchiveHabitRequest,
        DeleteHabitReminderRequest,
        HabitCreateRequest,
        PauseHabitRequest,
        ResumeHabitRequest,
        SetHabitReminderRequest,
        TrackHabitRequest,
        UntrackHabitRequest,
    )
    from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
    from core.services.protocols.infrastructure_protocols import EventBusOperations
    from core.services.protocols.search_protocols import HabitsSearchOperations
    from core.services.user import UserContext


class HabitsService(FacadeDelegationMixin, BaseService[HabitsOperations, Ku]):
    """
    Habits service facade with specialized sub-services.

    This facade:
    1. Delegates to 11 specialized sub-services for core operations
    2. Uses FacadeDelegationMixin for ~50 auto-generated delegation methods
    3. Retains explicit methods for complex orchestration operations
    4. Provides clean separation of concerns

    Auto-Generated Delegations (via FacadeDelegationMixin):
    - Core: get_habit, get_user_habits, list_habits, get_user_items_in_range
    - Progress: complete_habit_with_quality, get_at_risk_habits, analyze_habit_consistency, etc.
    - Search: search_habits, get_habits_by_status, get_habits_by_domain, etc.
    - Learning: get_learning_habits, create_habit_from_learning_goal, etc.
    - Planning: get_habit_priorities_for_user, get_actionable_habits_for_user, etc.
    - Scheduling: check_habit_capacity, create_habit_with_context, suggest_habit_stacking, etc.
    - Intelligence: get_habit_with_context, analyze_habit_performance, etc.
    - Events: get_events_for_habit, schedule_events_for_habit

    Explicit Methods (custom logic):
    - Completion tracking: track_habit, untrack_habit, get_habit_streak, etc.
    - Status management: pause_habit, resume_habit, archive_habit
    - Relationship linking: link_habit_to_knowledge, link_habit_to_principle
    - Orchestration: create_habit_with_context
    - Enrichment: get_enriched_learning_summary, get_enriched_curriculum_metadata

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - Uses FacadeDelegationMixin for delegation (January 2026 Phase 3)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(ActivityStatus.ARCHIVED.value,),
    )

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "create_habit": ("core", "create_habit"),
            "get_habit": ("core", "get_habit"),
            "get_user_habits": ("core", "get_user_habits"),
            "list_habits": ("core", "list_habits"),
            "get_user_items_in_range": ("core", "get_user_items_in_range"),
        },
        # Progress delegations
        {
            "complete_habit_with_quality": ("progress", "complete_habit_with_quality"),
            "get_at_risk_habits": ("progress", "get_at_risk_habits"),
            "analyze_habit_consistency": ("progress", "analyze_habit_consistency"),
            "get_keystone_habits": ("progress", "get_keystone_habits"),
            "identify_potential_keystone_habits": (
                "progress",
                "identify_potential_keystone_habits",
            ),
        },
        # Search delegations
        {
            "get_active_habits": ("search", "get_active_habits"),
            "search_habits": ("search", "search"),
            "list_habit_categories": ("search", "list_user_categories"),
            "list_all_habit_categories": ("search", "list_all_categories"),
            "get_habits_by_category": ("search", "get_by_category"),
            "get_habits_due_today": ("search", "get_user_due_today"),
            "get_all_habits_due_today": ("search", "get_all_due_today"),
            "get_overdue_habits": ("search", "get_overdue"),
            "get_habits_by_status": ("search", "get_by_status"),
            "get_habits_by_domain": ("search", "get_by_domain"),
            "get_habits_by_frequency": ("search", "get_by_frequency"),
            "get_prioritized_habits": ("search", "get_prioritized"),
        },
        # Learning delegations
        {
            "get_learning_habits": ("learning", "get_learning_habits"),
            "create_habit_from_learning_goal": ("learning", "create_habit_from_learning_goal"),
            "create_habit_with_learning_alignment": (
                "learning",
                "create_habit_with_learning_alignment",
            ),
            "suggest_learning_supporting_habits": (
                "learning",
                "suggest_learning_supporting_habits",
            ),
            "get_learning_reinforcing_habits": ("learning", "get_learning_reinforcing_habits"),
            "assess_habit_learning_impact": ("learning", "assess_habit_learning_impact"),
        },
        # Relationship delegations (factory-generated)
        create_relationship_delegations("habit"),
        # Intelligence delegations
        {
            "get_habit_with_context": ("intelligence", "get_habit_with_context"),
            "analyze_habit_performance": ("intelligence", "analyze_habit_performance"),
            "get_habit_knowledge_reinforcement": (
                "intelligence",
                "get_habit_knowledge_reinforcement",
            ),
            "get_habit_goal_support": ("intelligence", "get_habit_goal_support"),
        },
        # Event integration delegations
        {
            "get_events_for_habit": ("events", "get_events_for_habit"),
            "schedule_events_for_habit": ("events", "schedule_events_for_habit"),
        },
        # Planning delegations (January 2026)
        {
            "get_habit_priorities_for_user": ("planning", "get_habit_priorities_for_user"),
            "get_actionable_habits_for_user": ("planning", "get_actionable_habits_for_user"),
            "get_learning_habits_for_user": ("planning", "get_learning_habits_for_user"),
            "get_goal_supporting_habits_for_user": (
                "planning",
                "get_goal_supporting_habits_for_user",
            ),
            "get_habit_readiness_for_user": ("planning", "get_habit_readiness_for_user"),
        },
        # Scheduling delegations (January 2026)
        {
            "check_habit_capacity": ("scheduling", "check_habit_capacity"),
            "create_habit_with_scheduling_context": (
                "scheduling",
                "create_habit_with_context",
            ),
            "create_habit_with_learning_scheduling_context": (
                "scheduling",
                "create_habit_with_learning_context",
            ),
            "suggest_habit_frequency": ("scheduling", "suggest_habit_frequency"),
            "optimize_habit_schedule": ("scheduling", "optimize_habit_schedule"),
            "suggest_habit_stacking": ("scheduling", "suggest_habit_stacking"),
            "create_habit_from_learning_step": ("scheduling", "create_habit_from_learning_step"),
            "get_habit_load_by_day": ("scheduling", "get_habit_load_by_day"),
        },
    )

    def __init__(
        self,
        backend: HabitsOperations,
        graph_intelligence_service: GraphIntelligenceService,
        completions_backend: BackendOperations[HabitCompletion],
        driver: AsyncDriver,
        event_bus: EventBusOperations | None = None,
        ai_service: HabitsAIService | None = None,
        insight_store: Any = None,
    ) -> None:
        """
        Initialize enhanced habits service with specialized sub-services.

        Args:
            backend: Protocol-based backend for habit operations (REQUIRED)
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            completions_backend: Backend for habit completion tracking (REQUIRED)
            driver: Neo4j driver for event-driven integrations (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            ai_service: Optional AI service for LLM/embeddings features (January 2026)
            insight_store: InsightStore for persisting event-driven insights (optional, Phase 1 - January 2026)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v2.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.

        Migration Note (January 2026 - Fail-Fast):
            Made completions_backend and driver REQUIRED - no graceful degradation.
        """
        super().__init__(backend, "habits")

        # AI service (optional - app works without it)
        self.ai: HabitsAIService | None = ai_service

        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits")

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[HabitsIntelligenceService] = create_common_sub_services(
            domain="habits",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        self.core = common.core
        self.search: HabitsSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: HabitsIntelligenceService = common.intelligence

        # Completion tracking service (REQUIRED - fail-fast) - create before progress
        self.completions = HabitsCompletionService(
            habits_backend=backend, completions_backend=completions_backend, event_bus=event_bus
        )

        # Domain-specific sub-services (not common to all facades)
        self.progress = HabitsProgressService(
            backend=backend,
            completions_service=self.completions,
            relationship_service=self.relationships,
            event_bus=event_bus,
        )
        self.learning = HabitsLearningService(backend=backend, event_bus=event_bus)
        self.events = HabitsEventIntegrationService(backend=backend)

        # Planning and scheduling services (January 2026)
        self.planning = HabitsPlanningService(
            backend=backend,
            relationship_service=self.relationships,
        )
        self.scheduling = HabitsSchedulingService(
            backend=backend,
            completions_service=self.completions,
            event_bus=event_bus,
        )

        # Phase 4: Event-driven achievement service (driver is REQUIRED)
        self.achievements = HabitAchievementService(
            driver=driver,
            event_bus=event_bus,
        )

        self.logger.info(
            "HabitsService facade initialized with 11 sub-services: "
            "core, search, progress, learning, planning, scheduling, relationships, "
            "intelligence, event_integration, achievements, completions"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Habit entities."""
        return "Ku"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # COMPLETION TRACKING - Delegate to HabitsCompletionService
    # ========================================================================
    # Note: Core CRUD and Progress delegations (get_habit, get_user_habits,
    # complete_habit_with_quality, etc.) auto-generated by FacadeDelegationMixin.

    async def track_habit(
        self,
        request: TrackHabitRequest,
    ) -> Result[Any]:
        """
        Track/record a habit completion using typed request object.

        Args:
            request: TrackHabitRequest containing habit_uid, completion_date, value, notes

        Returns:
            Result with the completion record
        """
        # Parse date - default to now if not provided (explicit at boundary)
        if request.completion_date:
            if isinstance(request.completion_date, str):
                completed_at = datetime.fromisoformat(request.completion_date)
            elif isinstance(request.completion_date, date):
                completed_at = datetime.combine(request.completion_date, datetime.min.time())
            else:
                completed_at = datetime.now()
        else:
            # Explicit default at boundary - caller decides "now"
            completed_at = datetime.now()

        # Get habit to find user_uid
        habit_result = await self.core.get_habit(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=request.habit_uid))

        return await self.completions.record_completion(
            habit_uid=request.habit_uid,
            user_uid=habit.user_uid,
            completed_at=completed_at,  # Always explicit datetime now
            quality=request.value,
            notes=request.notes or "",
        )

    async def untrack_habit(self, request: UntrackHabitRequest) -> Result[bool]:
        """
        Remove a habit tracking entry using typed request object.

        Args:
            request: UntrackHabitRequest containing habit_uid and completion_date

        Returns:
            Result[bool] indicating success
        """
        # Parse date
        target_date = date.today()
        if request.completion_date:
            if isinstance(request.completion_date, str):
                target_date = date.fromisoformat(request.completion_date)
            elif isinstance(request.completion_date, date):
                target_date = request.completion_date

        # Get completions for the date
        completions_result = await self.completions.get_completions_for_habit(
            request.habit_uid, start_date=target_date, end_date=target_date
        )
        if completions_result.is_error:
            return Result.fail(completions_result.expect_error())

        completions = completions_result.value
        if not completions:
            return Result.fail(
                Errors.not_found(
                    resource="HabitCompletion", identifier=f"{request.habit_uid} on {target_date}"
                )
            )

        # Delete the completion(s) for that date
        # Note: Using backend directly as completions service may not have delete
        for completion in completions:
            await self.completions.completions_backend.delete(completion.uid)

        return Result.ok(True)

    async def get_habit_streak(self, habit_uid: str) -> Result[dict[str, Any]]:
        """
        Get current streak information for a habit.

        Args:
            habit_uid: UID of the habit

        Returns:
            Result with streak data including current_streak, longest_streak
        """
        # Get habit for streak data
        habit_result = await self.core.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        streak_data = {
            "habit_uid": habit_uid,
            "current_streak": habit.current_streak or 0,
            "longest_streak": habit.best_streak or 0,
            "last_completed": habit.last_completed.isoformat() if habit.last_completed else None,
        }

        return Result.ok(streak_data)

    async def get_habit_progress(
        self, habit_uid: str, period: str = "month"
    ) -> Result[dict[str, Any]]:
        """
        Get progress statistics for a habit over a period.

        Args:
            habit_uid: UID of the habit
            period: Time period - "week", "month", or "year"

        Returns:
            Result with progress statistics
        """
        # Map period to days
        period_days = {"week": 7, "month": 30, "year": 365}.get(period, 30)
        return await self.completions.get_completion_stats(habit_uid, days=period_days)

    async def get_habit_history(
        self, habit_uid: str, days: int = 90
    ) -> Result[list[dict[str, Any]]]:
        """
        Get completion history for a habit.

        Args:
            habit_uid: UID of the habit
            days: Number of days of history to retrieve (default: 90)

        Returns:
            Result with list of completion records
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get completions from completions service
        result = await self.completions.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        completions = result.value or []

        # Convert to simple dict format for API response
        history = [
            {
                "uid": c.uid,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                "quality": c.quality,
                "notes": c.notes,
            }
            for c in completions
        ]

        return Result.ok(history)

    async def get_completion_calendar(
        self, habit_uid: str, year: int | None = None, month: int | None = None
    ) -> Result[dict[str, Any]]:
        """
        Get completion data formatted for calendar visualization.

        Args:
            habit_uid: UID of the habit
            year: Year to get data for (default: current year)
            month: Month to get data for (default: current month)

        Returns:
            Result with calendar data including:
            - dates: dict mapping date strings to completion status
            - summary: completion statistics for the period
        """
        # Default to current month
        today = date.today()
        target_year = year or today.year
        target_month = month or today.month

        # Calculate date range for the month
        start_date = date(target_year, target_month, 1)
        # Get last day of month
        if target_month == 12:
            end_date = date(target_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(target_year, target_month + 1, 1) - timedelta(days=1)

        # Get completions for the month
        result = await self.completions.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        completions = result.value or []

        # Build calendar data: map dates to completion info
        dates: dict[str, dict[str, Any]] = {}
        for c in completions:
            if c.completed_at:
                date_str = c.completed_at.date().isoformat()
                dates[date_str] = {
                    "completed": True,
                    "quality": c.quality,
                    "notes": c.notes,
                }

        # Calculate summary stats
        days_in_month = (end_date - start_date).days + 1
        completed_days = len(dates)

        calendar_data = {
            "habit_uid": habit_uid,
            "year": target_year,
            "month": target_month,
            "dates": dates,
            "summary": {
                "days_in_month": days_in_month,
                "completed_days": completed_days,
                "completion_rate": round(completed_days / days_in_month * 100, 1),
            },
        }

        return Result.ok(calendar_data)

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def pause_habit(self, request: PauseHabitRequest) -> Result[Ku]:
        """
        Pause a habit temporarily using typed request object.

        Args:
            request: PauseHabitRequest containing habit_uid, reason, until_date

        Returns:
            Result with the updated habit
        """
        updates: dict[str, Any] = {
            "status": ActivityStatus.PAUSED.value,
            "notes": request.reason,
        }
        if request.until_date:
            if isinstance(request.until_date, str):
                updates["paused_until"] = request.until_date
            else:
                updates["paused_until"] = request.until_date.isoformat()

        return await self.core.update(request.habit_uid, updates)

    async def resume_habit(self, request: ResumeHabitRequest) -> Result[Ku]:
        """
        Resume a paused habit using typed request object.

        Args:
            request: ResumeHabitRequest containing habit_uid

        Returns:
            Result with the updated habit
        """
        updates = {
            "status": ActivityStatus.IN_PROGRESS.value,
            "paused_until": None,
        }
        return await self.core.update(request.habit_uid, updates)

    async def archive_habit(self, request: ArchiveHabitRequest) -> Result[Ku]:
        """
        Archive a completed or discontinued habit using typed request object.

        Args:
            request: ArchiveHabitRequest containing habit_uid, reason

        Returns:
            Result with the updated habit
        """
        updates = {
            "status": ActivityStatus.ARCHIVED.value,
            "notes": request.reason,
        }
        return await self.core.update(request.habit_uid, updates)

    # ========================================================================
    # REMINDERS
    # ========================================================================
    # Reminder configuration is stored directly on the Habit model.
    # Note: Search delegations (search_habits, get_habits_by_status, etc.)
    # auto-generated by FacadeDelegationMixin.

    async def set_habit_reminder(
        self,
        request: SetHabitReminderRequest,
    ) -> Result[dict[str, Any]]:
        """
        Set a reminder for a habit using typed request object.

        Stores reminder configuration directly on the Habit model.

        Args:
            request: SetHabitReminderRequest containing habit_uid, reminder_time, days, enabled

        Returns:
            Result with reminder configuration
        """
        # Verify habit exists
        habit_result = await self.core.get(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        # Update habit with reminder config
        updates = {
            "reminder_time": request.reminder_time,
            "reminder_days": request.days,
            "reminder_enabled": request.enabled,
        }
        update_result = await self.core.update(request.habit_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        self.logger.info(
            f"Set reminder for habit {request.habit_uid}: {request.reminder_time} on {request.days}"
        )
        return Result.ok(
            {
                "habit_uid": request.habit_uid,
                "reminder_time": request.reminder_time,
                "days": request.days,
                "enabled": request.enabled,
                "status": "configured",
            }
        )

    async def get_habit_reminders(self, habit_uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get reminders for a habit.

        Returns the reminder configuration stored on the habit.

        Args:
            habit_uid: UID of the habit

        Returns:
            Result with list of reminders (single reminder per habit)
        """
        habit_result = await self.core.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value

        # If no reminder configured, return empty list
        if not habit.reminder_time and not habit.reminder_enabled:
            return Result.ok([])

        # Return the single reminder config as a list for API consistency
        reminder = {
            "id": f"{habit_uid}_reminder",
            "habit_uid": habit_uid,
            "reminder_time": habit.reminder_time,
            "days": list(habit.reminder_days) if habit.reminder_days else [],
            "enabled": habit.reminder_enabled,
        }
        return Result.ok([reminder])

    async def delete_habit_reminder(self, request: DeleteHabitReminderRequest) -> Result[bool]:
        """
        Delete a habit reminder using typed request object.

        Clears the reminder configuration from the habit.

        Args:
            request: DeleteHabitReminderRequest containing habit_uid, reminder_id

        Returns:
            Result with success status
        """
        # Verify habit exists
        habit_result = await self.core.get(request.habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        # Clear reminder config
        updates = {
            "reminder_time": None,
            "reminder_days": [],
            "reminder_enabled": False,
        }
        update_result = await self.core.update(request.habit_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        self.logger.info(f"Deleted reminder for habit {request.habit_uid}")
        return Result.ok(True)

    # ========================================================================
    # ANALYTICS - Delegates to HabitsIntelligenceService
    # ========================================================================

    async def get_habit_analytics(
        self,
        habit_uid: str,
        _period: str = "month",
        _include_predictions: bool = False,
    ) -> Result[dict[str, Any]]:
        """
        Get analytics for a specific habit.

        Delegates to HabitsIntelligenceService.analyze_habit_performance().

        Args:
            habit_uid: UID of the habit
            _period: Placeholder - period filtering not yet implemented
            _include_predictions: Placeholder - AI predictions not yet implemented

        Returns:
            Result with analytics data including performance metrics,
            knowledge reinforcement, and goal support analysis
        """
        return await self.intelligence.analyze_habit_performance(habit_uid)

    async def get_habits_summary_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get summary analytics for all user habits.

        Delegates to HabitsIntelligenceService.get_performance_analytics().

        Args:
            user_uid: User UID to get analytics for
            period_days: Number of days for analytics period (default: 30)

        Returns:
            Result with summary analytics including totals, averages, and at-risk counts
        """
        return await self.intelligence.get_performance_analytics(user_uid, period_days)

    async def get_habit_trends(
        self, user_uid: str, time_range: str = "30d"
    ) -> Result[dict[str, Any]]:
        """
        Get habit completion trends for a user.

        Calculates trend data from habit metrics over time.

        Args:
            user_uid: User UID to get trends for
            time_range: Time range for trends (e.g., "7d", "30d", "90d")

        Returns:
            Result with trend data including streak trends and consistency patterns
        """
        # Parse time range to days
        days = 30  # default
        if time_range.endswith("d"):
            try:
                days = int(time_range[:-1])
            except ValueError:
                days = 30

        # Get performance analytics which includes trend-relevant data
        analytics_result = await self.intelligence.get_performance_analytics(user_uid, days)
        if analytics_result.is_error:
            return Result.fail(analytics_result.expect_error())

        analytics = analytics_result.value

        # Build trend response from analytics
        return Result.ok(
            {
                "user_uid": user_uid,
                "time_range": time_range,
                "period_days": days,
                "trends": {
                    "total_habits": analytics.get("total_habits", 0),
                    "active_habits": analytics.get("active_habits", 0),
                    "habits_with_streak": analytics.get("habits_with_streak", 0),
                    "at_risk_habits": analytics.get("at_risk_habits", 0),
                    "avg_consistency": analytics.get("avg_consistency", 0.0),
                    "avg_streak": analytics.get("avg_streak", 0.0),
                },
                "summary": {
                    "consistency_trend": "stable"
                    if analytics.get("avg_consistency", 0) >= 0.5
                    else "declining",
                    "streak_health": "healthy"
                    if analytics.get("habits_with_streak", 0) > analytics.get("at_risk_habits", 0)
                    else "at_risk",
                },
            }
        )

    # ========================================================================
    # GRAPH RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================
    # Note: Learning delegations (get_learning_habits, create_habit_from_learning_goal, etc.)
    # auto-generated by FacadeDelegationMixin.

    async def create_user_habit_relationship(
        self, user_uid: str, habit_uid: str, commitment_level: str = "active"
    ) -> Result[bool]:
        """Create User→Habit relationship in graph."""
        properties = (
            {"commitment_level": commitment_level} if commitment_level != "active" else None
        )
        return await self.relationships.create_user_relationship(user_uid, habit_uid, properties)

    async def link_habit_to_knowledge(
        self,
        habit_uid: str,
        knowledge_uid: str,
        skill_level: str = "beginner",
        proficiency_gain_rate: float = 0.1,
    ) -> Result[bool]:
        """Link habit to knowledge/skill it develops."""
        return await self.relationships.link_to_knowledge(
            habit_uid,
            knowledge_uid,
            skill_level=skill_level,
            proficiency_gain_rate=proficiency_gain_rate,
        )

    async def link_habit_to_principle(
        self, habit_uid: str, principle_uid: str, embodiment_strength: float = 1.0
    ) -> Result[bool]:
        """Link habit to principle/value it embodies."""
        return await self.relationships.link_to_principle(
            habit_uid,
            principle_uid,
            embodiment_strength=embodiment_strength,
        )

    # Note: get_habit_cross_domain_context, get_habit_with_semantic_context auto-generated
    # by FacadeDelegationMixin.

    async def get_skills_developed_by_habits(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get all skills/knowledge developed through user's habits."""
        # Get all user habits
        habits_result = await self.backend.list_by_user(user_uid=user_uid, limit=100)
        if habits_result.is_error:
            return Result.fail(habits_result)

        habits = habits_result.value
        if not habits:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "habit_count": 0,
                    "knowledge_uids": [],
                    "skills_count": 0,
                }
            )

        # Batch query: get all knowledge UIDs for all habits in ONE query
        habit_uids = [h.uid for h in habits]
        batch_result = await self.relationships.batch_get_related_uids("knowledge", habit_uids)

        # Collect all unique knowledge UIDs
        all_knowledge_uids: set[str] = set()
        if batch_result.is_ok:
            for uids in batch_result.value.values():
                all_knowledge_uids.update(uids)

        return Result.ok(
            {
                "user_uid": user_uid,
                "habit_count": len(habits),
                "knowledge_uids": list(all_knowledge_uids),
                "skills_count": len(all_knowledge_uids),
            }
        )

    async def create_semantic_skill_relationship(
        self,
        habit_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between habit and knowledge/skill."""
        return await self.relationships.create_semantic_relationship(
            habit_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_habits_developing_knowledge(
        self, knowledge_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Ku]]:
        """Find habits that develop or reinforce specific knowledge/skill."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid,
            min_confidence=min_confidence,
            direction="incoming",
        )

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================
    # Note: Intelligence delegations (get_habit_with_context, analyze_habit_performance, etc.)
    # and Event Integration delegations (get_events_for_habit, schedule_events_for_habit)
    # auto-generated by FacadeDelegationMixin.

    async def create_habit_with_context(
        self, habit_data: HabitCreateRequest, user_context: UserContext
    ) -> Result[Ku]:
        """
        Create a habit with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Validates knowledge prerequisites
        2. Links to supporting goals
        3. Sets up event scheduling
        4. Updates context after creation
        """
        # Check if habit supports any active goals
        supporting_goals = [
            goal_uid
            for goal_uid in user_context.active_goal_uids
            if habit_data.linked_goal_uids and goal_uid in habit_data.linked_goal_uids
        ]

        # Create habit through learning service (handles DTO creation)
        result = await self.learning.create_habit_with_learning_alignment(habit_data, None)
        if result.is_error:
            return result

        # Note: User context invalidation now happens via event-driven architecture
        # HabitCreated event → invalidate_context_on_habit_event() → user_service.invalidate_context()

        habit = result.value
        # Get knowledge count from request data
        knowledge_count = (
            len(habit_data.linked_knowledge_uids) if habit_data.linked_knowledge_uids else 0
        )
        self.logger.info(
            "Created habit %s supporting %d goals, reinforcing %d knowledge items",
            habit.uid,
            len(supporting_goals),
            knowledge_count,
        )

        return Result.ok(habit)

    # ========================================================================
    # ENRICHMENT METHODS (Moved from routes - November 28, 2025)
    # ========================================================================
    # These methods fetch graph relationships and create enriched views.
    # Previously inline in habits_api.py routes, now properly in service layer.

    async def get_enriched_learning_summary(self, habit: Ku) -> Result[dict[str, Any]]:
        """
        Get learning summary with relationship data from graph.

        Args:
            habit: Ku domain model (ku_type='habit')

        Returns:
            Result containing enriched learning summary dict
        """
        # Fetch knowledge relationships
        knowledge_result = await self.relationships.get_related_uids("knowledge", habit.uid)
        knowledge_uids = knowledge_result.value if knowledge_result.is_ok else []

        # Fetch goal relationships
        goals_result = await self.relationships.get_related_uids("supported_goals", habit.uid)
        goal_uids = goals_result.value if goals_result.is_ok else []

        # Fetch principle relationships
        principles_result = await self.relationships.get_related_uids("principles", habit.uid)
        principle_uids = principles_result.value if principles_result.is_ok else []

        # Learning step relationships - not in config, return empty for now
        step_uids: list[str] = []

        # Integration level calculation
        integration_count = 0
        if habit.source_learning_step_uid or habit.source_learning_path_uid:
            integration_count += 3
        if habit.is_identity_habit:
            integration_count += 2

        if integration_count == 0:
            integration_level = "standalone"
        elif integration_count <= 2:
            integration_level = "basic"
        elif integration_count <= 5:
            integration_level = "moderate"
        elif integration_count <= 9:
            integration_level = "high"
        else:
            integration_level = "comprehensive"

        polarity_value = habit.polarity.value if habit.polarity else "neutral"
        category_value = habit.habit_category.value if habit.habit_category else "other"
        difficulty_value = habit.habit_difficulty.value if habit.habit_difficulty else "moderate"

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "category": category_value,
            "polarity": polarity_value,
            "difficulty": difficulty_value,
            "linked_knowledge_count": len(knowledge_uids),
            "knowledge_uids": knowledge_uids,
            "linked_goal_count": len(goal_uids),
            "goal_uids": goal_uids,
            "linked_principle_count": len(principle_uids),
            "principle_uids": principle_uids,
            "is_curriculum_habit": habit.source_learning_step_uid is not None
            or habit.source_learning_path_uid is not None,
            "source_step_uid": habit.source_learning_step_uid,
            "source_path_uid": habit.source_learning_path_uid,
            "reinforces_step_count": len(step_uids),
            "step_uids": step_uids,
            "practice_type": habit.curriculum_practice_type,
            "is_identity_habit": habit.is_identity_habit,
            "reinforces_identity": habit.reinforces_identity,
            "identity_votes_cast": habit.identity_votes_cast,
            "current_streak": habit.current_streak,
            "best_streak": habit.best_streak,
            "total_completions": habit.total_completions,
            "success_rate": habit.success_rate,
            "learning_integration_level": integration_level,
        }

        return Result.ok(enriched)

    async def get_enriched_curriculum_metadata(self, habit: Ku) -> Result[dict[str, Any]]:
        """
        Get curriculum metadata with relationship data from graph.

        Args:
            habit: Ku domain model (ku_type='habit')

        Returns:
            Result containing curriculum metadata dict
        """
        # Learning step relationships - not in config, return empty for now
        step_uids: list[str] = []

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "is_curriculum_habit": habit.source_learning_step_uid is not None
            or habit.source_learning_path_uid is not None,
            "source_step_uid": habit.source_learning_step_uid,
            "source_path_uid": habit.source_learning_path_uid,
            "reinforces_step_uids": step_uids,
            "reinforces_step_count": len(step_uids),
            "practice_type": habit.curriculum_practice_type,
            "supports_multiple_steps": len(step_uids) > 1,
        }
        return Result.ok(enriched)

    async def get_enriched_prerequisite_metadata(self, habit: Ku) -> Result[dict[str, Any]]:
        """
        Get prerequisite chain metadata with relationship data from graph.

        Args:
            habit: Ku domain model (ku_type='habit')

        Returns:
            Result containing prerequisite metadata dict
        """
        # Fetch prerequisite relationships
        prereqs_result = await self.relationships.get_related_uids("prerequisite_habits", habit.uid)
        prerequisite_uids = prereqs_result.value if prereqs_result.is_ok else []

        difficulty_value = habit.habit_difficulty.value if habit.habit_difficulty else "moderate"
        status_value = habit.status.value if habit.status else "active"

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "has_prerequisites": len(prerequisite_uids) > 0,
            "prerequisite_uids": prerequisite_uids,
            "prerequisite_count": len(prerequisite_uids),
            "is_foundational": len(prerequisite_uids) == 0,
            "difficulty": difficulty_value,
            "is_active": status_value == "active",
        }
        return Result.ok(enriched)


# Legacy alias removed - class renamed directly to HabitsService
