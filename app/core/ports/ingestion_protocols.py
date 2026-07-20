"""
Ingestion Protocols
====================

Protocols for the ingestion persistence layer (ADR-044). Three contracts:

- ``IngestionBackendOperations`` — ingestion audit trail + incremental state.
  Implementation: adapters/persistence/neo4j/ingestion_backend.py
- ``IngestionWriteOperations`` — entity/edge graph writes + existence checks.
  Implementation: adapters/persistence/neo4j/ingestion_write_backend.py
- ``BulkUpsertOperations`` — bulk node upsert / constraints / delete.
  Implementation: adapters/persistence/neo4j/bulk_upsert_backend.py

Consumers: UnifiedIngestionService, batch helpers, validator, IngestionTracker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ingestion.ingestion_types import IngestionResult, RelationshipConfig
    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_names import RelationshipName
    from core.ports.query_types import EntityContentRow


@runtime_checkable
class IngestionBackendOperations(Protocol):
    """Backend operations for ingestion persistence.

    Covers two services:
    - IngestionHistoryService: audit trail for ingestion operations
    - IngestionTracker: incremental ingestion state (file hash/mtime)
    """

    # ================================================================
    # HISTORY — IngestionHistory node CRUD
    # ================================================================

    async def ensure_history_constraints(self) -> Result[list[dict[str, Any]]]: ...

    async def create_history_entry(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def update_history_entry(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def create_error_nodes(
        self, operation_id: str, errors: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_history(self, limit: int, offset: int) -> Result[list[dict[str, Any]]]: ...

    async def get_history_entry(self, operation_id: str) -> Result[list[dict[str, Any]]]: ...

    async def get_history_count(self) -> Result[list[dict[str, Any]]]: ...

    # ================================================================
    # TRACKER — IngestionMetadata node CRUD
    # ================================================================

    async def ensure_tracker_constraints(self) -> Result[list[dict[str, Any]]]: ...

    async def get_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def update_ingestion_metadata(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]: ...

    async def update_ingestion_metadata_batch(
        self, items: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]: ...

    async def delete_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def get_tracked_files_under(self, path_prefix: str) -> Result[list[dict[str, Any]]]: ...

    async def get_entity_owner_uids(self, uids: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def get_live_entity_uids(self, uids: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def get_entity_contents(self, uids: list[str]) -> Result[list[EntityContentRow]]: ...

    async def delete_entities_with_metadata(
        self, items: list[dict[str, str]]
    ) -> Result[list[dict[str, Any]]]: ...

    async def delete_edge_with_metadata(
        self, file_path: str, from_uid: str, to_uid: str, rel_type: RelationshipName
    ) -> Result[list[dict[str, Any]]]: ...


@runtime_checkable
class IngestionWriteOperations(Protocol):
    """Entity/edge graph writes and existence checks for the ingestion pipeline.

    Exception-based (raises ``NEO4J_EXCEPTIONS``), matching how the ingestion
    service and batch helpers already handle failures. ``rel_type`` is a
    ``RelationshipName`` and ``label`` a ``NeoLabel`` — the enums are the
    injection-safety guarantee for the interpolated Cypher.
    """

    async def ingest_edge(
        self, from_uid: str, to_uid: str, rel_type: RelationshipName, props: dict[str, Any]
    ) -> list[dict[str, Any]]: ...

    async def entity_exists(self, uid: str) -> bool: ...

    async def create_group_ownership(self, owner_uid: str, group_uid: str) -> None: ...

    async def check_existing_entities(self, uids: list[str]) -> dict[str, bool]: ...

    async def find_existing_uids_for_label(self, label: NeoLabel, uids: list[str]) -> list[str]: ...

    async def resolve_path_suffixes(
        self, suffixes: list[str], root_prefix: str | None
    ) -> list[dict[str, Any]]: ...

    async def refresh_moc_organizes(
        self, source_uid: str, target_uids: list[str], protected_target_uids: list[str]
    ) -> int: ...


@runtime_checkable
class BulkUpsertOperations(Protocol):
    """Bulk node upsert / delete Cypher for ingestion (ADR-044).

    Stateless w.r.t. entity label — the ``entity_label``/``base_label`` are passed
    per call (sourced from ``ENTITY_CONFIGS``, trusted), so a single backend
    instance serves every entity type.

    Uniqueness constraints are NOT this backend's job: they are created at
    startup by ``Neo4jAdapter`` bootstrap + ``Neo4jSchemaManager``.
    """

    async def upsert_nodes(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]: ...

    async def create_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]: ...

    async def upsert_with_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]: ...

    async def delete_batch(
        self, entity_label: str, uids: list[str], cascade: bool = False
    ) -> Result[IngestionResult]: ...
