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

import time
from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.config.unified_config import VectorSearchConfig

if TYPE_CHECKING:
    from core.ports import QueryExecutor
from core.models.semantic import SearchMetrics
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.vector_search")


class Neo4jVectorSearchService:
    """
    Vector similarity search using Neo4j native vector indexes.

    Uses db.index.vector.queryNodes() for fast approximate nearest neighbor search.
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        embeddings_service: Any | None = None,
        config: VectorSearchConfig | None = None,
    ) -> None:
        """
        Initialize vector search service.

        Args:
            executor: Query executor for database operations
            embeddings_service: Optional embeddings service for text-to-embedding conversion
            config: Optional vector search configuration (uses defaults if not provided)
        """
        self.executor = executor
        self.embeddings = embeddings_service
        self.config = config or VectorSearchConfig()
        self.logger = logger

    async def find_similar_by_vector(
        self,
        label: str,
        embedding: list[float],
        limit: int | None = None,
        min_score: float | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find similar nodes using vector index.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            embedding: Query embedding vector
            limit: Max results to return (uses config default if None)
            min_score: Minimum similarity score 0-1 (uses entity-specific threshold if None)

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        # Use config defaults and entity-specific thresholds
        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity(label)
        index_name = f"{label.lower()}_embedding_idx"

        query = """
        // Vector similarity search using native index
        CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
        YIELD node, score
        WHERE score >= $min_score
        RETURN node, score
        ORDER BY score DESC
        """

        params = {
            "index_name": index_name,
            "limit": limit,
            "embedding": embedding,
            "min_score": min_score,
        }

        result = await self.executor.execute_query(query, params)

        if result.is_error:
            self.logger.error(f"Vector search failed: {result.error}")
            return Result.fail(
                Errors.database(operation="vector_search", message=f"Search failed: {result.error}")
            )

        records = result.value
        if not records:
            return Result.ok([])

        # Convert to list of dicts
        similar = [{"node": record["node"], "score": record["score"]} for record in records]

        return Result.ok(similar)

    async def find_similar_by_text(
        self,
        label: str,
        text: str,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find similar nodes by generating embedding from text.

        Uses config defaults and entity-specific thresholds.

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
        limit: int | None = None,
        min_score: float | None = None,
        exclude_self: bool = True,
    ) -> Result[list[dict[str, Any]]]:
        """
        Find nodes similar to a specific node.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            uid: UID of source node
            limit: Max results to return (uses config default if None)
            min_score: Minimum similarity score (uses entity-specific threshold if None)
            exclude_self: Exclude source node from results

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        # Use config defaults
        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity(label)
        # Get source node's embedding
        query = f"""
        MATCH (source:{label} {{uid: $uid}})
        RETURN source.embedding as embedding
        """

        result = await self.executor.execute_query(query, {"uid": uid})

        if result.is_error:
            self.logger.error(f"Failed to get source embedding: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="get_embedding",
                    message=f"Failed to retrieve embedding: {result.error}",
                )
            )

        records = result.value
        if not records or not records[0].get("embedding"):
            return Result.fail(
                Errors.not_found(
                    resource=label,
                    identifier=uid,
                )
            )

        source_embedding = records[0]["embedding"]

        # Find similar nodes
        similar_result = await self.find_similar_by_vector(
            label=label,
            embedding=source_embedding,
            limit=limit + 1 if exclude_self else limit,
            min_score=min_score,
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
        limit_per_label: int | None = None,
        min_score: float | None = None,
    ) -> Result[dict[str, list[dict[str, Any]]]]:
        """
        Find similar nodes across multiple domains/labels.

        Uses entity-specific thresholds for each label.

        Args:
            embedding: Query embedding vector
            labels: List of node labels to search (e.g., ["Ku", "Task", "Goal"])
            limit_per_label: Max results per label (uses config default if None)
            min_score: Minimum similarity score - overrides entity-specific if provided

        Returns:
            Result containing dict mapping label -> list of {node, score} dicts
        """
        if limit_per_label is None:
            limit_per_label = self.config.default_limit

        results = {}

        for label in labels:
            # Use entity-specific threshold unless overridden
            label_min_score = (
                min_score if min_score is not None else self.config.get_min_score_for_entity(label)
            )

            search_result = await self.find_similar_by_vector(
                label=label, embedding=embedding, limit=limit_per_label, min_score=label_min_score
            )

            if search_result.is_ok:
                results[label] = search_result.value
            else:
                # Log error but continue with other labels
                self.logger.warning(
                    f"Search failed for label {label}: {search_result.expect_error()}"
                )
                results[label] = []

        return Result.ok(results)

    async def hybrid_search(
        self,
        label: str,
        query_text: str,
        vector_weight: float | None = None,
        limit: int | None = None,
        min_rrf_score: float | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Hybrid search combining vector similarity and full-text search.

        Uses Reciprocal Rank Fusion (RRF) to merge results from:
        1. Vector semantic search
        2. Neo4j full-text search

        RRF formula: score = Σ(1 / (k + rank)) where k=60 (standard)

        Note: RRF scores are typically in range 0.0-0.05, not 0.0-1.0.
        The min_rrf_score threshold should be set accordingly (default: 0.001).

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            query_text: Search query
            vector_weight: Weight for vector results (uses config default if None)
            limit: Max results to return (uses config default if None)
            min_rrf_score: Minimum RRF score threshold (default: 0.001, not entity-specific)

        Returns:
            Result containing list of {node, score} dicts sorted by RRF score

        Example:
            >>> result = await service.hybrid_search("Ku", "python programming", limit=10)
            >>> if result.is_ok:
            ...     for item in result.value:
            ...         print(f"{item['node']['title']}: {item['score']}")
        """
        # Use config defaults
        if limit is None:
            limit = self.config.default_limit
        if vector_weight is None:
            vector_weight = self.config.vector_weight
        # RRF scores are small (0.0-0.05), use low threshold
        if min_rrf_score is None:
            min_rrf_score = 0.001  # Not entity-specific - RRF scores are different scale

        # RRF k parameter (standard value)
        k = self.config.rrf_k

        # Step 1: Vector search (use entity-specific threshold for input search)
        entity_min_score = self.config.get_min_score_for_entity(label)
        vector_results = await self.find_similar_by_text(
            label=label, text=query_text, limit=limit * 2, min_score=entity_min_score
        )

        if vector_results.is_error:
            self.logger.warning(f"Vector search failed: {vector_results.expect_error()}")
            vector_nodes = []
        else:
            vector_nodes = vector_results.value

        # Step 2: Full-text search (no min_score - fulltext scores are different scale)
        fulltext_results = await self._fulltext_search(
            label=label, query_text=query_text, limit=limit * 2
        )

        if fulltext_results.is_error:
            self.logger.warning(f"Full-text search failed: {fulltext_results.expect_error()}")
            fulltext_nodes = []
        else:
            fulltext_nodes = fulltext_results.value

        # Step 3: RRF scoring and merging
        rrf_scores: dict[str, float] = {}
        node_data: dict[str, dict[str, Any]] = {}

        # Process vector results
        for rank, item in enumerate(vector_nodes, start=1):
            uid = item["node"]["uid"]
            rrf_score = vector_weight * (1.0 / (k + rank))
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + rrf_score
            node_data[uid] = item["node"]

        # Process full-text results
        text_weight = 1.0 - vector_weight
        for rank, item in enumerate(fulltext_nodes, start=1):
            uid = item["node"]["uid"]
            rrf_score = text_weight * (1.0 / (k + rank))
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + rrf_score
            if uid not in node_data:
                node_data[uid] = item["node"]

        # Step 4: Sort by RRF score and filter by min_rrf_score
        merged = [
            {"node": node_data[uid], "score": score}
            for uid, score in rrf_scores.items()
            if score >= min_rrf_score
        ]

        def by_score(item: dict[str, Any]) -> float:
            """Extract score for sorting."""
            return item["score"]

        merged.sort(key=by_score, reverse=True)

        # Step 5: Limit results
        final_results = merged[:limit]

        self.logger.info(
            f"Hybrid search: {len(vector_nodes)} vector + {len(fulltext_nodes)} fulltext "
            f"→ {len(merged)} merged → {len(final_results)} final (min_rrf_score={min_rrf_score:.4f})"
        )

        return Result.ok(final_results)

    async def _fulltext_search(
        self, label: str, query_text: str, limit: int
    ) -> Result[list[dict[str, Any]]]:
        """
        Full-text search using Neo4j full-text indexes.

        Internal method used by hybrid_search.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            query_text: Search query
            limit: Max results to return

        Returns:
            Result containing list of {node, score} dicts sorted by relevance
        """
        index_name = f"{label.lower()}_fulltext_idx"

        # Neo4j full-text search query
        # Note: db.index.fulltext.queryNodes returns (node, score)
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $query_text)
        YIELD node, score
        RETURN node, score
        ORDER BY score DESC
        LIMIT $limit
        """

        params = {"index_name": index_name, "query_text": query_text, "limit": limit}

        result = await self.executor.execute_query(query, params)

        if result.is_error:
            # Full-text index might not exist - return empty results instead of error
            # This allows hybrid search to fall back to vector-only
            self.logger.warning(f"Full-text search failed (index may not exist): {result.error}")
            return Result.ok([])

        records = result.value
        if not records:
            return Result.ok([])

        # Convert to list of dicts
        nodes = [{"node": record["node"], "score": record["score"]} for record in records]

        return Result.ok(nodes)

    def _create_metrics(
        self,
        query: str,
        search_type: str,
        label: str,
        results: list[dict[str, Any]],
        latency_ms: float,
        vector_weight: float | None = None,
        min_score_threshold: float | None = None,
    ) -> SearchMetrics:
        """
        Create search metrics from search results.

        Args:
            query: Search query text
            search_type: Type of search ("vector", "fulltext", "hybrid")
            label: Entity label searched
            results: Search results
            latency_ms: Query execution time in milliseconds
            vector_weight: Vector weight for hybrid search
            min_score_threshold: Minimum score threshold applied

        Returns:
            SearchMetrics instance
        """
        num_results = len(results)

        # Calculate similarity statistics
        if num_results > 0:
            scores = [r["score"] for r in results]
            avg_similarity = sum(scores) / len(scores)
            min_similarity = min(scores)
            max_similarity = max(scores)
        else:
            avg_similarity = 0.0
            min_similarity = 0.0
            max_similarity = 0.0

        return SearchMetrics(
            query=query,
            search_type=search_type,
            label=label,
            num_results=num_results,
            avg_similarity=avg_similarity,
            min_similarity=min_similarity,
            max_similarity=max_similarity,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            vector_weight=vector_weight,
            min_score_threshold=min_score_threshold,
        )

    async def find_similar_by_text_with_metrics(
        self,
        label: str,
        text: str,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> tuple[Result[list[dict[str, Any]]], SearchMetrics | None]:
        """
        Find similar nodes by text with metrics tracking.

        Wrapper around find_similar_by_text that collects performance metrics.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            text: Query text to embed and search
            limit: Max results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            Tuple of (search result, metrics)
            Metrics is None if search failed before execution
        """
        start_time = time.perf_counter()

        result = await self.find_similar_by_text(
            label=label, text=text, limit=limit, min_score=min_score
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if result.is_error:
            # Return error result without metrics
            return result, None

        # Create metrics
        metrics = self._create_metrics(
            query=text,
            search_type="vector",
            label=label,
            results=result.value,
            latency_ms=latency_ms,
            min_score_threshold=min_score,
        )

        # Log metrics
        self.logger.info(metrics.to_log_string())

        return result, metrics

    async def hybrid_search_with_metrics(
        self,
        label: str,
        query_text: str,
        vector_weight: float | None = None,
        limit: int | None = None,
        min_rrf_score: float | None = None,
    ) -> tuple[Result[list[dict[str, Any]]], SearchMetrics | None]:
        """
        Hybrid search with metrics tracking.

        Wrapper around hybrid_search that collects performance metrics.

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            query_text: Search query
            vector_weight: Weight for vector results
            limit: Max results to return
            min_rrf_score: Minimum RRF score threshold

        Returns:
            Tuple of (search result, metrics)
            Metrics is None if search failed before execution
        """
        start_time = time.perf_counter()

        result = await self.hybrid_search(
            label=label,
            query_text=query_text,
            vector_weight=vector_weight,
            limit=limit,
            min_rrf_score=min_rrf_score,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if result.is_error:
            return result, None

        # Create metrics
        metrics = self._create_metrics(
            query=query_text,
            search_type="hybrid",
            label=label,
            results=result.value,
            latency_ms=latency_ms,
            vector_weight=vector_weight or self.config.vector_weight,
            min_score_threshold=min_rrf_score,
        )

        # Log metrics
        self.logger.info(metrics.to_log_string())

        return result, metrics

    async def semantic_enhanced_search(
        self,
        label: str,
        text: str,
        context_uids: list[str] | None = None,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Vector search enhanced with semantic relationship boosting.

        Combines vector similarity with semantic context to improve result relevance.
        For each result, checks semantic relationships to provided context UIDs and
        boosts the score based on relationship type, confidence, and strength.

        Algorithm:
        1. Perform initial vector search (gets top results by cosine similarity)
        2. For each result, query semantic relationships to context_uids
        3. Calculate semantic boost based on:
           - Relationship type importance weight (from config)
           - Relationship confidence (0.0-1.0)
           - Relationship strength (0.0-1.0)
        4. Combine: final_score = vector_score * (1-w) + semantic_boost * w
           where w = semantic_boost_weight (default 0.3 = 30% semantic, 70% vector)
        5. Re-rank by enhanced score

        Args:
            label: Node label (e.g., "Ku", "Task", "Goal")
            text: Query text to embed and search
            context_uids: Optional list of UIDs representing user's current context
                         (e.g., current learning path KUs, active tasks)
            limit: Max results to return (uses config default if None)
            min_score: Minimum similarity score before boosting (uses entity-specific if None)

        Returns:
            Result containing list of {node, score} dicts sorted by enhanced relevance

        Example:
            >>> # Search for Python content in context of current learning
            >>> result = await service.semantic_enhanced_search(
            ...     label="Ku",
            ...     text="python programming",
            ...     context_uids=["ku.python-basics", "ku.functions"],
            ...     limit=10,
            ... )
            >>> if result.is_ok:
            ...     for item in result.value:
            ...         print(f"{item['node']['title']}: {item['score']:.3f}")

        Performance:
            - Adds ~30-50ms per search (1-2 graph queries for relationships)
            - Recommended for interactive search (not background batch)
        """
        if not self.config.semantic_boost_enabled:
            # Fall back to standard vector search if boosting disabled
            return await self.find_similar_by_text(
                label=label, text=text, limit=limit, min_score=min_score
            )

        if not context_uids:
            # No context provided - fall back to standard vector search
            return await self.find_similar_by_text(
                label=label, text=text, limit=limit, min_score=min_score
            )

        # Use config defaults
        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity(label)

        # Step 1: Perform initial vector search (fetch 2x limit for better coverage)
        vector_results = await self.find_similar_by_text(
            label=label, text=text, limit=limit * 2, min_score=min_score
        )

        if vector_results.is_error:
            return vector_results

        results = vector_results.value

        if not results:
            return Result.ok([])

        # Step 2: For each result, calculate semantic boost
        for result in results:
            uid = result["node"]["uid"]
            vector_score = result["score"]

            # Query semantic relationships to context UIDs
            semantic_boost = await self._calculate_semantic_boost(uid, context_uids)

            # Step 3: Combine vector similarity + semantic boost
            # final_score = vector_score * (1 - w) + semantic_boost * w
            vector_weight = 1.0 - self.config.semantic_boost_weight
            semantic_weight = self.config.semantic_boost_weight

            enhanced_score = (vector_score * vector_weight) + (semantic_boost * semantic_weight)

            result["score"] = enhanced_score
            result["vector_score"] = vector_score  # Preserve original for debugging
            result["semantic_boost"] = semantic_boost

        # Step 4: Re-rank by enhanced score
        results.sort(key=itemgetter("score"), reverse=True)

        # Step 5: Limit to requested count
        final_results = results[:limit]

        self.logger.info(
            f"Semantic-enhanced search: {len(results)} candidates → {len(final_results)} final "
            f"(boost_weight={self.config.semantic_boost_weight:.2f}, context_uids={len(context_uids)})"
        )

        return Result.ok(final_results)

    async def _calculate_semantic_boost(
        self,
        entity_uid: str,
        context_uids: list[str],
    ) -> float:
        """
        Calculate semantic relationship boost for an entity.

        Queries semantic relationships between entity and context UIDs,
        then computes boost based on relationship metadata.

        Args:
            entity_uid: Entity UID to calculate boost for
            context_uids: List of context UIDs to check relationships against

        Returns:
            Semantic boost score (0.0-1.0)
        """
        # Query semantic relationships from entity to context UIDs
        query = """
        MATCH (entity {uid: $entity_uid})
        MATCH (context)
        WHERE context.uid IN $context_uids
        MATCH (entity)-[r]->(context)
        WHERE r.confidence IS NOT NULL
        RETURN
            type(r) as relationship_type,
            r.confidence as confidence,
            COALESCE(r.strength, 1.0) as strength
        """

        params = {
            "entity_uid": entity_uid,
            "context_uids": context_uids,
        }

        try:
            result = await self.executor.execute_query(query, params)

            if result.is_error or not result.value:
                return 0.0

            records = result.value

            # Aggregate boosts from all relationships
            total_boost = 0.0
            relationship_count = 0

            for record in records:
                rel_type = record["relationship_type"]
                confidence = record["confidence"]
                strength = record["strength"]

                # Get importance weight for this relationship type
                type_weight = self.config.get_relationship_weight(rel_type)

                # Calculate boost contribution from this relationship
                # boost = type_weight * confidence * strength
                boost_contribution = type_weight * confidence * strength

                total_boost += boost_contribution
                relationship_count += 1

            # Normalize by number of relationships (average boost)
            if relationship_count > 0:
                avg_boost = total_boost / relationship_count
                # Cap at 1.0
                return min(avg_boost, 1.0)

            return 0.0

        except Exception as e:
            self.logger.warning(f"Failed to calculate semantic boost for {entity_uid}: {e}")
            return 0.0  # Fail gracefully - return no boost

    async def learning_aware_search(
        self,
        label: str,
        text: str,
        user_uid: str,
        prefer_unmastered: bool = True,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Vector search with learning state boosting for personalized results.

        Adjusts search results based on user's learning progress to prioritize
        content aligned with their current learning journey. Useful for
        "what should I learn next?" style searches.

        Boost Strategy:
        - MASTERED: -20% penalty (user already knows this)
        - IN_PROGRESS: +10% boost (currently learning, highly relevant)
        - VIEWED: 0% neutral (seen but not actively working on)
        - NOT_STARTED: +15% boost (new content, prioritize discovery)

        Args:
            label: Node label (currently only "Ku" supported)
            text: Query text to embed and search
            user_uid: User's UID for learning state lookup
            prefer_unmastered: If True, applies boosts as above. If False, inverts
                              boosts to prioritize mastered content (useful for review)
            limit: Max results to return (uses config default if None)
            min_score: Minimum similarity score before boosting (uses entity-specific if None)

        Returns:
            Result containing list of {node, score} dicts sorted by learning-aware relevance

        Example:
            >>> # Search for Python content, prioritizing unlearned material
            >>> result = await service.learning_aware_search(
            ...     label="Ku",
            ...     text="python programming",
            ...     user_uid="user_alice",
            ...     prefer_unmastered=True,
            ...     limit=10,
            ... )
            >>> if result.is_ok:
            ...     for item in result.value:
            ...         state = item.get("learning_state", "none")
            ...         print(f"{item['node']['title']}: {item['score']:.3f} ({state})")

        Performance:
            - Adds ~20-30ms per search (1 batch query for learning states)
            - Recommended for interactive "next steps" recommendations
        """
        # Only supported for Knowledge Units currently
        if label != "Ku":
            self.logger.warning(
                f"Learning-aware search only supports Ku, got {label}. Falling back."
            )
            return await self.find_similar_by_text(
                label=label, text=text, limit=limit, min_score=min_score
            )

        # Use config defaults
        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity(label)

        # Step 1: Perform initial vector search (fetch 2x limit for better coverage)
        vector_results = await self.find_similar_by_text(
            label=label, text=text, limit=limit * 2, min_score=min_score
        )

        if vector_results.is_error:
            return vector_results

        results = vector_results.value

        if not results:
            return Result.ok([])

        # Step 2: Batch fetch learning states for all result KUs
        ku_uids = [r["node"]["uid"] for r in results]
        learning_states_result = await self._get_learning_states_batch(user_uid, ku_uids)

        if learning_states_result.is_error:
            # If learning state fetch fails, log and fall back to unmodified results
            self.logger.warning(
                f"Failed to fetch learning states: {learning_states_result.expect_error()}"
            )
            learning_states = {}
        else:
            learning_states = learning_states_result.value

        # Step 3: Apply learning state boost to each result
        for result in results:
            uid = result["node"]["uid"]
            vector_score = result["score"]

            # Get learning state for this KU
            state = learning_states.get(uid, "none")

            # Get boost multiplier from config
            boost_multiplier = self.config.get_learning_state_boost(state)

            # Invert boost if prefer_unmastered is False (for review mode)
            if not prefer_unmastered:
                boost_multiplier = -boost_multiplier

            # Apply boost: score * (1 + boost_multiplier)
            # Example: 0.8 score with +15% boost = 0.8 * 1.15 = 0.92
            boosted_score = vector_score * (1.0 + boost_multiplier)

            result["score"] = boosted_score
            result["vector_score"] = vector_score  # Preserve original
            result["learning_state"] = state
            result["learning_boost"] = boost_multiplier

        # Step 4: Re-rank by boosted score
        results.sort(key=itemgetter("score"), reverse=True)

        # Step 5: Limit to requested count
        final_results = results[:limit]

        # Log summary
        state_counts = {}
        for r in final_results:
            state = r.get("learning_state", "none")
            state_counts[state] = state_counts.get(state, 0) + 1

        self.logger.info(
            f"Learning-aware search: {len(results)} candidates → {len(final_results)} final "
            f"(states={state_counts}, prefer_unmastered={prefer_unmastered})"
        )

        return Result.ok(final_results)

    async def _get_learning_states_batch(
        self,
        user_uid: str,
        ku_uids: list[str],
    ) -> Result[dict[str, str]]:
        """
        Batch fetch learning states for multiple KUs.

        Internal helper that queries learning state relationships efficiently.
        Returns dict mapping ku_uid -> state string.

        Args:
            user_uid: User's UID
            ku_uids: List of KU UIDs to check

        Returns:
            Result containing dict of ku_uid -> learning_state
            States: "mastered", "in_progress", "viewed", "none"
        """
        if not ku_uids:
            return Result.ok({})

        query = """
        UNWIND $ku_uids as ku_uid
        MATCH (ku:Ku {uid: ku_uid})
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
        RETURN
            ku.uid as ku_uid,
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered
        """

        result = await self.executor.execute_query(
            query, {"user_uid": user_uid, "ku_uids": ku_uids}
        )

        if result.is_error:
            self.logger.error(f"Failed to batch fetch learning states: {result.error}")
            return Result.fail(
                Errors.database(operation="get_learning_states_batch", message=str(result.error))
            )

        states = {}
        for record in result.value:
            if record["has_mastered"]:
                state = "mastered"
            elif record["has_in_progress"]:
                state = "in_progress"
            elif record["has_viewed"]:
                state = "viewed"
            else:
                state = "none"
            states[record["ku_uid"]] = state

        return Result.ok(states)
