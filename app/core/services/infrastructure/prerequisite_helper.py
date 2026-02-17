"""
Prerequisite Helper - Unified Prerequisite Checking
====================================================

Consolidates duplicate prerequisite checking logic from:
- TasksPlanningService._calculate_readiness_score()
- TasksSchedulingService._validate_task_prerequisites()

Provides both scoring (0.0-1.0) and validation (Result) interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


# Default mastery threshold for "mastered" knowledge
DEFAULT_MASTERY_THRESHOLD: float = 0.7


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


class PrerequisiteHelper:
    """
    Unified prerequisite checking for planning and scheduling services.

    Usage:
        # For scoring (Planning)
        result = PrerequisiteHelper.check_prerequisites(
            required_knowledge_uids=["ku.python"],
            required_task_uids=["task.setup"],
            context=user_context,
        )
        score = result.score  # 0.0-1.0

        # For validation (Scheduling)
        validation = PrerequisiteHelper.validate_prerequisites(
            required_knowledge_uids=["ku.python"],
            required_task_uids=["task.setup"],
            context=user_context,
        )
        if validation.is_error:
            return validation  # Propagate error
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
    def validate_prerequisites(
        required_knowledge_uids: list[str] | None,
        required_task_uids: list[str] | None,
        context: UserContext | None,
        mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD,
    ) -> Result[None]:
        """
        Validate prerequisites - returns Result for use in creation flows.

        This wraps check_prerequisites() for scheduling/creation validation.

        Args:
            required_knowledge_uids: Knowledge UIDs that must be mastered (or None)
            required_task_uids: Task UIDs that must be completed (or None)
            context: User context (if None, validation is skipped)
            mastery_threshold: Minimum mastery level (default 0.7)

        Returns:
            Result.ok(None) if valid, Result.fail() with missing prerequisites
        """
        # Skip validation if no context provided
        if context is None:
            return Result.ok(None)

        # Normalize None to empty lists
        knowledge_uids = required_knowledge_uids or []
        task_uids = required_task_uids or []

        # No prerequisites = valid
        if not knowledge_uids and not task_uids:
            return Result.ok(None)

        result = PrerequisiteHelper.check_prerequisites(
            required_knowledge_uids=knowledge_uids,
            required_task_uids=task_uids,
            context=context,
            mastery_threshold=mastery_threshold,
        )

        if result.is_ready:
            return Result.ok(None)

        # Build error message
        errors: list[str] = []
        if result.missing_knowledge:
            errors.append(f"Missing prerequisite knowledge: {', '.join(result.missing_knowledge)}")
        if result.missing_tasks:
            errors.append(f"Missing prerequisite tasks: {', '.join(result.missing_tasks)}")

        return Result.fail(Errors.validation("; ".join(errors)))

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
        result = PrerequisiteHelper.check_prerequisites(
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
        result = PrerequisiteHelper.check_prerequisites(
            required_knowledge_uids=required_knowledge_uids,
            required_task_uids=required_task_uids,
            context=context,
            max_blocking_reasons=max_reasons,
        )
        return list(result.blocking_reasons)
