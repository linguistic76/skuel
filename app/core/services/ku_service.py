"""
KuService - Atomic Knowledge Unit Facade
==========================================

Facade for atomic Ku operations. Delegates to 4 sub-services via factory:
- .core: CRUD operations (KuCoreService)
- .search_service: Search and namespace queries (KuSearchService)
- .relationships: Graph relationship operations (UnifiedRelationshipService)
- .intelligence: Graph analytics (KuIntelligenceService)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import KuBackend
    from core.models.graph_context import GraphContext
    from core.models.ku.ku import Ku
    from core.services.ku.ku_intelligence_service import KuIntelligenceService

logger = get_logger(__name__)


class KuService:
    """Facade for atomic Knowledge Unit operations.

    Ku is a lightweight ontology/reference node — a single definable thing:
    concept, state, principle, substance, practice, or value.

    Uses create_curriculum_sub_services() factory for consistent initialization,
    matching LS and Activity Domain patterns.
    """

    def __init__(
        self,
        backend: Any = None,
        graph_intel: Any = None,
        event_bus: Any = None,
    ) -> None:
        if not backend:
            raise ValueError(
                "KuService backend is REQUIRED. "
                "SKUEL follows fail-fast architecture — all required dependencies "
                "must be provided at initialization."
            )
        if not graph_intel:
            raise ValueError(
                "KuService graph_intel is REQUIRED. "
                "SKUEL follows fail-fast architecture — graph intelligence enables "
                "cross-domain queries for curriculum domains."
            )

        from core.utils.curriculum_domain_config import (
            CurriculumCommonSubServices,
            create_curriculum_sub_services,
        )

        common: CurriculumCommonSubServices[KuIntelligenceService] = create_curriculum_sub_services(
            domain="ku",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )

        self.core = common.core
        self.search_service = common.search
        self.relationships = common.relationships
        self.intelligence: KuIntelligenceService = common.intelligence
        self.backend: KuBackend = backend  # For get_lessons() reverse traversal

        logger.debug("KuService facade initialized with 4 sub-services via factory")

    # =========================================================================
    # CRUD (delegated to core)
    # =========================================================================

    async def create_ku(
        self,
        title: str,
        namespace: str | None = None,
        ku_category: str | None = None,
        aliases: list[str] | None = None,
        source: str | None = None,
        description: str | None = None,
        summary: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[Ku | None]:
        """Create a new atomic Knowledge Unit."""
        return await self.core.create_ku(
            title=title,
            namespace=namespace,
            ku_category=ku_category,
            aliases=aliases,
            source=source,
            description=description,
            summary=summary,
            domain=domain,
            tags=tags,
        )

    async def get_ku(self, uid: str) -> Result[Ku | None]:
        """Get a Knowledge Unit by UID."""
        return await self.core.get_ku(uid)

    # =========================================================================
    # SEARCH (delegated to search)
    # =========================================================================

    async def search(self, query: str, user_uid: str | None = None) -> Result[list[Any]]:
        """Full-text search across Kus."""
        return await self.search_service.search(query, user_uid)

    async def get_by_namespace(self, namespace: str) -> Result[list[dict[str, Any]]]:
        """Get all Kus in a specific namespace."""
        return await self.search_service.get_by_namespace(namespace)

    async def search_by_alias(self, alias: str) -> Result[list[dict[str, Any]]]:
        """Search Kus by alias (alternative name)."""
        return await self.search_service.search_by_alias(alias)

    # =========================================================================
    # INTELLIGENCE (delegated to intelligence)
    # =========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, GraphContext]]:
        """Get Ku with full graph context."""
        return await self.intelligence.get_with_context(uid, depth)

    async def get_usage_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """Count lessons, learning steps, and organized children for a Ku."""
        return await self.intelligence.get_usage_summary(ku_uid)

    # =========================================================================
    # GRAPH (reverse traversal via backend)
    # =========================================================================

    async def get_lessons(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all Lessons that use this atomic Ku via USES_KU."""
        if self.backend is None:
            return Result.fail(
                Errors.system("KuService backend not configured for graph operations")
            )
        return await self.backend.get_lessons_using(ku_uid)
