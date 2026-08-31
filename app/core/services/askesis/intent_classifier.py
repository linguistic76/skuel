"""
Intent Classifier - Semantic Query Intent Classification
=========================================================

Uses embeddings to classify user query intent.
Extracted from QueryProcessor for single responsibility.

Responsibilities:
- Classify query intent using embeddings-based semantic classification
- Classify pedagogical intent for PS-scoped Socratic tutoring
- Manage lazy-loaded intent exemplar embeddings

Architecture:
- Requires EmbeddingsService for semantic classification (fail-fast if unavailable)
- Uses INTENT_EXEMPLARS for semantic similarity matching
- Returns QueryIntent enum values or PedagogicalIntent (for guided pipeline)

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
March 2026: Removed keyword fallback — embeddings required, no degraded mode.
March 2026: Added classify_pedagogical_intent() for PS-scoped Socratic pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import IntelligenceThreshold
from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.enums import GuidanceMode
from core.models.query_types import QueryIntent
from core.utils.exception_types import LLM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.vector_math import cosine_similarity

if TYPE_CHECKING:
    from core.models.askesis.ps_bundle import PsBundle
    from core.models.zpd.zpd_assessment import ZoneEvidence


@dataclass(frozen=True)
class GuidanceDetermination:
    """Result of determining the guidance mode for a Socratic turn.

    Combines the high-level GuidanceMode (4 modes) with the fine-grained
    PedagogicalIntent (7 intents) and the ZPD evidence that drove the decision.

    Consumed by: ResponseGenerator.build_guided_system_prompt()
    """

    mode: GuidanceMode
    pedagogical_detail: PedagogicalIntent
    target_ku_uids: list[str]
    zone_evidence: dict[str, Any]


logger = get_logger(__name__)


# ============================================================================
# INTENT EXEMPLARS - For Embedding-Based Intent Classification
# ============================================================================


@dataclass(frozen=True)
class ExemplarLoad:
    """How completely the intent exemplar set embedded on its one-time load.

    Cached with the embeddings it describes, because the load happens once and
    a partial result is kept for the process's lifetime.
    """

    expected: int
    loaded: int
    intents_expected: int
    intents_loaded: int

    def is_complete(self) -> bool:
        """True when every exemplar of every intent embedded successfully."""
        return self.loaded == self.expected and self.intents_loaded == self.intents_expected

    def describe(self) -> str:
        """One-line summary for an error message."""
        return (
            f"{self.loaded}/{self.expected} exemplars across "
            f"{self.intents_loaded}/{self.intents_expected} intents"
        )


@dataclass(frozen=True)
class IntentClassification:
    """A classification verdict WITH the confidence that produced it.

    ``confident`` is whether ``score`` cleared
    ``IntelligenceThreshold.INTENT_CLASSIFICATION``. When it is False the intent
    is SPECIFIC — the catch-all — and ``score`` is what the best-matching intent
    actually reached, which is the number that says whether the gate is
    reachable at all.
    """

    intent: QueryIntent
    score: float
    confident: bool


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


_INTENT_TO_GUIDANCE_MODE: dict[PedagogicalIntent, GuidanceMode] = {
    PedagogicalIntent.ASSESS_UNDERSTANDING: GuidanceMode.SOCRATIC,
    PedagogicalIntent.PROBE_DEEPER: GuidanceMode.SOCRATIC,
    PedagogicalIntent.SCAFFOLD: GuidanceMode.EXPLORATORY,
    PedagogicalIntent.SURFACE_CONNECTION: GuidanceMode.EXPLORATORY,
    PedagogicalIntent.REDIRECT_TO_CURRICULUM: GuidanceMode.DIRECT,
    PedagogicalIntent.OUT_OF_SCOPE: GuidanceMode.DIRECT,
    PedagogicalIntent.ENCOURAGE_PRACTICE: GuidanceMode.ENCOURAGING,
}


class IntentClassifier:
    """
    Classify user query intent using semantic similarity.

    This service handles intent classification:
    - Embedding-based semantic classification (primary)
    - Deterministic pedagogical intent classification (Socratic pipeline)
    - GuidanceMode determination from PedagogicalIntent
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

    def __init__(self, embeddings_service: Any) -> None:
        """
        Initialize intent classifier.

        Args:
            embeddings_service: EmbeddingsService for semantic search (required)
        """
        self.embeddings_service = embeddings_service

        # Lazy-loaded intent exemplar embeddings (one-time initialization)
        self._intent_exemplar_embeddings: dict[QueryIntent, list[list[float]]] | None = None
        self._exemplar_load: ExemplarLoad | None = None

        logger.info("IntentClassifier initialized")

    async def classify_intent(self, query: str) -> Result[QueryIntent]:
        """
        Classify query intent using embeddings-based semantic classification.

        Fail-soft: an embeddings outage answers SPECIFIC rather than raising, so an
        Askesis turn still completes. An INCOMPLETE exemplar load answers SPECIFIC too —
        see below; that is a correctness guard, not tolerance.

        Args:
            query: User's natural language question

        Returns:
            Result[QueryIntent] - Classified intent or error if classification fails
        """
        try:
            intent = await self._classify_via_embeddings(query)
        except Exception:  # safety-net: embeddings service raises varied exceptions
            logger.warning(
                "Embedding-based classification failed — defaulting to SPECIFIC",
                exc_info=True,
            )
            return Result.ok(QueryIntent.SPECIFIC)

        # A partial load is cached for the process's lifetime, and averaging over FEWER
        # exemplars RAISES the mean — an intent left holding one exemplar scores its max.
        # So a degraded load does not merely lose precision, it manufactures confidence,
        # and it is the only route by which a verdict clears the gate today. Every
        # consumer downstream (chunk-type filter, graph context, suggested actions,
        # citations) would then act on the least trustworthy classification the service
        # can produce. SPECIFIC is precisely the "we do not know" verdict; take it.
        load = self._exemplar_load
        if intent and load is not None and not load.is_complete():
            logger.warning(
                "Intent exemplar set incomplete (%s) — scores are averaged over unequal "
                "counts and are not comparable; answering SPECIFIC instead of %s",
                load.describe(),
                intent.value,
            )
            return Result.ok(QueryIntent.SPECIFIC)

        if intent:
            logger.debug("Intent classified via embeddings: %s", intent.value)
            return Result.ok(intent)

        # Low confidence — default to SPECIFIC (this is a classification result, not a fallback)
        logger.debug("Low confidence embedding match — defaulting to SPECIFIC")
        return Result.ok(QueryIntent.SPECIFIC)

    # ========================================================================
    # SOCRATIC PIPELINE — PEDAGOGICAL INTENT CLASSIFICATION
    # ========================================================================

    def classify_pedagogical_intent(
        self,
        question: str,
        ps_bundle: PsBundle,
        zone_evidence: dict[str, ZoneEvidence],
        target_ku_uids: list[str],
    ) -> PedagogicalIntent:
        """Classify the pedagogical move for a Socratic tutoring turn.

        This is a structured decision tree — no embeddings, no LLM. The logic
        is deterministic based on bundle membership and ZPD evidence:

        1. Is the question about content in the bundle? → OUT_OF_SCOPE if no
        2. Which KUs does it touch? (from target_ku_uids, scoped to bundle)
        3. Check ZoneEvidence for those KUs:
           - Confirmed (2+ signals) → ASSESS_UNDERSTANDING
           - 1 signal → PROBE_DEEPER or ENCOURAGE_PRACTICE
           - Proximal (0 signals, but in bundle) → SCAFFOLD
           - Not engaged → REDIRECT_TO_CURRICULUM
        4. If question touches edge-connected concepts → SURFACE_CONNECTION

        Args:
            question: User's question text
            ps_bundle: Complete PS bundle (scoped context)
            zone_evidence: Per-KU engagement evidence from ZPD
            target_ku_uids: KU UIDs extracted from question (scoped to bundle)

        Returns:
            PedagogicalIntent for the ResponseGenerator
        """
        # No matching KUs in bundle → OUT_OF_SCOPE
        if not target_ku_uids:
            # Check if the question matches any bundle entity titles at all
            if self._question_matches_bundle(question, ps_bundle):
                # Matches non-KU entities (habits, tasks, path steps)
                return PedagogicalIntent.ENCOURAGE_PRACTICE
            return PedagogicalIntent.OUT_OF_SCOPE

        # Check if question touches edge-connected concepts. Bundle edges are
        # real Ku↔Ku lateral edges; a bundle KU can sit at either end of an
        # authored connection, so match both endpoints.
        if len(target_ku_uids) >= 2 and ps_bundle.edges:
            edge_uids = {
                uid
                for e in ps_bundle.edges
                if isinstance(e, dict)
                for uid in (e.get("source_uid"), e.get("target_uid"))
                if uid
            }
            if any(uid in edge_uids for uid in target_ku_uids):
                return PedagogicalIntent.SURFACE_CONNECTION

        # Classify based on ZPD evidence for the target KUs
        # Use the "weakest" KU's evidence to determine the move
        # (tutor to the learner's actual level, not their strongest point)
        weakest_signal_count = float("inf")
        has_missing_practice = False

        for ku_uid in target_ku_uids:
            evidence = zone_evidence.get(ku_uid)
            if evidence is None:
                # No evidence at all — redirect to curriculum
                return PedagogicalIntent.REDIRECT_TO_CURRICULUM

            if evidence.signal_count < weakest_signal_count:
                weakest_signal_count = evidence.signal_count

            # Check for missing practice signals specifically
            if evidence.signal_count == 1 and not (
                evidence.habit_reinforcement or evidence.task_application
            ):
                has_missing_practice = True

        # Decision based on weakest signal
        if weakest_signal_count >= 2:
            return PedagogicalIntent.ASSESS_UNDERSTANDING
        if weakest_signal_count == 1:
            if has_missing_practice:
                return PedagogicalIntent.ENCOURAGE_PRACTICE
            return PedagogicalIntent.PROBE_DEEPER
        # signal_count == 0 but evidence exists (empty ZoneEvidence)
        return PedagogicalIntent.SCAFFOLD

    def _question_matches_bundle(self, question: str, ps_bundle: PsBundle) -> bool:
        """Check if question text matches any bundle entity title."""
        question_lower = question.lower()
        for title in ps_bundle.get_all_titles().values():
            if not title:
                continue
            title_lower = title.lower()
            if title_lower in question_lower:
                return True
            # Check significant words (>3 chars)
            for word in title_lower.split():
                if len(word) > 3 and word in question_lower:
                    return True
        return False

    # ========================================================================
    # GUIDANCE MODE DETERMINATION
    # ========================================================================

    def determine_guidance_mode(
        self,
        question: str,
        ps_bundle: PsBundle,
        zone_evidence: dict[str, Any],
        target_ku_uids: list[str],
    ) -> GuidanceDetermination:
        """Determine the guidance mode for a Socratic turn.

        Combines pedagogical intent classification with GuidanceMode mapping:
        - ASSESS_UNDERSTANDING / PROBE_DEEPER -> SOCRATIC
        - SCAFFOLD / SURFACE_CONNECTION -> EXPLORATORY
        - REDIRECT_TO_CURRICULUM / OUT_OF_SCOPE -> DIRECT
        - ENCOURAGE_PRACTICE -> ENCOURAGING

        Args:
            question: User's question text
            ps_bundle: Complete PS bundle (scoped context)
            zone_evidence: Per-KU engagement evidence from ZPD
            target_ku_uids: KU UIDs extracted from question

        Returns:
            GuidanceDetermination with mode, pedagogical detail, and evidence
        """
        intent = self.classify_pedagogical_intent(
            question, ps_bundle, zone_evidence, target_ku_uids
        )

        mode = _INTENT_TO_GUIDANCE_MODE[intent]

        return GuidanceDetermination(
            mode=mode,
            pedagogical_detail=intent,
            target_ku_uids=target_ku_uids,
            zone_evidence=zone_evidence,
        )

    # ========================================================================
    # PRIVATE — EMBEDDING-BASED INTENT CLASSIFICATION
    # ========================================================================

    async def _score_against_exemplars(self, query: str) -> Result[IntentClassification]:
        """Score the query against whatever exemplars are loaded.

        The shared engine under both public contracts. It deliberately does NOT
        judge the exemplar set's COMPLETENESS; both callers do, and both REJECT a
        partial load — they differ only in how loudly (``classify_intent`` answers
        SPECIFIC, ``classify_intent_scored`` fails). The check lives in them because
        the verdict differs, not because either one tolerates it.

        Returns a Result for EVERY failure, raised ones included: the embeddings
        service can throw as well as return ``Result.fail`` — which is why
        ``classify_intent`` carries a safety net — and a caller that asked for an
        observable verdict must get one, not an exception that takes down the
        whole run instead of the one classification.
        """
        try:
            await self._ensure_exemplars_loaded()

            if not self._intent_exemplar_embeddings:
                return Result.fail(
                    Errors.unavailable(
                        feature="intent_classification",
                        reason="no intent exemplar embeddings available",
                        operation="classify_intent_scored",
                    )
                )

            query_result = await self.embeddings_service.create_embedding(query)
        except LLM_EXCEPTIONS as e:
            return Result.fail(
                Errors.integration(
                    service="embeddings",
                    message=f"embedding failed during intent classification: {e}",
                    operation="classify_intent_scored",
                )
            )
        except Exception as e:  # safety-net: embeddings service raises varied exceptions
            return Result.fail(
                Errors.integration(
                    service="embeddings",
                    message=f"intent classification raised: {e}",
                    operation="classify_intent_scored",
                )
            )

        if query_result.is_error:
            return Result.fail(query_result)
        query_embedding = query_result.value

        best_intent: QueryIntent | None = None
        best_score = 0.0
        for intent, exemplar_embeddings in self._intent_exemplar_embeddings.items():
            similarities = [
                cosine_similarity(query_embedding, exemplar_emb)
                for exemplar_emb in exemplar_embeddings
            ]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

            if avg_similarity > best_score:
                best_score = avg_similarity
                best_intent = intent

        confident = (
            best_score >= IntelligenceThreshold.INTENT_CLASSIFICATION and best_intent is not None
        )
        return Result.ok(
            IntentClassification(
                # Below the gate the verdict IS SPECIFIC — a classification
                # result, not a fallback (see classify_intent).
                intent=best_intent if confident and best_intent else QueryIntent.SPECIFIC,
                score=best_score,
                confident=confident,
            )
        )

    async def classify_intent_scored(self, query: str) -> Result[IntentClassification]:
        """Classify intent AND report the confidence behind the verdict.

                The observable counterpart to ``classify_intent``. That method is
                fail-soft by design — it converts an embedding outage into
                ``Result.ok(SPECIFIC)`` so an Askesis turn still answers — which makes a
                provider failure indistinguishable from a genuine low-confidence
                classification at the call site. Anything that must tell those apart
                (measurement, diagnostics, an eval that would otherwise score an outage
                as a finding) calls this instead and gets a real ``Result.fail``.

        Both methods refuse an INCOMPLETE exemplar set; this one differs only in
                saying so out loud. A load that lost exemplars to a transient error is cached
                for the process's lifetime, and its per-intent averages are then taken over
                unequal denominators — scores no longer comparable across intents, an intent
                that lost all eight can never win, and, worst, a SMALLER denominator RAISES
                the mean, so a degraded set looks confident rather than uncertain.
                ``classify_intent`` answers SPECIFIC there; a caller asking for the SCORE is
                asking whether the score can be trusted, so it gets a real ``Result.fail``
                rather than a verdict it cannot tell apart from a genuine one.

                The score is the best AVERAGE cosine similarity across an intent's
                exemplar set, and ``confident`` says whether it cleared
                ``IntelligenceThreshold.INTENT_CLASSIFICATION``. A verdict of SPECIFIC
                with a score far below the gate means the gate is out of reach, not that
                the query was unusual — the two readings call for opposite fixes.
        """
        scored = await self._score_against_exemplars(query)
        if scored.is_error:
            return scored
        load = self._exemplar_load
        if load is not None and not load.is_complete():
            return Result.fail(
                Errors.unavailable(
                    feature="intent_classification",
                    reason=(
                        f"exemplar set incomplete ({load.describe()}) — scores are "
                        "averaged over unequal exemplar counts and are not comparable"
                    ),
                    operation="classify_intent_scored",
                )
            )
        return scored

    async def _classify_via_embeddings(self, query: str) -> QueryIntent | None:
        """Classify intent using semantic similarity to exemplars.

        Returns the QueryIntent whose exemplar set the query best matches, or
        None when nothing clears ``IntelligenceThreshold.INTENT_CLASSIFICATION``
        or the classification could not be performed at all. The caller
        (``classify_intent``) turns both of those into SPECIFIC; a caller that
        must distinguish them wants ``classify_intent_scored``.

        Scores against whatever exemplars loaded, INCLUDING a partial set. That is
        deliberate HERE and safe only because both callers reject the result of a
        partial load: ``classify_intent_scored`` returns an error, and
        ``classify_intent`` answers SPECIFIC. Do not "simplify" by treating a verdict
        off this method as trustworthy on its own — averaging over fewer exemplars
        raises the mean, so a degraded set scores HIGHER, not lower.
        """
        scored = await self._score_against_exemplars(query)
        if scored.is_error:
            logger.warning(
                "Intent classification unavailable — cannot classify: %s", scored.expect_error()
            )
            return None
        if not scored.value.confident:
            return None
        logger.debug(
            "Embedding classification: %s (score: %.2f)",
            scored.value.intent.value,
            scored.value.score,
        )
        return scored.value.intent

    async def _ensure_exemplars_loaded(self) -> None:
        """
        Lazy-load intent exemplar embeddings on first use.

        Generates embeddings for all INTENT_EXEMPLARS and caches them for efficient
        intent classification. Individual exemplar failures are logged and skipped
        rather than raising — but the resulting set is NOT merely less precise, and
        neither caller will classify from it: ``classify_intent`` answers SPECIFIC and
        ``classify_intent_scored`` fails. The completeness of the load is recorded on
        ``self._exemplar_load`` for exactly that purpose.
        """
        if self._intent_exemplar_embeddings is not None:
            return  # Already loaded

        logger.info("Loading intent exemplar embeddings (one-time initialization)...")

        exemplar_embeddings: dict[QueryIntent, list[list[float]]] = {}
        failed_count = 0

        for intent, exemplar_queries in INTENT_EXEMPLARS.items():
            embeddings_for_intent = []

            for exemplar_query in exemplar_queries:
                embedding_result = await self.embeddings_service.create_embedding(exemplar_query)
                if embedding_result.is_ok:
                    embeddings_for_intent.append(embedding_result.value)
                else:
                    failed_count += 1
                    logger.warning(
                        "Failed to embed exemplar '%s' (%s): %s",
                        exemplar_query,
                        intent.value,
                        embedding_result.error,
                    )

            if embeddings_for_intent:
                exemplar_embeddings[intent] = embeddings_for_intent
                logger.debug(
                    "Loaded %d/%d exemplars for %s",
                    len(embeddings_for_intent),
                    len(exemplar_queries),
                    intent.value,
                )
            else:
                logger.warning("No exemplars loaded for intent %s — will not match", intent.value)

        self._intent_exemplar_embeddings = exemplar_embeddings
        # Keep the completeness of THIS load. A partially-loaded set is cached
        # permanently, and its per-intent averages are then taken over
        # different denominators — scores stop being comparable ACROSS intents,
        # which biases which intent wins, and an intent that lost every
        # exemplar can never win at all. Worse, a SMALLER denominator RAISES the
        # mean — one surviving exemplar scores its max — so a degraded set does not
        # look uncertain, it looks confident. Neither caller accepts that:
        # `classify_intent` answers SPECIFIC, `classify_intent_scored` fails.
        self._exemplar_load = ExemplarLoad(
            expected=sum(len(queries) for queries in INTENT_EXEMPLARS.values()),
            loaded=sum(len(embs) for embs in exemplar_embeddings.values()),
            intents_expected=len(INTENT_EXEMPLARS),
            intents_loaded=len(exemplar_embeddings),
        )

        if failed_count:
            logger.warning(
                "Intent exemplar embeddings loaded with %d failures (%d intents)",
                failed_count,
                len(exemplar_embeddings),
            )
        else:
            logger.info("Intent exemplar embeddings loaded (%d intents)", len(exemplar_embeddings))
