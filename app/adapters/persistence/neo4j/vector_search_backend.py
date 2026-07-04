"""
Vector Search Backend
======================

Backend for Neo4j vector index queries and full-text search.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 5 execute_query calls from Neo4jVectorSearchService.

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.enums.neo_labels import NeoLabel
    from core.ports.query_types import SemanticSearchChunkResult


class VectorSearchBackend:
    """Backend for vector search persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def query_vector_index(
        self, index_name: str, limit: int, embedding: list[float], min_score: float
    ) -> Result[list[dict[str, Any]]]:
        """Query a Neo4j vector index for similar nodes."""
        return await self._executor.execute_query(
            """
            // Vector similarity search using native index
            CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
            YIELD node, score
            WHERE score >= $min_score
            RETURN node, score
            ORDER BY score DESC
            """,
            {
                "index_name": index_name,
                "limit": limit,
                "embedding": embedding,
                "min_score": min_score,
            },
        )

    async def get_node_embedding(self, label: NeoLabel, uid: str) -> Result[list[dict[str, Any]]]:
        """Get the embedding vector for a specific node."""
        # Label is validated by the service layer (comes from config, not user input)
        return await self._executor.execute_query(
            f"""
            MATCH (source:{label} {{uid: $uid}})
            RETURN source.embedding as embedding
            """,
            {"uid": uid},
        )

    async def query_fulltext_index(
        self, index_name: str, query_text: str, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """Query a Neo4j full-text index."""
        return await self._executor.execute_query(
            """
            CALL db.index.fulltext.queryNodes($index_name, $query_text)
            YIELD node, score
            RETURN node, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            {"index_name": index_name, "query_text": query_text, "limit": limit},
        )

    async def get_semantic_relationships(
        self, entity_uid: str, context_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Get semantic relationships between entity and context UIDs."""
        return await self._executor.execute_query(
            """
            MATCH (entity:Entity {uid: $entity_uid})
            MATCH (context:Entity)
            WHERE context.uid IN $context_uids
            MATCH (entity)-[r]->(context)
            WHERE r.confidence IS NOT NULL
            RETURN
                type(r) as relationship_type,
                r.confidence as confidence,
                COALESCE(r.strength, 1.0) as strength
            """,
            {"entity_uid": entity_uid, "context_uids": context_uids},
        )

    async def semantic_search_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        chunk_types: list[str] | None = None,
        parent_uid: str | None = None,
    ) -> Result[list[SemanticSearchChunkResult]]:
        """Vector search across :ContentChunk nodes for precise RAG retrieval.

        Targets `contentchunk_embedding_idx` and joins back through
        :HAS_CHUNK / :HAS_CONTENT to surface the owning Entity (typically a
        PathStep) so callers can cite the parent in responses.
        """
        parts = [
            """CALL db.index.vector.queryNodes(
            'contentchunk_embedding_idx',
            $limit * 2,
            $query_embedding
        ) YIELD node AS chunk, score
        WHERE score >= $threshold"""
        ]
        if chunk_types:
            parts.append("AND chunk.chunk_type IN $chunk_types")
        if parent_uid:
            parts.append(
                """AND EXISTS {
                MATCH (chunk)<-[:HAS_CHUNK]-(content:Content {uid: $parent_uid})
            }"""
            )
        parts.append(
            """MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)<-[:HAS_CONTENT]-(parent:Entity)
        RETURN
            chunk.uid as chunk_uid,
            chunk.chunk_type as chunk_type,
            chunk.text as text,
            chunk.context_window as context_window,
            score as similarity_score,
            parent.uid as parent_uid,
            parent.title as parent_title
        ORDER BY score DESC
        LIMIT $limit"""
        )
        cypher = "\n".join(parts)
        params: dict[str, Any] = {
            "query_embedding": query_embedding,
            "limit": limit,
            "threshold": threshold,
            "chunk_types": chunk_types,
            "parent_uid": parent_uid,
        }
        # boundary: query_executor returns dict rows; the Cypher's RETURN
        # clause matches SemanticSearchChunkResult by construction.
        raw = await self._executor.execute_query(cypher, params)
        return cast("Result[list[SemanticSearchChunkResult]]", raw)

    async def get_learning_states_batch(
        self, user_uid: str, ku_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Batch fetch learning states (VIEWED/IN_PROGRESS/MASTERED) for KU UIDs."""
        return await self._executor.execute_query(
            """
            UNWIND $ku_uids as ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
            OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
            OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
            RETURN
                ku.uid as ku_uid,
                v IS NOT NULL as has_viewed,
                p IS NOT NULL as has_in_progress,
                m IS NOT NULL as has_mastered
            """,
            {"user_uid": user_uid, "ku_uids": ku_uids},
        )
