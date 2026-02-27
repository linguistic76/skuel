"""
Neo4j GenAI Plugin Embeddings Service
======================================

Uses Neo4j's native GenAI plugin for embedding generation via Cypher.

ARCHITECTURE (Docker Development):
- Plugin enabled via NEO4J_PLUGINS='["genai"]' in docker-compose.yml
- API keys passed per-query via token parameter (Docker)
- OpenAI API key from OPENAI_API_KEY environment variable
- Uses native Neo4j vector operations
- Graceful degradation when plugin unavailable

PRODUCTION (AuraDB):
- API keys configured at database level (no per-query passing)
- See: /docs/deployment/AURADB_MIGRATION_GUIDE.md

SECURITY:
- Docker: API key from environment variable, passed per-query
- AuraDB: API key stored at database layer (managed by Neo4j)
- No sensitive data in Cypher queries (token is parameter)

See: /docs/development/GENAI_SETUP.md
"""

from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger("skuel.genai_embeddings")

# Embedding version tracking
# Increment when changing embedding model or parameters
EMBEDDING_VERSION = "v1"


class Neo4jGenAIEmbeddingsService:
    """
    Embeddings service using Neo4j GenAI plugin.

    Uses genai.vector.encode() and genai.vector.encodeBatch() for embedding generation.

    Docker Setup (Development):
    - Plugin enabled via docker-compose.yml: NEO4J_PLUGINS='["genai"]'
    - API key passed per-query via token parameter
    - Requires OPENAI_API_KEY environment variable

    AuraDB Setup (Production):
    - Plugin enabled via console
    - API key configured at database level
    - See: /docs/deployment/AURADB_MIGRATION_GUIDE.md
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        prometheus_metrics: Any | None = None,
    ) -> None:
        """
        Initialize embeddings service.

        Args:
            executor: Query executor for database operations
            model: Embedding model to use (default: text-embedding-3-small)
            dimension: Expected embedding dimension (default: 1536 for text-embedding-3-small)
            prometheus_metrics: PrometheusMetrics for tracking OpenAI calls
        """
        self.executor = executor
        self.model = model
        self.dimension = dimension
        self.logger = logger
        self.prometheus_metrics = prometheus_metrics

        # Get OpenAI API key from environment
        import os

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if not self.openai_api_key:
            self.logger.warning("⚠️ OPENAI_API_KEY not set - embeddings will fail")

        # Check plugin availability (async, done lazily on first use)
        self._plugin_available: bool | None = None

    async def _check_plugin_availability(self) -> bool:
        """
        Check if Neo4j GenAI plugin is available.

        Returns:
            True if plugin is available, False otherwise
        """
        if self._plugin_available is not None:
            return self._plugin_available

        query = """
        SHOW PROCEDURES YIELD name
        WHERE name STARTS WITH 'genai.vector'
        RETURN name LIMIT 1
        """

        try:
            result = await self.executor.execute_query(query)

            if result.is_ok and result.value and len(result.value) > 0:
                self._plugin_available = True
                self.logger.info("Neo4j GenAI plugin available")
                return True
            else:
                self._plugin_available = False
                self.logger.warning("Neo4j GenAI plugin not available - embeddings disabled")
                return False

        except Exception as e:
            self._plugin_available = False
            self.logger.warning(f"Could not verify GenAI plugin: {e}")
            return False

    async def create_embedding(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> Result[list[float]]:
        """
        Create embedding using Neo4j GenAI plugin.

        SECURITY NOTE (Docker Development):
        - API key from OPENAI_API_KEY environment variable
        - Passed per-query as token parameter
        - Required for Docker setup (no database-level config)

        SECURITY NOTE (AuraDB Production):
        - API key configured at database level
        - No per-query credential passing needed
        - Plugin reads key from database configuration

        Args:
            text: Text to embed
            metadata: Optional metadata (not used by GenAI plugin)

        Returns:
            Result containing embedding vector or error
        """
        # Check plugin availability
        if not await self._check_plugin_availability():
            return Result.fail(
                Errors.unavailable(
                    feature="embeddings",
                    reason="Neo4j GenAI plugin not available. Configure in AuraDB console.",
                    operation="create_embedding",
                )
            )

        if not text or not text.strip():
            return Result.fail(Errors.validation("Text cannot be empty", field="text"))

        # Truncate to avoid token limits (8191 for text-embedding-3-small)
        max_chars = 30000  # ~8000 tokens
        if len(text) > max_chars:
            text = text[:max_chars]
            self.logger.warning(f"Text truncated to {max_chars} chars")

        query = """
        // GenAI plugin embedding generation using genai.vector.encode()
        // Note: Local Neo4j requires passing token explicitly
        RETURN genai.vector.encode(
            $text,
            'OpenAI',
            {
                token: $token,
                model: $model,
                dimensions: $dimensions
            }
        ) AS embedding
        """

        params = {
            "text": text,
            "model": self.model,
            "token": self.openai_api_key,
            "dimensions": self.dimension,
        }

        # Track OpenAI API call metrics
        import time

        start_time = time.time()

        result = await self.executor.execute_query(query, params)

        # Track timing
        duration = time.time() - start_time

        if result.is_error:
            # Track error metrics
            if self.prometheus_metrics:
                self.prometheus_metrics.ai.openai_errors_total.labels(
                    operation="embeddings", error_type="unknown"
                ).inc()

            self.logger.error(f"Embedding generation failed: {result.error}")
            return Result.fail(
                Errors.integration(
                    service="GenAI", message=f"Embedding generation failed: {result.error}"
                )
            )

        records = result.value

        # Track successful request
        if self.prometheus_metrics:
            self.prometheus_metrics.ai.openai_requests_total.labels(
                operation="embeddings", model=self.model
            ).inc()

            self.prometheus_metrics.ai.openai_duration_seconds.labels(
                operation="embeddings", model=self.model
            ).observe(duration)

            # Estimate token usage (rough approximation: ~4 chars per token)
            estimated_tokens = len(text) // 4
            self.prometheus_metrics.ai.openai_tokens_used.labels(
                operation="embeddings", model=self.model, token_type="prompt"
            ).inc(estimated_tokens)

        if not records or not records[0].get("embedding"):
            return Result.fail(
                Errors.integration(
                    service="GenAI", message="No embedding returned from GenAI plugin"
                )
            )

        embedding = records[0]["embedding"]

        # Validate dimension
        if len(embedding) != self.dimension:
            return Result.fail(
                Errors.integration(
                    service="GenAI",
                    message=f"Expected {self.dimension}d embedding, got {len(embedding)}d",
                )
            )

        return Result.ok(embedding)

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> Result[list[list[float]]]:
        """
        Create embeddings for multiple texts using GenAI plugin batch operation.

        Uses ai.text.embedBatch() for efficient bulk processing.

        Args:
            texts: List of texts to embed
            metadata_list: Optional metadata list (not used by GenAI plugin)

        Returns:
            Result containing list of embedding vectors or error
        """
        # Check plugin availability
        if not await self._check_plugin_availability():
            return Result.fail(
                Errors.unavailable(
                    feature="embeddings",
                    reason="Neo4j GenAI plugin not available",
                    operation="create_batch_embeddings",
                )
            )

        if not texts:
            return Result.ok([])

        # Truncate texts
        max_chars = 30000
        truncated_texts = [t[:max_chars] if len(t) > max_chars else t for t in texts]

        query = """
        // Batch embedding generation using genai.vector.encodeBatch()
        // Note: Local Neo4j requires passing token explicitly
        CALL genai.vector.encodeBatch(
            $texts,
            'OpenAI',
            {
                token: $token,
                model: $model,
                dimensions: $dimensions
            }
        )
        YIELD index, vector
        RETURN index, vector
        ORDER BY index
        """

        params = {
            "texts": truncated_texts,
            "model": self.model,
            "token": self.openai_api_key,
            "dimensions": self.dimension,
        }

        # Track OpenAI batch API call metrics
        import time

        start_time = time.time()

        result = await self.executor.execute_query(query, params)

        # Track timing
        duration = time.time() - start_time

        if result.is_error:
            # Track error metrics
            if self.prometheus_metrics:
                self.prometheus_metrics.ai.openai_errors_total.labels(
                    operation="embeddings", error_type="unknown"
                ).inc()

            self.logger.error(f"Batch embedding failed: {result.error}")
            return Result.fail(
                Errors.integration(
                    service="GenAI", message=f"Batch embedding failed: {result.error}"
                )
            )

        records = result.value

        # Track successful batch request
        if self.prometheus_metrics:
            self.prometheus_metrics.ai.openai_requests_total.labels(
                operation="embeddings", model=self.model
            ).inc()

            self.prometheus_metrics.ai.openai_duration_seconds.labels(
                operation="embeddings", model=self.model
            ).observe(duration)

            # Estimate total token usage for batch (rough approximation)
            total_chars = sum(len(t) for t in truncated_texts)
            estimated_tokens = total_chars // 4
            self.prometheus_metrics.ai.openai_tokens_used.labels(
                operation="embeddings", model=self.model, token_type="prompt"
            ).inc(estimated_tokens)

        # Extract embeddings in order (procedure yields 'vector', not 'embedding')
        embeddings = [record["vector"] for record in sorted(records, key=itemgetter("index"))]

        # Validate all dimensions
        for idx, emb in enumerate(embeddings):
            if len(emb) != self.dimension:
                return Result.fail(
                    Errors.integration(
                        service="GenAI",
                        message=f"Embedding {idx} has wrong dimension: {len(emb)} != {self.dimension}",
                    )
                )

        return Result.ok(embeddings)

    async def calculate_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> Result[float]:
        """
        Calculate cosine similarity between two embeddings.

        Note: Typically not needed - use db.index.vector.queryNodes() instead
        for efficient similarity search via vector indexes.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Result containing similarity score (0.0-1.0) or error
        """
        if len(embedding1) != len(embedding2):
            return Result.fail(
                Errors.validation("Embeddings must have same dimension", field="embeddings")
            )

        # Cosine similarity
        import math

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return Result.fail(
                Errors.validation("Cannot compute similarity for zero vectors", field="embeddings")
            )

        similarity = dot_product / (norm1 * norm2)
        return Result.ok(similarity)

    async def store_embedding_with_metadata(
        self,
        uid: str,
        label: str,
        embedding: list[float],
        text: str | None = None,
    ) -> Result[None]:
        """
        Store embedding with version metadata on a node.

        Updates the node's embedding field and adds version tracking metadata:
        - embedding_version: Version identifier (e.g., "v1")
        - embedding_model: Model name (e.g., "text-embedding-3-small")
        - embedding_updated_at: Timestamp of last update
        - embedding_source_text: Optional text that was embedded

        Args:
            uid: Node UID
            label: Node label (e.g., "Entity", "Task")
            embedding: Embedding vector to store
            text: Optional source text that was embedded

        Returns:
            Result indicating success or error

        Example:
            >>> result = await service.store_embedding_with_metadata(
            ...     uid="ku.python",
            ...     label="Entity",
            ...     embedding=[0.1, 0.2, ...],
            ...     text="Python programming language",
            ... )
        """
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
            "version": EMBEDDING_VERSION,
            "model": self.model,
            "text": text,
        }

        result = await self.executor.execute_query(query, params)

        if result.is_error:
            self.logger.error(f"Failed to store embedding metadata: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="store_embedding", message=f"Failed to store: {result.error}"
                )
            )

        if not result.value:
            return Result.fail(Errors.not_found(resource="Node", identifier=f"{label}:{uid}"))

        self.logger.debug(f"Stored embedding for {label}:{uid} (version={EMBEDDING_VERSION})")
        return Result.ok(None)

    async def get_embedding_metadata(self, uid: str, label: str) -> Result[dict[str, Any]]:
        """
        Get embedding version metadata for a node.

        Returns:
            Result containing metadata dict with keys:
            - has_embedding: Whether node has an embedding
            - version: Embedding version (e.g., "v1") or None
            - model: Model name or None
            - updated_at: Last update timestamp or None
            - dimension: Embedding dimension or None

        Example:
            >>> result = await service.get_embedding_metadata("ku.python", "Entity")
            >>> if result.is_ok:
            ... print(f"Version: {result.value['version']}")
        """
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        RETURN n.embedding as embedding,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at
        """

        result = await self.executor.execute_query(query, {"uid": uid})

        if result.is_error:
            self.logger.error(f"Failed to get embedding metadata: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="get_metadata", message=f"Failed to get metadata: {result.error}"
                )
            )

        if not result.value:
            return Result.fail(Errors.not_found(resource="Node", identifier=f"{label}:{uid}"))

        record = result.value[0]
        embedding = record.get("embedding")

        metadata = {
            "has_embedding": embedding is not None,
            "version": record.get("version"),
            "model": record.get("model"),
            "updated_at": record.get("updated_at"),
            "dimension": len(embedding) if embedding else None,
        }

        return Result.ok(metadata)

    async def check_version_compatibility(self, uid: str, label: str) -> Result[dict[str, Any]]:
        """
        Check if node's embedding version is compatible with current version.

        Returns:
            Result containing compatibility info:
            - is_current: Whether embedding is current version
            - node_version: Version on the node
            - current_version: Current service version
            - needs_update: Whether embedding should be regenerated

        Example:
            >>> result = await service.check_version_compatibility("ku.python", "Entity")
            >>> if result.is_ok and result.value["needs_update"]:
            ... # Regenerate embedding
        """
        metadata_result = await self.get_embedding_metadata(uid, label)

        if metadata_result.is_error:
            return metadata_result

        metadata = metadata_result.value
        node_version = metadata.get("version")

        # Check if version matches
        is_current = node_version == EMBEDDING_VERSION
        needs_update = metadata["has_embedding"] and not is_current

        compatibility = {
            "is_current": is_current,
            "node_version": node_version,
            "current_version": EMBEDDING_VERSION,
            "needs_update": needs_update,
            "has_embedding": metadata["has_embedding"],
        }

        return Result.ok(compatibility)

    async def get_or_create_embedding(self, uid: str, label: str, text: str) -> Result[list[float]]:
        """
        Get cached embedding or create new one with version tracking.

        Checks if node has current-version embedding:
        - Cache hit: Return existing embedding (no API call)
        - Cache miss or stale: Generate new embedding and store with metadata

        This method combines caching with version tracking for optimal performance.

        Args:
            uid: Node UID
            label: Node label
            text: Text to embed (used if generating new)

        Returns:
            Result containing embedding vector

        Example:
            >>> result = await service.get_or_create_embedding(
            ...     uid="ku.python", label="Entity", text="Python programming language"
            ... )
        """
        # Check if node has current-version embedding
        compat_result = await self.check_version_compatibility(uid, label)

        if compat_result.is_ok and compat_result.value["is_current"]:
            # Cache hit - get existing embedding
            metadata_result = await self.get_embedding_metadata(uid, label)

            if metadata_result.is_ok:
                query = f"""
                MATCH (n:{label} {{uid: $uid}})
                RETURN n.embedding as embedding
                """

                try:
                    result = await self.executor.execute_query(query, {"uid": uid})

                    if result.is_ok and result.value and result.value[0].get("embedding"):
                        self.logger.debug(f"Cache hit: {label}:{uid} (version={EMBEDDING_VERSION})")
                        return Result.ok(result.value[0]["embedding"])

                except Exception as e:
                    self.logger.warning(f"Failed to get cached embedding: {e}")
                    # Fall through to regenerate

        # Cache miss or stale - generate new embedding
        self.logger.debug(f"Cache miss: {label}:{uid} - generating new embedding")

        embedding_result = await self.create_embedding(text)

        if embedding_result.is_error:
            return embedding_result

        embedding = embedding_result.value

        # Store with metadata
        store_result = await self.store_embedding_with_metadata(
            uid=uid, label=label, embedding=embedding, text=text
        )

        if store_result.is_error:
            # Log warning but return embedding anyway
            self.logger.warning(f"Failed to store embedding metadata: {store_result.error}")

        return Result.ok(embedding)
