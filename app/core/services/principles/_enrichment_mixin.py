"""
Enrichment Mixin — PrinciplesService
======================================

Analytics and discovery — surfacing principle insights.

Part of principles_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.principle.principle import Principle


class _EnrichmentMixin:
    """
    Analytics delegates and discovery methods for PrinciplesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by PrinciplesService.__init__
    core: Any
    search: Any
    alignment: Any
    intelligence: Any
    backend: Any
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

    # ========================================================================
    # SEARCH & DISCOVERY
    # ========================================================================

    async def search_principles(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        user_uid: UserUID | None = None,
    ) -> Result[list[Principle]]:
        """
        Search principles by text query. Delegates to PrinciplesSearchService.

        Args:
            query: Search query string
            filters: Optional additional filters (category, strength, etc.)
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result with list of matching principles
        """
        from core.models.principle.principle import Principle

        # Basic text search via search sub-service
        result = await self.search.search(query, limit=limit, user_uid=user_uid)

        if result.is_error:
            return result

        matching = result.value

        # Apply additional filters if provided
        if filters:
            if "category" in filters:
                matching = [
                    p
                    for p in matching
                    if isinstance(p, Principle) and p.category and p.category == filters["category"]
                ]
            if "strength" in filters:
                matching = [
                    p
                    for p in matching
                    if isinstance(p, Principle)
                    and p.strength
                    and p.strength.value == filters["strength"]
                ]

        return Result.ok(matching)

    async def get_principle_sources(self) -> Result[list[str]]:
        """
        List all principle sources (where principles come from).

        Returns:
            Result with list of unique sources
        """
        from core.models.enums.principle_enums import PrincipleSource

        # Return all PrincipleSource enum values
        sources = [s.value for s in PrincipleSource]
        return Result.ok(sources)

    async def get_prioritized_principles(
        self, user_uid: UserUID, limit: int = 10
    ) -> Result[list[Principle]]:
        """
        Get principles prioritized for user context. Delegates to PrinciplesSearchService.

        Args:
            user_uid: User UID
            limit: Maximum results to return

        Returns:
            Result containing prioritized principles
        """
        from core.services.user import UserContext

        # Build minimal context for prioritization
        user_context = UserContext(user_uid=user_uid, username="")
        return await self.search.get_prioritized(user_context, limit=limit)
