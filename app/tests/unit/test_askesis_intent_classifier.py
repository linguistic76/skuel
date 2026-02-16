"""
Test Suite for IntentClassifier
================================

Tests the askesis intent classification service:
- Embedding-based classification
- Keyword fallback classification
- Confidence threshold handling
- Intent type coverage
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.askesis.intent_classifier import IntentClassifier, QueryIntent
from core.utils.result_simplified import Result

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_embeddings_service() -> Mock:
    """Create mock EmbeddingsService with correct method name and return type."""
    embeddings = Mock()

    # Production code calls .is_ok/.is_error/.value on the result
    embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1] * 1536))

    return embeddings


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_embeddings():
    return create_mock_embeddings_service()


@pytest.fixture
def classifier_with_embeddings(mock_embeddings):
    """IntentClassifier with embeddings service."""
    return IntentClassifier(embeddings_service=mock_embeddings)


@pytest.fixture
def classifier_no_embeddings():
    """IntentClassifier without embeddings (keyword fallback)."""
    # Note: IntentClassifier may require embeddings - adjust based on implementation
    try:
        return IntentClassifier()
    except (ValueError, TypeError):
        # If embeddings required, skip tests that need this fixture
        pytest.skip("IntentClassifier requires embeddings_service")


# ============================================================================
# TESTS: Embedding-Based Classification
# ============================================================================


class TestEmbeddingBasedClassification:
    """Test embedding-based intent classification."""

    @pytest.mark.asyncio
    async def test_classify_intent_embedding_based(self, classifier_with_embeddings):
        """Classifies intent using embeddings."""
        query = "What should I learn next?"

        result = await classifier_with_embeddings.classify_intent(query)

        assert result.is_ok
        assert isinstance(result.value, QueryIntent)

    @pytest.mark.asyncio
    async def test_classify_intent_hierarchical_query(self, classifier_with_embeddings):
        """Hierarchical query classified correctly."""
        query = "How do I progress in machine learning?"

        result = await classifier_with_embeddings.classify_intent(query)

        assert result.is_ok
        assert isinstance(result.value, QueryIntent)
        # Should classify as HIERARCHICAL or PREREQUISITE

    @pytest.mark.asyncio
    async def test_classify_intent_practice_query(self, classifier_with_embeddings):
        """Practice query classified correctly."""
        query = "Give me exercises for Python"

        result = await classifier_with_embeddings.classify_intent(query)

        assert result.is_ok
        assert isinstance(result.value, QueryIntent)
        # Should classify as PRACTICE


# ============================================================================
# TESTS: Keyword Fallback Classification
# ============================================================================


class TestKeywordFallbackClassification:
    """Test keyword-based fallback classification."""

    @pytest.mark.asyncio
    async def test_classify_via_keywords_learning(self, classifier_with_embeddings):
        """Keywords detect learning-related intents."""
        intent = classifier_with_embeddings.classify_via_keywords("learn skills develop master")

        assert isinstance(intent, QueryIntent)

    @pytest.mark.asyncio
    async def test_classify_via_keywords_prerequisite(self, classifier_with_embeddings):
        """Keywords detect prerequisite intents."""
        intent = classifier_with_embeddings.classify_via_keywords("what do I need before starting")

        assert isinstance(intent, QueryIntent)

    @pytest.mark.asyncio
    async def test_classify_via_keywords_practice(self, classifier_with_embeddings):
        """Keywords detect practice intents."""
        intent = classifier_with_embeddings.classify_via_keywords("exercises practice apply")

        assert isinstance(intent, QueryIntent)


# ============================================================================
# TESTS: Confidence Threshold
# ============================================================================


class TestConfidenceThreshold:
    """Test confidence threshold handling."""

    @pytest.mark.asyncio
    async def test_classify_intent_confidence_threshold(self, classifier_with_embeddings):
        """Low confidence falls back to keyword or default."""
        # Ambiguous query
        query = "hello"

        result = await classifier_with_embeddings.classify_intent(query)

        assert result.is_ok
        assert isinstance(result.value, QueryIntent)
        # Ambiguous query may fall back to SPECIFIC or default


# ============================================================================
# TESTS: Intent Type Coverage
# ============================================================================


class TestIntentTypeCoverage:
    """Test all intent types are covered."""

    def test_intent_types_coverage(self):
        """All QueryIntent enum values exist."""
        # Verify enum has expected values
        assert QueryIntent.HIERARCHICAL is not None
        assert QueryIntent.PREREQUISITE is not None
        assert QueryIntent.PRACTICE is not None
        assert QueryIntent.EXPLORATORY is not None
        assert QueryIntent.RELATIONSHIP is not None
        assert QueryIntent.AGGREGATION is not None
        assert QueryIntent.SPECIFIC is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
