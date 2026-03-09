"""
Report Protocols
================

Route-facing protocols for the Report stage of SKUEL's core educational loop:

    Ku → Exercise → Submission → Report
                                   ↑
                         someone responds to the work

Reports have two implementations — the mechanism differs, the concept is the same:

    Human report  (teacher reviews and writes)  → processor_type = HUMAN
    AI report     (LLM evaluates via Exercise)   → processor_type = LLM

Both create SUBMISSION_REPORT entities (EntityType.SUBMISSION_REPORT) linked to the
submission via REPORT_FOR. The processor_type field discriminates the source.

Progress reports (EntityType.ACTIVITY_REPORT) are macro-level AI reports — the system
summarises cross-domain activity over a time window. Still a report, broader scope.

Protocol Responsibilities
--------------------------
    SubmissionReportOperations   — Human + AI report CRUD (SUBMISSION_REPORT entities)
    ProgressReportOperations     — Auto-generated progress reports (ACTIVITY_REPORT entities)
    ProgressScheduleOperations   — Recurring progress report scheduling
    ActivityReportOperations     — Processor-neutral ActivityReport CRUD (snapshot, submit, history, annotate)
    ReviewQueueOperations        — ReviewRequest queue management (request_review, get_pending_reviews)
    TeacherReviewOperations      — Teacher review queue, report, revision, approval

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


@runtime_checkable
class SubmissionReportOperations(Protocol):
    """Human + AI reports on submissions. Both create SUBMISSION_REPORT entities.

    processor_type discriminates the source:
        ProcessorType.HUMAN — teacher writes report (create_assessment)
        ProcessorType.LLM   — LLM generates report via Exercise (generate_report)

    Assessment methods and AI report generation are unified here because
    they represent the same concept: a response to student work.

    Route consumers: submission_report_api.py (assessments), exercises_api.py (AI reports)
    Implementation: SubmissionsCoreService (assessments) + SubmissionReportService (AI)
    """

    # ------------------------------------------------------------------
    # HUMAN FEEDBACK — teacher-authored assessments
    # ------------------------------------------------------------------

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Create a teacher assessment (EntityType.SUBMISSION_REPORT, processor_type=HUMAN).

        Verifies teacher-student group membership before creating.
        Auto-shares with student via SHARES_WITH {role: 'student'}.

        Returns Result[SubmissionReport].
        """
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports received by a student. Returns Result[list[SubmissionReport]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports authored by a teacher. Returns Result[list[SubmissionReport]]."""
        ...

    # ------------------------------------------------------------------
    # AI FEEDBACK — LLM-generated via Exercise instructions
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        entry: Any,
        exercise: Any,
        user_uid: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[Any]:
        """Generate AI report for a submission using exercise instructions.

        Creates SUBMISSION_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via REPORT_FOR. Also updates the submission's
        denormalized report field for quick access.

        Args:
            entry: Submission to evaluate (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (owns the entity)
            temperature: LLM sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns Result[SubmissionReport] — the created SUBMISSION_REPORT entity.
        """
        ...


@runtime_checkable
class ProgressReportOperations(Protocol):
    """Auto-generated activity reports (EntityType.ACTIVITY_REPORT).

    Macro-level AI reports — the system summarises a user's cross-domain activity
    over a time window. NOT tied to a specific submission artifact.
    ActivityReport inherits UserOwnedEntity directly (not Submission).

    processor_type discriminates source:
        ProcessorType.AUTOMATIC — scheduled system generation
        ProcessorType.LLM       — on-demand AI generation
        ProcessorType.HUMAN     — admin-written activity review

    Route consumer: progress_report_api.py
    Implementation: ProgressReportGenerator
    """

    async def generate(
        self,
        user_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        depth: str = "standard",
        include_insights: bool = True,
    ) -> Result[Any]:
        """Generate activity feedback (EntityType.ACTIVITY_REPORT). Returns Result[ActivityReport]."""
        ...


@runtime_checkable
class ProgressScheduleOperations(Protocol):
    """Recurring progress report scheduling operations.

    Route consumer: progress_report_api.py
    Implementation: ProgressScheduleService
    """

    async def create_schedule(
        self,
        user_uid: str,
        schedule_type: str = "weekly",
        day_of_week: int = 0,
        domains: list[str] | None = None,
        depth: str = "standard",
    ) -> Result[Any]:
        """Create a recurring progress report schedule. Returns Result[ReportSchedule]."""
        ...

    async def get_user_schedule(self, user_uid: str) -> Result[Any]:
        """Get the user's active report schedule. Returns Result[ReportSchedule | None]."""
        ...

    async def update_schedule(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a schedule's configuration. Returns Result[ReportSchedule]."""
        ...

    async def deactivate_schedule(self, uid: str) -> Result[bool]:
        """Deactivate a schedule (soft delete). Returns Result[bool]."""
        ...


@runtime_checkable
class ActivityReportOperations(Protocol):
    """Processor-neutral ActivityReport CRUD — snapshot, submit, history, annotate.

    Owns all ActivityReport persistence regardless of processor_type (HUMAN, LLM,
    AUTOMATIC). The processor_type is data, not a service boundary.

    Route consumer: progress_report_api.py, activity_review_ui.py
    Implementation: ActivityReportService
    """

    async def create_snapshot(
        self,
        context: "UserContext",
        time_period: str = "7d",
        domains: list[str] | None = None,
        admin_uid: str = "",
    ) -> Result[Any]:
        """Build activity snapshot from pre-built UserContext for admin review. Returns Result[dict]."""
        ...

    async def submit_report(
        self,
        admin_uid: str,
        subject_uid: str,
        feedback_text: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        snapshot_context: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Create ActivityReport entity from admin-written assessment. Returns Result[ActivityReport]."""
        ...

    async def get_history(
        self,
        subject_uid: str,
        limit: int = 20,
    ) -> Result[list[Any]]:
        """Get all ActivityReport for a user (LLM + human). Returns Result[list[ActivityReport]]."""
        ...

    async def annotate(
        self,
        uid: str,
        user_uid: str,
        annotation_mode: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[Any]:
        """Save user annotation or revision to an owned ActivityReport. Returns Result[dict]."""
        ...

    async def get_annotation(self, uid: str, user_uid: str) -> Result[Any]:
        """Get current annotation state for an owned ActivityReport. Returns Result[dict]."""
        ...

    async def get_privacy_summary(self, user_uid: str) -> Result[Any]:
        """Return privacy-transparency summary for the user (admin snapshots, shares, schedule).

        User-facing — always scoped to the requesting user's own data.
        Returns Result[dict] with admin_snapshots, shares_granted, report_schedule.
        """
        ...


@runtime_checkable
class ReviewQueueOperations(Protocol):
    """ReviewRequest queue management — user-initiated review requests.

    Manages the lightweight ReviewRequest nodes that let users signal they want
    an admin to review their Activity Domain data.

    Route consumer: progress_report_api.py (activity-review/request + queue routes)
    Implementation: ReviewQueueService
    """

    async def request_review(
        self,
        user_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        message: str | None = None,
    ) -> Result[Any]:
        """User requests an activity review. Returns Result[dict]."""
        ...

    async def get_pending_reviews(
        self,
        _admin_uid: str,
        limit: int = 20,
    ) -> Result[list[Any]]:
        """Admin's pending review queue. Returns Result[list[dict]]."""
        ...


@runtime_checkable
class ReportRelationshipOperations(Protocol):
    """Pure-Cypher Level 1 queries for learning loop graph traversal.

    Route consumer: context intelligence, learning loop chain API
    Implementation: ReportRelationshipService
    """

    async def get_pending_submissions(self, user_uid: str) -> Result[list[str]]: ...
    async def get_unsubmitted_exercises(
        self, user_uid: str, limit: int = 5
    ) -> Result[list[dict[str, str | None]]]: ...
    async def get_report_summary(self, user_uid: str) -> Result[dict[str, int]]: ...
    async def get_learning_loop_chain(self, exercise_uid: str) -> Result[dict[str, Any]]: ...
    async def get_submission_chain(self, submission_uid: str) -> Result[dict[str, Any]]: ...


@runtime_checkable
class TeacherReviewOperations(Protocol):
    """Teacher review workflow — Phase 4 (Feedback) of the learning loop.

    Manages the full teacher-student interaction after a submission is shared:
    review queue → read submission → write feedback / request revision / approve.
    Also exposes exercise management and class/student views for the teacher dashboard.

    Route consumer: teaching_api.py (primary), teaching_ui.py
    Implementation: TeacherReviewService
    Protocol location: report_protocols.py (NOT group_protocols.py — this is
    Phase 4 Report infrastructure, not Group management infrastructure)
    """

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        ku_type_filter: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Get teacher's pending review queue. Returns Result[list[dict]]."""
        ...

    async def get_submission_detail(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[dict[str, Any]]:
        """Get full submission detail for teacher review (access-checked). Returns Result[dict]."""
        ...

    async def get_report_history(
        self,
        submission_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get SUBMISSION_REPORT nodes linked to a submission. Returns Result[list[dict]]."""
        ...

    async def submit_report(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """Submit report for a student submission. Returns Result[dict]."""
        ...

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[dict[str, Any]]:
        """Request revision for a student report. Returns Result[dict]."""
        ...

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[dict[str, Any]]:
        """Approve a student report. Returns Result[dict]."""
        ...

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get teacher's exercises with submission/reviewed counts. Returns Result[list[dict]]."""
        ...

    async def get_submissions_for_exercise(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all submissions against an exercise. Returns Result[list[dict]]."""
        ...

    async def get_students_summary(self, teacher_uid: str) -> Result[list[dict[str, Any]]]:
        """Get students who shared work with teacher, with counts. Returns Result[list[dict]]."""
        ...

    async def get_student_submissions(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get all submissions from student shared with teacher. Returns Result[list[dict]]."""
        ...

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[dict[str, Any]]:
        """Get at-a-glance stats for dashboard. Returns Result[dict]."""
        ...

    async def get_teacher_groups_with_stats(self, teacher_uid: str) -> Result[list[dict[str, Any]]]:
        """Get teacher's groups with member/exercise/pending counts. Returns Result[list[dict]]."""
        ...

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get group members with submission progress stats. Returns Result[list[dict]]."""
        ...
