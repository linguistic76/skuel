"""
Principles Sub-Services Package
================================

This package contains focused sub-services that compose the unified PrinciplesService facade.

Architecture: Facade Pattern (7 sub-services)
- Each sub-service handles ONE specific responsibility
- PrinciplesService (facade) auto-delegates to appropriate sub-service via FacadeDelegationMixin
- Philosophical guidance domain with alignment, reflection, and learning integration
- Zero breaking changes to external code

Sub-Services:
- PrinciplesCoreService: CRUD operations, event publishing
- PrinciplesSearchService: Search, discovery, filtering
- PrinciplesAlignmentService: Alignment assessment across domains
- PrinciplesLearningService: Learning path integration, knowledge connections
- PrinciplesPlanningService: Context-aware recommendations
- PrinciplesReflectionService: Reflection persistence and analytics
- PrinciplesIntelligenceService: Pure Cypher analytics (NO AI dependencies)

Common Import Pattern (Production):
    from core.services.principles_service import PrinciplesService  # Facade
    result = await principles_service.create_principle(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.principles import PrinciplesCoreService
    core = PrinciplesCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- PrinciplesRelationshipService replaced by UnifiedRelationshipService (December 2025)
"""

from core.services.principles.principles_alignment_service import PrinciplesAlignmentService
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles.principles_intelligence_service import PrinciplesIntelligenceService
from core.services.principles.principles_learning_service import PrinciplesLearningService
from core.services.principles.principles_planning_service import PrinciplesPlanningService
from core.services.principles.principles_reflection_service import PrinciplesReflectionService
from core.services.principles.principles_search_service import PrinciplesSearchService

__all__ = [
    "PrinciplesAlignmentService",
    "PrinciplesCoreService",
    "PrinciplesIntelligenceService",
    "PrinciplesLearningService",
    "PrinciplesPlanningService",
    "PrinciplesReflectionService",
    "PrinciplesSearchService",
]
