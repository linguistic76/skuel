"""
Choices Sub-Services Package
=============================

Specialized sub-services for the Choices domain.

This package provides:
- ChoicesCoreService: CRUD operations
- ChoicesSearchService: Search and discovery (DomainSearchOperations[Choice] protocol)
- ChoicesLearningService: Learning path guidance
- ChoicesIntelligenceService: Pure Cypher analytics + decision pattern analysis
- choices_types: Frozen dataclasses for intelligence results

NOTE: ChoicesRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

NOTE: ChoicesAnalyticsService consolidated into ChoicesIntelligenceService (January 2026)
Analytics methods (get_decision_patterns, get_choice_quality_correlations, get_domain_decision_patterns)
now live in ChoicesIntelligenceService for unified pattern across all Activity domains.

Version: 3.1.0
Date: 2026-01-19
- v3.1.0: Moved choices_types.py into package for consistency
"""

from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.choices.choices_learning_service import ChoicesLearningService
from core.services.choices.choices_search_service import ChoicesSearchService
from core.services.choices.choices_types import (
    CascadeImpact,
    ChoiceGraphContext,
    ChoiceImpactAnalysis,
    DecisionAnalysis,
    DecisionContext,
    DecisionImpact,
    DecisionIntelligence,
    DecisionRecommendations,
    DomainImpactBreakdown,
    DomainImpactDetail,
    ImpactSummary,
    PathAwareContext,
    RiskAssessment,
)

__all__ = [
    # Services
    "ChoicesCoreService",
    "ChoicesIntelligenceService",
    "ChoicesLearningService",
    "ChoicesSearchService",
    # Types
    "CascadeImpact",
    "ChoiceGraphContext",
    "ChoiceImpactAnalysis",
    "DecisionAnalysis",
    "DecisionContext",
    "DecisionImpact",
    "DecisionIntelligence",
    "DecisionRecommendations",
    "DomainImpactBreakdown",
    "DomainImpactDetail",
    "ImpactSummary",
    "PathAwareContext",
    "RiskAssessment",
]
