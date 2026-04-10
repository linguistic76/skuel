"""
Habits Service - Facade Pattern
=================================

Habits service facade that delegates to specialized sub-services.

Architecture: Shell delegates to 3 facade mixins in the habits/ package:
  _completion_mixin.py    — track_habit, untrack_habit, get_habit_streak/progress/history,
                             get_completion_calendar, pause/resume/archive_habit,
                             set/get/delete_habit_reminder
  _enrichment_mixin.py    — get_habit_analytics, get_habits_summary_analytics, get_habit_trends,
                             get_enriched_learning/curriculum/prerequisite_metadata
  _orchestration_mixin.py — complete_with_goal_impacts, create_with_goal_links,
                             create_user_habit_relationship, link_habit_to_knowledge/principle,
                             get_skills_developed_by_habits, create_semantic_skill_relationship,
                             find_habits_developing_knowledge, create_habit_with_context

Sub-Services:
- HabitsCoreService: CRUD operations
- HabitsSearchService: Search and discovery (DomainSearchOperations[Habit] protocol)
- HabitsProgressService: Streaks, consistency, keystone habits
- HabitsLearningService: Learning path integration
- HabitsPlanningService: Context-aware habit recommendations (January 2026)
- HabitsSchedulingService: Smart scheduling and capacity management (January 2026)
- UnifiedRelationshipService (HABITS_CONFIG): Graph relationships and semantic connections
- HabitsIntelligenceService: pure Cypher analytics + event scheduling intelligence
- HabitEventHandlerService: Event-driven reactive logic (fire-and-forget handlers)
- HabitsCompletionService: Completion tracking with quality scores and streaks
- HabitsPatternService: Atomic Habits pattern recognition with confidence scoring
- ActivityKnowledgeIntelligenceService: Domain-agnostic knowledge intelligence (shared singleton)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date

from core.models.enums import Domain, EntityStatus, RecurrencePattern
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.type_hints import EntityUID, UserUID
from core.ports.base_protocols import BackendOperations
from core.ports.domain_protocols import HabitsOperations
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context

# Import sub-services and mixins
from core.services.habits import (
    HabitsLearningService,
    HabitsPlanningService,
    HabitsProgressService,
    HabitsSchedulingService,
)
from core.services.habits._completion_mixin import _CompletionMixin
from core.services.habits._enrichment_mixin import _EnrichmentMixin
from core.services.habits._orchestration_mixin import _OrchestrationMixin
from core.services.habits.habit_event_handler_service import HabitEventHandlerService
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.services.habits.habits_pattern_service import HabitsPatternService
from core.services.habits.habits_scheduling_service import DEFAULT_MAX_DAILY_LOAD

# Unified relationship service
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import KnowledgeIntelligenceDelegationMixin
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_stats import compute_habit_stats
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_current_streak,
    get_name_lower,
    get_recurrence_pattern,
)

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.context_types import ContextualDependencies, ContextualHabit
    from core.models.graph_context import GraphContext
    from core.models.habit.habit_request import HabitCreateRequest
    from core.models.pathways.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import HabitsSearchOperations
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.habits.habits_ai_service import HabitsAIService
    from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
    from core.services.user import UserContext


def _compute_habit_metadata(_all_habits: list[Any]) -> dict[str, Any]:
    """Compute habit metadata — categories from HabitCategory enum."""
    from core.models.enums.habit_enums import HabitCategory

    return {"categories": [c.value for c in HabitCategory if c != HabitCategory.OTHER]}


def _compute_habit_stats(all_habits: list[Any]) -> dict[str, int | float]:
    """Dict projection of HabitStats for the cross-domain ListContext contract."""
    s = compute_habit_stats(all_habits)
    return {"total": s.total, "active": s.active, "streaks": s.streaks}


def _is_habit_active(h: Any) -> bool:
    """Filter predicate: habit is active."""
    return h.status == EntityStatus.ACTIVE


def _is_habit_paused(h: Any) -> bool:
    """Filter predicate: habit is paused."""
    return h.status == EntityStatus.PAUSED


def _is_habit_completed(h: Any) -> bool:
    """Filter predicate: habit is completed."""
    return h.status == EntityStatus.COMPLETED


_HABIT_FILTER_CONFIG: FilterConfig = {
    "active": _is_habit_active,
    "paused": _is_habit_paused,
    "completed": _is_habit_completed,
}

_HABIT_SORT_CONFIG: SortConfig = {
    "streak": (get_current_streak, True),
    "name": (get_name_lower, False),
    "created_at": (get_created_at_attr, True),
    "frequency": (get_recurrence_pattern, False),
}


def _apply_habit_sort(habits: list[Any], sort_by: str = "streak") -> list[Any]:
    """Sort habits using declarative config."""
    return apply_entity_sort(habits, sort_by, _HABIT_SORT_CONFIG, "streak")


class HabitsService(
    _CompletionMixin,
    _EnrichmentMixin,
    _OrchestrationMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService[HabitsOperations, Habit],
):
    """
    Habits service facade with specialized sub-services.

    Architecture: Shell delegates to 13 sub-services and 3 facade mixins.

    Delegation methods (explicit ~45 methods):
    - Core: get_habit, get_user_habits, list_habits, get_user_items_in_range
    - Progress: complete_habit_with_quality, get_at_risk_habits, analyze_habit_consistency, etc.
    - Search: search_habits, get_habits_by_status, get_habits_by_domain, etc.
    - Learning: get_learning_habits, create_habit_from_learning_goal, etc.
    - Planning: get_habit_priorities_for_user, get_actionable_habits_for_user, etc.
    - Scheduling: check_habit_capacity, suggest_habit_stacking, etc.
    - Intelligence: get_habit_with_context, analyze_habit_performance, etc.
    - Events: get_event_uids_for_habit, schedule_events_for_habit

    Mixin methods (see habits/ package):
    - _CompletionMixin: track_habit, untrack_habit, get_habit_streak/progress/history,
      get_completion_calendar, pause/resume/archive_habit, set/get/delete_habit_reminder
    - _EnrichmentMixin: get_habit_analytics, get_habits_summary_analytics, get_habit_trends,
      get_enriched_learning/curriculum/prerequisite_metadata
    - _OrchestrationMixin: complete_with_goal_impacts, create_with_goal_links,
      create_user_habit_relationship, link_habit_to_knowledge/principle,
      get_skills_developed_by_habits, create_habit_with_context, etc.
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=HabitDTO,
        model_class=Habit,
        entity_label="Entity",
        domain_name="habits",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
    )

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def create_habit(
        self, habit_request: HabitCreateRequest, user_uid: UserUID
    ) -> Result[Habit]:
        return await self.core.create_habit(habit_request, user_uid)

    async def get_habit(self, uid: str) -> Result[Habit]:
        return await self.core.get_habit(uid)

    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        return await self.core.get_user_habits(user_uid)

    async def list_habits(
        self, limit: int = 100, **filters: Any
    ) -> Result[tuple[list[Habit], int]]:
        return await self.core.list_habits(limit, **filters)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Habit]]:
        return await self.core.get_user_items_in_range(
            user_uid, start_date, end_date, include_completed
        )

    # Progress delegations
    async def complete_habit_with_quality(
        self,
        habit_uid: str,
        user_context: UserContext,
        quality_score: int = 4,
        completion_date: date | None = None,
    ) -> Result[Habit]:
        return await self.progress.complete_habit_with_quality(
            habit_uid, user_context, quality_score, completion_date
        )

    async def get_at_risk_habits(
        self, user_context: UserContext, _risk_threshold_days: int = 3
    ) -> Result[list[Habit]]:
        return await self.progress.get_at_risk_habits(user_context, _risk_threshold_days)

    async def analyze_habit_consistency(
        self, habit_uid: str, user_context: UserContext, _days: int = 30
    ) -> Result[dict[str, Any]]:
        return await self.progress.analyze_habit_consistency(habit_uid, user_context, _days)

    async def get_keystone_habits(self, user_context: UserContext) -> Result[list[Habit]]:
        return await self.progress.get_keystone_habits(user_context)

    async def identify_potential_keystone_habits(
        self, user_context: UserContext
    ) -> Result[list[Habit]]:
        return await self.progress.identify_potential_keystone_habits(user_context)

    # Search delegations
    async def get_active_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        return await self.search.get_active_habits(user_uid)

    async def search_habits(
        self, query: str, limit: int = 50, user_uid: UserUID | None = None
    ) -> Result[list[Habit]]:
        return await self.search.search(query, limit, user_uid)

    async def list_habit_categories(self, user_uid: UserUID) -> Result[list[str]]:
        return await self.search.list_user_categories(user_uid)

    async def list_all_habit_categories(self) -> Result[list[str]]:
        return await self.search.list_all_categories()

    async def get_habits_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Habit]]:
        return await self.search.get_by_category(category, user_uid=user_uid, limit=limit)

    async def get_habits_due_today(self, user_uid: UserUID) -> Result[list[Habit]]:
        return await self.search.get_user_due_today(user_uid)

    async def get_all_habits_due_today(self) -> Result[list[Habit]]:
        return await self.search.get_all_due_today()

    async def get_overdue_habits(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Habit]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_habits_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[Habit]]:
        return await self.search.get_by_status(status, limit, user_uid)

    async def get_habits_by_domain(self, domain: Domain, limit: int = 100) -> Result[list[Habit]]:
        return await self.search.get_by_domain(domain, limit)

    async def get_habits_by_frequency(
        self, frequency: RecurrencePattern, limit: int = 100
    ) -> Result[list[Habit]]:
        return await self.search.get_by_frequency(frequency, limit)

    async def get_prioritized_habits(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Habit]]:
        return await self.search.get_prioritized(user_context, limit)

    # Learning delegations
    async def get_learning_habits(self, user_context: UserContext) -> Result[list[Habit]]:
        return await self.learning.get_learning_habits(user_context)

    async def create_habit_from_learning_goal(
        self,
        knowledge_uid: str,
        user_context: UserContext,
        frequency: RecurrencePattern = RecurrencePattern.DAILY,
    ) -> Result[dict[str, Any]]:
        return await self.learning.create_habit_from_learning_goal(
            knowledge_uid, user_context, frequency
        )

    async def create_habit_with_learning_alignment(
        self, habit_request: HabitCreateRequest, learning_position: LpPosition | None = None
    ) -> Result[Habit]:
        return await self.learning.create_habit_with_learning_alignment(
            habit_request, learning_position
        )

    async def suggest_learning_supporting_habits(
        self, learning_position: LpPosition, habit_category: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_supporting_habits(
            learning_position, habit_category
        )

    async def get_learning_reinforcing_habits(
        self, user_uid: UserUID, learning_position: LpPosition
    ) -> Result[list[Habit]]:
        return await self.learning.get_learning_reinforcing_habits(user_uid, learning_position)

    async def assess_habit_learning_impact(
        self, habit_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        return await self.learning.assess_habit_learning_impact(habit_uid, learning_position)

    # Relationship delegations
    async def get_habit_cross_domain_context(
        self, entity_uid: EntityUID, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_cross_domain_context(entity_uid, depth, min_confidence)

    async def get_habit_with_semantic_context(
        self,
        uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_with_semantic_context(
            uid, min_confidence, semantic_types
        )

    # Intelligence delegations
    async def get_habit_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        return await self.intelligence.get_habit_with_context(uid, depth)

    async def analyze_habit_performance(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.analyze_habit_performance(uid, min_confidence)

    async def get_habit_knowledge_reinforcement(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_habit_knowledge_reinforcement(uid, depth, min_confidence)

    async def get_habit_goal_support(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_habit_goal_support(uid, depth, min_confidence)

    # Event scheduling intelligence delegations
    async def get_event_uids_for_habit(
        self, habit_uid: str, user_context: UserContext, _days_ahead: int = 7
    ) -> Result[list[str]]:
        return await self.intelligence.get_event_uids_for_habit(
            habit_uid, user_context, _days_ahead
        )

    async def schedule_events_for_habit(
        self, habit_uid: str, _user_context: UserContext, days_to_schedule: int = 7
    ) -> Result[list[dict[str, Any]]]:
        return await self.intelligence.schedule_events_for_habit(
            habit_uid, _user_context, days_to_schedule
        )

    # Planning delegations
    async def get_habit_priorities_for_user(
        self, context: UserContext, limit: int = 10
    ) -> Result[list[ContextualHabit]]:
        return await self.planning.get_habit_priorities_for_user(context, limit)

    async def get_actionable_habits_for_user(
        self, context: UserContext, limit: int = 10
    ) -> Result[list[ContextualHabit]]:
        return await self.planning.get_actionable_habits_for_user(context, limit)

    async def get_learning_habits_for_user(
        self,
        context: UserContext,
        knowledge_focus: list[str] | None = None,
        limit: int = 10,
    ) -> Result[list[ContextualHabit]]:
        return await self.planning.get_learning_habits_for_user(context, knowledge_focus, limit)

    async def get_goal_supporting_habits_for_user(
        self, context: UserContext, goal_uid: str | None = None, limit: int = 10
    ) -> Result[list[ContextualHabit]]:
        return await self.planning.get_goal_supporting_habits_for_user(context, goal_uid, limit)

    async def get_habit_readiness_for_user(
        self, habit_uid: str, context: UserContext
    ) -> Result[ContextualDependencies]:
        return await self.planning.get_habit_readiness_for_user(habit_uid, context)

    # Scheduling delegations
    async def check_habit_capacity(
        self,
        user_uid: UserUID,
        proposed_difficulty: HabitDifficulty = HabitDifficulty.MODERATE,
        proposed_duration: int = 15,
        max_daily_load: int = DEFAULT_MAX_DAILY_LOAD,
    ) -> Result[dict[str, Any]]:
        return await self.scheduling.check_habit_capacity(
            user_uid, proposed_difficulty, proposed_duration, max_daily_load
        )

    async def create_habit_with_scheduling_context(
        self,
        habit_data: HabitCreateRequest,
        user_context: UserContext,
        check_capacity: bool = True,
    ) -> Result[Habit]:
        return await self.scheduling.create_habit_with_context(
            habit_data, user_context, check_capacity
        )

    async def create_habit_with_learning_scheduling_context(
        self,
        habit_data: HabitCreateRequest,
        learning_position: LpPosition | None,
        user_context: UserContext,
    ) -> Result[Habit]:
        return await self.scheduling.create_habit_with_learning_context(
            habit_data, learning_position, user_context
        )

    async def suggest_habit_frequency(
        self,
        user_uid: UserUID,
        category: HabitCategory,
        difficulty: HabitDifficulty = HabitDifficulty.MODERATE,
    ) -> Result[dict[str, Any]]:
        return await self.scheduling.suggest_habit_frequency(user_uid, category, difficulty)

    async def optimize_habit_schedule(
        self, habit_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        return await self.scheduling.optimize_habit_schedule(habit_uid, user_context)

    async def suggest_habit_stacking(
        self,
        user_uid: UserUID,
        new_habit_time: str | None = None,
        new_habit_category: HabitCategory | None = None,
    ) -> Result[list[dict[str, Any]]]:
        return await self.scheduling.suggest_habit_stacking(
            user_uid, new_habit_time, new_habit_category
        )

    async def create_habit_from_path_step(
        self,
        path_step_uid: str,
        user_context: UserContext,
        frequency: RecurrencePattern = RecurrencePattern.DAILY,
        duration_minutes: int = 15,
    ) -> Result[Habit]:
        return await self.scheduling.create_habit_from_path_step(
            path_step_uid, user_context, frequency, duration_minutes
        )

    async def get_habit_load_by_day(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        return await self.scheduling.get_habit_load_by_day(user_uid)

    def __init__(
        self,
        backend: HabitsOperations,
        graph_intelligence_service: GraphIntelligenceService,
        completions_backend: BackendOperations[HabitCompletion],
        cross_domain_query: CrossDomainQueryService,
        event_bus: EventBusOperations | None = None,
        insight_store: Any = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: HabitsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced habits service with specialized sub-services.

        Args:
            backend: Protocol-based backend for habit operations (REQUIRED)
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            completions_backend: Backend for habit completion tracking (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v2.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.

        Migration Note (January 2026 - Fail-Fast):
            Made completions_backend REQUIRED - no graceful degradation.
        """
        super().__init__(backend, "habits")

        # Optional AI service (ADR-030: AI features are optional)
        self.ai: HabitsAIService | None = ai_service

        self.graph_intel = graph_intelligence_service
        self.cross_domain_query = cross_domain_query
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits")  # type: ignore[assignment]  # structlog BoundLogger

        # Initialize core/search/relationships/event_handler/learning/
        # knowledge_intelligence via factory. Intelligence is built manually
        # because HabitsIntelligenceService takes cross_domain_query for the
        # ZPD knowledge-signals bridge.
        common: CommonSubServices[HabitsIntelligenceService] = create_common_sub_services(
            domain="habits",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
            skip={"intelligence"},
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        self.core = common.core
        self.search: HabitsSearchOperations = common.search  # type: ignore[assignment]  # search service implements callable protocol
        self.relationships: UnifiedRelationshipService = common.relationships  # type: ignore[assignment]  # never skipped

        from core.services.habits.habits_intelligence_service import (
            HabitsIntelligenceService as _HabitsIntelligenceService,
        )

        self.intelligence: HabitsIntelligenceService = _HabitsIntelligenceService(
            backend=backend,
            relationship_service=self.relationships,
            cross_domain_query=cross_domain_query,
            graph_intelligence_service=graph_intelligence_service,
            insight_store=insight_store,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # type: ignore[assignment]  # always passed by bootstrap

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
        self.learning: HabitsLearningService = common.learning

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

        # Event-driven handler service from factory
        self.event_handler: HabitEventHandlerService = common.event_handler

        # Pattern recognition (March 2026)
        self.patterns = HabitsPatternService(habits_core=self.core)
        # HabitsGoalAnalyticsService shelved (2026-03-28)

        # Cross-domain dependency — post-wired in bootstrap
        self.goals_service: Any = None

        self.logger.info(
            "HabitsService facade initialized with 12 sub-services: "
            "core, search, progress, learning, planning, scheduling, relationships, "
            "intelligence, event_handler, completions, patterns, knowledge_intelligence"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Habit entities."""
        return "Entity"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "active",
        sort_by: str = "streak",
    ) -> Result[ListContext]:
        """Get filtered and sorted habits with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid, "all")

        def apply_filters(all_habits: list[Any]) -> list[Any]:
            return apply_entity_filter(all_habits, status_filter, _HABIT_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_habit_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_habit_sort,
            sort_by=sort_by,
            compute_metadata=_compute_habit_metadata,
        )


# Legacy alias removed - class renamed directly to HabitsService
