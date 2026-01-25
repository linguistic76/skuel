"""
Principles Sub-Services Package
================================

Specialized sub-services for the Principles domain.

This package provides:
- PrinciplesCoreService: CRUD operations
- PrinciplesSearchService: Search and discovery (DomainSearchOperations[Principle] protocol)
- PrinciplesAlignmentService: Alignment assessment
- PrinciplesLearningService: Learning path integration
- PrinciplesIntelligenceService: Pure Cypher queries
- PrinciplesReflectionService: Reflection persistence and analytics
- PrinciplesPlanningService: Context-aware recommendations (January 2026)

NOTE: PrinciplesRelationshipService replaced by UnifiedRelationshipService (December 2025)
See: core/services/relationships/unified_relationship_service.py

Version: 2.2.0
Date: 2026-01-19
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
