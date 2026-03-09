"""
ZPDService — Zone of Proximal Development
==========================================

Computes a user's Zone of Proximal Development by delegating graph traversal
to ZPDBackend. Answers: *what does this user know, and what are they
structurally ready to learn next?*

This service is the pedagogical core of Askesis. Without it, Askesis can only
react to what the user says. With it, Askesis knows where the user is in the
curriculum before the conversation starts.

Architecture
------------
- Delegates all Neo4j queries to ZPDBackend (adapters/persistence/neo4j/).
- Owns business logic: readiness scoring, behavioral enrichment.
- Optional behavioral intelligence injection: ChoicesIntelligenceService and
  HabitsIntelligenceService enrich the assessment with behavioral readiness.
- Returns ZPDAssessment with empty lists (not a failure) when the curriculum
  graph has fewer than 3 KUs or no user engagement exists.

Integration
-----------
  ZPDService (behavioral signals)
          ↓
  UserContextIntelligence.get_optimal_next_learning_steps()
          ↓
  AskesisService (scaffold_entry, ku_bridge prompts)

See: core/models/zpd/zpd_assessment.py — ZPDAssessment model
See: core/ports/zpd_protocols.py — ZPDOperations + ZPDBackendOperations protocols
See: adapters/persistence/neo4j/zpd_backend.py — persistence layer
See: docs/roadmap/zpd-service-deferred.md — full design rationale
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.models.zpd.zpd_assessment import ZPDAssessment
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from logging import Logger

    from core.ports.zpd_protocols import ZPDBackendOperations
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
    from core.services.habits.habits_intelligence_service import HabitsIntelligenceService


class ZPDService:
    """
    Zone of Proximal Development service.

    Stateless business logic — delegates graph traversal to ZPDBackend,
    then enriches results with readiness scoring and behavioral signals.

    Args:
        backend: ZPDBackend instance for Neo4j queries.
        choices_intelligence: Optional — enriches behavioral_readiness with
            choice history signals. When None, behavioral_readiness defaults
            to 0.5 (neutral).
        habits_intelligence: Optional — enriches current_zone with KUs
            reinforced by active habits. When None, habit reinforcement is
            excluded from the current zone.
        logger: Standard Python logger. Defaults to skuel.services.zpd.
    """

    def __init__(
        self,
        backend: ZPDBackendOperations,
        choices_intelligence: ChoicesIntelligenceService | None = None,
        habits_intelligence: HabitsIntelligenceService | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._backend = backend
        self._choices_intelligence = choices_intelligence
        self._habits_intelligence = habits_intelligence
        self._logger = logger or logging.getLogger("skuel.services.zpd")

    # =========================================================================
    # PUBLIC API (ZPDOperations protocol)
    # =========================================================================

    async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]:
        """Compute the user's full ZPD from the curriculum graph.

        Returns an empty ZPDAssessment (not an error) when the curriculum
        graph has fewer than 3 KUs.

        Args:
            user_uid: User's unique identifier (e.g. "user_alice")

        Returns:
            Result[ZPDAssessment]: Full ZPD snapshot.
        """
        # Guard: curriculum graph must be populated enough to be meaningful
        ku_count = await self._backend.get_ku_count()
        if ku_count < 3:
            self._logger.debug(
                "ZPD skipped: curriculum graph has %d KUs (minimum 3 required)", ku_count
            )
            return Result.ok(self._empty_assessment())

        # Graph traversal: current zone + proximal zone + readiness data
        graph_result = await self._backend.get_zone_data(user_uid)
        if graph_result.is_error:
            return Result.fail(graph_result.expect_error())

        current_zone, proximal_zone, engaged_paths, prereq_data, blocking_gaps = graph_result.value

        # Business logic: compute readiness scores from raw prereq data
        readiness_scores = self._compute_readiness_scores(prereq_data)

        # Behavioral readiness: enrich with choices + habits signals
        behavioral_readiness = await self._compute_behavioral_readiness(user_uid, current_zone)

        return Result.ok(
            ZPDAssessment(
                current_zone=current_zone,
                proximal_zone=proximal_zone,
                engaged_paths=engaged_paths,
                readiness_scores=readiness_scores,
                blocking_gaps=blocking_gaps,
                behavioral_readiness=behavioral_readiness,
            )
        )

    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]:
        """Get only the proximal zone KU UIDs, ranked by readiness score.

        Lightweight convenience wrapper over assess_zone() for callers that
        need only the candidate KU list.
        """
        assessment_result = await self.assess_zone(user_uid)
        if assessment_result.is_error:
            return Result.fail(assessment_result.expect_error())
        assessment = assessment_result.value
        return Result.ok(assessment.top_proximal_ku_uids())

    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]:
        """Get the readiness score for a specific KU (0.0-1.0).

        Returns 0.0 for KUs not in the proximal zone.
        """
        assessment_result = await self.assess_zone(user_uid)
        if assessment_result.is_error:
            return Result.fail(assessment_result.expect_error())
        score = assessment_result.value.readiness_scores.get(ku_uid, 0.0)
        return Result.ok(score)

    # =========================================================================
    # PRIVATE HELPERS — Business Logic
    # =========================================================================

    def _compute_readiness_scores(self, prereq_data: list[dict[str, Any]]) -> dict[str, float]:
        """Compute readiness score for each proximal KU.

        Score = fraction of the KU's prerequisites that are in current_zone.
        A KU with no prerequisites scores 1.0 (fully ready).
        """
        scores: dict[str, float] = {}
        for entry in prereq_data:
            ku_uid = entry.get("ku_uid")
            if not ku_uid:
                continue
            total = entry.get("total") or 0
            met = entry.get("met") or 0
            scores[ku_uid] = 1.0 if total == 0 else round(met / total, 3)
        return scores

    async def _compute_behavioral_readiness(self, user_uid: str, current_zone: list[str]) -> float:
        """Aggregate behavioral readiness from choices + habits signals.

        Weights:
        - principle_adherence_score:    25%
        - decision_consistency_score:   25%
        - high_quality_decision_rate:   15%
        - active_conflict_count:        -5% per conflict (capped at -25%)
        - habit_reinforcement_strength: 10% (mean strength across reinforced KUs
                                            that overlap with current_zone)
        - at_risk_ku_penalty:           -5% per at-risk KU in current_zone
                                            (capped at -20%)

        Returns 0.5 (neutral) when both intelligence services are unavailable.
        """
        behavioral_score = 0.5  # Neutral default

        choices_weight = 0.0
        habits_weight = 0.0

        # ── Choices signals ───────────────────────────────────────────────
        if self._choices_intelligence is not None:
            signals_result = await self._choices_intelligence.get_zpd_behavioral_signals(user_uid)
            if not signals_result.is_error:
                signals = signals_result.value
                adherence = signals.get("principle_adherence_score", 0.5)
                consistency = signals.get("decision_consistency_score", 0.5)
                quality_rate = signals.get("high_quality_decision_rate", 0.5)
                conflicts = signals.get("active_conflict_count", 0)

                conflict_penalty = min(0.25, conflicts * 0.05)
                choices_score = (
                    (adherence * 0.35)
                    + (consistency * 0.35)
                    + (quality_rate * 0.20)
                    - conflict_penalty
                )
                choices_score = max(0.0, min(1.0, choices_score))
                choices_weight = choices_score

        # ── Habits signals ────────────────────────────────────────────────
        if self._habits_intelligence is not None:
            knowledge_result = await self._habits_intelligence.get_zpd_knowledge_signals(user_uid)
            if not knowledge_result.is_error:
                knowledge = knowledge_result.value
                reinforced_uids: list[str] = knowledge.get("reinforced_ku_uids", [])
                strengths: dict[str, float] = knowledge.get("reinforcement_strength", {})
                at_risk: list[str] = knowledge.get("at_risk_ku_uids", [])

                # Mean reinforcement strength for KUs overlapping current_zone
                relevant_uids = [uid for uid in reinforced_uids if uid in current_zone]
                if relevant_uids:
                    mean_strength = sum(strengths.get(uid, 0.0) for uid in relevant_uids) / len(
                        relevant_uids
                    )
                else:
                    mean_strength = 0.0

                at_risk_in_zone = sum(1 for uid in at_risk if uid in current_zone)
                at_risk_penalty = min(0.20, at_risk_in_zone * 0.05)

                habits_score = max(0.0, min(1.0, mean_strength - at_risk_penalty))
                habits_weight = habits_score

        # ── Combine ───────────────────────────────────────────────────────
        if self._choices_intelligence is not None and self._habits_intelligence is not None:
            behavioral_score = (choices_weight * 0.65) + (habits_weight * 0.35)
        elif self._choices_intelligence is not None:
            behavioral_score = choices_weight
        elif self._habits_intelligence is not None:
            behavioral_score = habits_weight

        return round(behavioral_score, 3)

    def _empty_assessment(self) -> ZPDAssessment:
        """Return an empty ZPDAssessment for insufficient curriculum graph."""
        return ZPDAssessment(
            current_zone=[],
            proximal_zone=[],
            engaged_paths=[],
            readiness_scores={},
            blocking_gaps=[],
            behavioral_readiness=0.5,
        )
