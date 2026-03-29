"""
Enhanced Choices Service - Facade Pattern
==========================================

Choices service facade that delegates to specialized sub-services.

Sub-Services:
- ChoicesCoreService: CRUD operations
- ChoicesSearchService: Search and discovery (DomainSearchOperations[Choice] protocol)
- ChoicesLearningService: Learning path guidance and integration
- UnifiedRelationshipService (CHOICES_CONFIG): Cross-domain links and semantic connections
- ChoicesIntelligenceService: Pure Cypher analytics + decision pattern analysis
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.enums import EntityStatus
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import ChoicesOperations
from core.services.activity_domain_config import CommonSubServices, create_common_sub_services
from core.services.base_service import BaseService

# Import sub-services
from core.services.choices import ChoicesLearningService
from core.services.choices.choice_event_handler_service import ChoiceEventHandlerService
from core.services.domain_config import create_activity_domain_config
from core.services.filtered_context import build_filtered_context

# Unified relationship service
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships import UnifiedRelationshipService
from core.utils.list_helpers import FilterConfig, SortConfig, apply_entity_filter, apply_entity_sort
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    PRIORITY_STRING_SORT_ORDER,
    get_created_at_attr,
    get_decision_deadline,
    make_priority_string_getter,
)
from core.utils.type_converters import get_enum_attr_str

if TYPE_CHECKING:
    from datetime import date

    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.choice.choice_request import ChoiceCreateRequest
    from core.models.entity_requests import EntityUpdateRequest
    from core.models.enums import Domain, Priority
    from core.models.graph_context import GraphContext
    from core.models.pathways.lp_position import LpPosition
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.query_types import KnowledgePrerequisitesResult, ListContext
    from core.ports.search_protocols import ChoicesSearchOperations
    from core.services.choices.choices_ai_service import ChoicesAIService
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
    from core.services.choices.choices_types import ChoiceImpactAnalysis, DecisionIntelligence
    from core.services.user import UserContext


class ChoicesAnalyticsContext(TypedDict):
    """Return type for ChoicesService.get_analytics_context()."""

    total_choices: int
    total_decisions: int
    satisfaction_rate: float
    on_time_rate: float
    outcomes: list[dict[str, Any]]


def _get_choice_enum_value(obj: Any, attr: str, default: str = "") -> str:
    """Extract value from attribute (handles both enum and string)."""
    return get_enum_attr_str(obj, attr, default)


def _get_choice_priority(c: Any) -> str:
    """Extract priority string for sort key (SKUEL012: named function, no lambda)."""
    return get_enum_attr_str(c, "priority", "medium")


def _compute_choice_stats(all_choices: list[Any]) -> dict[str, int | float]:
    """Compute pre-filter stats from the full choice set."""
    pending = sum(1 for c in all_choices if _get_choice_enum_value(c, "status") == "pending")
    return {
        "total": len(all_choices),
        "active": pending,
        "pending": pending,
        "decided": sum(1 for c in all_choices if _get_choice_enum_value(c, "status") == "decided"),
    }


def _is_choice_pending(c: Any) -> bool:
    """Filter predicate: choice is pending."""
    return _get_choice_enum_value(c, "status") == "pending"


def _is_choice_decided(c: Any) -> bool:
    """Filter predicate: choice is decided."""
    return _get_choice_enum_value(c, "status") == "decided"


def _is_choice_implemented(c: Any) -> bool:
    """Filter predicate: choice is implemented."""
    return _get_choice_enum_value(c, "status") == "implemented"


_CHOICE_FILTER_CONFIG: FilterConfig = {
    "pending": _is_choice_pending,
    "decided": _is_choice_decided,
    "implemented": _is_choice_implemented,
}

_CHOICE_SORT_CONFIG: SortConfig = {
    "deadline": (get_decision_deadline, False),
    "priority": (
        make_priority_string_getter(PRIORITY_STRING_SORT_ORDER, _get_choice_priority),
        False,
    ),
    "created_at": (get_created_at_attr, True),
}


def _apply_choice_sort(choices: list[Any], sort_by: str = "deadline") -> list[Any]:
    """Sort choices using declarative config."""
    return apply_entity_sort(choices, sort_by, _CHOICE_SORT_CONFIG, "deadline")


class ChoicesService(BaseService["ChoicesOperations", Choice]):
    """
    Choices service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses explicit delegation methods (~26 methods) for sub-service access
    3. Retains explicit methods for complex operations
    4. Provides clean separation of concerns

    Delegations (explicit methods):
    - Core: get_choice, get_user_choices, get_user_items_in_range
    - Learning: create_choice_with_learning_guidance, suggest_learning_aligned_choices, etc.
    - Search: search_choices, get_choices_by_status, get_pending_choices, etc.
    - Intelligence: get_choice_with_context, get_decision_intelligence, get_decision_patterns, etc.

    Explicit Methods (custom logic):
    - Option management: add_option, update_option, remove_option, make_decision
    - Relationship linking: link_choice_to_goal, link_choice_to_habit, link_choice_to_principle
    - Semantic relationships: create_semantic_choice_relationship, find_choices_aligned_with_principle

    SKUEL Architecture:
    - Uses explicit delegation methods (February 2026)
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=ChoiceDTO,
        model_class=Choice,
        domain_name="choices",
        date_field="decision_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # ========================================================================
    # DELEGATION METHODS
    # ========================================================================

    # Core CRUD delegations
    async def get_choice(self, choice_uid: str) -> Result[Choice]:
        return await self.core.get_choice(choice_uid)

    async def get_user_choices(self, user_uid: UserUID) -> Result[list[Choice]]:
        return await self.core.get_user_choices(user_uid)

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Choice]]:
        return await self.core.get_user_items_in_range(
            user_uid, start_date, end_date, include_completed
        )

    # Learning delegations
    async def create_choice_with_learning_guidance(
        self,
        choice_request: ChoiceCreateRequest,
        user_uid: UserUID,
        learning_position: LpPosition | None = None,
    ) -> Result[Choice]:
        return await self.learning.create_choice_with_learning_guidance(
            choice_request, user_uid, learning_position
        )

    async def get_learning_informed_guidance(
        self,
        choice_description: str,
        learning_position: LpPosition,
        choice_options: list[str] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.learning.get_learning_informed_guidance(
            choice_description, learning_position, choice_options
        )

    async def track_choice_learning_outcomes(
        self,
        choice_uid: str,
        learning_position: LpPosition,
        _outcome_data: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.learning.track_choice_learning_outcomes(
            choice_uid, learning_position, _outcome_data
        )

    async def suggest_learning_aligned_choices(
        self,
        learning_position: LpPosition,
        choice_domain: Domain | None = None,
        urgency_level: Priority | None = None,
    ) -> Result[list[dict[str, Any]]]:
        return await self.learning.suggest_learning_aligned_choices(
            learning_position, choice_domain, urgency_level
        )

    # Relationship delegations
    async def get_choice_cross_domain_context(
        self,
        entity_uid: EntityUID,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_cross_domain_context(entity_uid, depth, min_confidence)

    async def get_choice_with_semantic_context(
        self,
        uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
    ) -> Result[dict[str, Any]]:
        return await self.relationships.get_with_semantic_context(
            uid, min_confidence, semantic_types
        )

    # Intelligence delegations
    async def get_choice_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Choice, GraphContext]]:
        return await self.intelligence.get_choice_with_context(uid, depth)

    async def get_decision_intelligence(
        self, choice_uid: str, min_confidence: float = 0.7, depth: int = 2
    ) -> Result[DecisionIntelligence]:
        return await self.intelligence.get_decision_intelligence(choice_uid, min_confidence, depth)

    async def analyze_choice_impact(
        self, choice_uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[ChoiceImpactAnalysis]:
        return await self.intelligence.analyze_choice_impact(choice_uid, depth, min_confidence)

    async def get_decision_patterns(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_decision_patterns(user_uid, days)

    async def get_choice_quality_correlations(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_choice_quality_correlations(user_uid, days)

    async def get_domain_decision_patterns(
        self, user_uid: UserUID, days: int = 90
    ) -> Result[dict[str, Any]]:
        return await self.intelligence.get_domain_decision_patterns(user_uid, days)

    # Search delegations
    async def search_choices(
        self, query: str, limit: int = 50, user_uid: UserUID | None = None
    ) -> Result[list[Choice]]:
        return await self.search.search(query, limit, user_uid)

    async def get_choices_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[Choice]]:
        return await self.search.get_by_status(status, limit, user_uid)

    async def get_choices_by_domain(self, domain: Any, limit: int = 100) -> Result[list[Choice]]:
        return await self.search.get_by_domain(domain, limit)

    async def get_pending_choices(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_pending(user_uid, limit)

    async def get_choices_due_soon(
        self, days_ahead: int = 7, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_due_soon(days_ahead, user_uid, limit)

    async def get_overdue_choices(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_overdue(user_uid, limit)

    async def get_choices_by_urgency(
        self, urgency: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Choice]]:
        return await self.search.get_by_urgency(urgency, user_uid, limit)

    async def get_choices_needing_decision(
        self, user_uid: UserUID, deadline_days: int = 7
    ) -> Result[list[Choice]]:
        return await self.search.get_needing_decision(user_uid, deadline_days)

    async def get_prioritized_choices(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Choice]]:
        return await self.search.get_prioritized(user_context, limit)

    async def list_choice_categories(self, user_uid: UserUID) -> Result[list[str]]:
        return await self.search.list_user_categories(user_uid)

    async def list_all_choice_categories(self) -> Result[list[str]]:
        return await self.search.list_all_categories()

    def __init__(
        self,
        backend: ChoicesOperations,
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        insight_store: Any = None,
        activity_knowledge_intelligence: Any = None,
        ai_service: ChoicesAIService | None = None,
    ) -> None:
        """
        Initialize enhanced choices service with specialized sub-services.

        Args:
            backend: Protocol-based backend for choice operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Choice operations trigger domain events which invalidate context.

        Migration Note (v2.1.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "choices")

        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        # Optional AI service (ADR-030: AI features are optional)
        self.ai: ChoicesAIService | None = ai_service
        self.logger = get_logger("skuel.services.choices")  # type: ignore[assignment]  # structlog BoundLogger

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[ChoicesIntelligenceService] = create_common_sub_services(
            domain="choices",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        self.core = common.core
        self.search: ChoicesSearchOperations = common.search  # type: ignore[assignment]  # search service implements callable protocol
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: ChoicesIntelligenceService = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.learning = ChoicesLearningService(backend=backend)
        self.event_handler = ChoiceEventHandlerService(
            backend=backend,
            relationship_service=self.relationships,
            insight_store=insight_store,
            event_bus=event_bus,
        )

        # Knowledge intelligence (shared singleton — domain-agnostic)
        self.knowledge_intelligence = activity_knowledge_intelligence

        self.logger.info(
            "ChoicesService facade initialized with 7 sub-services: "
            "core, search, learning, relationships, intelligence, "
            "event_handler, knowledge_intelligence"
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
        """Return the graph label for Choice entities."""
        return "Choice"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to ChoicesCoreService
    # ========================================================================
    # Note: Simple delegations (get_choice, get_user_choices, get_user_items_in_range)
    # delegated via explicit methods below.

    async def create_choice(
        self, choice_request: ChoiceCreateRequest, user_uid: UserUID
    ) -> Result[Choice]:
        """Create a basic choice.

        Args:
            choice_request: Choice creation request
            user_uid: User UID (REQUIRED - fail-fast philosophy)
        """
        return await self.core.create_choice(choice_request, user_uid)

    async def update_choice(
        self, choice_uid: str, choice_update: EntityUpdateRequest
    ) -> Result[Choice]:
        """Update a choice."""
        return await self.core.update_choice(choice_uid, choice_update)

    async def delete_choice(self, choice_uid: str) -> Result[bool]:
        """Delete a choice."""
        return await self.core.delete_choice(choice_uid)

    async def find_choices(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Choice]]:
        """Find choices with filters and pagination."""
        return await self.core.find_choices(filters, limit, offset, order_by, order_desc)

    async def count_choices(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """Count choices matching filters."""
        return await self.core.count_choices(filters)

    # ========================================================================
    # OPTION MANAGEMENT - Delegate to ChoicesCoreService
    # ========================================================================

    async def add_option(
        self,
        choice_uid: str,
        title: str,
        description: str,
        feasibility_score: float = 0.5,
        risk_level: float = 0.5,
        potential_impact: float = 0.5,
        resource_requirement: float = 0.5,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """Add a new option to an existing choice."""
        return await self.core.add_option(
            choice_uid=choice_uid,
            title=title,
            description=description,
            feasibility_score=feasibility_score,
            risk_level=risk_level,
            potential_impact=potential_impact,
            resource_requirement=resource_requirement,
            estimated_duration=estimated_duration,
            dependencies=dependencies,
            tags=tags,
        )

    async def update_option(
        self,
        choice_uid: str,
        option_uid: str,
        title: str | None = None,
        description: str | None = None,
        feasibility_score: float | None = None,
        risk_level: float | None = None,
        potential_impact: float | None = None,
        resource_requirement: float | None = None,
        estimated_duration: int | None = None,
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Result[Choice]:
        """Update an existing option in a choice."""
        return await self.core.update_option(
            choice_uid=choice_uid,
            option_uid=option_uid,
            title=title,
            description=description,
            feasibility_score=feasibility_score,
            risk_level=risk_level,
            potential_impact=potential_impact,
            resource_requirement=resource_requirement,
            estimated_duration=estimated_duration,
            dependencies=dependencies,
            tags=tags,
        )

    async def remove_option(
        self,
        choice_uid: str,
        option_uid: str,
    ) -> Result[Choice]:
        """Remove an option from a choice."""
        return await self.core.remove_option(choice_uid=choice_uid, option_uid=option_uid)

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Choice]:
        """Make a decision on a choice (select an option)."""
        return await self.core.make_decision(
            choice_uid=choice_uid,
            selected_option_uid=selected_option_uid,
            decision_rationale=decision_rationale,
            confidence=confidence,
        )

    # ========================================================================
    # CROSS-DOMAIN RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================
    # Note: Learning delegations (create_choice_with_learning_guidance, etc.)
    # delegated via explicit methods below.

    async def link_choice_to_goal(
        self, choice_uid: str, goal_uid: str, contribution_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to goal it supports/advances."""
        return await self.relationships.link_to_goal(
            choice_uid, goal_uid, contribution_score=contribution_score
        )

    async def link_choice_to_habit(
        self, choice_uid: str, habit_uid: str, reinforcement_strength: float = 0.5
    ) -> Result[bool]:
        """Link choice to habit it reinforces/weakens."""
        properties = {"reinforcement_strength": reinforcement_strength}
        return await self.relationships.create_relationship(
            "habits", choice_uid, habit_uid, properties
        )

    async def link_choice_to_principle(
        self, choice_uid: str, principle_uid: str, alignment_score: float = 0.5
    ) -> Result[bool]:
        """Link choice to principle it aligns with."""
        return await self.relationships.link_to_principle(
            choice_uid, principle_uid, alignment_score=alignment_score
        )

    # Note: get_choice_cross_domain_context, get_choice_with_semantic_context
    # delegated via explicit methods below.

    async def create_semantic_choice_relationship(
        self,
        choice_uid: str,
        related_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """Create semantic relationship for choice (to principle, knowledge, or goal)."""
        return await self.relationships.create_semantic_relationship(
            choice_uid, related_uid, semantic_type, confidence, notes
        )

    async def find_choices_aligned_with_principle(
        self, principle_uid: str, min_confidence: float = 0.8
    ) -> Result[list[Choice]]:
        """Find choices aligned with specific principle."""
        return await self.relationships.find_by_semantic_filter(
            target_uid=principle_uid, min_confidence=min_confidence, direction="incoming"
        )

    # ========================================================================
    # ANALYTICS OPERATIONS - Direct backend delegation
    # ========================================================================

    async def analyze_decision_patterns(
        self, user_uid: UserUID, lookback_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze user's decision-making patterns across domains.

        Returns comprehensive analysis including:
        - Decision style distribution
        - Average time pressure and energy levels
        - Goal alignment metrics
        - Habit reinforcement patterns
        - Principle integrity metrics
        - Quality correlations (pressure vs satisfaction, energy vs confidence)
        - Auto-generated recommendations

        Args:
            user_uid: UID of the user
            lookback_days: Days to look back (default 90)

        Returns:
            Result containing decision pattern analysis
        """
        return await self.intelligence.get_decision_patterns(user_uid, days=lookback_days)

    # ========================================================================
    # QUERY LAYER
    # ========================================================================

    async def get_filtered_context(
        self,
        user_uid: UserUID,
        status_filter: str = "pending",
        sort_by: str = "deadline",
    ) -> Result[ListContext]:
        """Get filtered and sorted choices with pre-filter stats in a single query."""

        async def fetch_all() -> Result[list[Any]]:
            return await self.core.get_for_user_filtered(user_uid, "all")

        def apply_filters(all_choices: list[Any]) -> list[Any]:
            return apply_entity_filter(all_choices, status_filter, _CHOICE_FILTER_CONFIG)

        return await build_filtered_context(
            fetch_all=fetch_all,
            compute_stats=_compute_choice_stats,
            apply_filters=apply_filters,
            apply_sort=_apply_choice_sort,
            sort_by=sort_by,
        )

    async def get_analytics_context(self, user_uid: UserUID) -> Result[ChoicesAnalyticsContext]:
        """Build pre-computed analytics context for the choices analytics view.

        Returns dict with: total_choices, total_decisions, satisfaction_rate,
        on_time_rate, outcomes.
        """
        all_result = await self.core.get_for_user_filtered(user_uid, "all")
        if all_result.is_error:
            return Result.fail(all_result)

        choices = all_result.value

        total = len(choices)
        decided_statuses = ["decided", "implemented", "evaluated"]
        decided = sum(1 for c in choices if get_enum_attr_str(c, "status") in decided_statuses)

        # Satisfaction rate from choices with satisfaction_score (1-5 scale)
        choices_with_satisfaction = [
            c for c in choices if getattr(c, "satisfaction_score", None) is not None
        ]
        if choices_with_satisfaction:
            satisfied_count = sum(
                1 for c in choices_with_satisfaction if getattr(c, "satisfaction_score", 0) >= 4
            )
            satisfaction_rate = satisfied_count / len(choices_with_satisfaction)
        else:
            satisfaction_rate = 0.0

        # On-time rate from choices with deadline and decided_at
        choices_with_deadline = [
            c
            for c in choices
            if getattr(c, "decision_deadline", None) is not None
            and getattr(c, "decided_at", None) is not None
        ]
        if choices_with_deadline:
            on_time_count = sum(
                1 for c in choices_with_deadline if c.decided_at <= c.decision_deadline
            )
            on_time_rate = on_time_count / len(choices_with_deadline)
        else:
            on_time_rate = 0.0

        # Outcomes from evaluated choices
        outcomes = [
            {
                "title": getattr(c, "title", "Choice"),
                "outcome": getattr(c, "actual_outcome", ""),
                "satisfaction": getattr(c, "satisfaction_score", None),
                "lessons": getattr(c, "lessons_learned", ()),
            }
            for c in choices
            if getattr(c, "actual_outcome", None) is not None
        ]

        return Result.ok(
            {
                "total_choices": total,
                "total_decisions": decided,
                "satisfaction_rate": satisfaction_rate,
                "on_time_rate": on_time_rate,
                "outcomes": outcomes,
            }
        )

    # Note: Intelligence delegations (get_choice_with_context, get_decision_intelligence,
    # analyze_choice_impact, get_decision_patterns, etc.) and Search delegations
    # (search_choices, get_choices_by_status, etc.) delegated via explicit methods below.
