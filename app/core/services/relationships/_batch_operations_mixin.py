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

from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig


class BatchOperationsMixin:
    """
    Mixin providing batch relationship query methods.

    Methods eliminate N+1 query patterns by using UNWIND in single queries.

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Any
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

        # Build batch query
        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, count(related) > 0 AS has_relationship
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Transform to dict
        return Result.ok(
            {
                str(record["entity_uid"]): record.get("has_relationship", False)
                for record in result.value
            }
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

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, count(related) AS count
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {str(record["entity_uid"]): record.get("count", 0) for record in result.value}
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

        Example:
            # Instead of N+1:
            # for habit in habits:
            #     uids = await service.get_related_uids("knowledge", habit.uid)
            #
            # Use batch:
            result = await service.batch_get_related_uids("knowledge", [h.uid for h in habits])
            # Returns: {"habit:1": ["ku:a", "ku:b"], "habit:2": ["ku:c"], ...}
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

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, collect(related.uid) AS related_uids
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Build mapping, filtering out None values from collect()
        return Result.ok(
            {
                str(record["entity_uid"]): [
                    uid for uid in (record.get("related_uids") or []) if uid is not None
                ]
                for record in result.value
            }
        )
