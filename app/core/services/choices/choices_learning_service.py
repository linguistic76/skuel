"""
Choices Learning Service - Learning Path Guidance
==================================================

Handles learning path integration and guidance for choices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.activity_requests import ChoiceCreateRequest
from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.curriculum.learning_step import LearningStep
from core.models.enums import Domain, EntityStatus, Priority
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure import LearningAlignmentHelper
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.curriculum.lp_position import LpPosition
    from core.ports import BackendOperations


class ChoicesLearningService(BaseService["BackendOperations[Choice]", Choice]):
    """
    Learning path integration and guidance for choices.

    Responsibilities:
    - Create choices with learning guidance
    - Generate learning-informed decision guidance
    - Analyze option learning impact
    - Track choice learning outcomes
    - Suggest learning-aligned choices


    Source Tag: "choices_learning_service_explicit"
    - Format: "choices_learning_service_explicit" for user-created relationships
    - Format: "choices_learning_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from choices_learning metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=ChoiceDTO,
        model_class=Choice,
        domain_name="choices",
        date_field="decision_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    def __init__(self, backend: BackendOperations[Choice]) -> None:
        """
        Initialize choices learning service.

        Args:
            backend: Protocol-based backend for choice operations
        """
        super().__init__(backend, "choices.learning")
        self.logger = get_logger("skuel.services.choices.learning")

        # Initialize LearningAlignmentHelper for learning operations
        self.learning_helper = LearningAlignmentHelper[Choice, ChoiceDTO, ChoiceCreateRequest](
            service=self,
            backend_get_method="get",
            backend_get_user_method="get_user_choices",
            backend_create_method="create",
            dto_class=ChoiceDTO,
            model_class=Choice,
            domain=Domain.CHOICES,
            entity_name="choice",
        )

    async def create_choice_with_learning_guidance(
        self,
        choice_request: ChoiceCreateRequest,
        user_uid: str,
        learning_position: LpPosition | None = None,
    ) -> Result[Choice]:
        """
        Create a choice enhanced with learning path guidance.

        This method applies knowledge-first thinking: How does the user's learning
        path position frame this choice creation?

        Args:
            choice_request: Choice creation request
            user_uid: User UID (REQUIRED)
            learning_position: User's learning path position context

        Returns:
            Result containing created Choice with learning path guidance
        """
        # Import core service for base creation
        from core.services.choices.choices_core_service import ChoicesCoreService

        core_service = ChoicesCoreService(backend=self.backend)

        # Create base choice using core service
        choice_result = await core_service.create_choice(choice_request, user_uid=user_uid)
        if choice_result.is_error:
            return choice_result  # type: ignore[return-value]

        choice = choice_result.value

        # Apply learning path guidance if position provided
        if learning_position:
            # Get learning-informed choice guidance
            guidance = learning_position.suggest_choice_guidance(
                choice_request.description or choice_request.title
            )

            # Log learning path guidance
            self.logger.info(
                "Choice '%s' created with learning guidance: %d implications from %d paths",
                choice.title,
                len(guidance["learning_path_implications"]),
                len(learning_position.active_paths),
            )

            # Store guidance in choice metadata (if choice has metadata field)
            # For now, just log the guidance

        return Result.ok(choice)

    async def get_learning_informed_guidance(
        self,
        choice_description: str,
        learning_position: LpPosition,
        choice_options: list[str] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Get learning-informed guidance for a decision.

        Args:
            choice_description: Description of the choice being made,
            learning_position: User's learning path position,
            choice_options: Optional list of choice options

        Returns:
            Result containing learning-informed decision guidance
        """
        # Get base guidance from learning position
        guidance = learning_position.suggest_choice_guidance(choice_description)

        # Enhance with choice-specific analysis
        enhanced_guidance = {
            "choice_description": choice_description,
            "learning_path_implications": guidance["learning_path_implications"],
            "recommended_approach": guidance["recommended_approach"],
            "long_term_learning_impact": guidance["long_term_learning_impact"],
            "prerequisite_considerations": guidance["prerequisite_considerations"],
            "option_analysis": [],
            "learning_alignment_scores": {},
            "decision_framework": [],
            "next_steps": [],
        }

        # Analyze specific options if provided
        if choice_options:
            for option in choice_options:
                option_analysis = self._analyze_option_learning_impact(option, learning_position)
                enhanced_guidance["option_analysis"].append(option_analysis)
                enhanced_guidance["learning_alignment_scores"][option] = option_analysis[
                    "alignment_score"
                ]

        # Generate decision framework
        enhanced_guidance["decision_framework"] = [
            "Consider alignment with active learning paths",
            "Evaluate impact on learning progression",
            "Assess prerequisite implications",
            "Consider long-term learning goals",
            "Reflect on character development opportunities",
        ]

        # Generate next steps
        if enhanced_guidance["learning_alignment_scores"]:
            best_option = max(
                enhanced_guidance["learning_alignment_scores"],
                key=enhanced_guidance["learning_alignment_scores"].get,
            )
            enhanced_guidance["next_steps"].append(
                f"Consider '{best_option}' for best learning alignment"
            )

        enhanced_guidance["next_steps"].extend(
            [
                "Reflect on decision through learning path lens",
                "Consider how choice supports learning objectives",
                "Plan integration with current learning activities",
            ]
        )

        self.logger.info(
            "Generated learning-informed guidance for choice: %d implications, %d options analyzed",
            len(enhanced_guidance["learning_path_implications"]),
            len(choice_options) if choice_options else 0,
        )

        return Result.ok(enhanced_guidance)

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Choice entities."""
        return "Entity"

    def _analyze_option_learning_impact(
        self, option: str, learning_position: LpPosition
    ) -> dict[str, Any]:
        """
        Analyze how an option impacts learning progression.

        Args:
            option: Choice option to analyze,
            learning_position: User's learning path position

        Returns:
            Option analysis with learning impact assessment
        """
        # Use typed local variables for calculations
        alignment_score: float = 0.0
        supporting_paths: list[dict[str, Any]] = []
        learning_benefits: list[str] = []
        potential_drawbacks: list[str] = []

        option_lower = option.lower()

        # Check alignment with active learning paths
        for path in learning_position.active_paths:
            path_alignment = 0.0

            # Domain alignment
            path_domain = str(path.domain.value)

            # Simple keyword matching for demonstration
            if any(word in option_lower for word in path.name.lower().split()):
                path_alignment += 0.5

            if path_domain.lower() in option_lower:
                path_alignment += 0.3

            # Current step relevance
            current_step = learning_position.current_steps.get(path.uid)
            if current_step and isinstance(current_step, LearningStep):
                # Check if any knowledge UIDs from the step appear in the option
                step_knowledge = current_step.get_all_knowledge_uids()
                if any(ku.lower() in option_lower for ku in step_knowledge):
                    path_alignment += 0.4

            if path_alignment > 0.3:
                supporting_paths.append(
                    {
                        "path": path.name,
                        "alignment": path_alignment,
                        "reason": f"Option aligns with {path.name} learning objectives",
                    }
                )
                alignment_score += path_alignment

        # Normalize alignment score
        if learning_position.active_paths:
            alignment_score = min(1.0, alignment_score / len(learning_position.active_paths))

        # Generate learning benefits
        if alignment_score > 0.7:
            learning_benefits = [
                "Strongly supports current learning objectives",
                "Aligns with active learning path progression",
                "Provides opportunities for knowledge application",
            ]
        elif alignment_score > 0.4:
            learning_benefits = [
                "Moderately supports learning objectives",
                "Some alignment with learning path goals",
            ]
        else:
            learning_benefits = [
                "May provide new learning opportunities",
                "Could broaden learning perspective",
            ]

        # Identify potential drawbacks
        if alignment_score < 0.3:
            potential_drawbacks = [
                "May divert focus from current learning priorities",
                "Limited connection to active learning paths",
            ]

        # Character development opportunities
        character_development: list[str] = [
            "Practice decision-making aligned with learning values",
            "Develop judgment in learning-oriented choices",
            "Build character through consistent learning decisions",
        ]

        # Build final analysis dict with all computed values
        return {
            "option": option,
            "alignment_score": alignment_score,
            "supporting_paths": supporting_paths,
            "learning_benefits": learning_benefits,
            "potential_drawbacks": potential_drawbacks,
            "character_development": character_development,
        }

    async def track_choice_learning_outcomes(
        self,
        choice_uid: str,
        learning_position: LpPosition,
        _outcome_data: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Track how choice outcomes relate to learning path advancement.

        Args:
            choice_uid: Choice to track,
            learning_position: User's learning path position,
            outcome_data: Optional outcome information

        Returns:
            Result containing choice outcome tracking in learning context
        """
        # Get the choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = self._to_domain_model(choice_result.value, ChoiceDTO, Choice)

        # Use typed local variables for calculations
        learning_impact_score: float = 0.0
        path_advancement: list[dict[str, Any]] = []
        knowledge_gains: list[str] = []
        character_development: list[str] = []
        lessons_learned: list[str] = []
        future_guidance: list[str] = []

        # Assess learning impact
        total_impact = 0.0
        path_count = 0

        for path in learning_position.active_paths:
            path_impact = 0.0

            # Check if choice affected this path
            choice_text = f"{choice.title} {choice.description}".lower()
            if path.name.lower() in choice_text:
                path_impact += 0.5

            # Check current step relevance
            current_step = learning_position.current_steps.get(path.uid)
            if current_step and isinstance(current_step, LearningStep):
                # Check if any knowledge UIDs from the step appear in the choice text
                step_knowledge = current_step.get_all_knowledge_uids()
                if any(ku.lower() in choice_text for ku in step_knowledge):
                    path_impact += 0.4

            if path_impact > 0.3:
                path_count += 1
                total_impact += path_impact

                path_advancement.append(
                    {
                        "path": path.name,
                        "impact_score": path_impact,
                        "advancement": f"Choice supported progression in {path.name}",
                    }
                )

        # Calculate overall impact
        if path_count > 0:
            learning_impact_score = total_impact / path_count

        # Generate insights
        if learning_impact_score > 0.7:
            lessons_learned = [
                "Choice was well-aligned with learning objectives",
                "Decision-making framework proved effective",
                "Learning path guidance was valuable",
            ]
        elif learning_impact_score > 0.4:
            lessons_learned = [
                "Choice had moderate learning benefits",
                "Some aspects aligned with learning goals",
            ]
        else:
            lessons_learned = [
                "Choice provided learning through experience",
                "Opportunity to refine decision-making approach",
            ]

        # Future guidance
        future_guidance = [
            "Continue applying learning-first decision framework",
            "Reflect on choice outcomes in learning context",
            "Use insights to improve future decision-making",
        ]

        # Build final outcome tracking dict
        outcome_tracking = {
            "choice_uid": choice.uid,
            "choice_title": choice.title,
            "learning_impact_score": learning_impact_score,
            "path_advancement": path_advancement,
            "knowledge_gains": knowledge_gains,
            "character_development": character_development,
            "lessons_learned": lessons_learned,
            "future_guidance": future_guidance,
        }

        return Result.ok(outcome_tracking)

    async def suggest_learning_aligned_choices(
        self,
        learning_position: LpPosition,
        choice_domain: Domain | None = None,
        urgency_level: Priority | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest choices that align with current learning path progression.

        Args:
            learning_position: User's learning path position,
            choice_domain: Optional domain filter,
            urgency_level: Optional urgency filter

        Returns:
            Result containing suggested choices with learning alignment
        """
        # Use LearningAlignmentHelper (consolidation)
        result = await self.learning_helper.suggest_learning_aligned_entities(
            learning_position=learning_position, filter_param=choice_domain, max_suggestions=10
        )

        if result.is_error:
            return result

        # Apply urgency level if specified
        if urgency_level:
            for choice in result.value:
                choice["urgency"] = urgency_level

        return result
