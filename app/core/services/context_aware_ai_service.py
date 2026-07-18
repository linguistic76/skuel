"""
Context-Aware AI Service
========================

AI-powered features for context-aware intelligence (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service provides:
- Situational intelligence and environmental factor analysis
- Context switching optimization
- Personalized recommendations based on current context
- Multi-factor decision support

The app works WITHOUT this service. It's an enhancement layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.embeddings_service import EmbeddingsService
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )
    from core.services.llm_service import LLMService


class ContextAwareAIService(BaseAIService[Any, Any]):
    """
    AI-powered features for context-aware intelligence.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    Features:
    - Behavioral insights based on environmental patterns
    - Context switching optimization with AI recommendations
    - AI-powered situational recommendations
    """

    # Service name for hierarchical logging
    _service_name = "context_aware.ai"

    # AI requirements - both required for this service

    def __init__(
        self,
        backend: Any,  # Uses UserContextOperations or similar
        llm_service: LLMService,
        embeddings_service: EmbeddingsService,
        graph_intel: GraphIntelligenceService | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize context-aware AI service.

        Args:
            backend: Backend for context operations
            llm_service: LLM service for AI insights (REQUIRED)
            embeddings_service: Embeddings service for semantic search (REQUIRED)
            graph_intel: GraphIntelligenceService for graph analytics
            event_bus: Event bus for publishing events (optional)

        NOTE: Both llm_service and embeddings_service are REQUIRED.
        This service should only be instantiated when AI is available.
        """
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )
        # Store graph for convenience
        self.graph = graph_intel

    async def get_performance_analytics(  # skuel-lint: disable=SKUEL029 -- IntelligenceOperations protocol method (async contract)
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Analyze context-aware performance metrics.

        Not yet implemented — requires LLM integration for narrative synthesis.
        """
        return Result.fail(
            Errors.business(
                "not_implemented", "Context-aware performance analytics not yet implemented"
            )
        )
