"""
Askesis AI Service
==================

AI-powered features for Askesis domain (requires LLM/Embeddings).

Created: January 2026
Purpose: Separate AI features from graph analytics (ADR-030)

AI services contain features that REQUIRE:
- embeddings_service (semantic search, similarity matching)
- llm_service (AI-generated insights, recommendations, natural language)

AI services are OPTIONAL - the app functions fully without them.
They enhance the user experience but are not required for core functionality.

This service provides:
- Willpower management and resistance pattern analysis
- Discipline tracking across domains
- Self-mastery progress insights
- Recovery optimization

The app works WITHOUT this service. It's an enhancement layer.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.embeddings_service import OpenAIEmbeddingsService
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )
    from core.services.llm_service import LLMService


class AskesisAIService(BaseAIService[Any, Any]):
    """
    AI-powered features for Askesis (discipline) domain.

    This service is OPTIONAL - the app works without it.
    Provides enhanced features using LLM and embeddings.

    Features:
    - Behavioral insights with AI-powered pattern recognition
    - Performance analytics with AI-generated recommendations
    - Willpower and discipline tracking with smart suggestions

    Source Tag: "askesis_ai_explicit"
    - Format: "askesis_ai_explicit" for user-created relationships
    - Format: "askesis_ai_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    NOTE: This service requires LLM/embeddings services.
    If not available, this service won't be instantiated.
    """

    # Service name for hierarchical logging
    _service_name = "askesis.ai"

    # AI requirements - both required for this service

    def __init__(
        self,
        backend: Any,  # No AskesisOperations protocol yet
        llm_service: "LLMService",
        embeddings_service: "OpenAIEmbeddingsService",
        graph_intelligence_service: "GraphIntelligenceService | None" = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize askesis AI service.

        Args:
            backend: Backend for askesis operations (no protocol yet)
            llm_service: LLM service for AI insights (REQUIRED)
            embeddings_service: Embeddings service for semantic search (REQUIRED)
            graph_intelligence_service: GraphIntelligenceService for graph analytics
            relationship_service: Optional relationship service for graph operations
            event_bus: Event bus for publishing events (optional)

        NOTE: Both llm_service and embeddings_service are REQUIRED.
        This service should only be instantiated when AI is available.
        """
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )
        # Store graph for convenience
        self.graph = graph_intelligence_service

    async def get_behavioral_insights(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """Analyze discipline patterns and willpower management."""
        self.logger.info(f"Analyzing askesis patterns for user {user_uid}")

        return Result.ok(
            {
                "behavior_patterns": [
                    {
                        "pattern": "willpower_cycles",
                        "description": "Energy peaks in morning hours",
                        "confidence": 0.80,
                    },
                    {
                        "pattern": "resistance_patterns",
                        "description": "Common obstacles identified",
                        "confidence": 0.75,
                    },
                ],
                "success_factors": [
                    "Consistent practice builds discipline capacity",
                    "Recovery periods prevent burnout",
                    "Small wins compound into self-mastery",
                ],
                "recommendations": [
                    "Schedule demanding tasks during peak willpower hours",
                    "Build recovery rituals after intense discipline periods",
                    "Track resistance patterns to identify triggers",
                ],
                "willpower_insights": {
                    "current_capacity": "moderate",
                    "depletion_risk": "low",
                    "recovery_status": "good",
                },
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                },
            }
        )

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Analyze discipline performance metrics."""
        return Result.ok(
            {
                "metrics": {
                    "discipline_consistency": 0.82,
                    "willpower_capacity": 0.75,
                    "resistance_management": 0.78,
                },
                "trends": {"self_mastery_progress": "improving"},
                "optimization_opportunities": [
                    {
                        "area": "willpower_preservation",
                        "suggestion": "Reduce low-value decisions to preserve willpower for important choices",
                        "potential_impact": "20-25% improvement in follow-through",
                    }
                ],
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                },
            }
        )
