"""
Batch Operations Mixin
======================

N+1 elimination helpers for relationship queries.

Provides:
    batch_get_related_uids: Get related UIDs for multiple entities

Requires on concrete class:
    config, backend, logger (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.ports.base_protocols import BackendOperations
from core.services.relationships._keyed_read import resolve_keyed_read
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig


class BatchOperationsMixin[Ops: BackendOperations]:
    """
    Mixin providing the batch relationship query.

    It eliminates N+1 query patterns by delegating to the backend batch method.

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Ops
    logger: Any

    @with_error_handling("batch_get_related_uids", error_type="database")
    async def batch_get_related_uids(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, list[str]]]:
        """
        Get related entity UIDs for multiple entities in a single query.

        Eliminates N+1 query pattern when fetching relationships for multiple entities.
        The key's definition decides the edge type, the direction, the tier and the
        far end's kind (``resolve_keyed_read``), as in ``get_related_uids``.

        Args:
            relationship_key: Key from config (e.g., "knowledge", "principles")
            entity_uids: UIDs of this service's entities to query

        Returns:
            Result[dict[str, list[str]]] mapping entity_uid → list of related UIDs
        """
        read = resolve_keyed_read(self.config, relationship_key)
        if read.is_error:
            return Result.fail(read)

        if not entity_uids:
            return Result.ok({})

        return await self.backend.batch_get_related_uids(
            entity_uids=entity_uids,
            relationship_type=read.value.spec.relationship,
            direction=read.value.spec.direction,
            properties=read.value.properties,
            target_label=read.value.target_label,
        )
