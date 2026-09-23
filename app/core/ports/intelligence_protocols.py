"""
Intelligence Service Protocols
==============================

Protocol definitions for intelligence services across all domains.

- KnowledgeIntelligenceOperations: Knowledge methods shared across all 6 activity domains.
  Implemented by ActivityKnowledgeIntelligenceService.

The per-domain intelligence services (TasksIntelligenceService, etc.) share no core
protocol; the route-facing slice they satisfy is IntelligenceRouteFactory's own
IntelligenceOperations (adapters/inbound/route_factories/intelligence_route_factory.py).

See: /docs/patterns/protocol_architecture.md
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.query_types import (
        KnowledgeGenerationResult,
        KnowledgePrerequisitesResult,
        KnowledgeSuggestionsResult,
        LearningOpportunitiesResult,
    )

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
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[KnowledgeSuggestionsResult]:
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
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]:
        """
        Analyze knowledge prerequisites for entity.

        Args:
            entity_uid: Entity identifier

        Returns:
            Result containing prerequisite knowledge and learning path
        """
        ...

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[KnowledgeGenerationResult]:
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
        self, user_uid: UserUID
    ) -> Result[LearningOpportunitiesResult]:
        """
        Discover learning opportunities from entity patterns.

        Args:
            user_uid: User identifier

        Returns:
            Result containing learning opportunities and recommendations
        """
        ...
