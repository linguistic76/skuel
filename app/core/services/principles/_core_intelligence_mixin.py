"""
Core Intelligence Mixin — PrinciplesIntelligenceService

Protocol bridge methods + graph context orchestration.

Graph context retrieval (mechanism B, registry-sourced) is inherited from the
shared ``_CoreIntelligenceMixin``: ``self.relationships.get_with_context`` sources
its edge vocabulary from ``PRINCIPLES_CONFIG.cross_domain_relationship_types`` (the
registry single source of truth). This mixin adds the protocol bridge methods plus
the principle-named alias.

Part of principles_intelligence_service.py decomposition (April 2026).
Converged onto mechanism B in Convergence Phase 1 (2C); the per-domain override
was collapsed into the shared base in the curriculum-convergence teardown.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md,
     /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.principle_enums import PrincipleStrength
from core.models.type_hints import UserUID
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.principle.principle import Principle
    from core.ports.domain_protocols import PrinciplesOperations


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Protocol bridge + graph context for PrinciplesIntelligenceService.

    ``get_with_context`` (mechanism B) is inherited from the shared
    ``_CoreIntelligenceMixin``; this mixin adds the protocol bridge methods plus
    the principle-named alias.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesIntelligenceService.__init__
    backend: "PrinciplesOperations"
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
