"""
Feedback Protocols
==================

Route-facing protocols for the Feedback stage of SKUEL's core educational loop:

    Ku → Exercise → Submission → Feedback
                                     ↑
                           someone responds to the work

Feedback has two implementations — the mechanism differs, the concept is the same:

    Human feedback  (teacher reviews and writes)  → processor_type = HUMAN
    AI feedback     (LLM evaluates via Exercise)   → processor_type = LLM

Both create SUBMISSION_FEEDBACK entities (EntityType.SUBMISSION_FEEDBACK) linked to the
submission via FEEDBACK_FOR. The processor_type field discriminates the source.

Progress feedback (EntityType.ACTIVITY_REPORT) is macro-level AI feedback — the system
summarises cross-domain activity over a time window. Still feedback, broader scope.

Protocol Responsibilities
--------------------------
    FeedbackOperations           — Human + AI feedback CRUD (SUBMISSION_FEEDBACK entities)
    ProgressFeedbackOperations   — Auto-generated progress reports (ACTIVITY_REPORT entities)
    ProgressScheduleOperations   — Recurring progress report scheduling
    ActivityReviewOperations     — Admin human feedback on Activity Domains
    TeacherReviewOperations      — Teacher review queue, feedback, revision, approval

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class FeedbackOperations(Protocol):
    """Human + AI feedback on submissions. Both create SUBMISSION_FEEDBACK entities.

    processor_type discriminates the source:
        ProcessorType.HUMAN — teacher writes feedback (create_assessment)
        ProcessorType.LLM   — LLM generates feedback via Exercise (generate_feedback)

    Assessment methods (from the former ReportsContentOperations) and AI feedback
    generation (from the former ReportsFeedbackOperations) are unified here because
    they represent the same concept: a response to student work.

    Route consumers: feedback_assessment_api.py (assessments), exercises_api.py (AI feedback)
    Implementation: SubmissionsCoreService (assessments) + FeedbackService (AI)
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
        """Create a teacher assessment (EntityType.SUBMISSION_FEEDBACK, processor_type=HUMAN).

        Verifies teacher-student group membership before creating.
        Auto-shares with student via SHARES_WITH {role: 'student'}.

        Returns Result[SubmissionFeedback].
        """
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports received by a student. Returns Result[list[SubmissionFeedback]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports authored by a teacher. Returns Result[list[SubmissionFeedback]]."""
        ...

    # ------------------------------------------------------------------
    # AI FEEDBACK — LLM-generated via Exercise instructions
    # ------------------------------------------------------------------

    async def generate_feedback(
        self,
        entry: Any,
        exercise: Any,
        user_uid: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[Any]:
        """Generate AI feedback for a submission using exercise instructions.

        Creates SUBMISSION_FEEDBACK entity (processor_type=LLM) in Neo4j, linked
        to the submission via FEEDBACK_FOR. Also updates the submission's
        denormalized feedback field for quick access.

        Args:
            entry: Submission to evaluate (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering feedback (owns the entity)
            temperature: LLM sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns Result[SubmissionFeedback] — the created SUBMISSION_FEEDBACK entity.
        """
        ...


@runtime_checkable
class ProgressFeedbackOperations(Protocol):
    """Auto-generated activity feedback (EntityType.ACTIVITY_REPORT).

    Macro-level AI feedback — the system summarises a user's cross-domain activity
    over a time window. NOT tied to a specific submission artifact.
    ActivityReport inherits UserOwnedEntity directly (not Submission).

    processor_type discriminates source:
        ProcessorType.AUTOMATIC — scheduled system generation
        ProcessorType.LLM       — on-demand AI generation
        ProcessorType.HUMAN     — admin-written activity review

    Route consumer: progress_feedback_api.py
    Implementation: ProgressFeedbackGenerator
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

    Route consumer: progress_feedback_api.py
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
class ActivityReviewOperations(Protocol):
    """Admin-facing activity review operations — human feedback on Activity Domains.

    Produces ActivityReport entities with ProcessorType.HUMAN. Admin reads a user's
    activity snapshot and writes qualitative feedback.

    Route consumer: progress_feedback_api.py (activity-review routes)
    Implementation: ActivityReviewService
    """

    async def create_activity_snapshot(
        self,
        subject_uid: str,
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> Result[Any]:
        """Generate activity snapshot for admin review. Returns Result[dict]."""
        ...

    async def submit_activity_feedback(
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

    async def get_activity_reviews_for_user(
        self,
        subject_uid: str,
        limit: int = 20,
    ) -> Result[list[Any]]:
        """Get all ActivityReport for a user (LLM + human). Returns Result[list[ActivityReport]]."""
        ...

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
        admin_uid: str,
        limit: int = 20,
    ) -> Result[list[Any]]:
        """Admin's pending review queue. Returns Result[list[dict]]."""
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


@runtime_checkable
class TeacherReviewOperations(Protocol):
    """Teacher review workflow — Phase 4 (Feedback) of the learning loop.

    Manages the full teacher-student interaction after a submission is shared:
    review queue → read submission → write feedback / request revision / approve.
    Also exposes exercise management and class/student views for the teacher dashboard.

    Route consumer: teaching_api.py (primary), teaching_ui.py
    Implementation: TeacherReviewService
    Protocol location: feedback_protocols.py (NOT group_protocols.py — this is
    Phase 4 Feedback infrastructure, not Group management infrastructure)
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

    async def get_feedback_history(
        self,
        submission_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get SUBMISSION_FEEDBACK nodes linked to a submission. Returns Result[list[dict]]."""
        ...

    async def submit_feedback(
        self,
        report_uid: str,
        teacher_uid: str,
        feedback: str,
    ) -> Result[dict[str, Any]]:
        """Submit feedback for a student report. Returns Result[dict]."""
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
