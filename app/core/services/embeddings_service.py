"""
OpenAI Embeddings Service
==========================

Service for generating and managing embeddings using OpenAI's API.
Handles vectorization of learning content for similarity search and recommendations.

Phase 4.3 (October 6, 2025):
- Added semantic distance calculation between entities
- Added relationship enrichment with semantic metadata
- Integrated with EdgeMetadata for Phase 4 graph-native architecture
"""

import hashlib
from operator import itemgetter
from typing import Any, Protocol

import numpy as np

from core.config import get_openai_key
from core.errors import ConfigurationError
from core.models.semantic.edge_metadata import EdgeMetadata
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.embeddings")


class EmbeddingBackendOperations(Protocol):
    """Protocol for backend operations needed by embeddings service."""

    async def get_entity_embedding(self, uid: str) -> Result[list[float] | None]:
        """Get embedding for an entity."""
        ...

    async def update_edge_metadata(
        self, from_uid: str, to_uid: str, relationship_type: str, metadata: EdgeMetadata
    ) -> Result[None]:
        """Update edge metadata in graph."""
        ...


class OpenAIEmbeddingsService:
    """
    Service for managing OpenAI embeddings.

    Features:
    - Generate embeddings for learning content
    - Cache embeddings to reduce API calls
    - Batch processing for efficiency
    - Similarity calculations


    Source Tag: "embeddings_service_explicit"
    - Format: "embeddings_service_explicit" for user-created relationships
    - Format: "embeddings_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from embeddings metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self, api_key: str | None = None, backend: EmbeddingBackendOperations | None = None
    ) -> None:
        """
        Initialize embeddings service.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var),
            backend: Optional backend for storing/retrieving embeddings from graph
        """
        # Use provided key or get from centralized config
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = get_openai_key()  # Will raise if not configured

        # Initialize OpenAI client
        try:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info("✅ OpenAI embeddings service initialized")
        except ImportError as e:
            raise ConfigurationError(
                "OpenAI library not installed. Install it with: poetry add openai"
            ) from e

        # Configuration
        self.model = "text-embedding-3-small"  # Newer, more efficient model
        self.dimensions = 1536  # Default dimensions for the model
        self.max_batch_size = 100  # OpenAI limit

        # Cache for embeddings (in production, use Redis or similar)
        self._cache: dict[str, list[float]] = {}

        # Backend for graph operations (Phase 4.3)
        self.backend = backend

    async def create_embedding(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> list[float] | None:
        """
        Create embedding for a single text.

        Args:
            text: Text to embed,
            metadata: Optional metadata for context

        Returns:
            Embedding vector or None on API failure
        """
        # self.client guaranteed to exist (service initialization fails if not configured)
        # Check cache first
        cache_key = self._get_cache_key(text)
        if cache_key in self._cache:
            logger.debug(f"Using cached embedding for: {text[:50]}...")
            return self._cache[cache_key]

        try:
            # Add metadata to text if provided
            if metadata:
                context = self._metadata_to_text(metadata)
                text = f"{text}\n\nContext: {context}"

            response = await self.client.embeddings.create(
                model=self.model, input=text, encoding_format="float"
            )

            embedding = response.data[0].embedding

            # Cache the result
            self._cache[cache_key] = embedding

            logger.debug(f"Generated embedding for: {text[:50]}...")
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            return None

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> list[list[float] | None]:
        """
        Create embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed,
            metadata_list: Optional metadata for each text

        Returns:
            List of embeddings (None for API failures)
        """
        # self.client guaranteed to exist (service initialization fails if not configured)
        results = []

        # Process in batches
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            batch_metadata = None
            if metadata_list:
                batch_metadata = metadata_list[i : i + self.max_batch_size]

            # Prepare texts with metadata
            prepared_texts = []
            for j, text in enumerate(batch):
                if batch_metadata and j < len(batch_metadata):
                    context = self._metadata_to_text(batch_metadata[j])
                    prepared_texts.append(f"{text}\n\nContext: {context}")
                else:
                    prepared_texts.append(text)

            try:
                response = await self.client.embeddings.create(
                    model=self.model, input=prepared_texts, encoding_format="float"
                )

                for text, data in zip(batch, response.data, strict=False):
                    embedding = data.embedding
                    cache_key = self._get_cache_key(text)
                    self._cache[cache_key] = embedding
                    results.append(embedding)

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                results.extend([None] * len(batch))

        logger.info(f"Generated {len(results)} embeddings in batches")
        return results

    def calculate_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector,
            embedding2: Second embedding vector

        Returns:
            Similarity score between 0 and 1
        """
        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            # Ensure result is between 0 and 1
            return max(0.0, min(1.0, (similarity + 1) / 2))

        except Exception as e:
            logger.error(f"Similarity calculation failed: {e}")
            return 0.0

    def find_similar(
        self,
        query_embedding: list[float],
        embeddings: list[tuple[str, list[float]]],
        threshold: float = 0.7,
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """
        Find similar embeddings to a query.

        Args:
            query_embedding: Query vector,
            embeddings: List of (id, embedding) tuples,
            threshold: Minimum similarity threshold,
            top_k: Return only top k results

        Returns:
            List of (id, similarity) tuples sorted by similarity
        """
        similarities = []

        for uid, embedding in embeddings:
            if embedding:
                similarity = self.calculate_similarity(query_embedding, embedding)
                if similarity >= threshold:
                    similarities.append((uid, similarity))

        # Sort by similarity (highest first)
        similarities.sort(key=itemgetter(1), reverse=True)

        if top_k:
            return similarities[:top_k]
        return similarities

    def combine_embeddings(
        self, embeddings: list[list[float]], weights: list[float] | None = None
    ) -> list[float]:
        """
        Combine multiple embeddings into one (weighted average).

        Args:
            embeddings: List of embedding vectors,
            weights: Optional weights for each embedding

        Returns:
            Combined embedding vector
        """
        if not embeddings:
            return [0.0] * self.dimensions

        if weights is None:
            weights = [1.0] * len(embeddings)

        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]

        # Weighted average
        result = np.zeros(len(embeddings[0]))
        for embedding, weight in zip(embeddings, weights, strict=False):
            result += np.array(embedding) * weight

        return result.tolist()

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()

    def _metadata_to_text(self, metadata: dict[str, Any]) -> str:
        """Convert metadata to text for embedding context."""
        parts = []

        if "tags" in metadata:
            parts.append(f"Tags: {', '.join(metadata['tags'])}")
        if "level" in metadata:
            parts.append(f"Level: {metadata['level']}")
        if "prerequisites" in metadata:
            parts.append(f"Prerequisites: {', '.join(metadata['prerequisites'])}")
        if "domain" in metadata:
            parts.append(f"Domain: {metadata['domain']}")

        return " | ".join(parts)

    async def create_knowledge_embedding(
        self, knowledge_unit: dict[str, Any]
    ) -> list[float] | None:
        """
        Create embedding specifically for a knowledge unit.

        Args:
            knowledge_unit: Knowledge unit data

        Returns:
            Embedding vector
        """
        # Combine relevant text fields
        text_parts = []

        if "title" in knowledge_unit:
            text_parts.append(f"Title: {knowledge_unit['title']}")
        if "summary" in knowledge_unit:
            text_parts.append(f"Summary: {knowledge_unit['summary']}")
        if "description" in knowledge_unit:
            text_parts.append(f"Description: {knowledge_unit['description']}")
        if "content" in knowledge_unit:
            # Limit content length to avoid token limits
            content = knowledge_unit["content"][:2000]
            text_parts.append(f"Content: {content}")

        text = "\n".join(text_parts)

        # Extract metadata
        metadata = {
            "tags": knowledge_unit.get("tags", []),
            "level": knowledge_unit.get("level"),
            "prerequisites": knowledge_unit.get("prerequisites", []),
            "domain": knowledge_unit.get("domain"),
        }

        return await self.create_embedding(text, metadata)

    @with_error_handling("create_user_context_embedding", error_type="system")
    async def create_user_context_embedding(self, user_data: dict[str, Any]) -> Result[list[float]]:
        """
        Create embedding for user's current learning context.

        Args:
            user_data: User profile and progress data

        Returns:
            Result[list[float]]: Context embedding vector
        """
        # Build user context text
        text_parts = []

        if "interests" in user_data:
            text_parts.append(f"Interests: {', '.join(user_data['interests'])}")
        if "current_goals" in user_data:
            text_parts.append(f"Goals: {', '.join(user_data['current_goals'])}")
        if "completed_topics" in user_data:
            text_parts.append(f"Completed: {', '.join(user_data['completed_topics'][:10])}")
        if "learning_style" in user_data:
            text_parts.append(f"Learning style: {user_data['learning_style']}")

        text = "\n".join(text_parts) if text_parts else "New learner"

        embedding = await self.create_embedding(text)
        if embedding is None:
            return Result.fail(Errors.system(message="Failed to create user context embedding"))

        return Result.ok(embedding)

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")

    # =========================================================================
    # PHASE 4.3: Semantic Distance Calculation (October 6, 2025)
    # =========================================================================

    async def get_embedding(self, uid: str) -> Result[list[float]]:
        """
        Get embedding for an entity.

        First checks backend storage, falls back to generating from content.

        Args:
            uid: Entity UID

        Returns:
            Result containing embedding vector
        """
        # Try to get from backend first
        if self.backend:
            embedding_result = await self.backend.get_entity_embedding(uid)
            if embedding_result.is_ok and embedding_result.value:
                return Result.ok(embedding_result.value)

        # Backend doesn't have it - would need to generate from entity content
        # For now, return error indicating embedding not available
        return Result.fail(Errors.not_found("embedding", uid))

    async def calculate_semantic_distance(self, uid_a: str, uid_b: str) -> Result[float]:
        """
        Calculate semantic distance between two entities using embeddings.

        Returns value 0-1 where:
        - 0.0 = identical/very similar
        - 1.0 = completely unrelated

        Args:
            uid_a: First entity UID,
            uid_b: Second entity UID

        Returns:
            Result containing distance value (0-1)
        """
        # Get embeddings for both entities
        embedding_a_result = await self.get_embedding(uid_a)
        if not embedding_a_result.is_ok:
            return Result.fail(embedding_a_result.expect_error())

        embedding_b_result = await self.get_embedding(uid_b)
        if not embedding_b_result.is_ok:
            return Result.fail(embedding_b_result.expect_error())

        embedding_a = embedding_a_result.value
        embedding_b = embedding_b_result.value

        # Calculate cosine similarity
        similarity = self.calculate_similarity(embedding_a, embedding_b)

        # Convert similarity (0-1) to distance (0-1)
        # Higher similarity = lower distance
        distance = 1.0 - similarity

        logger.debug(
            f"Semantic distance between {uid_a} and {uid_b}: {distance:.3f} "
            f"(similarity: {similarity:.3f})"
        )

        return Result.ok(float(distance))

    async def enrich_relationship_with_semantics(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: str,
        existing_metadata: EdgeMetadata | None = None,
    ) -> Result[EdgeMetadata]:
        """
        Add semantic distance to a relationship.

        Creates or updates edge metadata with semantic distance and confidence.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Type of relationship (e.g., RelationshipName.PREREQUISITE.value),
            existing_metadata: Optional existing metadata to update

        Returns:
            Result containing enriched EdgeMetadata
        """
        # Calculate semantic distance
        distance_result = await self.calculate_semantic_distance(from_uid, to_uid)
        if not distance_result.is_ok:
            return Result.fail(distance_result.expect_error())

        distance = distance_result.value

        # Create or update metadata
        if existing_metadata:
            # Update existing metadata
            metadata = EdgeMetadata(
                # Preserve existing fields
                confidence=existing_metadata.confidence,
                strength=existing_metadata.strength,
                difficulty_gap=existing_metadata.difficulty_gap,
                typical_learning_order=existing_metadata.typical_learning_order,
                co_occurrence_count=existing_metadata.co_occurrence_count,
                created_at=existing_metadata.created_at,
                last_traversed=existing_metadata.last_traversed,
                traversal_count=existing_metadata.traversal_count,
                user_specific=existing_metadata.user_specific,
                user_uid=existing_metadata.user_uid,
                notes=existing_metadata.notes,
                # Update semantic fields
                semantic_distance=distance,
                source="ai_enriched",  # Mark as AI-enriched
            )
        else:
            # Create new metadata
            metadata = EdgeMetadata(
                semantic_distance=distance,
                confidence=self._distance_to_confidence(distance),
                strength=1.0,  # Default strength
                source="ai_generated",
            )

        # Update edge in Neo4j if backend available
        if self.backend:
            update_result = await self.backend.update_edge_metadata(
                from_uid, to_uid, relationship_type, metadata
            )
            if not update_result.is_ok:
                return Result.fail(update_result.expect_error())

        logger.info(
            f"Enriched {relationship_type} relationship {from_uid} → {to_uid} "
            f"with semantic distance: {distance:.3f}"
        )

        return Result.ok(metadata)

    async def batch_enrich_relationships(
        self, relationships: list[tuple[str, str, str]], preserve_existing: bool = True
    ) -> Result[dict[str, EdgeMetadata]]:
        """
        Enrich multiple relationships with semantic metadata.

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples,
            preserve_existing: If True, preserve existing metadata fields

        Returns:
            Result containing dict of edge keys to metadata
        """
        results = {}
        errors = []

        for from_uid, to_uid, rel_type in relationships:
            edge_key = f"{from_uid}_{rel_type}_{to_uid}"

            # Get existing metadata if needed
            existing = None
            if preserve_existing and self.backend:
                # Would need backend method to get existing metadata
                pass

            # Enrich relationship
            result = await self.enrich_relationship_with_semantics(
                from_uid, to_uid, rel_type, existing
            )

            if result.is_ok:
                results[edge_key] = result.value
            else:
                error = result.expect_error()
                errors.append((edge_key, error.message))

        if errors:
            logger.warning(f"Failed to enrich {len(errors)} relationships: {errors[:3]}...")

        if not results:
            return Result.fail(
                Errors.integration(
                    service="embeddings",
                    message="Failed to enrich any relationships",
                    context={"error_count": len(errors), "total": len(relationships)},
                )
            )

        logger.info(
            f"Enriched {len(results)} relationships with semantic metadata ({len(errors)} failed)"
        )

        return Result.ok(results)

    def _distance_to_confidence(self, distance: float) -> float:
        """
        Convert semantic distance to confidence score.

        Closer entities = higher confidence in relationship.

        Args:
            distance: Semantic distance (0-1)

        Returns:
            Confidence score (0-1)
        """
        # Inverse relationship: distance 0 = confidence 1
        return 1.0 - distance
