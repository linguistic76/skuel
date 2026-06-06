"""
Core Intelligence Mixin — TasksIntelligenceService
===================================================

Context retrieval and cross-domain categorization.

Part of tasks_intelligence_service.py decomposition (April 2026).
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
    from core.models.task.task import Task


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Context retrieval for TasksIntelligenceService.

    ``get_with_context`` (mechanism B) is inherited from the shared
    ``_CoreIntelligenceMixin``; this mixin adds the task-named alias.

    Path-aware cross-domain context is now sourced from the CANONICAL typed reader
    (``get_cross_domain_context_typed`` → path-aware ``TaskCrossContext``) via
    ``BaseAnalyticsService._analyze_entity_with_typed_context`` — the hand-rolled
    ``categorize_cross_domain_context`` (dead, zero callers) was deleted in the
    typed-reader convergence.
    """

    @requires_graph_intelligence("get_task_with_context")
    async def get_task_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Task, GraphContext]]:
        """Domain-named alias for get_with_context() (mechanism B)."""
        return await self.get_with_context(uid, depth)
