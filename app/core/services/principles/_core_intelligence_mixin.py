"""
Core Intelligence Mixin — PrinciplesIntelligenceService

Protocol bridge methods + graph context orchestration.

Part of principles_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import PrincipleStrength
from core.models.type_hints import UserUID
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.models.principle.principle import Principle


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Protocol bridge + graph context for PrinciplesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesIntelligenceService.__init__
    backend: Any
    relationships: Any
    logger: Any

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, _period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get principle performance analytics for a user.

        Protocol method: Aggregates principle metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/principles/analytics route.

        Args:
            user_uid: User UID
            _period_days: Placeholder - not yet implemented. Will filter by period when added.

        Returns:
            Result containing analytics data dict

        Note: _period_days uses underscore prefix per CLAUDE.md convention to indicate
        "API contract defined, implementation deferred". Currently calculates analytics
        over ALL principles. Future enhancement: filter by created_at within period.
        """
        from core.models.principle.principle import Principle

        # Get all principles for user
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result)

        all_principles = principles_result.value or []
        principles: list[Principle] = [p for p in all_principles if isinstance(p, Principle)]

        # Calculate analytics
        total_principles = len(principles)
        active_principles = [p for p in principles if p.is_active]

        # Count by strength
        core_principles = [
            p for p in principles if p.strength and p.strength == PrincipleStrength.CORE
        ]
        strong_principles = [
            p for p in principles if p.strength and p.strength == PrincipleStrength.STRONG
        ]

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": _period_days,
                "total_principles": total_principles,
                "active_principles": len(active_principles),
                "core_principles": len(core_principles),
                "strong_principles": len(strong_principles),
                "analytics": {
                    "total": total_principles,
                    "active": len(active_principles),
                    "core": len(core_principles),
                    "strong": len(strong_principles),
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a principle.

        Protocol method: Maps to assess_principle_alignment.
        Used by IntelligenceRouteFactory for GET /api/principles/insights route.

        Args:
            uid: Principle UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        return await self.assess_principle_alignment(uid, min_confidence)  # type: ignore[attr-defined]

    # ========================================================================
    # GRAPH INTELLIGENCE METHODS
    # ========================================================================

    @requires_graph_intelligence("get_principle_with_context")
    async def get_principle_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Principle, GraphContext]]:
        """Domain-named alias for get_with_context(). See shared base."""
        return await self.get_with_context(uid, depth)  # type: ignore[return-value]
