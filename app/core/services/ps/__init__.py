"""
Learning Step Service Sub-modules
===================================

Decomposed path step services following the LessonService and LpService patterns.

Architecture (January 2026 - One Path Forward):
- ls_core_service.py: CRUD operations + persistence (extends BaseService)
- ls_search_service.py: Search operations (extends BaseService)
- UnifiedRelationshipService: All relationship operations (via PsService.relationships)

Usage:
    from core.services.ps_service import PsService  # Facade coordinates all sub-services

    # Or import sub-services directly:
    from core.services.ps import PsCoreService, PsSearchService
"""

from .ps_core_service import PsCoreService
from .ps_progress_service import PsProgressService
from .ps_search_service import PsSearchService

__all__ = [
    "PsCoreService",
    "PsProgressService",
    "PsSearchService",
]
