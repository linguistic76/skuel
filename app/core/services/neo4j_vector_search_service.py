"""
Neo4j Vector Search Service
============================

Uses native vector indexes and db.index.vector.queryNodes() for semantic search.

PERFORMANCE:
- Uses db.index.vector.queryNodes() for fast approximate nearest neighbor search
- Vector indexes must be created first (via schema manager)
- Supports top-K retrieval with similarity scores

ARCHITECTURE:
- Works with Neo4jGenAIEmbeddingsService for embedding generation
- Requires vector indexes created on embedding fields
- Returns nodes with similarity scores sorted by relevance

See: /docs/architecture/NEO4J_GENAI_ARCHITECTURE.md
"""

from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.vector_search")


class Neo4jVectorSearchService:
    """
    Vector similarity search using Neo4j native vector indexes.

    Uses db.index.vector.queryNodes() for fast approximate nearest neighbor search.
    """

    def __init__(self, driver: Any, embeddings_service: Any | None = None):
        """
        Initialize vector search service.

        Args:
            driver: Neo4j driver instance
            embeddings_service: Optional embeddings service for text-to-embedding conversion
        """
        self.driver = driver
        self.embeddings = embeddings_service
        self.logger = logger

    async def find_similar_by_vector(
        self, label: str, embedding: list[float], limit: int = 10, min_score: float = 0.7
    ) -> Result[list[dict[str, Any]]]:
        """
        Find similar nodes using vector index.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            embedding: Query embedding vector
            limit: Max results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        index_name = f"{label.lower()}_embedding_idx"

        query = """
        // Vector similarity search using native index
        CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
        YIELD node, score
        WHERE score >= $min_score
        RETURN node, score
        ORDER BY score DESC
        """

        params = {"index_name": index_name, "limit": limit, "embedding": embedding, "min_score": min_score}

        try:
            result = await self.driver.execute_query(query, params)

            if not result:
                return Result.ok([])

            # Convert to list of dicts
            similar = [{"node": dict(record["node"]), "score": record["score"]} for record in result]

            return Result.ok(similar)

        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            return Result.fail(
                Errors.database(operation="vector_search", message=f"Search failed: {e}")
            )

    async def find_similar_by_text(
        self, label: str, text: str, limit: int = 10, min_score: float = 0.7
    ) -> Result[list[dict[str, Any]]]:
        """
        Find similar nodes by generating embedding from text.

        Convenience method that combines embedding generation + vector search.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            text: Query text to embed and search
            limit: Max results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        if not self.embeddings:
            return Result.fail(
                Errors.unavailable(
                    feature="semantic_search",
                    reason="Embeddings service required for semantic search. Configure OPENAI_API_KEY.",
                    operation="find_similar_by_text",
                )
            )

        # Generate embedding
        embedding_result = await self.embeddings.create_embedding(text)
        if embedding_result.is_error:
            return Result.fail(embedding_result.expect_error())

        embedding = embedding_result.value

        # Search by vector
        return await self.find_similar_by_vector(
            label=label, embedding=embedding, limit=limit, min_score=min_score
        )

    async def find_similar_to_node(
        self,
        label: str,
        uid: str,
        limit: int = 10,
        min_score: float = 0.7,
        exclude_self: bool = True,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find nodes similar to a specific node.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            uid: UID of source node
            limit: Max results to return
            min_score: Minimum similarity score (0-1)
            exclude_self: Exclude source node from results

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        # Get source node's embedding
        query = f"""
        MATCH (source:{label} {{uid: $uid}})
        RETURN source.embedding as embedding
        """

        try:
            result = await self.driver.execute_query(query, {"uid": uid})

            if not result or not result[0].get("embedding"):
                return Result.fail(
                    Errors.not_found(
                        entity_type=label,
                        uid=uid,
                        context={"reason": "No embedding found for this node"},
                    )
                )

            source_embedding = result[0]["embedding"]

        except Exception as e:
            self.logger.error(f"Failed to get source embedding: {e}")
            return Result.fail(
                Errors.database(operation="get_embedding", message=f"Failed to retrieve embedding: {e}")
            )

        # Find similar nodes
        similar_result = await self.find_similar_by_vector(
            label=label, embedding=source_embedding, limit=limit + 1 if exclude_self else limit, min_score=min_score
        )

        if similar_result.is_error:
            return similar_result

        similar = similar_result.value

        # Exclude source node if requested
        if exclude_self:
            similar = [s for s in similar if s["node"].get("uid") != uid][:limit]

        return Result.ok(similar)

    async def find_cross_domain_similar(
        self,
        embedding: list[float],
        labels: list[str],
        limit_per_label: int = 5,
        min_score: float = 0.7,
    ) -> Result[dict[str, list[dict[str, Any]]]]:
        """
        Find similar nodes across multiple domains/labels.

        Args:
            embedding: Query embedding vector
            labels: List of node labels to search (e.g., ["Ku", "Task", "Goal"])
            limit_per_label: Max results per label
            min_score: Minimum similarity score (0-1)

        Returns:
            Result containing dict mapping label -> list of {node, score} dicts
        """
        results = {}

        for label in labels:
            search_result = await self.find_similar_by_vector(
                label=label, embedding=embedding, limit=limit_per_label, min_score=min_score
            )

            if search_result.is_ok:
                results[label] = search_result.value
            else:
                # Log error but continue with other labels
                self.logger.warning(f"Search failed for label {label}: {search_result.expect_error()}")
                results[label] = []

        return Result.ok(results)
