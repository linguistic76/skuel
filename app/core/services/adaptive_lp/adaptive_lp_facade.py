"""
Adaptive Learning Path Facade
==============================

Unified interface composing all adaptive learning path sub-services.

Provides backward compatibility with the original AdaptiveLpService
while delegating to specialized sub-services:
- Core: Dynamic path generation and knowledge analysis
- Recommendations: Adaptive recommendations based on gaps
- Cross-Domain: Cross-domain opportunity discovery
- Suggestions: Personalized application suggestions
"""

from typing import Any

from core.constants import MasteryLevel

# Import sub-services
from core.services.adaptive_lp.adaptive_lp_core_service import AdaptiveLpCoreService
from core.services.adaptive_lp.adaptive_lp_cross_domain_service import AdaptiveLpCrossDomainService

# Import dataclasses from shared models module (breaks circular dependency)
from core.services.adaptive_lp.adaptive_lp_models import (
    AdaptiveLp,
    AdaptiveRecommendation,
    CrossDomainOpportunity,
    LearningStyle,
    PersonalizedSuggestion,
)
from core.services.adaptive_lp.adaptive_lp_recommendations_service import (
    AdaptiveLpRecommendationsService,
)
from core.services.adaptive_lp.adaptive_lp_suggestions_service import AdaptiveLpSuggestionsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class AdaptiveLpFacade:
    """
    Facade composing all adaptive learning path sub-services.

    This provides a unified interface maintaining backward compatibility
    with the original AdaptiveLpService while delegating to specialized
    sub-services for cleaner architecture.
    """

    def __init__(
        self,
        ku_service=None,
        learning_service=None,
        goals_service=None,
        tasks_service=None,
        ku_generation_service=None,
        user_service=None,
    ) -> None:
        """
        Initialize the adaptive learning path facade.

        Args:
            ku_service: For accessing knowledge units,
            learning_service: For learning path management,
            goals_service: For user goals and progress,
            tasks_service: For task completion patterns,
            ku_generation_service: For pattern analysis,
            user_service: For building UserContext (REQUIRED for refactored methods)
        """
        self.logger = get_logger("skuel.adaptive_lp_facade")
        self.user_service = user_service

        # Initialize all sub-services
        self.core_service = AdaptiveLpCoreService(
            ku_service=ku_service,
            learning_service=learning_service,
            goals_service=goals_service,
            tasks_service=tasks_service,
        )

        self.recommendations_service = AdaptiveLpRecommendationsService(
            goals_service=goals_service,
            tasks_service=tasks_service,
            ku_generation_service=ku_generation_service,
        )

        self.cross_domain_service = AdaptiveLpCrossDomainService(MasteryLevel.BEGINNER)

        self.suggestions_service = AdaptiveLpSuggestionsService()

        self.logger.info("AdaptiveLpFacade initialized with all sub-services")

    # ========================================================================
    # DYNAMIC LEARNING PATH GENERATION (delegates to core_service)
    # ========================================================================

    async def generate_goal_driven_learning_path(
        self, user_uid: str, goal_uid: str, learning_style_override: LearningStyle | None = None
    ) -> Result[AdaptiveLp]:
        """
        Generate a dynamic learning path based on a specific user goal.

        Delegates to AdaptiveLpCoreService.

        Args:
            user_uid: User to generate path for,
            goal_uid: Specific goal to target,
            learning_style_override: Override detected learning style

        Returns:
            Result containing AdaptiveLp
        """
        return await self.core_service.generate_goal_driven_learning_path(
            user_uid=user_uid, goal_uid=goal_uid, learning_style_override=learning_style_override
        )

    # ========================================================================
    # ADAPTIVE RECOMMENDATIONS (delegates to recommendations_service)
    # ========================================================================

    async def generate_adaptive_recommendations(
        self, user_uid: str, context: dict[str, Any] | None = None
    ) -> Result[list[AdaptiveRecommendation]]:
        """
        Generate adaptive recommendations based on knowledge gaps and user context.

        Delegates to AdaptiveLpRecommendationsService.

        Args:
            user_uid: User to generate recommendations for,
            context: Additional context for personalization

        Returns:
            Result containing list of AdaptiveRecommendation objects
        """
        # Build UserContext (MEGA-QUERY via user_service)
        if not self.user_service:
            return Result.fail(
                Errors.system(
                    message="user_service required for UserContext",
                    operation="generate_adaptive_recommendations",
                )
            )

        user_context_result = await self.user_service.get_user_context(user_uid)
        if user_context_result.is_error:
            return Result.fail(user_context_result.expect_error())
        user_context = user_context_result.value

        # Get knowledge state from UserContext (no re-query)
        knowledge_state_result = await self.core_service.analyze_user_knowledge_state(user_context)
        if knowledge_state_result.is_error:
            return Result.fail(knowledge_state_result.expect_error())
        knowledge_state = knowledge_state_result.value

        # Get learning style from core service (real implementation)
        learning_style_result = await self.core_service.detect_learning_style(user_uid)
        if learning_style_result.is_error:
            return Result.fail(learning_style_result.expect_error())
        learning_style = learning_style_result.value

        return await self.recommendations_service.generate_adaptive_recommendations(
            user_uid=user_uid,
            knowledge_state=knowledge_state,
            learning_style=learning_style,
            context=context,
        )

    # ========================================================================
    # CROSS-DOMAIN OPPORTUNITIES (delegates to cross_domain_service)
    # ========================================================================

    async def discover_cross_domain_opportunities(
        self, user_uid: str, min_confidence: float | None = None
    ) -> Result[list[CrossDomainOpportunity]]:
        """
        Discover learning opportunities that span multiple knowledge domains.

        Delegates to AdaptiveLpCrossDomainService.

        Args:
            user_uid: User to analyze for cross-domain opportunities,
            min_confidence: Minimum confidence threshold for opportunities

        Returns:
            Result containing list of CrossDomainOpportunity objects
        """
        # Build UserContext (MEGA-QUERY via user_service)
        if not self.user_service:
            return Result.fail(
                Errors.system(
                    message="user_service required for UserContext",
                    operation="discover_cross_domain_opportunities",
                )
            )

        user_context_result = await self.user_service.get_user_context(user_uid)
        if user_context_result.is_error:
            return Result.fail(user_context_result.expect_error())
        user_context = user_context_result.value

        # Get knowledge state from UserContext (no re-query)
        knowledge_state_result = await self.core_service.analyze_user_knowledge_state(user_context)
        if knowledge_state_result.is_error:
            return Result.fail(knowledge_state_result.expect_error())
        knowledge_state = knowledge_state_result.value

        return await self.cross_domain_service.discover_cross_domain_opportunities(
            user_uid=user_uid, knowledge_state=knowledge_state, min_confidence=min_confidence
        )

    # ========================================================================
    # PERSONALIZED SUGGESTIONS (delegates to suggestions_service)
    # ========================================================================

    async def generate_personalized_application_suggestions(
        self, user_uid: str, context: dict[str, Any] | None = None
    ) -> Result[list[PersonalizedSuggestion]]:
        """
        Generate personalized suggestions for applying existing knowledge.

        Delegates to AdaptiveLpSuggestionsService.

        Args:
            user_uid: User to generate suggestions for,
            context: Additional context for personalization

        Returns:
            Result containing list of PersonalizedSuggestion objects
        """
        # Build UserContext (MEGA-QUERY via user_service)
        if not self.user_service:
            return Result.fail(
                Errors.system(
                    message="user_service required for UserContext",
                    operation="generate_personalized_application_suggestions",
                )
            )

        user_context_result = await self.user_service.get_user_context(user_uid)
        if user_context_result.is_error:
            return Result.fail(user_context_result.expect_error())
        user_context = user_context_result.value

        # Get knowledge state from UserContext (no re-query)
        knowledge_state_result = await self.core_service.analyze_user_knowledge_state(user_context)
        if knowledge_state_result.is_error:
            return Result.fail(knowledge_state_result.expect_error())
        knowledge_state = knowledge_state_result.value

        # Get learning style from core service (real implementation)
        learning_style_result = await self.core_service.detect_learning_style(user_uid)
        if learning_style_result.is_error:
            return Result.fail(learning_style_result.expect_error())
        learning_style = learning_style_result.value

        return await self.suggestions_service.generate_personalized_application_suggestions(
            user_uid=user_uid,
            knowledge_state=knowledge_state,
            learning_style=learning_style,
            context=context,
        )

    # ========================================================================
    # UTILITY METHODS (for direct access to sub-services if needed)
    # ========================================================================

    def get_core_service(self) -> AdaptiveLpCoreService:
        """Get direct access to the core service."""
        return self.core_service

    def get_recommendations_service(self) -> AdaptiveLpRecommendationsService:
        """Get direct access to the recommendations service."""
        return self.recommendations_service

    def get_cross_domain_service(self) -> AdaptiveLpCrossDomainService:
        """Get direct access to the cross-domain service."""
        return self.cross_domain_service

    def get_suggestions_service(self) -> AdaptiveLpSuggestionsService:
        """Get direct access to the suggestions service."""
        return self.suggestions_service
