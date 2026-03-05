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

from enum import Enum
from typing import TYPE_CHECKING, Any

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.enums import EntityStatus
from core.ports.domain_protocols import ChoicesOperations
from core.services.base_service import BaseService

# Import sub-services
from core.services.choices import ChoicesLearningService
from core.services.choices.choices_ai_service import ChoicesAIService
from core.services.domain_config import create_activity_domain_config

# Unified relationship service (replaces ChoicesRelationshipService)
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_decision_deadline,
    make_priority_string_getter,
)

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.choice.choice_request import ChoiceCreateRequest
    from core.models.entity_requests import EntityUpdateRequest
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.query_types import ListContext
    from core.ports.search_protocols import ChoicesSearchOperations
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService


def _get_choice_enum_value(obj: Any, attr: str, default: str = "") -> str:
    """Extract value from attribute (handles both enum and string)."""
    value = getattr(obj, attr, None)
    if value is None:
        return default
    if isinstance(value, Enum):
        return str(value.value).lower()
    return str(value).lower()


_CHOICE_PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _get_choice_priority(c: Any) -> str:
    """Extract priority string for sort key (SKUEL012: named function, no lambda)."""
    return _get_choice_enum_value(c, "priority", "medium")


def _apply_choice_sort(choices: list[Any], sort_by: str = "deadline") -> list[Any]:
    """Sort choices by specified field."""
    if sort_by == "deadline":
        return sorted(choices, key=get_decision_deadline)
    elif sort_by == "priority":
        sort_key = make_priority_string_getter(_CHOICE_PRIORITY_ORDER, _get_choice_priority)
        return sorted(choices, key=sort_key)
    elif sort_by == "created_at":
        return sorted(choices, key=get_created_at_attr, reverse=True)
    return sorted(choices, key=get_decision_deadline)


class ChoicesService(BaseService["ChoicesOperations", Choice]):
    """
    Choices service facade with specialized sub-services.

    This facade:
    1. Delegates to 5 specialized sub-services for core operations
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
    async def get_choice(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_choice(*args, **kwargs)

    async def get_user_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_choices(*args, **kwargs)

    async def get_user_items_in_range(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.core.get_user_items_in_range(*args, **kwargs)

    # Learning delegations
    async def create_choice_with_learning_guidance(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.create_choice_with_learning_guidance(*args, **kwargs)

    async def get_learning_informed_guidance(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.get_learning_informed_guidance(*args, **kwargs)

    async def track_choice_learning_outcomes(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.track_choice_learning_outcomes(*args, **kwargs)

    async def suggest_learning_aligned_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.learning.suggest_learning_aligned_choices(*args, **kwargs)

    # Relationship delegations
    async def get_choice_cross_domain_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_cross_domain_context(*args, **kwargs)

    async def get_choice_with_semantic_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.relationships.get_with_semantic_context(*args, **kwargs)

    # Intelligence delegations
    async def get_choice_with_context(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_choice_with_context(*args, **kwargs)

    async def get_decision_intelligence(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_decision_intelligence(*args, **kwargs)

    async def analyze_choice_impact(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.analyze_choice_impact(*args, **kwargs)

    async def get_decision_patterns(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_decision_patterns(*args, **kwargs)

    async def get_choice_quality_correlations(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_choice_quality_correlations(*args, **kwargs)

    async def get_domain_decision_patterns(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.intelligence.get_domain_decision_patterns(*args, **kwargs)

    # Search delegations
    async def search_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.search(*args, **kwargs)

    async def get_choices_by_status(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_status(*args, **kwargs)

    async def get_choices_by_domain(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_domain(*args, **kwargs)

    async def get_pending_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_pending(*args, **kwargs)

    async def get_choices_due_soon(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_due_soon(*args, **kwargs)

    async def get_overdue_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_overdue(*args, **kwargs)

    async def get_choices_by_urgency(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_by_urgency(*args, **kwargs)

    async def get_choices_needing_decision(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_needing_decision(*args, **kwargs)

    async def get_prioritized_choices(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.get_prioritized(*args, **kwargs)

    async def list_choice_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_user_categories(*args, **kwargs)

    async def list_all_choice_categories(self, *args: Any, **kwargs: Any) -> Result[Any]:
        return await self.search.list_all_categories(*args, **kwargs)

    def __init__(
        self,
        backend: ChoicesOperations,
        graph_intelligence_service: GraphIntelligenceService,
        event_bus: EventBusOperations | None = None,
        ai_service: ChoicesAIService | None = None,
        insight_store: Any = None,
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
        self.ai: ChoicesAIService | None = ai_service
        self.logger = get_logger("skuel.services.choices")

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[ChoicesIntelligenceService] = create_common_sub_services(
            domain="choices",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        self.core = common.core
        self.search: ChoicesSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: ChoicesIntelligenceService = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.learning = ChoicesLearningService(backend=backend)

        self.logger.info(
            "ChoicesService facade initialized with 5 sub-services: "
            "core, search, learning, relationships, intelligence"
        )

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
        self, choice_request: ChoiceCreateRequest, user_uid: str
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
        self, user_uid: str, lookback_days: int = 90
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
        user_uid: str,
        status_filter: str = "pending",
        sort_by: str = "deadline",
    ) -> Result[ListContext]:
        """Get filtered and sorted choices with pre-filter stats.

        Stats via Cypher COUNT (no entity deserialization).
        Status filter pushed to Cypher WHERE (not Python post-filter).
        """
        import asyncio

        stats_result, entities_result = await asyncio.gather(
            self.core.get_stats_for_user(user_uid),
            self.core.get_for_user_filtered(user_uid, status_filter),
        )
        if stats_result.is_error:
            return Result.fail(stats_result)
        if entities_result.is_error:
            return Result.fail(entities_result)
        sorted_choices = _apply_choice_sort(entities_result.value, sort_by)
        return Result.ok({"entities": sorted_choices, "stats": stats_result.value})

    # Note: Intelligence delegations (get_choice_with_context, get_decision_intelligence,
    # analyze_choice_impact, get_decision_patterns, etc.) and Search delegations
    # (search_choices, get_choices_by_status, etc.) delegated via explicit methods below.
