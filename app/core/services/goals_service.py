"""
Enhanced Goals Service - Facade Pattern
========================================

Goals service facade that delegates to specialized sub-services.

Architecture: Shell delegates to 2 facade mixins in the goals/ package:
  _orchestration_mixin.py  — create_goal_with_context, generate_tasks_for_goal,
                              assess_goal_feasibility
  _relationship_mixin.py   — link_goal_to_habit/knowledge/principle,
                              create_semantic_goal_relationship, etc.

Sub-Services:
- GoalsCoreService: CRUD operations
- GoalsSearchService: Search and discovery (DomainSearchOperations[Goal] protocol)
- GoalsProgressService: Progress tracking and milestones
- GoalsLearningService: Learning path integration
- GoalsSchedulingService: Capacity management and schedule optimization (January 2026)
- UnifiedRelationshipService (GOAPS_CONFIG): Graph relationships and cross-domain links
- GoalsIntelligenceService: pure Cypher analytics (5 intelligence mixins)
- GoalEventHandlerService: Event-driven reactive handlers

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, Priority
from core.models.enums.goal_enums import GoalTimeframe, GoalType
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import GoalsOperations
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context

# Import sub-services
from core.services.goals import (
    GoalEventHandlerService,
    GoalsIntelligenceService,
    GoalsLearningService,
    GoalsProgressService,
    GoalsSchedulingService,
)
from core.services.goals._orchestration_mixin import _OrchestrationMixin
from core.services.goals._relationship_mixin import _RelationshipMixin
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import KnowledgeIntelligenceDelegationMixin

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_stats import compute_goal_stats
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    PRIORITY_STRING_SORT_ORDER,
    get_created_at_attr,
    get_current_value,
    make_priority_string_getter,
)
from core.utils.type_converters import get_enum_attr_str

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.enums import Domain
    from core.models.goal.goal_request import GoalCreateRequest
    from core.models.graph_context import GraphContext
    from core.models.pathways.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import GoalsSearchOperations
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.goals.goals_ai_service import GoalsAIService
    from core.services.goals.goals_core_service import GoalsCoreService
    from core.services.goals.goals_scheduling_service import (
        AchievabilityResult,
        GoalCapacityResult,
        GoalSequenceItem,
        TimelineSuggestion,
    )
    from core.services.goals_types import GoalLearningProgress
    from core.services.insight.insight_store import InsightStore
    from core.services.user import UserContext


def _get_goal_status_str(goal: Any) -> str:
    """Extract status as lowercase string, handling both enum and string."""
    return get_enum_attr_str(goal, "status", "active")


def _get_goal_priority_str(goal: Any) -> str:
    """Extract priority as lowercase string, handling both enum and string."""
    return get_enum_attr_str(goal, "priority", "medium")


def _get_goal_target_date(goal: Any) -> date:
    """Extract target_date as date object, handling both date and string."""
    target = getattr(goal, "target_date", None)
    if target is None:
        return date.max
    if isinstance(target, date):
        return target
    if isinstance(target, str):
        try:
            return date.fromisoformat(target)
        except ValueError:
            pass
    return date.max


# Goal categories — the knowledge categorization subset of Domain enum.
_GOAL_CATEGORIES: list[str] = [
    "business",
    "health",
    "education",
    "personal",
    "tech",
    "creative",
    "social",
    "research",
]


def _compute_goal_metadata(_all_goals: list[Any]) -> dict[str, Any]:
    """Compute goal metadata — categories for UI dropdowns."""
    return {"categories": _GOAL_CATEGORIES}


def _compute_goal_stats(all_goals: list[Any]) -> dict[str, int | float]:
    """Dict projection of GoalStats for the cross-domain ListContext contract."""
    s = compute_goal_stats(all_goals)
    return {"total": s.total, "active": s.active, "completed": s.completed}


def _is_goal_active(g: Any) -> bool:
    """Filter predicate: goal is not in a terminal state."""
    return _get_goal_status_str(g) not in (
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.ARCHIVED,
    )


def _is_goal_completed(g: Any) -> bool:
    """Filter predicate: goal is completed."""
    return _get_goal_status_str(g) == EntityStatus.COMPLETED


_GOAL_FILTER_CONFIG: FilterConfig = {
    "active": _is_goal_active,
    "completed": _is_goal_completed,
}

_GOAL_SORT_CONFIG: SortConfig = {
    "target_date": (_get_goal_target_date, False),
    "priority": (
        make_priority_string_getter(PRIORITY_STRING_SORT_ORDER, _get_goal_priority_str),
        False,
    ),
    "progress": (get_current_value, True),
    "created_at": (get_created_at_attr, True),
}


def _apply_goal_sort(goals: list[Any], sort_by: str = "target_date") -> list[Any]:
    """Sort goals using declarative config."""
    return apply_entity_sort(goals, sort_by, _GOAL_SORT_CONFIG, "target_date")


class GoalsService(
    _OrchestrationMixin,
    _RelationshipMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService[GoalsOperations, Goal],
):
    """
    Goals service facade with specialized sub-services.

    Architecture: Shell delegates to 2 facade mixins + 8 sub-services:
      _OrchestrationMixin  — create_goal_with_context, generate_tasks_for_goal,
                              assess_goal_feasibility
      _RelationshipMixin   — link_goal_to_habit/knowledge/principle,
                              create_semantic_goal_relationship, etc.

    Delegations (explicit methods):
    - Core: get_goal, get_user_goals, get_user_items_in_range, activate/pause/complete/archive
    - Progress: calculate_goal_progress_with_context, complete_milestone, etc.
    - Learning: create_goal_with_learning_integration, assess_goal_learning_alignment, etc.
    - Search: get_goals_by_status, get_prioritized_goals, get_upcoming, get_overdue, etc.
    - Intelligence: get_goal_with_context, get_goal_progress_dashboard, etc.
    - Scheduling: check_goal_capacity, suggest_goal_timeline, assess_goal_achievability, etc.

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    - Facade mixins extracted (April 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
    )

    # ========================================================================
    # CLASS-LEVEL TYPE ANNOTATIONS
    # ========================================================================
    core: GoalsCoreService
    search: GoalsSearchOperations  # type: ignore[assignment]  # search service implements callable protocol
    progress: GoalsProgressService
    scheduling: GoalsSchedulingService
    learning: GoalsLearningService
    relationships: UnifiedRelationshipService
    intelligence: GoalsIntelligenceService
    event_handler: GoalEventHandlerService
    ai: GoalsAIService | None

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_goal(self, goal_uid: str) -> Result[Goal]:
        return await self.core.get_goal(goal_uid)

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        return await self.core.get_user_goals(user_uid)

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[Goal]]:
        return await self.core.get_user_items_in_range(
            user_uid, start_date, end_date, include_completed
        )

    async def activate_goal(self, uid: str) -> Result[bool]:
        return await self.core.activate_goal(uid)

    async def pause_goal(
        self, uid: str, reason: str = "Paused", until_date: str | None = None
    ) -> Result[bool]:
        return await self.core.pause_goal(uid, reason, until_date)

    async def complete_goal(
        self, uid: str, completion_notes: str = "", completion_date: str | None = None
    ) -> Result[bool]:
        return await self.core.complete_goal(uid, completion_notes, completion_date)

    async def archive_goal(self, uid: str, reason: str = "Archived") -> Result[bool]:
        return await self.core.archive_goal(uid, reason)

    async def set_status(self, uid: str, new_status: str) -> Result[Goal]:
        """Apply a status transition and return the refreshed goal.

        Why: ``activate_goal`` / ``complete_goal`` / ``archive_goal`` each carry
        different side effects (progress_percentage, completion_date, archive
        metadata). Centralising the dispatch here keeps transition semantics in
        the domain service so every caller — route, CLI, future batch job —
        applies them uniformly.
        """
        if new_status == EntityStatus.ACTIVE.value:
            transition: Result[bool] = await self.activate_goal(uid)
        elif new_status == EntityStatus.COMPLETED.value:
            transition = await self.complete_goal(uid)
        elif new_status == EntityStatus.ARCHIVED.value:
            transition = await self.archive_goal(uid)
        elif new_status == EntityStatus.CANCELLED.value:
            transition = await self.cancel_goal(uid)
        else:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid goal status: {new_status}",
                    field="status",
                    value=new_status,
                )
            )

        if transition.is_error:
            return Result.fail(transition)

        return await self.get_goal(uid)

    async def cancel_goal(self, uid: str) -> Result[bool]:
        """Cancel a goal, rejecting the request if the goal has active tasks.

        The abandonment guard is the only valid entry point for CANCELLED status.
        Placing it here (facade) allows it to coordinate across the task and goal
        domains without leaking cross-domain dependencies into GoalsCoreService.
        """
        count_result = await self.cross_domain_query.count_active_tasks_for_goal(EntityUID(uid))
        if count_result.is_error:
            self.logger.warning(
                f"Failed to check active tasks for goal {uid}: {count_result.expect_error()}"
            )
        elif count_result.value.count > 0:
            active_task_count = count_result.value.count
            return Result.fail(
                Errors.validation(
                    message=f"Cannot abandon goal with {active_task_count} active task(s). Complete or reassign tasks first.",
                    field="status",
                    value=EntityStatus.CANCELLED.value,
                )
            )
        result = await self.core.update(uid, {"status": EntityStatus.CANCELLED.value})
        return Result.ok(True) if result.is_ok else Result.fail(result)

    async def create_goal(self, goal_request: GoalCreateRequest, user_uid: UserUID) -> Result[Goal]:
        return await self.core.create_goal(goal_request, user_uid)

    # Progress delegations
    async def calculate_goal_progress_with_context(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        return await self.progress.calculate_goal_progress_with_context(goal_uid, user_context)

    async def complete_milestone(
        self, goal_uid: str, milestone_index: int, user_context: UserContext
    ) -> Result[Goal]:
        return await self.progress.complete_milestone(goal_uid, milestone_index, user_context)

    async def update_goal_from_habit_progress(
        self, goal_uid: str, habit_uid: str, new_streak: int
    ) -> Result[Goal]:
        return await self.progress.update_goal_from_habit_progress(goal_uid, habit_uid, new_streak)

    async def update_goal_progress(
        self, uid: str, progress_value: float, notes: str = "", update_date: str | None = None
    ) -> Result[dict[str, Any]]:
        return await self.progress.update_goal_progress(uid, progress_value, notes, update_date)

    async def get_goal_progress(self, uid: str, period: str = "month") -> Result[dict[str, Any]]:
        return await self.progress.get_goal_progress(uid, period)

    async def create_goal_milestone(
        self, uid: str, milestone_title: str, target_date: str, description: str = ""
    ) -> Result[bool]:
        return await self.progress.create_goal_milestone(
            uid, milestone_title, target_date, description
        )

    async def get_goal_milestones(self, uid: str) -> Result[list[dict[str, Any]]]:
        return await self.progress.get_goal_milestones(uid)

    # Learning delegations
    async def create_goal_with_learning_integration(
        self, goal_request: GoalCreateRequest, learning_position: LpPosition | None = None
    ) -> Result[Goal]:
        return await self.learning.create_goal_with_learning_integration(
            goal_request, learning_position
        )

    async def assess_goal_learning_alignment(
        self, goal_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        return await self.learning.assess_goal_learning_alignment(goal_uid, learning_position)

    async def suggest_learning_aligned_goals(
        self, learning_position: LpPosition, goal_domain: Domain | None = None
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_aligned_goals(learning_position, goal_domain)

    async def get_learning_supporting_goals(
        self, user_uid: UserUID, learning_position: LpPosition
    ) -> Result[list[Goal]]:
        return await self.learning.get_learning_supporting_goals(user_uid, learning_position)

    async def track_goal_learning_progress(
        self, goal_uid: str, learning_position: LpPosition
    ) -> Result[GoalLearningProgress]:
        return await self.learning.track_goal_learning_progress(goal_uid, learning_position)

    async def get_goals_needing_habits(self, user_context: UserContext) -> Result[list[Goal]]:
        return await self.learning.get_goals_needing_habits(user_context)

    async def get_goals_blocked_by_knowledge(self, user_context: UserContext) -> Result[list[Goal]]:
        return await self.learning.get_goals_blocked_by_knowledge(user_context)

    # Relationship delegations
    async def get_goal_cross_domain_context(
        self, entity_uid: EntityUID, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_cross_domain_context(entity_uid, depth, min_confidence)

    async def get_goal_with_semantic_context(
        self,
        uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_with_semantic_context(
            uid, min_confidence, semantic_types
        )

    # Intelligence delegations
    async def get_goal_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Goal, GraphContext]]:
        return await self.intelligence.get_goal_with_context(uid, depth)

    async def get_goal_progress_dashboard(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_goal_progress_dashboard(uid, min_confidence)

    async def get_goal_completion_forecast(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_goal_completion_forecast(uid, depth, min_confidence)

    async def get_goal_learning_requirements(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_goal_learning_requirements(uid, depth, min_confidence)

    # Search delegations
    async def list_goal_categories(self, user_uid: UserUID) -> Result[list[str]]:
        return await self.search.list_user_categories(user_uid)

    async def list_all_goal_categories(self) -> Result[list[str]]:
        return await self.search.list_all_categories()

    async def get_goals_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Goal]]:
        return await self.search.get_by_category(category, user_uid, limit)

    async def get_goals_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[Goal]]:
        return await self.search.get_by_status(status, limit, user_uid)

    async def get_upcoming(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Goal]]:
        return await self.search.get_upcoming(days_ahead, user_uid, limit)

    async def get_overdue(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Goal]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Goal]]:
        return await self.search.get_active(user_uid, limit)

    async def get_goals_by_domain(self, domain: Domain, limit: int = 100) -> Result[list[Goal]]:
        return await self.search.get_by_domain(domain, limit)

    async def get_prioritized_goals(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Goal]]:
        return await self.search.get_prioritized(user_context, limit)

    # Scheduling delegations
    async def check_goal_capacity(
        self,
        user_uid: UserUID,
        proposed_type: GoalType = GoalType.OUTCOME,
        proposed_timeframe: GoalTimeframe = GoalTimeframe.QUARTERLY,
        proposed_priority: Priority = Priority.MEDIUM,
        max_active_goals: int = 5,
    ) -> Result[GoalCapacityResult]:
        return await self.scheduling.check_goal_capacity(
            user_uid, proposed_type, proposed_timeframe, proposed_priority, max_active_goals
        )

    async def suggest_goal_timeline(
        self,
        user_uid: UserUID,
        goal_type: GoalType,
        timeframe: GoalTimeframe,
        complexity_factors: list[str] | None = None,
    ) -> Result[TimelineSuggestion]:
        return await self.scheduling.suggest_goal_timeline(
            user_uid, goal_type, timeframe, complexity_factors
        )

    async def assess_goal_achievability(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[AchievabilityResult]:
        return await self.scheduling.assess_goal_achievability(goal_uid, user_context)

    async def get_schedule_aware_next_goal(self, user_context: UserContext) -> Result[Goal | None]:
        return await self.scheduling.get_schedule_aware_next_goal(user_context)

    async def optimize_goal_sequencing(
        self, user_uid: UserUID, goal_uids: list[str]
    ) -> Result[list[GoalSequenceItem]]:
        return await self.scheduling.optimize_goal_sequencing(user_uid, goal_uids)

    async def get_goal_load_by_timeframe(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        return await self.scheduling.get_goal_load_by_timeframe(user_uid)

    async def create_goal_with_scheduling_context(
        self, goal_data: GoalCreateRequest, user_context: UserContext, check_capacity: bool = True
    ) -> Result[Goal]:
        return await self.scheduling.create_goal_with_context(
            goal_data, user_context, check_capacity
        )

    async def create_goal_with_learning_scheduling(
        self,
        goal_data: GoalCreateRequest,
        learning_position: LpPosition | None,
        user_context: UserContext,
    ) -> Result[Goal]:
        return await self.scheduling.create_goal_with_learning_context(
            goal_data, learning_position, user_context
        )

    def __init__(
        self,
        backend: GoalsOperations,
        graph_intel: GraphIntelligenceService,
        cross_domain_query: CrossDomainQueryService,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: KnowledgeIntelligenceOperations | None = None,
        ai_service: GoalsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced goals service with specialized sub-services.

        Args:
            backend: Protocol-based backend for goal operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Goal events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v3.2.0 - December 2025):
            Made graph_intel REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "goals")

        # Optional AI service (ADR-030: AI features are optional)
        self.ai: GoalsAIService | None = ai_service

        self.graph_intel = graph_intel
        self.cross_domain_query = cross_domain_query
        self.logger = get_logger("skuel.services.goals")  # structlog BoundLogger

        # Initialize core, search, relationships, event_handler, learning, and
        # knowledge_intelligence via factory. intelligence is skipped because it
        # needs progress_service, which is created below.
        common: CommonSubServices[
            GoalsCoreService, GoalsSearchOperations, GoalsIntelligenceService
        ] = create_common_sub_services(
            domain="goals",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
            insight_store=insight_store,
            skip={"intelligence"},
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        assert common.core is not None  # 'core' not in skip
        assert common.search is not None  # 'search' not in skip
        assert common.relationships is not None  # 'relationships' not in skip
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships

        # Domain-specific sub-services that need relationships
        self.progress = GoalsProgressService(
            backend=backend,
            event_bus=event_bus,
            relationship_service=self.relationships,
        )

        # Learning service from factory
        self.learning: GoalsLearningService = common.learning

        # Intelligence requires progress_service — created manually (skipped in factory)
        self.intelligence: GoalsIntelligenceService = GoalsIntelligenceService(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=self.relationships,
            progress_service=self.progress,
            insight_store=insight_store,
        )

        # Event-driven handlers from factory
        self.event_handler: GoalEventHandlerService = common.event_handler

        # January 2026: Scheduling service for capacity and timeline management
        self.scheduling = GoalsSchedulingService(
            backend=backend,
            progress_service=self.progress,
            event_bus=event_bus,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = common.knowledge_intelligence  # always passed by bootstrap

        self.logger.info(
            "GoalsService facade initialized with 9 sub-services: "
            "core, search, progress, learning, scheduling, relationships, "
            "intelligence, event_handler, knowledge_intelligence"
        )

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # Note: Graph relationship methods provided by _RelationshipMixin
    # Note: Orchestration methods provided by _OrchestrationMixin

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "active",
        sort_by: str = "target_date",
    ) -> Result[ListContext]:
        """Get filtered and sorted goals with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid, "all")

        def apply_filters(all_goals: list[Any]) -> list[Any]:
            return apply_entity_filter(all_goals, status_filter, _GOAL_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_goal_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_goal_sort,
            sort_by=sort_by,
            compute_metadata=_compute_goal_metadata,
        )

    # Note: Status operations (activate_goal, pause_goal, complete_goal, archive_goal)
    # and Search operations (list_goal_categories, get_goals_by_status, get_upcoming,
    # get_overdue, get_active, etc.) delegated via explicit methods above.
