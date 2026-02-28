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

Both create FEEDBACK_REPORT entities (EntityType.FEEDBACK_REPORT) linked to the
submission via FEEDBACK_FOR. The processor_type field discriminates the source.

Progress feedback (EntityType.AI_FEEDBACK) is macro-level AI feedback — the system
summarises cross-domain activity over a time window. Still feedback, broader scope.

Protocol Responsibilities
--------------------------
    FeedbackOperations           — Human + AI feedback CRUD (FEEDBACK_REPORT entities)
    ProgressFeedbackOperations   — Auto-generated progress reports (AI_FEEDBACK entities)
    ProgressScheduleOperations   — Recurring progress report scheduling

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class FeedbackOperations(Protocol):
    """Human + AI feedback on submissions. Both create FEEDBACK_REPORT entities.

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
        """Create a teacher assessment (EntityType.FEEDBACK_REPORT, processor_type=HUMAN).

        Verifies teacher-student group membership before creating.
        Auto-shares with student via SHARES_WITH {role: 'student'}.

        Returns Result[Feedback].
        """
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports received by a student. Returns Result[list[Feedback]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get feedback reports authored by a teacher. Returns Result[list[Feedback]]."""
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

        Creates FEEDBACK_REPORT entity (processor_type=LLM) in Neo4j, linked
        to the submission via FEEDBACK_FOR. Also updates the submission's
        denormalized feedback field for quick access.

        Args:
            entry: Submission to evaluate (uses content or processed_content)
            exercise: Exercise with instructions and model selection
            user_uid: UID of user triggering feedback (owns the entity)
            temperature: LLM sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns Result[Feedback] — the created FEEDBACK_REPORT entity.
        """
        ...


@runtime_checkable
class ProgressFeedbackOperations(Protocol):
    """Auto-generated activity feedback (EntityType.AI_FEEDBACK).

    Macro-level AI feedback — the system summarises a user's cross-domain activity
    over a time window. NOT tied to a specific submission artifact.
    AiFeedback inherits UserOwnedEntity directly (not Submission).

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
        """Generate activity feedback (EntityType.AI_FEEDBACK). Returns Result[AiFeedback]."""
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

    Produces AiFeedback entities with ProcessorType.HUMAN. Admin reads a user's
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
        """Create AiFeedback entity from admin-written assessment. Returns Result[AiFeedback]."""
        ...

    async def get_activity_reviews_for_user(
        self,
        subject_uid: str,
        limit: int = 20,
    ) -> Result[list[Any]]:
        """Get all AiFeedback for a user (LLM + human). Returns Result[list[AiFeedback]]."""
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
