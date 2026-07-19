"""
UserEntry Learning Loop Event Handler — ADR-054
===============================================

Fire-and-forget handlers that track UserEntry iterations, teacher
feedback turnaround calibration, and mastery velocity — persisting
insights to ``InsightStore``. Ported from
``LearningLoopEventHandlerService`` with event sources rewired onto
``UserEntryCreated`` / ``UserEntryApproved`` / ``ReportSubmitted`` from
``core/events/learning_loop_events.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from core.constants import LearningLoop
from core.events.learning_loop_events import ReportSubmitted, UserEntryApproved
from core.events.user_entry_events import UserEntryCreated
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.type_hints import EntityUID, UserUID
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_float, coerce_int

if TYPE_CHECKING:
    from core.services.insight.insight_store import InsightStore


def _classify_iteration_count(count: int) -> str:
    if count <= 1:
        return "first_attempt"
    if count == 2:
        return "second_attempt"
    if count < LearningLoop.EXTENDED_EFFORT_THRESHOLD:
        return "persistent"
    return "extended_effort"


def _classify_mastery_velocity(iterations: int, hours: float) -> str:
    if iterations <= 2 and hours < LearningLoop.DEFAULT_FEEDBACK_HOURS:
        return "quick_mastery"
    if iterations >= LearningLoop.PERSISTENT_ITERATION_THRESHOLD:
        return "persistent_learner"
    return "standard"


def _is_feedback_anomaly(hours: float, ema_hours: float) -> tuple[bool, str]:
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

    Handles:
    - UserEntryCreated: Iteration counting and classification
    - ReportSubmitted: Feedback turnaround calibration and anomaly detection
    - UserEntryApproved: Mastery velocity classification
    """

    def __init__(
        self,
        backend: UserEntryOperations,
        insight_store: InsightStore | None = None,
    ) -> None:
        self.backend = backend
        self.insight_store = insight_store
        self.logger = get_logger("skuel.services.user_entry.learning_loop_handler")

    async def handle_submission_created(self, event: UserEntryCreated) -> None:
        """Track UserEntry iterations against the same exercise.

        Fire-and-forget — errors are logged, never propagated. Name kept as
        ``handle_submission_created`` so external subscription wiring
        remains source-compatible.
        """
        try:
            if not event.fulfills_exercise_uid:
                return

            count_result = await self.backend.count_entries_for_exercise(
                event.user_uid, event.fulfills_exercise_uid
            )
            if count_result.is_error:
                self.logger.warning(f"Failed to count entries: {count_result.expect_error()}")
                return

            count = count_result.value
            classification = _classify_iteration_count(count)

            self.logger.info(
                f"UserEntry iteration: {classification} (count={count})",
                extra={
                    "entity_uid": event.entity_uid,
                    "user_uid": event.user_uid,
                    "exercise_uid": event.fulfills_exercise_uid,
                    "iteration_count": count,
                    "classification": classification,
                    "event_type": "learning_loop.user_entry_iteration",
                },
            )

            if count >= 2 and self.insight_store:
                impact = (
                    InsightImpact.HIGH
                    if count >= LearningLoop.EXTENDED_EFFORT_THRESHOLD
                    else InsightImpact.MEDIUM
                )
                insight = PersistedInsight(
                    uid=PersistedInsight.generate_uid(
                        InsightType.LEARNING_PROGRESS, EntityUID(event.entity_uid)
                    ),
                    user_uid=event.user_uid,
                    insight_type=InsightType.LEARNING_PROGRESS,
                    domain="user_entry",
                    title=f"UserEntry Iteration #{count}",
                    description=(
                        f"Student has submitted {count} times for the same exercise. "
                        f"Classification: {classification}."
                    ),
                    confidence=0.9,
                    impact=impact,
                    entity_uid=EntityUID(event.entity_uid),
                    supporting_data={
                        "exercise_uid": event.fulfills_exercise_uid,
                        "iteration_count": count,
                        "classification": classification,
                    },
                )
                create_result = await self.insight_store.create_insight(insight)
                if create_result.is_error:
                    self.logger.warning(
                        f"Failed to persist iteration insight: {create_result.expect_error()}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling user_entry created: {e}",
                extra={
                    "entity_uid": event.entity_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_report_submitted(self, event: ReportSubmitted) -> None:
        """Track teacher feedback turnaround calibration + anomaly detection."""
        try:
            sub_result = await self.backend.get(event.submission_uid)
            if sub_result.is_error or sub_result.value is None:
                self.logger.warning(
                    f"UserEntry not found for turnaround calc: {event.submission_uid}"
                )
                return

            entry = sub_result.value
            entry_created_at = getattr(entry, "created_at", None)
            if not entry_created_at:
                return

            if isinstance(entry_created_at, str):
                entry_created_at = datetime.fromisoformat(entry_created_at)

            turnaround_hours = (event.occurred_at - entry_created_at).total_seconds() / 3600.0

            self.logger.info(
                f"Feedback turnaround: {turnaround_hours:.1f}h",
                extra={
                    "entity_uid": event.submission_uid,
                    "teacher_uid": event.teacher_uid,
                    "student_uid": event.student_uid,
                    "turnaround_hours": turnaround_hours,
                    "event_type": "learning_loop.feedback_turnaround",
                },
            )

            state_result = await self.backend.get_teacher_feedback_state(event.teacher_uid)
            if state_result.is_error:
                return

            state = state_result.value
            ema_hours = coerce_float(
                state.get("feedback_ema_hours") or LearningLoop.DEFAULT_FEEDBACK_HOURS
            )
            sample_count = coerce_int(state.get("feedback_sample_count"))

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

            if new_count >= LearningLoop.MIN_SAMPLES_FEEDBACK and self.insight_store:
                is_anomaly, anomaly_type = _is_feedback_anomaly(turnaround_hours, new_ema)
                if is_anomaly:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.COMPLETION_PATTERN, EntityUID(event.report_uid)
                        ),
                        user_uid=UserUID(event.teacher_uid),
                        insight_type=InsightType.COMPLETION_PATTERN,
                        domain="user_entry",
                        title=f"Feedback Turnaround Anomaly ({anomaly_type})",
                        description=(
                            f"Teacher feedback took {turnaround_hours:.1f}h vs "
                            f"EMA of {new_ema:.1f}h ({anomaly_type} anomaly)."
                        ),
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=EntityUID(event.report_uid),
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
                            "Failed to persist feedback anomaly insight: "
                            f"{create_result.expect_error()}"
                        )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling report submitted: {e}",
                extra={
                    "entity_uid": event.submission_uid,
                    "teacher_uid": event.teacher_uid,
                    "error": str(e),
                },
            )

    async def handle_submission_approved(self, event: UserEntryApproved) -> None:
        """Classify mastery velocity on approval."""
        try:
            if event.mastered_ku_count == 0:
                return

            exercise_result = await self.backend.get_exercise_for_entry(event.entity_uid)
            if exercise_result.is_error or not exercise_result.value:
                self.logger.debug(
                    f"No exercise found for user_entry {event.entity_uid}, skipping velocity calc"
                )
                return

            exercise_uid = exercise_result.value

            count_result = await self.backend.count_entries_for_exercise(
                UserUID(event.student_uid), exercise_uid
            )
            if count_result.is_error:
                return
            iterations = count_result.value

            first_result = await self.backend.get_first_entry_for_exercise(
                UserUID(event.student_uid), exercise_uid
            )
            if first_result.is_error or not first_result.value:
                return

            first_created = first_result.value.get("created_at")
            if not first_created:
                return

            if isinstance(first_created, str):
                first_created_dt = datetime.fromisoformat(first_created)
            elif isinstance(first_created, datetime):
                first_created_dt = first_created
            else:
                return

            hours = (event.occurred_at - first_created_dt).total_seconds() / 3600.0
            velocity = _classify_mastery_velocity(iterations, hours)

            self.logger.info(
                f"Mastery velocity: {velocity} (iterations={iterations}, hours={hours:.1f})",
                extra={
                    "entity_uid": event.entity_uid,
                    "student_uid": event.student_uid,
                    "exercise_uid": exercise_uid,
                    "iterations": iterations,
                    "hours": hours,
                    "velocity": velocity,
                    "mastered_ku_count": event.mastered_ku_count,
                    "event_type": "learning_loop.mastery_velocity",
                },
            )

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
                    uid=PersistedInsight.generate_uid(insight_type, EntityUID(event.entity_uid)),
                    user_uid=UserUID(event.student_uid),
                    insight_type=insight_type,
                    domain="user_entry",
                    title=title,
                    description=description,
                    confidence=0.85,
                    impact=impact,
                    entity_uid=EntityUID(event.entity_uid),
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
                        "Failed to persist mastery velocity insight: "
                        f"{create_result.expect_error()}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling user_entry approved: {e}",
                extra={
                    "entity_uid": event.entity_uid,
                    "student_uid": event.student_uid,
                    "error": str(e),
                },
            )
