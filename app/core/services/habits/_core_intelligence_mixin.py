"""
Core Intelligence Mixin — HabitsIntelligenceService

Graph context retrieval via mechanism B (registry-sourced). Routes through
``self.relationships.get_with_context`` so the edge vocabulary comes from
``HABITS_CONFIG.cross_domain_relationship_types`` (the registry single source of
truth) rather than the inherited ``GraphContextLoader`` EXPLORATORY path.

Part of habits_intelligence_service.py decomposition (April 2026).
Converged onto mechanism B in Convergence Phase 1 (2B), copying the Tasks reference.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md,
     /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.models.habit.habit import Habit
    from core.services.relationships import UnifiedRelationshipService


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """Graph context methods for HabitsIntelligenceService."""

    # Populated by BaseAnalyticsService.__init__ (stores relationship_service)
    relationships: UnifiedRelationshipService[Any, Any, Any] | None

    @requires_graph_intelligence("get_with_context")
    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        """
        Get habit with full graph context via mechanism B (registry-sourced).

        One Path Forward (Convergence Phase 1): route through
        ``self.relationships.get_with_context`` — which sources its edge vocabulary
        from ``HABITS_CONFIG.cross_domain_relationship_types`` (the registry, the single
        source of truth) — instead of the inherited ``GraphContextLoader`` EXPLORATORY
        path. Copies the Tasks reference (PR #225, 2A).

        See: /docs/roadmap/intent-traversal-registry-convergence.md
        """
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="relationship_service required for get_with_context",
                    operation="get_with_context",
                )
            )
        return await self.relationships.get_with_context(uid, depth)

    @requires_graph_intelligence("get_habit_with_context")
    async def get_habit_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        """Domain-named alias for get_with_context() (mechanism B)."""
        return await self.get_with_context(uid, depth)
