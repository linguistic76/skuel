"""
Choices Sub-Services Package
=============================

This package contains focused sub-services that compose the unified ChoicesService facade.

Architecture: Facade Pattern (4 sub-services)
- Each sub-service handles ONE specific responsibility
- ChoicesService (facade) auto-delegates to appropriate sub-service via FacadeDelegationMixin
- Decision-making domain with principle alignment and learning guidance
- Zero breaking changes to external code

Sub-Services:
- ChoicesCoreService: CRUD operations, event publishing
- ChoicesSearchService: Search, discovery, filtering
- ChoicesLearningService: Learning path guidance, knowledge integration
- ChoicesIntelligenceService: Pure Cypher analytics, decision pattern analysis (NO AI dependencies)

Additional Exports:
- choices_types: Frozen dataclasses for intelligence results (DecisionAnalysis, RiskAssessment, etc.)

Common Import Pattern (Production):
    from core.services.choices_service import ChoicesService  # Facade
    result = await choices_service.create_choice(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.choices import ChoicesCoreService
    core = ChoicesCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- ChoicesRelationshipService replaced by UnifiedRelationshipService (December 2025)
- ChoicesAnalyticsService consolidated into ChoicesIntelligenceService (January 2026)

Version: 3.2.0
Date: 2026-01-29
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
