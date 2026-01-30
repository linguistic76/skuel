"""
Neo4j Content Repository Adapter
==================================

Implements ContentRepoPort for Neo4j database.
Manages Content nodes separately from Knowledge nodes.
"""

__version__ = "1.0"


import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jContentAdapter:
    """
    Neo4j implementation of the ContentRepoPort.

    Manages Content nodes that store the body text of knowledge units.
    Content nodes are linked to Knowledge nodes via HAS_CONTENT relationship.
    """

    def __init__(self, neo4j_connection) -> None:
        """
        Initialize with Neo4j connection.

        Args:
            neo4j_connection: Neo4j database connection
        """
        self.neo4j = neo4j_connection

    async def fetch_content(self, unit_uid: str) -> dict[str, Any] | None:
        """
        Fetch content for a knowledge unit.

        Args:
            unit_uid: The knowledge unit's UID

        Returns:
            Dictionary with content data or None if not found
        """
        query = """
        MATCH (unit:Ku {uid: $uid})-[:HAS_CONTENT]->(content:Content)
        RETURN content {
            .body,
            .format,
            .language,
            .source_path,
            .body_sha256,
            .created_at,
            .updated_at
        } as content
        """

        result = await self.neo4j.execute_query(query, {"uid": unit_uid})

        if result and len(result) > 0:
            content: dict[str, Any] = result[0]["content"]
            return content
        return None

    async def create_content(self, unit_uid: str, body: str, **metadata: Any) -> dict[str, Any]:
        """
        Create content for a knowledge unit.

        Creates a Content node and links it to the Knowledge via HAS_CONTENT.

        Args:
            unit_uid: The knowledge unit's UID
            body: The content body (markdown)
            **metadata: Additional metadata (format, language, etc.)

        Returns:
            Created content dictionary
        """
        # Calculate body hash for integrity
        body_sha256 = hashlib.sha256(body.encode()).hexdigest()

        # Prepare timestamps
        now = datetime.now(UTC).isoformat()

        # Default values
        format_type = metadata.get("format", "markdown")
        language = metadata.get("language", "en")
        source_path = metadata.get("source_path")

        query = """
        MATCH (unit:Ku {uid: $uid})
        CREATE (content:Content {
            unit_uid: $uid
            body: $body
            format: $format
            language: $language
            source_path: $source_path
            body_sha256: $body_sha256
            created_at: $created_at
            updated_at: $updated_at
        })
        CREATE (unit)-[:HAS_CONTENT]->(content)
        RETURN content {
            .unit_uid,
            .body,
            .format,
            .language,
            .source_path,
            .body_sha256,
            .created_at,
            .updated_at
        } as content
        """

        params = {
            "uid": unit_uid,
            "body": body,
            "format": format_type,
            "language": language,
            "source_path": source_path,
            "body_sha256": body_sha256,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.neo4j.execute_query(query, params)

        if result and len(result) > 0:
            logger.info(f"Created content for knowledge unit: {unit_uid}")
            content: dict[str, Any] = result[0]["content"]
            return content

        raise RuntimeError(f"Failed to create content for {unit_uid}")

    async def update_content(self, unit_uid: str, body: str) -> dict[str, Any]:
        """
        Update content for a knowledge unit.

        Args:
            unit_uid: The knowledge unit's UID
            body: The new content body

        Returns:
            Updated content dictionary
        """
        # Calculate new body hash
        body_sha256 = hashlib.sha256(body.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()

        query = """
        MATCH (unit:Ku {uid: $uid})-[:HAS_CONTENT]->(content:Content)
        SET content.body = $body,
            content.body_sha256 = $body_sha256,
            content.updated_at = $updated_at
        RETURN content {
            .unit_uid,
            .body,
            .format,
            .language,
            .source_path,
            .body_sha256,
            .created_at,
            .updated_at
        } as content
        """

        params = {"uid": unit_uid, "body": body, "body_sha256": body_sha256, "updated_at": now}

        result = await self.neo4j.execute_query(query, params)

        if result and len(result) > 0:
            logger.info(f"Updated content for knowledge unit: {unit_uid}")
            content: dict[str, Any] = result[0]["content"]
            return content

        # Content doesn't exist, create it
        logger.warning(f"Content not found for {unit_uid}, creating new content")
        return await self.create_content(unit_uid, body)

    async def delete_content(self, unit_uid: str) -> bool:
        """
        DETACH DELETE content for a knowledge unit.

        Args:
            unit_uid: The knowledge unit's UID

        Returns:
            True if deleted, False if not found
        """
        query = """
        MATCH (unit:Ku {uid: $uid})-[:HAS_CONTENT]->(content:Content)
        DETACH DELETE content
        RETURN count(content) as deleted
        """

        result = await self.neo4j.execute_query(query, {"uid": unit_uid})

        if result and len(result) > 0:
            deleted_count = result[0]["deleted"]
            if deleted_count > 0:
                logger.info(f"Deleted content for knowledge unit: {unit_uid}")
                return True

        logger.warning(f"No content found to delete for: {unit_uid}")
        return False

    async def store_content_with_chunks(
        self,
        uid: str,
        content: Any,  # KnowledgeContent object
    ) -> bool:
        """
        Store content with its semantic chunks for RAG retrieval.

        Creates:
        - Content node with full text
        - ContentChunk nodes for each chunk
        - HAS_CHUNK relationships
        - ContentMetadata node with analytics

        Args:
            uid: Knowledge unit UID,
            content: KnowledgeContent object with chunks

        Returns:
            True if successful
        """
        try:
            logger.info(f"store_content_with_chunks called with content type: {type(content)}")
            logger.info(f"Content attributes: {dir(content) if content else 'None'}")

            # Start transaction for atomic storage
            query = """
            // Match the knowledge unit
            MATCH (ku:Ku {uid: $uid})

            // Create or merge Content node
            MERGE (c:Content {uid: $uid})
            SET c.body = $body
            SET c.format = $format
            SET c.word_count = $word_count
            SET c.chunk_count = $chunk_count
            SET c.updated_at = datetime()

            // Link to knowledge unit
            MERGE (ku)-[:HAS_CONTENT]->(c)

            // Create metadata node
            MERGE (m:ContentMetadata {uid: $uid})
            SET m.has_code = $has_code
            SET m.has_examples = $has_examples
            SET m.has_definitions = $has_definitions
            SET m.complexity_score = $complexity_score
            SET m.readability_score = $readability_score

            // Link metadata
            MERGE (c)-[:HAS_METADATA]->(m)

            RETURN c.uid as uid
            """

            # Extract metadata from content object using getattr for safety
            metadata = {
                "uid": uid,
                "body": getattr(content, "body", str(content)),
                "format": getattr(content, "format", "markdown"),
                "word_count": getattr(content, "word_count", 0),
                "chunk_count": getattr(content, "chunk_count", 0),
                "has_code": False,
                "has_examples": False,
                "has_definitions": False,
                "complexity_score": 0.5,
                "readability_score": 0.5,
            }

            # Execute main content storage
            result = await self.neo4j.execute_query(query, metadata)

            if not result:
                logger.error(f"Failed to store content for {uid}")
                return False

            # Store chunks if available
            # Check for chunks using getattr
            chunks = getattr(content, "chunks", None)
            logger.info(f"Checking for chunks: has chunks = {chunks is not None}")
            if chunks:
                logger.info(f"Number of chunks: {len(content.chunks) if content.chunks else 0}")
                logger.info(f"Chunks type: {type(content.chunks)}")
                if content.chunks and len(content.chunks) > 0:
                    logger.info(f"First chunk type: {type(content.chunks[0])}")
                    logger.info(f"First chunk attributes: {dir(content.chunks[0])}")

            if chunks:
                chunk_query = """
                MATCH (c:Content {uid: $uid})
                CREATE (chunk:ContentChunk {
                    uid: $chunk_uid,
                    chunk_type: $chunk_type,
                    text: $text,
                    start_index: $start_index,
                    end_index: $end_index,
                    context_window: $context_window,
                    created_at: datetime(),
                    embedding: null,
                    embedding_version: null,
                    embedding_model: null,
                    embedding_updated_at: null,
                    embedding_source_text: null
                })
                CREATE (c)-[:HAS_CHUNK {sequence: $sequence}]->(chunk)
                RETURN chunk.uid
                """

                for i, chunk in enumerate(content.chunks):
                    # Convert chunk_type enum to string for Neo4j
                    chunk_type = getattr(chunk, "chunk_type", "CONTENT")
                    if isinstance(chunk_type, Enum):
                        chunk_type = chunk_type.value
                    else:
                        chunk_type = str(chunk_type)

                    chunk_params = {
                        "uid": uid,
                        "chunk_uid": getattr(chunk, "chunk_id", f"{uid}_chunk_{i}"),
                        "chunk_type": chunk_type,
                        "text": getattr(chunk, "text", str(chunk)),
                        "context_window": getattr(chunk, "context_window", getattr(chunk, "text", str(chunk))),
                        "start_index": getattr(chunk, "chunk_index", i),
                        "end_index": getattr(
                            chunk, "word_count", len(getattr(chunk, "text", "").split())
                        ),
                        # Note: Metadata not stored (Neo4j can't handle nested structures)
                        "sequence": i,
                    }

                    chunk_result = await self.neo4j.execute_query(chunk_query, chunk_params)

                    if chunk_result is None:
                        logger.error(f"Failed to create chunk {i} - query returned None")
                        (logger.error(f"Chunk params: {chunk_params}"),)
                    else:
                        logger.info(
                            f"Created chunk {i} ({chunk_params['chunk_type']}): {chunk_params['chunk_uid']}"
                        )

                    # Update metadata based on chunk types
                    if chunk_params["chunk_type"] == "CODE":
                        metadata["has_code"] = True
                    elif chunk_params["chunk_type"] == "EXAMPLE":
                        metadata["has_examples"] = True
                    elif chunk_params["chunk_type"] == "DEFINITION":
                        metadata["has_definitions"] = True

                logger.info(f"Stored {len(content.chunks)} chunks for {uid}")

            logger.info(f"Successfully stored content with chunks for {uid}")
            return True

        except Exception as e:
            logger.error(f"Failed to store content with chunks for {uid}: {e}")
            return False

    async def get_chunks(self, uid: str, chunk_type: str | None = None) -> list[dict[str, Any]]:
        """
        Retrieve chunks for a knowledge unit.

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
                params = ({"uid": uid, "chunk_type": chunk_type},)
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

        except Exception as e:
            logger.error(f"Failed to retrieve chunks for {uid}: {e}")
            return []

    async def store_chunk_embeddings(
        self,
        chunk_uids: list[str],
        embeddings: list[list[float]],
        version: str,
        model: str,
    ) -> bool:
        """
        Store pre-generated embeddings on existing ContentChunk nodes.

        Used by background worker after batch generation.

        Args:
            chunk_uids: List of chunk UIDs to update
            embeddings: List of embedding vectors (same length as chunk_uids)
            version: Embedding version (e.g., "v1")
            model: Model name (e.g., "text-embedding-3-small")

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
                c.embedding_source_text = c.context_window
            RETURN count(c) as updated_count
            """

            chunks_param = [
                {"uid": uid, "embedding": emb}
                for uid, emb in zip(chunk_uids, embeddings, strict=True)
            ]

            result = await self.neo4j.execute_query(
                query,
                {"chunks": chunks_param, "version": version, "model": model},
            )

            if result and len(result) > 0:
                updated_count = result[0]["updated_count"]
                logger.info(
                    f"✅ Stored embeddings for {updated_count}/{len(chunk_uids)} chunks "
                    f"(version={version}, model={model})"
                )
                return updated_count == len(chunk_uids)

            logger.warning("No chunks updated - chunks may not exist")
            return False

        except Exception as e:
            logger.error(f"Failed to store chunk embeddings: {e}")
            return False
