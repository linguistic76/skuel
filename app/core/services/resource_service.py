"""
ResourceService — Curated Content Domain
=========================================

Minimal service for Resource entities (books, talks, films, podcasts, articles).
Resources are admin-curated shared content (ContentOrigin.CURATED, ContentScope.SHARED).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.models.resource.resource import Resource
from core.models.type_hints import Neo4jProperties
from core.ports.resource_protocols import ResourceBackendOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.resource")


class ResourceService:
    """
    Service for Resource entities.

    Thin facade over ResourceBackend — no sub-services needed at this stage.
    Resources are read-only from the user's perspective (admin-ingested via YAML).
    """

    def __init__(self, backend: ResourceBackendOperations) -> None:
        """
        Args:
            backend: Resource backend port (ResourceBackend satisfies it)
        """
        self.backend = backend
        logger.info("ResourceService initialized")

    async def list_all(self, limit: int = 500) -> Result[list[Resource]]:
        """List all Resource entities sorted by title."""
        # backend.list() returns a (page, total_count) tuple; this facade
        # promises just the page, so unwrap it.
        result = await self.backend.list(limit=limit, sort_by="title")
        if result.is_error:
            return Result.fail(result)
        resources, _total = result.value
        return Result.ok(resources)

    async def get(self, uid: str) -> Result[Resource | None]:
        """Fetch one Resource by UID (None when absent — not an error).

        Backing the per-Resource detail page (the citation click destination).
        """
        return await self.backend.get(uid)

    async def get_citing_entities(self, uid: str) -> Result[list[Neo4jProperties]]:
        """The citers behind the Resource detail page's "Cited by" section.

        Reverse CITES_RESOURCE traversal — the Kus / PathSteps that point at this
        Resource, each row carrying uid/title/entity_type/locator. Backend:
        ResourceBackend.get_citing_entities.
        """
        result = await self.backend.get_citing_entities(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(row) for row in (result.value or [])])
