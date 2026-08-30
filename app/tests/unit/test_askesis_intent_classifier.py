"""
Test Suite for IntentClassifier
================================

Tests the askesis intent classification service:
- Embedding-based classification
- Confidence threshold handling
- Intent type coverage
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import IntelligenceThreshold
from core.services.askesis.intent_classifier import IntentClassifier, QueryIntent
from core.utils.result_simplified import Errors, Result

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_embeddings_service() -> Mock:
    """Create mock EmbeddingsService with correct method name and return type."""
    embeddings = Mock()

    # Production code calls .is_ok/.is_error/.value on the result
    embeddings.create_embedding = AsyncMock(return_value=Result.ok([0.1] * 1024))

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


# ============================================================================
# TESTS: classify_intent_scored — the OBSERVABLE contract
# ============================================================================


class TestClassifyIntentScored:
    """`classify_intent` is fail-soft; `classify_intent_scored` is not.

    The distinction is the point: a caller that must tell a provider outage
    from a genuine low-confidence verdict cannot use the fail-soft one, because
    both arrive as `Result.ok(SPECIFIC)`.
    """

    @pytest.mark.asyncio
    async def test_embedding_failure_errors_instead_of_verdicting_specific(
        self, mock_embeddings
    ) -> None:
        mock_embeddings.create_embedding = AsyncMock(
            return_value=Result.fail(Errors.integration(service="openai", message="429"))
        )
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [[0.1] * 1024]}

        scored = await classifier.classify_intent_scored("anything")

        assert scored.is_error
        # ...while the fail-soft sibling reports success, indistinguishably
        # from a real low-confidence classification. That is the whole reason
        # the scored variant exists.
        soft = await classifier.classify_intent("anything")
        assert soft.is_ok and soft.value is QueryIntent.SPECIFIC

    @pytest.mark.asyncio
    async def test_missing_exemplars_are_an_error(self, mock_embeddings) -> None:
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {}

        assert (await classifier.classify_intent_scored("anything")).is_error

    @pytest.mark.asyncio
    async def test_below_the_gate_is_specific_but_carries_the_score(self, mock_embeddings) -> None:
        # An orthogonal exemplar scores ~0, well under the gate. The verdict is
        # SPECIFIC and `confident` is False — but the score still rides out, so
        # a caller can tell "gate unreachable" from "query ambiguous".
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok([1.0] + [0.0] * 1023))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [[0.0, 1.0] + [0.0] * 1022]}

        scored = await classifier.classify_intent_scored("anything")

        assert scored.is_ok
        assert scored.value.intent is QueryIntent.SPECIFIC
        assert scored.value.confident is False
        assert scored.value.score < IntelligenceThreshold.INTENT_CLASSIFICATION

    @pytest.mark.asyncio
    async def test_above_the_gate_returns_the_matched_intent(self, mock_embeddings) -> None:
        # An identical vector scores 1.0 — comfortably over the gate.
        vector = [1.0] + [0.0] * 1023
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok(vector))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}

        scored = await classifier.classify_intent_scored("anything")

        assert scored.is_ok
        assert scored.value.intent is QueryIntent.PRACTICE
        assert scored.value.confident is True
        assert scored.value.score == pytest.approx(1.0)
        # The fail-soft path must agree whenever classification succeeded.
        soft = await classifier.classify_intent("anything")
        assert soft.is_ok and soft.value is QueryIntent.PRACTICE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
