"""
Reports Core Service
========================

Content management operations for Report entities.
Handles categories, tags, publish/archive workflow, and bulk operations.

This service provides the content management layer for Reports,
complementing ReportSubmissionService (file upload) and
ReportsProcessingService (content processing).

ARCHITECTURE (November 2025):
-----------------------------
Report nodes are the SINGLE SOURCE OF TRUTH for submitted content.
Content metadata (categories, tags, status) is stored in Report.metadata.

Services:
- ReportSubmissionService: File upload and storage
- ReportsProcessingService: Content processing orchestration
- ReportsCoreService: Content management (THIS FILE)
- ReportsSearchService: Read-only queries

This pattern mirrors JournalCoreService but operates on Report entities.
"""

import json
from datetime import date, datetime
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.report_events import ReportDeleted
from core.models.report.report import (
    Report,
    ReportDTO,
    ReportStatus,
    ReportType,
)
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_report_date

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
    ) -> None:
        """
        Initialize reports core service.

        Args:
            backend: Backend for Report persistence
            event_bus: Optional event bus for publishing events
            sharing_service: Optional sharing service for access control
        """
        super().__init__(backend, "ReportsCoreService")
        self.event_bus = event_bus
        self.sharing_service = sharing_service

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
