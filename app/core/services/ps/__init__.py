"""
PathStep Service Sub-modules
==============================

Decomposed path step services.

Architecture:
- ps_core_service.py: CRUD operations + persistence (extends BaseService)
- ps_search_service.py: Search operations (extends BaseService)
- ps_graph_service.py: Graph navigation and relationships
- ps_semantic_service.py: Semantic relationship management
- ps_practice_service.py: Event-driven practice tracking
- ps_mastery_service.py: Pedagogical tracking
- ps_adaptive_service.py: Personalized curriculum
- ps_application_discovery_service.py: Reverse relationship queries
- ps_context_service.py: Context-first knowledge recommendations
- ps_organization_service.py: ORGANIZES relationships
- ps_intelligence_service.py: Intelligence and analytics
- ps_progress_service.py: KU completion progress

Usage:
    from core.services.ps_service import PsService  # Facade coordinates all sub-services
"""

from .ps_core_service import PsCoreService
from .ps_progress_service import PsProgressService
from .ps_search_service import PsSearchService

__all__ = [
    "PsCoreService",
    "PsProgressService",
    "PsSearchService",
]
