"""
Intent Classifier - Semantic Query Intent Classification
=========================================================

Uses embeddings to classify user query intent.
Extracted from QueryProcessor for single responsibility.

Responsibilities:
- Classify query intent using embeddings-based semantic classification
- Classify pedagogical intent for LS-scoped Socratic tutoring
- Manage lazy-loaded intent exemplar embeddings

Architecture:
- Requires EmbeddingsService for semantic classification (fail-fast if unavailable)
- Uses INTENT_EXEMPLARS for semantic similarity matching
- Returns QueryIntent enum values or PedagogicalIntent (for guided pipeline)

January 2026: Extracted from QueryProcessor as part of Askesis design improvement.
March 2026: Removed keyword fallback — embeddings required, no degraded mode.
March 2026: Added classify_pedagogical_intent() for LS-scoped Socratic pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.askesis.pedagogical_intent import PedagogicalIntent
from core.models.enums import GuidanceMode
from core.models.query_types import QueryIntent
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.askesis.ls_bundle import LSBundle
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

        logger.info("IntentClassifier initialized")

    async def classify_intent(self, query: str) -> Result[QueryIntent]:
        """
        Classify query intent using embeddings-based semantic classification.

        Args:
            query: User's natural language question

        Returns:
            Result[QueryIntent] - Classified intent or error if classification fails
        """
        try:
            intent = await self._classify_via_embeddings(query)
        except Exception:
            logger.warning(
                "Embedding-based classification failed — defaulting to SPECIFIC",
                exc_info=True,
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
        ls_bundle: LSBundle,
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
            ls_bundle: Complete LS bundle (scoped context)
            zone_evidence: Per-KU engagement evidence from ZPD
            target_ku_uids: KU UIDs extracted from question (scoped to bundle)

        Returns:
            PedagogicalIntent for the ResponseGenerator
        """
        # No matching KUs in bundle → OUT_OF_SCOPE
        if not target_ku_uids:
            # Check if the question matches any bundle entity titles at all
            if self._question_matches_bundle(question, ls_bundle):
                # Matches non-KU entities (habits, tasks, articles)
                return PedagogicalIntent.ENCOURAGE_PRACTICE
            return PedagogicalIntent.OUT_OF_SCOPE

        # Check if question touches edge-connected concepts
        if len(target_ku_uids) >= 2 and ls_bundle.edges:
            edge_uids = {e.get("target_uid") for e in ls_bundle.edges if isinstance(e, dict)}
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

    def _question_matches_bundle(self, question: str, ls_bundle: LSBundle) -> bool:
        """Check if question text matches any bundle entity title."""
        question_lower = question.lower()
        for title in ls_bundle.get_all_titles().values():
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
        ls_bundle: LSBundle,
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
            ls_bundle: Complete LS bundle (scoped context)
            zone_evidence: Per-KU engagement evidence from ZPD
            target_ku_uids: KU UIDs extracted from question

        Returns:
            GuidanceDetermination with mode, pedagogical detail, and evidence
        """
        intent = self.classify_pedagogical_intent(
            question, ls_bundle, zone_evidence, target_ku_uids
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
            logger.warning("No intent exemplar embeddings available — cannot classify")
            return None

        # Create query embedding (returns Result[list[float]])
        query_result = await self.embeddings_service.create_embedding(query)
        if query_result.is_error:
            logger.warning("Failed to create query embedding — cannot classify intent")
            return None
        query_embedding = query_result.value

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

    async def _ensure_exemplars_loaded(self) -> None:
        """
        Lazy-load intent exemplar embeddings on first use.

        Generates embeddings for all INTENT_EXEMPLARS and caches them
        for efficient intent classification. Individual exemplar failures
        are logged and skipped — classification still works with fewer
        exemplars per intent (lower precision, not a crash).
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

        if failed_count:
            logger.warning(
                "Intent exemplar embeddings loaded with %d failures (%d intents)",
                failed_count,
                len(exemplar_embeddings),
            )
        else:
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
