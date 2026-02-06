"""
Reports Core Service
========================

Content management operations for Report entities.
Handles categories, tags, publish/archive workflow, bulk operations,
and journal-specific CRUD (create_journal_report, FIFO cleanup, etc.).

ARCHITECTURE (February 2026):
------------------------------
Report nodes are the SINGLE SOURCE OF TRUTH for all submitted content.
Journals are reports with report_type=JOURNAL (merged February 2026).

Services:
- ReportSubmissionService: File upload and storage
- ReportsProcessingService: Content processing orchestration
- ReportsCoreService: Content management + journal CRUD (THIS FILE)
- ReportsSearchService: Read-only queries
- ReportProjectService: LLM instruction projects
- ReportFeedbackService: AI feedback generation
"""

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.report_events import ReportDeleted
from core.models.enums.report_enums import JournalType, ReportStatus, ReportType
from core.models.report.report import (
    Report,
    ReportDTO,
)
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_report_date
from core.utils.uid_generator import UIDGenerator

# ============================================================================
# REPORT CATEGORY ENUM
# ============================================================================
# Categories for content organization (stored in metadata.category)


class ReportCategory:
    """
    Categories for report content organization.

    Stored in Report.metadata['category'].
    Using constants instead of Enum for flexibility with existing data.
    """

    # Time-based
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    # Content type
    REFLECTION = "reflection"
    GRATITUDE = "gratitude"
    GOALS = "goals"
    IDEAS = "ideas"
    DREAMS = "dreams"

    # Life domains
    HEALTH = "health"
    WORK = "work"
    PERSONAL = "personal"
    LEARNING = "learning"
    PROJECT = "project"

    # Catch-all
    OTHER = "other"

    @classmethod
    def all_categories(cls) -> list[str]:
        """Return all valid categories."""
        return [
            cls.DAILY,
            cls.WEEKLY,
            cls.MONTHLY,
            cls.REFLECTION,
            cls.GRATITUDE,
            cls.GOALS,
            cls.IDEAS,
            cls.DREAMS,
            cls.HEALTH,
            cls.WORK,
            cls.PERSONAL,
            cls.LEARNING,
            cls.PROJECT,
            cls.OTHER,
        ]


class ReportsCoreService(BaseService[BackendOperations[Report], Report]):
    """
    Core report service for content management operations.

    This service focuses on:
    - Retrieving reports with content
    - Status workflow (publish, archive, draft)
    - Category management
    - Tag management
    - Bulk operations
    - Export functionality

    NOTE: For file submission, use ReportSubmissionService.
    NOTE: For processing, use ReportsProcessingService.


    Source Tag: "reports_core_service_explicit"

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification
    """

    # =========================================================================
    # DomainConfig (January 2026 Phase 3)
    # =========================================================================
    _config = DomainConfig(
        dto_class=ReportDTO,
        model_class=Report,
        entity_label="Report",
        search_fields=("original_filename", "processed_title", "processed_content"),
        search_order_by="submitted_at",
        category_field="report_type",
        user_ownership_relationship="OWNS",  # User-owned content
    )

    def __init__(
        self,
        backend: UniversalNeo4jBackend[Report] | None = None,
        event_bus: EventBusOperations | None = None,
        sharing_service: Any | None = None,
        transcript_processor: Any | None = None,
    ) -> None:
        """
        Initialize reports core service.

        Args:
            backend: Backend for Report persistence
            event_bus: Optional event bus for publishing events
            sharing_service: Optional sharing service for access control
            transcript_processor: Optional TranscriptProcessorService for AI processing
        """
        super().__init__(backend, "ReportsCoreService")
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.transcript_processor = transcript_processor

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Report entities."""
        return "Report"

    def _validate_report_exists(self, report: Report | None) -> Result[Report]:
        """Validate report exists."""
        if report:
            return Result.ok(report)
        return Result.fail(Errors.not_found("Report not found"))

    # ========================================================================
    # RETRIEVE
    # ========================================================================

    async def get_report(self, uid: str) -> Result[Report]:
        """
        Get a report by UID.

        Args:
            uid: Report unique identifier

        Returns:
            Result containing the report or an error
        """
        result = await self.backend.get(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        report = result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        return Result.ok(report)

    async def get_with_access_check(self, uid: str, user_uid: str) -> Result[Report]:
        """
        Get a report with access control verification.

        Checks if the user can view the report based on:
        - Ownership (user owns the report)
        - Visibility (PUBLIC reports visible to all)
        - Sharing (SHARED reports with SHARES_WITH relationship)

        Args:
            uid: Report unique identifier
            user_uid: User requesting access

        Returns:
            Result containing the report or an error if access denied
        """
        if not self.sharing_service:
            # Fall back to simple get if no sharing service
            return await self.get_report(uid)

        # Check access
        access_result = await self.sharing_service.check_access(uid, user_uid)
        if access_result.is_error:
            return Result.fail(access_result.expect_error())

        if not access_result.value:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # User has access, fetch the report
        return await self.get_report(uid)

    async def get_report_for_date(
        self, target_date: date, user_uid: str | None = None
    ) -> Result[Report | None]:
        """
        Get the report for a specific date.

        Args:
            target_date: Date to find report for
            user_uid: Optional user filter

        Returns:
            Result containing the report if found, None otherwise
        """
        filters: dict[str, Any] = {}

        # Filter by user if provided
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value
        if not reports:
            return Result.ok(None)

        # Filter by date (checking created_at date portion)
        for report in reports:
            if report.created_at:
                report_date = report.created_at.date()
                if report_date == target_date:
                    return Result.ok(report)

        return Result.ok(None)

    async def get_recent_reports(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        report_type: ReportType | None = None,
    ) -> Result[list[Report]]:
        """
        Get recent reports.

        Args:
            limit: Maximum number of reports to return
            user_uid: Optional user filter
            report_type: Optional type filter (e.g., JOURNAL, TRANSCRIPT)

        Returns:
            Result containing list of reports
        """
        filters: dict[str, Any] = {}

        if user_uid:
            filters["user_uid"] = user_uid
        if report_type:
            filters["report_type"] = report_type.value

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit)
            if result.is_ok:
                reports_list = result.value
                reports_list.sort(key=get_report_date, reverse=True)
                return Result.ok(reports_list[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Sort by created_at descending
        reports.sort(key=get_report_date, reverse=True)

        return Result.ok(reports[:limit])

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update_report(self, uid: str, updates: dict[str, Any]) -> Result[Report]:
        """
        Update a report.

        Args:
            uid: Report UID
            updates: Dictionary of updates to apply

        Returns:
            Result containing updated report or error
        """
        # Define allowed fields
        allowed_fields = {
            "status",
            "processed_content",
            "processed_file_path",
            "metadata",
            "processing_error",
            # Journal fields
            "title",
            "content",
            "tags",
            "journal_category",
            "journal_type",
            "content_type",
            "entry_date",
            "mood",
            "energy_level",
            "key_topics",
            "mentioned_people",
            "mentioned_places",
            "action_items",
            "project_uid",
            "feedback",
            "feedback_generated_at",
            "word_count",
            "reading_time_minutes",
        }

        # Filter updates to allowed fields
        filtered_updates = {
            field: value for field, value in updates.items() if field in allowed_fields
        }

        # Serialize metadata to JSON string for Neo4j storage
        # Neo4j cannot store nested dicts/maps as property values
        if "metadata" in filtered_updates and isinstance(filtered_updates["metadata"], dict):
            filtered_updates["metadata"] = json.dumps(filtered_updates["metadata"])

        # Always update updated_at
        filtered_updates["updated_at"] = datetime.now()

        # Perform update
        result = await self.backend.update(uid, filtered_updates)

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        return Result.ok(updated)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_report(self, uid: str) -> Result[bool]:
        """
        Delete a report.

        Args:
            uid: Report UID to delete

        Returns:
            Result indicating success or failure
        """
        # Get report for event data before deletion
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Delete
        delete_result = await self.backend.delete(uid)

        if delete_result.is_error:
            return Result.fail(delete_result.expect_error())

        if delete_result.value:
            # Publish event
            event = ReportDeleted(
                report_uid=uid,
                user_uid=report.user_uid,
                report_type=report.report_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.debug(f"Published ReportDeleted event for {uid}")
            return Result.ok(True)

        return Result.fail(Errors.system("Failed to delete report"))

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def publish_report(self, uid: str) -> Result[Report]:
        """Publish a report (set status to completed/published)."""
        return await self._update_report_status(uid, ReportStatus.COMPLETED)

    async def archive_report(self, uid: str) -> Result[Report]:
        """Archive a report by updating status in metadata."""
        # Get current report
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Update metadata to include archived flag
        current_metadata = report.metadata or {}
        current_metadata["archived"] = True
        current_metadata["archived_at"] = datetime.now().isoformat()

        return await self.update_report(uid, {"metadata": current_metadata})

    async def mark_as_draft(self, uid: str) -> Result[Report]:
        """Mark a report as draft (submitted, not yet processed)."""
        return await self._update_report_status(uid, ReportStatus.SUBMITTED)

    async def _update_report_status(self, uid: str, status: ReportStatus) -> Result[Report]:
        """Update report status."""
        result = await self.backend.update(uid, {"status": status.value})

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        self.logger.info(f"Updated report {uid} status to {status.value}")
        return Result.ok(updated)

    # ========================================================================
    # CATEGORY MANAGEMENT
    # ========================================================================

    async def categorize_report(self, uid: str, category: str) -> Result[Report]:
        """
        Categorize a report.

        Categories are stored in Report.metadata['category'].

        Args:
            uid: Report UID
            category: Category to assign (use ReportCategory constants)

        Returns:
            Updated report
        """
        # Validate category
        if category not in ReportCategory.all_categories():
            self.logger.warning(f"Unknown category '{category}', using anyway")

        # Get current report to preserve metadata
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Update metadata with category
        current_metadata = report.metadata or {}
        current_metadata["category"] = category

        return await self.update_report(uid, {"metadata": current_metadata})

    async def get_reports_by_category(
        self, category: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Report]]:
        """
        Get reports by category.

        Args:
            category: Category to filter by
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of reports in category
        """
        # Get all reports and filter by metadata.category
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)  # Fetch more, filter down
            if result.is_ok:
                reports_list = result.value
                # Filter by category in metadata
                filtered = [
                    a for a in reports_list if a.metadata and a.metadata.get("category") == category
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by category in metadata
        filtered = [a for a in reports if a.metadata and a.metadata.get("category") == category]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Report]:
        """
        Add tags to a report.

        Tags are stored in Report.metadata['tags'].

        Args:
            uid: Report UID
            tags: Tags to add

        Returns:
            Updated report
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Merge with existing tags
        current_metadata = report.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        new_tags = list(set(current_tags + tags))
        current_metadata["tags"] = new_tags

        return await self.update_report(uid, {"metadata": current_metadata})

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Report]:
        """
        Remove tags from a report.

        Args:
            uid: Report UID
            tags: Tags to remove

        Returns:
            Updated report
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Remove specified tags
        current_metadata = report.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        updated_tags = [t for t in current_tags if t not in tags]
        current_metadata["tags"] = updated_tags

        return await self.update_report(uid, {"metadata": current_metadata})

    async def get_reports_by_tag(
        self, tag: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Report]]:
        """
        Get reports with a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of reports with the tag
        """
        # Get all reports and filter by metadata.tags
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)
            if result.is_ok:
                reports_list = result.value
                # Filter by tag in metadata
                filtered = [
                    a for a in reports_list if a.metadata and tag in (a.metadata.get("tags") or [])
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by tag in metadata
        filtered = [a for a in reports if a.metadata and tag in (a.metadata.get("tags") or [])]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """
        Bulk categorize multiple reports.

        Args:
            uids: List of report UIDs to categorize
            category: Category to assign to all reports

        Returns:
            Result containing count of successfully updated reports
        """
        self.logger.info(f"Bulk categorizing {len(uids)} reports to category: {category}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.categorize_report(uid, category)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Updated report {uid} to category {category}")
            else:
                error_msg = f"Failed to update report {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk categorization completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk categorization completed: {updated_count}/{len(uids)} reports updated"
        )
        return Result.ok(updated_count)

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """
        Bulk add tags to multiple reports.

        Args:
            uids: List of report UIDs to tag
            tags: List of tags to add to all reports

        Returns:
            Result containing count of successfully updated reports
        """
        self.logger.info(f"Bulk tagging {len(uids)} reports with tags: {tags}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.add_tags(uid, tags)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Added tags {tags} to report {uid}")
            else:
                error_msg = f"Failed to tag report {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk tagging completed with {len(errors)} errors")

        self.logger.info(f"Bulk tagging completed: {updated_count}/{len(uids)} reports updated")
        return Result.ok(updated_count)

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """
        Bulk delete multiple reports.

        Args:
            uids: List of report UIDs to delete
            soft_delete: If True, archive instead of permanent delete

        Returns:
            Result containing count of successfully deleted reports
        """
        self.logger.info(f"Bulk deleting {len(uids)} reports (soft_delete={soft_delete})")

        deleted_count = 0
        errors = []

        for uid in uids:
            if soft_delete:
                result = await self.archive_report(uid)
                success = result.is_ok
            else:
                delete_result = await self.delete_report(uid)
                success = delete_result.is_ok and bool(delete_result.value)

            if success:
                deleted_count += 1
                self.logger.debug(f"Deleted report {uid}")
            else:
                error_msg = f"Failed to delete report {uid}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk deletion completed with {len(errors)} errors")

        self.logger.info(f"Bulk deletion completed: {deleted_count}/{len(uids)} reports deleted")
        return Result.ok(deleted_count)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_to_markdown(self, uid: str) -> Result[str]:
        """
        Export report to markdown format.

        Args:
            uid: Report UID

        Returns:
            Markdown formatted report content
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        report = get_result.value
        if not report:
            return Result.fail(Errors.not_found("resource", f"Report {uid} not found"))

        # Extract metadata
        metadata = report.metadata or {}
        category = metadata.get("category", "")
        tags = metadata.get("tags", [])
        title = metadata.get("title", report.original_filename)

        # Format as markdown
        md_lines = [
            f"# {title}",
            f"*{report.created_at.strftime('%Y-%m-%d')}*" if report.created_at else "",
            "",
            report.processed_content or "",
            "",
            f"**Type:** {report.report_type.value}" if report.report_type else "",
            f"**Category:** {category}" if category else "",
            f"**Tags:** {', '.join(tags)}" if tags else "",
            f"**Status:** {report.status.value}" if report.status else "",
        ]

        markdown = "\n".join(line for line in md_lines if line)
        return Result.ok(markdown)

    # ========================================================================
    # JOURNAL CRUD (merged from JournalsCoreService — February 2026)
    # ========================================================================

    @with_error_handling("create_journal_report", error_type="database")
    async def create_journal_report(
        self,
        user_uid: str,
        title: str,
        content: str,
        journal_type: JournalType = JournalType.CURATED,
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
        # Source info (for transcribed audio journals)
        source_type: str | None = None,
        source_file: str | None = None,
        transcription_uid: str | None = None,
    ) -> Result[Report]:
        """
        Create a journal-type report.

        Journals are Reports with report_type=JOURNAL. This method handles
        journal-specific creation logic including FIFO cleanup for VOICE journals.

        Args:
            user_uid: User who owns this journal
            title: Journal entry title
            content: Journal body text
            journal_type: VOICE (ephemeral, max 3) or CURATED (permanent)
            journal_category: Optional category for organization
            entry_date: Date of entry (defaults to today)
            tags: Optional tags
            mood: Optional mood indicator
            energy_level: Optional energy level (1-10)
            key_topics: Optional extracted topics
            action_items: Optional action items
            project_uid: Optional ReportProject UID for AI feedback
            metadata: Optional additional metadata
            enforce_fifo: If True, enforce FIFO cleanup for VOICE journals

        Returns:
            Result containing the created Report
        """
        from core.models.enums.report_enums import JournalCategory as JCat

        uid = UIDGenerator.generate_uid("report")

        # Build journal category enum if provided
        category_enum = None
        if journal_category:
            try:
                category_enum = JCat(journal_category)
            except ValueError:
                self.logger.warning(f"Unknown journal category '{journal_category}', ignoring")

        journal = Report(
            uid=uid,
            user_uid=user_uid,
            report_type=ReportType.JOURNAL,
            status=ReportStatus.DRAFT,
            title=title,
            content=content,
            journal_type=journal_type,
            journal_category=category_enum,
            entry_date=entry_date or date.today(),
            tags=tags or [],
            mood=mood,
            energy_level=energy_level,
            key_topics=key_topics or [],
            action_items=action_items or [],
            project_uid=project_uid,
            metadata=metadata,
            source_type=source_type,
            source_file=source_file,
            transcription_uid=transcription_uid,
        )

        result = await self.backend.create(journal)
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Created journal report: {uid} - {title}")

        # Enforce FIFO for voice journals
        if enforce_fifo and journal_type == JournalType.VOICE:
            await self._enforce_voice_fifo(user_uid)

        return Result.ok(journal)

    @with_error_handling("get_journals_by_type", error_type="database")
    async def get_journals_by_type(
        self,
        user_uid: str,
        journal_type: JournalType,
        limit: int = 50,
    ) -> Result[list[Report]]:
        """
        Get journal reports by type for a user.

        Args:
            user_uid: User identifier
            journal_type: VOICE or CURATED
            limit: Maximum number of journals to return

        Returns:
            Result containing list of journal reports, newest first
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            report_type=ReportType.JOURNAL.value,
            journal_type=journal_type.value,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        journals = result.value or []
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_voice_journals", error_type="database")
    async def get_voice_journals(self, user_uid: str, limit: int = 3) -> Result[list[Report]]:
        """Get voice journals (ephemeral, max 3) for a user."""
        return await self.get_journals_by_type(user_uid, JournalType.VOICE, limit)

    @with_error_handling("get_curated_journals", error_type="database")
    async def get_curated_journals(self, user_uid: str, limit: int = 50) -> Result[list[Report]]:
        """Get curated journals (permanent) for a user."""
        return await self.get_journals_by_type(user_uid, JournalType.CURATED, limit)

    @with_error_handling("get_journals_by_date_range", error_type="database")
    async def get_journals_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        journal_type: JournalType | None = None,
        limit: int = 100,
    ) -> Result[list[Report]]:
        """
        Get journal reports within a date range.

        Args:
            user_uid: User identifier
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            journal_type: Optional filter by type
            limit: Maximum number to return

        Returns:
            Result containing list of journal reports
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "report_type": ReportType.JOURNAL.value,
            "entry_date__gte": start_date,
            "entry_date__lte": end_date,
        }

        if journal_type:
            filters["journal_type"] = journal_type.value

        result = await self.backend.find_by(**filters, limit=limit)

        if result.is_error:
            return Result.fail(result.expect_error())

        journals = result.value or []
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals)

    @with_error_handling("promote_to_curated", error_type="database")
    async def promote_to_curated(self, uid: str) -> Result[Report]:
        """
        Promote a voice journal to curated (permanent).

        Changes journal_type from VOICE to CURATED.
        This removes the journal from FIFO cleanup.

        Args:
            uid: Report UID to promote

        Returns:
            Result containing the promoted report
        """
        return await self.update_report(uid, {"journal_type": JournalType.CURATED.value})

    async def get_journal_with_insights(self, uid: str) -> Result[Report | None]:
        """
        Get a journal report with its extracted insights.

        Args:
            uid: Report UID

        Returns:
            Result containing the report (includes insights in model fields)
        """
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        report = result.value
        if not report or not report.is_journal:
            return Result.ok(None)

        return Result.ok(report)

    # ========================================================================
    # FIFO CLEANUP FOR VOICE JOURNALS
    # ========================================================================

    async def process_assignment_submission(
        self,
        report_uid: str,
        project_uid: str,
    ) -> Result[bool]:
        """
        Process a report submitted against an ASSIGNED ReportProject.

        When a student submits against an assigned project:
        1. Create FULFILLS_PROJECT relationship
        2. Look up the project's owner (teacher)
        3. Auto-create SHARES_WITH from teacher to report
        4. Set report status to MANUAL_REVIEW if processor_type is HUMAN

        Called by routes after report creation when project_uid is provided.

        Args:
            report_uid: The submitted report UID
            project_uid: The ReportProject UID this report fulfills

        Returns:
            Result[bool]: True if assignment processing was applied
        """
        from core.models.relationship_names import RelationshipName

        try:
            # Check if the project is ASSIGNED scope
            records, _, _ = await self.backend.driver.execute_query(
                """
                MATCH (project:ReportProject {uid: $project_uid})
                RETURN project.scope as scope,
                       project.user_uid as teacher_uid,
                       project.processor_type as processor_type
                """,
                project_uid=project_uid,
            )

            if not records:
                return Result.ok(False)  # Project not found — not an error, just not an assignment

            scope = records[0]["scope"]
            if scope != "assigned":
                return Result.ok(False)  # Not an assigned project

            teacher_uid = records[0]["teacher_uid"]
            processor_type = records[0]["processor_type"]

            # 1. Create FULFILLS_PROJECT relationship
            await self.backend.driver.execute_query(
                f"""
                MATCH (report:Report {{uid: $report_uid}})
                MATCH (project:ReportProject {{uid: $project_uid}})
                MERGE (report)-[:{RelationshipName.FULFILLS_PROJECT}]->(project)
                RETURN true as success
                """,
                report_uid=report_uid,
                project_uid=project_uid,
            )

            # 2. Auto-share with teacher
            await self.backend.driver.execute_query(
                """
                MATCH (teacher:User {uid: $teacher_uid})
                MATCH (report:Report {uid: $report_uid})
                MERGE (teacher)-[r:SHARES_WITH]->(report)
                SET r.shared_at = datetime($now),
                    r.role = 'teacher'
                RETURN true as success
                """,
                teacher_uid=teacher_uid,
                report_uid=report_uid,
                now=datetime.now().isoformat(),
            )

            # 3. Set status to MANUAL_REVIEW if processor_type is HUMAN
            if processor_type in ("human", "hybrid"):
                await self.backend.driver.execute_query(
                    """
                    MATCH (report:Report {uid: $report_uid})
                    SET report.status = $status,
                        report.processor_type = $processor_type,
                        report.updated_at = datetime($now)
                    RETURN true as success
                    """,
                    report_uid=report_uid,
                    status=ReportStatus.MANUAL_REVIEW.value,
                    processor_type=processor_type,
                    now=datetime.now().isoformat(),
                )

            self.logger.info(
                f"Assignment submission processed: report={report_uid} -> project={project_uid}, "
                f"teacher={teacher_uid}, processor={processor_type}"
            )
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Error processing assignment submission: {e}")
            return Result.ok(False)  # Non-fatal — report was still created

    async def _enforce_voice_fifo(self, user_uid: str) -> Result[int]:
        """
        Enforce FIFO cleanup for voice journals.

        Voice journals have a max retention of 3. When a new voice journal is
        created, delete oldest entries to maintain the limit.

        Args:
            user_uid: User identifier

        Returns:
            Result containing count of journals deleted
        """
        max_retention = JournalType.VOICE.max_retention_count()
        if max_retention is None:
            return Result.ok(0)

        result = await self.backend.find_by(
            user_uid=user_uid,
            report_type=ReportType.JOURNAL.value,
            journal_type=JournalType.VOICE.value,
        )

        if result.is_error:
            self.logger.warning(f"Failed to get voice journals for FIFO: {result.error}")
            return Result.ok(0)

        journals = result.value or []
        if len(journals) <= max_retention:
            return Result.ok(0)

        # Sort by created_at ascending (oldest first)
        journals.sort(key=_get_created_at_key)

        # Delete oldest journals that exceed the limit
        to_delete = journals[: len(journals) - max_retention]
        deleted_count = 0

        for journal in to_delete:
            delete_result = await self.backend.delete(journal.uid, cascade=True)
            if delete_result.is_ok and delete_result.value:
                deleted_count += 1
                self.logger.info(f"FIFO cleanup: deleted voice journal {journal.uid}")

        return Result.ok(deleted_count)

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """
        Create journal-type report when transcription completes.

        Pipeline:
        1. Try AI processing via TranscriptProcessorService (if available)
        2. Fall back to raw transcript if AI fails
        3. Create Report with report_type=JOURNAL via create_journal_report()
        4. Triggers FIFO cleanup for VOICE journals

        Args:
            event: TranscriptionCompleted event with transcript data

        Note:
            Errors logged but not raised — journal creation is best-effort
            to prevent transcription failure if journal creation fails.
        """
        from core.models.enums.report_enums import JournalType

        try:
            self.logger.info(
                f"Creating journal report from transcription {event.transcription_uid} "
                f"for user {event.user_uid}"
            )

            # Default to raw transcript
            title = f"Voice Journal - {event.occurred_at.strftime('%Y-%m-%d %H:%M')}"
            content = event.transcript_text
            key_topics: list[str] = []
            action_items: list[str] = []
            summary: str | None = None

            # Try AI processing if available
            if self.transcript_processor:
                insights_result = await self.transcript_processor.process_transcript(
                    raw_transcript=event.transcript_text,
                    user_uid=event.user_uid,
                )

                if insights_result.is_ok:
                    insights = insights_result.value
                    title = insights.title or title
                    content = insights.formatted_content or content
                    key_topics = insights.themes or []
                    action_items = insights.action_items or []
                    summary = insights.summary
                    self.logger.debug(f"AI processing successful for {event.transcription_uid}")
                else:
                    self.logger.warning(
                        f"AI processing failed for {event.transcription_uid}: "
                        f"{insights_result.error}. Using raw transcript."
                    )

            # Build metadata
            metadata: dict[str, str] = {}
            if summary:
                metadata["summary"] = summary

            # Create journal report (triggers FIFO for VOICE journals)
            result = await self.create_journal_report(
                user_uid=event.user_uid,
                title=title,
                content=content,
                journal_type=JournalType.VOICE,
                key_topics=key_topics if key_topics else None,
                action_items=action_items if action_items else None,
                source_type="audio",
                source_file=event.audio_file_path,
                transcription_uid=event.transcription_uid,
            )

            if result.is_ok:
                self.logger.info(
                    f"Created journal report {result.value.uid} from transcription "
                    f"{event.transcription_uid}"
                )
            else:
                self.logger.error(
                    f"Failed to create journal report from {event.transcription_uid}: "
                    f"{result.error}"
                )

        except Exception as e:
            self.logger.error(
                f"Error handling TranscriptionCompleted for {event.transcription_uid}: {e!s}"
            )


def _get_entry_date_key(report: Report) -> date:
    """Get entry_date from report for sorting, with fallback to date.min."""
    return report.entry_date if report.entry_date else date.min


def _get_created_at_key(report: Report) -> datetime:
    """Get created_at from report for sorting, with fallback to datetime.min."""
    return report.created_at if report.created_at else datetime.min
