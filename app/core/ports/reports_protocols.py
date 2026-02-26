"""
Reports Protocols
==================

Route-facing protocols for reports operations (submission, processing,
sharing, feedback, scheduling).

These complement the KuOperations protocol in curriculum_protocols.py which
handles backend CRUD. These protocols cover the higher-level content lifecycle:

    ReportsSubmissionOperations — File upload and Ku management
    ReportsContentOperations — Content management (tags, categories, journals, assessments)
    ReportsContentSearchOperations — Cross-type search and statistics
    ReportsSharingOperations — Visibility and sharing control
    ReportsProcessingOperations — Processing pipeline (transcription, LLM)
    ExerciseOperations — LLM instruction templates (exercises)
    ReportsFeedbackOperations — LLM-based feedback generation
    ProgressReportGeneratorOperations — Progress Ku generation
    ReportsScheduleOperations — Recurring progress Ku scheduling

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class ReportsSubmissionOperations(Protocol):
    """File upload and entity management operations.

    Route consumer: ku_api.py (primary service)
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
        fulfills_project_uid: str | None = None,
    ) -> Result[Any]:
        """Submit a file for processing. Returns Result[Ku]."""
        ...

    async def get_report(self, uid: str) -> Result[Any | None]:
        """Get Entity by UID. Returns Result[Ku | None]."""
        ...

    async def list_reports(
        self,
        user_uid: str,
        ku_type: Any | None = None,
        status: Any | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Any]]:
        """List Ku for a user with filters. Returns Result[list[Ku]]."""
        ...

    async def get_file_content(self, ku_uid: str) -> Result[bytes]:
        """Get original file content. Returns Result[bytes]."""
        ...

    async def get_processed_file_content(self, ku_uid: str) -> Result[bytes]:
        """Get processed file content. Returns Result[bytes]."""
        ...

    async def get_report_statistics(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get entity statistics for a user. Returns Result[dict]."""
        ...

    async def update_processed_content(
        self,
        uid: str,
        processed_content: str,
        processed_file_path: str | None = None,
    ) -> Result[Any]:
        """Update processed content on an entity. Returns Result[Ku]."""
        ...


@runtime_checkable
class ReportsContentOperations(Protocol):
    """Content management operations (categories, tags, bulk, journals, assessments).

    Route consumer: ku_api.py, ku_sharing_api.py
    Implementation: KuContentService
    """

    async def get_report(self, uid: str) -> Result[Any]:
        """Get Entity by UID. Returns Result[Ku]."""
        ...

    async def categorize_report(self, uid: str, category: str) -> Result[Any]:
        """Set category on an entity. Returns Result[Ku]."""
        ...

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Add tags to an entity. Returns Result[Ku]."""
        ...

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Remove tags from an entity. Returns Result[Ku]."""
        ...

    async def publish_report(self, uid: str) -> Result[Any]:
        """Publish an entity (set status to COMPLETED). Returns Result[Ku]."""
        ...

    async def archive_report(self, uid: str) -> Result[Any]:
        """Archive an entity. Returns Result[Ku]."""
        ...

    async def mark_as_draft(self, uid: str) -> Result[Any]:
        """Mark Ku as draft. Returns Result[Ku]."""
        ...

    async def get_reports_by_category(
        self,
        category: str,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Get Ku by category. Returns Result[list[Ku]]."""
        ...

    async def get_recent_reports(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        ku_type: Any | None = None,
    ) -> Result[list[Any]]:
        """Get recent Ku. Returns Result[list[Ku]]."""
        ...

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """Bulk categorize entities. Returns Result[int] (count updated)."""
        ...

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """Bulk tag entities. Returns Result[int] (count updated)."""
        ...

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """Bulk delete entities. Returns Result[int] (count deleted)."""
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
        """Create a journal-type Ku (JOURNAL with journal processing). Returns Result[Ku]."""
        ...

    async def search(
        self,
        query: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search Ku (inherited from BaseService). Returns Result[list[Ku]]."""
        ...

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Create a teacher assessment Ku (FEEDBACK_REPORT). Returns Result[Ku]."""
        ...

    async def get_assessments_for_student(
        self,
        student_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get assessment Ku received by a student. Returns Result[list[Ku]]."""
        ...

    async def get_assessments_by_teacher(
        self,
        teacher_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get assessment Ku authored by a teacher. Returns Result[list[Ku]]."""
        ...


@runtime_checkable
class ReportsContentSearchOperations(Protocol):
    """Cross-type query operations for all entity types.

    Route consumer: ku_api.py
    Implementation: KuContentSearchService
    """

    async def search_reports(
        self,
        user_uid: str,
        query: str,
        ku_type: Any | None = None,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search Ku with filters. Returns Result[list[Ku]]."""
        ...

    async def get_report_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        ku_type: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Get entity statistics for a date range. Returns Result[dict]."""
        ...

    async def get_recent_reports(
        self,
        user_uid: str,
        ku_type: Any | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """Get recent Ku. Returns Result[list[Ku]]."""
        ...

    async def get_journal_for_report(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """Get journal data for an entity. Returns Result[dict | None]."""
        ...


@runtime_checkable
class ReportsSharingOperations(Protocol):
    """Content sharing and visibility control operations.

    Route consumer: ku_sharing_api.py (primary service)
    Implementation: ReportsSharingService
    """

    async def share_report(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share an entity with a user. Returns Result[bool]."""
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
        """Get users an entity is shared with. Returns Result[list[dict]]."""
        ...

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get entities shared with user. Returns Result[list[EntityDTO]]."""
        ...

    async def set_visibility(
        self,
        ku_uid: str,
        owner_uid: str,
        visibility: Any,
    ) -> Result[bool]:
        """Set entity visibility level. Returns Result[bool]."""
        ...

    async def check_access(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user has access to entity. Returns Result[bool]."""
        ...


@runtime_checkable
class ReportsProcessingOperations(Protocol):
    """Entity processing pipeline operations (transcription, LLM analysis).

    Route consumer: ku_api.py, ku_ui.py
    Implementation: ReportsProcessingService
    """

    async def process_report(
        self,
        ku_uid: str,
        instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Process an entity through the pipeline. Returns Result[Ku]."""
        ...

    async def reprocess_report(
        self,
        ku_uid: str,
        new_instructions: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Reprocess an entity with new instructions. Returns Result[Ku]."""
        ...


@runtime_checkable
class ExerciseOperations(Protocol):
    """Reusable LLM instruction template operations.

    Route consumer: exercises_api.py (via CRUDRouteFactory)
    Implementation: ExerciseService
    """

    async def create_exercise(
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
        """Create an Exercise. Returns Result[Exercise]."""
        ...

    async def get_exercise(self, uid: str) -> Result[Any | None]:
        """Get exercise by UID. Returns Result[Exercise | None]."""
        ...

    async def list_user_exercises(
        self,
        user_uid: str,
        active_only: bool = True,
    ) -> Result[list[Any]]:
        """List user's exercises. Returns Result[list[Exercise]]."""
        ...

    async def update_exercise(
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
        """Update an exercise. Returns Result[Exercise]."""
        ...

    async def delete_exercise(self, uid: str) -> Result[bool]:
        """Delete an exercise. Returns Result[bool]."""
        ...

    # Backward-compatible aliases for route consumers
    async def get_project(self, uid: str) -> Result[Any | None]:
        """Alias for get_exercise."""
        ...

    async def list_user_projects(
        self, user_uid: str, active_only: bool = True
    ) -> Result[list[Any]]:
        """Alias for list_user_exercises."""
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
        """Alias for update_exercise."""
        ...

    async def delete_project(self, uid: str) -> Result[bool]:
        """Alias for delete_exercise."""
        ...

    # Curriculum linking
    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Link exercise to curriculum KU via REQUIRES_KNOWLEDGE."""
        ...

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Remove REQUIRES_KNOWLEDGE relationship."""
        ...

    async def get_required_knowledge(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get curriculum KUs required by an exercise."""
        ...

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get exercises that require a specific curriculum KU."""
        ...


@runtime_checkable
class ReportsFeedbackOperations(Protocol):
    """LLM-based feedback generation operations.

    Route consumer: ku_projects_api.py
    Implementation: ReportsFeedbackService
    """

    async def generate_feedback(
        self,
        entry: Any,
        project: Any,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Result[str]:
        """Generate AI feedback for a report entry using an Assignment. Returns Result[str]."""
        ...


@runtime_checkable
class ProgressReportGeneratorOperations(Protocol):
    """Progress report generation operations.

    Route consumer: ku_progress_api.py
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
        """Generate a progress Ku (AI_REPORT type). Returns Result[Ku]."""
        ...


@runtime_checkable
class ReportsScheduleOperations(Protocol):
    """Recurring progress report scheduling operations.

    Route consumer: ku_progress_api.py
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
        """Create an entity generation schedule. Returns Result[KuSchedule]."""
        ...

    async def get_user_schedule(self, user_uid: str) -> Result[Any]:
        """Get the user's active entity schedule. Returns Result[KuSchedule | None]."""
        ...

    async def update_schedule(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update a schedule's configuration. Returns Result[KuSchedule]."""
        ...

    async def deactivate_schedule(self, uid: str) -> Result[bool]:
        """Deactivate a schedule (soft delete). Returns Result[bool]."""
        ...
