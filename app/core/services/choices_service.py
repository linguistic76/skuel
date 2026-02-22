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

from typing import TYPE_CHECKING, Any

from core.models.enums import KuStatus
from core.models.ku.ku import Ku
from core.models.ku.ku_base import KuBase
from core.models.ku.ku_dto import KuDTO
from core.services.base_service import BaseService

# Import sub-services and mixins
from core.services.choices import ChoicesLearningService
from core.services.choices.choices_ai_service import ChoicesAIService
from core.services.domain_config import create_activity_domain_config

# Unified relationship service (replaces ChoicesRelationshipService)
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.mixins import (
    FacadeDelegationMixin,
    create_relationship_delegations,
    merge_delegations,
)
from core.ports import BackendOperations
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.ku.ku_request import KuChoiceCreateRequest, KuUpdateRequest
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.search_protocols import ChoicesSearchOperations


class ChoicesService(FacadeDelegationMixin, BaseService["BackendOperations[Ku]", Ku]):
    """
    Choices service facade with specialized sub-services.

    This facade:
    1. Delegates to 5 specialized sub-services for core operations
    2. Uses FacadeDelegationMixin for ~30 auto-generated delegation methods
    3. Retains explicit methods for complex operations
    4. Provides clean separation of concerns

    Auto-Generated Delegations (via FacadeDelegationMixin):
    - Core: get_choice, get_user_choices, get_user_items_in_range
    - Learning: create_choice_with_learning_guidance, suggest_learning_aligned_choices, etc.
    - Search: search_choices, get_choices_by_status, get_pending_choices, etc.
    - Intelligence: get_choice_with_context, get_decision_intelligence, get_decision_patterns, etc.

    Explicit Methods (custom logic):
    - Option management: add_option, update_option, remove_option, make_decision
    - Relationship linking: link_choice_to_goal, link_choice_to_habit, link_choice_to_principle
    - Semantic relationships: create_semantic_choice_relationship, find_choices_aligned_with_principle

    SKUEL Architecture:
    - Uses FacadeDelegationMixin for delegation (January 2026 Phase 3)
    - Uses CypherGenerator for ALL graph queries
    - Returns Result[T] for error handling
    """

    # ========================================================================
    # DOMAIN CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================
    # Facade services use same config as core/search sub-services
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=KuBase,
        domain_name="choices",
        date_field="decision_date",
        completed_statuses=(KuStatus.COMPLETED.value,),
    )

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "get_choice": ("core", "get_choice"),
            "get_user_choices": ("core", "get_user_choices"),
            "get_user_items_in_range": ("core", "get_user_items_in_range"),
        },
        # Learning delegations
        {
            "create_choice_with_learning_guidance": (
                "learning",
                "create_choice_with_learning_guidance",
            ),
            "get_learning_informed_guidance": ("learning", "get_learning_informed_guidance"),
            "track_choice_learning_outcomes": ("learning", "track_choice_learning_outcomes"),
            "suggest_learning_aligned_choices": ("learning", "suggest_learning_aligned_choices"),
        },
        # Relationship delegations (factory-generated)
        create_relationship_delegations("choice"),
        # Intelligence delegations (includes consolidated analytics methods - January 2026)
        {
            "get_choice_with_context": ("intelligence", "get_choice_with_context"),
            "get_decision_intelligence": ("intelligence", "get_decision_intelligence"),
            "analyze_choice_impact": ("intelligence", "analyze_choice_impact"),
            # Analytics methods (consolidated from ChoicesAnalyticsService)
            "get_decision_patterns": ("intelligence", "get_decision_patterns"),
            "get_choice_quality_correlations": ("intelligence", "get_choice_quality_correlations"),
            "get_domain_decision_patterns": ("intelligence", "get_domain_decision_patterns"),
        },
        # Search delegations
        {
            "search_choices": ("search", "search"),
            "get_choices_by_status": ("search", "get_by_status"),
            "get_choices_by_domain": ("search", "get_by_domain"),
            "get_pending_choices": ("search", "get_pending"),
            "get_choices_due_soon": ("search", "get_due_soon"),
            "get_overdue_choices": ("search", "get_overdue"),
            "get_choices_by_urgency": ("search", "get_by_urgency"),
            "get_choices_needing_decision": ("search", "get_needing_decision"),
            "get_prioritized_choices": ("search", "get_prioritized"),
            "list_choice_categories": ("search", "list_user_categories"),
            "list_all_choice_categories": ("search", "list_all_categories"),
        },
    )

    def __init__(
        self,
        backend: BackendOperations[Ku],
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
            insight_store: InsightStore for persisting event-driven insights (optional, Phase 1 - January 2026)

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
        return "Ku"

    # Note: Backend access uses inherited BaseService._backend property
    # Custom backend property removed November 2025 - was unnecessary indirection

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to ChoicesCoreService
    # ========================================================================
    # Note: Simple delegations (get_choice, get_user_choices, get_user_items_in_range)
    # auto-generated by FacadeDelegationMixin.

    async def create_choice(
        self, choice_request: KuChoiceCreateRequest, user_uid: str
    ) -> Result[Ku]:
        """Create a basic choice.

        Args:
            choice_request: Choice creation request
            user_uid: User UID (REQUIRED - fail-fast philosophy)
        """
        return await self.core.create_choice(choice_request, user_uid)

    async def update_choice(self, choice_uid: str, choice_update: KuUpdateRequest) -> Result[Ku]:
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
    ) -> Result[list[Ku]]:
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
    ) -> Result[Ku]:
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
    ) -> Result[Ku]:
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
    ) -> Result[Ku]:
        """Remove an option from a choice."""
        return await self.core.remove_option(choice_uid=choice_uid, option_uid=option_uid)

    async def make_decision(
        self,
        choice_uid: str,
        selected_option_uid: str,
        decision_rationale: str | None = None,
        confidence: float = 0.5,
    ) -> Result[Ku]:
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
    # auto-generated by FacadeDelegationMixin.

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
    # auto-generated by FacadeDelegationMixin.

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
    ) -> Result[list[Ku]]:
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

    # Note: Intelligence delegations (get_choice_with_context, get_decision_intelligence,
    # analyze_choice_impact, get_decision_patterns, etc.) and Search delegations
    # (search_choices, get_choices_by_status, etc.) auto-generated by FacadeDelegationMixin.
