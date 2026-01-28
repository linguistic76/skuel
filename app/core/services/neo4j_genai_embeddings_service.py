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


class Neo4jGenAIEmbeddingsService:
    """
    Embeddings service using Neo4j GenAI plugin.

    Uses ai.text.embed() and ai.text.embedBatch() for embedding generation.
    Plugin must be enabled in AuraDB with OpenAI API key configured at database level.
    """

    def __init__(self, driver: Any, model: str = "text-embedding-3-small", dimension: int = 1536):
        """
        Initialize embeddings service.

        Args:
            driver: Neo4j driver instance
            model: Embedding model to use (default: text-embedding-3-small)
            dimension: Expected embedding dimension (default: 1536 for text-embedding-3-small)
        """
        self.driver = driver
        self.model = model
        self.dimension = dimension
        self.logger = logger

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

        try:
            result = await self.driver.execute_query(query, params)

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

        try:
            result = await self.driver.execute_query(query, params)

            # Extract embeddings in order
            embeddings = [record["embedding"] for record in sorted(result, key=lambda r: r["index"])]

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
