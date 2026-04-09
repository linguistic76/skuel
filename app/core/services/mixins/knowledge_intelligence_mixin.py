"""Knowledge Intelligence Delegation Mixin for Activity Domain facades.

Provides the 4 KnowledgeIntelligenceOperations delegation methods shared
by all 6 Activity Domain facades (Tasks, Goals, Habits, Events, Choices,
Principles). Each facade delegates to a shared ActivityKnowledgeIntelligenceService
singleton via self.knowledge_intelligence.

Extracted April 2026 to eliminate 24 identical methods (4 x 6 facades).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.ports.query_types import (
        KnowledgeGenerationResult,
        KnowledgePrerequisitesResult,
        KnowledgeSuggestionsResult,
        LearningOpportunitiesResult,
    )


class KnowledgeIntelligenceDelegationMixin:
    """Delegates knowledge intelligence methods to self.knowledge_intelligence.

    Requires the consuming class to assign self.knowledge_intelligence in __init__.
    """

    knowledge_intelligence: KnowledgeIntelligenceOperations

    async def get_knowledge_suggestions(
        self, user_uid: UserUID, entity_uid: EntityUID | None = None
    ) -> Result[KnowledgeSuggestionsResult]:
        """Generate knowledge suggestions from entity patterns."""
        return await self.knowledge_intelligence.get_knowledge_suggestions(user_uid, entity_uid)

    async def generate_knowledge_from_entities(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[KnowledgeGenerationResult]:
        """Generate knowledge units from completed entities."""
        return await self.knowledge_intelligence.generate_knowledge_from_entities(
            user_uid, period_days
        )

    async def get_knowledge_prerequisites(
        self, entity_uid: EntityUID
    ) -> Result[KnowledgePrerequisitesResult]:
        """Analyze knowledge prerequisites for an entity."""
        return await self.knowledge_intelligence.get_knowledge_prerequisites(entity_uid)

    async def get_learning_opportunities(
        self, user_uid: UserUID
    ) -> Result[LearningOpportunitiesResult]:
        """Discover learning opportunities from entity patterns."""
        return await self.knowledge_intelligence.get_learning_opportunities(user_uid)
