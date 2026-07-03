"""
Neo4j Content Adapter
=====================

Persists the (Entity)-[:HAS_CONTENT]->(Content)-[:HAS_CHUNK]->(ContentChunk)
subtree. Write path: ingestion / batch re-chunk via ``store_content_with_chunks``
(MERGE upsert — ADR-074); embedding worker reads freshness and stores chunk
vectors here. Display reads use the inline ``Entity.content`` field, not this
adapter; re-chunk body reads go through ``BatchChunkingBackend``.
"""

__version__ = "1.0"


from typing import Any

from core.models.ps_content.content import CurriculumContent
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jContentAdapter:
    """
    Neo4j adapter for the Content/ContentChunk subtree.

    Manages Content nodes that store the body text of knowledge units.
    Content nodes are linked to Entity nodes via HAS_CONTENT relationship.
    """

    def __init__(self, neo4j_connection) -> None:
        """
        Initialize with Neo4j connection.

        Args:
            neo4j_connection: Neo4j database connection
        """
        self.neo4j = neo4j_connection

    async def delete_content_subtree(self, unit_uid: str) -> bool:
        """
        Delete an entity's full content subtree.

        (Entity)-[:HAS_CONTENT]->(Content)-[:HAS_CHUNK]->(ContentChunk) plus
        (Content)-[:HAS_METADATA]->(ContentMetadata) — deleted leaf-first,
        mirroring IngestionBackend.delete_entities_with_metadata (deleting the
        Content node alone would orphan chunks in the vector index and chunk
        regeneration scans). The explicit clear path for a PathStep re-ingested
        with an emptied body (ADR-074).

        Args:
            unit_uid: The knowledge unit's UID

        Returns:
            True if a subtree was deleted, False if none existed or on error
        """
        query = """
        MATCH (unit:Entity {uid: $uid})-[:HAS_CONTENT]->(content:Content)
        OPTIONAL MATCH (content)-[:HAS_CHUNK]->(chunk:ContentChunk)
        OPTIONAL MATCH (content)-[:HAS_METADATA]->(meta:ContentMetadata)
        DETACH DELETE chunk, meta
        WITH DISTINCT content
        DETACH DELETE content
        RETURN count(content) as deleted
        """

        try:
            result = await self.neo4j.execute_query(query, {"uid": unit_uid})
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to delete content subtree for {unit_uid}: {e}")
            return False

        if result and len(result) > 0 and result[0]["deleted"] > 0:
            logger.info(f"Deleted content subtree for knowledge unit: {unit_uid}")
            return True

        logger.debug(f"No content subtree to delete for: {unit_uid}")
        return False

    async def store_content_with_chunks(
        self,
        uid: str,
        content: CurriculumContent,
    ) -> bool:
        """
        Store content with its semantic chunks for RAG retrieval.

        Creates:
        - Content node with full text
        - ContentChunk nodes for each chunk
        - HAS_CHUNK relationships

        Args:
            uid: Knowledge unit UID,
            content: CurriculumContent with chunks

        Returns:
            True if successful
        """
        try:
            # Start transaction for atomic storage
            query = """
            // Match the knowledge unit
            MATCH (ku:Entity {uid: $uid})

            // Create or merge Content node
            MERGE (c:Content {uid: $uid})
            SET c.body = $body
            SET c.format = $format
            SET c.word_count = $word_count
            SET c.chunk_count = $chunk_count
            SET c.updated_at = datetime()

            // Link to knowledge unit
            MERGE (ku)-[:HAS_CONTENT]->(c)

            RETURN c.uid as uid
            """

            params = {
                "uid": uid,
                "body": content.body,
                "format": content.format,
                "word_count": content.word_count,
                "chunk_count": content.chunk_count,
            }

            # Execute main content storage
            result = await self.neo4j.execute_query(query, params)

            if not result:
                logger.error(f"Failed to store content for {uid}")
                return False

            # Store chunks if available
            if content.chunks:
                # Idempotency: drop only the chunks that no longer exist in the
                # new chunk set (uids are deterministic — parent_uid + index).
                # Surviving uids are MERGEd below with their embeddings
                # preserved when the text is unchanged, so a force re-ingest of
                # an identical body never wipes good chunk vectors.
                new_uids = [chunk.chunk_id for chunk in content.chunks]
                await self.neo4j.execute_query(
                    """
                    MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                    WHERE NOT chunk.uid IN $keep_uids
                    DETACH DELETE chunk
                    """,
                    {"uid": uid, "keep_uids": new_uids},
                )

                # MERGE keeps an existing chunk node; embedding fields are wiped
                # only when the stored embedding_source_text (what the vector was
                # generated from) no longer matches the incoming context_window —
                # a re-chunk of identical content keeps its embedding, and the
                # worker's freshness pre-check then skips re-generating it.
                chunk_query = """
                MATCH (c:Content {uid: $uid})
                MERGE (chunk:ContentChunk {uid: $chunk_uid})
                ON CREATE SET
                    chunk.created_at = datetime(),
                    chunk.embedding = null,
                    chunk.embedding_version = null,
                    chunk.embedding_model = null,
                    chunk.embedding_updated_at = null,
                    chunk.embedding_source_text = null
                SET chunk.chunk_type = $chunk_type,
                    chunk.text = $text,
                    chunk.start_index = $start_index,
                    chunk.end_index = $end_index,
                    chunk.context_window = $context_window,
                    chunk.chunking_version = $chunking_version
                FOREACH (_ IN CASE
                    WHEN chunk.embedding_source_text IS NULL
                      OR chunk.embedding_source_text <> $context_window
                    THEN [1] ELSE [] END |
                    SET chunk.embedding = null,
                        chunk.embedding_version = null,
                        chunk.embedding_model = null,
                        chunk.embedding_updated_at = null,
                        chunk.embedding_source_text = null)
                MERGE (c)-[r:HAS_CHUNK]->(chunk)
                SET r.sequence = $sequence
                RETURN chunk.uid
                """

                for i, chunk in enumerate(content.chunks):
                    chunk_params = {
                        "uid": uid,
                        "chunk_uid": chunk.chunk_id,
                        "chunk_type": chunk.chunk_type.value,
                        "text": chunk.text,
                        "context_window": chunk.context_window,
                        "start_index": chunk.chunk_index,
                        "end_index": chunk.word_count,
                        "chunking_version": chunk.chunking_version,
                        "sequence": i,
                    }

                    chunk_result = await self.neo4j.execute_query(chunk_query, chunk_params)

                    if chunk_result is None:
                        logger.error(f"Failed to create chunk {i} - query returned None")
                        logger.error(f"Chunk params: {chunk_params}")
                    else:
                        logger.debug(
                            f"Created chunk {i} ({chunk_params['chunk_type']}): {chunk_params['chunk_uid']}"
                        )

                logger.info(f"Stored {len(content.chunks)} chunks for {uid}")

            logger.debug(f"Successfully stored content with chunks for {uid}")
            return True

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to store content with chunks for {uid}: {e}")
            return False

    async def get_chunks(self, uid: str, chunk_type: str | None = None) -> list[dict[str, Any]]:
        """
        Retrieve chunks for a knowledge unit.

        PLANNED (unwired by intent — ruled 2026-07-02): zero production callers
        today; kept as the chunk-inspection read surface (RAG debugging, a
        future chunk-viewer UI). The live RAG path (vector_search_backend)
        traverses chunks in its own vector query and does not need this.
        Registered here because the bloat detector's PLANNED_METHODS registry
        only scans core/services/.

        Args:
            uid: Knowledge unit UID,
            chunk_type: Optional filter by chunk type

        Returns:
            List of chunk dictionaries
        """
        try:
            if chunk_type:
                query = """
                MATCH (c:Content {uid: $uid})-[r:HAS_CHUNK]->(chunk:ContentChunk)
                WHERE chunk.chunk_type = $chunk_type
                RETURN chunk, r.sequence as sequence
                ORDER BY r.sequence
                """
                params = {"uid": uid, "chunk_type": chunk_type}
            else:
                query = """
                MATCH (c:Content {uid: $uid})-[r:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN chunk, r.sequence as sequence
                ORDER BY r.sequence
                """
                params = {"uid": uid}

            result = await self.neo4j.execute_query(query, params)

            if not result:
                return []

            chunks = []
            for record in result:
                chunk_data = dict(record["chunk"])
                chunk_data["sequence"] = record["sequence"]
                chunks.append(chunk_data)

            logger.debug(f"Retrieved {len(chunks)} chunks for {uid}")
            return chunks

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to retrieve chunks for {uid}: {e}")
            return []

    async def get_chunk_embedding_freshness(self, chunk_uids: list[str]) -> list[dict[str, Any]]:
        """
        Read the freshness triple (has_embedding, version, source_text) per chunk.

        Consumed by the background worker's pre-generation skip: a chunk whose
        stored ``embedding_source_text`` still equals the incoming context
        window (and whose version is current) keeps its embedding — chunks
        compare raw text, no hash field. Returns an empty list on read failure
        so the caller fails OPEN (skips nothing).

        Args:
            chunk_uids: Chunk UIDs to check

        Returns:
            One dict per existing chunk: uid, has_embedding, version, source_text
        """
        query = """
        MATCH (c:ContentChunk)
        WHERE c.uid IN $uids
        RETURN c.uid as uid,
               c.embedding IS NOT NULL as has_embedding,
               c.embedding_version as version,
               c.embedding_source_text as source_text
        """
        try:
            result = await self.neo4j.execute_query(query, {"uids": chunk_uids})
            return [dict(record) for record in result] if result else []
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to read chunk embedding freshness: {e}")
            return []

    async def store_chunk_embeddings(
        self,
        chunk_uids: list[str],
        embeddings: list[list[float]],
        version: str,
        model: str,
        texts: list[str],
    ) -> bool:
        """
        Store pre-generated embeddings on existing ContentChunk nodes.

        Used by the background worker after batch generation and by the
        backfill script's chunk mode (both pass the current EMBEDDING_VERSION).

        ``embedding_source_text`` is stamped from ``texts`` — the exact text
        each vector was generated from — NOT from the node's current
        ``context_window``. Stamping the node-current value would mislabel the
        vector when a conflicting re-chunk lands between event publish and
        this store; with truthful provenance the already-queued event for the
        newer text sees the mismatch and re-embeds (self-heal within one batch
        cycle). Mirrors the entity-side ``text_hash`` param design.

        Args:
            chunk_uids: List of chunk UIDs to update
            embeddings: List of embedding vectors (same length as chunk_uids)
            version: Embedding version (callers pass EMBEDDING_VERSION from
                core.services.embeddings_service so chunk staleness detection
                tracks the same constant as entity embeddings)
            model: Model name (e.g., "text-embedding-3-small")
            texts: The source text each embedding was generated from (same
                length/order as embeddings)

        Returns:
            True if successful, False otherwise
        """
        try:
            if len(chunk_uids) != len(embeddings):
                logger.error(
                    f"Mismatch: {len(chunk_uids)} chunk UIDs but {len(embeddings)} embeddings"
                )
                return False

            query = """
            UNWIND $chunks as chunk_data
            MATCH (c:ContentChunk {uid: chunk_data.uid})
            SET c.embedding = chunk_data.embedding,
                c.embedding_version = $version,
                c.embedding_model = $model,
                c.embedding_updated_at = datetime(),
                c.embedding_source_text = chunk_data.source_text
            RETURN count(c) as updated_count
            """

            chunks_param = [
                {"uid": uid, "embedding": emb, "source_text": text}
                for uid, emb, text in zip(chunk_uids, embeddings, texts, strict=True)
            ]

            result = await self.neo4j.execute_query(
                query,
                {"chunks": chunks_param, "version": version, "model": model},
            )

            if result and len(result) > 0:
                updated_count: int = result[0]["updated_count"]
                logger.info(
                    f"✅ Stored embeddings for {updated_count}/{len(chunk_uids)} chunks "
                    f"(version={version}, model={model})"
                )
                return updated_count == len(chunk_uids)

            logger.warning("No chunks updated - chunks may not exist")
            return False

        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to store chunk embeddings: {e}")
            return False
