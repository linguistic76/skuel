"""
Evaluation Engine — Structured Assessment of Learner Responses (Skeleton)
==========================================================================

Interface for structured evaluation of learner responses against learning
objectives. The contract is defined here; full implementation is deferred
until curriculum content with structured objectives exists (Phase 6).

The evaluation engine will be called after the learner responds to an
ASSESS_UNDERSTANDING or PROBE_DEEPER move, comparing their response
against the evaluation rubric from the SocraticMove.

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.utils.result_simplified import Result


@dataclass(frozen=True)
class EvaluationResult:
    """Result of evaluating a learner's response against learning objectives.

    Produced by EvaluationEngine.evaluate_response(). Consumed by the
    Socratic pipeline to inform the next pedagogical move.
    """

    objectives_demonstrated: tuple[str, ...] = ()
    objectives_missed: tuple[str, ...] = ()
    depth_achieved: str = "surface"  # surface | functional | deep
    follow_up_suggestion: str | None = None


class EvaluationEngine:
    """Evaluate learner responses against structured learning objectives.

    Skeleton implementation — returns a default EvaluationResult. Full
    implementation requires curriculum content with structured objectives
    (StructuredLearningObjective with assessment_type, evidence_markers,
    depth_levels).
    """

    async def evaluate_response(
        self,
        user_response: str,
        learning_objectives: tuple[str, ...],
        article_content: str,
    ) -> Result[EvaluationResult]:
        """Evaluate a learner's response against learning objectives.

        Args:
            user_response: The learner's text response to a Socratic question.
            learning_objectives: String learning objectives from the Article.
            article_content: The Article content to check understanding against.

        Returns:
            Result[EvaluationResult]: Assessment of which objectives were
                demonstrated, which were missed, and suggested follow-up.
        """
        # Skeleton: return a default result indicating evaluation is not yet
        # implemented. The pipeline can check depth_achieved == "surface" and
        # follow_up_suggestion to know this is a placeholder.
        return Result.ok(
            EvaluationResult(
                objectives_demonstrated=(),
                objectives_missed=learning_objectives,
                depth_achieved="surface",
                follow_up_suggestion=(
                    "Structured evaluation not yet available. Continue with Socratic dialogue."
                ),
            )
        )
