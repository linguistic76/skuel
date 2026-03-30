"""
Enhanced Goals Service - Facade Pattern
========================================

Goals service facade that delegates to specialized sub-services.

Sub-Services:
- GoalsCoreService: CRUD operations
- GoalsSearchService: Search and discovery (DomainSearchOperations[Goal] protocol)
- GoalsProgressService: Progress tracking and milestones
- GoalsLearningService: Learning path integration
- GoalsSchedulingService: Capacity management and schedule optimization (January 2026)
- UnifiedRelationshipService (GOAPS_CONFIG): Graph relationships and cross-domain links
- GoalsIntelligenceService: pure Cypher analytics
- GoalEventHandlerService: Event-driven reactive handlers
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
from core.services.activity_domain_config import create_common_sub_services
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
from core.services.goals.goal_relationships import GoalRelationships
from core.services.goals_types import GoalFeasibilityAssessment
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

# Unified relationship service
from core.services.relationships import UnifiedRelationshipService
from core.utils.dto_helpers import to_domain_model
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
    from core.ports.query_types import KnowledgePrerequisitesResult, ListContext
    from core.ports.search_protocols import GoalsSearchOperations
    from core.services.goals.goals_ai_service import GoalsAIService
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
    """Compute pre-filter stats from the full goal set."""
    return {
        "total": len(all_goals),
        "active": sum(
            1
            for g in all_goals
            if _get_goal_status_str(g)
            not in (EntityStatus.COMPLETED, EntityStatus.CANCELLED, EntityStatus.ARCHIVED)
        ),
        "completed": sum(1 for g in all_goals if _get_goal_status_str(g) == EntityStatus.COMPLETED),
    }


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


class GoalsService(BaseService[GoalsOperations, Goal]):
    """
    Goals service facade with specialized sub-services.

    This facade:
    1. Delegates to 8 specialized sub-services for core operations
    2. Uses explicit delegation methods (~40 methods) for sub-service access
    3. Retains explicit methods for complex orchestration operations
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core: get_goal, get_user_goals, get_user_items_in_range, activate/pause/complete/archive
    - Progress: calculate_goal_progress_with_context, complete_milestone, etc.
    - Learning: create_goal_with_learning_integration, assess_goal_learning_alignment, etc.
    - Search: search_goals, get_goals_by_status, get_prioritized_goals, etc.
    - Intelligence: get_goal_with_context, get_goal_progress_dashboard, etc.
    - Scheduling: check_goal_capacity, suggest_goal_timeline, assess_goal_achievability, etc.

    Explicit Methods (custom logic):
    - Relationship linking: link_goal_to_habit, link_goal_to_knowledge, link_goal_to_principle
    - Orchestration: create_goal_with_context, generate_tasks_for_goal, assess_goal_feasibility

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        entity_label="Entity",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
    )

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
        return await self.search.get_by_category(category, user_uid, limit)  # type: ignore[call-arg, return-value]

    async def get_goals_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[Goal]]:
        return await self.search.get_by_status(status, limit, user_uid)

    async def search_goals(
        self, query: str, limit: int = 50, user_uid: UserUID | None = None
    ) -> Result[list[Goal]]:
        return await self.search.search(query, limit, user_uid)

    async def get_goals_due_soon(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Goal]]:
        return await self.search.get_due_soon(days_ahead, user_uid, limit)

    async def get_overdue_goals(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Goal]]:
        return await self.search.get_overdue(user_uid, limit)

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
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        insight_store: InsightStore | None = None,
        activity_knowledge_intelligence: Any = None,
        ai_service: GoalsAIService | None = None,
    ) -> None:
        """
        Initialize enhanced goals service with specialized sub-services.

        Args:
            backend: Protocol-based backend for goal operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Goal events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v3.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "goals")

        # Optional AI service (ADR-030: AI features are optional)
        self.ai: GoalsAIService | None = ai_service

        self.graph_intel = graph_intelligence_service
        self.logger = get_logger("skuel.services.goals")  # type: ignore[assignment]  # structlog BoundLogger

        # Initialize 3 common sub-services via factory (core, search, relationships)
        # Note: intelligence is created separately because it needs progress_service
        common = create_common_sub_services(
            domain="goals",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
        )
        self.core = common.core
        self.search: GoalsSearchOperations = common.search  # type: ignore[assignment]  # search service implements callable protocol
        self.relationships: UnifiedRelationshipService = common.relationships

        # Domain-specific sub-services that need relationships
        self.progress = GoalsProgressService(
            backend=backend,
            event_bus=event_bus,
            relationships_service=self.relationships,
        )

        self.learning = GoalsLearningService(
            backend=backend,
            event_bus=event_bus,
            relationships_service=self.relationships,
        )

        # Intelligence requires progress_service - override factory's version
        self.intelligence: GoalsIntelligenceService = GoalsIntelligenceService(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=self.relationships,
            progress_service=self.progress,
        )

        # Event-driven handlers (replaces GoalsRecommendationService)
        self.event_handler = GoalEventHandlerService(
            backend=backend,
            relationship_service=self.relationships,
            event_bus=event_bus,
            insight_store=insight_store,
        )

        # January 2026: Scheduling service for capacity and timeline management
        self.scheduling = GoalsSchedulingService(
            backend=backend,
            progress_service=self.progress,
            event_bus=event_bus,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = activity_knowledge_intelligence

        self.logger.info(
            "GoalsService facade initialized with 9 sub-services: "
            "core, search, progress, learning, scheduling, relationships, "
            "intelligence, event_handler, knowledge_intelligence"
        )

    # ========================================================================
    # KNOWLEDGE INTELLIGENCE - Delegate to ActivityKnowledgeIntelligenceService
    # ========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[dict[str, Any]]:
        """Generate knowledge suggestions from entity patterns."""
        return await self.knowledge_intelligence.get_knowledge_suggestions(user_uid, entity_uid)

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Generate knowledge units from completed entities."""
        return await self.knowledge_intelligence.generate_knowledge_from_entities(
            user_uid, period_days
        )

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]:
        """Analyze knowledge prerequisites for an entity."""
        return await self.knowledge_intelligence.get_knowledge_prerequisites(entity_uid)

    async def get_learning_opportunities(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Discover learning opportunities from entity patterns."""
        return await self.knowledge_intelligence.get_learning_opportunities(user_uid)

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Goal entities."""
        return "Entity"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # GRAPH RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================
    # Note: Simple delegations (Core CRUD, Progress, Learning) auto-generated
    # delegated via explicit method below.

    async def create_user_goal_relationship(
        self, user_uid: UserUID, goal_uid: str, role: str = "owner"
    ) -> Result[bool]:
        """Create User→Goal relationship in graph."""
        properties = {"role": role} if role != "owner" else None
        return await self.relationships.create_user_relationship(user_uid, goal_uid, properties)

    async def link_goal_to_habit(
        self,
        goal_uid: str,
        habit_uid: str,
        weight: float = 1.0,
        contribution_type: str = "consistency",
    ) -> Result[bool]:
        """Link goal to supporting habit with weighted contribution."""
        properties = {"weight": weight, "contribution_type": contribution_type}
        return await self.relationships.create_relationship(
            "supporting_habits", goal_uid, habit_uid, properties
        )

    async def get_goal_habits(self, uid: str) -> Result[list[str]]:
        """Get habits linked to a goal. Delegates to UnifiedRelationshipService."""
        return await self.relationships.get_related_uids("supporting_habits", uid)

    async def unlink_goal_from_habit(self, uid: str, habit_uid: str) -> Result[bool]:
        """Unlink a habit from a goal. Delegates to UnifiedRelationshipService."""
        return await self.relationships.delete_relationship("supporting_habits", uid, habit_uid)

    async def link_goal_to_knowledge(
        self,
        goal_uid: str,
        knowledge_uid: str,
        proficiency_required: str = "intermediate",
        priority: int = 1,
    ) -> Result[bool]:
        """Link goal to required knowledge/skill."""
        return await self.relationships.link_to_knowledge(
            goal_uid,
            knowledge_uid,
            proficiency_required=proficiency_required,
            priority=priority,
        )

    async def link_goal_to_principle(
        self, goal_uid: str, principle_uid: str, alignment_strength: float = 1.0
    ) -> Result[bool]:
        """Link goal to guiding principle/value."""
        return await self.relationships.link_to_principle(
            goal_uid, principle_uid, alignment_strength=alignment_strength
        )

    # Note: get_goal_cross_domain_context, get_goal_with_semantic_context auto-generated
    # delegated via explicit method below.

    async def create_semantic_goal_relationship(
        self,
        goal_uid: str,
        knowledge_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship between goal and knowledge."""
        return await self.relationships.create_semantic_relationship(
            goal_uid, knowledge_uid, semantic_type, confidence, notes
        )

    async def find_goals_requiring_knowledge(
        self, knowledge_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Goal]]:
        """Find goals that require specific knowledge."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=knowledge_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # ORCHESTRATION METHODS - Remain in Facade
    # ========================================================================
    # Note: Intelligence delegations (get_goal_with_context, get_goal_progress_dashboard,
    # get_goal_completion_forecast, get_goal_learning_requirements) auto-generated
    # delegated via explicit method below.

    async def create_goal_with_context(
        self, goal_data: GoalCreateRequest, user_context: UserContext
    ) -> Result[Goal]:
        """
        Create a goal with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Knowledge prerequisites validation
        2. Habit availability validation
        3. Goal creation via learning service
        4. Context invalidation
        """
        # Check knowledge prerequisites
        if goal_data.required_knowledge_uids:
            missing_prereqs = (
                set(goal_data.required_knowledge_uids) - user_context.mastered_knowledge_uids
            )
            if missing_prereqs:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal without required knowledge prerequisites",
                        field="required_knowledge_uids",
                        value=list(missing_prereqs),
                        user_message=f"Please master these knowledge areas first: {', '.join(missing_prereqs)}",
                    )
                )

        # Validate habit availability
        if goal_data.supporting_habit_uids:
            inactive_habits = [
                habit_uid
                for habit_uid in goal_data.supporting_habit_uids
                if habit_uid not in user_context.active_habit_uids
            ]
            if inactive_habits:
                return Result.fail(
                    Errors.validation(
                        message="Cannot create goal with inactive supporting habits",
                        field="supporting_habit_uids",
                        value=inactive_habits,
                        user_message=f"Please activate these habits first: {', '.join(inactive_habits)}",
                    )
                )

        # Create goal through learning service (handles DTO creation)
        result = await self.learning.create_goal_with_learning_integration(goal_data, None)
        if result.is_error:
            return result

        # Note: User context invalidation now happens via event-driven architecture
        # GoalCreated event → invalidate_context_on_goal_event() → user_service.invalidate_context()

        goal = result.value
        # GRAPH-NATIVE: Get counts from goal_data (input) since relationships stored in graph
        habit_count = len(goal_data.supporting_habit_uids) if goal_data.supporting_habit_uids else 0
        knowledge_count = (
            len(goal_data.required_knowledge_uids) if goal_data.required_knowledge_uids else 0
        )
        self.logger.info(
            "Created goal %s with %d habits, %d knowledge requirements",
            goal.uid,
            habit_count,
            knowledge_count,
        )

        return Result.ok(goal)

    async def generate_tasks_for_goal(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate task suggestions for achieving a goal (orchestration method).

        This combines goal data with user context to generate:
        - Milestone tasks
        - Knowledge acquisition tasks
        - Habit reinforcement tasks
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # GRAPH-NATIVE: Fetch relationships from graph
        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        task_suggestions = []

        # Generate milestone tasks
        if goal.milestones:
            for i, milestone in enumerate(goal.milestones):
                if not milestone.is_completed:
                    task = {
                        "title": f"Complete: {milestone.title}",
                        "description": milestone.description or "",
                        "fulfills_goal_uid": goal_uid,
                        "goal_progress_contribution": 100.0 / len(goal.milestones),
                        "priority": Priority.HIGH
                        if goal.days_remaining() < 30
                        else Priority.MEDIUM,
                        "tags": ["goal", f"milestone-{i + 1}"],
                    }
                    task_suggestions.append(task)

        # Generate knowledge acquisition tasks
        if rels.required_knowledge_uids:
            for knowledge_uid in rels.required_knowledge_uids:
                if knowledge_uid not in user_context.mastered_knowledge_uids:
                    task = {
                        "title": f"Learn: {knowledge_uid}",
                        "fulfills_goal_uid": goal_uid,
                        "applies_knowledge_uids": [knowledge_uid],
                        "knowledge_mastery_check": True,
                        "priority": Priority.HIGH,
                        "tags": ["learning", "goal"],
                    }
                    task_suggestions.append(task)

        # Generate habit reinforcement tasks
        if rels.supporting_habit_uids:
            for habit_uid in rels.supporting_habit_uids:
                if user_context.habit_streaks.get(habit_uid, 0) < 7:
                    task = {
                        "title": f"Strengthen habit: {habit_uid}",
                        "reinforces_habit_uid": habit_uid,
                        "fulfills_goal_uid": goal_uid,
                        "habit_streak_maintainer": True,
                        "priority": Priority.MEDIUM,
                        "recurring": True,
                        "tags": ["habit", "goal"],
                    }
                    task_suggestions.append(task)

        self.logger.info(
            "Generated %d task suggestions for goal %s", len(task_suggestions), goal_uid
        )

        return Result.ok(task_suggestions)

    async def assess_goal_feasibility(
        self, goal: Goal, user_context: UserContext
    ) -> Result[GoalFeasibilityAssessment]:
        """
        Assess if a goal is feasible given user's context (orchestration method).

        Combines checks across:
        - Knowledge prerequisites
        - Habit support
        - Current workload
        """
        # GRAPH-NATIVE: Fetch goal relationships from graph
        rels = await GoalRelationships.fetch(goal.uid, self.relationships)

        # Mutable accumulation variables
        is_feasible_flag = True
        confidence_score = 0.8
        blockers_list: list[str] = []
        enablers_list: list[str] = []
        estimated_date = None

        # Check knowledge prerequisites (from graph relationships)
        if rels.required_knowledge_uids:
            missing = set(rels.required_knowledge_uids) - user_context.mastered_knowledge_uids
            if missing:
                blockers_list.append(f"Missing {len(missing)} knowledge prerequisites")
                is_feasible_flag = False
                confidence_score *= 0.5

        # Check habit support (from graph relationships)
        if rels.supporting_habit_uids:
            active_habits = [
                h for h in rels.supporting_habit_uids if h in user_context.active_habit_uids
            ]
            if len(active_habits) < len(rels.supporting_habit_uids) / 2:
                blockers_list.append("Insufficient habit support")
                confidence_score *= 0.7
            else:
                enablers_list.append(f"{len(active_habits)} supporting habits active")

        # Check workload
        current_workload = user_context.current_workload_score
        if current_workload > 0.8:
            blockers_list.append("Current workload too high")
            is_feasible_flag = False

        # Estimate completion
        if is_feasible_flag and goal.target_date:
            estimated_date = goal.target_date

        # Build immutable result using frozen dataclass
        assessment = GoalFeasibilityAssessment(
            is_feasible=is_feasible_flag,
            confidence=confidence_score,
            blockers=blockers_list,
            enablers=enablers_list,
            estimated_completion_date=estimated_date,
        )

        return Result.ok(assessment)

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
    # and Search operations (list_goal_categories, get_goals_by_status, search_goals, etc.)
    # delegated via explicit method below.
