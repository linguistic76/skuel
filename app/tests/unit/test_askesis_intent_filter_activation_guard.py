"""Guards on ACTIVATING the Askesis intent → chunk-type filter.

The filter (`_INTENT_CHUNK_TYPES` → `retrieve_scoped_chunks(chunk_types=)`) is
staged, not dead: it executes on every Askesis question and takes its no-filter
branch every time, because the classifier can only return `SPECIFIC` today
(`IntelligenceThreshold.INTENT_CLASSIFICATION` = 0.65 is an *average* cosine
over 8 exemplars, and a verbatim exemplar scores 0.43-0.56 against its own
intent). Measured + ruled 2026-08-30 — see `docs/roadmap/deferred-work.md`
§ "Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval", Named work 4.

No dead-code detector can find this: the map IS referenced and IS executed. So
the two claims that would otherwise decay into stale prose are pinned here.

Neither test asserts that the filter is inert — that is live-corpus state, and
its home is `./dev eval-askesis-draw`. These pin the two things that must hold
BEFORE and AFTER the filter is activated.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import IntelligenceThreshold
from core.services.askesis.context_retriever import _intent_to_chunk_types
from core.services.askesis.intent_classifier import (
    ExemplarLoad,
    IntentClassifier,
    QueryIntent,
)
from core.utils.result_simplified import Result


def _classifier(create_embedding: AsyncMock) -> IntentClassifier:
    embeddings = Mock()
    embeddings.create_embedding = create_embedding
    return IntentClassifier(embeddings_service=embeddings)


# ============================================================================
# GUARD 1: the catch-all verdict must never carry a chunk-type filter
# ============================================================================


class TestCatchAllVerdictCarriesNoFilter:
    """`classify_intent` returns SPECIFIC for BOTH a low-confidence verdict and
    an embeddings outage. Mapping SPECIFIC in `_INTENT_CHUNK_TYPES` would
    therefore make a provider failure silently narrow retrieval — the outage
    would answer from a filtered slice of the corpus and look like a normal
    answer. That stays true after the classifier is fixed: SPECIFIC remains the
    outage fallback, so this guard is permanent, not a snapshot of today's
    inertness.

    Written against BEHAVIOUR rather than `SPECIFIC not in _INTENT_CHUNK_TYPES`
    so it survives a rename and keeps pointing at the property that matters.
    """

    @pytest.mark.asyncio
    async def test_embeddings_outage_does_not_narrow_retrieval(self) -> None:
        raising = AsyncMock(side_effect=RuntimeError("embeddings provider down"))

        result = await _classifier(raising).classify_intent("anything at all")

        assert result.is_ok, "classify_intent is fail-soft by contract"
        assert _intent_to_chunk_types(result.value) is None, (
            "an embeddings outage classifies as SPECIFIC; if SPECIFIC ever gains "
            "a _INTENT_CHUNK_TYPES entry, every outage silently answers from a "
            "type-filtered slice of the corpus"
        )

    @pytest.mark.asyncio
    async def test_a_degraded_exemplar_load_does_not_narrow_retrieval(self) -> None:
        """The third route to the catch-all, and the one that nearly shipped.

        A partial load is cached for the process's lifetime and averages over fewer
        exemplars, which RAISES the mean — so it is the one path that can clear the gate
        today, on the least trustworthy classification the service can produce. Before
        this guard it would have filtered the draw with no thin-draw fallback.
        """
        vector = [1.0] + [0.0] * 1023
        classifier = _classifier(AsyncMock(return_value=Result.ok(vector)))
        # One exemplar scoring 1.0 — the mean IS the max, comfortably over 0.65.
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=48, loaded=44, intents_expected=6, intents_loaded=6
        )

        result = await classifier.classify_intent("anything at all")

        assert result.is_ok
        assert _intent_to_chunk_types(result.value) is None, (
            "a degraded exemplar load must not narrow the chunk draw — PRACTICE would "
            "restrict it to 137 of 925 chunks on a manufactured confidence score"
        )

    @pytest.mark.asyncio
    async def test_low_confidence_verdict_does_not_narrow_retrieval(self) -> None:
        # A real embedding that matches no exemplar well — the ordinary route to
        # SPECIFIC, and the one every production query takes today.
        succeeding = AsyncMock(return_value=Result.ok([0.0] * 1024))

        result = await _classifier(succeeding).classify_intent("anything at all")

        assert result.is_ok
        assert result.value is QueryIntent.SPECIFIC
        assert _intent_to_chunk_types(result.value) is None, (
            "SPECIFIC is the catch-all: any chunk type may answer it"
        )


# ============================================================================
# GUARD 2: the premise under "fixing this is not lowering the threshold"
# ============================================================================


class TestScoreIsAveragedNotMaximised:
    """The gate is an AVERAGE over an intent's exemplars, and that mechanism —
    not the value 0.65 — is why a query that IS an exemplar verbatim still only
    reaches 0.43-0.56 against its own intent.

    An argument cannot be tested, so this pins the premise the argument rests
    on. Switch the aggregation to max and this fails, forcing whoever does it to
    read why: 0.65 against a max is a completely different gate, and the
    measured evidence for "the threshold is unreachable" would no longer apply.
    """

    @pytest.mark.asyncio
    async def test_score_is_the_mean_across_exemplars_not_the_best_match(self) -> None:
        query_vector = [1.0, 0.0, 0.0, 0.0]
        identical = [1.0, 0.0, 0.0, 0.0]  # cosine 1.0 against the query
        orthogonal = [0.0, 1.0, 0.0, 0.0]  # cosine 0.0 against the query

        classifier = _classifier(AsyncMock(return_value=Result.ok(query_vector)))
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [identical, orthogonal]}
        classifier._exemplar_load = ExemplarLoad(
            expected=2, loaded=2, intents_expected=1, intents_loaded=1
        )

        result = await classifier.classify_intent_scored("a query")

        assert result.is_ok, result.expect_error() if result.is_error else ""
        assert result.value.score == pytest.approx(0.5), (
            "score must be the MEAN across the exemplar set; a max would read "
            "1.0 here and the 'threshold is unreachable' measurement would not hold"
        )
        assert result.value.confident is False
        assert result.value.intent is QueryIntent.SPECIFIC

    def test_threshold_value_matches_the_evidence_quoted_in_the_docs(self) -> None:
        """The measured 0.078-0.291 / 0.43-0.56 scores are quoted AGAINST 0.65 in
        four places. Moving the constant without them orphans the evidence and
        leaves prose that reads as measured but is not.

        This is deliberately a change-detector: the point is to fail at the exact
        moment someone lowers the gate, so they update the measurement's other
        half rather than discovering later that it silently stopped applying.
        """
        assert IntelligenceThreshold.INTENT_CLASSIFICATION == 0.65, (
            "changing this value orphans the measurement quoted in "
            "core/constants.py, docs/roadmap/deferred-work.md (Named work 4), "
            "docs/architecture/ASKESIS_HOW_IT_WORKS.md and "
            "docs/guides/ASKESIS_RAG_PIPELINE.md — update them in the same change"
        )
