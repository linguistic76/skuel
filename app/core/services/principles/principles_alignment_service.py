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

from dataclasses import dataclass
from datetime import date, datetime
from operator import itemgetter
from typing import Any

from core.constants import QueryLimit
from core.events import publish_event
from core.models.enums.principle_enums import AlignmentLevel, PrincipleStrength
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.principle.principle_types import (
    AlignmentAssessment as UserAlignmentAssessment,
)
from core.models.principle.principle_types import (
    PrincipleAlignment,
    PrincipleConflict,
    PrincipleDecision,
)

# Protocol interfaces - Use main Operations protocols (not QueryOperations aliases)
from core.ports.domain_protocols import GoalsOperations, HabitsOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_principle_priority, get_timestamp

logger = get_logger(__name__)


@dataclass
class MotivationalProfile:
    """A user's complete motivational profile based on principles"""

    user_uid: str
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

    entity_uid: str
    entity_type: str
    entity_name: str
    principle_alignments: list[PrincipleAlignment]
    overall_alignment: float
    primary_principle: Principle | None
    strengths: list[str]
    gaps: list[str]
    recommendations: list[str]


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
        backend,
        goals_backend: GoalsOperations | None = None,
        habits_backend: HabitsOperations | None = None,
        event_bus=None,
    ) -> None:
        """
        Initialize principles alignment service.

        Args:
            backend: Backend for principle operations,
            goals_backend: Backend for goal queries,
            habits_backend: Backend for habit queries
            event_bus: Event bus for publishing domain events (optional)
        """
        self.backend = backend
        self.goals_backend = goals_backend
        self.habits_backend = habits_backend
        self.event_bus = event_bus
        self.alignment_cache: dict[str, AlignmentAssessment] = {}
        self.logger = get_logger(__name__)

    # ========================================================================
    # ALIGNMENT ASSESSMENT
    # ========================================================================

    @with_error_handling("assess_goal_alignment", error_type="system", uid_param="goal_uid")
    async def assess_goal_alignment(
        self, goal_uid: str, user_uid: str
    ) -> Result[AlignmentAssessment]:
        """
        Assess how a goal aligns with user's principles.

        Args:
            goal_uid: Goal to assess,
            user_uid: User whose principles to check

        Returns:
            Complete alignment assessment
        """
        # Null-safety check
        if not self.goals_backend:
            return Result.fail(
                Errors.system(
                    message="Goals backend not available", operation="assess_goal_alignment"
                )
            )

        # Get goal
        goal = await self.goals_backend.get(goal_uid)
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return principles_result

        principles = principles_result.value

        # Assess alignment with each principle
        alignments = []
        total_score = 0.0

        for principle in principles:
            alignment_level = principle.assess_goal_alignment(goal.purpose, goal.category.value)

            # Calculate alignment score
            score = self._calculate_alignment_score(alignment_level)

            # Weight by principle priority
            priority_numeric = get_principle_priority(principle)
            weighted_score = score * (priority_numeric / 10.0)
            total_score += weighted_score

            # Create alignment record
            priority_numeric = get_principle_priority(principle)
            alignment = PrincipleAlignment(
                principle_uid=principle.uid,
                entity_uid=goal_uid,
                entity_type="goal",
                alignment_level=alignment_level,
                alignment_score=score,
                influence_description=f"{principle.label} influences goal through {goal.category.value}",
                influence_weight=priority_numeric / 10.0,
            )
            alignments.append(alignment)

            # Publish PrincipleAlignmentAssessed event (event-driven architecture)
            from core.events import PrincipleAlignmentAssessed

            event = PrincipleAlignmentAssessed(
                principle_uid=principle.uid,
                entity_uid=goal_uid,
                entity_type="goal",
                user_uid=user_uid,
                alignment_score=score,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        # Calculate overall alignment
        overall = total_score / len(principles) if principles else 0.0

        # Find primary principle
        primary = max(principles, key=get_principle_priority) if principles else None

        # Generate insights
        strengths = self._identify_alignment_strengths(alignments)
        gaps = self._identify_alignment_gaps(alignments)
        recommendations = self._generate_alignment_recommendations(goal, alignments, principles)

        assessment = AlignmentAssessment(
            entity_uid=goal_uid,
            entity_type="goal",
            entity_name=goal.name,
            principle_alignments=alignments,
            overall_alignment=overall,
            primary_principle=primary,
            strengths=strengths,
            gaps=gaps,
            recommendations=recommendations,
        )

        # Cache the assessment
        self.alignment_cache[f"goal_{goal_uid}"] = assessment

        return Result.ok(assessment)

    @with_error_handling("assess_habit_alignment", error_type="database")
    async def assess_habit_alignment(
        self, habit_uid: str, user_uid: str
    ) -> Result[AlignmentAssessment]:
        """
        Assess how a habit aligns with user's principles.

        Similar to goal alignment but for habits.
        """
        # Null-safety check
        if not self.habits_backend:
            return Result.fail(
                Errors.system(
                    message="Habits backend not available", operation="assess_habit_alignment"
                )
            )

        # Get habit
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return habit_result
        habit = habit_result.value

        # Get user's principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return principles_result

        principles = principles_result.value

        # Assess alignment with each principle
        alignments = []
        total_score = 0.0

        for principle in principles:
            alignment_level = principle.assess_habit_alignment(
                habit.habit_category.value, habit.polarity.value
            )

            # Calculate alignment score
            score = self._calculate_alignment_score(alignment_level)
            priority_numeric = get_principle_priority(principle)
            weighted_score = score * (priority_numeric / 10.0)
            total_score += weighted_score

            # Create alignment record
            priority_numeric = get_principle_priority(principle)
            alignment = PrincipleAlignment(
                principle_uid=principle.uid,
                entity_uid=habit_uid,
                entity_type="habit",
                alignment_level=alignment_level,
                alignment_score=score,
                influence_description=f"{principle.label} practiced through {habit.title}",
                influence_weight=priority_numeric / 10.0,
            )
            alignments.append(alignment)

            # Publish PrincipleAlignmentAssessed event (event-driven architecture)
            from core.events import PrincipleAlignmentAssessed

            event = PrincipleAlignmentAssessed(
                principle_uid=principle.uid,
                entity_uid=habit_uid,
                entity_type="habit",
                user_uid=user_uid,
                alignment_score=score,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

        # Calculate overall alignment
        overall = total_score / len(principles) if principles else 0.0

        # Find primary principle
        primary = max(principles, key=get_principle_priority) if principles else None

        # Generate insights
        assessment = AlignmentAssessment(
            entity_uid=habit_uid,
            entity_type="habit",
            entity_name=habit.title,
            principle_alignments=alignments,
            overall_alignment=overall,
            primary_principle=primary,
            strengths=self._identify_alignment_strengths(alignments),
            gaps=self._identify_alignment_gaps(alignments),
            recommendations=self._generate_habit_recommendations(habit, alignments, principles),
        )

        return Result.ok(assessment)

    # ========================================================================
    # HYBRID DUAL-TRACK ALIGNMENT (January 2026)
    # ========================================================================

    @with_error_handling("assess_with_user_input", error_type="database")
    async def assess_with_user_input(
        self,
        principle_uid: str,
        user_uid: str,
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
        from datetime import date

        from core.models.principle.principle_dto import PrincipleDTO
        from core.models.principle.principle_request import PrincipleAlignmentAssessmentResult

        # 1. Get the principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return principle_result

        principle_dict = principle_result.value
        if isinstance(principle_dict, dict):
            principle_dto = PrincipleDTO.from_dict(principle_dict)
            principle = Principle.from_dto(principle_dto)
        else:
            principle = principle_dict

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
        insights = self._generate_gap_insights(direction, gap, principle.title)

        # 7. Generate recommendations
        recommendations = self._generate_gap_recommendations(
            direction, gap, principle, system_evidence
        )

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
            entity_uid=principle_uid,
            entity_type="principle",
            user_uid=user_uid,
            alignment_score=system_score,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(result.to_dict())

    async def _store_user_assessment(
        self, principle_uid: str, assessment: UserAlignmentAssessment
    ) -> None:
        """Store user's self-assessment in principle's alignment_history."""
        from core.models.principle.principle_dto import PrincipleDTO

        # Get current principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            self.logger.warning(f"Could not store assessment: {principle_result.error}")
            return

        principle_dict = principle_result.value
        if isinstance(principle_dict, dict):
            dto = PrincipleDTO.from_dict(principle_dict)
        else:
            dto = principle_dict.to_dto()

        # Add assessment to history (append pattern — no assess_alignment method on PrincipleDTO)
        from datetime import date

        from core.models.principle.principle_types import (
            AlignmentAssessment as KuAlignmentAssessment,
        )

        ku_assessment = KuAlignmentAssessment(
            assessed_date=date.today(),
            alignment_level=assessment.alignment_level,
            evidence=assessment.evidence,
            reflection=assessment.reflection,
        )
        dto.alignment_history.append(ku_assessment)

        # Update in backend
        await self.backend.update(principle_uid, dto.to_dict())

    async def _calculate_system_alignment(
        self, principle: Principle, user_uid: str
    ) -> dict[str, Any]:
        """
        Calculate system alignment from goals, habits, and choices.

        Examines:
        - Goals guided by this principle
        - Habits inspired by this principle
        - Recent choices aligned with this principle

        Returns:
            Dict with alignment_level, score, and evidence list
        """
        evidence = []
        total_score = 0.0
        count = 0

        # Check goals (if backend available)
        if self.goals_backend:
            try:
                goals = await self.goals_backend.list_by_user(user_uid)
                for goal in goals:
                    # Check if goal aligns with principle
                    alignment = principle.assess_goal_alignment(
                        goal.title,  # Goal has 'title', not 'purpose' or 'name'
                        goal.domain.value,  # Goal has 'domain: Domain', not 'category'
                    )
                    if alignment in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]:
                        evidence.append(f"Goal '{goal.title}' embodies this principle")
                        total_score += self._calculate_alignment_score(alignment)
                        count += 1
            except Exception as e:
                self.logger.debug(f"Could not check goals: {e}")

        # Check habits (if backend available)
        if self.habits_backend:
            try:
                habits = await self.habits_backend.list_by_user(user_uid)
                for habit in habits:
                    # Check if habit aligns with principle
                    alignment = principle.assess_habit_alignment(
                        habit.habit_category.value,  # HabitCategory always exists (default: OTHER)
                        habit.polarity.value,  # HabitPolarity always exists (default: BUILD)
                    )
                    if alignment in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]:
                        evidence.append(f"Habit '{habit.title}' practices this principle")
                        total_score += self._calculate_alignment_score(alignment)
                        count += 1
            except Exception as e:
                self.logger.debug(f"Could not check habits: {e}")

        # Calculate overall alignment
        if count > 0:
            avg_score = total_score / count
        else:
            avg_score = 0.25  # Unknown if no connected entities

        # Convert score to alignment level
        system_level = self._score_to_alignment_level(avg_score)

        return {
            "alignment_level": system_level,
            "score": avg_score,
            "evidence": evidence,
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

    def _generate_gap_insights(self, direction: str, gap: float, principle_name: str) -> list[str]:
        """Generate insights based on the perception gap."""
        insights = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of alignment with '{principle_name}' "
                "matches your recorded actions. This indicates healthy self-reflection."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your recorded actions suggest "
                f"(gap: {gap:.0%}). Consider: Are there activities expressing this principle "
                "that aren't tracked in SKUEL?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate a blind spot in self-perception, "
                    "or opportunities to better live out this principle."
                )
        else:  # system_higher
            insights.append(
                f"Your actions show stronger alignment than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your consistency with this principle."
            )
            if gap > 0.3:
                insights.append(
                    "Consider acknowledging your progress - self-recognition strengthens motivation."
                )

        return insights

    def _generate_gap_recommendations(
        self,
        direction: str,
        gap: float,
        principle: Principle,
        evidence: list[str],
    ) -> list[str]:
        """Generate recommendations to close the gap."""
        recommendations = []

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            if principle.expressions:
                recommendations.append(
                    "Consider documenting new expressions of this principle as they arise."
                )
        elif direction == "user_higher":
            recommendations.append(
                "Review your goals and habits to ensure they explicitly connect to this principle."
            )
            if not evidence:
                recommendations.append(
                    "Create at least one goal or habit that directly expresses this principle."
                )
            recommendations.append(
                "Track specific instances where you practice this principle over the next week."
            )
        else:  # system_higher
            recommendations.append(
                "Acknowledge the alignment you've already achieved through your actions."
            )
            if evidence:
                recommendations.append(
                    f"Celebrate your progress: {len(evidence)} activities already express this principle."
                )
            recommendations.append(
                "Consider reflecting on why your self-perception doesn't match your positive actions."
            )

        return recommendations[:4]  # Limit to top 4 recommendations

    # ========================================================================
    # MOTIVATIONAL INTELLIGENCE
    # ========================================================================

    @with_error_handling("get_motivational_profile", error_type="database")
    async def get_motivational_profile(self, user_uid: str) -> Result[MotivationalProfile]:
        """
        Generate complete motivational profile for a user.

        This combines principles with goals and habits to understand
        the user's core motivations and alignment.

        Args:
            user_uid: User to profile

        Returns:
            Complete motivational profile
        """
        # Get principles
        principles_result = await self.backend.find_by(user_uid=user_uid)
        if principles_result.is_error:
            return principles_result

        all_principles = principles_result.value

        # Separate core and developing
        core_principles = [p for p in all_principles if p.strength == PrincipleStrength.CORE]
        developing = [p for p in all_principles if p.strength == PrincipleStrength.DEVELOPING]

        # Get user's goals and habits
        goals = await self.goals_backend.list_by_user(user_uid) if self.goals_backend else []
        habits = await self.habits_backend.list_by_user(user_uid) if self.habits_backend else []

        # Calculate alignment scores
        goal_scores = []
        for goal in goals:
            assessment = await self.assess_goal_alignment(goal.uid, user_uid)
            if assessment.is_ok:
                goal_scores.append(assessment.value.overall_alignment)

        habit_scores = []
        for habit in habits:
            assessment = await self.assess_habit_alignment(habit.uid, user_uid)
            if assessment.is_ok:
                habit_scores.append(assessment.value.overall_alignment)

        # Calculate averages
        goal_alignment = sum(goal_scores) / len(goal_scores) if goal_scores else 0.0
        habit_alignment = sum(habit_scores) / len(habit_scores) if habit_scores else 0.0

        # Identify primary motivators
        primary_motivators = [f"{p.label}: {p.why_matters}" for p in core_principles[:3]]

        # Identify conflicts
        conflicts = []
        for principle in all_principles:
            conflicts.extend(principle.conflicting_principles)

        # Generate suggestions
        goal_suggestions = []
        habit_suggestions = []

        for principle in core_principles[:2]:  # Top 2 core principles
            goal_suggestions.extend(principle.generate_aligned_goals())
            habit_suggestions.extend(principle.generate_aligned_habits())

        # Identify growth opportunities
        growth_opportunities = []
        for principle in developing:
            growth_opportunities.extend(principle.growth_edges)

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
        self, user_uid: str, decision_description: str, options: list[str], context: str = ""
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
            return principles_result

        principles = principles_result.value

        # Score each option against each principle
        principle_scores = {}

        for option in options:
            option_scores = {}

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
        reason = f"This option best aligns with your core principles: {', '.join([p.label for p in top_principles])}"

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
                        conflict_description=f"{p1.label} vs {p2.label}",
                        resolution_strategy=p1.resolve_conflict(p2, context),
                        priority_in_conflict=1 if p1_priority > p2_priority else 2,
                    )
                    conflicts.append(conflict)

        decision = PrincipleDecision(
            decision_description=decision_description,
            options=options,
            principle_scores=principle_scores,
            recommended_option=recommended,
            recommendation_reason=reason,
            conflicts=conflicts,
            context=context,
            importance="medium",
        )

        return Result.ok(decision)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _calculate_alignment_score(self, level: AlignmentLevel) -> float:
        """Convert alignment level to numeric score"""
        scores = {
            AlignmentLevel.ALIGNED: 1.0,
            AlignmentLevel.MOSTLY_ALIGNED: 0.75,
            AlignmentLevel.PARTIAL: 0.5,
            AlignmentLevel.MISALIGNED: 0.0,
            AlignmentLevel.UNKNOWN: 0.25,
        }
        return scores.get(level, 0.25)

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
        self, goal: Goal, alignments: list[PrincipleAlignment], principles: list[Principle]
    ) -> list[str]:
        """Generate recommendations for improving goal alignment"""
        recommendations = []

        # Find misaligned principles
        for alignment in alignments:
            if alignment.alignment_level in [AlignmentLevel.MISALIGNED, AlignmentLevel.PARTIAL]:
                principle = next(p for p in principles if p.uid == alignment.principle_uid)
                recommendations.append(
                    f"Consider how {goal.name} can better embody {principle.title}"
                )

        # Suggest habits that support aligned principles
        for alignment in alignments:
            if alignment.alignment_level == AlignmentLevel.ALIGNED:
                recommendations.extend(alignment.strengthen_alignment())

        return recommendations[:5]  # Top 5 recommendations

    def _generate_habit_recommendations(
        self, habit: Habit, alignments: list[PrincipleAlignment], principles: list[Principle]
    ) -> list[str]:
        """Generate recommendations for improving habit alignment"""
        recommendations = []

        # Suggest ways to strengthen alignment
        for alignment in alignments:
            if alignment.alignment_score < 0.75:
                principle = next(p for p in principles if p.uid == alignment.principle_uid)
                recommendations.append(f"Modify {habit.title} to better practice {principle.title}")

        return recommendations[:5]

    def _score_option_against_principle(
        self, option: str, principle: Principle, _context: str
    ) -> float:
        """Score how well an option aligns with a principle"""
        # Simple keyword matching - would be more sophisticated in practice
        score = 0.5  # Neutral baseline

        option_lower = option.lower()
        principle_keywords = (
            principle.title.lower().split() + principle.description.lower().split()[:10]
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

    async def calculate_average_alignment(self, user_uid: str) -> Result[float]:
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
            return principles_result

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

    def _alignment_level_to_score(self, level: AlignmentLevel) -> float:
        """
        Convert alignment level enum to numeric score.

        Mapping:
        - ALIGNED: 1.0
        - MOSTLY_ALIGNED: 0.75
        - PARTIAL: 0.5
        - MISALIGNED: 0.0
        - UNKNOWN: 0.25
        """
        mapping = {
            AlignmentLevel.ALIGNED: 1.0,
            AlignmentLevel.MOSTLY_ALIGNED: 0.75,
            AlignmentLevel.PARTIAL: 0.5,
            AlignmentLevel.MISALIGNED: 0.0,
            AlignmentLevel.UNKNOWN: 0.25,
        }
        return mapping.get(level, 0.0)

    async def get_principle_expressions_and_alignments(
        self, principle_uid: str
    ) -> Result[dict[str, Any]]:
        """
        Get expressions and alignment history for a principle.

        Returns:
            Result[Dict]: {
                "expressions": List[str],
                "alignments": List[Dict] with assessed_date, level, evidence, reflection
            }
        """
        self.logger.debug(f"Getting expressions and alignments for {principle_uid}")

        # Get principle
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return principle_result

        principle_dict = principle_result.value
        from core.models.principle.principle_dto import PrincipleDTO

        principle_dto = PrincipleDTO.from_dict(principle_dict)
        principle = Principle.from_dto(principle_dto)

        # Extract expressions
        expressions = list(principle.expressions) if principle.expressions else []

        # Extract alignment history
        alignments = []
        if principle.alignment_history:
            for assessment in principle.alignment_history:
                # Handle both date objects and string dates
                from datetime import date, datetime

                assessed_date_str = (
                    assessment.assessed_date.isoformat()
                    if isinstance(assessment.assessed_date, date | datetime)
                    else str(assessment.assessed_date)
                )

                alignments.append(
                    {
                        "assessed_date": assessed_date_str,
                        "alignment_level": assessment.alignment_level.value,
                        "alignment_score": self._alignment_level_to_score(
                            assessment.alignment_level
                        ),
                        "evidence": assessment.evidence,
                        "reflection": assessment.reflection,
                    }
                )

        return Result.ok(
            {
                "principle_uid": principle_uid,
                "expressions": expressions,
                "alignments": alignments,
                "current_alignment": principle.current_alignment.value
                if principle.current_alignment
                else None,
                "total_expressions": len(expressions),
                "total_assessments": len(alignments),
            }
        )

    async def get_recent_activity(
        self, user_uid: str, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Get recent principle-related activities for a user.

        Activities include:
        - Alignment assessments created
        - Principles updated
        - Expressions added

        Returns:
            Result[List[Dict]]: List of activity dicts with timestamp, type, description
        """
        self.logger.debug(f"Getting recent activity for user {user_uid}")

        # Get all user's principles
        principles_result = await self.backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if principles_result.is_error:
            return principles_result

        activities = []

        for item in principles_result.value:
            if isinstance(item, dict):
                from core.models.principle.principle_dto import PrincipleDTO

                principle_dto = PrincipleDTO.from_dict(item)
                principle = Principle.from_dto(principle_dto)
            else:
                principle = item

            # Track principle updates
            activities.append(
                {
                    "timestamp": principle.updated_at,
                    "type": "principle_updated",
                    "description": f"Updated principle: {principle.statement}",
                    "principle_uid": principle.uid,
                    "principle_name": principle.statement[:50] + "..."
                    if len(principle.statement) > 50
                    else principle.statement,
                }
            )

            # Track alignment assessments
            if principle.alignment_history:
                activities.extend(
                    [
                        {
                            # Convert date to datetime for consistent sorting with other timestamps
                            "timestamp": datetime.combine(
                                assessment.assessed_date, datetime.min.time()
                            )
                            if isinstance(assessment.assessed_date, date)
                            and not isinstance(assessment.assessed_date, datetime)
                            else assessment.assessed_date,
                            "type": "alignment_assessed",
                            "description": f"Assessed alignment as {assessment.alignment_level.value}",
                            "principle_uid": principle.uid,
                            "principle_name": principle.statement[:50] + "..."
                            if len(principle.statement) > 50
                            else principle.statement,
                            "alignment_level": assessment.alignment_level.value,
                        }
                        for assessment in principle.alignment_history
                    ]
                )

            # Track expressions (using principle updated_at as proxy)
            if principle.expressions:
                for expression in principle.expressions:
                    # Handle PrincipleExpression objects and strings
                    from core.models.principle.principle_types import PrincipleExpression

                    expr_text = (
                        expression.behavior
                        if isinstance(expression, PrincipleExpression)
                        else str(expression)
                    )
                    expr_summary = expr_text[:50] + "..." if len(expr_text) > 50 else expr_text

                    activities.append(
                        {
                            "timestamp": principle.updated_at,
                            "type": "expression_added",
                            "description": f"Added expression: {expr_summary}",
                            "principle_uid": principle.uid,
                            "principle_name": principle.statement[:50] + "..."
                            if len(principle.statement) > 50
                            else principle.statement,
                            "expression": expr_text,
                        }
                    )

        # Sort by timestamp (most recent first)
        activities.sort(key=get_timestamp, reverse=True)

        # Limit results
        limited_activities = activities[:limit]

        self.logger.debug(f"Found {len(limited_activities)} recent activities")
        return Result.ok(limited_activities)
