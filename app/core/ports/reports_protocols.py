"""
Reports Protocols
==================

Route-facing protocols for the Reports domain — the content submission,
processing, sharing, and feedback half of SKUEL's core educational loop.

The Core Educational Loop
--------------------------
SKUEL's fundamental learning cycle:

    Exercise (shared template, admin/teacher-created)
        ↓  user submits work against it
    Submission (user-owned work product, EntityType.SUBMISSION)
        ↓  FULFILLS_EXERCISE relationship created
        ↓  auto-shared with teacher (SHARES_WITH role='teacher')
    Teacher review queue
        ↓  teacher gives feedback
    Feedback (first-class entity, EntityType.FEEDBACK_REPORT)
        ↓  FEEDBACK_FOR relationship to Submission
        ↓  auto-shared with student (SHARES_WITH role='student')

The Exercise is the shared instruction template. The Submission is the
user's own work product — it is user-owned from the moment of creation.
The Feedback closes the loop.

Protocol Responsibilities
--------------------------
    ReportsSubmissionOperations — File upload and submission CRUD
    ReportsContentOperations   — Content management (tags, categories, journals, assessments)
    ReportsContentSearchOperations — Cross-type search and statistics
    ReportsSharingOperations   — Visibility and sharing control
    ReportsProcessingOperations — Processing pipeline (transcription, LLM)
    ReportsFeedbackOperations  — LLM-based feedback generation (Exercise → Submission → AI feedback)
    ProgressReportGeneratorOperations — Auto-generated progress reports (AI_REPORT type)
    ReportsScheduleOperations  — Recurring progress report scheduling

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class ReportsSubmissionOperations(Protocol):
    """File upload and submission entity management operations.

    Route consumer: reports_api.py (primary service)
    Implementation: ReportsSubmissionService
    """

    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        ku_type: Any,
        processor_type: Any = ...,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
        fulfills_exercise_uid: str | None = None,
    ) -> Result[Any]:
        """Submit a file for processing. Returns Result[Submission]."""
        ...

    async def get_report(self, uid: str) -> Result[Any | None]:
        """Get submission entity by UID. Returns Result[Submission | None]."""
        ...

    async def list_reports(
        self,
        user_uid: str,
        ku_type: Any | None = None,
        status: Any | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Any]]:
        """List submissions for a user with filters. Returns Result[list[Submission]]."""
        ...

    async def get_file_content(self, ku_uid: str) -> Result[bytes]:
        """Get original file content. Returns Result[bytes]."""
        ...

    async def get_processed_file_content(self, ku_uid: str) -> Result[bytes]:
        """Get processed file content. Returns Result[bytes]."""
        ...

    async def get_report_statistics(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get submission statistics for a user. Returns Result[dict]."""
        ...

    async def update_processed_content(
        self,
        uid: str,
        processed_content: str,
        processed_file_path: str | None = None,
    ) -> Result[Any]:
        """Update processed content on a submission. Returns Result[Submission]."""
        ...


@runtime_checkable
class ReportsContentOperations(Protocol):
    """Content management operations (categories, tags, bulk, journals, assessments).

    Route consumer: reports_api.py, reports_sharing_api.py
    Implementation: ReportsCoreService
    """

    async def get_report(self, uid: str) -> Result[Any]:
        """Get report entity by UID. Returns Result[Submission]."""
        ...

    async def categorize_report(self, uid: str, category: str) -> Result[Any]:
        """Set category on a report. Returns Result[Submission]."""
        ...

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Add tags to a report. Returns Result[Submission]."""
        ...

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Remove tags from a report. Returns Result[Submission]."""
        ...

    async def publish_report(self, uid: str) -> Result[Any]:
        """Publish a report (set status to COMPLETED). Returns Result[Submission]."""
        ...

    async def archive_report(self, uid: str) -> Result[Any]:
        """Archive a report. Returns Result[Submission]."""
        ...

    async def mark_as_draft(self, uid: str) -> Result[Any]:
        """Mark report as draft. Returns Result[Submission]."""
        ...

    async def get_reports_by_category(
        self,
        category: str,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Get reports by category. Returns Result[list[Submission]]."""
        ...

    async def get_recent_reports(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        ku_type: Any | None = None,
    ) -> Result[list[Any]]:
        """Get recent reports. Returns Result[list[Submission]]."""
        ...

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """Bulk categorize reports. Returns Result[int] (count updated)."""
        ...

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """Bulk tag reports. Returns Result[int] (count updated)."""
        ...

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """Bulk delete reports. Returns Result[int] (count deleted)."""
        ...

    async def create_journal_report(
        self,
        user_uid: str,
        title: str,
        content: str,
        journal_type: Any = ...,
        journal_category: str | None = None,
        entry_date: date | None = None,
        tags: list[str] | None = None,
        mood: str | None = None,
        energy_level: int | None = None,
        key_topics: list[str] | None = None,
        action_items: list[str] | None = None,
        project_uid: str | None = None,
        metadata: dict[str, Any] | None = None,
        enforce_fifo: bool = True,
        source_type: str | None = None,
        source_file: str | None = None,
        transcription_uid: str | None = None,
    ) -> Result[Any]:
        """Create a journal entry (EntityType.JOURNAL). Returns Result[Journal]."""
        ...

    async def search(
        self,
        query: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search reports by text. Returns Result[list[Submission]]."""
        ...

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Create a teacher assessment (EntityType.FEEDBACK_REPORT). Returns Result[Feedback]."""
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


@runtime_checkable
class ReportsContentSearchOperations(Protocol):
    """Cross-type search and query operations across all report entity types.

    Route consumer: reports_api.py
    Implementation: ReportsSearchService
    """

    async def search_reports(
        self,
        user_uid: str,
        query: str,
        ku_type: Any | None = None,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search reports with text and type filters. Returns Result[list[Submission]]."""
        ...

    async def get_report_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        ku_type: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Get report statistics for a date range. Returns Result[dict]."""
        ...

    async def get_recent_reports(
        self,
        user_uid: str,
        ku_type: Any | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """Get recent reports. Returns Result[list[Submission]]."""
        ...

    async def get_journal_for_report(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """Get journal metadata for a report entity. Returns Result[dict | None]."""
        ...


@runtime_checkable
class ReportsSharingOperations(Protocol):
    """Content sharing and visibility control operations.

    Route consumer: reports_sharing_api.py (primary service)
    Implementation: ReportsSharingService
    """

    async def share_report(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share a report with a user. Returns Result[bool]."""
        ...

    async def unshare_report(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke sharing access. Returns Result[bool]."""
        ...

    async def get_shared_with_users(
        self,
        ku_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get users a report is shared with. Returns Result[list[dict]]."""
        ...

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get reports shared with a user. Returns Result[list[SubmissionDTO]]."""
        ...

    async def set_visibility(
        self,
        ku_uid: str,
        owner_uid: str,
        visibility: Any,
    ) -> Result[bool]:
        """Set report visibility level. Returns Result[bool]."""
        ...

    async def check_access(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user has access to a report. Returns Result[bool]."""
        ...


@runtime_checkable
class ReportsProcessingOperations(Protocol):
    """Report processing pipeline operations (transcription, LLM analysis).

    Route consumer: reports_api.py, reports_ui.py
    Implementation: ReportsProcessingService
    """

    async def process_report(
        self,
        ku_uid: str,
        instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Process a submission through the pipeline. Returns Result[Submission]."""
        ...

    async def reprocess_report(
        self,
        ku_uid: str,
        new_instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Reprocess a submission with new instructions. Returns Result[Submission]."""
        ...


@runtime_checkable
class ReportsFeedbackOperations(Protocol):
    """LLM-based AI feedback generation operations.

    This is the AI half of the core educational loop:
        Exercise (instructions) + Submission (user's work) → LLM → AI feedback text

    Route consumer: exercises_api.py
    Implementation: ReportsFeedbackService
    """

    async def generate_feedback(
        self,
        entry: Any,
        exercise: Any,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[str]:
        """Generate AI feedback for a submission entry using an Exercise. Returns Result[str]."""
        ...


@runtime_checkable
class ProgressReportGeneratorOperations(Protocol):
    """Auto-generated progress report operations.

    Generates AI_REPORT entities summarising a user's cross-domain activity
    over a time window. These are system-generated, not submitted by users.

    Route consumer: reports_progress_api.py
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
        """Generate a progress report (EntityType.AI_REPORT). Returns Result[AiReport]."""
        ...


@runtime_checkable
class ReportsScheduleOperations(Protocol):
    """Recurring progress report scheduling operations.

    Route consumer: reports_progress_api.py
    Implementation: ReportsScheduleService
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
