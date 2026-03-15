"""
Learning Step Service Sub-modules
===================================

Decomposed learning step services following the LessonService and LpService patterns.

Architecture (January 2026 - One Path Forward):
- ls_core_service.py: CRUD operations + persistence (extends BaseService)
- ls_search_service.py: Search operations (extends BaseService)
- UnifiedRelationshipService: All relationship operations (via LsService.relationships)

Usage:
    from core.services.ls_service import LsService  # Facade coordinates all sub-services

    # Or import sub-services directly:
    from core.services.ls import LsCoreService, LsSearchService
"""

from .ls_core_service import LsCoreService
from .ls_progress_service import LsProgressService
from .ls_search_service import LsSearchService

__all__ = [
    "LsCoreService",
    "LsProgressService",
    "LsSearchService",
]
