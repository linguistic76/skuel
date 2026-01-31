"""
Neo4j GenAI Plugin Embeddings Service
======================================

Uses Neo4j's native GenAI plugin for embedding generation via Cypher.
API keys configured at database level (not per-query).

ARCHITECTURE:
- API keys configured at AuraDB database level
- No per-query credential passing
- Uses native Neo4j vector operations
- Graceful degradation when plugin unavailable

SECURITY:
- Credentials stored at database layer (not in app)
- No sensitive data in Cypher queries
- AuraDB manages plugin authentication

See: /docs/architecture/NEO4J_GENAI_ARCHITECTURE.md
"""

from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.genai_embeddings")

# Embedding version tracking
# Increment when changing embedding model or parameters
EMBEDDING_VERSION = "v1"


class Neo4jGenAIEmbeddingsService:
    """
    Embeddings service using Neo4j GenAI plugin.

    Uses ai.text.embed() and ai.text.embedBatch() for embedding generation.
    Plugin must be enabled in AuraDB with OpenAI API key configured at database level.
    """

    def __init__(
        self,
        driver: Any,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        prometheus_metrics: Any | None = None,
    ) -> None:
        """
        Initialize embeddings service.

        Args:
            driver: Neo4j driver instance
            model: Embedding model to use (default: text-embedding-3-small)
            dimension: Expected embedding dimension (default: 1536 for text-embedding-3-small)
            prometheus_metrics: PrometheusMetrics for tracking OpenAI calls (Phase 1 - January 2026)
        """
        self.driver = driver
        self.model = model
        self.dimension = dimension
        self.logger = logger
        self.prometheus_metrics = prometheus_metrics

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
        CALL dbms.components() YIELD name, versions
        WHERE name = 'GenAI Plugin'
        RETURN name
        """

        try:
            result = await self.driver.execute_query(query)

            if result and len(result) > 0:
                self._plugin_available = True
                self.logger.info("✅ Neo4j GenAI plugin available")
                return True
            else:
                self._plugin_available = False
                self.logger.warning("⚠️ Neo4j GenAI plugin not available - embeddings disabled")
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

        SECURITY NOTE:
        - API key configured at database level (AuraDB console)
        - No credentials passed in this query
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
        // GenAI plugin embedding generation
        // Note: API key configured at database level, not passed here
        WITH ai.text.embed($text, $model) as embedding
        RETURN embedding
        """

        params = {"text": text, "model": self.model}

        # Track OpenAI API call metrics (Phase 1 - January 2026)
        import time

        start_time = time.time()

        try:
            result = await self.driver.execute_query(query, params)

            # Track successful request
            duration = time.time() - start_time
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

            if not result or not result[0].get("embedding"):
                return Result.fail(
                    Errors.integration(
                        service="GenAI", message="No embedding returned from GenAI plugin"
                    )
                )

            embedding = result[0]["embedding"]

            # Validate dimension
            if len(embedding) != self.dimension:
                return Result.fail(
                    Errors.integration(
                        service="GenAI",
                        message=f"Expected {self.dimension}d embedding, got {len(embedding)}d",
                    )
                )

            return Result.ok(embedding)

        except Exception as e:
            # Track error metrics
            if self.prometheus_metrics:
                error_type = "timeout" if "timeout" in str(e).lower() else "unknown"
                self.prometheus_metrics.ai.openai_errors_total.labels(
                    operation="embeddings", error_type=error_type
                ).inc()

            self.logger.error(f"Embedding generation failed: {e}")
            return Result.fail(
                Errors.integration(service="GenAI", message=f"Embedding generation failed: {e}")
            )

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
        // Batch embedding generation
        CALL ai.text.embedBatch($texts, $model)
        YIELD index, embedding
        RETURN index, embedding
        ORDER BY index
        """

        params = {"texts": truncated_texts, "model": self.model}

        # Track OpenAI batch API call metrics (Phase 1 - January 2026)
        import time

        start_time = time.time()

        try:
            result = await self.driver.execute_query(query, params)

            # Track successful batch request
            duration = time.time() - start_time
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

            # Extract embeddings in order
            embeddings = [
                record["embedding"] for record in sorted(result, key=lambda r: r["index"])
            ]

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

        except Exception as e:
            # Track error metrics
            if self.prometheus_metrics:
                error_type = "timeout" if "timeout" in str(e).lower() else "unknown"
                self.prometheus_metrics.ai.openai_errors_total.labels(
                    operation="embeddings", error_type=error_type
                ).inc()

            self.logger.error(f"Batch embedding failed: {e}")
            return Result.fail(
                Errors.integration(service="GenAI", message=f"Batch embedding failed: {e}")
            )

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
            label: Node label (e.g., "Ku", "Task")
            embedding: Embedding vector to store
            text: Optional source text that was embedded

        Returns:
            Result indicating success or error

        Example:
            >>> result = await service.store_embedding_with_metadata(
            ...     uid="ku.python",
            ...     label="Ku",
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

        try:
            result = await self.driver.execute_query(query, params)

            if not result:
                return Result.fail(Errors.not_found(entity="Node", identifier=f"{label}:{uid}"))

            self.logger.debug(f"Stored embedding for {label}:{uid} (version={EMBEDDING_VERSION})")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to store embedding metadata: {e}")
            return Result.fail(
                Errors.database(operation="store_embedding", message=f"Failed to store: {e}")
            )

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
            >>> result = await service.get_embedding_metadata("ku.python", "Ku")
            >>> if result.is_ok:
            ...     print(f"Version: {result.value['version']}")
        """
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        RETURN n.embedding as embedding,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at
        """

        try:
            result = await self.driver.execute_query(query, {"uid": uid})

            if not result:
                return Result.fail(Errors.not_found(entity="Node", identifier=f"{label}:{uid}"))

            record = result[0]
            embedding = record.get("embedding")

            metadata = {
                "has_embedding": embedding is not None,
                "version": record.get("version"),
                "model": record.get("model"),
                "updated_at": record.get("updated_at"),
                "dimension": len(embedding) if embedding else None,
            }

            return Result.ok(metadata)

        except Exception as e:
            self.logger.error(f"Failed to get embedding metadata: {e}")
            return Result.fail(
                Errors.database(operation="get_metadata", message=f"Failed to get metadata: {e}")
            )

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
            >>> result = await service.check_version_compatibility("ku.python", "Ku")
            >>> if result.is_ok and result.value["needs_update"]:
            ...     # Regenerate embedding
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
            ...     uid="ku.python", label="Ku", text="Python programming language"
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
                    result = await self.driver.execute_query(query, {"uid": uid})

                    if result and result[0].get("embedding"):
                        self.logger.debug(f"Cache hit: {label}:{uid} (version={EMBEDDING_VERSION})")
                        return Result.ok(result[0]["embedding"])

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
