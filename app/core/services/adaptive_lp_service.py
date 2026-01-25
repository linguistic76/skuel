"""
Adaptive Learning Paths Service (Phase 4.2)
=============================================

AI-powered adaptive learning path generation with:
- Dynamic learning path generation based on user goals
- Adaptive recommendations based on knowledge gaps
- Cross-domain learning opportunity discovery
- Personalized knowledge application suggestions

Builds on the Knowledge Generation Service to create personalized,
adaptive learning experiences that evolve with user progress.

**NOTE**: This is now a thin wrapper around the refactored sub-services.
The actual implementation is split into specialized services for better
maintainability and testability. See `/core/services/adaptive_lp/` for details.
"""

from typing import Any

# Import facade for implementation
from core.services.adaptive_lp.adaptive_lp_facade import AdaptiveLpFacade

# Import shared models from dedicated module (breaks circular dependency)
from core.services.adaptive_lp.adaptive_lp_models import (
    LearningStyle,
)
from core.utils.logging import get_logger

# ========================================================================
# SERVICE WRAPPER (Delegates to Facade)
# ========================================================================


class AdaptiveLpService:
    """
    Service for generating and managing adaptive learning paths.

    This service creates personalized learning experiences that adapt
    to user goals, knowledge gaps, learning style, and progress patterns.

    **REFACTORED**: This class now delegates to specialized sub-services
    via AdaptiveLpFacade for better maintainability and testability.


    Source Tag: "adaptive_lp_service_explicit"
    - Format: "adaptive_lp_service_explicit" for user-created relationships
    - Format: "adaptive_lp_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from adaptive_lp metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        ku_service=None,
        learning_service=None,
        goals_service=None,
        tasks_service=None,
        ku_generation_service=None,
    ) -> None:
        """
        Initialize the adaptive learning paths service.

        Args:
            ku_service: For accessing knowledge units,
            learning_service: For learning path management,
            goals_service: For user goals and progress,
            tasks_service: For task completion patterns,
            ku_generation_service: For pattern analysis
        """
        self.logger = get_logger("skuel.adaptive_learning")

        # Initialize facade (which composes all sub-services)
        self._facade = AdaptiveLpFacade(
            ku_service=ku_service,
            learning_service=learning_service,
            goals_service=goals_service,
            tasks_service=tasks_service,
            ku_generation_service=ku_generation_service,
        )

        self.logger.info("AdaptiveLpService initialized (using facade pattern)")

    # ========================================================================
    # PUBLIC API (Delegates to Facade)
    # ========================================================================

    async def generate_goal_driven_learning_path(
        self, user_uid: str, goal_uid: str, learning_style_override: LearningStyle | None = None
    ):
        """Generate a dynamic learning path based on a specific user goal."""
        return await self._facade.generate_goal_driven_learning_path(
            user_uid=user_uid, goal_uid=goal_uid, learning_style_override=learning_style_override
        )

    async def generate_adaptive_recommendations(
        self, user_uid: str, context: dict[str, Any] | None = None
    ):
        """Generate adaptive recommendations based on knowledge gaps."""
        return await self._facade.generate_adaptive_recommendations(
            user_uid=user_uid, context=context
        )

    async def discover_cross_domain_opportunities(
        self, user_uid: str, min_confidence: float | None = None
    ):
        """Discover learning opportunities spanning multiple knowledge domains."""
        return await self._facade.discover_cross_domain_opportunities(
            user_uid=user_uid, min_confidence=min_confidence
        )

    async def generate_personalized_application_suggestions(
        self, user_uid: str, context: dict[str, Any] | None = None
    ):
        """Generate personalized suggestions for applying existing knowledge."""
        return await self._facade.generate_personalized_application_suggestions(
            user_uid=user_uid, context=context
        )
