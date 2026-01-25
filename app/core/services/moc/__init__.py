"""
MOC Service Sub-modules - KU-Based Architecture
=================================================

January 2026: MOC is NOT a separate entity - it IS a Knowledge Unit.

A KU "is" a MOC when it has outgoing ORGANIZES relationships to other KUs.

Architecture (January 2026 - KU-Based Refactor):
- moc_navigation_service.py: MOC navigation patterns on KUs (ORGANIZES relationships)

DELETED (January 2026 - One Path Forward):
- moc_core_service.py: Replaced by KuService
- moc_section_service.py: Sections are now KUs with ORGANIZES relationships
- moc_content_service.py: Content aggregation via KU's ORGANIZES
- moc_discovery_service.py: Discovery via MocNavigationService
- moc_search_service.py: Search via KuService
- moc_intelligence_service.py: Intelligence via KuService.intelligence
- moc_ai_service.py: AI via KuService.ai

Usage:
    from core.services.moc_service import MOCService  # Facade over MocNavigationService
    from core.services.moc import MocNavigationService  # Direct access

See Also:
    - /core/services/moc_service.py: MOC facade
    - /core/services/ku_service.py: KU operations (underlying storage)
"""

from .moc_navigation_service import MocNavigationService, MocView, OrganizedKu

__all__ = [
    "MocNavigationService",
    "MocView",
    "OrganizedKu",
]
