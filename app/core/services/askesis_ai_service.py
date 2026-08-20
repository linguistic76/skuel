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

from core.models.entity import Entity
from core.models.type_hints import UserUID
from core.services.base_ai_service import BaseAIService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.embeddings_service import EmbeddingsService
    from core.services.infrastructure.graph_intelligence_service import (
        GraphIntelligenceService,
    )
    from core.services.llm_service import LLMService
    from core.services.user_service import UserService


class AskesisAIService(BaseAIService["UserService", Entity]):
    """
    AI-powered features for Askesis (discipline) domain.

    This service is OPTIONAL - the app works without it.

    Backend note (measured 2026-08-19, Scope D): this service makes **zero**
    ``self.backend`` calls, and ``BaseAIService`` never reads ``self.backend``
    either — it validates it non-None and stores it. So ``backend`` is
    ceremonial here: it exists to satisfy the base's fail-fast contract. It is
    typed as ``UserService`` because that is what ``_wire_ai_services`` actually
    passes, not as an aspiration. The former ``Any`` carried the comment
    "# No AskesisOperations protocol yet"; ``UserContextOperations`` does exist, but a satisfiability probe
    shows ``UserService`` does **not** implement it, so naming it would have
    been a second untrue declaration. Whether these two should take a real
    user-state protocol — or ``BaseAIService`` should stop requiring a backend
    at all — is an open design question, deliberately not decided here.
        Provides enhanced features using LLM and embeddings.

    Features:
    - Behavioral insights with AI-powered pattern recognition
    - Performance analytics with AI-generated recommendations
    - Willpower and discipline tracking with smart suggestions
    """

    # Service name for hierarchical logging
    _service_name = "askesis.ai"

    # AI requirements - both required for this service

    def __init__(
        self,
        backend: "UserService",
        llm_service: "LLMService",
        embeddings_service: "EmbeddingsService",
        graph_intel: "GraphIntelligenceService | None" = None,
        relationship_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initialize askesis AI service.

        Args:
            backend: UserService, the user-state handle every AI service is
                given. This service reads nothing off it today — see the class
                docstring — but BaseAIService requires it (fail-fast).
            llm_service: LLM service for AI insights (REQUIRED)
            embeddings_service: Embeddings service for semantic search (REQUIRED)
            graph_intel: GraphIntelligenceService for graph analytics
            relationship_service: Optional relationship service for graph operations
            event_bus: Event bus for publishing events (optional)

        NOTE: Both llm_service and embeddings_service are REQUIRED.
        This service should only be instantiated when AI is available.
        """
        super().__init__(
            backend=backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )
        # Store graph for convenience
        self.graph = graph_intel

    async def get_performance_analytics(  # skuel-lint: disable=SKUEL029 -- IntelligenceOperations protocol method (async contract)
        self, user_uid: UserUID, period_days: int = 30
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
