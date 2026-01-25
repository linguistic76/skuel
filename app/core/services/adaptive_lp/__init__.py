"""
Adaptive Learning Path Services
================================

Modular adaptive learning path system split into focused sub-services:

- AdaptiveLpCoreService: Dynamic path generation, learning style detection
- AdaptiveLpRecommendationsService: Adaptive recommendations based on gaps
- AdaptiveLpCrossDomainService: Cross-domain opportunity discovery
- AdaptiveLpSuggestionsService: Personalized application suggestions
- AdaptiveLpFacade: Unified interface composing all services
"""

from core.services.adaptive_lp.adaptive_lp_core_service import AdaptiveLpCoreService
from core.services.adaptive_lp.adaptive_lp_cross_domain_service import AdaptiveLpCrossDomainService
from core.services.adaptive_lp.adaptive_lp_facade import AdaptiveLpFacade
from core.services.adaptive_lp.adaptive_lp_recommendations_service import (
    AdaptiveLpRecommendationsService,
)
from core.services.adaptive_lp.adaptive_lp_suggestions_service import AdaptiveLpSuggestionsService

__all__ = [
    "AdaptiveLpCoreService",
    "AdaptiveLpCrossDomainService",
    "AdaptiveLpFacade",
    "AdaptiveLpRecommendationsService",
    "AdaptiveLpSuggestionsService",
]
