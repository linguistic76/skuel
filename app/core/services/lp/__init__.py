"""
Learning Path Service Sub-modules
===================================

Decomposed learning path services following the unified facade pattern.

Architecture (January 2026 - LP Consolidation ADR-031):
- lp_core_service.py: CRUD operations + persistence (extends BaseService)
- lp_search_service.py: Search operations (extends BaseService)
- lp_progress_service.py: Progress tracking (event-driven)

Note: Validation, analysis, adaptive, and context operations are now
consolidated into LpIntelligenceService (in parent directory).

Usage:
    from core.services.lp_service import LpService  # Facade coordinates all sub-services

    # Or import sub-services directly:
    from core.services.lp import LpCoreService, LpSearchService, LpProgressService
"""

from .lp_core_service import LpCoreService
from .lp_progress_service import LpProgressService
from .lp_search_service import LpSearchService

__all__ = [
    "LpCoreService",
    "LpSearchService",
    "LpProgressService",
]
