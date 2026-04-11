"""
Ingestion Backend
==================

Backend for ingestion audit trail and incremental state tracking.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 12 execute_query calls:
- IngestionHistoryService (7 calls → 7 methods)
- IngestionTracker (5 calls → 5 methods)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class IngestionBackend:
    """Backend for ingestion persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # HISTORY — IngestionHistory node CRUD
    # ========================================================================

    async def ensure_history_constraints(self) -> Result[list[dict[str, Any]]]:
        """Create unique constraint on IngestionHistory.operation_id."""
        return await self._executor.execute_query(
            """
            CREATE CONSTRAINT IF NOT EXISTS
            FOR (ih:IngestionHistory)
            REQUIRE ih.operation_id IS UNIQUE
            """
        )

    async def create_history_entry(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Create an IngestionHistory node."""
        return await self._executor.execute_query(
            """
            CREATE (ih:IngestionHistory {
                operation_id: $operation_id,
                operation_type: $operation_type,
                started_at: datetime($started_at),
                status: 'in_progress',
                user_uid: $user_uid,
                source_path: $source_path
            })
            RETURN ih.operation_id AS operation_id
            """,
            params,
        )

    async def update_history_entry(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Update an IngestionHistory node with completion stats."""
        return await self._executor.execute_query(
            """
            MATCH (ih:IngestionHistory {operation_id: $operation_id})
            SET ih.completed_at = datetime($completed_at),
                ih.status = $status,
                ih.total_files = $total_files,
                ih.successful = $successful,
                ih.failed = $failed,
                ih.nodes_created = $nodes_created,
                ih.nodes_updated = $nodes_updated,
                ih.relationships_created = $relationships_created,
                ih.duration_seconds = $duration_seconds
            """,
            params,
        )

    async def create_error_nodes(
        self, operation_id: str, errors: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]:
        """Create IngestionError nodes linked to an IngestionHistory entry."""
        return await self._executor.execute_query(
            """
            MATCH (ih:IngestionHistory {operation_id: $operation_id})
            UNWIND $errors AS error
            CREATE (e:IngestionError {
                file: error.file,
                error: error.error,
                stage: error.stage,
                error_type: error.error_type,
                entity_type: error.entity_type,
                suggestion: error.suggestion
            })
            CREATE (ih)-[:HAD_ERROR]->(e)
            """,
            {"operation_id": operation_id, "errors": errors},
        )

    async def get_history(self, limit: int, offset: int) -> Result[list[dict[str, Any]]]:
        """Retrieve paginated ingestion history with error nodes."""
        return await self._executor.execute_query(
            """
            MATCH (ih:IngestionHistory)
            OPTIONAL MATCH (ih)-[:HAD_ERROR]->(e:IngestionError)
            WITH ih, COLLECT(e) AS errors
            RETURN ih, errors
            ORDER BY ih.started_at DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"limit": limit, "offset": offset},
        )

    async def get_history_entry(self, operation_id: str) -> Result[list[dict[str, Any]]]:
        """Get a specific IngestionHistory entry with error nodes."""
        return await self._executor.execute_query(
            """
            MATCH (ih:IngestionHistory {operation_id: $operation_id})
            OPTIONAL MATCH (ih)-[:HAD_ERROR]->(e:IngestionError)
            WITH ih, COLLECT(e) AS errors
            RETURN ih, errors
            """,
            {"operation_id": operation_id},
        )

    async def get_history_count(self) -> Result[list[dict[str, Any]]]:
        """Get total count of IngestionHistory entries."""
        return await self._executor.execute_query(
            """
            MATCH (ih:IngestionHistory)
            RETURN COUNT(ih) AS total
            """
        )

    # ========================================================================
    # TRACKER — IngestionMetadata node CRUD
    # ========================================================================

    async def ensure_tracker_constraints(self) -> Result[list[dict[str, Any]]]:
        """Create unique constraint on IngestionMetadata.file_path."""
        return await self._executor.execute_query(
            """
            CREATE CONSTRAINT ingestion_metadata_file_path IF NOT EXISTS
            FOR (s:IngestionMetadata) REQUIRE s.file_path IS UNIQUE
            """
        )

    async def get_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]:
        """Fetch ingestion metadata for given file paths."""
        return await self._executor.execute_query(
            """
            UNWIND $paths AS path
            MATCH (s:IngestionMetadata {file_path: path})
            RETURN s.file_path AS file_path,
                   s.content_hash AS content_hash,
                   s.file_mtime AS file_mtime,
                   s.last_ingested_at AS last_ingested_at,
                   s.entity_uid AS entity_uid
            """,
            {"paths": paths},
        )

    async def update_ingestion_metadata(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """Upsert ingestion metadata for a single file."""
        return await self._executor.execute_query(
            """
            MERGE (s:IngestionMetadata {file_path: $file_path})
            SET s.content_hash = $content_hash,
                s.file_mtime = $file_mtime,
                s.last_ingested_at = datetime(),
                s.entity_uid = $entity_uid
            """,
            params,
        )

    async def update_ingestion_metadata_batch(
        self, items: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]:
        """Batch upsert ingestion metadata for multiple files."""
        return await self._executor.execute_query(
            """
            UNWIND $items AS item
            MERGE (s:IngestionMetadata {file_path: item.file_path})
            SET s.content_hash = item.content_hash,
                s.file_mtime = item.file_mtime,
                s.last_ingested_at = datetime(),
                s.entity_uid = item.entity_uid
            RETURN count(s) AS updated
            """,
            {"items": items},
        )

    async def delete_ingestion_metadata(self, paths: list[str]) -> Result[list[dict[str, Any]]]:
        """Delete ingestion metadata for removed files."""
        return await self._executor.execute_query(
            """
            UNWIND $paths AS path
            MATCH (s:IngestionMetadata {file_path: path})
            DETACH DELETE s
            RETURN count(*) AS deleted
            """,
            {"paths": paths},
        )
