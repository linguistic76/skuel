"""
Sharing Service Package
========================

Cross-cutting sharing infrastructure. Any entity type can be shared —
SHARES_WITH relationships and visibility levels work identically for
Submissions, ActivityReports, Tasks, Goals, or any future domain.

Services:
- UnifiedSharingService: Entity-agnostic sharing (driver-based)

See: /docs/patterns/SHARING_PATTERNS.md
"""

from core.services.sharing.unified_sharing_service import UnifiedSharingService

__all__ = ["UnifiedSharingService"]
