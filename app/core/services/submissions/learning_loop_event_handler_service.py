"""
Learning Loop Event Handler Service
=====================================

Handles event-driven reactive logic for the learning loop:
Exercise -> Submission -> Report -> RevisedExercise -> re-submission.

Fire-and-forget handlers that track submission iterations, feedback
turnaround times, and mastery velocity — persisting insights to InsightStore.

Mirrors the pattern used by the 6 Activity Domain event handler services
(TaskEventHandlerService, GoalEventHandlerService, etc.).

Responsibilities:
- Submission iteration tracking and classification
- Teacher feedback turnaround calibration (EMA on User node)
- Mastery velocity classification on approval
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import LearningLoop
from core.events.submission_events import (
    ReportSubmitted,
    SubmissionApproved,
    SubmissionCreated,
)
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import SubmissionsBackend
    from core.services.insight.insight_store import InsightStore


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _classify_iteration_count(count: int) -> str:
    """Classify a submission iteration count into a category.

    Args:
        count: Number of submissions for the same exercise by the same user.

    Returns:
        "first_attempt", "second_attempt", "persistent", or "extended_effort"
    """
    if count <= 1:
        return "first_attempt"
    if count == 2:
        return "second_attempt"
    if count < LearningLoop.EXTENDED_EFFORT_THRESHOLD:
        return "persistent"
    return "extended_effort"


def _classify_mastery_velocity(iterations: int, hours: float) -> str:
    """Classify mastery velocity based on iteration count and elapsed time.

    Args:
        iterations: Total submissions for the exercise.
        hours: Hours from first submission to approval.

    Returns:
        "quick_mastery", "standard", or "persistent_learner"
    """
    if iterations <= 2 and hours < LearningLoop.DEFAULT_FEEDBACK_HOURS:
        return "quick_mastery"
    if iterations >= LearningLoop.PERSISTENT_ITERATION_THRESHOLD:
        return "persistent_learner"
    return "standard"


def _is_feedback_anomaly(hours: float, ema_hours: float) -> tuple[bool, str]:
    """Check whether a feedback turnaround time is anomalous relative to EMA.

    Args:
        hours: Actual turnaround hours for this report.
        ema_hours: Current exponential moving average of turnaround hours.

    Returns:
        (is_anomaly, anomaly_type) where anomaly_type is "fast", "slow", or "".
    """
    if ema_hours <= 0:
        return False, ""
    ratio = hours / ema_hours
    if ratio < LearningLoop.FEEDBACK_FAST_RATIO:
        return True, "fast"
    if ratio > LearningLoop.FEEDBACK_SLOW_RATIO:
        return True, "slow"
    return False, ""


class LearningLoopEventHandlerService:
    """Event-driven handlers for learning loop events.

    Fire-and-forget handlers that track submission iterations, teacher
    feedback turnaround, and mastery velocity.

    Handles:
    - SubmissionCreated: Iteration counting and classification
    - ReportSubmitted: Feedback turnaround calibration and anomaly detection
    - SubmissionApproved: Mastery velocity classification
    """

    def __init__(
        self,
        backend: SubmissionsBackend,
        insight_store: InsightStore | None = None,
    ) -> None:
        self.backend = backend
        self.insight_store = insight_store
        self.logger = get_logger("skuel.services.submissions.learning_loop_handler")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_submission_created(self, event: SubmissionCreated) -> None:
        """Handle new submission with iteration tracking.

        Counts how many times a user has submitted against the same exercise.
        Persists LEARNING_PROGRESS insight on 2nd+ attempt to capture persistence.

        Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # Guard: only track exercise-linked submissions
            if not event.fulfills_exercise_uid:
                return

            count_result = await self.backend.count_submissions_for_exercise(
                event.user_uid, event.fulfills_exercise_uid
            )
            if count_result.is_error:
                self.logger.warning(f"Failed to count submissions: {count_result.error}")
                return

            count = count_result.value
            classification = _classify_iteration_count(count)

            self.logger.info(
                f"Submission iteration: {classification} (count={count})",
                extra={
                    "submission_uid": event.submission_uid,
                    "user_uid": event.user_uid,
                    "exercise_uid": event.fulfills_exercise_uid,
                    "iteration_count": count,
                    "classification": classification,
                    "event_type": "learning_loop.submission_iteration",
                },
            )

            # Persist insight for 2nd+ attempt (first attempt is unremarkable)
            if count >= 2 and self.insight_store:
                impact = (
                    InsightImpact.HIGH
                    if count >= LearningLoop.EXTENDED_EFFORT_THRESHOLD
                    else InsightImpact.MEDIUM
                )
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.LEARNING_PROGRESS, event.submission_uid
                    ),
                    user_uid=event.user_uid,
                    insight_type=InsightType.LEARNING_PROGRESS,
                    domain="submissions",
                    title=f"Submission Iteration #{count}",
                    description=(
                        f"Student has submitted {count} times for the same exercise. "
                        f"Classification: {classification}."
                    ),
                    confidence=0.9,
                    impact=impact,
                    entity_uid=event.submission_uid,
                    supporting_data={
                        "exercise_uid": event.fulfills_exercise_uid,
                        "iteration_count": count,
                        "classification": classification,
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist iteration insight: {create_result.error}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling submission created: {e}",
                extra={
                    "submission_uid": event.submission_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_report_submitted(self, event: ReportSubmitted) -> None:
        """Handle teacher feedback with turnaround calibration.

        Computes turnaround hours from submission creation to report.
        Updates teacher's feedback EMA on the User node.
        Detects anomalously fast or slow turnaround times.

        Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # Get submission created_at to compute turnaround
            sub_result = await self.backend.get(event.submission_uid)
            if sub_result.is_error or sub_result.value is None:
                self.logger.warning(
                    f"Submission not found for turnaround calc: {event.submission_uid}"
                )
                return

            submission = sub_result.value
            submission_created_at = getattr(submission, "created_at", None)
            if not submission_created_at:
                return

            # Parse created_at if it's a string
            if isinstance(submission_created_at, str):
                submission_created_at = datetime.fromisoformat(submission_created_at)

            turnaround_hours = (event.occurred_at - submission_created_at).total_seconds() / 3600.0

            self.logger.info(
                f"Feedback turnaround: {turnaround_hours:.1f}h",
                extra={
                    "submission_uid": event.submission_uid,
                    "teacher_uid": event.teacher_uid,
                    "student_uid": event.student_uid,
                    "turnaround_hours": turnaround_hours,
                    "event_type": "learning_loop.feedback_turnaround",
                },
            )

            # Update teacher's feedback EMA
            state_result = await self.backend.get_teacher_feedback_state(event.teacher_uid)
            if state_result.is_error:
                return

            state = state_result.value
            ema_hours = state.get("feedback_ema_hours") or LearningLoop.DEFAULT_FEEDBACK_HOURS
            sample_count = state.get("feedback_sample_count") or 0

            # EMA update
            alpha = LearningLoop.EMA_ALPHA_FEEDBACK
            new_ema = alpha * turnaround_hours + (1 - alpha) * ema_hours
            new_count = sample_count + 1

            await self.backend.update_teacher_feedback_state(
                event.teacher_uid,
                {
                    "feedback_ema_hours": new_ema,
                    "feedback_sample_count": new_count,
                    "feedback_updated_at": event.occurred_at.isoformat(),
                },
            )

            # Anomaly detection (only with enough samples)
            if new_count >= LearningLoop.MIN_SAMPLES_FEEDBACK and self.insight_store:
                is_anomaly, anomaly_type = _is_feedback_anomaly(turnaround_hours, new_ema)
                if is_anomaly:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.COMPLETION_PATTERN, event.report_uid
                        ),
                        user_uid=event.teacher_uid,
                        insight_type=InsightType.COMPLETION_PATTERN,
                        domain="submissions",
                        title=f"Feedback Turnaround Anomaly ({anomaly_type})",
                        description=(
                            f"Teacher feedback took {turnaround_hours:.1f}h vs "
                            f"EMA of {new_ema:.1f}h ({anomaly_type} anomaly)."
                        ),
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=event.report_uid,
                        supporting_data={
                            "turnaround_hours": turnaround_hours,
                            "ema_hours": new_ema,
                            "anomaly_type": anomaly_type,
                            "sample_count": new_count,
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist feedback anomaly insight: {create_result.error}"
                        )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling report submitted: {e}",
                extra={
                    "submission_uid": event.submission_uid,
                    "teacher_uid": event.teacher_uid,
                    "error": str(e),
                },
            )

    async def handle_submission_approved(self, event: SubmissionApproved) -> None:
        """Handle submission approval with mastery velocity classification.

        Looks up the exercise, counts iterations, and classifies how quickly
        the student achieved mastery. Persists MASTERY_ACHIEVED or
        LEARNING_PROGRESS insight.

        Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # Guard: skip if no KU mastery was achieved
            if event.mastered_ku_count == 0:
                return

            # Look up exercise for this submission
            exercise_result = await self.backend.get_exercise_for_submission(event.submission_uid)
            if exercise_result.is_error or not exercise_result.value:
                self.logger.debug(
                    f"No exercise found for submission {event.submission_uid}, skipping velocity calc"
                )
                return

            exercise_uid = exercise_result.value

            # Count total iterations
            count_result = await self.backend.count_submissions_for_exercise(
                event.student_uid, exercise_uid
            )
            if count_result.is_error:
                return
            iterations = count_result.value

            # Get first submission time for velocity calculation
            first_result = await self.backend.get_first_submission_for_exercise(
                event.student_uid, exercise_uid
            )
            if first_result.is_error or not first_result.value:
                return

            first_created = first_result.value.get("created_at")
            if not first_created:
                return

            if isinstance(first_created, str):
                first_created = datetime.fromisoformat(first_created)

            hours = (event.occurred_at - first_created).total_seconds() / 3600.0
            velocity = _classify_mastery_velocity(iterations, hours)

            self.logger.info(
                f"Mastery velocity: {velocity} (iterations={iterations}, hours={hours:.1f})",
                extra={
                    "submission_uid": event.submission_uid,
                    "student_uid": event.student_uid,
                    "exercise_uid": exercise_uid,
                    "iterations": iterations,
                    "hours": hours,
                    "velocity": velocity,
                    "mastered_ku_count": event.mastered_ku_count,
                    "event_type": "learning_loop.mastery_velocity",
                },
            )

            # Persist insight
            if self.insight_store:
                if velocity == "quick_mastery":
                    insight_type = InsightType.MASTERY_ACHIEVED
                    impact = InsightImpact.HIGH
                    title = "Quick Mastery Achieved"
                    description = (
                        f"Student mastered {event.mastered_ku_count} KU(s) in "
                        f"{iterations} attempt(s) over {hours:.1f}h."
                    )
                else:
                    insight_type = InsightType.LEARNING_PROGRESS
                    impact = (
                        InsightImpact.HIGH
                        if velocity == "persistent_learner"
                        else InsightImpact.MEDIUM
                    )
                    title = f"Mastery via Persistence ({iterations} attempts)"
                    description = (
                        f"Student mastered {event.mastered_ku_count} KU(s) after "
                        f"{iterations} attempt(s) over {hours:.1f}h. "
                        f"Classification: {velocity}."
                    )

                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(insight_type, event.submission_uid),
                    user_uid=event.student_uid,
                    insight_type=insight_type,
                    domain="submissions",
                    title=title,
                    description=description,
                    confidence=0.85,
                    impact=impact,
                    entity_uid=event.submission_uid,
                    supporting_data={
                        "exercise_uid": exercise_uid,
                        "iterations": iterations,
                        "hours": hours,
                        "velocity": velocity,
                        "mastered_ku_count": event.mastered_ku_count,
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist mastery velocity insight: {create_result.error}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling submission approved: {e}",
                extra={
                    "submission_uid": event.submission_uid,
                    "student_uid": event.student_uid,
                    "error": str(e),
                },
            )
