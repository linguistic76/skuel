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

from abc import abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.models.post_processors import apply_processor
from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.relationship_names import RelationshipName
from core.ports import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Sequence
    from logging import Logger


class ContextOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing graph context retrieval operations.

    Uses registry-driven query generation from RelationshipRegistry
    to fetch entities with their graph neighborhood in a single query.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For logging
        entity_label: str - Neo4j base-label for Cypher matching (e.g., "Entity", "Ku")
        config_lookup_label: str - LABEL_CONFIGS registry key (e.g., "Task", "PathStep")
        _content_field: str - Field containing content
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _prerequisite_relationships: tuple[RelationshipName, ...] - For basic context queries
        get: Method to get entity by UID
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    _content_field: str
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None
    _prerequisite_relationships: tuple[RelationshipName, ...]

    @property
    @abstractmethod
    def entity_label(self) -> str:
        """Neo4j base-label (e.g., ``"Entity"``, ``"Ku"``) - provided by composing class."""
        ...

    @property
    @abstractmethod
    def config_lookup_label(self) -> str:
        """LABEL_CONFIGS registry key (e.g., ``"Task"``, ``"PathStep"``) - provided by composing class."""
        ...

    @abstractmethod
    async def get(self, uid: str) -> Result[T]:
        """Get entity by UID - provided by CrudOperationsMixin."""
        ...

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
            return Result.fail(entity_result)

        entity = entity_result.value
        if entity is None:
            return Result.fail(Errors.not_found(resource=self.config_lookup_label, identifier=uid))

        # Check if content is already populated in entity
        content: str | None = getattr(entity, self._content_field, None)

        # If no inline content, fetch from the :Content subtree. A read
        # failure propagates — silently degrading to (entity, None) would
        # render a body-less page and mask a real database error.
        if not content:
            content_method = getattr(self.backend, "get_content", None)
            if content_method:
                content_result = await content_method(uid)
                if content_result.is_error:
                    return Result.fail(content_result)
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
        Uses registry-driven query generation from RelationshipRegistry.
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
        from core.models.relationship_registry import LABEL_CONFIGS

        if self.config_lookup_label not in LABEL_CONFIGS:
            # Entity not in registry - use basic 3-relationship pattern
            return await self._basic_get_with_context(uid, depth, min_confidence)

        result = await self.backend.context_query_raw(
            uid,
            include_relationships=list(include_relationships) if include_relationships else None,
            exclude_relationships=list(exclude_relationships) if exclude_relationships else None,
            default_confidence=min_confidence,
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records or len(records) == 0:
            return Result.fail(Errors.not_found(resource=self.config_lookup_label, identifier=uid))

        record = records[0]
        return self._parse_context_result(record, LABEL_CONFIGS.get(self.config_lookup_label))

    async def _basic_get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[T]:
        """
        Basic get_with_context for entities not in RelationshipRegistry.

        Uses a standard 3-relationship pattern (prerequisites, enables, related).
        Entities in the registry use the richer registry-driven query generation.
        """
        prereq_rels = (
            "|".join(rel.value for rel in self._prerequisite_relationships)
            if self._prerequisite_relationships
            else RelationshipName.REQUIRES_KNOWLEDGE.value
        )

        result = await self.backend.basic_context_query_raw(
            uid=uid,
            prereq_rels=prereq_rels,
            min_confidence=min_confidence,
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records or len(records) == 0:
            return Result.fail(Errors.not_found(resource=self.config_lookup_label, identifier=uid))

        record = records[0]
        node_data = record.get(self.config_lookup_label.lower(), record.get("n", {}))

        # Build entity with context - fail-fast if not configured
        if not self._dto_class or not self._model_class:
            return Result.fail(
                Errors.system(
                    message=f"{self.config_lookup_label} service must configure _dto_class and _model_class",
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
            node_data = record.get(self.config_lookup_label.lower(), record.get("n", {}))

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


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import ContextOperations

    _protocol_check: type[ContextOperations[Any]] = ContextOperationsMixin  # type: ignore[type-abstract]
