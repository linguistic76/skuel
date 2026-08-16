"""
Neo4j Vector Search Service
============================

Uses native vector indexes and db.index.vector.queryNodes() for semantic search.

PERFORMANCE:
- Uses db.index.vector.queryNodes() for fast approximate nearest neighbor search
- Vector indexes must be created first (via schema manager)
- Supports top-K retrieval with similarity scores

ARCHITECTURE:
- Works with EmbeddingsService for embedding generation
- Requires vector indexes created on embedding fields
- Returns nodes with similarity scores sorted by relevance

See: /docs/architecture/NEO4J_GENAI_ARCHITECTURE.md
"""

import time
from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.config.unified_config import VectorSearchConfig
from core.models.enums.neo_labels import NeoLabel
from core.models.semantic import SearchMetrics
from core.models.type_hints import EntityUID, FilterParams, UserUID
from core.ports.query_types import SemanticSearchChunkResult

if TYPE_CHECKING:
    from core.ports.vector_search_protocols import VectorSearchBackendOperations
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.lucene import escape_lucene_query
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.vector_search")


class Neo4jVectorSearchService:
    """
    Vector similarity search using Neo4j native vector indexes.

    Uses db.index.vector.queryNodes() for fast approximate nearest neighbor search.
    """

    def __init__(
        self,
        backend: "VectorSearchBackendOperations",
        embeddings_service: Any | None = None,
        config: VectorSearchConfig | None = None,
    ) -> None:
        """
        Initialize vector search service.

        Args:
            backend: Typed backend for vector search persistence
            embeddings_service: Optional embeddings service for text-to-embedding conversion
            config: Optional vector search configuration (uses defaults if not provided)
        """
        self.backend = backend
        self.embeddings = embeddings_service
        self.config = config or VectorSearchConfig()
        self.logger = logger

    @property
    def max_rrf_score(self) -> float:
        """
        The largest RRF score `hybrid_search` can produce, for normalization.

        A document ranked first by BOTH halves scores
        `vector_weight/(k+1) + text_weight/(k+1)`, and the two weights always
        sum to 1 (`text_weight = 1.0 - vector_weight`), so the ceiling is
        `1/(k+1)` — independent of the weight split, and identical for every
        label.

        That last property is the point: a caller ranking hits from several
        labels together must divide by a SHARED ceiling. Normalizing per batch
        instead hands every label's best hit a 1.0 and throws away the
        difference between "ranked first by both halves" and "ranked first by
        one" (Codex, PR #1074).
        """
        return 1.0 / (self.config.rrf_k + 1)

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
            label: Node label (e.g., "Entity", "Task", "Goal")
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

        result = await self.backend.query_vector_index(index_name, limit, embedding, min_score)

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
            label: Node label (e.g., "Entity", "Task", "Goal")
            text: Query text to embed and search
            limit: Max results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        embedding_result = await self.embed_query(text)
        if embedding_result.is_error:
            return Result.fail(embedding_result)

        return await self.find_similar_by_vector(
            label=label, embedding=embedding_result.value, limit=limit, min_score=min_score
        )

    async def embed_query(self, text: str) -> Result[list[float]]:
        """
        Embed query text for vector search.

        Split out so a caller fanning ONE query across several labels can pay
        for the embedding once and hand the vector to each `hybrid_search`
        call. `create_embedding` is uncached, so a per-label embed makes the
        same request N times, sequentially (Codex, PR #1074).

        Args:
            text: Query text to embed

        Returns:
            Result containing the embedding vector, or `unavailable` on the
            CORE tier (no embeddings service)
        """
        if not self.embeddings:
            return Result.fail(
                Errors.unavailable(
                    feature="semantic_search",
                    reason="Embeddings service required for semantic search. Configure OPENAI_API_KEY.",
                    operation="embed_query",
                )
            )

        result: Result[list[float]] = await self.embeddings.create_embedding(text)
        return result

    async def hybrid_search(
        self,
        label: str,
        query_text: str,
        vector_weight: float | None = None,
        limit: int | None = None,
        min_rrf_score: float | None = None,
        query_embedding: list[float] | None = None,
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
            label: Node label (e.g., "Entity", "Task", "Goal")
            query_text: Search query
            vector_weight: Weight for vector results (uses config default if None)
            limit: Max results to return (uses config default if None)
            min_rrf_score: Minimum RRF score threshold (default: 0.001, not entity-specific)
            query_embedding: Pre-computed embedding of `query_text`. Supply it when
                fanning one query across several labels — otherwise each call
                re-embeds the same text through the uncached embeddings service.

        Returns:
            Result containing list of {node, score, matched_vector,
            matched_fulltext} dicts sorted by RRF score. The two flags say
            which half produced the hit, so a caller can describe the match
            honestly when only one half ran.

        Example:
            >>> result = await service.hybrid_search("Entity", "python programming", limit=10)
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
            min_rrf_score = self.config.min_rrf_score  # Not entity-specific - different scale

        # RRF k parameter (standard value)
        k = self.config.rrf_k

        # Step 1: Vector search (use entity-specific threshold for input search).
        # A caller-supplied embedding skips the paid embed — same vector either way.
        entity_min_score = self.config.get_min_score_for_entity(label)
        if query_embedding is not None:
            vector_results = await self.find_similar_by_vector(
                label=label, embedding=query_embedding, limit=limit * 2, min_score=entity_min_score
            )
        else:
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
        # WHICH half produced each uid, carried through to the caller: a
        # presentation layer that says "keyword + semantic" for every hit lies
        # whenever one half returned nothing — fulltext-only after an
        # embedding/index failure, or before a label's embeddings are
        # backfilled (Codex, PR #1074).
        vector_uids: set[str] = set()
        fulltext_uids: set[str] = set()

        # Process vector results
        for rank, item in enumerate(vector_nodes, start=1):
            uid = item["node"]["uid"]
            rrf_score = vector_weight * (1.0 / (k + rank))
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + rrf_score
            node_data[uid] = item["node"]
            vector_uids.add(uid)

        # Process full-text results
        text_weight = 1.0 - vector_weight
        for rank, item in enumerate(fulltext_nodes, start=1):
            uid = item["node"]["uid"]
            rrf_score = text_weight * (1.0 / (k + rank))
            rrf_scores[uid] = rrf_scores.get(uid, 0.0) + rrf_score
            fulltext_uids.add(uid)
            if uid not in node_data:
                node_data[uid] = item["node"]

        # Step 4: Sort by RRF score and filter by min_rrf_score
        merged = [
            {
                "node": node_data[uid],
                "score": score,
                "matched_vector": uid in vector_uids,
                "matched_fulltext": uid in fulltext_uids,
            }
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

        Internal method used by hybrid_search. User input is Lucene-escaped
        here — ``queryNodes`` parses its argument as a Lucene query, so a raw
        ``+``/``(``/``"`` is a parse error rather than a search.

        Args:
            label: Node label (e.g., "Entity", "Task", "Goal") — comes from
                config/enum derivation, never user input
            query_text: Search query
            limit: Max results to return

        Returns:
            Result containing list of {node, score} dicts sorted by relevance.
            A label whose index does not exist degrades to an empty result so
            hybrid search can continue vector-only.

        Raises:
            ValueError: label is not a NeoLabel member. Fail-fast by design —
                an unknown label is a coding error, and the old flat
                ``label.lower()`` derivation turned it into a silent no-op.
        """
        index_name = NeoLabel.fulltext_index_name(label)

        result = await self.backend.query_fulltext_index(
            index_name, escape_lucene_query(query_text), limit
        )

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

    async def find_similar_chunks_by_text(
        self,
        text: str,
        chunk_types: list[str] | None = None,
        parent_uid: str | None = None,
        limit: int | None = None,
        min_score: float | None = None,
        parent_filters: FilterParams | None = None,
    ) -> Result[list[SemanticSearchChunkResult]]:
        """Find similar :ContentChunk nodes by embedding the query text.

        Returns SemanticSearchChunkResult-shaped dicts (chunk_uid, chunk_type,
        text, context_window, similarity_score, parent_uid, parent_title) so
        callers can ground responses in the matched passage AND cite the
        owning Entity (PathStep).

        Args:
            text: Query text to embed and search.
            chunk_types: Optional filter of persisted ``ContentChunkType`` values
                (e.g. ``["definition", "example"]``) — matched against
                ``chunk.chunk_type``, which the content adapters write as
                ``chunk_type.value`` (lowercase). An unknown name matches zero
                rows silently rather than erroring.
            parent_uid: Optional filter restricting chunks to a single parent.
            limit: Max results (uses config default if None).
            min_score: Similarity threshold (uses ContentChunk threshold if None).
            parent_filters: Optional facet scope on the chunk's owning Entity
                (e.g. ``{"nous": "body"}``) — the same facet→property mapping
                faceted search applies to entities, so body hits stay inside the
                active facets instead of leaking across topics.
        """
        if not self.embeddings:
            return Result.fail(
                Errors.unavailable(
                    feature="semantic_chunk_search",
                    reason="Embeddings service required. Configure OPENAI_API_KEY.",
                    operation="find_similar_chunks_by_text",
                )
            )

        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity("ContentChunk")

        embedding_result = await self.embeddings.create_embedding(text)
        if embedding_result.is_error:
            return Result.fail(embedding_result)

        result = await self.backend.semantic_search_chunks(
            query_embedding=embedding_result.value,
            limit=limit,
            threshold=min_score,
            chunk_types=chunk_types,
            parent_uid=parent_uid,
            parent_filters=parent_filters,
        )

        if result.is_error:
            self.logger.error(f"Chunk vector search failed: {result.expect_error()}")
            return Result.fail(result)

        return Result.ok(list(result.value))

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
            label: Node label (e.g., "Entity", "Task", "Goal")
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
            ...     label="Entity",
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
        entity_uid: EntityUID,
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
        try:
            result = await self.backend.get_semantic_relationships(entity_uid, context_uids)

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

        except NEO4J_EXCEPTIONS as e:
            self.logger.warning(f"Failed to calculate semantic boost for {entity_uid}: {e}")
            return 0.0  # Fail gracefully - return no boost

    async def learning_aware_search(
        self,
        label: str,
        text: str,
        user_uid: UserUID,
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
            label: Node label (currently only "Entity" supported)
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
            ...     label="Entity",
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
        if label != "Entity":
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
        state_counts: dict[str, int] = {}
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
        user_uid: UserUID,
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

        result = await self.backend.get_learning_states_batch(user_uid, ku_uids)

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

    async def find_related_concepts(self, label: str, uid: str) -> Result[list[dict[str, Any]]]:
        """
        Read-time "Related concepts" lens for the Ku/PathStep detail pages.

        Node→node similarity against the node's own-label vector index with
        the empirically derived node→node threshold (node→node scores run
        lower than text→entity queries, so ku_min_score would starve it —
        see VectorSearchConfig.ku_similar_min_score for the derivation).
        Read-only: no edges are created or persisted from this path.

        Args:
            label: Node label — "Ku" or "PathStep"
            uid: UID of the source node

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        return await self.find_similar_to_node(
            label=label,
            uid=uid,
            limit=self.config.related_concepts_limit,
            min_score=self.config.ku_similar_min_score,
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
            label: Node label (e.g., "Entity", "Task", "Goal")
            uid: UID of source node
            limit: Max results to return (uses config default if None)
            min_score: Minimum similarity score (uses entity-specific threshold if None)
            exclude_self: Exclude source node from results

        Returns:
            Result containing list of {node, score} dicts sorted by similarity
        """
        if limit is None:
            limit = self.config.default_limit
        if min_score is None:
            min_score = self.config.get_min_score_for_entity(label)
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))
        result = await self.backend.get_node_embedding(NeoLabel(label), uid)

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

        similar_result = await self.find_similar_by_vector(
            label=label,
            embedding=source_embedding,
            limit=limit + 1 if exclude_self else limit,
            min_score=min_score,
        )

        if similar_result.is_error:
            return similar_result

        similar = similar_result.value

        if exclude_self:
            similar = [s for s in similar if s["node"].get("uid") != uid][:limit]

        return Result.ok(similar)

    # -------------------------------------------------------------------------
    # Test-covered public API — no production route caller yet (PLANNED)
    # -------------------------------------------------------------------------

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
            labels: List of node labels to search (e.g., ["Entity", "Task", "Goal"])
            limit_per_label: Max results per label (uses config default if None)
            min_score: Minimum similarity score — overrides entity-specific if provided

        Returns:
            Result containing dict mapping label -> list of {node, score} dicts
        """
        if limit_per_label is None:
            limit_per_label = self.config.default_limit

        results = {}

        for label in labels:
            label_min_score = (
                min_score if min_score is not None else self.config.get_min_score_for_entity(label)
            )

            search_result = await self.find_similar_by_vector(
                label=label, embedding=embedding, limit=limit_per_label, min_score=label_min_score
            )

            if search_result.is_ok:
                results[label] = search_result.value
            else:
                self.logger.warning(
                    f"Search failed for label {label}: {search_result.expect_error()}"
                )
                results[label] = []

        return Result.ok(results)

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
        """
        start_time = time.perf_counter()

        result = await self.find_similar_by_text(
            label=label, text=text, limit=limit, min_score=min_score
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if result.is_error:
            return result, None

        metrics = self._create_metrics(
            query=text,
            search_type="vector",
            label=label,
            results=result.value,
            latency_ms=latency_ms,
            min_score_threshold=min_score,
        )

        self.logger.info(metrics.to_log_string())

        return result, metrics

    async def hybrid_search_with_metrics(
        self,
        label: str,
        query_text: str,
        vector_weight: float | None = None,
        limit: int | None = None,
        min_rrf_score: float | None = None,
        query_embedding: list[float] | None = None,
    ) -> tuple[Result[list[dict[str, Any]]], SearchMetrics | None]:
        """
        Hybrid search with metrics tracking.

        Wrapper around hybrid_search that collects performance metrics.
        `query_embedding` is passed straight through — see `hybrid_search`.
        """
        start_time = time.perf_counter()

        result = await self.hybrid_search(
            label=label,
            query_text=query_text,
            vector_weight=vector_weight,
            limit=limit,
            min_rrf_score=min_rrf_score,
            query_embedding=query_embedding,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if result.is_error:
            return result, None

        metrics = self._create_metrics(
            query=query_text,
            search_type="hybrid",
            label=label,
            results=result.value,
            latency_ms=latency_ms,
            vector_weight=vector_weight or self.config.vector_weight,
            min_score_threshold=min_rrf_score,
        )

        self.logger.info(metrics.to_log_string())

        return result, metrics

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
        """Create search metrics from search results."""
        num_results = len(results)

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
