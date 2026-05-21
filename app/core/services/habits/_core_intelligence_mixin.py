"""
Core Intelligence Mixin — HabitsIntelligenceService

Domain-named alias for get_with_context(). Shared base provides the
orchestrator delegation.

Part of habits_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
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
    """Graph context methods for HabitsIntelligenceService."""

    @requires_graph_intelligence("get_habit_with_context")
    async def get_habit_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, GraphContext]]:
        """Domain-named alias for get_with_context(). See shared base."""
        return await self.get_with_context(uid, depth)
