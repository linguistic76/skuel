"""
Enrichment Mixin — PrinciplesService
======================================

Analytics and discovery — surfacing principle insights.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Result


class _EnrichmentMixin:
    """
    Analytics delegates for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    core: Any
    search: Any
    alignment: Any
    intelligence: Any
    logger: Any

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    async def get_analytics_summary(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Analytics: counts, adherence, recent reflections. Orchestrates sub-services."""
        all_result = await self.core.get_for_user_filtered(user_uid)
        if all_result.is_error:
            return Result.fail(all_result)
        principles = all_result.value

        total = len(principles)
        core_count = sum(1 for p in principles if getattr(p, "strength", 0) >= 0.9)
        active_count = sum(1 for p in principles if getattr(p, "is_active", True))

        overall_adherence = 0.0
        try:
            adherence_result = await self.alignment.calculate_average_alignment(user_uid)
            if not adherence_result.is_error:
                overall_adherence = adherence_result.value
        except Exception as e:  # safety-net: optional alignment degrades gracefully
            self.logger.warning(f"Could not calculate adherence: {e}")

        # PrinciplesReflectionService shelved (2026-03-28)

        return Result.ok(
            {
                "total_principles": total,
                "overall_adherence": overall_adherence,
                "core_count": core_count,
                "active_count": active_count,
                "reflections": [],
            }
        )
