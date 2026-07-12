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
    from core.models.relationship_names import RelationshipName


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

    async def get_tracked_files_under(self, path_prefix: str) -> Result[list[dict[str, Any]]]:
        """List all tracked (file_path, entity_uid, content_hash) rows under a directory prefix.

        Used by deletion reconciliation: tracked files that no longer exist on
        disk are vault deletions to propagate. ``content_hash`` feeds the
        move-detection pre-pass — a gone row and a new file sharing a hash is
        a rename, not a delete+create. The prefix must end with the path
        separator so /vault/a doesn't match /vault/abc.
        """
        return await self._executor.execute_query(
            """
            MATCH (s:IngestionMetadata)
            WHERE s.file_path STARTS WITH $path_prefix
            RETURN s.file_path AS file_path, s.entity_uid AS entity_uid,
                   s.content_hash AS content_hash
            """,
            {"path_prefix": path_prefix},
        )

    async def get_live_entity_uids(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Which of ``uids`` name a live node, across the three uid-bearing shapes.

        Mirrors the shapes ``delete_entities_with_metadata`` can delete
        (:Entity multi-label, :Group, :Expense). Used by the move-detection
        pre-pass as its live-node guard: a stale tracker row whose uid names
        no node is not a move source — rewriting it would attach a
        hand-deleted entity's identity to the new path.
        """
        return await self._executor.execute_query(
            """
            UNWIND $uids AS uid
            OPTIONAL MATCH (e:Entity {uid: uid})
            OPTIONAL MATCH (g:Group {uid: uid})
            OPTIONAL MATCH (x:Expense {uid: uid})
            WITH uid, e, g, x
            WHERE e IS NOT NULL OR g IS NOT NULL OR x IS NOT NULL
            RETURN uid AS uid
            """,
            {"uids": uids},
        )

    async def get_entity_contents(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Last-ingested body (``Entity.content``) for each live entity among ``uids``.

        Feeds the move pre-pass's similarity matching (rename + edit in one
        sync): the gone row's node still holds the body as it was last
        ingested, which is compared against new files' resolved on-disk
        content — no extra fingerprint storage needed. :Entity only — the
        other uid-bearing shapes (:Group, :Expense) carry no comparable body,
        so their rows simply never similarity-match (safe delete+create).
        A returned row doubles as the live-node proof for its uid. Nodes
        with no ``content`` yield no row; body-chunked types (Ku, PathStep)
        store content on the :Content subtree, not the node, so they are
        naturally excluded — they carry authored uids and never need this.
        """
        return await self._executor.execute_query(
            """
            UNWIND $uids AS uid
            MATCH (e:Entity {uid: uid})
            WHERE e.content IS NOT NULL AND trim(e.content) <> ''
            RETURN uid AS uid, e.content AS content
            """,
            {"uids": uids},
        )

    async def get_entity_owner_uids(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Owner for each user-owned node among ``uids``.

        Covers every uid-bearing shape ``delete_entities_with_metadata`` can
        delete (Kody #522): :Entity carries ``user_uid``, :Group carries
        ``owner_uid`` (stamped from the uploading user — see
        ``owner_uid_from_user_uid`` in ingestion config), :Expense carries
        ``user_uid``. Ownerless nodes (SHARED curriculum, by design) yield no
        row. Used by deletion reconciliation to refuse cross-owner deletes: a
        tracked node owned by a different user than the syncing vault's owner
        is skipped, not deleted.
        """
        return await self._executor.execute_query(
            """
            UNWIND $uids AS uid
            OPTIONAL MATCH (e:Entity {uid: uid})
            OPTIONAL MATCH (g:Group {uid: uid})
            OPTIONAL MATCH (x:Expense {uid: uid})
            WITH uid, coalesce(e.user_uid, g.owner_uid, x.user_uid) AS owner_uid
            WHERE owner_uid IS NOT NULL
            RETURN uid AS uid, owner_uid AS user_uid
            """,
            {"uids": uids},
        )

    async def delete_entities_with_metadata(
        self, items: list[dict[str, str]]
    ) -> Result[list[dict[str, Any]]]:
        """Delete vault-removed entities, their content subtree, and tracking rows.

        Each item carries {file_path, entity_uid}. Matches the entity across the
        three uid-bearing node shapes ingestion can create (:Entity multi-label,
        :Group, :Expense). The content subtree hangs off the entity as
        (Entity)-[:HAS_CONTENT]->(Content)-[:HAS_CHUNK]->(ContentChunk) with
        (Content)-[:HAS_METADATA]->(ContentMetadata) — all of it is deleted
        leaf-first (DETACH DELETE on the entity alone would orphan the content
        side, leaving deleted material in chunk regeneration scans and the
        vector index). A canon-shelved Resource additionally hangs
        (Resource)-[:HAS_REFERENCE_CHUNK]->(ReferenceChunk) directly off the
        entity — deleted here too so reconciling a book away can't orphan its
        reference chunks + vectors in the referencechunk vector index (their
        own store's delete-then-create only covers a re-ingest, not entity
        removal). Missing entities (already deleted by hand) still get their
        metadata row cleaned up.
        """
        return await self._executor.execute_query(
            """
            UNWIND $items AS item
            MATCH (s:IngestionMetadata {file_path: item.file_path})
            OPTIONAL MATCH (e:Entity {uid: item.entity_uid})
            OPTIONAL MATCH (g:Group {uid: item.entity_uid})
            OPTIONAL MATCH (x:Expense {uid: item.entity_uid})
            OPTIONAL MATCH (e)-[:HAS_CONTENT]->(content:Content)
            OPTIONAL MATCH (content)-[:HAS_CHUNK]->(chunk:ContentChunk)
            OPTIONAL MATCH (content)-[:HAS_METADATA]->(meta:ContentMetadata)
            OPTIONAL MATCH (e)-[:HAS_REFERENCE_CHUNK]->(refchunk:ReferenceChunk)
            DETACH DELETE chunk, meta, refchunk
            WITH DISTINCT item, s, e, g, x, content
            DETACH DELETE content
            WITH DISTINCT item, s, e, g, x
            DETACH DELETE e, g, x, s
            RETURN item.file_path AS file_path, item.entity_uid AS entity_uid
            """,
            {"items": items},
        )

    async def delete_edge_with_metadata(
        self, file_path: str, from_uid: str, to_uid: str, rel_type: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """Delete the relationship a vault-removed Edge YAML created, plus its tracking row.

        ``rel_type`` is a ``RelationshipName`` — the enum type makes the
        interpolation injection-safe, mirroring ``IngestionWriteBackend.ingest_edge``.
        A missing relationship (already removed by hand) still cleans up the
        metadata row.
        """
        return await self._executor.execute_query(
            f"""
            MATCH (s:IngestionMetadata {{file_path: $file_path}})
            OPTIONAL MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            DELETE r
            WITH DISTINCT s
            DETACH DELETE s
            RETURN $file_path AS file_path
            """,
            {"file_path": file_path, "from_uid": from_uid, "to_uid": to_uid},
        )
