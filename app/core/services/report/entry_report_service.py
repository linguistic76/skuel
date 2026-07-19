"""
Entry Report Service
========================

Generates AI reports for submission entries using Exercises.

AI report creates a first-class ENTRY_REPORT entity (ReportSource.LLM),
symmetric with human teacher reports (ReportSource.HUMAN). Both are stored
as ENTRY_REPORT entities linked to the submission via REPORT_FOR.

The core educational loop:
    Exercise (instructions) + Submission (student work) → LLM → ENTRY_REPORT entity

Following SKUEL principles:
- Transparent: User sees exact prompt sent to LLM
- Symmetric: AI report = same entity type as teacher report, processor_type differs
- Atomic: Entity creation + REPORT_FOR + SHARES_WITH in one transaction
"""

from datetime import datetime
from typing import TYPE_CHECKING

from core.events import publish_event
from core.events.learning_loop_events import EntryReportGenerated
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.learning_enums import AssessmentOutcome, MasteryImpact
from core.models.enums.pipeline import Pipeline, ReportSource
from core.models.exercises.exercise import Exercise
from core.models.relationship_names import RelationshipName
from core.models.report.entry_report import EntryReport
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.prompts import PROMPT_REGISTRY
from core.services.llm_caller import LLMCallerProtocol
from core.utils.exception_types import LLM_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.report_protocols import EntryReportBackendOperations
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.report.report_mastery_service import ReportMasteryService
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger(__name__)


class EntryReportService:
    """
    Generates AI reports for submission entries using exercise instructions.

    Creates an ENTRY_REPORT entity (ReportSource.LLM) linked to the
    submission via REPORT_FOR — symmetric with teacher reports.

    Supports both OpenAI and Anthropic models.
    User selects which model to use via Exercise.model field.
    """

    def __init__(
        self,
        llm_caller: LLMCallerProtocol | None,
        backend: "EntryReportBackendOperations | None" = None,
        ku_interaction_service: "PsMasteryService | None" = None,
        report_mastery_service: "ReportMasteryService | None" = None,
        entry_service: "UserEntryService | None" = None,
        event_bus: "EventBusOperations | None" = None,
    ) -> None:
        """
        Initialize with LLM caller and domain backends.

        Args:
            llm_caller: Unified LLM caller for model-agnostic generation
            backend: The typed read facade for EntryReport — typed reads
                (``list_for_submission``, etc.) plus the mastery-loop scalar
                projection (``get_linked_ku_and_student``). Report *creation*
                is delegated to ``user_entry_backend.create_report_node`` —
                the canonical path shared with teacher reports.
             Canonical
                report-node creator shared with TeacherReviewService so AI
                and teacher reports go through the same Cypher.
            ku_interaction_service: Optional — updates MASTERED relationships on linked Ku nodes
                after feedback is persisted, closing the mastery loop for PERSONAL scope
                exercises where no teacher approval step exists
            report_mastery_service: Optional — explicit mastery propagation service
            entry_service: Optional — UserEntryService facade used by
                ``generate_entry_response`` for the ownership-verified entry
                fetch and the journal-chain eligibility check (TRANSFORMS edge).
            event_bus: Optional — publishes ``EntryReportGenerated`` after an
                AI report persists (drives the ADR-051 InteractionResult
                transition; the teacher path publishes ``ReportSubmitted``
                from TeacherReviewService instead).
        """
        self.llm_caller = llm_caller
        self.backend = backend
        self.ku_interaction_service = ku_interaction_service
        self.report_mastery_service = report_mastery_service
        self.entry_service = entry_service
        self.event_bus = event_bus
        self.logger = logger

        available = []
        if self.llm_caller:
            available.append("LLMCaller")
        if self.backend:
            available.append("Neo4j")
        if self.ku_interaction_service:
            available.append("MasteryLoop")

        logger.info(f"EntryReportService initialized with: {', '.join(available)}")

    async def get(self, uid: str) -> Result[EntryReport]:
        """Typed single-fetch for EntryReport by UID.

        Delegates to ``EntryReportBackend.get`` and narrows a missing
        row to a not-found error so routes can use the standard
        ``require_found`` pattern.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "EntryReportBackend not configured",
                    operation="get",
                )
            )
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="EntryReport", identifier=uid))
        return Result.ok(result.value)

    async def list_for_submission(self, submission_uid: str) -> Result[list[EntryReport]]:
        """List all reports attached to a submission (ASC by created_at).

        Delegates to EntryReportBackend.list_for_submission — typed
        end-to-end, no TypedDict projection, no mapping step. Both teacher
        (HUMAN) and AI (LLM) reports appear here, discriminated by
        ``EntryReport.processor_type``.
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "EntryReportBackend not configured",
                    operation="list_for_submission",
                )
            )
        return await self.backend.list_for_submission(submission_uid)

    # =========================================================================
    # JOURNAL-RESPONSE GENERATION (ADR-069)
    # =========================================================================

    async def generate_entry_response(
        self, entry_uid: str, user_uid: UserUID
    ) -> Result[EntryReport]:
        """Generate an LLM reflective response to a user's own journal entry.

        Unlike ``generate_report`` (which evaluates an exercise turn-in against
        an Exercise rubric), this produces a warm, peer-like reflection on a
        personal journal entry. The result is a PRIVATE, self-owned
        ``ENTRY_REPORT`` (ReportSource.LLM) — no teacher author, no student
        share grant, and **no status transition** on the entry.

        Eligibility — the entry must be on the journal chain:
          * ``pipeline == EXTRACT_ACTIVITIES`` (ADR-069 activity extraction), or
          * ``pipeline == TRANSCRIBE_AND_STRUCTURE`` (journal source), or
          * ``pipeline == NONE`` with an outgoing ``TRANSFORMS`` edge (the
            structured journal output child).
        Exercise turn-ins (``pipeline == TEACHER_REVIEW``) go through teacher
        review and are rejected with a business error.

        FULL tier only — at CORE tier ``llm_caller`` is ``None`` and a
        ``llm_tier_required`` business error is returned (same shape as
        ``Pipeline.LLM_SUMMARY``).
        """
        if not self.llm_caller:
            return Result.fail(
                Errors.business(
                    rule="llm_tier_required",
                    message=(
                        "Reflective entry responses require INTELLIGENCE_TIER=full; "
                        "the LLM caller is not configured (CORE tier)."
                    ),
                )
            )
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "EntryReportBackend not configured", operation="generate_entry_response"
                )
            )
        if not self.entry_service:
            return Result.fail(
                Errors.system(
                    "UserEntryService not configured", operation="generate_entry_response"
                )
            )

        # Ownership-verified fetch — returns not-found (404) for entries the
        # user does not own, never 403 (OWNERSHIP_VERIFICATION pattern).
        entry_result = await self.entry_service.get_entry(entry_uid, user_uid)
        if entry_result.is_error:
            return Result.fail(entry_result)
        entry = entry_result.value
        if entry is None:
            return Result.fail(Errors.not_found(resource="UserEntry", identifier=entry_uid))

        eligibility = await self._is_journal_chain_entry(entry)
        if eligibility.is_error:
            return Result.fail(eligibility)
        if not eligibility.value:
            return Result.fail(
                Errors.business(
                    rule="entry_not_eligible_for_response",
                    message=(
                        "Reflective responses are only available for journal entries; "
                        "exercise turn-ins go through teacher review."
                    ),
                )
            )

        source_text = entry.processed_content or entry.content
        if not source_text:
            return Result.fail(
                Errors.validation("Entry has no content to respond to", field="content")
            )

        try:
            prompt = PROMPT_REGISTRY.render("entry_response", content=source_text)
            llm_result = await self.llm_caller.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=1200,
            )
            if llm_result.is_error:
                return Result.fail(llm_result)

            return await self._persist_entry_response(
                entry=entry,
                response_text=llm_result.value,
                user_uid=user_uid,
            )
        except LLM_EXCEPTIONS as e:
            self.logger.error(f"LLM error generating entry response: {e}")
            return Result.fail(
                Errors.integration(
                    service="LLM",
                    operation="generate_entry_response",
                    message=f"Entry response generation failed: {e!s}",
                )
            )

    async def is_response_eligible(self, entry: UserEntry) -> Result[bool]:
        """Whether ``entry`` can receive a reflective response (UI gate).

        Public wrapper over the same journal-chain check ``generate_entry_response``
        enforces — so the Respond button shows for *exactly* the entries the POST
        accepts, including ``NONE``-pipeline ``TRANSFORMS`` children (one graph
        read; the two explicit journal pipelines short-circuit without a query).
        """
        return await self._is_journal_chain_entry(entry)

    async def _is_journal_chain_entry(self, entry: UserEntry) -> Result[bool]:
        """Whether ``entry`` is on the journal chain (response-eligible).

        See :meth:`generate_entry_response` for the three eligible cases.
        """
        if entry.pipeline in (Pipeline.EXTRACT_ACTIVITIES, Pipeline.TRANSCRIBE_AND_STRUCTURE):
            return Result.ok(True)
        if entry.pipeline == Pipeline.NONE and self.entry_service is not None:
            rels = await self.entry_service.get_relationships(
                entry.uid, rel_type=RelationshipName.TRANSFORMS, direction="outgoing"
            )
            if rels.is_error:
                return Result.fail(rels)
            return Result.ok(bool(rels.value))
        return Result.ok(False)

    async def _persist_entry_response(
        self, entry: UserEntry, response_text: str, user_uid: UserUID
    ) -> Result[EntryReport]:
        """Persist a journal response as a PRIVATE, self-owned ENTRY_REPORT.

        Delegates to ``create_report_node`` with ``visibility='private'``,
        ``create_student_share=False``, ``author_uid=None`` (no human author),
        and ``submission_status=None`` (no status transition).
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "EntryReportBackend not configured", operation="_persist_entry_response"
                )
            )

        report_entity_uid = UIDGenerator.generate_uid("er")
        now = datetime.now().isoformat()
        title = (
            f"Reflection on: {entry.title[:50]}"
            if entry.title
            else f"Reflection on entry {entry.uid[:20]}"
        )

        try:
            query_result = await self.backend.create_report_node(
                {
                    "report_uid": entry.uid,
                    "report_entity_uid": report_entity_uid,
                    "author_uid": None,
                    "feedback": response_text,
                    "report_file_path": None,
                    "title": title,
                    "entity_type": EntityType.ENTRY_REPORT.value,
                    "submission_status": None,
                    "completed_status": EntityStatus.COMPLETED.value,
                    "processor_type": ReportSource.LLM.value,
                    "assessment_outcome": None,
                    "allowed_from_statuses": None,
                    "visibility": "private",
                    "create_student_share": False,
                    "now": now,
                },
            )
            if query_result.is_error or not query_result.value:
                return Result.fail(
                    Errors.database(
                        "create_entry_response",
                        "Failed to create ENTRY_REPORT node for journal response",
                    )
                )

            self.logger.info(f"Journal-response ENTRY_REPORT created: {report_entity_uid}")
            return Result.ok(
                EntryReport(
                    uid=report_entity_uid,
                    entity_type=EntityType.ENTRY_REPORT,
                    title=title,
                    user_uid=user_uid,
                    author_uid=None,
                    status=EntityStatus.COMPLETED,
                    processor_type=ReportSource.LLM,
                    assessment_outcome=None,
                    processed_content=response_text,
                    subject_uid=entry.uid,
                )
            )
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to persist journal response: {e}")
            return Result.fail(
                Errors.database(
                    "create_entry_response",
                    f"Failed to persist journal response: {e!s}",
                )
            )

    async def generate_report(
        self,
        entry: UserEntry,
        exercise: Exercise,
        user_uid: UserUID,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[EntryReport]:
        """
        Generate AI report for a submission entry using exercise instructions.

        Creates an ENTRY_REPORT entity (ReportSource.LLM) in Neo4j, linked
        to the submission via REPORT_FOR. The typed read path
        (list_for_submission) is the authoritative source for report content.

        Args:
            entry: Submission to analyze (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (teacher/admin — owns the entity)
            temperature: Sampling temperature (0-1, default 0.7)
            max_tokens: Maximum tokens to generate (default 4000)

        Returns:
            Result[EntryReport] containing the created ENTRY_REPORT entity
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

            # Persist as ENTRY_REPORT entity
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
        submission: UserEntry,
        exercise: Exercise,
        feedback_text: str,
        user_uid: UserUID,
    ) -> Result[EntryReport]:
        """
        Persist AI report as an ENTRY_REPORT entity in Neo4j.

        Delegates to ``UserEntryBackend.create_report_node`` — the canonical
        report-creation path shared with teacher reports. Creates the entity,
        OWNS + REPORT_FOR relationships, and SHARES_WITH the student — all in
        one transaction.

        AI reports pass ``submission_status=None`` and
        ``allowed_from_statuses=None`` so the submission's status is not
        transitioned and no status guard runs (AI reports are not a state
        machine event the way teacher reviews are).
        """
        if not self.backend:
            return Result.fail(
                Errors.system(
                    "backend not configured — EntryReportService requires "
                    "backend at startup (fail-fast dependency)",
                    operation="_persist_report_entity",
                )
            )

        report_entity_uid = UIDGenerator.generate_uid("er")
        now = datetime.now().isoformat()
        title = (
            f"AI Feedback: {exercise.title[:50]}"
            if exercise.title
            else f"AI Feedback: {exercise.uid[:20]}"
        )

        try:
            query_result = await self.backend.create_report_node(
                {
                    "report_uid": submission.uid,
                    "report_entity_uid": report_entity_uid,
                    # LLM-authored report ⇒ no human author (EntryReport contract).
                    # user_uid is the triggerer/owner, not the author.
                    "author_uid": None,
                    "feedback": feedback_text,
                    "report_file_path": None,
                    "title": title,
                    "entity_type": EntityType.ENTRY_REPORT.value,
                    "submission_status": None,
                    "completed_status": EntityStatus.COMPLETED.value,
                    "processor_type": ReportSource.LLM.value,
                    "assessment_outcome": AssessmentOutcome.AI_EVALUATED.value,
                    "allowed_from_statuses": None,
                    "visibility": "shared",
                    "create_student_share": True,
                    "now": now,
                },
            )

            if query_result.is_error or not query_result.value:
                return Result.fail(
                    Errors.database(
                        "create_report_entity",
                        "Failed to create ENTRY_REPORT entity",
                    )
                )

            self.logger.info(f"ENTRY_REPORT entity created: {report_entity_uid}")

            student_uid: UserUID = (
                UserUID(str(query_result.value[0].get("student_uid") or user_uid))
                if query_result.value
                else user_uid
            )
            feedback_entity = EntryReport(
                uid=report_entity_uid,
                entity_type=EntityType.ENTRY_REPORT,
                title=title,
                user_uid=student_uid,
                author_uid=None,
                status=EntityStatus.COMPLETED,
                processor_type=ReportSource.LLM,
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

            await publish_event(
                self.event_bus,
                EntryReportGenerated(
                    entry_uid=submission.uid,
                    report_uid=report_entity_uid,
                    student_uid=str(student_uid),
                    source=ReportSource.LLM.value,
                ),
                self.logger,
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
        submission: UserEntry,
        user_uid: UserUID,
        mastery_impact: MasteryImpact,
    ) -> None:
        """Explicit propagation via the ReportMasteryService."""
        if not self.backend:
            return

        result = await self.backend.get_linked_ku_and_student(submission.uid)
        if result.is_error or not result.value:
            return

        linked_uids: list[str] = [
            str(record.get("ku_uid")) for record in result.value if record.get("ku_uid")
        ]
        student_uid: UserUID = (
            UserUID(str(result.value[0].get("student_uid") or user_uid))
            if result.value
            else user_uid
        )

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
        submission: UserEntry,
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
            ku_uid_raw = record.get("ku_uid")
            if not ku_uid_raw:
                continue
            ku_uid = str(ku_uid_raw)
            student_uid = UserUID(str(record.get("student_uid") or user_uid))

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
