"""
Submission Protocols
====================

Route-facing protocols for the Submission stage of SKUEL's core educational loop:

    Ku → Exercise → Submission → Feedback
                         ↑
               student produces work

Four protocols covering CRUD, processing, sharing, and search across
EntityType.SUBMISSION and EntityType.JOURNAL (both are student work products).

Protocol Responsibilities
--------------------------
    SubmissionOperations         — CRUD, file management, journal creation, content management
    SubmissionProcessingOperations — Processing pipeline (transcription, LLM enrichment)
    SubmissionSharingOperations  — Visibility and sharing control (SHARES_WITH)
    SubmissionSearchOperations   — Cross-type search and statistics

ISP-compliant: each protocol captures only the methods called from routes.

See: /docs/patterns/protocol_architecture.md
See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class SubmissionOperations(Protocol):
    """CRUD, file management, journal creation, and content management.

    Merges the former ReportsSubmissionOperations (CRUD/files) with the
    submission-side of the former ReportsContentOperations (tags, categories,
    journals). Assessment methods belong to FeedbackOperations.

    Route consumers: submissions_api.py (primary), submissions_sharing_api.py
    Implementation: SubmissionsService (CRUD/files) + SubmissionsCoreService (content)
    """

    # ------------------------------------------------------------------
    # FILE UPLOAD & SUBMISSION CRUD
    # ------------------------------------------------------------------

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

    async def list_submissions(
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

    # ------------------------------------------------------------------
    # CONTENT MANAGEMENT
    # ------------------------------------------------------------------

    async def categorize_report(self, uid: str, category: str) -> Result[Any]:
        """Set category on a submission. Returns Result[Submission]."""
        ...

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Add tags to a submission. Returns Result[Submission]."""
        ...

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Any]:
        """Remove tags from a submission. Returns Result[Submission]."""
        ...

    async def publish_report(self, uid: str) -> Result[Any]:
        """Publish a submission (set status to COMPLETED). Returns Result[Submission]."""
        ...

    async def archive_report(self, uid: str) -> Result[Any]:
        """Archive a submission. Returns Result[Submission]."""
        ...

    async def mark_as_draft(self, uid: str) -> Result[Any]:
        """Mark submission as draft. Returns Result[Submission]."""
        ...

    async def get_reports_by_category(
        self,
        category: str,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Get submissions by category. Returns Result[list[Submission]]."""
        ...

    async def get_recent_submissions(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        ku_type: Any | None = None,
    ) -> Result[list[Any]]:
        """Get recent submissions. Returns Result[list[Submission]]."""
        ...

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """Bulk categorize submissions. Returns Result[int] (count updated)."""
        ...

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """Bulk tag submissions. Returns Result[int] (count updated)."""
        ...

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """Bulk delete submissions. Returns Result[int] (count deleted)."""
        ...

    # ------------------------------------------------------------------
    # JOURNAL CREATION (EntityType.JOURNAL — specialized submission)
    # ------------------------------------------------------------------

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
        """Search submissions by text. Returns Result[list[Submission]]."""
        ...


@runtime_checkable
class SubmissionProcessingOperations(Protocol):
    """Submission processing pipeline operations (transcription, LLM enrichment).

    Processes the submission content — transcribes audio, enriches text with LLM.
    This is enrichment OF the submission itself, not feedback ON the submission.

    Route consumers: reports_api.py, reports_ui.py
    Implementation: SubmissionsProcessingService
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
class SubmissionSharingOperations(Protocol):
    """Submission sharing and visibility control operations.

    Manages who can see a submission — SHARES_WITH relationships and
    visibility levels (PRIVATE / SHARED / PUBLIC).

    Route consumer: submissions_sharing_api.py (primary service)
    Implementation: SubmissionsSharingService
    """

    async def share_report(
        self,
        ku_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share a submission with a user. Returns Result[bool]."""
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
        """Get users a submission is shared with. Returns Result[list[dict]]."""
        ...

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Get submissions shared with a user. Returns Result[list[SubmissionDTO]]."""
        ...

    async def set_visibility(
        self,
        ku_uid: str,
        owner_uid: str,
        visibility: Any,
    ) -> Result[bool]:
        """Set submission visibility level. Returns Result[bool]."""
        ...

    async def check_access(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user has access to a submission. Returns Result[bool]."""
        ...


@runtime_checkable
class SubmissionSearchOperations(Protocol):
    """Cross-type search and statistics across submission entity types.

    Route consumer: submissions_api.py
    Implementation: SubmissionsSearchService
    """

    async def search_submissions(
        self,
        user_uid: str,
        query: str,
        ku_type: Any | None = None,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """Search submissions with text and type filters. Returns Result[list[Submission]]."""
        ...

    async def get_report_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        ku_type: Any | None = None,
    ) -> Result[dict[str, Any]]:
        """Get submission statistics for a date range. Returns Result[dict]."""
        ...

    async def get_recent_submissions(
        self,
        user_uid: str,
        ku_type: Any | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """Get recent submissions. Returns Result[list[Submission]]."""
        ...

    async def get_journal_for_report(
        self,
        ku_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """Get journal metadata for a submission entity. Returns Result[dict | None]."""
        ...
