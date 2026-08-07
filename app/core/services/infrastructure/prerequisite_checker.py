"""
Prerequisite Checker - Unified Prerequisite Checking
=====================================================

Consolidates duplicate prerequisite checking logic from:
- TasksPlanningService._calculate_readiness_score()
- TasksSchedulingService._validate_task_prerequisites()

Provides both scoring (0.0-1.0) and validation (Result) interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


# Default mastery threshold for "mastered" knowledge
DEFAULT_MASTERY_THRESHOLD: float = 0.7

# Default estimate of preparation effort per unmet knowledge requirement (hours).
LEARNING_HOURS_PER_KNOWLEDGE_AREA: int = 2


class KnowledgeRequirementsBlock(TypedDict):
    """Required-vs-mastered knowledge breakdown for a learning-requirements payload."""

    required_knowledge: list[dict[str, str]]
    mastered_knowledge: list[dict[str, str]]
    knowledge_gaps: list[dict[str, str]]
    total_required: int
    total_mastered: int
    mastery_percentage: float


class LearningPathsBlock(TypedDict):
    """Available / recommended learning paths and an effort estimate."""

    available_paths: list[dict[str, str]]
    recommended_path: dict[str, str] | None
    estimated_learning_time: int


class LearningAnalysisBlock(TypedDict):
    """Boolean readiness flags derived from the requirement/mastery split."""

    ready_to_start: bool
    has_prerequisites: bool
    learning_in_progress: bool
    knowledge_complete: bool


class LearningRequirements(TypedDict):
    """Stable shape returned by :func:`build_learning_requirements` (JSON-safe)."""

    knowledge_requirements: KnowledgeRequirementsBlock
    learning_paths: LearningPathsBlock
    learning_analysis: LearningAnalysisBlock


@dataclass(frozen=True)
class PrerequisiteResult:
    """
    Result of prerequisite check with both score and validation info.

    Attributes:
        score: Readiness score (0.0-1.0) - percentage of prerequisites met
        is_ready: True if score >= threshold (default 0.7)
        missing_knowledge: List of knowledge UIDs not yet mastered
        missing_tasks: List of task UIDs not yet completed
        blocking_reasons: Human-readable blocking reasons (max 3)
    """

    score: float
    is_ready: bool
    missing_knowledge: tuple[str, ...]
    missing_tasks: tuple[str, ...]
    blocking_reasons: tuple[str, ...]

    @property
    def is_blocked(self) -> bool:
        """True if any prerequisites are missing."""
        return not self.is_ready


class PrerequisiteChecker:
    """
    Unified prerequisite checking for planning and scheduling services.

    Usage:
        # For scoring (Planning)
        result = PrerequisiteChecker.check_prerequisites(
            required_knowledge_uids=["ku.python"],
            required_task_uids=["task.setup"],
            context=user_context,
        )
        score = result.score  # 0.0-1.0
    """

    @staticmethod
    def check_prerequisites(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
        max_blocking_reasons: int = 3,
    ) -> PrerequisiteResult:
        """
        Check prerequisites and return detailed result with score.

        This is the core method - both scoring and validation use this.

        Args:
            required_knowledge_uids: Knowledge UIDs that must be mastered
            required_task_uids: Task UIDs that must be completed
            context: User context with mastery and completion data
            mastery_threshold: Minimum mastery level to count as "met" (default 0.7)
            max_blocking_reasons: Maximum blocking reasons to return

        Returns:
            PrerequisiteResult with score, missing items, and blocking reasons
        """
        total = len(required_knowledge_uids) + len(required_task_uids)

        # No prerequisites = fully ready
        if total == 0:
            return PrerequisiteResult(
                score=1.0,
                is_ready=True,
                missing_knowledge=(),
                missing_tasks=(),
                blocking_reasons=(),
            )

        met = 0
        missing_knowledge: list[str] = []
        missing_tasks: list[str] = []
        blocking_reasons: list[str] = []

        # Check knowledge prerequisites
        for ku_uid in required_knowledge_uids:
            mastery = context.knowledge_mastery.get(ku_uid, 0.0)
            if mastery >= mastery_threshold:
                met += 1
            else:
                missing_knowledge.append(ku_uid)
                if len(blocking_reasons) < max_blocking_reasons:
                    blocking_reasons.append(f"Missing knowledge: {ku_uid} ({mastery:.0%} mastery)")

        # Check task prerequisites
        for task_uid in required_task_uids:
            if task_uid in context.completed_task_uids:
                met += 1
            else:
                missing_tasks.append(task_uid)
                if len(blocking_reasons) < max_blocking_reasons:
                    blocking_reasons.append(f"Incomplete prerequisite: {task_uid}")

        score = met / total
        is_ready = score >= mastery_threshold

        return PrerequisiteResult(
            score=score,
            is_ready=is_ready,
            missing_knowledge=tuple(missing_knowledge),
            missing_tasks=tuple(missing_tasks),
            blocking_reasons=tuple(blocking_reasons),
        )

    @staticmethod
    def calculate_readiness_score(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
    ) -> float:
        """
        Calculate readiness score (0.0-1.0) based on prerequisites met.

        Convenience method that returns just the score.

        Args:
            required_knowledge_uids: Knowledge UIDs that must be mastered
            required_task_uids: Task UIDs that must be completed
            context: User context with mastery and completion data
            mastery_threshold: Minimum mastery level (default 0.7)

        Returns:
            Float between 0.0 and 1.0 representing percentage of prerequisites met
        """
        result = PrerequisiteChecker.check_prerequisites(
            required_knowledge_uids=required_knowledge_uids,
            required_task_uids=required_task_uids,
            context=context,
            mastery_threshold=mastery_threshold,
        )
        return result.score

    @staticmethod
    def identify_blocking_reasons(
        required_knowledge_uids: list[str],
        required_task_uids: list[str],
        context: UserContext,
        max_reasons: int = 3,
    ) -> list[str]:
        """
        Identify reasons blocking engagement.

        Convenience method that returns just the blocking reasons.

        Args:
            required_knowledge_uids: Knowledge UIDs that must be mastered
            required_task_uids: Task UIDs that must be completed
            context: User context with mastery and completion data
            max_reasons: Maximum number of reasons to return

        Returns:
            List of human-readable blocking reasons
        """
        result = PrerequisiteChecker.check_prerequisites(
            required_knowledge_uids=required_knowledge_uids,
            required_task_uids=required_task_uids,
            context=context,
            max_blocking_reasons=max_reasons,
        )
        return list(result.blocking_reasons)


def build_learning_requirements(
    required_knowledge_uids: list[str],
    learning_path_uids: list[str],
    context: UserContext | None = None,
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
) -> LearningRequirements:
    """Build a domain-agnostic learning-requirements / readiness payload.

    Shared by the activity domains that carry a ``REQUIRES_KNOWLEDGE`` edge (Tasks,
    Goals): given the knowledge a domain entity requires and the learning paths that
    cover it, produce the ``knowledge_requirements`` / ``learning_paths`` /
    ``learning_analysis`` blocks both lenses surface.

    The mastery split is delegated to :meth:`PrerequisiteChecker.check_prerequisites`
    (same 0.7 readiness threshold the planning/scheduling readiness already uses) so
    ``knowledge_gaps`` / ``ready_to_start`` reflect what the user has actually mastered
    rather than a stub.

    When ``context`` is ``None`` (mastery unknown — no user in scope), every requirement
    is treated as an open gap: ``mastered_knowledge`` is empty and ``ready_to_start`` is
    ``False`` whenever there are requirements. This reproduces the pre-mastery behaviour
    of the goal/task lenses exactly, so context-free callers are unchanged.

    Args:
        required_knowledge_uids: KU UIDs the entity requires (already deduped by the
            typed cross-domain reader — order preserved).
        learning_path_uids: Learning-path UIDs available for the required knowledge.
        context: User context carrying ``knowledge_mastery`` (or ``None`` if unknown).
        mastery_threshold: Minimum mastery to count a requirement as met (default 0.7).

    Returns:
        A dict with ``knowledge_requirements``, ``learning_paths`` and
        ``learning_analysis`` blocks (all primitives — JSON-serializable).
    """
    if context is not None and required_knowledge_uids:
        check = PrerequisiteChecker.check_prerequisites(
            required_knowledge_uids=required_knowledge_uids,
            required_task_uids=[],
            context=context,
            mastery_threshold=mastery_threshold,
        )
        gap_uids = set(check.missing_knowledge)
        knowledge_gaps = [uid for uid in required_knowledge_uids if uid in gap_uids]
        mastered = [uid for uid in required_knowledge_uids if uid not in gap_uids]
    else:
        # Mastery unknown → treat every requirement as an open gap.
        knowledge_gaps = list(required_knowledge_uids)
        mastered = []

    total_required = len(required_knowledge_uids)
    total_mastered = len(mastered)
    mastery_percentage = (total_mastered / total_required * 100) if total_required > 0 else 100.0
    recommended_path = {"uid": learning_path_uids[0]} if learning_path_uids else None

    return {
        "knowledge_requirements": {
            "required_knowledge": [{"uid": uid} for uid in required_knowledge_uids],
            "mastered_knowledge": [{"uid": uid} for uid in mastered],
            "knowledge_gaps": [{"uid": uid} for uid in knowledge_gaps],
            "total_required": total_required,
            "total_mastered": total_mastered,
            "mastery_percentage": mastery_percentage,
        },
        "learning_paths": {
            "available_paths": [{"uid": uid} for uid in learning_path_uids],
            "recommended_path": recommended_path,
            "estimated_learning_time": len(knowledge_gaps) * LEARNING_HOURS_PER_KNOWLEDGE_AREA,
        },
        "learning_analysis": {
            "ready_to_start": len(knowledge_gaps) == 0,
            "has_prerequisites": total_required > 0,
            "learning_in_progress": len(learning_path_uids) > 0,
            "knowledge_complete": mastery_percentage >= 100,
        },
    }
