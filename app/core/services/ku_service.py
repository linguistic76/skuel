"""
KuService - Atomic Knowledge Unit Facade
==========================================

Facade for atomic Ku operations. Delegates to:
- .core: CRUD operations (KuCoreService)
- .search: Search and namespace queries (KuSearchService)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.services.ku.ku_core_service import KuCoreService
from core.services.ku.ku_search_service import KuSearchService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import KuBackend


class KuService:
    """Facade for atomic Knowledge Unit operations.

    Ku is a lightweight ontology/reference node — a single definable thing:
    concept, state, principle, substance, practice, or value.
    """

    def __init__(
        self,
        core: KuCoreService,
        search: KuSearchService,
        backend: "KuBackend | None" = None,
    ) -> None:
        self.core = core
        self.search = search
        self.backend = backend

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
    ) -> Result[KuDTO]:
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

    async def get_ku(self, uid: str) -> Result[Ku]:
        """Get a Knowledge Unit by UID."""
        return await self.core.get_ku(uid)

    # =========================================================================
    # SEARCH (delegated to search)
    # =========================================================================

    async def search(self, query: str, user_uid: str | None = None) -> Result[list[Any]]:
        """Full-text search across Kus."""
        return await self.search.search(query, user_uid)

    async def get_by_namespace(self, namespace: str) -> Result[list[dict[str, Any]]]:
        """Get all Kus in a specific namespace."""
        return await self.search.get_by_namespace(namespace)

    async def search_by_alias(self, alias: str) -> Result[list[dict[str, Any]]]:
        """Search Kus by alias (alternative name)."""
        return await self.search.search_by_alias(alias)

    # =========================================================================
    # GRAPH (reverse traversal via backend)
    # =========================================================================

    async def get_articles(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all Articles that use this atomic Ku via USES_KU."""
        if self.backend is None:
            return Result.fail("KuService backend not configured for graph operations")
        return await self.backend.get_articles_using(ku_uid)
