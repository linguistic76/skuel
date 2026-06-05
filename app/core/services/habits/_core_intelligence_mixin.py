"""
Core Intelligence Mixin — HabitsIntelligenceService

Graph context retrieval via mechanism B (registry-sourced) is inherited from the
shared ``_CoreIntelligenceMixin`` — it routes through
``self.relationships.get_with_context`` so the edge vocabulary comes from
``HABITS_CONFIG.cross_domain_relationship_types`` (the registry single source of
truth). This mixin adds only the habit-named alias.

Part of habits_intelligence_service.py decomposition (April 2026).
Converged onto mechanism B in Convergence Phase 1 (2B); the per-domain override
was collapsed into the shared base in the curriculum-convergence teardown.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md,
     /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.models.habit.habit import Habit


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Graph context methods for HabitsIntelligenceService.

    ``get_with_context`` (mechanism B) is inherited from the shared
    ``_CoreIntelligenceMixin``; this mixin adds only the habit-named alias.
    """

    @requires_graph_intelligence("get_habit_with_context")
    async def get_habit_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        """Domain-named alias for get_with_context() (mechanism B)."""
        return await self.get_with_context(uid, depth)
