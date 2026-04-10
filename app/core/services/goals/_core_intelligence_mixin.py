"""
Core Intelligence Mixin — GoalsIntelligenceService
====================================================

Graph-context method: get_goal_with_context.

Part of goals_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.goal.goal import Goal
    from core.models.graph_context import GraphContext


class _CoreIntelligenceMixin:
    """
    Graph context methods for GoalsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsIntelligenceService.__init__
    backend: Any
    orchestrator: Any
    relationships: Any
    logger: Any

    @requires_graph_intelligence("get_goal_with_context")
    async def get_goal_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Goal, GraphContext]]:
        """
        Get goal with full graph context using pure Cypher graph intelligence.

        Automatically selects optimal query type based on goal's suggested intent:
        - HIERARCHICAL -> Supporting activities and milestones
        - PREREQUISITE -> Required knowledge and learning paths
        - AGGREGATION -> Progress tracking across all activities
        - Default -> Comprehensive goal ecosystem

        Args:
            uid: Goal UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (goal, GraphContext) tuple with comprehensive insights
        """
        # Use GraphContextOrchestrator pattern (consolidation)
        # Orchestrator is guaranteed to exist when @requires_graph_intelligence passes
        if not self.orchestrator:
            return Result.fail(
                Errors.system(
                    message="GraphContextOrchestrator not initialized",
                    operation="get_goal_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)
