"""
Embeddings Backend
==================

Neo4j adapter for storing and retrieving embedding vectors and metadata.

Implements: EmbeddingsBackendOperations protocol
Consumer: EmbeddingsService
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger(__name__)


class EmbeddingsBackend:
    """Neo4j backend for embedding storage and retrieval."""

    def __init__(self, executor: "QueryExecutor") -> None:
        self.executor = executor

    async def store_embedding_metadata(
        self,
        label: NeoLabel,
        uid: str,
        embedding: list[float],
        version: str,
        model: str,
        text: str | None,
    ) -> Result[list[dict[str, Any]]]:
        """Store embedding vector with version metadata on a node."""
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        SET n.embedding = $embedding,
            n.embedding_version = $version,
            n.embedding_model = $model,
            n.embedding_updated_at = datetime(),
            n.embedding_source_text = $text
        RETURN n.uid as uid
        """
        params = {
            "uid": uid,
            "embedding": embedding,
            "version": version,
            "model": model,
            "text": text,
        }
        try:
            return await self.executor.execute_query(query, params)
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(operation="store_embedding_metadata", message=str(e))
            )

    async def get_embedding_metadata(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get embedding version metadata for a node."""
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        RETURN n.embedding as embedding,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at
        """
        try:
            return await self.executor.execute_query(query, {"uid": uid})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation="get_embedding_metadata", message=str(e)))

    async def get_cached_embedding(self, label: NeoLabel, uid: str) -> Result[list[dict[str, Any]]]:
        """Get cached embedding vector for a node."""
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        RETURN n.embedding as embedding
        """
        try:
            return await self.executor.execute_query(query, {"uid": uid})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation="get_cached_embedding", message=str(e)))
