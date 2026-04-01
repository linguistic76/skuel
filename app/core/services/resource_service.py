"""
ResourceService — Curated Content Domain
=========================================

Minimal service for Resource entities (books, talks, films, podcasts, articles).
Resources are admin-curated shared content (ContentOrigin.CURATED, ContentScope.SHARED).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from core.models.resource.resource import Resource
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.resource")


class ResourceService:
    """
    Service for Resource entities.

    Thin facade over ResourceBackend — no sub-services needed at this stage.
    Resources are read-only from the user's perspective (admin-ingested via YAML).
    """

    def __init__(self, backend: Any) -> None:
        """
        Args:
            backend: ResourceBackend (UniversalNeo4jBackend[Resource])
        """
        self.backend = backend
        logger.info("ResourceService initialized")

    async def list_all(self, limit: int = 500) -> Result[list[Resource]]:
        """List all Resource entities sorted by title."""
        return await self.backend.list(limit=limit, sort_by="title")
