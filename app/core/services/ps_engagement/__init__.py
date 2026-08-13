"""PsEngagementService — PathStep + Activity Templates lifecycle (Phase 4).

Implements the engagement contract: 4 transitions (publish, engage, complete, abandon) over 3 entities (Template,
Instance, Engagement). The facade owns ``PsEngagementService``; the helpers
(``_PsValidator``, ``_SpawnOrchestrator``, ``_EngagementGateway``) are private
and are imported by tests via the underscore-prefixed names.
"""

from core.services.ps_engagement.engagement import Engagement, EngagementEdgeState
from core.services.ps_engagement.ps_engagement_service import PsEngagementService

__all__ = ["Engagement", "EngagementEdgeState", "PsEngagementService"]
