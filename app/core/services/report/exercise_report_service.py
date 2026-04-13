"""
Exercise Report Service
========================

Generates AI reports for submission entries using Exercises.

AI report creates a first-class EXERCISE_REPORT entity (processor_type=LLM),
symmetric with human teacher reports (processor_type=HUMAN). Both are stored
as EXERCISE_REPORT entities linked to the submission via REPORT_FOR.

The core educational loop:
    Exercise (instructions) + Submission (student work) → LLM → EXERCISE_REPORT entity

Following SKUEL principles:
- Transparent: User sees exact prompt sent to LLM
- Symmetric: AI report = same entity type as teacher report, processor_type differs
- Atomic: Entity creation + REPORT_FOR + SHARES_WITH in one transaction
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.learning_enums import AssessmentOutcome, MasteryImpact
from core.models.exercises.exercise import Exercise
from core.models.report.exercise_report import ExerciseReport
from core.models.submissions.submission import Submission
from core.models.type_hints import UserUID
from core.services.llm_caller import LLMCallerProtocol
from core.utils.exception_types import LLM_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.submissions_backend import SubmissionsBackend
    from core.ports.report_protocols import ExerciseReportBackendOperations
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.report.report_mastery_service import ReportMasteryService

logger = get_logger(__name__)


class ExerciseReportService:
    """
    Generates AI reports for submission entries using exercise instructions.

    Creates an EXERCISE_REPORT entity (processor_type=LLM) linked to the
    submission via REPORT_FOR — symmetric with teacher reports.

    Supports both OpenAI and Anthropic models.
    User selects which model to use via Exercise.model field.
    """

    def __init__(
        self,
        llm_caller: LLMCallerProtocol | None,
        backend: "ExerciseReportBackendOperations | None" = None,
        submissions_backend: "SubmissionsBackend | None" = None,
        ku_interaction_service: "PsMasteryService | None" = None,
        report_mastery_service: "ReportMasteryService | None" = None,
    ) -> None:
        """
        Initialize with LLM caller and domain backends.

        Args:
            llm_caller: Unified LLM caller for model-agnostic generation
            backend: The typed read facade for ExerciseReport — typed reads
                (``list_for_submission``, etc.) plus the mastery-loop scalar
                projection (``get_linked_ku_and_student``). Report *creation*
                is delegated to ``submissions_backend.create_report_node`` —
                the canonical path shared with teacher reports.
            submissions_backend: SubmissionsBackend — canonical report-node
                creator. Shared with TeacherReviewService so AI and teacher
                reports go through the same Cypher.
            ku_interaction_service: Optional — updates MASTERED relationships on linked Ku nodes
                after feedback is persisted, closing the mastery loop for PERSONAL scope
                exercises where no teacher approval step exists
            report_mastery_service: Optional — explicit mastery propagation service
        """
        self.llm_caller = llm_caller
        self.backend = backend
        self.submissions_backend = submissions_backend
        self.ku_interaction_service = ku_interaction_service
        self.report_mastery_service = report_mastery_service
        self.logger = logger

        available = []
        if self.llm_caller:
            available.append("LLMCaller")
        if self.submissions_backend:
            available.append("Neo4j")
        if self.ku_interaction_service:
            available.append("MasteryLoop")

        logger.info(f"ExerciseReportService initialized with: {', '.join(available)}")

    async def get_by_uid(self, uid: str) -> Result[ExerciseReport]:
        """Typed single-fetch for ExerciseReport by UID.

        Delegates to ExerciseReportBackend.get_by_uid and narrows a missing
        row to a not-found error so routes can use the standard
        ``require_found`` pattern.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "ExerciseReportBackend not configured",
                    operation="get_by_uid",
                )
            )
        result = await self.backend.get_by_uid(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="ExerciseReport", identifier=uid))
        return Result.ok(result.value)

    async def list_for_submission(self, submission_uid: str) -> Result[list[ExerciseReport]]:
        """List all reports attached to a submission (ASC by created_at).

        Delegates to ExerciseReportBackend.list_for_submission — typed
        end-to-end, no TypedDict projection, no mapping step. Both teacher
        (HUMAN) and AI (LLM) reports appear here, discriminated by
        ``ExerciseReport.processor_type``.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "ExerciseReportBackend not configured",
                    operation="list_for_submission",
                )
            )
        return await self.backend.list_for_submission(submission_uid)

    async def generate_report(
        self,
        entry: Submission,
        exercise: Exercise,
        user_uid: UserUID,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[ExerciseReport]:
        """
        Generate AI report for a submission entry using exercise instructions.

        Creates an EXERCISE_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via REPORT_FOR. The typed read path
        (list_for_submission) is the authoritative source for report content.

        Args:
            entry: Submission to analyze (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (teacher/admin — owns the entity)
            temperature: Sampling temperature (0-1, default 0.7)
            max_tokens: Maximum tokens to generate (default 4000)

        Returns:
            Result[ExerciseReport] containing the created EXERCISE_REPORT entity
        """
        try:
            if not self.llm_caller:
                return Result.fail(
                    Errors.system(
                        "LLM caller not configured (CORE intelligence tier)",
                        operation="generate_report",
                    )
                )
            if not exercise.is_valid():
                return Result.fail(
                    Errors.validation("Invalid exercise: missing required fields", field="exercise")
                )

            entry_content = entry.content or entry.processed_content or ""
            if not entry_content:
                return Result.fail(
                    Errors.validation("Submission has no content for report", field="content")
                )

            prompt = exercise.get_feedback_prompt(entry_content)

            self.logger.info(
                f"Generating report for entry {entry.uid} using exercise {exercise.uid}"
            )
            self.logger.debug(f"Model: {exercise.model}, Prompt length: {len(prompt)} chars")

            # Generate report text via LLM (routing handled by UnifiedLLMCaller)
            llm_result = await self.llm_caller.generate(
                prompt=prompt,
                model=exercise.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if llm_result.is_error:
                self.logger.error(f"AI service error: {llm_result.error}")
                return Result.fail(llm_result)

            feedback_text = llm_result.value
            self.logger.info(f"Report generated: {len(feedback_text)} chars")

            # Persist as EXERCISE_REPORT entity
            return await self._persist_report_entity(
                submission=entry,
                exercise=exercise,
                feedback_text=feedback_text,
                user_uid=user_uid,
            )

        except LLM_EXCEPTIONS as e:
            self.logger.error(f"LLM error generating report: {e}")
            return Result.fail(
                Errors.integration(
                    service="LLM",
                    operation="generate_report",
                    message=f"Report generation failed: {e!s}",
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Unexpected error generating report: {e}")
            return Result.fail(
                Errors.system(f"Report generation failed: {e!s}", operation="generate_report")
            )

    async def _persist_report_entity(
        self,
        submission: Submission,
        exercise: Exercise,
        feedback_text: str,
        user_uid: UserUID,
    ) -> Result[ExerciseReport]:
        """
        Persist AI report as an EXERCISE_REPORT entity in Neo4j.

        Delegates to ``SubmissionsBackend.create_report_node`` — the canonical
        report-creation path shared with teacher reports. Creates the entity,
        OWNS + REPORT_FOR relationships, and SHARES_WITH the student — all in
        one transaction.

        AI reports pass ``submission_status=None`` and
        ``allowed_from_statuses=None`` so the submission's status is not
        transitioned and no status guard runs (AI reports are not a state
        machine event the way teacher reviews are).
        """
        if not self.submissions_backend:
            self.logger.warning(
                "No submissions_backend configured — AI report generated but not persisted "
                "as entity. Wire submissions_backend in ExerciseReportService to enable "
                "full persistence."
            )
            # Return a transient ExerciseReport object for graceful degradation
            return self._build_transient_report(submission, exercise, feedback_text, user_uid)

        report_entity_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )

        try:
            query_result = await self.submissions_backend.create_report_node(
                {
                    "report_uid": submission.uid,
                    "report_entity_uid": report_entity_uid,
                    "author_uid": user_uid,
                    "feedback": feedback_text,
                    "report_file_path": None,
                    "title": title,
                    "entity_type": EntityType.EXERCISE_REPORT.value,
                    "submission_status": None,
                    "completed_status": EntityStatus.COMPLETED.value,
                    "processor_type": ProcessorType.LLM.value,
                    "assessment_outcome": AssessmentOutcome.AI_EVALUATED.value,
                    "allowed_from_statuses": None,
                    "now": now,
                },
            )

            if query_result.is_error or not query_result.value:
                return Result.fail(
                    Errors.database(
                        "create_report_entity",
                        "Failed to create EXERCISE_REPORT entity",
                    )
                )

            self.logger.info(f"EXERCISE_REPORT entity created: {report_entity_uid}")

            feedback_entity = ExerciseReport(
                uid=report_entity_uid,
                entity_type=EntityType.EXERCISE_REPORT,
                title=title,
                user_uid=user_uid,
                status=EntityStatus.COMPLETED,
                processor_type=ProcessorType.LLM,
                assessment_outcome=AssessmentOutcome.AI_EVALUATED,
                processed_content=feedback_text,
                subject_uid=submission.uid,
            )

            # Close the mastery loop: explicitly propagate mastery via the service
            # if available, falling back to implicit logic if not.
            if self.report_mastery_service:
                await self._propagate_mastery_via_service(
                    submission, user_uid, exercise.mastery_impact
                )
            else:
                await self._update_mastery_for_linked_ku(
                    submission, user_uid, exercise.mastery_impact
                )

            return Result.ok(feedback_entity)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to persist report entity: {e}")
            return Result.fail(
                Errors.database(
                    "create_report_entity",
                    f"Failed to persist report entity: {e!s}",
                )
            )

    async def _propagate_mastery_via_service(
        self,
        submission: Submission,
        user_uid: UserUID,
        mastery_impact: MasteryImpact,
    ) -> None:
        """Explicit propagation via the ReportMasteryService."""
        if not self.backend:
            return

        result = await self.backend.get_linked_ku_and_student(submission.uid)
        if result.is_error or not result.value:
            return

        linked_uids = [record.get("ku_uid") for record in result.value if record.get("ku_uid")]
        student_uid = result.value[0].get("student_uid") if result.value else user_uid

        if linked_uids and self.report_mastery_service:
            await self.report_mastery_service.propagate_mastery(
                submission_uid=submission.uid,
                user_uid=student_uid,
                linked_ku_uids=linked_uids,
                mastery_impact=mastery_impact,
                method="activity_report",
            )

    async def _update_mastery_for_linked_ku(
        self,
        submission: Submission,
        user_uid: UserUID,
        mastery_impact: MasteryImpact = MasteryImpact.MODERATE,
    ) -> None:
        """
        Update MASTERED relationships on Ku nodes linked to the submission.

        Queries APPLIES_KNOWLEDGE from the submission to find which Ku nodes
        the student demonstrated knowledge of, then calls mark_mastered() on each.

        The mastery score comes from the Exercise's MasteryImpact enum via
        get_ai_score(). Teacher approval via approve_report() uses the higher
        get_teacher_score(). The MASTERED Cypher uses CASE WHEN new > existing,
        so teacher approval later will correctly upgrade the AI score.

        This closes the mastery loop for PERSONAL scope exercises where there
        is no teacher approval step. For ASSIGNED scope exercises, both this
        and approve_report() may run — the higher teacher score wins.

        Failure is logged but never propagates — mastery update is best-effort
        and must not abort the feedback response.
        """
        if not self.ku_interaction_service or not self.backend:
            return

        result = await self.backend.get_linked_ku_and_student(submission.uid)

        if result.is_error or not result.value:
            return

        for record in result.value:
            ku_uid = record.get("ku_uid")
            student_uid = record.get("student_uid") or user_uid
            if not ku_uid:
                continue

            ai_score = mastery_impact.get_ai_score()
            mastery_result = await self.ku_interaction_service.mark_mastered(
                user_uid=student_uid,
                ku_uid=ku_uid,
                mastery_score=ai_score,
                method="activity_report",
            )
            if mastery_result.is_error:
                self.logger.warning(
                    f"Mastery update failed for KU {ku_uid} after AI report: {mastery_result.error}"
                )
            else:
                self.logger.info(
                    f"Mastery updated via AI report: {student_uid} -> {ku_uid} "
                    f"(score={ai_score}, impact={mastery_impact.value})"
                )

    def _build_transient_report(
        self,
        submission: Submission,
        exercise: Exercise,
        feedback_text: str,
        user_uid: UserUID,
    ) -> Result[ExerciseReport]:
        """Build a non-persisted ExerciseReport object for graceful degradation."""
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )
        feedback_entity = ExerciseReport(
            uid=f"transient_{submission.uid}",
            entity_type=EntityType.EXERCISE_REPORT,
            title=title,
            user_uid=user_uid,
            status=EntityStatus.COMPLETED,
            processor_type=ProcessorType.LLM,
            assessment_outcome=AssessmentOutcome.AI_EVALUATED,
            processed_content=feedback_text,
            subject_uid=submission.uid,
        )
        return Result.ok(feedback_entity)

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get list of supported models by provider."""
        if not self.llm_caller:
            return {}
        return self.llm_caller.get_supported_models()

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported by available services."""
        if not self.llm_caller:
            return False
        return self.llm_caller.is_model_supported(model)
