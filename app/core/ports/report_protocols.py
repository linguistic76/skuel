"""
Report Protocols
================

Route-facing protocols for the Report stage of SKUEL's core educational loop:

    Exercise → UserEntry → EntryReport → RevisedExercise
                              ↑
                    someone responds to the work

PathStep is the curriculum anchor, linked via ``(PathStep)-[:HAS_EXERCISE]->(Exercise)``.

Reports have two implementations — the mechanism differs, the concept is the same:

    Human report  (teacher reviews and writes)  → ReportSource.HUMAN
    AI report     (LLM evaluates via Exercise)   → ReportSource.LLM

Both create ENTRY_REPORT entities (EntityType.ENTRY_REPORT) linked to the
submission via REPORT_FOR. The processor_type field discriminates the source.

Progress reports (EntityType.ACTIVITY_REPORT) are macro-level AI reports — the system
summarises cross-domain activity over a time window. Still a report, broader scope.

The HUMAN and AI halves are SEPARATE protocols implemented by separate services
(they are not a single-class union — that was split 2026-05-30, PR #128):

    AI report (LLM) + typed reads → EntryReportOperations  (EntryReportService)
    Human assessment (teacher)    → AssessmentOperations       (AssessmentService)

``list_for_submission`` (on EntryReportOperations) is the authoritative typed
read for BOTH HUMAN and LLM reports — processor_type discriminates.

Protocol Responsibilities
--------------------------
    EntryReportOperations     — AI report + typed reads (generate_report, list_for_submission)
    AssessmentOperations         — Teacher-authored assessments (create_assessment, get_assessments_*)
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

from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.base_protocols import BackendOperations
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    LearningLoopChain,
    PendingReviewItem,
    ReportApprovalResult,
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
    from core.models.entity_types import SubmissionEntity
    from core.models.exercises.exercise import Exercise
    from core.models.exercises.revised_exercise import RevisedExercise
    from core.models.report.activity_report import ActivityReport
    from core.models.report.entry_report import EntryReport
    from core.models.report_schedule import ReportSchedule
    from core.models.user_entry.user_entry import UserEntry
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
class EntryReportOperations(Protocol):
    """AI-generated + typed-read reports on submissions (ENTRY_REPORT entities).

    This is the AI/read-model half of the report surface. ``generate_report``
    creates an LLM report (processor_type=ReportSource.LLM) via Exercise
    instructions; ``list_for_submission`` is the authoritative typed read for
    BOTH HUMAN (teacher-authored) and LLM reports attached to a submission
    (processor_type discriminates the source).

    Teacher-authored assessment *creation* and assessment queries live on the
    sibling :class:`AssessmentOperations` (implemented by ``AssessmentService``)
    — they are a distinct service, not a single-class union with this one.

    Route consumers: exercises_api.py (AI reports), teaching_api.py / teaching_ui.py
    / user_entry_ui.py (report history).
    Implementation: ``EntryReportService``.
    """

    # ------------------------------------------------------------------
    # TYPED READS — shared by routes that display report history
    # ------------------------------------------------------------------

    async def list_for_submission(
        self,
        submission_uid: str,
    ) -> "Result[list[EntryReport]]":
        """List all reports attached to a submission (ASC by created_at).

        Returns both HUMAN (teacher-authored) and LLM (AI-generated) reports —
        processor_type discriminates. Replaces the dict-returning report
        history path.
        """
        ...

    # ------------------------------------------------------------------
    # AI FEEDBACK — LLM-generated via Exercise instructions
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        entry: "UserEntry",
        exercise: "Exercise",
        user_uid: UserUID,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> "Result[EntryReport]":
        """Generate AI report for a submission using exercise instructions.

        Creates ENTRY_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via REPORT_FOR. The typed read path
        (EntryReportService.list_for_submission) is the authoritative
        source for report content.

        Args:
            entry: Submission to evaluate (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering report (owns the entity)
            temperature: LLM sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns Result[EntryReport] — the created ENTRY_REPORT entity.
        """
        ...


@runtime_checkable
class AssessmentOperations(Protocol):
    """Teacher-authored assessments — HUMAN feedback on student work.

    The human half of the report surface (the AI half is
    :class:`EntryReportOperations`). Assessments are ENTRY_REPORT entities
    (ReportSource.HUMAN) created by a teacher, owned by the student (``OWNS``,
    written atomically with the node — the visibility anchor for
    received-feedback reads) and auto-shared via SHARES_WITH.

    Route consumers: entry_report_api.py (assessment CRUD),
    entry_reports_ui.py via UserEntryOrchestrator (a student's received
    feedback). Implementation: ``AssessmentService`` (core/services/user_entry/).
    """

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Result[EntryReport]":
        """Create a teacher assessment (EntityType.ENTRY_REPORT, ReportSource.HUMAN).

        Verifies teacher-student group membership before creating.
        Auto-shares with student via SHARES_WITH {role: 'student'}.

        Returns Result[EntryReport].
        """
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> "Result[list[EntryReport]]":
        """Get feedback reports received by a student. Returns Result[list[EntryReport]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> "Result[list[SubmissionEntity]]":
        """Get feedback reports authored by a teacher. Returns Result[list[SubmissionEntity]]."""
        ...


@runtime_checkable
class EntryReportBackendOperations(Protocol):
    """Backend-level protocol for typed EntryReport reads.

    Distinct from the service-level ``EntryReportOperations`` (which is
    the route-facing facade): this protocol captures the narrow backend
    surface used by ``EntryReportService`` and anything else that needs
    typed persistence-layer reads over ENTRY_REPORT nodes.

    Implemented structurally by
    ``EntryReportBackend(UniversalNeo4jBackend[EntryReport])``.
    """

    async def create_assessment_node(
        self, entity: "EntryReport", now: str
    ) -> "Result[list[Neo4jProperties]]":
        """Create a teacher-assessment ENTRY_REPORT node atomically with its
        student ``OWNS`` and ``SHARES_WITH`` edges — all-or-nothing, because
        ownership is the received-feedback visibility anchor and a report
        must never exist without it. Stamps ``:Entity:EntryReport``
        multi-labels. Empty result when the student does not exist.
        """
        ...

    async def get(self, uid: str) -> "Result[EntryReport | None]":
        """Typed single-fetch for EntryReport by UID.

        Returns ``Result.ok(None)`` when no matching node exists.
        """
        ...

    async def list_for_submission(self, submission_uid: str) -> "Result[list[EntryReport]]":
        """All reports attached to a submission, ASC by created_at."""
        ...

    async def get_reports_for_student_exercise(
        self, student_uid: str, exercise_uid: str
    ) -> "Result[list[EntryReport]]":
        """All reports on a student's submissions for a given exercise."""
        ...

    async def get_reports_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> "Result[list[EntryReport]]":
        """All reports authored by a teacher, newest first.

        Filters on ``author_uid`` (explicit authorship field). ``user_uid``
        always stores the student (access ownership); ``author_uid`` stores
        the teacher for HUMAN reports and is None for LLM/AI reports.
        """
        ...

    async def get_linked_ku_and_student(
        self, submission_uid: str
    ) -> Result[list[Neo4jProperties]]:  # boundary: mastery-loop scalar projection
        """Ku UIDs + student UID linked to a submission via APPLIES_KNOWLEDGE."""
        ...

    async def create_report_node(self, params: dict[str, Any]) -> Result[list[Neo4jProperties]]:
        """Create EntryReport node, link via REPORT_FOR, share with student, update submission."""
        ...

    async def create_report_and_revised_exercise(
        self, params: dict[str, Any], re_entity: RevisedExercise
    ) -> Result[list[Neo4jProperties]]:
        """Atomically create EntryReport + RevisedExercise in one transaction.

        The RevisedExercise model is serialized to node properties below the
        hexagonal boundary (adapter-side ``to_neo4j_node``).
        """
        ...


@runtime_checkable
class ProgressReportOperations(Protocol):
    """Auto-generated activity reports (EntityType.ACTIVITY_REPORT).

    Macro-level AI reports — the system summarises a user's cross-domain activity
    over a time window. NOT tied to a specific submission artifact.
    ActivityReport inherits UserOwnedEntity directly (not Submission).

    processor_type discriminates source:
        ReportSource.AUTOMATIC — scheduled system generation
        ReportSource.LLM       — on-demand AI generation
        ReportSource.HUMAN     — admin-written activity review

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
class ActivityReportBackendOperations(BackendOperations["ActivityReport"], Protocol):
    """Backend operations for ActivityReport — base CRUD + privacy-audit reads.

    Implementation: ActivityReportBackend (backends/misc_backends.py)
    Consumer: ActivityReportService.__init__
    """

    async def get_for_user(self, uid: str, user_uid: str) -> Result[list[Neo4jProperties]]: ...

    async def get_history(
        self, subject_uid: str, limit: int = 20
    ) -> Result[list[Neo4jProperties]]: ...

    async def annotate(
        self,
        uid: str,
        user_uid: UserUID,
        annotation_mode: str,
        now: str,
        user_annotation: str | None = None,
        user_revision: str | None = None,
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_annotation(
        self, uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_admin_snapshots(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_shares_granted(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_report_schedule(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]: ...


@runtime_checkable
class ReportScheduleBackendOperations(BackendOperations["ReportSchedule"], Protocol):
    """Backend operations for ReportSchedule — base CRUD + schedule-specific.

    Implementation: ReportScheduleBackend (backends/misc_backends.py)
    Consumer: ProgressScheduleService.__init__
    """

    async def create_user_schedule_relationship(
        self, user_uid: str, schedule_uid: str
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_due_schedules(self, min_interval_hours: int) -> Result[list[Neo4jProperties]]: ...


@runtime_checkable
class ActivityReportGeneratorBackendOperations(Protocol):
    """Backend-level reads for ``ProgressReportGenerator``.

    Two cross-entity queries that aren't natural fits for
    ``UniversalNeo4jBackend`` — both encapsulated below the hexagonal boundary
    (``adapters/persistence/neo4j/backends/misc_backends.py``).

    Implementation: ``ActivityReportGeneratorBackend``.
    Consumer: ``ProgressReportGenerator`` (cooldown check + previous-annotation
    carry-forward for AI report generation).
    """

    async def check_cooldown(
        self, user_uid: str, cooldown_minutes: int
    ) -> Result[list[Neo4jProperties]]:
        """Return a single-row ``recent_count`` for ActivityReports written
        within the cooldown window.

        Used to suppress duplicate AI report generation when one was just
        produced. Row shape: ``[{"recent_count": <int>}]``.
        """
        ...

    async def get_previous_annotation(
        self, user_uid: str, period_start: str
    ) -> Result[list[Neo4jProperties]]:
        """Return the most recent ``user_annotation`` (or ``user_revision``
        fallback) from any prior ActivityReport whose ``period_end`` is before
        ``period_start``.

        Used to carry forward the user's last self-annotation into the new
        report's prompt. Row shape: ``[{"annotation": <str>}]`` or ``[]``.
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
class ReviewQueueBackendOperations(Protocol):
    """Backend-level persistence for ReviewRequest nodes.

    ReviewRequest is a lightweight workflow marker — not an Entity subclass, so
    not managed by ``UniversalNeo4jBackend``. The backend owns the raw Cypher;
    ``ReviewQueueService`` orchestrates and translates the row dicts into the
    typed ``ReviewRequestResult`` / ``PendingReviewItem`` shapes returned by
    ``ReviewQueueOperations``.

    Implementation: ``ReviewQueueBackend``.
    """

    async def create_review_request(
        self,
        user_uid: str,
        uid: str,
        time_period: str,
        domains: list[str],
        message: str,
        now: str,
    ) -> Result[list[Neo4jProperties]]:
        """Open a new pending review request on the user's behalf.

        Not idempotent — every call opens a distinct request.

        Row shape: ``[{"uid": <str>, "status": "pending"}]``.
        """
        ...

    async def get_pending_reviews(self, limit: int = 20) -> Result[list[Neo4jProperties]]:
        """Return pending :ReviewRequest rows with the requesting user's
        username, ordered by ``created_at`` ASC.

        Row shape: ``[{"uid", "user_uid", "time_period", "domains", "message",
        "created_at", "username"}]``.
        """
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
        student_uid: str | None = None,
    ) -> "Result[list[ReviewQueueItem]]":
        """Get teacher's pending review queue (group-shared entries only).

        ``student_uid`` scopes the queue to one student — the single
        needs-review rule shared by the queue page and the per-student page.
        """
        ...

    async def get_submission_detail(
        self, submission_uid: str, teacher_uid: str
    ) -> "Result[SubmissionDetailResult]":
        """Get full submission detail for teacher review (access-checked). Returns Result[SubmissionDetailResult]."""
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

    async def get_report_file_path(self, report_uid: str, teacher_uid: str) -> Result[str | None]:
        """Get the report file path, gated by the teacher's classroom access.

        ``None`` when the report is missing or outside the teacher's active
        groups — role decides who may review, this decides whose feedback.
        """
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
        """Atomically create EntryReport + RevisedExercise in one transaction."""
        ...

    async def approve_report(
        self,
        report_uid: str,
        teacher_uid: str,
    ) -> Result[ReportApprovalResult]:
        """Approve a student report."""
        ...

    async def verify_teacher_authority(
        self,
        teacher_uid: str,
        student_uid: str,
    ) -> Result[bool]:
        """Verify that a teacher has authority over a student's records."""
        ...

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """Get teacher's exercises with submission/reviewed counts."""
        ...

    async def get_submissions_for_exercise(
        self, exercise_uid: str, teacher_uid: str
    ) -> Result[list[SubmissionForExercise]]:
        """Get submissions against an exercise that are shared with the teacher's groups."""
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


# ============================================================================
# Narrow ISP slices consumed by TeacherReviewService
# ============================================================================
#
# TeacherReviewService reaches into ExerciseBackend and GroupBackend for a
# handful of queries each. Rather than typing self.* against the full
# backend classes (which would expose ~30 unrelated methods), we declare the
# minimal Protocol slice each consumer actually calls. Same ISP discipline
# applied elsewhere in core/ports/.


@runtime_checkable
class TeacherReviewExerciseQueries(Protocol):
    """Narrow ExerciseBackend slice consumed by TeacherReviewService.

    Implementation: ExerciseBackend (backends/exercise_backends.py)
    Consumer: TeacherReviewService.exercise_backend
    """

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]: ...


@runtime_checkable
class TeacherReviewGroupQueries(Protocol):
    """Narrow GroupBackend slice consumed by TeacherReviewService.

    Implementation: GroupBackend (backends/collab_backends.py)
    Consumer: TeacherReviewService.group_backend
    """

    async def get_teacher_groups_with_stats(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_group_detail(
        self, group_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]: ...
