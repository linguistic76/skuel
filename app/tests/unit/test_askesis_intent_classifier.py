"""
Test Suite for IntentClassifier
================================

Tests the askesis intent classification service:
- Embedding-based classification
- Confidence threshold handling
- Intent type coverage
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import EmbeddingFanOut, IntelligenceThreshold
from core.services.askesis.intent_classifier import (
    INTENT_EXEMPLARS,
    ExemplarLoad,
    IntentClassifier,
    QueryIntent,
)
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

    def test_every_intent_carries_the_same_number_of_exemplars(self):
        """Unequal exemplar counts make the per-intent scores incomparable.

        The score is a MEAN over an intent's exemplars, so a set with six
        exemplars is scored on a different denominator than one with eight — and
        a SMALLER denominator RAISES the mean, so the thinner set wins ties it
        should lose. Production already refuses a partial LOAD for this reason
        (`ExemplarLoad`); this pins the same property in the authored set, where
        an editor adding a seventh line to one intent would otherwise tilt
        classification silently.
        """
        counts = {intent: len(exemplars) for intent, exemplars in INTENT_EXEMPLARS.items()}

        assert len(set(counts.values())) == 1, (
            f"exemplar counts differ across intents: {counts} — per-intent means "
            "are then averaged over different denominators and stop being comparable"
        )

    def test_no_exemplar_is_shared_between_two_intents(self):
        """A duplicated exemplar scores identically for both owners.

        It cannot discriminate, and it drags both means toward each other — the
        collision the AGGREGATION/EXPLORATORY rewrite exists to remove.
        """
        seen: dict[str, QueryIntent] = {}
        for intent, exemplars in INTENT_EXEMPLARS.items():
            for exemplar in exemplars:
                assert exemplar not in seen, (
                    f"{exemplar!r} belongs to both {seen.get(exemplar)} and {intent}"
                )
                seen[exemplar] = intent


# ============================================================================
# TESTS: the one-time exemplar load
# ============================================================================


class TestExemplarLoad:
    """The lazy exemplar load runs inside the first question's pipeline timeout."""

    @pytest.mark.asyncio
    async def test_exemplars_embed_concurrently_up_to_the_fan_out_ceiling(
        self, mock_embeddings
    ) -> None:
        """Peak in-flight equals `EmbeddingFanOut.MAX_IN_FLIGHT` — no less, no more.

        The load is lazy and sits inside `AskesisPipelineTimeout` for the first
        question of a process, so N serial round-trips would be N times the
        provider's latency charged to that learner: a serial loop measures a peak
        of 1 and fails here. The ceiling is the other half — an unbounded gather
        measures the whole set and fails here too, because a burst past a
        provider's concurrency limit refuses exemplars, and a refused exemplar is
        an incomplete load cached for the process lifetime.
        """
        total = sum(len(exemplars) for exemplars in INTENT_EXEMPLARS.values())
        ceiling = EmbeddingFanOut.MAX_IN_FLIGHT
        assert ceiling < total, "the fixture set must exceed the ceiling for the bound to show"
        in_flight = 0
        peak = 0
        calls = 0
        release = asyncio.Event()

        async def embed(_text: str) -> Result[list[float]]:
            nonlocal in_flight, peak, calls
            calls += 1
            in_flight += 1
            peak = max(peak, in_flight)
            await release.wait()  # park here until the test has counted the wave
            in_flight -= 1
            return Result.ok([0.1] * 1024)

        mock_embeddings.create_embedding = AsyncMock(side_effect=embed)
        classifier = IntentClassifier(embeddings_service=mock_embeddings)

        load = asyncio.create_task(classifier._ensure_exemplars_loaded())
        for _ in range(10):  # let every scheduled call reach its first await
            await asyncio.sleep(0)
        # Sampled while the whole wave is parked: a serial loop shows 1, an
        # unbounded gather shows the whole set — only the ceiling shows `ceiling`.
        assert in_flight == ceiling, f"in flight {in_flight}, ceiling {ceiling}, set {total}"
        release.set()
        await asyncio.wait_for(load, timeout=2)

        assert peak == ceiling, f"peak in-flight {peak}, ceiling {ceiling}, set {total}"
        assert calls == total
        assert classifier._exemplar_load is not None
        assert classifier._exemplar_load.is_complete()

    @pytest.mark.asyncio
    async def test_one_refused_exemplar_does_not_discard_the_rest(self, mock_embeddings) -> None:
        """Failure tolerance is per exemplar, and the incompleteness is recorded.

        The load gathers individual `create_embedding` calls rather than the
        batch API precisely so a single refused text costs one exemplar, not the
        set — and `ExemplarLoad` still records the load as incomplete, which is
        what makes both callers refuse to classify from it.
        """
        refused = INTENT_EXEMPLARS[QueryIntent.PRACTICE][0]

        async def embed(text: str) -> Result[list[float]]:
            if text == refused:
                return Result.fail(Errors.integration(service="embeddings", message="refused"))
            return Result.ok([0.1] * 1024)

        mock_embeddings.create_embedding = AsyncMock(side_effect=embed)
        classifier = IntentClassifier(embeddings_service=mock_embeddings)

        await classifier._ensure_exemplars_loaded()

        load = classifier._exemplar_load
        assert load is not None
        assert load.expected == sum(len(e) for e in INTENT_EXEMPLARS.values())
        assert load.loaded == load.expected - 1
        assert not load.is_complete()
        assert classifier._intent_exemplar_embeddings is not None
        practice = classifier._intent_exemplar_embeddings[QueryIntent.PRACTICE]
        assert len(practice) == len(INTENT_EXEMPLARS[QueryIntent.PRACTICE]) - 1
        assert load.intents_loaded == len(INTENT_EXEMPLARS)


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
    async def test_a_raised_embedding_failure_is_also_an_error_result(
        self, mock_embeddings
    ) -> None:
        # The embeddings service throws as well as returning Result.fail —
        # which is why classify_intent carries a safety net. A caller that
        # asked for an observable verdict must get one, not an exception that
        # takes down the whole run instead of the single classification.
        mock_embeddings.create_embedding = AsyncMock(side_effect=RuntimeError("socket closed"))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [[0.1] * 1024]}

        scored = await classifier.classify_intent_scored("anything")

        assert scored.is_error
        assert "socket closed" in str(scored.expect_error())

    @pytest.mark.asyncio
    async def test_a_raised_failure_during_exemplar_load_is_an_error_result(
        self, mock_embeddings
    ) -> None:
        # The load itself embeds 48 exemplars, so it is the other throw site.
        mock_embeddings.create_embedding = AsyncMock(side_effect=RuntimeError("429"))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)

        assert (await classifier.classify_intent_scored("anything")).is_error

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
    async def test_a_partial_exemplar_load_is_refused(self, mock_embeddings) -> None:
        # A transient 429 partway through the 48 exemplar embeddings leaves a
        # subset cached for the process's lifetime. Averages then run over
        # unequal denominators, so scores stop being comparable across intents
        # — confident-looking numbers with no error, which is precisely what
        # this API exists to prevent.
        vector = [1.0] + [0.0] * 1023
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok(vector))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=48, loaded=44, intents_expected=6, intents_loaded=6
        )

        scored = await classifier.classify_intent_scored("anything")

        assert scored.is_error
        assert "44/48" in str(scored.expect_error())

    @pytest.mark.asyncio
    async def test_a_missing_intent_is_refused(self, mock_embeddings) -> None:
        # An intent that lost every exemplar can never win — a silent
        # narrowing of the classification space.
        vector = [1.0] + [0.0] * 1023
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok(vector))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=48, loaded=48, intents_expected=6, intents_loaded=5
        )

        assert (await classifier.classify_intent_scored("anything")).is_error

    @pytest.mark.asyncio
    async def test_a_partial_load_answers_specific_rather_than_a_confident_verdict(
        self, mock_embeddings
    ) -> None:
        """A partial load does not lose precision — it MANUFACTURES confidence.

        Averaging over fewer exemplars raises the mean (an intent left holding one
        exemplar scores its max), and the set is cached for the process's lifetime. This
        test previously asserted the opposite and was the evidence that the chunk-type
        filter could fire on a degraded classification (Codex, #1201).
        """
        vector = [1.0] + [0.0] * 1023
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok(vector))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=48, loaded=44, intents_expected=6, intents_loaded=6
        )

        soft = await classifier.classify_intent("anything")

        assert soft.is_ok
        assert soft.value is QueryIntent.SPECIFIC, (
            "a 1.0-scoring one-exemplar set must not out-rank a complete one"
        )

    @pytest.mark.asyncio
    async def test_above_the_gate_returns_the_matched_intent(self, mock_embeddings) -> None:
        # An identical vector scores 1.0 — comfortably over the gate.
        vector = [1.0] + [0.0] * 1023
        mock_embeddings.create_embedding = AsyncMock(return_value=Result.ok(vector))
        classifier = IntentClassifier(embeddings_service=mock_embeddings)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=1, loaded=1, intents_expected=1, intents_loaded=1
        )

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
