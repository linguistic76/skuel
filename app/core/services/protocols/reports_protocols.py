"""
Reports Domain Protocols
=========================

Route-facing protocols for the Reports domain services.
ISP-compliant: each protocol captures only the methods called from routes.

Return types use Any where concrete types would create circular imports,
matching the existing pattern in infrastructure_protocols.py.

See: /docs/patterns/protocol_architecture.md
See: /docs/patterns/SHARING_PATTERNS.md
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class ReportSubmissionOperations(Protocol):
    """File upload and report management operations.

    Route consumer: reports_api.py (primary service)
    Implementation: ReportSubmissionService
    """

    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        report_type: Any,
        processor_type: Any = ...,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
    ) -> Result[Any]:
        """Submit a file for processing. Returns Result[Report]."""
        ...

    async def get_report(self, uid: str) -> Result[Any | None]:
        """Get report by UID. Returns Result[Report | None]."""
        ...

    async def list_reports(
        self,
        user_uid: str,
        report_type: Any | None = None,
        status: Any | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Any]]:
        """List reports for a user with filters. Returns Result[list[Report]]."""
        ...

    async def get_file_content(self, report_uid: str) -> Result[bytes]:
        """Get original file content. Returns Result[bytes]."""
        ...

    async def get_processed_file_content(self, report_uid: str) -> Result[bytes]:
        """Get processed file content. Returns Result[bytes]."""
        ...

    async def get_report_statistics(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get report statistics for a user. Returns Result[dict]."""
        ...

    async def update_processed_content(
        self,
        uid: str,
        processed_content: str,
        processed_file_path: str | None = None,
    ) -> Result[Any]:
        """Update processed content on a report. Returns Result[Report]."""
        ...


@runtime_checkable
class ReportsCoreOperations(Protocol):
    """Content management operations (categories, tags, bulk, journals).

    Route consumer: reports_api.py, reports_sharing_api.py
    Implementation: ReportsCoreService
    """

    async def get_report(self, uid: str) -> Result[Any]:
        """Get report by UID. Returns Result[Report]."""
        ...

    async def categorize_report(self, uid: str, category: str) -> Result[Any]:
        """Set category on a report. Returns Result[Report]."""
        ...

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Add tags to a report. Returns Result[Report]."""
        ...

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Remove tags from a report. Returns Result[Report]."""
        ...

    async def publish_report(self, uid: str) -> Result[Any]:
        """Publish a report. Returns Result[Report]."""
        ...

    async def archive_report(self, uid: str) -> Result[Any]:
        """Archive a report. Returns Result[Report]."""
        ...

    async def mark_as_draft(self, uid: str) -> Result[Any]:
        """Mark report as draft. Returns Result[Report]."""
        ...

    async def get_reports_by_category(
        self,
        category: str,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Get reports by category. Returns Result[list[Report]]."""
        ...

    async def get_recent_reports(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        report_type: Any | None = None,
    ) -> Result[list[Any]]:
        """Get recent reports. Returns Result[list[Report]]."""
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
        """Create a journal-type report. Returns Result[Report]."""
        ...

    async def search(
        self,
        query: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search reports (inherited from BaseService). Returns Result[list[Report]]."""
        ...

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Create a teacher assessment for a student. Returns Result[Report]."""
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get assessments received by a student. Returns Result[list[Report]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get assessments authored by a teacher. Returns Result[list[Report]]."""
        ...


@runtime_checkable
class ReportsSearchOperations(Protocol):
    """Cross-domain query operations for all report types.

    Route consumer: reports_api.py
    Implementation: ReportsSearchService
    """

    async def search_reports(
        self,
        user_uid: str,
        query: str,
        report_type: Any | None = None,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search reports with filters. Returns Result[list[Report]]."""
        ...

    async def get_report_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        report_type: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Get report statistics for a date range. Returns Result[dict]."""
        ...

    async def get_recent_reports(
        self,
        user_uid: str,
        report_type: Any | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """Get recent reports. Returns Result[list[Report]]."""
        ...

    async def get_journal_for_report(
        self,
        report_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """Get journal data for a report. Returns Result[dict | None]."""
        ...


@runtime_checkable
class ReportSharingOperations(Protocol):
    """Content sharing and visibility control operations.

    Route consumer: reports_sharing_api.py (primary service)
    Implementation: ReportSharingService
    """

    async def share_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share a report with a user. Returns Result[bool]."""
        ...

    async def unshare_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke sharing access. Returns Result[bool]."""
        ...

    async def get_shared_with_users(
        self,
        report_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get users a report is shared with. Returns Result[list[dict]]."""
        ...

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get reports shared with user. Returns Result[list[ReportDTO]]."""
        ...

    async def set_visibility(
        self,
        report_uid: str,
        owner_uid: str,
        visibility: Any,
    ) -> Result[bool]:
        """Set report visibility level. Returns Result[bool]."""
        ...

    async def check_access(
        self,
        report_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user has access to report. Returns Result[bool]."""
        ...


@runtime_checkable
class ReportsProcessingOperations(Protocol):
    """Report processing pipeline operations.

    Route consumer: reports_api.py, reports_ui.py
    Implementation: ReportsProcessingService
    """

    async def process_report(
        self,
        report_uid: str,
        instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Process a report. Returns Result[Report]."""
        ...

    async def reprocess_report(
        self,
        report_uid: str,
        new_instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Reprocess a report with new instructions. Returns Result[Report]."""
        ...


@runtime_checkable
class ReportProjectOperations(Protocol):
    """Reusable LLM project template operations.

    Route consumer: report_projects_api.py (via CRUDRouteFactory)
    Implementation: ReportProjectService
    """

    async def create_project(
        self,
        user_uid: str,
        name: str,
        instructions: str,
        model: str = "claude-3-5-sonnet-20241022",
        context_notes: list[str] | None = None,
        domain: Any | None = None,
        scope: Any = ...,
        due_date: date | None = None,
        processor_type: Any = ...,
        group_uid: str | None = None,
    ) -> Result[Any]:
        """Create a report project. Returns Result[ReportProjectPure]."""
        ...

    async def get_project(self, uid: str) -> Result[Any | None]:
        """Get project by UID. Returns Result[ReportProjectPure | None]."""
        ...

    async def list_user_projects(
        self,
        user_uid: str,
        active_only: bool = True,
    ) -> Result[list[Any]]:
        """List user's projects. Returns Result[list[ReportProjectPure]]."""
        ...

    async def update_project(
        self,
        uid: str,
        name: str | None = None,
        instructions: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        domain: Any | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Update a project. Returns Result[ReportProjectPure]."""
        ...

    async def delete_project(self, uid: str) -> Result[bool]:
        """Delete a project. Returns Result[bool]."""
        ...


@runtime_checkable
class ReportFeedbackOperations(Protocol):
    """LLM-based feedback generation operations.

    Route consumer: report_projects_api.py
    Implementation: ReportFeedbackService
    """

    async def generate_feedback(
        self,
        entry: Any,
        project: Any,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[str]:
        """Generate AI feedback for an entry using a project. Returns Result[str]."""
        ...


@runtime_checkable
class ProgressReportGeneratorOperations(Protocol):
    """Progress report generation operations.

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
        """Generate a progress report. Returns Result[Report]."""
        ...


@runtime_checkable
class ReportScheduleOperations(Protocol):
    """Report schedule CRUD operations.

    Route consumer: reports_progress_api.py
    Implementation: ReportScheduleService
    """

    async def create_schedule(
        self,
        user_uid: str,
        schedule_type: str = "weekly",
        day_of_week: int = 0,
        domains: list[str] | None = None,
        depth: str = "standard",
    ) -> Result[Any]:
        """Create a report generation schedule. Returns Result[ReportSchedule]."""
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
