"""
Intelligence Service Protocols
==============================

Protocol definitions for intelligence services across all domains.

These protocols define the common intelligence capabilities that all
domain-specific intelligence services should provide.
"""

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class IntelligenceOperations(Protocol):
    """
    Protocol for intelligence operations across all domains.

    All domain-specific intelligence services (TasksIntelligenceService,
    HabitsIntelligenceService, etc.) should implement these methods.
    """

    # ========================================================================
    # KNOWLEDGE INTELLIGENCE
    # ========================================================================

    async def get_knowledge_suggestions(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge suggestions from entity patterns.

        Args:
            user_uid: User identifier
            entity_uid: Optional specific entity

        Returns:
            Result containing knowledge suggestions and learning opportunities
        """
        ...

    async def get_knowledge_prerequisites(self, entity_uid: str) -> Result[dict[str, Any]]:
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
    ) -> Result[dict[str, Any]]:
        """
        Generate knowledge units from completed entities.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing generated knowledge units and patterns
        """
        ...

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

    # ========================================================================
    # LEARNING INTELLIGENCE
    # ========================================================================

    async def get_learning_opportunities(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Discover learning opportunities from entity patterns.

        Args:
            user_uid: User identifier

        Returns:
            Result containing learning opportunities and recommendations
        """
        ...

    async def get_learning_velocity(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze learning velocity from entity completion patterns.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing velocity metrics and trends
        """
        ...

    # ========================================================================
    # BEHAVIORAL INTELLIGENCE
    # ========================================================================

    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze behavioral patterns and insights.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing behavioral patterns and recommendations
        """
        ...

    # ========================================================================
    # PERFORMANCE INTELLIGENCE
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Analyze performance metrics and trends.

        Args:
            user_uid: User identifier
            period_days: Period to analyze

        Returns:
            Result containing performance metrics and optimization opportunities
        """
        ...

    # ========================================================================
    # CROSS-DOMAIN INTELLIGENCE
    # ========================================================================

    async def get_cross_domain_opportunities(
        self, user_uid: str, entity_uid: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Identify cross-domain opportunities and connections.

        Args:
            user_uid: User identifier
            entity_uid: Optional specific entity

        Returns:
            Result containing cross-domain connections and synergies
        """
        ...

    # ========================================================================
    # AI-POWERED INSIGHTS
    # ========================================================================

    async def get_ai_insights(
        self, user_uid: str, entity_uid: str | None = None, query: str | None = None
    ) -> Result[dict[str, Any]]:
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
