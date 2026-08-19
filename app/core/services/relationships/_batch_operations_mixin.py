"""
Batch Operations Mixin
======================

N+1 elimination helpers for relationship queries.

Provides:
    batch_has_relationship: Check relationship existence for multiple entities
    batch_count_related: Count related entities for multiple entities
    batch_get_related_uids: Get related UIDs for multiple entities

Requires on concrete class:
    config, backend, logger (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.ports.base_protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig


class BatchOperationsMixin[Ops: BackendOperations]:
    """
    Mixin providing batch relationship query methods.

    Methods eliminate N+1 query patterns by delegating to backend batch methods.

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Ops
    logger: Any

    @with_error_handling("batch_has_relationship", error_type="database")
    async def batch_has_relationship(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, bool]]:
        """
        Check if multiple entities have relationships of a given type.

        This eliminates N+1 queries by using UNWIND in a single query.

        Args:
            relationship_key: Key from config
            entity_uids: List of entity UIDs

        Returns:
            Result[dict[str, bool]] mapping uid → has_relationship
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        return await self.backend.batch_has_relationship(
            entity_label=self.config.entity_label,
            entity_uids=entity_uids,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
        )

    @with_error_handling("batch_count_related", error_type="database")
    async def batch_count_related(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, int]]:
        """
        Count related entities for multiple entities.

        Args:
            relationship_key: Key from config
            entity_uids: List of entity UIDs

        Returns:
            Result[dict[str, int]] mapping uid → count
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        return await self.backend.batch_count_related(
            entity_label=self.config.entity_label,
            entity_uids=entity_uids,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
        )

    @with_error_handling("batch_get_related_uids", error_type="database")
    async def batch_get_related_uids(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, list[str]]]:
        """
        Get related entity UIDs for multiple entities in a single query.

        Eliminates N+1 query pattern when fetching relationships for multiple entities.

        Args:
            relationship_key: Key from config (e.g., "knowledge", "principles")
            entity_uids: List of entity UIDs to query

        Returns:
            Result[dict[str, list[str]]] mapping entity_uid → list of related UIDs
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        return await self.backend.batch_get_related_uids(
            entity_label=self.config.entity_label,
            entity_uids=entity_uids,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
        )
