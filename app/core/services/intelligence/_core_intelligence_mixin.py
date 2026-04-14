"""
Shared Core Intelligence Mixin
================================

Provides the `get_with_context()` protocol method for all Activity Domain
intelligence services. Delegates to GraphContextLoader, which handles
the generic entity-fetch + Cypher graph context pattern.

All 6 Activity Domain intelligence services inherit from this mixin.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext


class _CoreIntelligenceMixin:
    """
    Shared base for all Activity Domain intelligence services.

    Provides the IntelligenceOperations protocol method `get_with_context()`
    via GraphContextLoader. Each domain intelligence service also
    exposes a domain-named alias (e.g. `get_goal_with_context`).
    """

    # Populated by each domain intelligence service __init__
    context_loader: Any
    logger: Any

    @requires_graph_intelligence("get_with_context")
    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Any, GraphContext]]:
        """
        Get entity with full graph context. Implements IntelligenceOperations protocol.

        Delegates to GraphContextLoader, which selects the optimal Cypher
        query type based on the entity's suggested_query_intent and executes it
        as a single round-trip.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (entity, GraphContext) tuple
        """
        if not self.context_loader:
            return Result.fail(
                Errors.system(
                    message="GraphContextLoader not initialized",
                    operation="get_with_context",
                )
            )
        return await self.context_loader.get_with_context(uid=uid, depth=depth)
