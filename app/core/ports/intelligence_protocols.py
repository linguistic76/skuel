"""
Intelligence Service Protocols
==============================

Protocol definitions for intelligence services across all domains.

Split into focused protocols (March 2026):
- KnowledgeIntelligenceOperations: Knowledge methods shared across all 6 activity domains.
  Implemented by ActivityKnowledgeIntelligenceService.
- DomainIntelligenceOperations: Domain-specific behavioral/performance intelligence.
  Implemented by per-domain intelligence services (TasksIntelligenceService, etc.).
- IntelligenceOperations: Composed protocol (both combined) for backward compatibility.

See: /docs/patterns/protocol_architecture.md
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.query_types import (
        AIInsightsResult,
        BehavioralInsightsResult,
        CrossDomainOpportunitiesResult,
        KnowledgeGenerationResult,
        KnowledgePrerequisitesResult,
        KnowledgeSuggestionsResult,
        LearningOpportunitiesResult,
        PerformanceAnalyticsResult,
    )
    from core.services.cross_domain_analytics_service import LearningVelocityMetrics

# ============================================================================
# KNOWLEDGE INTELLIGENCE — shared across all activity domains
# ============================================================================


@runtime_checkable
class KnowledgeIntelligenceOperations(Protocol):
    """
    Knowledge intelligence operations shared across all 6 activity domains.

    Implemented by ActivityKnowledgeIntelligenceService — a single service
    instance wired into every activity facade via self.knowledge_intelligence.

    Methods analyze how activities connect to knowledge: suggestions,
    prerequisites, knowledge generation from completed entities, and
    learning opportunity discovery.

    See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
    """

    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> "Result[KnowledgeSuggestionsResult]":
        """
        Generate knowledge suggestions from entity patterns.

        Args:
            user_uid: User identifier
            entity_uid: Optional specific entity

        Returns:
            Result containing knowledge suggestions and learning opportunities
        """
        ...

    async def get_knowledge_prerequisites(
        self, entity_uid: str
    ) -> "Result[KnowledgePrerequisitesResult]":
        """
        Analyze knowledge prerequisites for entity.

        Args:
            entity_uid: Entity identifier

        Returns:
            Result containing prerequisite knowledge and learning path
        """
        ...

    async def generate_knowledge_from_entities(
        self, user_uid: str, period_days: int = 30
    ) -> "Result[KnowledgeGenerationResult]":
        """
        Generate knowledge units from completed entities.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing generated knowledge units and patterns
        """
        ...

    async def get_learning_opportunities(
        self, user_uid: str
    ) -> "Result[LearningOpportunitiesResult]":
        """
        Discover learning opportunities from entity patterns.

        Args:
            user_uid: User identifier

        Returns:
            Result containing learning opportunities and recommendations
        """
        ...


# ============================================================================
# DOMAIN INTELLIGENCE — domain-specific behavioral/performance
# ============================================================================


@runtime_checkable
class DomainIntelligenceOperations(Protocol):
    """
    Domain-specific intelligence operations.

    Implemented by per-domain intelligence services (TasksIntelligenceService,
    GoalsIntelligenceService, etc.) for behavioral analysis, performance
    tracking, content similarity, and AI-powered insights.

    See: /docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md
    """

    async def find_similar_content(self, uid: str, limit: int = 5) -> Result[list[str]]:
        """
        Find knowledge units similar to the given unit.

        Uses embeddings or content analysis for similarity matching.

        Args:
            uid: Knowledge unit UID to find similar content for
            limit: Maximum similar units to return

        Returns:
            Result containing list of similar knowledge unit UIDs
        """
        ...

    async def search_by_features(
        self, features: dict[str, Any], limit: int = 25
    ) -> Result[list[str]]:
        """
        Search knowledge units by content features.

        Args:
            features: Feature criteria (complexity, readability, etc.)
            limit: Maximum results to return

        Returns:
            Result containing list of matching knowledge unit UIDs
        """
        ...

    async def get_learning_velocity(
        self, user_uid: str, period_days: int = 90
    ) -> "Result[LearningVelocityMetrics]":
        """
        Analyze learning velocity from entity completion patterns.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing velocity metrics and trends
        """
        ...

    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> "Result[BehavioralInsightsResult]":
        """
        Analyze behavioral patterns and insights.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing behavioral patterns and recommendations
        """
        ...

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> "Result[PerformanceAnalyticsResult]":
        """
        Analyze performance metrics and trends.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing performance metrics and optimization opportunities
        """
        ...

    async def get_cross_domain_opportunities(
        self, user_uid: str, entity_uid: str | None = None
    ) -> "Result[CrossDomainOpportunitiesResult]":
        """
        Identify cross-domain opportunities and connections.

        Args:
            user_uid: User identifier
            entity_uid: Optional specific entity

        Returns:
            Result containing cross-domain connections and synergies
        """
        ...

    async def get_ai_insights(
        self, user_uid: str, entity_uid: str | None = None, query: str | None = None
    ) -> "Result[AIInsightsResult]":
        """
        Get AI-powered insights using LLM.

        Args:
            user_uid: User identifier
            entity_uid: Optional specific entity
            query: Optional specific query

        Returns:
            Result containing AI-generated insights and recommendations
        """
        ...


# ============================================================================
# COMPOSED PROTOCOL — full intelligence operations
# ============================================================================


@runtime_checkable
class IntelligenceOperations(
    KnowledgeIntelligenceOperations, DomainIntelligenceOperations, Protocol
):
    """
    Full intelligence operations (composed).

    Combines KnowledgeIntelligenceOperations (shared across all activity
    domains) and DomainIntelligenceOperations (domain-specific). Use the
    focused protocols when only a subset is needed.

    Note: The route factory in adapters/inbound/route_factories/ defines its
    own local IntelligenceOperations protocol (3 methods: get_with_context,
    get_performance_analytics, get_domain_insights) — that is separate from
    this core protocol.
    """

    ...
