"""
Simple Learning Path Position Context
====================================

Leverages existing LearningPath and LearningStep models to provide learning path position context
for service operations. This enables knowledge-first operations where learning path progression
guides task, habit, goal, and other domain operations.

Design Principle: "How does the user's learning path position frame this operation?"
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.lp.lp import LearningPath
from core.models.ls import LearningStep
from core.models.shared_enums import Domain


@dataclass
class LpPosition:
    """
    Simple learning path position using existing LearningPath models.

    This context frames operations by understanding where the user is
    in their learning journey using existing domain models.
    """

    # Core Learning State (using existing models)
    active_paths: list[LearningPath]  # User's current learning paths
    current_steps: dict[str, LearningStep]  # Current step in each path (path_uid -> step)
    completed_step_uids: set[str]  # All completed step UIDs across paths
    next_recommended: list[str]  # Next step UIDs ready to start

    # Simple Context Data
    user_uid: str
    generated_at: datetime
    readiness_scores: dict[str, float]  # step_uid -> readiness (0.0-1.0)

    def assess_task_relevance(self, task_domain: str, task_knowledge_uids: list[str]) -> float:
        """
        Simple learning path relevance assessment for tasks.

        Args:
            task_domain: Domain of the task
            task_knowledge_uids: Knowledge UIDs the task applies

        Returns:
            Relevance score (0.0-1.0) based on learning path position
        """
        if not task_knowledge_uids:
            return 0.1  # Low relevance for tasks without knowledge connections

        relevance_score = 0.0
        relevance_factors = 0

        # Check relevance across all active learning paths
        for path in self.active_paths:
            # Domain alignment
            if str(path.domain.value) == task_domain:
                relevance_score += 0.3
                relevance_factors += 1

            # Knowledge alignment with current and next steps
            current_step = self.current_steps.get(path.uid)
            if current_step:
                # Check if task knowledge matches current step (iterate over tuple)
                for ku_uid in current_step.primary_knowledge_uids:
                    if ku_uid in task_knowledge_uids:
                        relevance_score += 0.5  # High relevance for current step knowledge
                        relevance_factors += 1
                        break  # Count each step once

                # Check next steps for preparatory relevance
                next_step = path.get_next_step(self.completed_step_uids)
                if next_step:
                    for ku_uid in next_step.primary_knowledge_uids:
                        if ku_uid in task_knowledge_uids:
                            relevance_score += 0.4  # Good relevance for next step preparation
                            relevance_factors += 1
                            break  # Count each step once

        # Return average relevance (0.0 if no factors found)
        return relevance_score / relevance_factors if relevance_factors > 0 else 0.0

    def suggest_habit_alignment(self, habit_category: str) -> list[str]:
        """
        Simple habit suggestions for learning path alignment.

        Args:
            habit_category: Category of habit being created

        Returns:
            List of learning-aligned habit suggestions
        """
        suggestions = []

        # Domain-specific learning habits
        active_domains = set(path.domain for path in self.active_paths)

        for domain in active_domains:
            if domain == Domain.TECH and habit_category in ["study", "practice", "development"]:
                suggestions.extend(
                    [
                        "Daily coding practice (15 minutes)",
                        "Read technical documentation",
                        "Review completed coding tasks",
                    ]
                )
            elif domain == Domain.LEARNING and habit_category in ["study", "learning", "education"]:
                suggestions.extend(
                    [
                        "Complete one learning step daily",
                        "Review previous learning concepts",
                        "Practice knowledge application",
                    ]
                )
            elif domain == Domain.HEALTH and habit_category in ["health", "wellness", "exercise"]:
                suggestions.extend(
                    [
                        "Study health concepts (10 minutes)",
                        "Practice mindful learning breaks",
                        "Track learning energy levels",
                    ]
                )

        # Learning path specific suggestions
        for path in self.active_paths:
            current_step = self.current_steps.get(path.uid)
            if current_step:
                suggestions.append(f"Practice {path.name} concepts daily")
                # Use first primary knowledge UID for suggestion
                if current_step.primary_knowledge_uids:
                    ku_uid = current_step.primary_knowledge_uids[0]
                    suggestions.append(f"Review {ku_uid} mastery")

        return list(set(suggestions))  # Remove duplicates

    def assess_goal_alignment(self, goal_description: str, goal_domain: str) -> dict[str, Any]:
        """
        Simple goal alignment assessment with learning paths.

        Args:
            goal_description: Description of the goal
            goal_domain: Domain of the goal

        Returns:
            Alignment assessment with learning path context
        """
        # Type-annotated lists for MyPy
        supporting_paths: list[str] = []
        prerequisite_steps: list[str] = []
        outcome_alignment: list[str] = []

        alignment = {
            "learning_path_support": 0.0,
            "recommended_timeline": "3 months",  # Default
            "supporting_paths": supporting_paths,
            "prerequisite_steps": prerequisite_steps,
            "outcome_alignment": outcome_alignment,
        }

        # Check alignment with active learning paths
        for path in self.active_paths:
            path_support = 0.0

            # Domain alignment
            if str(path.domain.value) == goal_domain:
                path_support += 0.4
                supporting_paths.append(path.uid)

                # Timeline estimation based on remaining steps
                len([s for s in path.steps if s.uid not in self.completed_step_uids])
                estimated_hours = sum(
                    s.estimated_hours for s in path.steps if s.uid not in self.completed_step_uids
                )

                if estimated_hours > 0:
                    weeks = max(1, int(estimated_hours / 10))  # 10 hours per week assumption
                    alignment["recommended_timeline"] = f"{weeks} weeks"

            # Outcome alignment
            for outcome in path.outcomes:
                if any(word in goal_description.lower() for word in outcome.lower().split()):
                    path_support += 0.2
                    outcome_alignment.append(outcome)

            current_support = float(alignment["learning_path_support"])
            alignment["learning_path_support"] = max(current_support, path_support)

        return alignment

    def frame_principle_practice(self, principle_category: str) -> dict[str, Any]:
        """
        Frame principle practice opportunities within learning context.

        Args:
            principle_category: Category of principle being practiced

        Returns:
            Learning-contextual principle practice framework
        """
        practice_frame = {
            "learning_applications": [],
            "current_step_relevance": [],
            "practice_opportunities": [],
            "mastery_indicators": [],
        }

        # Connect principles to current learning context
        for path in self.active_paths:
            current_step = self.current_steps.get(path.uid)
            if current_step:
                # Learning applications (use first primary knowledge UID)
                ku_uid = (
                    current_step.primary_knowledge_uids[0]
                    if current_step.primary_knowledge_uids
                    else "this step"
                )
                practice_frame["learning_applications"].append(
                    {
                        "path": path.name,
                        "step": ku_uid,
                        "application": f"Apply {principle_category} while learning {ku_uid}",
                    }
                )

                # Current step relevance
                if principle_category.lower() in path.name.lower():
                    practice_frame["current_step_relevance"].append(
                        {
                            "path": path.name,
                            "relevance": "Direct principle practice in current learning",
                        }
                    )

        # Practice opportunities based on learning progression
        practice_frame["practice_opportunities"] = [
            f"Apply {principle_category} during daily learning sessions",
            f"Reflect on {principle_category} after completing learning steps",
            f"Use {principle_category} to guide learning path decisions",
        ]

        return practice_frame

    def suggest_choice_guidance(self, choice_description: str) -> dict[str, Any]:
        """
        Provide learning-path-informed choice guidance.

        Args:
            choice_description: Description of the choice being made

        Returns:
            Learning path contextual choice guidance
        """
        # Type-annotated lists for MyPy
        learning_path_implications: list[dict[str, Any]] = []
        prerequisite_considerations: list[str] = []

        guidance = {
            "learning_path_implications": learning_path_implications,
            "recommended_approach": "",
            "long_term_learning_impact": "",
            "prerequisite_considerations": prerequisite_considerations,
        }

        # Analyze choice impact on learning paths
        for path in self.active_paths:
            current_step = self.current_steps.get(path.uid)
            if current_step and any(
                word in choice_description.lower() for word in path.name.lower().split()
            ):
                # Use first primary knowledge UID
                ku_uid = (
                    current_step.primary_knowledge_uids[0]
                    if current_step.primary_knowledge_uids
                    else current_step.uid
                )
                learning_path_implications.append(
                    {
                        "path": path.name,
                        "impact": f"Choice may affect progression in {path.name}",
                        "current_step": ku_uid,
                    }
                )

        # Provide learning-informed recommendations
        if self.active_paths:
            primary_path = self.active_paths[0]  # Primary learning focus
            guidance["recommended_approach"] = (
                f"Consider alignment with {primary_path.name} learning objectives"
            )
            guidance["long_term_learning_impact"] = (
                "Evaluate how this choice supports your learning journey"
            )

        return guidance

    def get_learning_context_summary(self) -> dict[str, Any]:
        """
        Get a summary of current learning context for framing operations.

        Returns:
            Summary of learning path position for operation framing
        """
        return {
            "active_learning_paths": len(self.active_paths),
            "current_domains": list(set(str(path.domain.value) for path in self.active_paths)),
            "total_progress": len(self.completed_step_uids),
            "next_steps_available": len(self.next_recommended),
            "primary_focus": self.active_paths[0].name if self.active_paths else None,
            "learning_readiness": sum(self.readiness_scores.values()) / len(self.readiness_scores)
            if self.readiness_scores
            else 0.0,
        }


def create_lp_position(
    user_uid: str,
    active_paths: list[LearningPath],
    completed_step_uids: set[str],
    readiness_map: dict[str, bool] | None = None,
) -> LpPosition:
    """
    Factory function to create LpPosition from existing models.

    Args:
        user_uid: User identifier,
        active_paths: User's active learning paths,
        completed_step_uids: Set of completed step UIDs
        readiness_map: Optional map of step UIDs to readiness status.
                      If None, all steps assumed ready. Use LsRelationshipService.is_ready()
                      at service layer to populate this with real graph data.

    Returns:
        LpPosition instance for framing operations
    """
    # Determine current steps for each path
    current_steps = {}
    next_recommended = []
    readiness_scores = {}

    for path in active_paths:
        # Get current step (first incomplete step that's ready)
        for step in path.steps:
            if step.uid not in completed_step_uids:
                # Use readiness_map if provided, otherwise assume ready
                is_ready = readiness_map.get(step.uid, True) if readiness_map else True
                if is_ready:
                    current_steps[path.uid] = step
                    next_recommended.append(step.uid)
                    # Readiness scoring from map or default
                    readiness_scores[step.uid] = 1.0 if is_ready else 0.5
                    break

    return LpPosition(
        active_paths=active_paths,
        current_steps=current_steps,
        completed_step_uids=completed_step_uids,
        next_recommended=next_recommended,
        user_uid=user_uid,
        generated_at=datetime.now(),
        readiness_scores=readiness_scores,
    )
