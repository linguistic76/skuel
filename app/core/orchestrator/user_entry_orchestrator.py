"""UserEntry UI Orchestrator (ADR-054)
======================================

Unified orchestrator for the UserEntry hub — the successor to the former
``SubmissionsOrchestrator`` + ``JournalOrchestrator``. Journal is a
``pipeline=TRANSCRIBE_AND_STRUCTURE`` flow on ``UserEntry``, not a
separate domain, so the previously-split orchestrators collapse into one.

All dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any, TypedDict

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import EntityUID, UserUID
from core.utils.result_simplified import ErrorCategory, Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise
    from core.models.exercises.revised_exercise import RevisedExercise
    from core.models.report.activity_report import ActivityReport
    from core.models.report.entry_report import EntryReport
    from core.models.user_entry.user_entry import UserEntry
    from core.ports.query_types import (
        ExchangeThread,
        KnowledgeEntryGroundingRow,
        OrganizerResult,
        StudentExchangeSummaries,
        SubmissionChain,
    )
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.report.entry_report_service import EntryReportService
    from core.services.report.report_relationship_service import ReportRelationshipService
    from core.services.report.teacher_review_service import TeacherReviewService
    from core.services.revised_exercises import RevisedExerciseService
    from core.services.sharing import UnifiedSharingService
    from core.services.user_entry.assessment_service import AssessmentService
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService


class EntryReportView(TypedDict):
    """Bundled view for the exercise-report detail page.

    Returned by :meth:`UserEntryOrchestrator.get_entry_report_view` — combines
    the report itself with the optional ``RevisedExercise`` that targets it, so
    the UI can render both in a single round trip.
    """

    report: EntryReport
    revised_exercise: RevisedExercise | None


class UserEntryOrchestrator:
    """Facade for the UserEntry UI layer.

    Collapses the former SubmissionsOrchestrator + JournalOrchestrator
    surfaces onto ``UserEntryService``, the single domain facade for all
    user-authored content.
    """

    def __init__(
        self,
        user_entry_service: UserEntryService,
        exercises_service: ExerciseService,
        teacher_review_service: TeacherReviewService,
        user_service: UserService,
        activity_report_service: ActivityReportService,
        revised_exercise_service: RevisedExerciseService,
        entry_report_service: EntryReportService,
        sharing_service: UnifiedSharingService,
        assessment_service: AssessmentService,
        report_relationship_service: ReportRelationshipService,
    ) -> None:
        self._entries = user_entry_service
        self._exercises = exercises_service
        self._teacher_review = teacher_review_service
        self._user_service = user_service
        self._activity_report = activity_report_service
        self._revised_exercise = revised_exercise_service
        self._entry_report = entry_report_service
        self._sharing = sharing_service
        self._assessment = assessment_service
        self._report_relationship = report_relationship_service

    @property
    def user_service(self) -> UserService:
        """Expose user service for admin role checks in UI routes."""
        return self._user_service

    # ------------------------------------------------------------------
    # UserEntry reads
    # ------------------------------------------------------------------

    async def get_entry(self, uid: str, user_uid: UserUID) -> Result[UserEntry | None]:
        """Ownership-verified fetch of a single UserEntry."""
        return await self._entries.get_entry(uid, user_uid)

    async def list_for_user(
        self,
        user_uid: UserUID,
        pipeline: Pipeline | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[UserEntry]]:
        """List a user's entries, optionally filtered by pipeline/status."""
        return await self._entries.list_for_user(
            user_uid=user_uid,
            pipeline=pipeline,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_journal_entries(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[UserEntry]]:
        """Return journal-domain entries across both journal pipelines.

        Includes:
        - JOURNAL                  — entries written via /journals UI (FOUNDER DNWF /
                                     STANDARD) and vault-synced notes with pipeline: journal
        - TRANSCRIBE_AND_STRUCTURE — legacy audio journal entries

        NONE is intentionally excluded: it is shared with plain submissions and uploads
        that have no journal identity. Vault notes intended for journals should declare
        ``pipeline: journal`` in their frontmatter instead.
        """
        import asyncio

        results = await asyncio.gather(
            self._entries.list_for_user(user_uid=user_uid, pipeline=Pipeline.JOURNAL, limit=limit),
            self._entries.list_for_user(
                user_uid=user_uid, pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE, limit=limit
            ),
        )

        entries: list[UserEntry] = []
        for result in results:
            if result.is_error:
                return Result.fail(result)
            if result.value:
                entries.extend(result.value)

        entries.sort(key=operator.attrgetter("created_at"), reverse=True)
        return Result.ok(entries[:limit])

    async def list_exercise_entries(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[UserEntry]]:
        """Return the user's exercise submissions (FULFILLS_EXERCISE edge, any pipeline)."""
        return await self._entries.list_exercise_entries(user_uid=user_uid, limit=limit)

    async def list_knowledge_entries_with_grounding(
        self, user_uid: UserUID, limit: int = 500
    ) -> Result[list[KnowledgeEntryGroundingRow]]:
        """Knowledge-pipeline entries + their grounded-Ku chips (newest first)."""
        return await self._entries.list_knowledge_entries_with_grounding(user_uid, limit)

    async def get_entry_organized_children(self, uid: str) -> Result[list[OrganizerResult]]:
        """Ordered ORGANIZES children of an entry — the emergent-MOC map.

        Renders as a card section on /gradebook/{uid} for ANY owned entry with
        ORGANIZES edges (vault ``moc: true`` files included). Not
        ownership-verified — the route gates on :meth:`get_entry` first.
        """
        return await self._entries.get_organized_children(uid)

    async def delete_entry(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Ownership-verified cascade delete."""
        return await self._entries.delete_entry(uid, user_uid)

    # ------------------------------------------------------------------
    # Exercises (dropdowns, assignment reads)
    # ------------------------------------------------------------------

    async def get_student_exercises(self, user_uid: UserUID) -> Result[list[Exercise]]:
        """Get assigned exercises for dropdowns in the submit form."""
        return await self._exercises.get_student_exercises(user_uid)

    async def list_user_exercises(self, user_uid: UserUID) -> Result[list[Exercise]]:
        """List saved instruction-template exercises owned by the user."""
        return await self._exercises.list_user_exercises(user_uid)

    async def create_exercise(
        self, user_uid: UserUID, name: str, instructions: str
    ) -> Result[Exercise]:
        """Save a new instruction file as an Exercise entity."""
        return await self._exercises.create_exercise(
            user_uid=user_uid,
            name=name,
            instructions=instructions,
        )

    # ------------------------------------------------------------------
    # Reports & Reviews
    # ------------------------------------------------------------------

    async def get_entry_report(self, uid: str) -> Result[EntryReport]:
        """Fetch an EntryReport by UID."""
        return await self._entry_report.get(uid)

    async def generate_entry_response(
        self, entry_uid: str, user_uid: UserUID
    ) -> Result[EntryReport]:
        """Generate an LLM reflective response to a user's own journal entry (ADR-069).

        Delegates to :meth:`EntryReportService.generate_entry_response` — the
        service performs the ownership-verified fetch, journal-chain eligibility
        check, and persists a PRIVATE self-owned ENTRY_REPORT.
        """
        return await self._entry_report.generate_entry_response(entry_uid, user_uid)

    async def is_entry_response_eligible(self, entry: UserEntry) -> Result[bool]:
        """Whether ``entry`` can receive a reflective response (drives the UI button).

        Delegates to :meth:`EntryReportService.is_response_eligible` so the button
        shows for exactly the entries the respond POST accepts (ADR-069).
        """
        return await self._entry_report.is_response_eligible(entry)

    async def get_entry_chain(self, entry_uid: str) -> Result[SubmissionChain]:
        """Full submission chain for an entry: exercise, feedback, revisions.

        The ``exercise`` projection comes from the FULFILLS_EXERCISE edge —
        the writer's single source of truth (entry metadata never carried it).

        Backend: ReportRelationshipService.get_submission_chain.
        """
        return await self._report_relationship.get_submission_chain(entry_uid)

    async def get_exchange_thread(
        self,
        viewer_uid: UserUID,
        exercise_uid: str,
        student_uid: str | None = None,
    ) -> Result[ExchangeThread]:
        """One (student, root exercise) exchange for the /exchange thread view.

        The viewer reads their own exchange by default; passing another
        ``student_uid`` requires the viewer to share an active owned group
        with that student — the same gate that guards the report-file
        download — and the chain read is then additionally scoped to entries
        ``SHARED_WITH_GROUP`` an active group the viewer owns, so a
        multi-class student's work directed to another teacher's classroom
        stays invisible. Every denial (no authority, missing exercise,
        student never submitted, nothing shared with this viewer) collapses
        to the same not-found error, so the page can probe neither exercise
        existence nor other classrooms' work (404-not-403,
        OWNERSHIP_VERIFICATION.md). Operational failures propagate with
        their own category — an outage must never read as missing data.

        Backend: ReportRelationshipService.get_exchange_thread (one chain
        read); TeacherReviewService.verify_teacher_authority (the gate).
        """
        target_uid = student_uid or viewer_uid
        teacher_scope: str | None = None
        if target_uid != viewer_uid:
            authority = await self._teacher_review.verify_teacher_authority(
                teacher_uid=viewer_uid, student_uid=target_uid
            )
            if authority.is_error:
                # Only the gate's own FORBIDDEN verdict is the deliberately
                # hidden class; a database failure during the check is an
                # outage and keeps its category for the route's 500 branch.
                if authority.expect_error().category is not ErrorCategory.FORBIDDEN:
                    return Result.fail(authority)
                return Result.fail(Errors.not_found(resource="Exchange", identifier=exercise_uid))
            teacher_scope = viewer_uid
        return await self._report_relationship.get_exchange_thread(
            exercise_uid, target_uid, viewer_uid=teacher_scope
        )

    async def get_student_exchange_summaries(
        self, student_uid: UserUID
    ) -> Result[StudentExchangeSummaries]:
        """Every exchange the caller is in, one summary line each — the
        GradeBook page's single read (arc 2 C1). Self-view only: the
        authenticated user reads their own OWNS-scoped summaries.

        Backend: ReportRelationshipService.get_student_exchange_summaries.
        """
        return await self._report_relationship.get_student_exchange_summaries(student_uid)

    async def get_entry_responses(self, entry_uid: str) -> Result[list[dict[str, Any]]]:
        """List the EntryReports attached to an entry (the "Responses" section).

        Wires ``ReportRelationshipService.get_submission_chain`` — returns the
        chain's ``feedback`` projection (uid, title, processor_type, created_at)
        for each report pointing at this entry via REPORT_FOR.
        """
        chain_result = await self._report_relationship.get_submission_chain(entry_uid)
        if chain_result.is_error:
            return Result.fail(chain_result)
        return Result.ok(list(chain_result.value.get("feedback") or []))

    async def get_entries_awaiting_response(self, user_uid: UserUID) -> Result[list[str]]:
        """UIDs of journal-chain entries that have no report yet (Respond candidates).

        Wires ``ReportRelationshipService.get_pending_submissions`` with the
        journal-pipeline filter so exercise turn-ins (teacher_review) are
        excluded from the "awaiting a response" surface.
        """
        return await self._report_relationship.get_pending_submissions(
            user_uid,
            pipelines=[Pipeline.EXTRACT_ACTIVITIES, Pipeline.TRANSCRIBE_AND_STRUCTURE],
        )

    async def check_report_access(self, report_uid: EntityUID, user_uid: UserUID) -> Result[bool]:
        """Canonical access check for a report — owner, PUBLIC, or shared."""
        return await self._sharing.check_access(report_uid, user_uid)

    async def get_entry_report_view(
        self, report_uid: str, user_uid: UserUID
    ) -> Result[EntryReportView]:
        """Fetch a report with access check + optional linked revision.

        Access denial surfaces as a not-found error so the route can render
        the standard "Report not found" banner without leaking existence.
        """
        report_result = await self._entry_report.get(report_uid)
        if report_result.is_error:
            return Result.fail(report_result)
        report = report_result.value

        access_result = await self._sharing.check_access(report.uid, user_uid)
        if access_result.is_error or not access_result.value:
            return Result.fail(Errors.not_found("EntryReport", report_uid))

        revision: RevisedExercise | None = None
        revision_result = await self._revised_exercise.get_by_report_uid(report.uid)
        if revision_result.is_ok:
            revision = revision_result.value

        return Result.ok({"report": report, "revised_exercise": revision})

    async def get_assessments_for_student(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[EntryReport]]:
        """Assessments (ENTRY_REPORT entities) received by a student."""
        return await self._assessment.get_assessments_for_student(user_uid, limit)

    # ------------------------------------------------------------------
    # Activity Reports
    # ------------------------------------------------------------------

    async def get_activity_report(self, uid: str, user_uid: UserUID) -> Result[ActivityReport]:
        """Fetch a single ActivityReport by UID, scoped to the owning user."""
        return await self._activity_report.get_for_user(uid, user_uid)

    async def get_activity_report_history(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[ActivityReport]]:
        """Fetch history of activity-based feedback."""
        return await self._activity_report.get_history(subject_uid=user_uid, limit=limit)

    # ------------------------------------------------------------------
    # Revised Exercises
    # ------------------------------------------------------------------

    async def get_revised_exercise(self, uid: str) -> Result[RevisedExercise]:
        """Fetch a specific student-requested revision."""
        return await self._revised_exercise.get(uid)

    async def get_revision_by_report(self, report_uid: str) -> Result[RevisedExercise | None]:
        """Find a revision generated starting from a given report."""
        return await self._revised_exercise.get_by_report_uid(report_uid)

    async def list_revised_exercises(self, user_uid: UserUID) -> Result[list[RevisedExercise]]:
        """List all revisions created by the student."""
        return await self._revised_exercise.list_for_student(user_uid)

    # ------------------------------------------------------------------
    # Teacher queue
    # ------------------------------------------------------------------

    async def get_review_queue(
        self, teacher_uid: UserUID, status_filter: list[str] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Teacher review queue — entries shared to the teacher's groups."""
        return await self._entries.get_review_queue(teacher_uid, status_filter=status_filter)
