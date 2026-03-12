"""
ZPDService — Zone of Proximal Development (Pedagogical Gravity Well)
=====================================================================

The capstone computation on UserContext — synthesizes curriculum graph
traversal, behavioral signals, life path alignment, and compound evidence
into "what's most important, what advances your life path most."

Without ZPD, intelligence services can only react to isolated domain signals.
With ZPD, the system knows where the user is in the curriculum, what they're
ready for, and how it connects to their life direction.

Architecture
------------
- Delegates all Neo4j queries to ZPDBackend (adapters/persistence/neo4j/).
- Owns business logic: readiness scoring, behavioral enrichment, compound
  evidence tracking, recommended action generation.
- Optional behavioral intelligence injection: ChoicesIntelligenceService and
  HabitsIntelligenceService enrich the assessment with behavioral readiness.
- Accepts optional UserContext for life path integration and evidence enrichment.
- Returns ZPDAssessment with empty lists (not a failure) when the curriculum
  graph has fewer than 3 KUs or no user engagement exists.

Integration
-----------
  UserContextBuilder.build_rich()  ← capstone step
          ↓
  ZPDService.assess_zone(user_uid, context)
          ↓
  ZPDAssessment on UserContext.zpd_assessment
          ↓
  DailyPlanningMixin P5  |  LearningIntelligenceMixin  |  AskesisService

See: core/models/zpd/zpd_assessment.py — ZPDAssessment, ZoneEvidence, ZPDAction
See: core/ports/zpd_protocols.py — ZPDOperations + ZPDBackendOperations protocols
See: adapters/persistence/neo4j/zpd_backend.py — persistence layer
See: docs/roadmap/zpd-service-deferred.md — full design rationale
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.models.zpd.zpd_assessment import ZoneEvidence, ZPDAction, ZPDAssessment
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from logging import Logger

    from core.ports.zpd_protocols import ZPDBackendOperations
    from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
    from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
    from core.services.user.unified_user_context import UserContext


class ZPDService:
    """
    Zone of Proximal Development service — the pedagogical gravity well.

    Stateless business logic — delegates graph traversal to ZPDBackend,
    then enriches results with readiness scoring, behavioral signals,
    compound evidence, life path alignment, and recommended actions.

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

    async def assess_zone(
        self, user_uid: str, context: UserContext | None = None
    ) -> Result[ZPDAssessment]:
        """Compute the user's full ZPD from the curriculum graph.

        When context is provided, enriches the assessment with life path
        alignment, compound zone evidence, and recommended actions.

        Returns an empty ZPDAssessment (not an error) when the curriculum
        graph has fewer than 3 KUs.

        Args:
            user_uid: User's unique identifier (e.g. "user_alice")
            context: Optional UserContext for life path + evidence enrichment.

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

        (
            current_zone,
            proximal_zone,
            engaged_paths,
            prereq_data,
            blocking_gaps,
            task_engaged,
            journal_engaged,
            habit_engaged,
            submission_data,
        ) = graph_result.value

        # Business logic: compute readiness scores from raw prereq data
        readiness_scores = self._compute_readiness_scores(prereq_data)

        # Behavioral readiness: enrich with choices + habits signals
        behavioral_readiness = await self._compute_behavioral_readiness(user_uid, current_zone)

        # Build compound zone evidence from per-source engagement data
        zone_evidence = self._build_zone_evidence(
            current_zone, task_engaged, journal_engaged, habit_engaged, submission_data
        )

        # Parse submission scores
        submission_scores = self._parse_submission_scores(submission_data)

        # Life path integration (when context available)
        life_path_alignment = 0.0
        life_path_uid: str | None = None
        if context is not None:
            life_path_alignment = getattr(context, "life_path_alignment_score", 0.0) or 0.0
            life_path_uid = getattr(context, "life_path_uid", None)

        # Build recommended actions from proximal zone + current zone evidence
        recommended_actions = self._build_recommended_actions(
            proximal_zone,
            readiness_scores,
            behavioral_readiness,
            life_path_alignment,
            zone_evidence=zone_evidence,
            blocking_gaps=blocking_gaps,
        )

        return Result.ok(
            ZPDAssessment(
                current_zone=current_zone,
                proximal_zone=proximal_zone,
                engaged_paths=engaged_paths,
                readiness_scores=readiness_scores,
                blocking_gaps=blocking_gaps,
                behavioral_readiness=behavioral_readiness,
                life_path_alignment=life_path_alignment,
                life_path_uid=life_path_uid,
                recommended_actions=tuple(recommended_actions),
                zone_evidence=zone_evidence,
                submission_scores=submission_scores,
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

    async def assess_ku_readiness(
        self, user_uid: str, ku_uids: list[str]
    ) -> Result[dict[str, ZoneEvidence]]:
        """Get targeted ZPD evidence for specific KUs.

        Lightweight alternative to assess_zone() — queries engagement data
        for just the specified KUs without traversing the full curriculum graph.
        Used by the Socratic pipeline for query-time ZPD assessment.

        Args:
            user_uid: User's unique identifier
            ku_uids: KU UIDs to assess

        Returns:
            Result[dict[str, ZoneEvidence]]: Per-KU engagement evidence.
                KUs with no engagement get a default ZoneEvidence (all zeros).
        """
        if not ku_uids:
            return Result.ok({})

        engagement_result = await self._backend.get_targeted_ku_engagement(user_uid, ku_uids)
        if engagement_result.is_error:
            return Result.fail(engagement_result.expect_error())

        task_engaged, journal_engaged, habit_engaged, submission_data = engagement_result.value

        # Build ZoneEvidence for each requested KU
        sub_lookup: dict[str, dict[str, Any]] = {}
        for entry in submission_data:
            ku_uid = entry.get("ku_uid")
            if ku_uid:
                sub_lookup[ku_uid] = entry

        task_set = set(task_engaged)
        journal_set = set(journal_engaged)
        habit_set = set(habit_engaged)

        evidence: dict[str, ZoneEvidence] = {}
        for ku_uid in ku_uids:
            sub_entry = sub_lookup.get(ku_uid, {})
            evidence[ku_uid] = ZoneEvidence(
                ku_uid=ku_uid,
                submission_count=sub_entry.get("count", 0),
                best_submission_score=sub_entry.get("best_score", 0.0),
                habit_reinforcement=ku_uid in habit_set,
                task_application=ku_uid in task_set,
                journal_application=ku_uid in journal_set,
            )

        return Result.ok(evidence)

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

    def _build_zone_evidence(
        self,
        current_zone: list[str],
        task_engaged: list[str],
        journal_engaged: list[str],
        habit_engaged: list[str],
        submission_data: list[dict[str, Any]],
    ) -> dict[str, ZoneEvidence]:
        """Build compound evidence for each KU in the current zone.

        Combines per-source engagement data with submission scores.
        A KU needs 2+ signal types to be considered "confirmed".
        """
        # Build submission lookup
        sub_lookup: dict[str, dict[str, Any]] = {}
        for entry in submission_data:
            ku_uid = entry.get("ku_uid")
            if ku_uid:
                sub_lookup[ku_uid] = entry

        task_set = set(task_engaged)
        journal_set = set(journal_engaged)
        habit_set = set(habit_engaged)

        evidence: dict[str, ZoneEvidence] = {}
        for ku_uid in current_zone:
            sub_entry = sub_lookup.get(ku_uid, {})
            evidence[ku_uid] = ZoneEvidence(
                ku_uid=ku_uid,
                submission_count=sub_entry.get("count", 0),
                best_submission_score=sub_entry.get("best_score", 0.0),
                habit_reinforcement=ku_uid in habit_set,
                task_application=ku_uid in task_set,
                journal_application=ku_uid in journal_set,
            )
        return evidence

    def _parse_submission_scores(self, submission_data: list[dict[str, Any]]) -> dict[str, float]:
        """Extract best submission score per KU from raw submission data."""
        scores: dict[str, float] = {}
        for entry in submission_data:
            ku_uid = entry.get("ku_uid")
            if ku_uid:
                scores[ku_uid] = entry.get("best_score", 0.0)
        return scores

    def _build_recommended_actions(
        self,
        proximal_zone: list[str],
        readiness_scores: dict[str, float],
        behavioral_readiness: float,
        life_path_alignment: float,
        zone_evidence: dict[str, ZoneEvidence] | None = None,
        blocking_gaps: list[str] | None = None,
    ) -> list[ZPDAction]:
        """Build recommended actions from proximal zone and current zone signals.

        Three action types, reflecting the learning loop:
        - **learn**: Proximal KUs the user is ready for (advances the zone)
        - **reinforce**: Current-zone KUs with weak evidence (compounds mastery)
        - **unblock**: Blocking-gap KUs that gate multiple proximal KUs (high leverage)

        Priority formula (learn):
            readiness_score * 0.5 + life_path_alignment * 0.3 + behavioral_readiness * 0.2

        Priority formula (reinforce):
            (1 - signal_strength) * 0.4 + life_path_alignment * 0.3 + behavioral_readiness * 0.3

        Priority formula (unblock):
            0.9 (blocking gaps are always high priority — they unlock territory)
        """
        actions: list[ZPDAction] = []

        # ── Unblock actions — blocking gaps unlock the most territory ──────
        for gap_uid in blocking_gaps or []:
            actions.append(
                ZPDAction(
                    entity_uid=gap_uid,
                    entity_type="article",
                    action_type="unblock",
                    priority=0.9,
                    rationale="blocking gap — unlocks further progress",
                    ku_uid=gap_uid,
                )
            )

        # ── Learn actions — proximal KUs the user is ready for ─────────────
        for ku_uid in proximal_zone:
            readiness = readiness_scores.get(ku_uid, 0.0)
            priority = round(
                readiness * 0.5 + life_path_alignment * 0.3 + behavioral_readiness * 0.2,
                3,
            )

            rationale_parts = []
            if readiness >= 1.0:
                rationale_parts.append("all prerequisites met")
            elif readiness > 0.0:
                rationale_parts.append(f"{readiness:.0%} prerequisites met")
            if life_path_alignment > 0.5:
                rationale_parts.append("aligns with life path")

            actions.append(
                ZPDAction(
                    entity_uid=ku_uid,
                    entity_type="article",
                    action_type="learn",
                    priority=priority,
                    rationale="; ".join(rationale_parts) if rationale_parts else "ready to learn",
                    ku_uid=ku_uid,
                )
            )

        # ── Reinforce actions — current-zone KUs with thin evidence ────────
        if zone_evidence:
            for ku_uid, evidence in zone_evidence.items():
                if evidence.is_confirmed:
                    continue  # Already compound-confirmed — no reinforcement needed
                signal_strength = evidence.signal_count / 4.0  # 4 possible signal types
                priority = round(
                    (1.0 - signal_strength) * 0.4
                    + life_path_alignment * 0.3
                    + behavioral_readiness * 0.3,
                    3,
                )
                actions.append(
                    ZPDAction(
                        entity_uid=ku_uid,
                        entity_type="article",
                        action_type="reinforce",
                        priority=priority,
                        rationale=f"{evidence.signal_count}/4 evidence types — needs compound mastery",
                        ku_uid=ku_uid,
                    )
                )

        return actions

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
