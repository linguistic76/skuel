"""
Submission Report Service
==========================

Generates AI reports for submission entries using Exercises.

AI report creates a first-class SUBMISSION_REPORT entity (processor_type=LLM),
symmetric with human teacher reports (processor_type=HUMAN). Both are stored
as SUBMISSION_REPORT entities linked to the submission via REPORT_FOR.

The core educational loop:
    Exercise (instructions) + Submission (student work) → LLM → SUBMISSION_REPORT entity

Following SKUEL principles:
- Transparent: User sees exact prompt sent to LLM
- Symmetric: AI report = same entity type as teacher report, processor_type differs
- Atomic: Entity creation + relationship + denormalization in one transaction
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.exercises.exercise import Exercise
from core.models.report.submission_report import SubmissionReport
from core.models.submissions.submission import Submission
from core.services.ai_service import AnthropicService, OpenAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports import QueryExecutor
    from core.services.lesson.lesson_mastery_service import LessonMasteryService

logger = get_logger(__name__)


class SubmissionReportService:
    """
    Generates AI reports for submission entries using exercise instructions.

    Creates a SUBMISSION_REPORT entity (processor_type=LLM) linked to the
    submission via REPORT_FOR — symmetric with teacher reports.

    Supports both OpenAI and Anthropic models.
    User selects which model to use via Exercise.model field.
    """

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        anthropic_service: AnthropicService | None = None,
        executor: "QueryExecutor | None" = None,
        ku_interaction_service: "LessonMasteryService | None" = None,
    ) -> None:
        """
        Initialize with AI services and query executor.

        Args:
            openai_service: OpenAI service for GPT models
            anthropic_service: Anthropic service for Claude models
            executor: QueryExecutor for creating SUBMISSION_REPORT entity in Neo4j
            ku_interaction_service: Optional — updates MASTERED relationships on linked Ku nodes
                after feedback is persisted, closing the mastery loop for PERSONAL scope
                exercises where no teacher approval step exists
        """
        if not openai_service and not anthropic_service:
            raise ValueError("At least one AI service (OpenAI or Anthropic) must be provided")

        self.openai = openai_service
        self.anthropic = anthropic_service
        self.executor = executor
        self.ku_interaction_service = ku_interaction_service
        self.logger = logger

        available = []
        if self.openai:
            available.append("OpenAI")
        if self.anthropic:
            available.append("Anthropic")
        if self.executor:
            available.append("Neo4j")
        if self.ku_interaction_service:
            available.append("MasteryLoop")

        logger.info(f"SubmissionReportService initialized with: {', '.join(available)}")

    async def generate_report(
        self,
        entry: Submission,
        exercise: Exercise,
        user_uid: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[SubmissionReport]:
        """
        Generate AI report for a submission entry using exercise instructions.

        Creates a SUBMISSION_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via REPORT_FOR. Also updates the submission's
        denormalized report field for quick access.

        Args:
            entry: Submission to analyze (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (teacher/admin — owns the entity)
            temperature: Sampling temperature (0-1, default 0.7)
            max_tokens: Maximum tokens to generate (default 4000)

        Returns:
            Result[SubmissionReport] containing the created SUBMISSION_REPORT entity
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

            # Generate report text via LLM
            if exercise.model.startswith("gpt"):
                if not self.openai:
                    return Result.fail(
                        Errors.integration(
                            service="OpenAI",
                            operation="generate_report",
                            message="OpenAI service not configured, but GPT model requested",
                        )
                    )
                llm_result = await self.openai.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=exercise.model,
                )

            elif exercise.model.startswith("claude"):
                if not self.anthropic:
                    return Result.fail(
                        Errors.integration(
                            service="Anthropic",
                            operation="generate_report",
                            message="Anthropic service not configured, but Claude model requested",
                        )
                    )
                llm_result = await self.anthropic.generate_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=exercise.model,
                )

            else:
                return Result.fail(
                    Errors.validation(
                        f"Unknown model: {exercise.model}. Must start with 'gpt' or 'claude'",
                        field="model",
                    )
                )

            if llm_result.is_error:
                self.logger.error(f"AI service error: {llm_result.error}")
                return Result.fail(llm_result.expect_error())

            feedback_text = llm_result.value
            self.logger.info(f"Report generated: {len(feedback_text)} chars")

            # Persist as SUBMISSION_REPORT entity
            return await self._persist_report_entity(
                submission=entry,
                exercise=exercise,
                feedback_text=feedback_text,
                user_uid=user_uid,
            )

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            return Result.fail(
                Errors.system(f"Report generation failed: {e!s}", operation="generate_report")
            )

    async def _persist_report_entity(
        self,
        submission: Submission,
        exercise: Exercise,
        feedback_text: str,
        user_uid: str,
    ) -> Result[SubmissionReport]:
        """
        Persist AI report as a SUBMISSION_REPORT entity in Neo4j.

        Creates the entity, OWNS relationship, REPORT_FOR relationship,
        and updates the submission's denormalized report field — atomically.

        Pattern follows TeacherReviewService.submit_report().
        """
        if not self.executor:
            self.logger.warning(
                "No executor configured — AI report generated but not persisted as entity. "
                "Configure executor in SubmissionReportService to enable full persistence."
            )
            # Return a transient SubmissionReport object for graceful degradation
            return self._build_transient_report(submission, exercise, feedback_text, user_uid)

        report_uid = UIDGenerator.generate_uid("sr")
        now = datetime.now().isoformat()
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )

        query = """
        MATCH (submission:Entity {uid: $submission_uid})
        OPTIONAL MATCH (creator:User {uid: $user_uid})

        SET submission.report_content = $feedback_text,
            submission.report_generated_at = datetime($now),
            submission.updated_at = datetime($now)

        CREATE (fb:Entity {
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
        })

        WITH submission, creator, fb
        CREATE (fb)-[:REPORT_FOR]->(submission)

        WITH submission, creator, fb
        WHERE creator IS NOT NULL
        CREATE (creator)-[:OWNS]->(fb)

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
                        "Failed to create SUBMISSION_REPORT entity",
                    )
                )

            self.logger.info(f"SUBMISSION_REPORT entity created: {report_uid}")

            feedback_entity = SubmissionReport(
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

        except Exception as e:
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
        user_uid: str,
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

        query = """
        MATCH (submission:Entity {uid: $submission_uid})-[:APPLIES_KNOWLEDGE]->(ku:Entity {entity_type: 'ku'})
        OPTIONAL MATCH (student:User)-[:OWNS]->(submission)
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
        user_uid: str,
    ) -> Result[SubmissionReport]:
        """Build a non-persisted SubmissionReport object for graceful degradation."""
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )
        feedback_entity = SubmissionReport(
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
        models: dict[str, Any] = {}
        if self.openai:
            models["openai"] = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        if self.anthropic:
            models["anthropic"] = [
                "claude-sonnet-4-6",  # Sonnet 4.6 — default
                "claude-opus-4-6",  # Opus 4.6 — highest capability
                "claude-haiku-4-5-20251001",  # Haiku 4.5 — fastest
                "claude-3-5-sonnet-20241022",  # 3.5 Sonnet — kept for existing exercises
                "claude-3-5-haiku-20241022",  # 3.5 Haiku — kept for existing exercises
            ]
        return models

    def is_model_supported(self, model: str) -> bool:
        """Check if a model is supported by available services."""
        if model.startswith("gpt") and self.openai:
            return True
        return bool(model.startswith("claude") and self.anthropic)
