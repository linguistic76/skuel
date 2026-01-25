"""
Intent Classifier - Semantic Query Intent Classification
=========================================================

Uses embeddings to classify user query intent.
Extracted from QueryProcessor for single responsibility.

Responsibilities:
- Classify query intent using embeddings-based semantic classification
- Provide keyword-based fallback for offline scenarios
- Manage lazy-loaded intent exemplar embeddings

Architecture:
- Requires EmbeddingsService for semantic classification
- Uses INTENT_EXEMPLARS for semantic similarity matching
- Returns QueryIntent enum values

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
"""

from __future__ import annotations

from typing import Any

from core.models.query import QueryIntent
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# ============================================================================
# INTENT EXEMPLARS - For Embedding-Based Intent Classification
# ============================================================================

INTENT_EXEMPLARS: dict[QueryIntent, list[str]] = {
    QueryIntent.HIERARCHICAL: [
        "What should I learn next?",
        "I want to get better at Python",
        "Help me improve my coding skills",
        "What topics should I study?",
        "How can I master async programming?",
        "What should I focus on learning?",
        "I want to understand machine learning better",
        "How do I improve my knowledge of databases?",
    ],
    QueryIntent.PREREQUISITE: [
        "What do I need to learn before async?",
        "What's required before I start decorators?",
        "What are the prerequisites for this topic?",
        "What should I know first?",
        "What do I need to understand beforehand?",
        "What comes before learning this?",
        "What foundation do I need?",
        "What should I master before tackling this?",
    ],
    QueryIntent.PRACTICE: [
        "Where can I practice this?",
        "How do I apply what I learned?",
        "Give me exercises for Python",
        "What projects use this skill?",
        "How can I use this in real work?",
        "Show me practical examples",
        "Where can I try this out?",
        "What tasks will help me practice?",
    ],
    QueryIntent.EXPLORATORY: [
        "Show me what's available",
        "What can I learn about?",
        "Explore Python topics",
        "What's in my learning path?",
        "Discover new concepts",
        "What topics are related?",
        "Browse available knowledge",
        "What else is there?",
    ],
    QueryIntent.RELATIONSHIP: [
        "How are these topics connected?",
        "What's related to Python?",
        "Show me similar concepts",
        "How does this relate to that?",
        "What's linked to async programming?",
        "Find connections between topics",
        "What shares common ground?",
        "How do these concepts tie together?",
    ],
    QueryIntent.AGGREGATION: [
        "How many tasks do I have?",
        "What's my total progress?",
        "Show me statistics",
        "Count my goals",
        "What are my metrics?",
        "Summarize my learning",
        "Give me an overview",
        "What's my status?",
    ],
}


class IntentClassifier:
    """
    Classify user query intent using semantic similarity.

    This service handles intent classification:
    - Embedding-based semantic classification (primary)
    - Keyword-based fallback classification
    - Lazy-loaded intent exemplar embeddings

    Architecture:
    - Requires EmbeddingsService for semantic classification
    - Uses INTENT_EXEMPLARS for similarity matching
    - Returns QueryIntent enum values

    Usage:
        classifier = IntentClassifier(embeddings_service)
        result = await classifier.classify_intent("What should I learn next?")
        if result.is_ok:
            intent = result.value  # QueryIntent.HIERARCHICAL
    """

    def __init__(self, embeddings_service: Any = None) -> None:
        """
        Initialize intent classifier.

        Args:
            embeddings_service: EmbeddingsService for semantic search

        Note:
            embeddings_service is required for semantic classification.
            If None, classify_intent() will return Result.fail().
        """
        self.embeddings_service = embeddings_service

        # Lazy-loaded intent exemplar embeddings (one-time initialization)
        self._intent_exemplar_embeddings: dict[QueryIntent, list[list[float]]] | None = None

        logger.info("IntentClassifier initialized")

    async def classify_intent(self, query: str) -> Result[QueryIntent]:
        """
        Classify query intent using embeddings-based semantic classification.

        Fail-fast design: Requires embeddings service (no keyword fallback).

        Strategy:
        1. Embedding-based classification (semantic understanding)
        2. Returns high-confidence intent or defaults to SPECIFIC

        Args:
            query: User's natural language question

        Returns:
            Result[QueryIntent] - Success with intent or failure with error
        """
        # Fail-fast: embeddings service is required
        if not self.embeddings_service:
            return Result.fail(
                Errors.system(
                    message="EmbeddingsService is required for intent classification - "
                    "ensure OPENAI_API_KEY is configured",
                    operation="classify_intent",
                )
            )

        try:
            # Embedding-based intent detection
            intent = await self._classify_via_embeddings(query)
            if intent:
                logger.debug("Intent classified via embeddings: %s", intent.value)
                return Result.ok(intent)

            # Low confidence - default to SPECIFIC
            logger.debug("Low confidence embedding match - defaulting to SPECIFIC intent")
            return Result.ok(QueryIntent.SPECIFIC)
        except ValueError as e:
            return Result.fail(
                Errors.system(
                    message=str(e),
                    operation="classify_intent",
                )
            )

    async def _classify_via_embeddings(self, query: str) -> QueryIntent | None:
        """
        Classify intent using semantic similarity to exemplars.

        Approach:
        1. Get query embedding
        2. Compare to pre-computed intent exemplar embeddings
        3. Return intent with highest average similarity (if above threshold)

        Args:
            query: User's natural language question

        Returns:
            QueryIntent if confidence >= 0.65, else None (low confidence)
        """
        # Ensure exemplar embeddings are loaded (lazy initialization)
        await self._ensure_exemplars_loaded()

        if not self._intent_exemplar_embeddings:
            raise ValueError(
                "Intent exemplar embeddings failed to load - check embeddings service configuration"
            )

        # Create query embedding
        query_embedding = await self.embeddings_service.create_embedding(query)
        if not query_embedding:
            raise ValueError("Failed to create query embedding - OpenAI API may be unavailable")

        # Compare to each intent's exemplar embeddings
        best_intent = None
        best_score = 0.0

        for intent, exemplar_embeddings in self._intent_exemplar_embeddings.items():
            # Calculate average similarity to all exemplars for this intent
            similarities = [
                self._cosine_similarity(query_embedding, exemplar_emb)
                for exemplar_emb in exemplar_embeddings
            ]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

            if avg_similarity > best_score:
                best_score = avg_similarity
                best_intent = intent

        # Return if confidence is high enough (65% threshold)
        if best_score >= 0.65:
            logger.debug(
                "Embedding classification: %s (score: %.2f)",
                best_intent.value if best_intent else None,
                best_score,
            )
            return best_intent

        return None

    def classify_via_keywords(self, query: str) -> QueryIntent:
        """
        Classify intent using keyword matching (fallback approach).

        Args:
            query: User's question

        Returns:
            QueryIntent enum value (always returns a value)
        """
        message_lower = query.lower()

        if any(word in message_lower for word in ["learn", "study", "understand", "master"]):
            return QueryIntent.HIERARCHICAL
        elif any(word in message_lower for word in ["prerequisite", "need", "require", "before"]):
            return QueryIntent.PREREQUISITE
        elif any(word in message_lower for word in ["practice", "apply", "use", "exercise"]):
            return QueryIntent.PRACTICE
        elif any(word in message_lower for word in ["explore", "discover", "find", "what"]):
            return QueryIntent.EXPLORATORY
        elif any(word in message_lower for word in ["relate", "connect", "similar", "link"]):
            return QueryIntent.RELATIONSHIP
        elif any(
            word in message_lower
            for word in ["how many", "count", "total", "statistics", "metrics", "summary"]
        ):
            return QueryIntent.AGGREGATION
        else:
            return QueryIntent.SPECIFIC

    async def _ensure_exemplars_loaded(self) -> None:
        """
        Lazy-load intent exemplar embeddings on first use.

        Generates embeddings for all INTENT_EXEMPLARS and caches them
        for efficient intent classification.
        """
        if self._intent_exemplar_embeddings is not None:
            return  # Already loaded

        logger.info("Loading intent exemplar embeddings (one-time initialization)...")

        exemplar_embeddings: dict[QueryIntent, list[list[float]]] = {}

        for intent, exemplar_queries in INTENT_EXEMPLARS.items():
            embeddings_for_intent = []

            for exemplar_query in exemplar_queries:
                embedding = await self.embeddings_service.create_embedding(exemplar_query)
                if embedding:
                    embeddings_for_intent.append(embedding)

            if embeddings_for_intent:
                exemplar_embeddings[intent] = embeddings_for_intent
                logger.debug("Loaded %d exemplars for %s", len(embeddings_for_intent), intent.value)

        self._intent_exemplar_embeddings = exemplar_embeddings
        logger.info("Intent exemplar embeddings loaded (%d intents)", len(exemplar_embeddings))

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0.0 to 1.0)
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)
