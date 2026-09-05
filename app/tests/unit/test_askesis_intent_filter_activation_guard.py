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
(guards 1-2), plus the invariant that REPLACED the AGGREGATION carve-out when
the tool-selection first slice lifted it (guard 3: served or declined, never
invented — and never another user's data). None asserts the filter is inert —
that is live-corpus state, and its home is `./dev eval-askesis-draw`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import IntelligenceThreshold
from core.ports.llm_protocols import ToolSelection
from core.services.askesis.context_retriever import _intent_to_chunk_types
from core.services.askesis.intent_classifier import (
    ExemplarLoad,
    IntentClassifier,
    QueryIntent,
)
from core.services.askesis.query_tools import (
    AggregationAnswered,
    AggregationCount,
    AggregationDeclined,
    CountGoalsAchievedArgs,
    QueryTool,
    run_tool,
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
            "docs/roadmap/per-domain-chunking-knobs.md (Named work 4), "
            "docs/architecture/ASKESIS_HOW_IT_WORKS.md, "
            "docs/guides/ASKESIS_RAG_PIPELINE.md (three sites), "
            "docs/intelligence/ASKESIS_INTELLIGENCE.md, "
            "docs/roadmap/askesis-tool-selection-queries.md and docs/INDEX.md — "
            "update them in the same change. Re-derive the list with "
            "`git grep -nE '0\\.35|0\\.65' -- docs core` and READ the hits (both "
            "digits appear in unrelated constants) rather than trusting it"
        )


# ============================================================================
# GUARD 3: AGGREGATION is served or declined — never invented, never cross-tenant
# ============================================================================


def _one_tool_catalog(handler) -> dict[str, QueryTool]:
    return {
        "count_goals_achieved": QueryTool(
            name="count_goals_achieved",
            description="test tool",
            args_model=CountGoalsAchievedArgs,
            handler=handler,
        )
    }


class TestAggregationServedOrDeclined:
    """The invariant that REPLACED the carve-out (lifted 2026-08-31, the same
    change that added the aggregation tool — the one condition the old guard's
    docstring named for its own deletion).

    PR-2 held AGGREGATION out of the production verdict because nothing could
    answer it. The tool-selection first slice put a tool, a decline path, and a
    deterministic delivery behind the intent, so the carve-out is gone and the
    invariant is now: an AGGREGATION verdict is ANSWERED by an executed tool or
    DECLINED/UNAVAILABLE with a learner-visible reason — never generated,
    never invented, and never another user's data. The delivery half
    (generation short-circuited on every outcome) is pinned in
    tests/unit/test_askesis_aggregation_delivery.py; the executor half is
    pinned here because it is the safety-critical piece: server-side
    ``user_uid`` injection is the whole reason this pattern is safe where
    text2cypher is not.
    """

    @pytest.mark.asyncio
    async def test_aggregation_is_a_production_verdict_now(self) -> None:
        """The lift is complete — both classifier APIs agree on AGGREGATION.

        A half-lift (scored says aggregation, production still says SPECIFIC)
        would silently disconnect the tool this guard exists to protect.
        """
        vector = [1.0] + [0.0] * 1023
        classifier = _classifier(AsyncMock(return_value=Result.ok(vector)))
        classifier._intent_exemplar_embeddings = {QueryIntent.AGGREGATION: [vector]}
        classifier._exemplar_load = ExemplarLoad(
            expected=1, loaded=1, intents_expected=1, intents_loaded=1
        )

        production = await classifier.classify_intent("how many tasks do I have")
        scored = await classifier.classify_intent_scored("how many tasks do I have")

        assert production.is_ok and scored.is_ok
        assert production.value is QueryIntent.AGGREGATION, (
            "AGGREGATION classified but did not become the production verdict — "
            "the carve-out was lifted 2026-08-31 with the tool behind it; a "
            "re-introduced suppression strands the aggregation branch"
        )
        assert scored.value.intent is production.value, (
            "classify_intent and classify_intent_scored disagree — the eval's "
            "production-agreement check reads the scored API, so a divergence "
            "voids every eval run"
        )

    @pytest.mark.asyncio
    async def test_llm_supplied_user_uid_is_ignored_by_the_executor(self) -> None:
        """THE cross-tenant guard: identity is injected server-side, always.

        A model-smuggled ``user_uid`` argument is discarded; the handler runs
        for the AUTHENTICATED user and the answer is the caller's own data —
        never the named user's.
        """
        seen: dict[str, str] = {}

        async def handler(*, user_uid: str, period) -> Result[AggregationCount]:
            seen["user_uid"] = user_uid
            return Result.ok(
                AggregationCount(
                    subject="goals achieved", total=2, since="2026-04-01", until="2026-06-30"
                )
            )

        selection = ToolSelection(
            tool_name="count_goals_achieved",
            arguments={"period": "last_quarter", "user_uid": "user_someone_else"},
        )

        result = await run_tool(selection, _one_tool_catalog(handler), user_uid="user_caller")

        assert result.is_ok
        assert isinstance(result.value, AggregationAnswered)
        assert seen["user_uid"] == "user_caller", (
            "the executor let a model-supplied user_uid reach the handler — "
            "server-side injection is the safety property that separates "
            "tool-selection from text2cypher"
        )

    @pytest.mark.asyncio
    async def test_out_of_coverage_selection_declines(self) -> None:
        """No tool / unknown tool → an explicit Declined, never a fall-through.

        The decline is a NORMAL outcome carrying a learner-visible reason —
        modelling it as an error would let the response generator answer the
        unsupported question anyway (the design doc's OPEN PROBLEM 2).
        """

        async def handler(*, user_uid: str, period) -> Result[AggregationCount]:
            raise AssertionError("no handler may run for an out-of-coverage selection")

        catalog = _one_tool_catalog(handler)

        for selection in (
            ToolSelection(tool_name=None, arguments={}),
            ToolSelection(tool_name="count_unicorns", arguments={"period": "last_quarter"}),
        ):
            result = await run_tool(selection, catalog, user_uid="user_caller")
            assert result.is_ok, "a coverage gap is a decline, not a failure"
            outcome = result.value
            assert isinstance(outcome, AggregationDeclined)
            assert outcome.reason, "the decline must carry a stated reason"
