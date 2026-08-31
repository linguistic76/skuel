"""Guards on ACTIVATING the Askesis intent → chunk-type filter.

The filter (`_INTENT_CHUNK_TYPES` → `retrieve_scoped_chunks(chunk_types=)`) is
staged, not dead — and HOW it is held off changed with PR-2 of the activation
arc (2026-08-31). Before: the gate (0.65, an *average* cosine over 8 exemplars,
which a verbatim exemplar reached only 0.43-0.56 against) was unreachable, so
the map executed on every question and took its no-filter branch every time.
Since PR-2: the gate is live at 0.35 and intents DO classify, and the map is
held off EXPLICITLY — `retrieve_relevant_context` hard-wires `chunk_types=None`
at the call site, and `_intent_to_chunk_types` is registered in
PLANNED_METHODS. See `docs/roadmap/deferred-work.md` § "Per-Domain Chunking
Knobs + Chunk-Type-Aware Retrieval", Named work 4.

These pin what must hold BEFORE and AFTER the filter is ever activated
(guards 1-2), plus the AGGREGATION carve-out PR-2 introduced (guard 3). None
asserts the filter is inert — that is live-corpus state, and its home is
`./dev eval-askesis-draw`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import IntelligenceThreshold
from core.services.askesis.context_retriever import _intent_to_chunk_types
from core.services.askesis.intent_classifier import (
    UNREACHABLE_INTENTS,
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
        exemplars, which RAISES the mean — manufacturing confidence on the least
        trustworthy classification the service can produce (before PR-2 opened the
        gate, it was the ONLY path that could clear it). Before this guard it would
        have filtered the draw with no thin-draw fallback.
        """
        vector = [1.0] + [0.0] * 1023
        classifier = _classifier(AsyncMock(return_value=Result.ok(vector)))
        # One exemplar scoring 1.0 — the mean IS the max, comfortably over the gate.
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
    async def test_a_cached_degraded_load_costs_no_further_embedding_calls(self) -> None:
        """The verdict is decided before the call, so the call must not happen.

        A partial load is cached for the process's lifetime; scoring first would buy a
        query embedding — latency and provider spend — to reach a conclusion already
        known. Only the request that DID the loading can pay it.
        """
        vector = [1.0] + [0.0] * 1023
        embed = AsyncMock(return_value=Result.ok(vector))
        classifier = _classifier(embed)
        classifier._intent_exemplar_embeddings = {QueryIntent.PRACTICE: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=48, loaded=44, intents_expected=6, intents_loaded=6
        )

        result = await classifier.classify_intent("anything at all")

        assert result.is_ok and result.value is QueryIntent.SPECIFIC
        assert embed.await_count == 0, (
            "a cached degraded load must short-circuit BEFORE embedding the query"
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
# GUARD 2: the score is a MEAN — and the mean is the measured-best aggregation
# ============================================================================


class TestScoreIsAveragedNotMaximised:
    """The gate is an AVERAGE over an intent's exemplars, and switching that to a
    max must be a deliberate, measured decision rather than a passing edit.

    ⚠ This guard's REASON changed on 2026-08-31 and the new one is stronger, so
    do not dismiss it by refuting the old one. Originally: averaging is why a
    verbatim exemplar only reaches 0.43-0.56 against its own intent, so a max
    would invalidate the "threshold is unreachable" evidence. That reason
    EXPIRED when PR-2 moved the gate (2026-08-31).

    The reason that replaces it is a measurement, not an argument. On the
    ratified 45-query set, compared at each aggregation's EXACT
    zero-wrong-activation gate (`zero_wrong_frontier` in the report — computed
    at observed scores, because a 0.05 ladder rounds the frontier up and
    understates every arm), the mean ACTIVATES THE MOST QUERIES WITHOUT
    MIS-ROUTING ANY, and scores highest doing it: 21 of 45 at 0.3329 (78%),
    against max 17 at 0.5353 (69%) and top-3 15 at 0.4911 (64%). So the mean is
    not merely the incumbent: it is the best-behaved of the three on the metric
    that costs a user something.

    ⚠ Do not re-derive those figures FROM this docstring — re-measure with
    `./dev eval-intent-classification`. They are a snapshot of a corpus and an
    embedding model, both of which move, and this comment has already been stale
    once (#1206). Changing the aggregation needs a fresh measurement, and this
    failure is what asks for one.
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
            "score must be the MEAN across the exemplar set — a max would read 1.0 "
            "here. Measured on the ratified labelled set, the mean mis-routes least "
            "of the three aggregations; re-measure with "
            "./dev eval-intent-classification before changing it"
        )
        # 0.5 clears the live 0.35 gate, so the verdict is the winning intent —
        # before PR-2 this same mean sat below the 0.65 gate and the verdict was
        # SPECIFIC. Either way a max aggregation would have scored 1.0 above.
        assert result.value.confident is True
        assert result.value.intent is QueryIntent.PRACTICE

    def test_threshold_value_matches_the_evidence_quoted_in_the_docs(self) -> None:
        """The 0.35 gate is quoted WITH the measurement that chose it across the
        docs (the ratified baseline's zero-wrong frontier, cleared by ~0.03).
        Moving the constant without them orphans the evidence and leaves prose
        that reads as measured but is not.

        ⚠ The enumeration in the assertion message is a snapshot, not an
        authority: the 0.65-era list was four entries until a review (#1206)
        found three more that had drifted in unnoticed. Re-derive the list
        rather than trusting it — a checklist decays exactly like the
        references it lists.

        This is deliberately a change-detector: the point is to fail at the exact
        moment someone moves the gate, so they update the measurement's other
        half rather than discovering later that it silently stopped applying.
        """
        assert IntelligenceThreshold.INTENT_CLASSIFICATION == 0.35, (
            "changing this value orphans the measurement quoted in EIGHT places — "
            "core/constants.py (the comment above the constant), "
            "docs/roadmap/askesis-intent-classification-activation.md (§ PR-2: the "
            "proposal and the shipped measurement), "
            "docs/roadmap/deferred-work.md (Named work 4 + § AGGREGATION Carve-Out), "
            "docs/architecture/ASKESIS_HOW_IT_WORKS.md, "
            "docs/guides/ASKESIS_RAG_PIPELINE.md (three sites), "
            "docs/intelligence/ASKESIS_INTELLIGENCE.md, "
            "docs/roadmap/askesis-tool-selection-queries.md and docs/INDEX.md — "
            "update them in the same change. Re-derive the list with "
            "`git grep -nE '0\\.35|0\\.65' -- docs core` and READ the hits (both "
            "digits appear in unrelated constants) rather than trusting it"
        )


# ============================================================================
# GUARD 3: AGGREGATION is carved out — classified, never the production verdict
# ============================================================================


class TestAggregationHeldUnreachable:
    """PR-2 moved the gate to 0.35, and at that gate AGGREGATION is the
    best-separated intent in the ratified set (all 6 of its 6 labelled queries
    fire) — but nothing can answer it: `retrieve_relevant_context` has no
    AGGREGATION branch and the tool catalog does not exist. So
    `UNREACHABLE_INTENTS` holds it out of the PRODUCTION verdict
    (`classify_intent` answers SPECIFIC and logs the real verdict), while
    `classify_intent_scored` reports it raw for measurement. Ruled 2026-08-31;
    registered in deferred-work.md § AGGREGATION Carve-Out.

    ⚠ This guard — and the carve-out it pins — may only be deleted in the SAME
    change that adds the aggregation tool and its `retrieve_relevant_context`
    branch (the tool-selection first slice,
    docs/roadmap/askesis-tool-selection-queries.md). The dangerous edit is
    deleting the exclusion early, not adding the branch late: an empty set with
    no tool re-opens the window in which count questions classify, meet no
    branch, and are answered generically or invented.
    """

    @pytest.mark.asyncio
    async def test_aggregation_never_becomes_the_production_verdict(self) -> None:
        vector = [1.0] + [0.0] * 1023
        classifier = _classifier(AsyncMock(return_value=Result.ok(vector)))
        # AGGREGATION wins at cosine 1.0 — far above any gate, so only the
        # carve-out can be what keeps it out of the verdict.
        classifier._intent_exemplar_embeddings = {QueryIntent.AGGREGATION: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=1, loaded=1, intents_expected=1, intents_loaded=1
        )

        result = await classifier.classify_intent("how many tasks do I have")

        assert result.is_ok
        assert result.value is QueryIntent.SPECIFIC, (
            "AGGREGATION became a production verdict with nothing behind it — no "
            "retrieve_relevant_context branch and no tool can answer a count "
            "question. The carve-out may only be lifted in the same change that "
            "adds the aggregation tool (tool-selection first slice)"
        )

    @pytest.mark.asyncio
    async def test_scored_api_still_reports_the_raw_aggregation_verdict(self) -> None:
        """The eval's production-agreement check reads `classify_intent_scored`.

        Carving the verdict out THERE would make the eval's mean arm disagree
        with production on every aggregation-labelled row and void every run —
        the carve-out is a reachability decision, not a scoring one.
        """
        vector = [1.0] + [0.0] * 1023
        classifier = _classifier(AsyncMock(return_value=Result.ok(vector)))
        classifier._intent_exemplar_embeddings = {QueryIntent.AGGREGATION: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=1, loaded=1, intents_expected=1, intents_loaded=1
        )

        result = await classifier.classify_intent_scored("how many tasks do I have")

        assert result.is_ok
        assert result.value.intent is QueryIntent.AGGREGATION
        assert result.value.confident is True

    def test_the_carve_out_names_exactly_aggregation(self) -> None:
        """Membership pin, both directions: GROWING the set would silently
        disable an intent PR-2 activated, and EMPTYING it without a tool
        re-opens the window. Either move is a deliberate, reviewed decision.
        """
        assert frozenset({QueryIntent.AGGREGATION}) == UNREACHABLE_INTENTS, (
            "UNREACHABLE_INTENTS changed. Removing AGGREGATION is legal only in "
            "the same change that adds the aggregation tool "
            "(docs/roadmap/askesis-tool-selection-queries.md, first slice); adding "
            "an intent deactivates part of PR-2 and needs its own ruling"
        )
