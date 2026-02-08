"""
Knowledge Service Sub-Services
================================

This package contains focused sub-services that compose the unified KuService.

Architecture: Facade Pattern (January 2026 - ADR-031)
- Each sub-service handles a specific responsibility
- KuService (facade) delegates to appropriate sub-service
- Zero breaking changes to external code

Sub-services:
- KuCoreService: CRUD operations
- KuSearchService: Search and discovery
- KuGraphService: Graph navigation and relationships
- KuSemanticService: Semantic relationship management
- KuPracticeService: Event-driven practice tracking
- KuInteractionService: Pedagogical tracking (VIEWED->IN_PROGRESS->MASTERED)

DELETED (January 2026):
- KuLpService: Redundant delegation to LpService (use LpService directly)
"""

# Import implemented services
from core.services.ku.ku_adaptive_service import KuAdaptiveService
from core.services.ku.ku_core_service import KuCoreService
from core.services.ku.ku_graph_service import KuGraphService
from core.services.ku.ku_interaction_service import (
    KuInteractionService,
    LearningState,
    UserKuProgress,
)
from core.services.ku.ku_practice_service import KuPracticeService
from core.services.ku.ku_search_service import KuSearchService
from core.services.ku.ku_semantic_service import KuSemanticService

__all__ = [
    "KuAdaptiveService",
    "KuCoreService",
    "KuGraphService",
    "KuInteractionService",
    "KuPracticeService",
    "KuSearchService",
    "KuSemanticService",
    "LearningState",
    "UserKuProgress",
]
