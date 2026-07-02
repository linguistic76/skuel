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
        text_hash: str,
    ) -> Result[list[dict[str, Any]]]:
        """Store embedding vector with version metadata on a node.

        ``embedding_text_hash`` (sha256 of the embedded text) is the
        content-truth freshness signal read back by
        ``get_embedding_freshness``. ``embedding_source_text = null`` clears
        the legacy property this hash supersedes on entity nodes (chunks keep
        theirs — it's their equality check in ``store_chunk_embeddings``).
        """
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        SET n.embedding = $embedding,
            n.embedding_version = $version,
            n.embedding_model = $model,
            n.embedding_updated_at = datetime(),
            n.embedding_text_hash = $text_hash,
            n.embedding_source_text = null
        RETURN n.uid as uid
        """
        params = {
            "uid": uid,
            "embedding": embedding,
            "version": version,
            "model": model,
            "text_hash": text_hash,
        }
        try:
            return await self.executor.execute_query(query, params)
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(operation="store_embedding_metadata", message=str(e))
            )

    async def get_embedding_freshness(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Read the freshness triple (has_embedding, version, text_hash) per uid.

        Matches on the universal :Entity base label so one read covers a
        mixed-type batch — every embeddable label is an :Entity multi-label
        node (EMBEDDING_NODE_LABELS).
        """
        query = """
        MATCH (n:Entity)
        WHERE n.uid IN $uids
        RETURN n.uid as uid,
               n.embedding IS NOT NULL as has_embedding,
               n.embedding_version as version,
               n.embedding_text_hash as text_hash
        """
        try:
            return await self.executor.execute_query(query, {"uids": uids})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation="get_embedding_freshness", message=str(e)))

    async def touch_embedding_updated_at(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        """Refresh embedding_updated_at on nodes whose embedding was verified fresh.

        Metadata-only write (no vector change): a hash-verified skip means the
        stored vector matches the current text, so the coarse timestamp filter
        (``embedding_updated_at < updated_at``) must converge instead of
        re-flagging the node on every --stale run.
        """
        query = """
        MATCH (n:Entity)
        WHERE n.uid IN $uids
        SET n.embedding_updated_at = datetime()
        RETURN count(n) as touched
        """
        try:
            return await self.executor.execute_query(query, {"uids": uids})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(operation="touch_embedding_updated_at", message=str(e))
            )

    async def stamp_embedding_text_hashes(
        self, label: NeoLabel, rows: list[dict[str, str]], version: str
    ) -> Result[list[dict[str, Any]]]:
        """One-shot hash rollout: stamp text hashes onto already-embedded nodes.

        Writes ``embedding_text_hash`` WITHOUT re-embedding, only where the
        stored vector is provably current: embedding present, version matches,
        no hash yet, and no timestamp drift (``updated_at`` coerced through
        ``datetime()`` — writer-decided storage type, same trap as the --stale
        predicate). Guards re-checked here even though the caller pre-selects,
        so a race can't stamp a hash onto a drifted vector.
        """
        query = f"""
        UNWIND $rows AS row
        MATCH (n:{label} {{uid: row.uid}})
        WHERE n.embedding IS NOT NULL
          AND n.embedding_version = $version
          AND n.embedding_text_hash IS NULL
          AND NOT (n.updated_at IS NOT NULL AND n.embedding_updated_at < datetime(n.updated_at))
        SET n.embedding_text_hash = row.text_hash
        RETURN count(n) as stamped
        """
        try:
            return await self.executor.execute_query(query, {"rows": rows, "version": version})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(operation="stamp_embedding_text_hashes", message=str(e))
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
