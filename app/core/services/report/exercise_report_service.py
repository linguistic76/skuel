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
- Atomic: Entity creation + relationship + denormalization in one transaction
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.exercises.exercise import Exercise
from core.models.relationship_names import RelationshipName
from core.models.report.exercise_report import ExerciseReport
from core.models.submissions.submission import Submission
from core.models.type_hints import UserUID
from core.services.llm_caller import LLMCallerProtocol
from core.utils.exception_types import LLM_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports import QueryExecutor
    from core.services.lesson.lesson_mastery_service import LessonMasteryService

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
        llm_caller: LLMCallerProtocol,
        executor: "QueryExecutor | None" = None,
        ku_interaction_service: "LessonMasteryService | None" = None,
    ) -> None:
        """
        Initialize with LLM caller and query executor.

        Args:
            llm_caller: Unified LLM caller for model-agnostic generation
            executor: QueryExecutor for creating EXERCISE_REPORT entity in Neo4j
            ku_interaction_service: Optional — updates MASTERED relationships on linked Ku nodes
                after feedback is persisted, closing the mastery loop for PERSONAL scope
                exercises where no teacher approval step exists
        """
        self.llm_caller = llm_caller
        self.executor = executor
        self.ku_interaction_service = ku_interaction_service
        self.logger = logger

        available = ["LLMCaller"]
        if self.executor:
            available.append("Neo4j")
        if self.ku_interaction_service:
            available.append("MasteryLoop")

        logger.info(f"ExerciseReportService initialized with: {', '.join(available)}")

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
        to the submission via REPORT_FOR. Also updates the submission's
        denormalized report field for quick access.

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

        Creates the entity, OWNS relationship, REPORT_FOR relationship,
        and updates the submission's denormalized report field — atomically.

        Pattern follows TeacherReviewService.submit_report().
        """
        if not self.executor:
            self.logger.warning(
                "No executor configured — AI report generated but not persisted as entity. "
                "Configure executor in ExerciseReportService to enable full persistence."
            )
            # Return a transient ExerciseReport object for graceful degradation
            return self._build_transient_report(submission, exercise, feedback_text, user_uid)

        report_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )

        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})
        OPTIONAL MATCH (creator:User {{uid: $user_uid}})

        SET submission.report_content = $feedback_text,
            submission.report_generated_at = datetime($now),
            submission.updated_at = datetime($now)

        CREATE (fb:Entity {{
            uid: $report_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: $user_uid,
            status: $completed_status,
            processor_type: $processor_type,
            content: $feedback_text,
            report_content: $feedback_text,
            report_generated_at: datetime($now),
            subject_uid: $submission_uid,
            created_by: $user_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        }})

        WITH submission, creator, fb
        CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

        WITH submission, creator, fb
        WHERE creator IS NOT NULL
        CREATE (creator)-[:{RelationshipName.OWNS.value}]->(fb)

        RETURN fb.uid as report_uid
        """

        try:
            query_result = await self.executor.execute_query(
                query,
                {
                    "submission_uid": submission.uid,
                    "report_uid": report_uid,
                    "user_uid": user_uid,
                    "feedback_text": feedback_text,
                    "title": title,
                    "entity_type": EntityType.EXERCISE_REPORT.value,
                    "completed_status": EntityStatus.COMPLETED.value,
                    "processor_type": ProcessorType.LLM.value,
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

            self.logger.info(f"EXERCISE_REPORT entity created: {report_uid}")

            feedback_entity = ExerciseReport(
                uid=report_uid,
                entity_type=EntityType.EXERCISE_REPORT,
                title=title,
                user_uid=user_uid,
                status=EntityStatus.COMPLETED,
                processor_type=ProcessorType.LLM,
                content=feedback_text,
                report_content=feedback_text,
                subject_uid=submission.uid,
            )

            # Close the mastery loop: update MASTERED relationships on any Ku nodes
            # linked to the submission via APPLIES_KNOWLEDGE. Mirrors approve_report()
            # in TeacherReviewService but uses score=0.6 (AI-validated, not teacher-approved).
            await self._update_mastery_for_linked_ku(submission, user_uid)

            return Result.ok(feedback_entity)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to persist report entity: {e}")
            return Result.fail(
                Errors.database(
                    "create_report_entity",
                    f"Failed to persist report entity: {e!s}",
                )
            )

    async def _update_mastery_for_linked_ku(
        self,
        submission: Submission,
        user_uid: UserUID,
    ) -> None:
        """
        Update MASTERED relationships on Ku nodes linked to the submission.

        Queries APPLIES_KNOWLEDGE from the submission to find which Ku nodes
        the student demonstrated knowledge of, then calls mark_mastered() on each.

        Uses mastery_score=0.6 (AI-validated applied knowledge). Teacher approval
        via approve_report() uses 0.8. The MASTERED Cypher uses CASE WHEN new >
        existing, so teacher approval later will correctly upgrade 0.6 → 0.8.

        This closes the mastery loop for PERSONAL scope exercises where there
        is no teacher approval step. For ASSIGNED scope exercises, both this
        and approve_report() may run — the higher teacher score wins.

        Failure is logged but never propagates — mastery update is best-effort
        and must not abort the feedback response.
        """
        if not self.ku_interaction_service or not self.executor:
            return

        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity {{entity_type: 'ku'}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
        RETURN ku.uid AS ku_uid, student.uid AS student_uid
        """

        result = await self.executor.execute_query(query, {"submission_uid": submission.uid})

        if result.is_error or not result.value:
            return

        for record in result.value:
            ku_uid = record.get("ku_uid")
            student_uid = record.get("student_uid") or user_uid
            if not ku_uid:
                continue

            mastery_result = await self.ku_interaction_service.mark_mastered(
                user_uid=student_uid,
                ku_uid=ku_uid,
                mastery_score=0.6,
                method="activity_report",
            )
            if mastery_result.is_error:
                self.logger.warning(
                    f"Mastery update failed for KU {ku_uid} after AI report: {mastery_result.error}"
                )
            else:
                self.logger.info(
                    f"Mastery updated via AI report: {student_uid} -> {ku_uid} (score=0.6)"
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
            content=feedback_text,
            report_content=feedback_text,
            subject_uid=submission.uid,
        )
        return Result.ok(feedback_entity)

    def get_supported_models(self) -> dict[str, list[str]]:
        """Get list of supported models by provider."""
        return self.llm_caller.get_supported_models()

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported by available services."""
        return self.llm_caller.is_model_supported(model)
