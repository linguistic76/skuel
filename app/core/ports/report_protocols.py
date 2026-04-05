"""
Report Protocols
================

Route-facing protocols for the Report stage of SKUEL's core educational loop:

    PathStep → Exercise → Submission → Report
                                     ↑
                           someone responds to the work

Reports have two implementations — the mechanism differs, the concept is the same:

    Human report  (teacher reviews and writes)  → processor_type = HUMAN
    AI report     (LLM evaluates via Exercise)   → processor_type = LLM

Both create EXERCISE_REPORT entities (EntityType.EXERCISE_REPORT) linked to the
submission via REPORT_FOR. The processor_type field discriminates the source.

Progress reports (EntityType.ACTIVITY_REPORT) are macro-level AI reports — the system
summarises cross-domain activity over a time window. Still a report, broader scope.

Protocol Responsibilities
--------------------------
    ExerciseReportOperations     — Human + AI report CRUD (EXERCISE_REPORT entities)
    ProgressReportOperations     — Auto-generated progress reports (ACTIVITY_REPORT entities)
    ProgressScheduleOperations   — Recurring progress report scheduling
    ActivityReportOperations     — Processor-neutral ActivityReport CRUD (snapshot, submit, history, annotate)
    ReviewQueueOperations        — ReviewRequest queue management (request_review, get_pending_reviews)
    TeacherReviewOperations      — Teacher review queue, report, revision, approval

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.models.type_hints import UserUID
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    LearningLoopChain,
    PendingReviewItem,
    ReportApprovalResult,
    ReportHistoryItem,
    ReportSubmitResult,
    ReportSummary,
    ReviewRequestResult,
    RevisionRequestResult,
    RevisionWithExerciseResult,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionChain,
    SubmissionForExercise,
    TeacherGroupStats,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise
    from core.models.report.activity_report import ActivityReport
    from core.models.report.exercise_report import ExerciseReport
    from core.models.submissions.report_schedule import ReportSchedule
    from core.models.submissions.submission import Submission
    from core.ports.query_types import (
        AnnotationResult,
        AnnotationState,
        PrivacySummary,
        ReviewQueueItem,
        SubmissionDetailResult,
        TeacherDashboardStats,
    )
    from core.services.user.unified_user_context import UserContext


@runtime_checkable
class ExerciseReportOperations(Protocol):
    """Human + AI reports on submissions. Both create EXERCISE_REPORT entities.

    processor_type discriminates the source:
        ProcessorType.HUMAN — teacher writes report (create_assessment)
        ProcessorType.LLM   — LLM generates report via Exercise (generate_report)

    Assessment methods and AI report generation are unified here because
    they represent the same concept: a response to student work.

    Route consumers: exercise_report_api.py (assessments), exercises_api.py (AI reports)
    Implementation: SubmissionsCoreService (assessments) + ExerciseReportService (AI)
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
    ) -> "Result[ExerciseReport]":
        """Create a teacher assessment (EntityType.EXERCISE_REPORT, processor_type=HUMAN).

        Verifies teacher-student group membership before creating.
        Auto-shares with student via SHARES_WITH {role: 'student'}.

        Returns Result[ExerciseReport].
        """
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> "Result[list[ExerciseReport]]":
        """Get feedback reports received by a student. Returns Result[list[ExerciseReport]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> "Result[list[ExerciseReport]]":
        """Get feedback reports authored by a teacher. Returns Result[list[ExerciseReport]]."""
        ...

    # ------------------------------------------------------------------
    # AI FEEDBACK — LLM-generated via Exercise instructions
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        entry: "Submission",
        exercise: "Exercise",
        user_uid: UserUID,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> "Result[ExerciseReport]":
        """Generate AI report for a submission using exercise instructions.

        Creates EXERCISE_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via REPORT_FOR. Also updates the submission's
        denormalized report field for quick access.

        Args:
            entry: Submission to evaluate (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (owns the entity)
            temperature: LLM sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns Result[ExerciseReport] — the created EXERCISE_REPORT entity.
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
        user_uid: UserUID,
        time_period: str = "7d",
        domains: list[str] | None = None,
        depth: str = "standard",
        include_insights: bool = True,
    ) -> "Result[ActivityReport]":
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
        user_uid: UserUID,
        schedule_type: str = "weekly",
        day_of_week: int = 0,
        domains: list[str] | None = None,
        depth: str = "standard",
    ) -> "Result[ReportSchedule]":
        """Create a recurring progress report schedule. Returns Result[ReportSchedule]."""
        ...

    async def get_user_schedule(self, user_uid: UserUID) -> "Result[ReportSchedule | None]":
        """Get the user's active report schedule. Returns Result[ReportSchedule | None]."""
        ...

    async def update_schedule(self, uid: str, updates: dict[str, Any]) -> "Result[ReportSchedule]":
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
    ) -> Result[dict[str, Any]]:
        """Build activity snapshot from pre-built UserContext for admin review.

        boundary: Returns dict[str, Any] — dynamic domain slices where keys in
        the 'domains' sub-dict vary based on the domains parameter (tasks, goals,
        habits, events, choices, principles, knowledge, learning_paths).
        """
        ...

    async def submit_report(
        self,
        admin_uid: str,
        subject_uid: str,
        feedback_text: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
        snapshot_context: dict[str, Any] | None = None,
    ) -> "Result[ActivityReport]":
        """Create ActivityReport entity from admin-written assessment. Returns Result[ActivityReport]."""
        ...

    async def get_history(
        self,
        subject_uid: str,
        limit: int = 20,
    ) -> "Result[list[ActivityReport]]":
        """Get all ActivityReport for a user (LLM + human). Returns Result[list[ActivityReport]]."""
        ...

    async def annotate(
        self,
        uid: str,
        user_uid: UserUID,
        annotation_mode: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> "Result[AnnotationResult]":
        """Save user annotation or revision to an owned ActivityReport. Returns Result[AnnotationResult]."""
        ...

    async def get_annotation(self, uid: str, user_uid: UserUID) -> "Result[AnnotationState]":
        """Get current annotation state for an owned ActivityReport. Returns Result[AnnotationState]."""
        ...

    async def get_privacy_summary(self, user_uid: UserUID) -> "Result[PrivacySummary]":
        """Return privacy-transparency summary for the user (admin snapshots, shares, schedule).

        User-facing — always scoped to the requesting user's own data.
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
        user_uid: UserUID,
        time_period: str = "7d",
        domains: list[str] | None = None,
        message: str | None = None,
    ) -> Result[ReviewRequestResult]:
        """User requests an activity review."""
        ...

    async def get_pending_reviews(
        self,
        _admin_uid: str,
        limit: int = 20,
    ) -> Result[list[PendingReviewItem]]:
        """Admin's pending review queue."""
        ...


@runtime_checkable
class ReportRelationshipOperations(Protocol):
    """Pure-Cypher Level 1 queries for learning loop graph traversal.

    Route consumer: context intelligence, learning loop chain API
    Implementation: ReportRelationshipService
    """

    async def get_pending_submissions(self, user_uid: UserUID) -> Result[list[str]]: ...
    async def get_unsubmitted_exercises(
        self, user_uid: UserUID, limit: int = 5
    ) -> Result[list[dict[str, str | None]]]: ...
    async def get_report_summary(self, user_uid: UserUID) -> Result[ReportSummary]: ...
    async def get_learning_loop_chain(self, exercise_uid: str) -> Result[LearningLoopChain]: ...
    async def get_submission_chain(self, submission_uid: str) -> Result[SubmissionChain]: ...


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
        entity_type_filter: str | None = None,
    ) -> "Result[list[ReviewQueueItem]]":
        """Get teacher's pending review queue. Returns Result[list[ReviewQueueItem]]."""
        ...

    async def get_submission_detail(
        self, submission_uid: str, teacher_uid: str
    ) -> "Result[SubmissionDetailResult]":
        """Get full submission detail for teacher review (access-checked). Returns Result[SubmissionDetailResult]."""
        ...

    async def get_report_history(
        self,
        submission_uid: str,
    ) -> Result[list[ReportHistoryItem]]:
        """Get EXERCISE_REPORT nodes linked to a submission."""
        ...

    async def submit_report(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
        file_path: str | None = None,
    ) -> Result[ReportSubmitResult]:
        """Submit report for a student submission."""
        ...

    async def get_report_file_path(self, report_uid: str) -> Result[str | None]:
        """Get the report_file_path for an ExerciseReport node by UID."""
        ...

    async def request_revision(
        self,
        report_uid: str,
        teacher_uid: str,
        notes: str,
    ) -> Result[RevisionRequestResult]:
        """Request revision for a student report."""
        ...

    async def request_revision_with_exercise(
        self,
        submission_uid: str,
        teacher_uid: str,
        notes: str,
        original_exercise_uid: str,
        feedback_points: list[dict[str, str]],
        revision_rationale: str | None,
    ) -> Result[RevisionWithExerciseResult]:
        """Atomically create ExerciseReport + RevisedExercise in one transaction."""
        ...

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[ReportApprovalResult]:
        """Approve a student report."""
        ...

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """Get teacher's exercises with submission/reviewed counts."""
        ...

    async def get_submissions_for_exercise(
        self, exercise_uid: str
    ) -> Result[list[SubmissionForExercise]]:
        """Get all submissions against an exercise."""
        ...

    async def get_students_summary(self, teacher_uid: str) -> Result[list[StudentSummaryItem]]:
        """Get students who shared work with teacher, with counts."""
        ...

    async def get_student_submissions(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[StudentSubmissionItem]]:
        """Get all submissions from student shared with teacher."""
        ...

    async def get_dashboard_stats(self, teacher_uid: str) -> "Result[TeacherDashboardStats]":
        """Get at-a-glance stats for dashboard. Returns Result[TeacherDashboardStats]."""
        ...

    async def get_teacher_groups_with_stats(
        self, teacher_uid: str
    ) -> Result[list[TeacherGroupStats]]:
        """Get teacher's groups with member/exercise/pending counts."""
        ...

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[GroupMemberProgress]]:
        """Get group members with submission progress stats."""
        ...
