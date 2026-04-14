"""
Shared Core Intelligence Mixin
================================

Provides the `get_with_context()` protocol method for intelligence services
that load `(entity, GraphContext)` via `GraphContextLoader`.

Inherited by all 6 Activity Domain intelligence services plus the curriculum
intelligence services: `PsIntelligenceService`, `LpIntelligenceService`, and
`KuIntelligenceService`. Parameterize with the domain model to get a typed
return: `class PsIntelligenceService(_CoreIntelligenceMixin[PathStep], ...)`.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext


class _CoreIntelligenceMixin[T]:
    """
    Shared `get_with_context()` for intelligence services.

    Generic in the domain model so subclasses get a typed return:
    `_CoreIntelligenceMixin[PathStep]` → `Result[tuple[PathStep, GraphContext]]`.

    Activity domain services additionally expose a domain-named alias
    (e.g. `get_goal_with_context`) from their per-domain wrapper.
    """

    # Populated by BaseAnalyticsService._init_context_loader
    context_loader: Any
    logger: Any

    @requires_graph_intelligence("get_with_context")
    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]:
        """
        Get entity with full graph context. Implements IntelligenceOperations protocol.

        The `@requires_graph_intelligence` decorator short-circuits with an error
        Result when `self.graph_intel` is missing; if graph_intel is present then
        `BaseAnalyticsService._init_context_loader` has built `self.context_loader`.
        No runtime path reaches this body with a missing loader.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (entity, GraphContext) tuple
        """
        return await self.context_loader.get_with_context(uid=uid, depth=depth)
