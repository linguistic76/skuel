"""
Shared Core Intelligence Mixin
================================

Provides the `get_with_context()` protocol method for intelligence services
via **mechanism B** (registry-sourced): it routes through
`self.relationships.get_with_context`, whose edge vocabulary comes from the
domain's `DomainConfig.cross_domain_relationship_types` (the registry single
source of truth).

Inherited by all 6 Activity Domain intelligence services plus the curriculum
intelligence services: `PsIntelligenceService`, `LpIntelligenceService`, and
`KuIntelligenceService`. Parameterize with the domain model to get a typed
return: `class PsIntelligenceService(_CoreIntelligenceMixin[PathStep], ...)`.

One Path Forward (intent-traversal ↔ registry convergence): this shared base is
the single reader. The 6 activity domains no longer override it — they inherit
this mechanism-B implementation directly.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md,
     /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.services.relationships import UnifiedRelationshipService


class _CoreIntelligenceMixin[T]:
    """
    Shared `get_with_context()` for intelligence services (mechanism B).

    Generic in the domain model so subclasses get a typed return:
    `_CoreIntelligenceMixin[PathStep]` → `Result[tuple[PathStep, GraphContext]]`.

    Activity domain services additionally expose a domain-named alias
    from their per-domain wrapper.
    """

    # Populated by BaseAnalyticsService.__init__ (stores relationship_service).
    # boundary: this shared base is domain-agnostic — the relationship service's
    # (Ops, Model, DtoType) params are genuinely heterogeneous across the 9 domains
    # that inherit this mixin, so they cannot be pinned here (Any Usage Policy, Category C).
    relationships: UnifiedRelationshipService[Any, Any, Any] | None
    logger: Any

    @requires_graph_intelligence("get_with_context")
    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]:
        """
        Get entity with full graph context via mechanism B (registry-sourced).

        Routes through ``self.relationships.get_with_context`` — which sources its
        edge vocabulary from the domain config's ``cross_domain_relationship_types``
        (the registry, the single source of truth). Implements the
        IntelligenceOperations protocol.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (entity, GraphContext) tuple
        """
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="relationship_service required for get_with_context",
                    operation="get_with_context",
                )
            )
        return await self.relationships.get_with_context(uid, depth)
