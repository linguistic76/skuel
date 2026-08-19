"""
Principles Alignment Service - Alignment Assessment
====================================================

Handles alignment assessment between principles and goals/habits.
Provides motivational intelligence and decision support.

Responsibilities:
- Assess goal/habit alignment with principles
- Generate motivational profiles
- Support principle-based decision making
- Calculate integrity scores

Part of the PrinciplesService decomposition.
"""

from dataclasses import asdict, dataclass
from datetime import date
from operator import itemgetter
from typing import Any

from core.constants import QueryLimit
from core.events import publish_event
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import AlignmentLevel, PrincipleStrength
from core.models.principle.principle import Principle, get_principle_priority
from core.models.principle.principle_types import (
    AlignmentAssessment as UserAlignmentAssessment,
)
from core.models.principle.principle_types import (
    PrincipleAlignment,
    PrincipleConflict,
    PrincipleDecision,
)
from core.models.type_hints import EntityUID, UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.services.cross_domain import CrossDomainQueryService
from core.services.cross_domain.cross_domain_types import PrincipleAlignmentEvidence
from core.services.intelligence import principle_gap_insights, principle_gap_recommendations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


@dataclass
class MotivationalProfile:
    """A user's complete motivational profile based on principles"""

    user_uid: UserUID
    core_principles: list[Principle]
    developing_principles: list[Principle]
    goal_alignment_score: float
    habit_alignment_score: float
    primary_motivators: list[str]
    value_conflicts: list[PrincipleConflict]
    growth_opportunities: list[str]
    aligned_goal_suggestions: list[dict]
    aligned_habit_suggestions: list[dict]


@dataclass
class AlignmentAssessment:
    """Complete assessment of principle alignment for an entity"""

    entity_uid: EntityUID
    entity_type: str
    entity_name: str
    principle_alignments: list[PrincipleAlignment]
    overall_alignment: float
    primary_principle: Principle | None
    strengths: list[str]
    gaps: list[str]
    recommendations: list[str]


def _resolution_strategy(principle: Principle) -> str:
    """The principle's own first authored resolution strategy.

    ``Principle.resolution_strategies`` is the authored tuple for exactly this
    question. It replaces a ``principle.resolve_conflict(other, context)`` call
    that no Principle has ever carried — the model has data here, not behaviour.
    """
    return principle.resolution_strategies[0] if principle.resolution_strategies else ""


def _to_principle_conflict(principle: Principle, other_ref: str) -> PrincipleConflict:
    """Narrow one authored ``conflicting_principles`` entry into a PrincipleConflict.

    ``conflicting_principles`` holds references to the principles this one pulls
    against; ``resolution_strategies`` holds how the author resolves them. Both
    are authored fields, so this is a narrowing rather than an inference.
    ``priority_in_conflict`` is 1 — from this principle's own point of view,
    which is whose tuple the reference was authored in.
    """
    return PrincipleConflict(
        conflicting_principle_uid=other_ref,
        conflict_description=f"{principle.title} conflicts with {other_ref}",
        resolution_strategy=_resolution_strategy(principle),
        priority_in_conflict=1,
    )


class PrinciplesAlignmentService:
    """
    Alignment assessment and motivational intelligence.

    Responsibilities:
    - Assess goal/habit alignment with principles
    - Generate motivational profiles
    - Support principle-based decision making
    - Calculate integrity scores
    """

    def __init__(
        self,
        backend: PrinciplesOperations,
        cross_domain_query: CrossDomainQueryService,
        event_bus=None,
    ) -> None:
        """
        Initialize principles alignment service.

        Args:
            backend: Backend for principle operations.
            cross_domain_query: CrossDomainQueryService for graph-derived
                cross-domain reads (REQUIRED — fail-fast).
            event_bus: Event bus for publishing domain events (optional).
        """
        self.backend = backend
        self.cross_domain_query = cross_domain_query
        self.event_bus = event_bus
        self.alignment_cache: dict[str, AlignmentAssessment] = {}
        self.logger = get_logger(__name__)

    # ========================================================================
    # ALIGNMENT ASSESSMENT
    # ========================================================================

    @with_error_handling("assess_goal_alignment", error_type="system", uid_param="goal_uid")
    async def assess_goal_alignment(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[AlignmentAssessment]:
        """
        Assess how a goal aligns with user's principles.

        Uses graph-based alignment evidence (explicit relationships like
        GUIDES_GOAL, GUIDED_BY_PRINCIPLE, EMBODIES_PRINCIPLE) rather than
        keyword heuristics.

        Args:
            goal_uid: Goal to assess.
            user_uid: User whose principles to check.

        Returns:
            Complete alignment assessment.
        """
        return await self._assess_entity_alignment_via_graph(
            entity_uid=EntityUID(goal_uid),
            entity_type=EntityType.GOAL,
            user_uid=user_uid,
        )

    @with_error_handling("assess_habit_alignment", error_type="database")
    async def assess_habit_alignment(
        self, habit_uid: str, user_uid: UserUID
    ) -> Result[AlignmentAssessment]:
        """
        Assess how a habit aligns with user's principles.

        Uses graph-based alignment evidence (explicit relationships like
        INSPIRES_HABIT, EMBODIES_PRINCIPLE) rather than keyword heuristics.

        Args:
            habit_uid: Habit to assess.
            user_uid: User whose principles to check.

        Returns:
            Complete alignment assessment.
        """
        return await self._assess_entity_alignment_via_graph(
            entity_uid=EntityUID(habit_uid),
            entity_type=EntityType.HABIT,
            user_uid=user_uid,
        )

    async def get_embodiment_rates_7d(
        self, principle_uids: list[EntityUID], user_uid: UserUID
    ) -> Result[dict[str, float]]:
        """Rolling 7-day embodiment rate per principle (0..1).

        Thin pass-through to ``CrossDomainQueryService.get_embodiment_rates_7d``
        — owned by alignment because EMBODIES_PRINCIPLE is an alignment edge.
        See the cross-domain method for the rate formula.
        """
        return await self.cross_domain_query.get_embodiment_rates_7d(principle_uids, user_uid)

    # ========================================================================
    # GRAPH-BASED ALIGNMENT (shared implementation)
    # ========================================================================

    async def _assess_entity_alignment_via_graph(
        self, entity_uid: EntityUID, entity_type: EntityType, user_uid: UserUID
    ) -> Result[AlignmentAssessment]:
        """
        Assess how an entity (goal or habit) aligns with user's principles
        using graph-based alignment evidence.

        For each principle, checks whether ``entity_uid`` appears in the
        principle's connected goals/habits via explicit relationships
        (GUIDES_GOAL, GUIDED_BY_PRINCIPLE, INSPIRES_HABIT, EMBODIES_PRINCIPLE).

        Args:
            entity_uid: Entity to assess.
            entity_type: EntityType.GOAL or EntityType.HABIT.
            user_uid: User whose principles to check.
        """
        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result)

        principles = principles_result.value

        # For each principle, get graph evidence and check if entity is connected
        alignments: list[PrincipleAlignment] = []
        total_score = 0.0
        entity_name = ""

        for principle in principles:
            evidence_result = await self.cross_domain_query.get_principle_alignment_evidence(
                principle.uid, user_uid
            )
            if evidence_result.is_error:
                continue

            evidence = evidence_result.value
            connected, name = self._find_entity_in_evidence(entity_uid, entity_type, evidence)

            if connected:
                level = evidence.alignment_level
                score = evidence.score
                if name:
                    entity_name = name
            else:
                level = AlignmentLevel.UNKNOWN
                score = 0.0

            priority_numeric = get_principle_priority(principle)
            weighted_score = score * (priority_numeric / 10.0)
            total_score += weighted_score

            alignment = PrincipleAlignment(
                principle_uid=principle.uid,
                entity_uid=entity_uid,
                entity_type=entity_type,
                alignment_level=level,
                alignment_score=score,
                influence_description=(
                    f"{principle.title} connected via graph relationships"
                    if connected
                    else f"{principle.title} has no graph connection"
                ),
                influence_weight=priority_numeric / 10.0,
            )
            alignments.append(alignment)

            # Publish event
            from core.events import PrincipleAlignmentAssessed

            event = PrincipleAlignmentAssessed(
                principle_uid=principle.uid,
                entity_uid=entity_uid,
                entity_type=entity_type,
                user_uid=user_uid,
                alignment_score=score,
            )
            await publish_event(self.event_bus, event, self.logger)

        # Calculate overall alignment
        overall = total_score / len(principles) if principles else 0.0
        primary = max(principles, key=get_principle_priority) if principles else None

        assessment = AlignmentAssessment(
            entity_uid=entity_uid,
            entity_type=entity_type,
            entity_name=entity_name,
            principle_alignments=alignments,
            overall_alignment=overall,
            primary_principle=primary,
            strengths=self._identify_alignment_strengths(alignments),
            gaps=self._identify_alignment_gaps(alignments),
            recommendations=self._generate_alignment_recommendations(alignments, principles),
        )

        self.alignment_cache[f"{entity_type}_{entity_uid}"] = assessment
        return Result.ok(assessment)

    @staticmethod
    def _find_entity_in_evidence(
        entity_uid: EntityUID,
        entity_type: EntityType,
        evidence: PrincipleAlignmentEvidence,
    ) -> tuple[bool, str]:
        """Check if an entity appears in a principle's alignment evidence.

        Returns:
            (is_connected, entity_title) — title is non-empty when found.
        """
        entities = (
            evidence.aligned_goals if entity_type == EntityType.GOAL else evidence.aligned_habits
        )
        for entity in entities:
            if entity.uid == entity_uid:
                return True, entity.title
        return False, ""

    # ========================================================================
    # HYBRID DUAL-TRACK ALIGNMENT (January 2026)
    # ========================================================================

    @with_error_handling("assess_with_user_input", error_type="database")
    async def assess_with_user_input(
        self,
        principle_uid: str,
        user_uid: UserUID,
        user_alignment_level: AlignmentLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        min_confidence: float = 0.7,
    ) -> Result[dict[str, Any]]:
        """
        Hybrid assessment: store user input AND calculate system alignment.

        This implements SKUEL's dual-track philosophy:
        - VISION: User's self-assessment (what they believe)
        - ACTION: System calculation (what they do)
        - INSIGHT: Gap analysis (perception vs reality)

        Similar to LifePath's WordActionAlignment pattern.

        Args:
            principle_uid: Principle to assess
            user_uid: User making the assessment
            user_alignment_level: User's self-reported alignment level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their alignment
            min_confidence: Minimum confidence threshold for system calculation

        Returns:
            Result with PrincipleAlignmentAssessmentResult as dict
        """

        from core.models.principle.principle_request import PrincipleAlignmentAssessmentResult

        # 1. Get the principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result)

        principle = principle_result.value
        if principle is None:
            return Result.fail(Errors.not_found(resource="Principle", identifier=principle_uid))

        # 2. Create user's assessment
        user_assessment = UserAlignmentAssessment(
            assessed_date=date.today(),
            alignment_level=user_alignment_level,
            evidence=user_evidence,
            reflection=user_reflection,
        )

        # 3. Store user assessment in alignment_history
        await self._store_user_assessment(principle_uid, user_assessment)

        # 4. Calculate system alignment from goals/habits/choices
        system_result = await self._calculate_system_alignment(principle, user_uid)
        system_alignment = system_result["alignment_level"]
        system_score = system_result["score"]
        system_evidence = system_result["evidence"]

        # 5. Calculate perception gap
        gap, direction = self._calculate_perception_gap(user_alignment_level, system_alignment)

        # 6. Generate insights based on gap
        insights = principle_gap_insights(direction, gap, principle.title)

        # 7. Generate recommendations
        recommendations = principle_gap_recommendations(direction, gap, principle, system_evidence)

        # 8. Build result
        result = PrincipleAlignmentAssessmentResult(
            principle_uid=principle_uid,
            user_assessment=user_assessment,
            system_alignment=system_alignment,
            system_score=system_score,
            system_evidence=tuple(system_evidence),
            perception_gap=gap,
            gap_direction=direction,
            insights=tuple(insights),
            recommendations=tuple(recommendations),
        )

        # Publish event for audit trail
        from core.events import PrincipleAlignmentAssessed

        event = PrincipleAlignmentAssessed(
            principle_uid=principle_uid,
            entity_uid=EntityUID(principle_uid),
            entity_type="principle",
            user_uid=user_uid,
            alignment_score=system_score,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(result.to_dict())

    async def _store_user_assessment(
        self, principle_uid: str, assessment: UserAlignmentAssessment
    ) -> None:
        """Store user's self-assessment in principle's alignment_history."""
        # Get current principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            self.logger.warning(f"Could not store assessment: {principle_result.error}")
            return

        principle = principle_result.value
        if principle is None:
            self.logger.warning(f"Could not store assessment: principle {principle_uid} not found")
            return

        dto = principle.to_dto()

        # Add assessment to history (append pattern — no assess_alignment method on PrincipleDTO)

        from core.models.principle.principle_types import (
            AlignmentAssessment as KuAlignmentAssessment,
        )

        ku_assessment = KuAlignmentAssessment(
            assessed_date=date.today(),
            alignment_level=assessment.alignment_level,
            evidence=assessment.evidence,
            reflection=assessment.reflection,
        )
        # DTO stores alignment_history as list[dict] (flattened on to_dict via asdict);
        # convert here so the transfer-tier contract stays honest. See Principle._from_dto.
        dto.alignment_history.append(asdict(ku_assessment))

        # raw-write: full-DTO entity replace after appending to alignment_history (not a
        # partial property patch). ADR-066's PrincipleUpdateIntent models partial column
        # patches, not whole-entity persistence or history mutation — dto.to_dict() is the
        # honest shape here.
        await self.backend.update(principle_uid, dto.to_dict())

    async def _calculate_system_alignment(
        self, principle: Principle, user_uid: UserUID
    ) -> dict[str, Any]:
        """
        Calculate system alignment for a principle from the graph.

        Delegates to ``CrossDomainQueryService.get_principle_alignment_evidence``
        — one Cypher query that walks the explicit alignment edges
        (``GUIDES_GOAL``, ``GUIDED_BY_PRINCIPLE``, ``INSPIRES_HABIT``,
        ``EMBODIES_PRINCIPLE``) instead of pulling every goal and habit into
        Python and looping with a string-overlap heuristic.

        Returns:
            Dict with alignment_level, score, and evidence list (kept as a
            dict to preserve the contract with the caller).
        """
        evidence_result = await self.cross_domain_query.get_principle_alignment_evidence(
            principle.uid, user_uid
        )
        if evidence_result.is_error:
            self.logger.warning(
                "cross_domain_query.get_principle_alignment_evidence failed",
                extra={"principle_uid": principle.uid, "user_uid": user_uid},
            )
            return {
                "alignment_level": AlignmentLevel.UNKNOWN,
                "score": 0.0,
                "evidence": [],
            }

        evidence_data = evidence_result.value
        evidence_strings = [
            f"Goal '{g.title}' embodies this principle" for g in evidence_data.aligned_goals
        ] + [f"Habit '{h.title}' practices this principle" for h in evidence_data.aligned_habits]

        return {
            "alignment_level": evidence_data.alignment_level,
            "score": evidence_data.score,
            "evidence": evidence_strings,
        }

    def _calculate_perception_gap(
        self, user_level: AlignmentLevel, system_level: AlignmentLevel
    ) -> tuple[float, str]:
        """
        Calculate gap between self-perception and system measurement.

        Returns:
            Tuple of (gap_magnitude, gap_direction)
        """
        level_scores = {
            AlignmentLevel.ALIGNED: 1.0,
            AlignmentLevel.MOSTLY_ALIGNED: 0.75,
            AlignmentLevel.PARTIAL: 0.5,
            AlignmentLevel.MISALIGNED: 0.25,
            AlignmentLevel.UNKNOWN: 0.0,
        }

        user_score = level_scores.get(user_level, 0.5)
        system_score = level_scores.get(system_level, 0.5)
        gap = user_score - system_score

        if abs(gap) < 0.15:
            direction = "aligned"
        elif gap > 0:
            direction = "user_higher"  # User thinks more aligned than system shows
        else:
            direction = "system_higher"  # System shows more aligned than user thinks

        return abs(gap), direction

    def _score_to_alignment_level(self, score: float) -> AlignmentLevel:
        """Convert numeric score to AlignmentLevel."""
        if score >= 0.85:
            return AlignmentLevel.ALIGNED
        elif score >= 0.6:
            return AlignmentLevel.MOSTLY_ALIGNED
        elif score >= 0.4:
            return AlignmentLevel.PARTIAL
        elif score >= 0.15:
            return AlignmentLevel.MISALIGNED
        else:
            return AlignmentLevel.UNKNOWN

    # Gap insight/recommendation text lives in core/services/intelligence/
    # metrics_calculators.py (principle_gap_insights / principle_gap_recommendations),
    # shared with the dual-track path in _AlignmentIntelligenceMixin (ADR-030).

    # ========================================================================
    # MOTIVATIONAL INTELLIGENCE
    # ========================================================================

    @with_error_handling("get_motivational_profile", error_type="database")
    async def get_motivational_profile(self, user_uid: UserUID) -> Result[MotivationalProfile]:
        """
        Generate complete motivational profile for a user.

        Uses graph-based alignment evidence to compute goal/habit alignment
        scores directly from each principle's connected entities — no need
        to fetch goals/habits separately.

        Args:
            user_uid: User to profile.

        Returns:
            Complete motivational profile.
        """
        # Get principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result)

        all_principles = principles_result.value

        # Separate core and developing
        core_principles = [p for p in all_principles if p.strength == PrincipleStrength.CORE]
        developing = [p for p in all_principles if p.strength == PrincipleStrength.DEVELOPING]

        # Collect alignment evidence across all principles
        goal_scores: list[float] = []
        habit_scores: list[float] = []

        for principle in all_principles:
            evidence_result = await self.cross_domain_query.get_principle_alignment_evidence(
                principle.uid, user_uid
            )
            if evidence_result.is_error:
                continue

            evidence = evidence_result.value
            if evidence.aligned_goals:
                goal_scores.append(evidence.score)
            if evidence.aligned_habits:
                habit_scores.append(evidence.score)

        goal_alignment = sum(goal_scores) / len(goal_scores) if goal_scores else 0.0
        habit_alignment = sum(habit_scores) / len(habit_scores) if habit_scores else 0.0

        # Identify primary motivators
        primary_motivators = [f"{p.title}: {p.why_important}" for p in core_principles[:3]]

        # Identify conflicts from the two authored fields that carry them.
        conflicts = [
            _to_principle_conflict(p, other)
            for p in all_principles
            for other in p.conflicting_principles
        ]

        # NOT YET AUTHORED — deliberately empty, not silently dropped.
        #
        # These three fields were read from Principle members that have never
        # existed in this repo (``generate_aligned_goals()``,
        # ``generate_aligned_habits()``, ``growth_edges``), so every call to this
        # method raised AttributeError — surfaced as a *database* error by the
        # decorator above. PR2b makes the profile return the seven fields the
        # model can actually support rather than inventing semantics for the
        # other three.
        #
        # To fill them, decide what a suggestion IS first: the candidate sources
        # are ``Principle.expressions`` (PrincipleExpression) and
        # ``key_behaviors`` for the two suggestion lists, and the DEVELOPING
        # principles' ``key_behaviors`` for growth opportunities. That is a
        # pedagogical ruling, not a refactor.
        goal_suggestions: list[dict] = []
        habit_suggestions: list[dict] = []
        growth_opportunities: list[str] = []

        profile = MotivationalProfile(
            user_uid=user_uid,
            core_principles=core_principles,
            developing_principles=developing,
            goal_alignment_score=goal_alignment,
            habit_alignment_score=habit_alignment,
            primary_motivators=primary_motivators,
            value_conflicts=conflicts,
            growth_opportunities=growth_opportunities,
            aligned_goal_suggestions=goal_suggestions[:5],
            aligned_habit_suggestions=habit_suggestions[:5],
        )

        return Result.ok(profile)

    @with_error_handling("make_principle_based_decision", error_type="database")
    async def make_principle_based_decision(
        self, user_uid: UserUID, decision_description: str, options: list[str], context: str = ""
    ) -> Result[PrincipleDecision]:
        """
        Help make a decision based on principles.

        Args:
            user_uid: User making the decision,
            decision_description: What decision is being made,
            options: Available options,
            context: Additional context

        Returns:
            Principle-based decision recommendation
        """
        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return Result.fail(principles_result)

        principles = principles_result.value

        # Score each option against each principle
        principle_scores: dict[str, dict[str, float]] = {}

        for option in options:
            option_scores: dict[str, float] = {}

            for principle in principles:
                # Simple scoring based on keyword matching
                # In reality, this would be more sophisticated
                score = self._score_option_against_principle(option, principle, context)
                option_scores[principle.uid] = score

            principle_scores[option] = option_scores

        # Find recommended option
        option_rankings = []
        for option, scores in principle_scores.items():
            # Weight scores by principle priority
            weighted_sum = 0.0
            for principle_uid, score in scores.items():
                principle = next(p for p in principles if p.uid == principle_uid)
                priority_numeric = get_principle_priority(principle)
                weighted_sum += score * (priority_numeric / 10.0)

            option_rankings.append((option, weighted_sum))

        option_rankings.sort(key=itemgetter(1), reverse=True)
        recommended = option_rankings[0][0] if option_rankings else options[0]

        # Build recommendation reason
        top_principles = sorted(principles, key=get_principle_priority, reverse=True)[:3]
        reason = f"This option best aligns with your core principles: {', '.join([p.title for p in top_principles])}"

        # Identify conflicts
        conflicts = []
        for p1 in principles:
            for p2 in principles:
                if p1.uid != p2.uid and self._creates_conflict(principle_scores, p1, p2):
                    # Check if options create conflict between principles
                    p1_priority = get_principle_priority(p1)
                    p2_priority = get_principle_priority(p2)
                    conflict = PrincipleConflict(
                        conflicting_principle_uid=p2.uid,
                        conflict_description=f"{p1.title} vs {p2.title}",
                        resolution_strategy=_resolution_strategy(p1),
                        priority_in_conflict=1 if p1_priority > p2_priority else 2,
                    )
                    conflicts.append(conflict)

        decision = PrincipleDecision(
            decision_description=decision_description,
            options=tuple(options),
            principle_scores=principle_scores,
            recommended_option=recommended,
            recommendation_reason=reason,
            conflicts=tuple(conflicts),
            context=context,
            importance="medium",
        )

        return Result.ok(decision)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _identify_alignment_strengths(self, alignments: list[PrincipleAlignment]) -> list[str]:
        """Identify where alignment is strong"""
        return [
            f"Strong alignment with {alignment.principle_uid}"
            for alignment in alignments
            if alignment.alignment_score >= 0.75
        ]

    def _identify_alignment_gaps(self, alignments: list[PrincipleAlignment]) -> list[str]:
        """Identify where alignment is weak"""
        return [
            f"Weak alignment with {alignment.principle_uid}"
            for alignment in alignments
            if alignment.alignment_score < 0.5
        ]

    def _generate_alignment_recommendations(
        self, alignments: list[PrincipleAlignment], principles: list[Principle]
    ) -> list[str]:
        """Generate recommendations for improving alignment based on graph evidence."""
        recommendations = []

        # Find unconnected principles — suggest creating explicit links
        for alignment in alignments:
            if alignment.alignment_level in [AlignmentLevel.UNKNOWN, AlignmentLevel.MISALIGNED]:
                principle = next((p for p in principles if p.uid == alignment.principle_uid), None)
                if principle:
                    recommendations.append(
                        f"Create an explicit connection between this entity and '{principle.title}'"
                    )

        # Suggest strengthening already-aligned principles
        for alignment in alignments:
            if alignment.alignment_level == AlignmentLevel.ALIGNED:
                recommendations.extend(alignment.strengthen_alignment())

        return recommendations[:5]

    def _score_option_against_principle(
        self, option: str, principle: Principle, _context: str
    ) -> float:
        """Score how well an option aligns with a principle"""
        # Simple keyword matching - would be more sophisticated in practice
        score = 0.5  # Neutral baseline

        option_lower = option.lower()
        principle_keywords = principle.title.lower().split() + (
            principle.description.lower().split()[:10] if principle.description else []
        )

        # Check for keyword matches
        matches = sum(1 for keyword in principle_keywords if keyword in option_lower)
        score += matches * 0.1

        # Cap at 1.0
        return min(score, 1.0)

    def _creates_conflict(
        self, scores: dict[str, dict[str, float]], p1: Principle, p2: Principle
    ) -> bool:
        """Check if option scores create conflict between principles"""
        # Check if principles disagree strongly on best option
        for option1, scores1 in scores.items():
            for option2, scores2 in scores.items():
                if option1 != option2:
                    p1_prefers_1 = scores1.get(p1.uid, 0) > scores2.get(p1.uid, 0)
                    p2_prefers_2 = scores2.get(p2.uid, 0) > scores1.get(p2.uid, 0)

                    if p1_prefers_1 and p2_prefers_2:
                        return True

        return False

    # ========================================================================
    # ALIGNMENT CALCULATION & TRACKING (October 14, 2025)
    # ========================================================================

    async def calculate_average_alignment(self, user_uid: UserUID) -> Result[float]:
        """
        Calculate average alignment score across all user's principles.

        Takes the most recent alignment assessment from each principle's
        alignment_history and calculates a weighted average.

        Returns:
            Result[float]: Average alignment score (0.0 to 1.0)
        """
        self.logger.debug(f"Calculating average alignment for user {user_uid}")

        # Get all user's principles
        principles_result = await self.backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if principles_result.is_error:
            return Result.fail(principles_result)

        if not principles_result.value:
            return Result.ok(0.0)

        # Calculate alignment score for each principle
        total_score = 0.0
        count = 0

        for item in principles_result.value:
            if isinstance(item, dict):
                from core.models.principle.principle_dto import PrincipleDTO

                principle_dto = PrincipleDTO.from_dict(item)
                principle = Principle.from_dto(principle_dto)
            else:
                principle = item

            # Get most recent alignment from history
            if principle.alignment_history and len(principle.alignment_history) > 0:
                latest_alignment = principle.alignment_history[-1]
                score = self._alignment_level_to_score(latest_alignment.alignment_level)
                total_score += score
                count += 1

        if count == 0:
            return Result.ok(0.0)

        average = total_score / count
        self.logger.debug(f"Average alignment: {average:.2f} across {count} principles")
        return Result.ok(average)

    @staticmethod
    def _alignment_level_to_score(level: AlignmentLevel) -> float:
        """Convert alignment level enum to numeric score (0.0-1.0).

        Delegates to AlignmentLevel.to_score() — the single source of truth.
        """
        return level.to_score()
