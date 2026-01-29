"""
Assignments Core Service
========================

Content management operations for Assignment entities.
Handles categories, tags, publish/archive workflow, and bulk operations.

This service provides the content management layer for Assignments,
complementing AssignmentSubmissionService (file upload) and
AssignmentProcessorService (content processing).

ARCHITECTURE (November 2025):
-----------------------------
Assignment nodes are the SINGLE SOURCE OF TRUTH for submitted content.
Content metadata (categories, tags, status) is stored in Assignment.metadata.

Services:
- AssignmentSubmissionService: File upload and storage
- AssignmentProcessorService: Content processing orchestration
- AssignmentsCoreService: Content management (THIS FILE)
- AssignmentsQueryService: Read-only queries

This pattern mirrors JournalCoreService but operates on Assignment entities.
"""

import json
from datetime import date, datetime
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.assignment_events import AssignmentDeleted
from core.models.assignment.assignment import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
)
from core.services.base_service import BaseService
from core.services.protocols import BackendOperations
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_assignment_date

# ============================================================================
# ASSIGNMENT CATEGORY ENUM
# ============================================================================
# Categories for content organization (stored in metadata.category)


class AssignmentCategory:
    """
    Categories for assignment content organization.

    Stored in Assignment.metadata['category'].
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


class AssignmentsCoreService(BaseService[BackendOperations[Assignment], Assignment]):
    """
    Core assignment service for content management operations.

    This service focuses on:
    - Retrieving assignments with content
    - Status workflow (publish, archive, draft)
    - Category management
    - Tag management
    - Bulk operations
    - Export functionality

    NOTE: For file submission, use AssignmentSubmissionService.
    NOTE: For processing, use AssignmentProcessorService.


    Source Tag: "assignments_core_service_explicit"

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification
    """

    def __init__(
        self,
        backend: UniversalNeo4jBackend[Assignment] | None = None,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize assignments core service.

        Args:
            backend: Backend for Assignment persistence
            event_bus: Optional event bus for publishing events
        """
        super().__init__(backend, "AssignmentsCoreService")
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Assignment entities."""
        return "Assignment"

    def _validate_assignment_exists(self, assignment: Assignment | None) -> Result[Assignment]:
        """Validate assignment exists."""
        if assignment:
            return Result.ok(assignment)
        return Result.fail(Errors.not_found("Assignment not found"))

    # ========================================================================
    # RETRIEVE
    # ========================================================================

    async def get_assignment(self, uid: str) -> Result[Assignment]:
        """
        Get an assignment by UID.

        Args:
            uid: Assignment unique identifier

        Returns:
            Result containing the assignment or an error
        """
        result = await self.backend.get(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        assignment = result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        return Result.ok(assignment)

    async def get_assignment_for_date(
        self, target_date: date, user_uid: str | None = None
    ) -> Result[Assignment | None]:
        """
        Get the assignment for a specific date.

        Args:
            target_date: Date to find assignment for
            user_uid: Optional user filter

        Returns:
            Result containing the assignment if found, None otherwise
        """
        filters: dict[str, Any] = {}

        # Filter by user if provided
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result.expect_error())

        assignments = result.value
        if not assignments:
            return Result.ok(None)

        # Filter by date (checking created_at date portion)
        for assignment in assignments:
            if assignment.created_at:
                assignment_date = assignment.created_at.date()
                if assignment_date == target_date:
                    return Result.ok(assignment)

        return Result.ok(None)

    async def get_recent_assignments(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        assignment_type: AssignmentType | None = None,
    ) -> Result[list[Assignment]]:
        """
        Get recent assignments.

        Args:
            limit: Maximum number of assignments to return
            user_uid: Optional user filter
            assignment_type: Optional type filter (e.g., JOURNAL, TRANSCRIPT)

        Returns:
            Result containing list of assignments
        """
        filters: dict[str, Any] = {}

        if user_uid:
            filters["user_uid"] = user_uid
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit)
            if result.is_ok:
                assignments_list, _ = result.value
                assignments_list.sort(key=get_assignment_date, reverse=True)
                return Result.ok(assignments_list[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        assignments = result.value or []
        # Sort by created_at descending
        assignments.sort(key=get_assignment_date, reverse=True)

        return Result.ok(assignments[:limit])

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update_assignment(self, uid: str, updates: dict[str, Any]) -> Result[Assignment]:
        """
        Update an assignment.

        Args:
            uid: Assignment UID
            updates: Dictionary of updates to apply

        Returns:
            Result containing updated assignment or error
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
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        return Result.ok(updated)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_assignment(self, uid: str) -> Result[bool]:
        """
        Delete an assignment.

        Args:
            uid: Assignment UID to delete

        Returns:
            Result indicating success or failure
        """
        # Get assignment for event data before deletion
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Delete
        delete_result = await self.backend.delete(uid)

        if delete_result.is_error:
            return Result.fail(delete_result.expect_error())

        if delete_result.value:
            # Publish event
            event = AssignmentDeleted(
                assignment_uid=uid,
                user_uid=assignment.user_uid,
                assignment_type=assignment.assignment_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.debug(f"Published AssignmentDeleted event for {uid}")
            return Result.ok(True)

        return Result.fail(Errors.system("Failed to delete assignment"))

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def publish_assignment(self, uid: str) -> Result[Assignment]:
        """Publish an assignment (set status to completed/published)."""
        return await self._update_assignment_status(uid, AssignmentStatus.COMPLETED)

    async def archive_assignment(self, uid: str) -> Result[Assignment]:
        """Archive an assignment by updating status in metadata."""
        # Get current assignment
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Update metadata to include archived flag
        current_metadata = assignment.metadata or {}
        current_metadata["archived"] = True
        current_metadata["archived_at"] = datetime.now().isoformat()

        return await self.update_assignment(uid, {"metadata": current_metadata})

    async def mark_as_draft(self, uid: str) -> Result[Assignment]:
        """Mark an assignment as draft (submitted, not yet processed)."""
        return await self._update_assignment_status(uid, AssignmentStatus.SUBMITTED)

    async def _update_assignment_status(
        self, uid: str, status: AssignmentStatus
    ) -> Result[Assignment]:
        """Update assignment status."""
        result = await self.backend.update(uid, {"status": status.value})

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        self.logger.info(f"Updated assignment {uid} status to {status.value}")
        return Result.ok(updated)

    # ========================================================================
    # CATEGORY MANAGEMENT
    # ========================================================================

    async def categorize_assignment(self, uid: str, category: str) -> Result[Assignment]:
        """
        Categorize an assignment.

        Categories are stored in Assignment.metadata['category'].

        Args:
            uid: Assignment UID
            category: Category to assign (use AssignmentCategory constants)

        Returns:
            Updated assignment
        """
        # Validate category
        if category not in AssignmentCategory.all_categories():
            self.logger.warning(f"Unknown category '{category}', using anyway")

        # Get current assignment to preserve metadata
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Update metadata with category
        current_metadata = assignment.metadata or {}
        current_metadata["category"] = category

        return await self.update_assignment(uid, {"metadata": current_metadata})

    async def get_assignments_by_category(
        self, category: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Assignment]]:
        """
        Get assignments by category.

        Args:
            category: Category to filter by
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of assignments in category
        """
        # Get all assignments and filter by metadata.category
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)  # Fetch more, filter down
            if result.is_ok:
                assignments_list, _ = result.value
                # Filter by category in metadata
                filtered = [
                    a
                    for a in assignments_list
                    if a.metadata and a.metadata.get("category") == category
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        assignments = result.value or []
        # Filter by category in metadata
        filtered = [a for a in assignments if a.metadata and a.metadata.get("category") == category]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Assignment]:
        """
        Add tags to an assignment.

        Tags are stored in Assignment.metadata['tags'].

        Args:
            uid: Assignment UID
            tags: Tags to add

        Returns:
            Updated assignment
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Merge with existing tags
        current_metadata = assignment.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        new_tags = list(set(current_tags + tags))
        current_metadata["tags"] = new_tags

        return await self.update_assignment(uid, {"metadata": current_metadata})

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Assignment]:
        """
        Remove tags from an assignment.

        Args:
            uid: Assignment UID
            tags: Tags to remove

        Returns:
            Updated assignment
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Remove specified tags
        current_metadata = assignment.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        updated_tags = [t for t in current_tags if t not in tags]
        current_metadata["tags"] = updated_tags

        return await self.update_assignment(uid, {"metadata": current_metadata})

    async def get_assignments_by_tag(
        self, tag: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Assignment]]:
        """
        Get assignments with a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of assignments with the tag
        """
        # Get all assignments and filter by metadata.tags
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)
            if result.is_ok:
                assignments_list, _ = result.value
                # Filter by tag in metadata
                filtered = [
                    a
                    for a in assignments_list
                    if a.metadata and tag in (a.metadata.get("tags") or [])
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        assignments = result.value or []
        # Filter by tag in metadata
        filtered = [a for a in assignments if a.metadata and tag in (a.metadata.get("tags") or [])]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """
        Bulk categorize multiple assignments.

        Args:
            uids: List of assignment UIDs to categorize
            category: Category to assign to all assignments

        Returns:
            Result containing count of successfully updated assignments
        """
        self.logger.info(f"Bulk categorizing {len(uids)} assignments to category: {category}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.categorize_assignment(uid, category)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Updated assignment {uid} to category {category}")
            else:
                error_msg = f"Failed to update assignment {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk categorization completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk categorization completed: {updated_count}/{len(uids)} assignments updated"
        )
        return Result.ok(updated_count)

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """
        Bulk add tags to multiple assignments.

        Args:
            uids: List of assignment UIDs to tag
            tags: List of tags to add to all assignments

        Returns:
            Result containing count of successfully updated assignments
        """
        self.logger.info(f"Bulk tagging {len(uids)} assignments with tags: {tags}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.add_tags(uid, tags)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Added tags {tags} to assignment {uid}")
            else:
                error_msg = f"Failed to tag assignment {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk tagging completed with {len(errors)} errors")

        self.logger.info(f"Bulk tagging completed: {updated_count}/{len(uids)} assignments updated")
        return Result.ok(updated_count)

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """
        Bulk delete multiple assignments.

        Args:
            uids: List of assignment UIDs to delete
            soft_delete: If True, archive instead of permanent delete

        Returns:
            Result containing count of successfully deleted assignments
        """
        self.logger.info(f"Bulk deleting {len(uids)} assignments (soft_delete={soft_delete})")

        deleted_count = 0
        errors = []

        for uid in uids:
            if soft_delete:
                result = await self.archive_assignment(uid)
                success = result.is_ok
            else:
                delete_result = await self.delete_assignment(uid)
                success = delete_result.is_ok and bool(delete_result.value)

            if success:
                deleted_count += 1
                self.logger.debug(f"Deleted assignment {uid}")
            else:
                error_msg = f"Failed to delete assignment {uid}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk deletion completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk deletion completed: {deleted_count}/{len(uids)} assignments deleted"
        )
        return Result.ok(deleted_count)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_to_markdown(self, uid: str) -> Result[str]:
        """
        Export assignment to markdown format.

        Args:
            uid: Assignment UID

        Returns:
            Markdown formatted assignment content
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        assignment = get_result.value
        if not assignment:
            return Result.fail(Errors.not_found("resource", f"Assignment {uid} not found"))

        # Extract metadata
        metadata = assignment.metadata or {}
        category = metadata.get("category", "")
        tags = metadata.get("tags", [])
        title = metadata.get("title", assignment.original_filename)

        # Format as markdown
        md_lines = [
            f"# {title}",
            f"*{assignment.created_at.strftime('%Y-%m-%d')}*" if assignment.created_at else "",
            "",
            assignment.processed_content or "",
            "",
            f"**Type:** {assignment.assignment_type.value}" if assignment.assignment_type else "",
            f"**Category:** {category}" if category else "",
            f"**Tags:** {', '.join(tags)}" if tags else "",
            f"**Status:** {assignment.status.value}" if assignment.status else "",
        ]

        markdown = "\n".join(line for line in md_lines if line)
        return Result.ok(markdown)
