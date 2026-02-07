"""
Enhanced Principles Service - Facade Pattern
=============================================

Principles service facade that delegates to specialized sub-services.
This service provides a unified interface while maintaining clean separation of concerns.

Version: 5.0.0
Date: 2025-11-28

Changelog:
- v5.0.0 (2025-11-28): Added PrinciplesSearchService implementing DomainSearchOperations[Principle]
  Removed custom backend property (code smell) - using inherited BaseService.backend
  Delegated search methods to self.search sub-service
- v4.0.0 (2025-11-09): Facade pattern harmonization - renamed from PrincipleAlignmentService
- v3.0.0 (2025-10-13): Facade pattern implementation with 5 specialized sub-services
- v2.0.0 (2025-10-03): Phase 1-4 integration with pure Cypher graph intelligence
- v1.0.0: Base implementation

Sub-Services:
- PrinciplesCoreService: CRUD operations for principles
- PrinciplesSearchService: Search and discovery (DomainSearchOperations[Principle] protocol)
- PrinciplesAlignmentService: Alignment assessment and motivational intelligence
- PrinciplesLearningService: Learning path integration and framing
- UnifiedRelationshipService (PRINCIPLES_UNIFIED): Cross-domain links and integrity calculation
- PrinciplesIntelligenceService: Pure Cypher analytics

Architecture: Zero breaking changes - all existing code continues to work unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.principle.principle import Principle, PrincipleCategory
from core.models.principle.principle_dto import PrincipleDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

# Import sub-services, mixins, and their types
from core.services.mixins import (
    FacadeDelegationMixin,
    create_relationship_delegations,
    merge_delegations,
)
from core.services.principles import (
    PrinciplesAlignmentService,
    PrinciplesLearningService,
    PrinciplesPlanningService,
    PrinciplesReflectionService,
)
from core.services.principles.principles_ai_service import PrinciplesAIService
from core.services.protocols.domain_protocols import (
    GoalsOperations,
    HabitsOperations,
    PrinciplesOperations,
)

# Unified relationship service (replaces PrinciplesRelationshipService)
from core.services.relationships import UnifiedRelationshipService
from core.utils.activity_domain_config import CommonSubServices, create_common_sub_services
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.principles.principles_alignment_service import (
        AlignmentAssessment,
    )
    from core.services.principles.principles_intelligence_service import (
        PrinciplesIntelligenceService,
    )
    from core.services.protocols.search_protocols import PrinciplesSearchOperations


# NOTE: AlignmentAssessment and MotivationalProfile are now imported from
# principles_alignment_service to avoid type duplication issues


class PrinciplesService(FacadeDelegationMixin, BaseService[PrinciplesOperations, Principle]):
    """
    Principles service facade with specialized sub-services.

    This facade:
    1. Delegates to 6 specialized sub-services for core operations
    2. Uses FacadeDelegationMixin for ~25 auto-generated delegation methods
    3. Retains explicit methods for complex operations
    4. Provides clean separation of concerns

    Auto-Generated Delegations (via FacadeDelegationMixin):
    - Core: get_principle, get_user_principles, get_user_items_in_range
    - Alignment: assess_goal_alignment, assess_habit_alignment, get_motivational_profile, etc.
    - Learning: frame_principle_practice_with_learning, assess_principle_learning_alignment, etc.
    - Intelligence: get_principle_with_context, assess_principle_alignment, etc.
    - Search: get_principle_categories, get_principles_by_status, etc.

    Explicit Methods (custom logic):
    - create_principle (many parameters)
    - Relationship methods: create_user_principle_relationship, get_user_principle_portfolio
    - search_principles (has post-filtering logic)
    - Stub methods for future implementation

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
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(),  # Principles don't have completion status
    )

    # ========================================================================
    # DELEGATION SPECIFICATION (FacadeDelegationMixin)
    # ========================================================================
    _delegations = merge_delegations(
        # Core CRUD delegations
        {
            "get_principle": ("core", "get_principle"),
            "get_user_principles": ("core", "get_user_principles"),
            "get_user_items_in_range": ("core", "get_user_items_in_range"),
        },
        # Alignment delegations
        {
            "assess_goal_alignment": ("alignment", "assess_goal_alignment"),
            "assess_habit_alignment": ("alignment", "assess_habit_alignment"),
            "get_motivational_profile": ("alignment", "get_motivational_profile"),
            "make_principle_based_decision": ("alignment", "make_principle_based_decision"),
        },
        # Learning delegations
        {
            "frame_principle_practice_with_learning": (
                "learning",
                "frame_principle_practice_with_learning",
            ),
            "assess_principle_learning_alignment": (
                "learning",
                "assess_principle_learning_alignment",
            ),
            "suggest_learning_supported_principles": (
                "learning",
                "suggest_learning_supported_principles",
            ),
            "track_principle_learning_development": (
                "learning",
                "track_principle_learning_development",
            ),
        },
        # Relationship delegations (factory-generated, no semantic context for principles)
        create_relationship_delegations("principle", include_semantic=False),
        # Intelligence delegations
        {
            "get_principle_with_context": ("intelligence", "get_principle_with_context"),
            "assess_principle_alignment": ("intelligence", "assess_principle_alignment"),
            "get_principle_adherence_trends": ("intelligence", "get_principle_adherence_trends"),
            "get_principle_conflict_analysis": ("intelligence", "get_principle_conflict_analysis"),
        },
        # Search delegations
        {
            "get_principle_categories": ("search", "list_user_categories"),
            "list_all_principle_categories": ("search", "list_all_categories"),
            "get_related_principles": ("search", "get_related_principles"),
            "get_principles_by_status": ("search", "get_by_status"),
            "get_principles_by_strength": ("search", "get_by_strength"),
            "get_principles_by_category": ("search", "get_by_category"),
            "get_principles_needing_review": ("search", "get_needing_review"),
            "get_principles_for_goal": ("search", "get_for_goal"),
            "get_principles_for_choice": ("search", "get_for_choice"),
        },
        # Reflection delegations
        {
            "save_reflection": ("reflection", "save_reflection"),
            "get_reflections_for_principle": ("reflection", "get_reflections_for_principle"),
            "get_recent_reflections": ("reflection", "get_recent_reflections"),
            "get_alignment_trend": ("reflection", "calculate_alignment_trend"),
            "get_cross_domain_insights": ("reflection", "get_cross_domain_insights"),
            "get_reflection_frequency": ("reflection", "get_reflection_frequency"),
            "get_conflict_analysis": ("reflection", "get_conflict_analysis"),
        },
        # Planning delegations (January 2026)
        {
            "get_principles_needing_attention_for_user": (
                "planning",
                "get_principles_needing_attention_for_user",
            ),
            "get_contextual_principles_for_user": (
                "planning",
                "get_contextual_principles_for_user",
            ),
            "get_principle_practice_opportunities_for_user": (
                "planning",
                "get_principle_practice_opportunities_for_user",
            ),
        },
    )

    def __init__(
        self,
        backend: PrinciplesOperations,
        graph_intelligence_service: Any,
        goals_backend: GoalsOperations | None = None,
        habits_backend: HabitsOperations | None = None,
        reflection_backend: Any | None = None,
        event_bus: Any = None,
        ai_service: PrinciplesAIService | None = None,
        insight_store: Any = None,
    ) -> None:
        """
        Initialize enhanced principles service with specialized sub-services.

        Args:
            backend: Protocol-based backend for principle operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics (REQUIRED)
            goals_backend: Backend for goal queries (cross-domain alignment)
            habits_backend: Backend for habit queries (cross-domain alignment)
            reflection_backend: Backend for reflection persistence (optional, uses backend if not provided)
            event_bus: Event bus for publishing domain events (optional)
            insight_store: InsightStore for persisting event-driven insights (optional, Phase 1 - January 2026)

        Note:
            Context invalidation now happens via event-driven architecture.
            Principle events trigger user_service.invalidate_context() in bootstrap.

        Migration Note (v3.2.0 - December 2025):
            Made graph_intelligence_service REQUIRED - relationship service needs it.
            Fail-fast at construction, not at method call.
        """
        super().__init__(backend, "principles")

        self.graph_intel = graph_intelligence_service
        self.event_bus = event_bus
        self.ai: PrinciplesAIService | None = ai_service
        self.logger = get_logger("skuel.services.principles")
        self.alignment_cache: dict[str, AlignmentAssessment] = {}

        # Initialize 4 common sub-services via factory (eliminates ~30 lines of repetitive code)
        common: CommonSubServices[PrinciplesIntelligenceService] = create_common_sub_services(
            domain="principles",
            backend=backend,
            graph_intel=graph_intelligence_service,
            event_bus=event_bus,
            insight_store=insight_store,
        )
        self.core = common.core
        self.search: PrinciplesSearchOperations = common.search
        self.relationships: UnifiedRelationshipService = common.relationships
        self.intelligence: PrinciplesIntelligenceService = common.intelligence

        # Domain-specific sub-services (not common to all facades)
        self.alignment = PrinciplesAlignmentService(
            backend=backend,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            event_bus=event_bus,
        )
        self.learning = PrinciplesLearningService(backend=backend)

        # Reflection sub-service (January 2026 - graph-connected reflections)
        self.reflection = PrinciplesReflectionService(
            backend=reflection_backend or backend,
            event_bus=event_bus,
        )

        # Planning sub-service (January 2026 - context-aware recommendations)
        self.planning = PrinciplesPlanningService(
            backend=backend,
            relationship_service=self.relationships,
        )

        self.logger.info(
            "PrinciplesService facade initialized with 8 sub-services: "
            "core, search, alignment, learning, relationships, intelligence, reflection, planning"
        )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Principle entities."""
        return "Principle"

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to PrinciplesCoreService
    # ========================================================================
    # Note: Simple delegations (get_principle, get_user_principles, get_user_items_in_range,
    # alignment assessment, motivational intelligence, learning path integration)
    # auto-generated by FacadeDelegationMixin.

    async def create_principle(
        self,
        label: str,
        description: str,
        category: PrincipleCategory,
        why_matters: str,
        **kwargs: Any,
    ) -> Result[Principle]:
        """Create a new principle."""
        return await self.core.create_principle(label, description, category, why_matters, **kwargs)

    # ========================================================================
    # CROSS-DOMAIN RELATIONSHIPS - Delegate to UnifiedRelationshipService
    # ========================================================================

    async def create_user_principle_relationship(
        self,
        user_uid: str,
        principle_uid: str,
        strength: str = "core",
        adoption_date: str | None = None,
    ) -> Result[bool]:
        """Create User→Principle relationship in graph."""
        properties: dict[str, str] = {"strength": strength}
        if adoption_date:
            properties["adoption_date"] = adoption_date
        return await self.relationships.create_user_relationship(
            user_uid, principle_uid, properties if properties else None
        )

    async def link_principle_to_knowledge(
        self, principle_uid: str, knowledge_uid: str, relevance: str = "fundamental"
    ) -> Result[bool]:
        """Link principle to knowledge it's based on."""
        return await self.relationships.link_to_knowledge(
            principle_uid, knowledge_uid, relevance=relevance
        )

    # Note: get_principle_cross_domain_context auto-generated by FacadeDelegationMixin.

    async def get_user_principle_portfolio(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get user's complete principle portfolio with integrity analysis."""
        # Get all principles for the user
        principles_result = await self.backend.list(filters={"user_uid": user_uid}, limit=100)
        if principles_result.is_error:
            return Result.fail(principles_result)
        # list() returns tuple[list[Principle], int]
        principles, total = principles_result.value
        return Result.ok(
            {
                "user_uid": user_uid,
                "principles": principles,
                "count": len(principles),
            }
        )

    async def calculate_principle_integrity(
        self, user_uid: str, principle_uid: str
    ) -> Result[dict[str, Any]]:
        """Calculate how well user's actions align with stated principle."""
        # Get the principle and its cross-domain context
        context_result = await self.relationships.get_cross_domain_context(principle_uid)
        if context_result.is_error:
            return context_result
        return Result.ok(
            {
                "principle_uid": principle_uid,
                "user_uid": user_uid,
                "context": context_result.value,
                "integrity_score": 0.5,  # Placeholder - would need actual calculation
            }
        )

    # ========================================================================
    # SEARCH AND FILTERING - Delegate to PrinciplesSearchService
    # ========================================================================
    # Note: Intelligence delegations (get_principle_with_context, assess_principle_alignment,
    # get_principle_adherence_trends, get_principle_conflict_analysis)
    # auto-generated by FacadeDelegationMixin.

    async def search_principles(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> Result[list[Principle]]:
        """
        Search principles by text query. Delegates to PrinciplesSearchService.

        Args:
            query: Search query string
            filters: Optional additional filters (category, strength, etc.)
            limit: Maximum results to return

        Returns:
            Result with list of matching principles
        """
        # Basic text search via search sub-service
        result = await self.search.search(query, limit=limit)

        if result.is_error:
            return result

        matching = result.value

        # Apply additional filters if provided
        if filters:
            if "category" in filters:
                matching = [
                    p for p in matching if p.category and p.category.value == filters["category"]
                ]
            if "strength" in filters:
                matching = [
                    p for p in matching if p.strength and p.strength.value == filters["strength"]
                ]

        return Result.ok(matching)

    # Note: Simple search delegations (get_principle_categories, list_all_principle_categories,
    # get_related_principles, get_principles_by_status, get_principles_by_strength,
    # get_principles_by_category, get_principles_needing_review, get_principles_for_goal,
    # get_principles_for_choice) auto-generated by FacadeDelegationMixin.

    async def get_principle_sources(self) -> Result[list[str]]:
        """
        List all principle sources (where principles come from).

        Returns:
            Result with list of unique sources
        """
        from core.models.principle.principle import PrincipleSource
        from core.utils.result_simplified import Result

        # Return all PrincipleSource enum values
        sources = [s.value for s in PrincipleSource]
        return Result.ok(sources)

    async def get_prioritized_principles(
        self, user_uid: str, limit: int = 10
    ) -> Result[list[Principle]]:
        """
        Get principles prioritized for user context. Delegates to PrinciplesSearchService.

        Args:
            user_uid: User UID
            limit: Maximum results to return

        Returns:
            Result containing prioritized principles
        """
        from core.services.user import UserContext

        # Build minimal context for prioritization
        user_context = UserContext(user_uid=user_uid, username="")
        return await self.search.get_prioritized(user_context, limit=limit)

    # ========================================================================
    # STUB METHODS - Future Implementation (Not Yet Developed)
    # ========================================================================
    # These methods are called by the API but require more design work.
    # They return stub responses to avoid MyPy errors while marking them
    # as not implemented for future development.

    async def create_principle_expression(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a principle expression (how principle was lived out).

        STUB: Expression tracking system not yet implemented.

        Args:
            dto: Expression creation DTO

        Returns:
            Result with stub response
        """
        from core.utils.result_simplified import Result

        self.logger.warning(
            "create_principle_expression called but expression system not implemented"
        )
        return Result.ok(
            {
                "status": "stub_not_implemented",
                "message": "Principle expression tracking not yet implemented",
                "dto_received": str(type(dto).__name__),
            }
        )

    async def get_principle_expressions(
        self,
        principle_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get expressions of a principle (instances where it was lived out).

        STUB: Expression tracking system not yet implemented.

        Args:
            principle_uid: Principle UID

        Returns:
            Result with empty list (stub)
        """
        from core.utils.result_simplified import Result

        self.logger.warning(
            f"get_principle_expressions called for {principle_uid} but expression system not implemented"
        )
        return Result.ok([])

    async def get_principle_alignment_history(
        self,
        principle_uid: str,
        limit: int = 50,
        days: int = 90,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get historical alignment assessments for a principle.

        STUB: Alignment history tracking not yet implemented.

        Args:
            principle_uid: Principle UID
            limit: Maximum records
            days: Lookback period in days

        Returns:
            Result with empty list (stub)
        """
        from core.utils.result_simplified import Result

        self.logger.warning(
            f"get_principle_alignment_history called for {principle_uid} but history tracking not implemented"
        )
        return Result.ok([])

    async def create_principle_link(
        self,
        dto: Any,
    ) -> Result[dict[str, Any]]:
        """
        Create a link between principles (e.g., supports, conflicts with).

        STUB: Principle linking system not yet implemented.

        Args:
            dto: Link creation DTO

        Returns:
            Result with stub response
        """
        from core.utils.result_simplified import Result

        self.logger.warning("create_principle_link called but linking system not implemented")
        return Result.ok(
            {
                "status": "stub_not_implemented",
                "message": "Principle linking not yet implemented",
                "dto_received": str(type(dto).__name__),
            }
        )

    async def get_principle_links(
        self,
        principle_uid: str,
        link_type: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get links for a principle (relationships to other principles).

        STUB: Principle linking system not yet implemented.

        Args:
            principle_uid: Principle UID
            link_type: Optional filter by link type

        Returns:
            Result with empty list (stub)
        """
        from core.utils.result_simplified import Result

        self.logger.warning(
            f"get_principle_links called for {principle_uid} but linking system not implemented"
        )
        return Result.ok([])


# Alias for backward compatibility
PrincipleAlignmentService = PrinciplesService
