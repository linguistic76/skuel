"""
Principles Learning Service - Learning Path Integration
========================================================

Handles learning path integration for principles.

Responsibilities:
- Frame principle practice in learning context
- Assess principle-learning alignment
- Suggest learning-supported principles
- Track principle development through learning

Part of the PrinciplesService decomposition.
"""

from operator import itemgetter
from typing import Any

from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.curriculum.learning_path import LearningPath
from core.models.curriculum.learning_step import LearningStep
from core.models.curriculum.lp_position import LpPosition
from core.models.enums import Domain, EntityStatus
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.infrastructure.learning_alignment_helper import LearningAlignmentHelper
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


# ========================================================================
# CUSTOM SCORERS FOR PRINCIPLES DOMAIN
# ========================================================================


def _calculate_virtue_embodiment_score(
    principle: Principle, learning_position: LpPosition
) -> float:
    """
    Custom scorer for principle virtue embodiment.

    Discipline principles: progress x 0.8 (consistency weighted)
    Wisdom principles: min(0.9, progress x 0.6 + 0.3) (baseline knowledge valued)

    Args:
        principle: Principle to score
        learning_position: User's learning path position

    Returns:
        Float embodiment score (0.0-1.0)
    """
    if not learning_position.active_paths:
        return 0.0

    # Calculate average progress across all paths
    total_progress = 0.0
    for path in learning_position.active_paths:
        steps = path.steps if isinstance(path, LearningPath) else ()
        completed_steps = len([s for s in steps if s.uid in learning_position.completed_step_uids])
        total_steps = len(steps)
        path_progress = completed_steps / total_steps if total_steps > 0 else 0.0
        total_progress += path_progress

    avg_progress = total_progress / len(learning_position.active_paths)

    # Get principle category (Principle has .category property)
    principle_category = ""
    if isinstance(principle, Principle):
        principle_category = principle.category.lower() if principle.category else ""

    # Discipline: consistency-weighted
    if principle_category in {"personal", "health"}:
        return avg_progress * 0.8

    # Wisdom: baseline knowledge valued
    if principle_category in {"intellectual", "professional"}:
        return min(0.9, avg_progress * 0.6 + 0.3)

    # Default
    return avg_progress * 0.7


def _calculate_embodiment_data(
    principle: Principle, learning_position: LpPosition
) -> dict[str, Any]:
    """
    Calculate character development embodiment data.

    Returns:
        dict with virtue_category, embodiment_depth, character_development_stage
    """
    embodiment_score = _calculate_virtue_embodiment_score(principle, learning_position)

    category = "unknown"
    if isinstance(principle, Principle):
        category = principle.category if principle.category else "unknown"

    return {
        "virtue_category": category,
        "embodiment_depth": embodiment_score,
        "character_development_stage": (
            "embodied"
            if embodiment_score >= 0.7
            else "practicing"
            if embodiment_score >= 0.4
            else "learning"
        ),
    }


class PrinciplesLearningService(BaseService[PrinciplesOperations, Principle]):
    """
    Learning path integration for principles.

    Responsibilities:
    - Frame principle practice in learning context
    - Assess principle-learning alignment
    - Suggest learning-supported principles
    - Track principle development through learning


    Source Tag: "principles_learning_service_explicit"
    - Format: "principles_learning_service_explicit" for user-created relationships
    - Format: "principles_learning_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from principles_learning metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - Uses LearningAlignmentHelper with custom scorers

    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(EntityStatus.ARCHIVED.value,),
    )

    def __init__(self, backend: PrinciplesOperations) -> None:
        """
        Initialize principles learning service.

        Args:
            backend: Backend for principle operations
        """
        super().__init__(backend, "principles.learning")

        # Initialize LearningAlignmentHelper with custom scorers
        self.learning_helper = LearningAlignmentHelper[
            Principle, PrincipleDTO, PrincipleCreateRequest
        ](
            service=self,
            backend_get_method="get",
            backend_get_user_method="list_user_principles",
            backend_create_method="create",
            dto_class=PrincipleDTO,
            model_class=Principle,
            domain=Domain.PRINCIPLES,
            entity_name="principle",
            alignment_scorer=_calculate_virtue_embodiment_score,
            embodiment_scorer=_calculate_embodiment_data,
        )

    # ========================================================================
    # LEARNING CONTEXT ENHANCEMENT
    # ========================================================================

    async def frame_principle_practice_with_learning(
        self, principle_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        """
        Frame principle practice opportunities within learning context.

        This method applies knowledge-first thinking: How does the user's learning
        path position frame this principle practice?

        Args:
            principle_uid: Principle to frame,
            learning_position: User's learning path position context

        Returns:
            Result containing learning-contextual principle practice framework
        """
        # Get the principle (assuming we have access to principles)
        # For now, use the principle_uid as category
        principle_category = principle_uid.split(".")[-1] if "." in principle_uid else principle_uid

        # Get learning-contextualized practice framework
        practice_frame = learning_position.frame_principle_practice(principle_category)

        # Enhance with principle-specific analysis
        enhanced_frame = {
            "principle_uid": principle_uid,
            "principle_category": principle_category,
            "learning_applications": practice_frame["learning_applications"],
            "current_step_relevance": practice_frame["current_step_relevance"],
            "practice_opportunities": practice_frame["practice_opportunities"],
            "mastery_indicators": [],
            "learning_path_integration": [],
            "character_development_alignment": [],
        }

        # Add principle-specific mastery indicators
        for path in learning_position.active_paths:
            current_step = learning_position.current_steps.get(path.uid)
            if current_step:
                enhanced_frame["mastery_indicators"].append(
                    {
                        "path": path.name,
                        "indicator": f"Apply {principle_category} while mastering {current_step.title}",
                        "success_metric": f"Demonstrate {principle_category} in {current_step.title} application",
                    }
                )

        # Add learning path integration guidance
        for path in learning_position.active_paths:
            enhanced_frame["learning_path_integration"].append(
                {
                    "path": path.name,
                    "integration": f"Practice {principle_category} throughout {path.name} learning journey",
                    "milestone": f"Embody {principle_category} in {path.name} outcomes",
                }
            )

        # Character development alignment
        enhanced_frame["character_development_alignment"] = [
            f"Use {principle_category} to guide learning choices",
            f"Let {principle_category} shape learning approach",
            f"Develop {principle_category} through learning challenges",
        ]

        logger.info(
            f"Framed principle {principle_uid} practice with learning context: %d applications, %d paths",
            len(enhanced_frame["learning_applications"]),
            len(learning_position.active_paths),
        )

        return Result.ok(enhanced_frame)

    async def assess_principle_learning_alignment(
        self, principle_uid: str, learning_position: LpPosition
    ) -> Result[dict[str, Any]]:
        """
        Assess how well a principle aligns with current learning progression.

        Uses LearningAlignmentHelper with custom virtue embodiment scoring.

        Args:
            principle_uid: Principle to assess,
            learning_position: User's learning path position

        Returns:
            Result containing principle-learning alignment assessment with character development data
        """
        # Use LearningAlignmentHelper with custom scorers (consolidation)
        return await self.learning_helper.assess_learning_alignment(
            entity_uid=principle_uid, learning_position=learning_position
        )

    async def suggest_learning_supported_principles(
        self, learning_position: LpPosition, principle_category_filter: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest principles that are supported by current learning progression.

        Args:
            learning_position: User's learning path position,
            principle_category_filter: Optional category filter

        Returns:
            Result containing suggested principles with learning support
        """
        suggestions = []

        # Define principle categories that align with learning
        learning_principles = [
            "discipline",
            "persistence",
            "excellence",
            "growth_mindset",
            "curiosity",
            "wisdom",
            "patience",
            "humility",
            "courage",
        ]

        # Filter if requested
        if principle_category_filter:
            learning_principles = [
                p for p in learning_principles if principle_category_filter.lower() in p.lower()
            ]

        # Generate suggestions based on learning paths
        for principle_category in learning_principles:
            learning_support_score = 0.0
            supporting_paths = []

            # Assess support from each active path
            for path in learning_position.active_paths:
                path_support = 0.0

                # Domain-based support
                path_domain = str(path.domain.value)

                if principle_category in ["discipline", "persistence"] and path_domain in [
                    "learning",
                    "tech",
                ]:
                    path_support += 0.6
                elif principle_category in ["wisdom", "curiosity"] and path_domain == "learning":
                    path_support += 0.7
                elif principle_category in ["growth_mindset", "humility"]:
                    path_support += 0.5  # Always supported by learning

                # Current step context support
                current_step = learning_position.current_steps.get(path.uid)
                step_hours = (
                    current_step.estimated_hours
                    if isinstance(current_step, LearningStep | LearningPath)
                    else None
                )
                if current_step and (step_hours or 0) > 5:  # Substantial learning
                    path_support += 0.2

                if path_support > 0.4:
                    learning_support_score += path_support
                    supporting_paths.append(path.name)

            # Create suggestion if well-supported
            if learning_support_score > 0.5:
                suggestion = {
                    "principle_category": principle_category,
                    "principle_uid": f"principle.{principle_category}",
                    "learning_support_score": min(1.0, learning_support_score),
                    "supporting_paths": supporting_paths,
                    "practice_context": f"Develop {principle_category} through active learning paths",
                    "character_development": f"Build {principle_category} as core learning virtue",
                    "integration_approach": f"Practice {principle_category} daily in learning activities",
                }
                suggestions.append(suggestion)

        # Sort by learning support score
        suggestions.sort(key=itemgetter("learning_support_score"), reverse=True)

        logger.info(
            "Generated %d learning-supported principle suggestions from %d active paths",
            len(suggestions),
            len(learning_position.active_paths),
        )

        return Result.ok(suggestions[:8])  # Return top 8 suggestions

    async def track_principle_learning_development(
        self,
        principle_uid: str,
        learning_position: LpPosition,
        _practice_history: list[dict[str, Any]] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Track how principle development relates to learning path advancement.

        Args:
            principle_uid: Principle to track,
            learning_position: User's learning path position,
            practice_history: Optional history of principle practice

        Returns:
            Result containing principle development tracking in learning context
        """
        principle_category = principle_uid.split(".")[-1] if "." in principle_uid else principle_uid

        # Type-annotated lists for MyPy
        character_growth_indicators: list[str] = []
        learning_path_embodiment: list[dict[str, Any]] = []
        virtue_milestones: list[str] = []
        next_development_actions: list[str] = []

        development_tracking: dict[str, Any] = {
            "principle_uid": principle_uid,
            "principle_category": principle_category,
            "learning_development_score": 0.0,
            "character_growth_indicators": character_growth_indicators,
            "learning_path_embodiment": learning_path_embodiment,
            "virtue_milestones": virtue_milestones,
            "next_development_actions": next_development_actions,
        }

        # Assess development through learning paths
        total_embodiment = 0.0
        path_count = 0

        for path in learning_position.active_paths:
            path_embodiment = 0.0

            # Check how principle is embodied in path progression
            steps = path.steps if isinstance(path, LearningPath) else ()
            completed_steps = len(
                [s for s in steps if s.uid in learning_position.completed_step_uids]
            )
            total_steps = len(steps)
            path_progress = completed_steps / total_steps if total_steps > 0 else 0.0

            # Principle-specific embodiment scoring
            if principle_category.lower() in ["discipline", "persistence"]:
                path_embodiment = path_progress * 0.8  # High correlation with completion
            elif principle_category.lower() in ["wisdom", "humility"]:
                path_embodiment = min(0.9, path_progress * 0.6 + 0.3)  # Growth through learning
            else:
                path_embodiment = path_progress * 0.5

            if path_embodiment > 0.3:
                path_count += 1
                total_embodiment += path_embodiment

                learning_path_embodiment.append(
                    {
                        "path": path.name,
                        "embodiment_score": path_embodiment,
                        "progress": path_progress,
                        "development_evidence": f"Demonstrating {principle_category} through {path.name} progression",
                    }
                )

        # Calculate overall development score
        if path_count > 0:
            development_tracking["learning_development_score"] = total_embodiment / path_count

        # Character growth indicators
        development_tracking["character_growth_indicators"] = [
            f"Consistent practice of {principle_category} in learning contexts",
            f"Growth in {principle_category} through learning challenges",
            f"Integration of {principle_category} into learning identity",
        ]

        # Virtue milestones (type-safe comparisons)
        development_score = float(development_tracking["learning_development_score"])
        if development_score > 0.8:
            virtue_milestones.append(f"Strong embodiment of {principle_category} through learning")
        elif development_score > 0.6:
            virtue_milestones.append(f"Growing manifestation of {principle_category} in learning")
        else:
            virtue_milestones.append(f"Foundational development of {principle_category} beginning")

        # Next development actions
        development_tracking["next_development_actions"] = [
            f"Continue practicing {principle_category} in daily learning activities",
            f"Reflect on how {principle_category} shapes learning approach",
            f"Seek opportunities to deepen {principle_category} through learning challenges",
        ]

        return Result.ok(development_tracking)
