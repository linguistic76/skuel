"""
Context Operations Mixin
========================

Provides graph context retrieval and enrichment operations.

These methods enable fetching entities with their graph neighborhood context
in a single query, supporting rich entity views with related data.

REQUIRES (Mixin Dependencies):
    - CrudOperationsMixin: Uses get() method for entity retrieval

PROVIDES (Methods for Intelligence/Routes):
    - get_with_content: Get entity with full content loaded
    - get_with_context: Get entity with graph neighborhood context
    - _basic_get_with_context: Implementation for entities not in registry
    - _parse_context_result: Parse context query results

Methods:
    - get_with_content: Get entity with full content loaded
    - get_with_context: Get entity with graph neighborhood context
    - _basic_get_with_context: Implementation for entities not in registry
    - _parse_context_result: Parse context query results
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.query.cypher.post_processors import apply_processor
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Sequence
    from logging import Logger


class ContextOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing graph context retrieval operations.

    Uses registry-driven query generation from UnifiedRelationshipRegistry
    to fetch entities with their graph neighborhood in a single query.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For logging
        entity_label: str - Neo4j node label
        _content_field: str - Field containing content
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _prerequisite_relationships: list[str] - For basic context queries
        get: Method to get entity by UID
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    _content_field: str
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None
    _prerequisite_relationships: ClassVar[list[str]]

    @property
    def entity_label(self) -> str:
        """Entity label - must be provided by composing class."""
        raise NotImplementedError

    async def get(self, uid: str) -> Result[T]:
        """Get entity by UID - provided by CrudOperationsMixin."""
        raise NotImplementedError

    # ========================================================================
    # CONTENT OPERATIONS (January 2026 - Unified)
    # ========================================================================

    @with_error_handling("get_with_content", error_type="database", uid_param="uid")
    async def get_with_content(self, uid: str) -> Result[tuple[T, str | None]]:
        """
        Get entity with full content loaded.

        For entities with separate content storage, this ensures full content
        is retrieved regardless of storage strategy.

        Args:
            uid: Entity UID

        Returns:
            Result[tuple[T, str | None]]: Entity and its content
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        entity_result = await self.get(uid)
        if entity_result.is_error:
            return Result.fail(entity_result.expect_error())

        entity = entity_result.value
        if entity is None:
            return Result.fail(Errors.not_found(resource=self.entity_label, identifier=uid))

        # Check if content is already populated in entity
        content: str | None = getattr(entity, self._content_field, None)

        # If no inline content, try to fetch from content storage
        if not content:
            content_method = getattr(self.backend, "get_content", None)
            if content_method:
                content_result = await content_method(uid)
                if content_result.is_ok:
                    content = content_result.value

        return Result.ok((entity, content))

    @with_error_handling("get_with_context", error_type="database", uid_param="uid")
    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        include_relationships: Sequence[str] | None = None,
        exclude_relationships: Sequence[str] | None = None,
    ) -> Result[T]:
        """
        Get entity with graph neighborhood context.

        Fetches the entity plus related entities in a single query.
        Context is stored in entity.metadata["graph_context"].

        **January 2026 Consolidation:**
        Uses registry-driven query generation from UnifiedRelationshipRegistry.
        Domain-specific get_with_context() overrides are no longer needed.

        Args:
            uid: Entity UID
            depth: How many relationship hops to include (default: 2)
            min_confidence: Minimum relationship confidence (default: 0.7)
            include_relationships: Only include these context_field_names (None = all)
            exclude_relationships: Exclude these context_field_names (None = none)

        Returns:
            Result[T]: Entity with graph_context in metadata
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        # Check registry before attempting query generation (avoid exception for control flow)
        from core.models.unified_relationship_registry import UNIFIED_REGISTRY_BY_LABEL

        if self.entity_label not in UNIFIED_REGISTRY_BY_LABEL:
            # Entity not in registry - use basic 3-relationship pattern
            return await self._basic_get_with_context(uid, depth, min_confidence)

        # Registry-driven generation
        from core.models.query.cypher.context_query_generator import generate_context_query

        query, params = generate_context_query(
            entity_label=self.entity_label,
            include_relationships=include_relationships,
            exclude_relationships=exclude_relationships,
            default_confidence=min_confidence,
        )
        params["uid"] = uid

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records or len(records) == 0:
            return Result.fail(Errors.not_found(resource=self.entity_label, identifier=uid))

        record = records[0]
        return self._parse_context_result(record, UNIFIED_REGISTRY_BY_LABEL.get(self.entity_label))

    async def _basic_get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[T]:
        """
        Basic get_with_context for entities not in UnifiedRelationshipRegistry.

        Uses a standard 3-relationship pattern (prerequisites, enables, related).
        Entities in the registry use the richer registry-driven query generation.
        """
        label = self.entity_label
        prereq_rels = (
            "|".join(self._prerequisite_relationships)
            if self._prerequisite_relationships
            else "REQUIRES"
        )

        query = f"""
        MATCH (n:{label} {{uid: $uid}})

        // Prerequisites (outgoing REQUIRES relationships)
        OPTIONAL MATCH (n)-[r1:{prereq_rels}]->(prereq:{label})
        WHERE coalesce(r1.confidence, 1.0) >= $min_confidence
        WITH n, collect(DISTINCT {{
            uid: prereq.uid,
            title: prereq.title,
            confidence: coalesce(r1.confidence, 1.0)
        }}) as prerequisites

        // Entities this enables (incoming relationships)
        OPTIONAL MATCH (enabled:{label})-[r2:{prereq_rels}]->(n)
        WHERE coalesce(r2.confidence, 1.0) >= $min_confidence
        WITH n, prerequisites, collect(DISTINCT {{
            uid: enabled.uid,
            title: enabled.title,
            confidence: coalesce(r2.confidence, 1.0)
        }}) as enables

        // Related entities (lateral connections)
        OPTIONAL MATCH (n)-[r3:RELATED_TO|SIMILAR_TO]-(related:{label})
        WHERE coalesce(r3.confidence, 1.0) >= $min_confidence * 0.8
        WITH n, prerequisites, enables, collect(DISTINCT {{
            uid: related.uid,
            title: related.title,
            confidence: coalesce(r3.confidence, 1.0)
        }}) as related

        RETURN n, prerequisites, enables, related
        """

        result = await self.backend.execute_query(
            query, {"uid": uid, "depth": depth, "min_confidence": min_confidence}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records or len(records) == 0:
            return Result.fail(Errors.not_found(resource=self.entity_label, identifier=uid))

        record = records[0]
        node_data = record.get(self.entity_label.lower(), record.get("n", {}))

        # Build entity with context - fail-fast if not configured
        if not self._dto_class or not self._model_class:
            return Result.fail(
                Errors.system(
                    message=f"{self.entity_label} service must configure _dto_class and _model_class",
                    operation="_basic_get_with_context",
                )
            )

        dto = self._dto_class.from_dict(dict(node_data))
        dto.metadata = dto.metadata or {}
        dto.metadata["graph_context"] = {
            "prerequisites": [p for p in record.get("prerequisites", []) if p.get("uid")],
            "enables": [e for e in record.get("enables", []) if e.get("uid")],
            "related": [r for r in record.get("related", []) if r.get("uid")],
            "query_timestamp": datetime.now(UTC).isoformat(),
        }
        return Result.ok(self._model_class.from_dto(dto))

    def _parse_context_result(
        self,
        record: dict,
        config: Any | None,
    ) -> Result[T]:
        """
        Parse context query result into domain model with metadata.

        Extracts relationship data from record using the config's relationship definitions.
        This is THE method that handles results from generate_context_query().

        Args:
            record: Query result record with entity and relationship collections
            config: DomainRelationshipConfig from registry (None for unregistered entities)

        Returns:
            Result[T]: Entity with graph_context populated in metadata
        """
        # Get entity data
        node_data = record.get("entity", {})
        if not node_data:
            node_data = record.get(self.entity_label.lower(), record.get("n", {}))

        if not self._dto_class or not self._model_class:
            return Result.fail(Errors.system(message="Missing DTO or model class configuration"))

        # Build entity from node data
        dto = self._dto_class.from_dict(dict(node_data))
        dto.metadata = dto.metadata or {}

        # Build graph_context from relationship data
        graph_context: dict[str, Any] = {
            "query_timestamp": datetime.now(UTC).isoformat(),
        }

        relationships = getattr(config, "relationships", None) if config else None
        if relationships:
            # Extract each relationship's data from the record
            for rel_def in relationships:
                alias = rel_def.context_field_name
                if alias in record:
                    value = record[alias]
                    if rel_def.single:
                        # Single result (e.g., goal_context, habit_context)
                        graph_context[alias] = value
                    else:
                        # List result - filter out empty entries
                        if isinstance(value, list):
                            graph_context[alias] = [v for v in value if v and v.get("uid")]
                        else:
                            graph_context[alias] = value
        else:
            # Unregistered entity: extract standard relationship aliases
            for key in ["prerequisites", "enables", "related", "dependents"]:
                if key in record:
                    value = record[key]
                    if isinstance(value, list):
                        graph_context[key] = [v for v in value if v and v.get("uid")]
                    else:
                        graph_context[key] = value

        # Post-query processors for calculated fields (registry-driven, January 2026)
        post_processors = getattr(config, "post_processors", None) if config else None
        if post_processors:
            for processor in post_processors:
                source_data = graph_context.get(processor.source_field, [])
                graph_context[processor.target_field] = apply_processor(
                    processor.processor_name, source_data
                )

        dto.metadata["graph_context"] = graph_context
        return Result.ok(self._model_class.from_dto(dto))
