"""
Submissions Core Service
========================

Content management operations for submission entities.
Handles categories, tags, publish/archive workflow, bulk operations,
journal CRUD, and the Exercise → Submission link that drives the
core educational loop.

The Core Educational Loop
--------------------------
SKUEL's fundamental process for applied learning:

    Exercise (shared template, admin/teacher-created)
        ↓  user submits work against it
    Submission (user-owned, EntityType.SUBMISSION)
        ↓  process_exercise_submission() called with exercise_uid
        ↓  creates FULFILLS_EXERCISE relationship
        ↓  auto-shares with teacher (SHARES_WITH role='teacher')
    Teacher review → SubmissionFeedback (EntityType.SUBMISSION_FEEDBACK)

The Exercise is a shared curriculum template. The moment a user creates
a Submission against it, the Submission is exclusively their own work product —
user-owned, privately scoped by default.

Four Entity Types
--------------------------
    SUBMISSION      → Student's work submitted against an Exercise (user-owned)
    JOURNAL         → Voice/text journal entries with metadata (user-owned)
    ACTIVITY_REPORT     → System-generated progress reports (user-owned)
    SUBMISSION_FEEDBACK → Teacher feedback on a Submission (teacher-owned)

Journal-specific fields (mood, energy_level, entry_date, etc.) live in metadata.
max_retention controls FIFO cleanup for voice journals (None = permanent).

Service Responsibilities
--------------------------
- SubmissionsService: File upload and storage
- SubmissionsProcessingService: Content processing orchestration
- SubmissionsCoreService: Content management + journal CRUD + exercise linking (THIS FILE)
- SubmissionsSearchService: Read-only queries
- ExerciseService: Exercise CRUD (in exercises package)
- FeedbackService: AI feedback generation
"""

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted

from core.events import publish_event
from core.events.submission_events import AssessmentCreated, SubmissionDeleted
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.feedback.submission_feedback import SubmissionFeedback
from core.models.relationship_names import RelationshipName
from core.models.submissions.journal import Journal
from core.models.submissions.submission_dto import SubmissionDTO
from core.ports import BackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_report_date
from core.utils.uid_generator import UIDGenerator

# ============================================================================
# KU CATEGORY CONSTANTS
# ============================================================================
# Categories for content organization (stored in metadata['category'])


class ReportCategory:
    """
    Categories for submission content organization.

    Stored in Ku.metadata['category'].
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


class SubmissionsCoreService(BaseService[BackendOperations[Entity], Entity]):
    """
    Core submission service for content management operations.

    This service focuses on:
    - Retrieving Ku entities with content
    - Status workflow (publish, archive, draft)
    - Category management
    - Tag management
    - Bulk operations
    - Export functionality
    - Journal CRUD (create_journal_ku, FIFO cleanup)
    - Assessment CRUD (teacher feedback)

    NOTE: For file submission, use SubmissionsService.
    NOTE: For processing, use SubmissionsProcessingService.
    """

    # =========================================================================
    # DomainConfig
    # =========================================================================
    _config = DomainConfig(
        dto_class=SubmissionDTO,
        model_class=Entity,
        entity_label="Entity",
        search_fields=("title", "original_filename", "processed_content"),
        search_order_by="created_at",
        category_field="entity_type",
        user_ownership_relationship=RelationshipName.OWNS,  # User-owned content
    )

    def __init__(
        self,
        backend: BackendOperations[SubmissionEntity] | None = None,
        event_bus: EventBusOperations | None = None,
        sharing_service: Any | None = None,
        content_enrichment: Any | None = None,
    ) -> None:
        """
        Initialize Ku core service.

        Args:
            backend: Backend for Ku persistence
            event_bus: Optional event bus for publishing events
            sharing_service: Optional sharing service for access control
            content_enrichment: Optional ContentEnrichmentService for AI processing
        """
        super().__init__(backend, "SubmissionsCoreService")
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.content_enrichment = content_enrichment

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Entity nodes."""
        return "Entity"

    def _validate_submission_exists(
        self, submission: SubmissionEntity | None
    ) -> Result[SubmissionEntity]:
        """Validate entity exists."""
        if submission:
            return Result.ok(submission)
        return Result.fail(Errors.not_found("Submission not found"))

    # ========================================================================
    # RETRIEVE
    # ========================================================================

    async def get_submission(self, uid: str) -> Result[SubmissionEntity]:
        """
        Get a submission by UID.

        Args:
            uid: Ku unique identifier

        Returns:
            Result containing the entity or an error
        """
        result = await self.backend.get(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        submission = result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        return Result.ok(submission)

    async def get_with_access_check(self, uid: str, user_uid: str) -> Result[SubmissionEntity]:
        """
        Get a submission with access control verification.

        Checks if the user can view the entity based on:
        - Ownership (user owns the Ku)
        - Visibility (PUBLIC Ku visible to all)
        - Sharing (SHARED submission with SHARES_WITH relationship)

        Args:
            uid: Ku unique identifier
            user_uid: User requesting access

        Returns:
            Result containing the entity or an error if access denied
        """
        if not self.sharing_service:
            # Fall back to simple get if no sharing service
            return await self.get_submission(uid)

        # Check access
        access_result = await self.sharing_service.check_access(uid, user_uid)
        if access_result.is_error:
            return Result.fail(access_result.expect_error())

        if not access_result.value:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # User has access, fetch the entity
        return await self.get_submission(uid)

    async def get_submission_for_date(
        self, target_date: date, user_uid: str | None = None
    ) -> Result[SubmissionEntity | None]:
        """
        Get the submission for a specific date.

        Args:
            target_date: Date to find submission for
            user_uid: Optional user filter

        Returns:
            Result containing the entity if found, None otherwise
        """
        filters: dict[str, Any] = {}

        # Filter by user if provided
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result.expect_error())

        submissions = result.value
        if not submissions:
            return Result.ok(None)

        # Filter by date (checking created_at date portion)
        for submission in submissions:
            if submission.created_at:
                submission_date = submission.created_at.date()
                if submission_date == target_date:
                    return Result.ok(submission)

        return Result.ok(None)

    async def get_recent_submissions(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        entity_type: EntityType | None = None,
    ) -> Result[list[SubmissionEntity]]:
        """
        Get recent Ku entities.

        Args:
            limit: Maximum number of Ku entities to return
            user_uid: Optional user filter
            entity_type: Optional type filter (e.g., SUBMISSION, ACTIVITY_REPORT)

        Returns:
            Result containing list of Ku entities
        """
        filters: dict[str, Any] = {}

        if user_uid:
            filters["user_uid"] = user_uid
        if entity_type:
            filters["entity_type"] = entity_type.value

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit)
            if result.is_ok:
                kus_list = result.value
                kus_list.sort(key=get_report_date, reverse=True)
                return Result.ok(kus_list[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        submissions = result.value or []
        # Sort by created_at descending
        submissions.sort(key=get_report_date, reverse=True)

        return Result.ok(submissions[:limit])

    async def get_public_submissions(
        self,
        limit: int = 50,
        user_uid: str | None = None,
    ) -> Result[list[SubmissionEntity]]:
        """
        Get submissions with visibility=PUBLIC.

        Applies the visibility filter at query time so limit is honoured
        after filtering — callers always receive up to `limit` public results.

        Args:
            limit: Maximum number of submissions to return
            user_uid: Optional owner filter (portfolio view for a specific user)

        Returns:
            Result containing list of public submissions, newest first
        """
        from core.models.enums.metadata_enums import Visibility

        filters: dict[str, Any] = {"visibility": Visibility.PUBLIC.value}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(limit=limit, **filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        submissions = result.value or []
        submissions.sort(key=get_report_date, reverse=True)
        return Result.ok(submissions)

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update_submission(
        self, uid: str, updates: dict[str, Any]
    ) -> Result[SubmissionEntity]:
        """
        Update an entity.

        Args:
            uid: Submission UID
            updates: Dictionary of updates to apply

        Returns:
            Result containing updated submission or error
        """
        # Define allowed fields (Entity model first-class fields only)
        allowed_fields = {
            "status",
            "processed_content",
            "processed_file_path",
            "metadata",
            "processing_error",
            "title",
            "content",
            "summary",
            "tags",
            "feedback",
            "feedback_generated_at",
            "word_count",
            "visibility",
            "instructions",
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
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        return Result.ok(updated)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_submission(self, uid: str) -> Result[bool]:
        """
        Delete an entity.

        Args:
            uid: Report UID to delete

        Returns:
            Result indicating success or failure
        """
        # Get submission for event data before deletion
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Delete
        delete_result = await self.backend.delete(uid)

        if delete_result.is_error:
            return Result.fail(delete_result.expect_error())

        if delete_result.value:
            from core.models.user_owned_entity import UserOwnedEntity

            event = SubmissionDeleted(
                submission_uid=uid,
                user_uid=submission.user_uid if isinstance(submission, UserOwnedEntity) else None,
                entity_type=submission.entity_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.debug(f"Published SubmissionDeleted event for {uid}")
            return Result.ok(True)

        return Result.fail(Errors.system("Failed to delete Ku"))

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def publish_submission(self, uid: str) -> Result[SubmissionEntity]:
        """Publish an entity (set status to completed/published)."""
        return await self._update_submission_status(uid, EntityStatus.COMPLETED)

    async def archive_submission(self, uid: str) -> Result[SubmissionEntity]:
        """Archive a submission by updating status in metadata."""
        # Get current entity
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Update metadata to include archived flag
        current_metadata = submission.metadata or {}
        current_metadata["archived"] = True
        current_metadata["archived_at"] = datetime.now().isoformat()

        return await self.update_submission(uid, {"metadata": current_metadata})

    async def mark_as_draft(self, uid: str) -> Result[SubmissionEntity]:
        """Mark an entity as draft."""
        return await self._update_submission_status(uid, EntityStatus.DRAFT)

    async def _update_submission_status(
        self, uid: str, status: EntityStatus
    ) -> Result[SubmissionEntity]:
        """Update entity status."""
        result = await self.backend.update(uid, {"status": status.value})

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        self.logger.info(f"Updated submission {uid} status to {status.value}")
        return Result.ok(updated)

    # ========================================================================
    # CATEGORY MANAGEMENT
    # ========================================================================

    async def categorize_submission(self, uid: str, category: str) -> Result[SubmissionEntity]:
        """
        Categorize an entity.

        Categories are stored in Ku.metadata['category'].

        Args:
            uid: Submission UID
            category: Category to assign (use ReportCategory constants)

        Returns:
            Updated submission
        """
        # Validate category
        if category not in ReportCategory.all_categories():
            self.logger.warning(f"Unknown category '{category}', using anyway")

        # Get current submission to preserve metadata
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Update metadata with category
        current_metadata = submission.metadata or {}
        current_metadata["category"] = category

        return await self.update_submission(uid, {"metadata": current_metadata})

    async def get_submissions_by_category(
        self, category: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[SubmissionEntity]]:
        """
        Get Ku entities by category.

        Args:
            category: Category to filter by
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of Ku entities in category
        """
        # Get all entities and filter by metadata.category
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)  # Fetch more, filter down
            if result.is_ok:
                kus_list = result.value
                # Filter by category in metadata
                filtered = [
                    k for k in kus_list if k.metadata and k.metadata.get("category") == category
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by category in metadata
        filtered = [k for k in reports if k.metadata and k.metadata.get("category") == category]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    async def add_tags(self, uid: str, tags: list[str]) -> Result[SubmissionEntity]:
        """
        Add tags to an entity.

        Tags are stored in Ku.metadata['tags'].

        Args:
            uid: Submission UID
            tags: Tags to add

        Returns:
            Updated submission
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Merge with existing tags
        current_metadata = submission.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        new_tags = list(set(current_tags + tags))
        current_metadata["tags"] = new_tags

        return await self.update_submission(uid, {"metadata": current_metadata})

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[SubmissionEntity]:
        """
        Remove tags from an entity.

        Args:
            uid: Submission UID
            tags: Tags to remove

        Returns:
            Updated submission
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Remove specified tags
        current_metadata = submission.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        updated_tags = [t for t in current_tags if t not in tags]
        current_metadata["tags"] = updated_tags

        return await self.update_submission(uid, {"metadata": current_metadata})

    async def get_submissions_by_tag(
        self, tag: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[SubmissionEntity]]:
        """
        Get Ku entities with a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of Ku entities with the tag
        """
        # Get all entities and filter by metadata.tags
        filters: dict[str, Any] = {}
        if user_uid:
            filters["user_uid"] = user_uid

        if filters:
            result = await self.backend.find_by(**filters)
        else:
            result = await self.backend.list(limit=limit * 2)
            if result.is_ok:
                kus_list = result.value
                # Filter by tag in metadata
                filtered = [
                    k for k in kus_list if k.metadata and tag in (k.metadata.get("tags") or [])
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by tag in metadata
        filtered = [k for k in reports if k.metadata and tag in (k.metadata.get("tags") or [])]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """
        Bulk categorize multiple Ku entities.

        Args:
            uids: List of submission UIDs to categorize
            category: Category to assign to all entities

        Returns:
            Result containing count of successfully updated entities
        """
        self.logger.info(
            f"Bulk categorizing {len(uids)} submission entities to category: {category}"
        )

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.categorize_submission(uid, category)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Updated submission {uid} to category {category}")
            else:
                error_msg = f"Failed to update Ku {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk categorization completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk categorization completed: {updated_count}/{len(uids)} submission entities updated"
        )
        return Result.ok(updated_count)

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """
        Bulk add tags to multiple Ku entities.

        Args:
            uids: List of submission UIDs to tag
            tags: List of tags to add to all entities

        Returns:
            Result containing count of successfully updated entities
        """
        self.logger.info(f"Bulk tagging {len(uids)} submission entities with tags: {tags}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.add_tags(uid, tags)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Added tags {tags} to Ku {uid}")
            else:
                error_msg = f"Failed to tag Ku {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk tagging completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk tagging completed: {updated_count}/{len(uids)} submission entities updated"
        )
        return Result.ok(updated_count)

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """
        Bulk delete multiple Ku entities.

        Args:
            uids: List of submission UIDs to delete
            soft_delete: If True, archive instead of permanent delete

        Returns:
            Result containing count of successfully deleted entities
        """
        self.logger.info(
            f"Bulk deleting {len(uids)} submission entities (soft_delete={soft_delete})"
        )

        deleted_count = 0
        errors = []

        for uid in uids:
            if soft_delete:
                result = await self.archive_submission(uid)
                success = result.is_ok
            else:
                delete_result = await self.delete_submission(uid)
                success = delete_result.is_ok and bool(delete_result.value)

            if success:
                deleted_count += 1
                self.logger.debug(f"Deleted submission {uid}")
            else:
                error_msg = f"Failed to delete Ku {uid}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk deletion completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk deletion completed: {deleted_count}/{len(uids)} submission entities deleted"
        )
        return Result.ok(deleted_count)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_to_markdown(self, uid: str) -> Result[str]:
        """
        Export submission to markdown format.

        Args:
            uid: Submission UID

        Returns:
            Markdown formatted submission content
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        # Extract metadata
        metadata = submission.metadata or {}
        category = metadata.get("category", "")
        tags_list = metadata.get("tags", [])

        # Format as markdown
        md_lines = [
            f"# {submission.title}",
            f"*{submission.created_at.strftime('%Y-%m-%d')}*" if submission.created_at else "",
            "",
            getattr(submission, "processed_content", None) or submission.content or "",
            "",
            f"**Type:** {submission.entity_type.value}" if submission.entity_type else "",
            f"**Category:** {category}" if category else "",
            f"**Tags:** {', '.join(tags_list)}" if tags_list else "",
            f"**Status:** {submission.status.value}" if submission.status else "",
        ]

        markdown = "\n".join(line for line in md_lines if line)
        return Result.ok(markdown)

    # ========================================================================
    # JOURNAL CRUD (merged from JournalsCoreService — February 2026)
    #
    # Journals are SUBMISSION entities with journal-specific fields in metadata:
    #   metadata['journal_type'], metadata['journal_category'],
    #   metadata['entry_date'], metadata['mood'], metadata['energy_level'],
    #   metadata['key_topics'], metadata['action_items'],
    #   metadata['source_type'], metadata['source_file'],
    #   metadata['transcription_uid']
    # ========================================================================

    async def _count_journals_for_date(self, user_uid: str, entry_date: date) -> int:
        """Count journals owned by user on the given calendar day (for sequence ordering)."""

        day_start = datetime(entry_date.year, entry_date.month, entry_date.day, tzinfo=UTC)
        day_end = datetime(
            entry_date.year, entry_date.month, entry_date.day, 23, 59, 59, tzinfo=UTC
        )
        query = """
            MATCH (u:User {uid: $user_uid})-[:OWNS]->(j:Entity {entity_type: 'journal'})
            WHERE j.created_at >= $day_start AND j.created_at <= $day_end
            RETURN count(j) AS total
        """
        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "day_start": day_start, "day_end": day_end},
        )
        if result.is_error or not result.value:
            return 0
        return int(result.value[0]["total"]) if result.value else 0

    async def generate_journal_title(
        self, user_uid: str, entry_date: date | None = None
    ) -> Result[str]:
        """Generate canonical journal title with sequence number for the given day.

        Format: Journal — {user_id} — {Mar 02, 2026} — #{order}
        """
        resolved_date = entry_date or date.today()
        existing_count = await self._count_journals_for_date(user_uid, resolved_date)
        return Result.ok(Journal.generate_title(user_uid, resolved_date, order=existing_count + 1))

    @with_error_handling("create_journal_entry", error_type="database")
    async def create_journal_entry(
        self,
        user_uid: str,
        title: str | None = None,
        content: str = "",
        max_retention: int | None = None,
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
    ) -> Result[Journal]:
        """
        Create a journal-type Ku (JOURNAL with journal metadata).

        Journals are Ku entities with entity_type=JOURNAL. max_retention controls
        FIFO cleanup: when set (e.g., 3), oldest journals are deleted to
        maintain the limit. When None, journals are permanent.

        Args:
            user_uid: User who owns this journal
            title: Journal entry title (auto-generated if None)
            content: Journal body text
            max_retention: FIFO cleanup limit (None = permanent, 3 = keep last 3)
            entry_date: Date of entry (defaults to today)
            tags: Optional tags
            mood: Optional mood indicator
            energy_level: Optional energy level (1-10)
            key_topics: Optional extracted topics
            action_items: Optional action items
            project_uid: Optional Assignment UID for AI feedback
            metadata: Optional additional metadata
            enforce_fifo: If True, enforce FIFO cleanup when max_retention is set

        Returns:
            Result containing the created submission
        """
        resolved_date = entry_date or date.today()
        if title is None:
            title_result = await self.generate_journal_title(user_uid, resolved_date)
            title = title_result.value if title_result.is_ok else f"Journal — {resolved_date}"

        uid = UIDGenerator.generate_uid("je", title)

        # Build journal metadata
        journal_metadata = metadata.copy() if metadata else {}
        journal_metadata["entry_date"] = resolved_date.isoformat()
        if mood:
            journal_metadata["mood"] = mood
        if energy_level is not None:
            journal_metadata["energy_level"] = energy_level
        if key_topics:
            journal_metadata["key_topics"] = key_topics
        if action_items:
            journal_metadata["action_items"] = action_items
        if project_uid:
            journal_metadata["project_uid"] = project_uid
        if source_type:
            journal_metadata["source_type"] = source_type
        if source_file:
            journal_metadata["source_file"] = source_file
        if transcription_uid:
            journal_metadata["transcription_uid"] = transcription_uid

        journal = Journal(
            uid=uid,
            title=title,
            entity_type=EntityType.JOURNAL,
            user_uid=user_uid,
            status=EntityStatus.DRAFT,
            content=content,
            max_retention=max_retention,
            tags=tuple(tags) if tags else (),
            metadata=journal_metadata,
        )

        result = await self.backend.create(journal)
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Created journal submission: {uid} - {title}")

        # Enforce FIFO for ephemeral journals
        if enforce_fifo and max_retention is not None:
            await self._enforce_fifo(user_uid, max_retention)

        return Result.ok(journal)

    @with_error_handling("get_ephemeral_journals", error_type="database")
    async def get_ephemeral_journals(self, user_uid: str, limit: int = 10) -> Result[list[Journal]]:
        """Get journals with FIFO retention (max_retention is set) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        reports = result.value or []
        journals = [k for k in reports if getattr(k, "max_retention", None) is not None]
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_permanent_journals", error_type="database")
    async def get_permanent_journals(self, user_uid: str, limit: int = 50) -> Result[list[Journal]]:
        """Get permanent journals (no FIFO retention) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        reports = result.value or []
        journals = [k for k in reports if getattr(k, "max_retention", None) is None]
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_journals_by_date_range", error_type="database")
    async def get_journals_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        limit: int = 100,
    ) -> Result[list[Journal]]:
        """
        Get journal submission entities within a date range.

        Args:
            user_uid: User identifier
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number to return

        Returns:
            Result containing list of journal submission entities
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        submissions = result.value or []
        journals = []
        for submission in submissions:
            entry_date_str = (submission.metadata or {}).get("entry_date")
            if entry_date_str:
                try:
                    entry = date.fromisoformat(entry_date_str)
                    if start_date <= entry <= end_date:
                        journals.append(submission)
                except (ValueError, TypeError):
                    pass

        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("make_permanent", error_type="database")
    async def make_permanent(self, uid: str) -> Result[SubmissionEntity]:
        """
        Make a journal permanent by clearing its max_retention.

        Removes the journal from FIFO cleanup.

        Args:
            uid: Report UID to make permanent

        Returns:
            Result containing the updated submission
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        submission = get_result.value
        if not submission:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        return await self.update_submission(uid, {"max_retention": None})

    async def get_journal_with_insights(self, uid: str) -> Result[Journal | None]:
        """
        Get a journal submission with its extracted insights.

        Args:
            uid: Submission UID

        Returns:
            Result containing the entity (includes insights in metadata)
        """
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        submission = result.value
        if not submission or submission.entity_type != EntityType.JOURNAL:
            return Result.ok(None)

        return Result.ok(submission)

    # ========================================================================
    # FIFO CLEANUP FOR VOICE JOURNALS
    # ========================================================================

    async def process_exercise_submission(
        self,
        ku_uid: str,
        exercise_uid: str,
    ) -> Result[bool]:
        """
        Process an entity submitted against an ASSIGNED Exercise.

        When a student submits against an assigned exercise:
        1. Create FULFILLS_EXERCISE relationship
        2. Look up the exercise's owner (teacher)
        3. Auto-create SHARES_WITH from teacher to Ku
        4. Set Ku status to SUBMITTED if processor_type is HUMAN

        Called by routes after Ku creation when exercise_uid is provided.

        Args:
            ku_uid: The submitted submission UID
            exercise_uid: The Exercise UID this Ku fulfills

        Returns:
            Result[bool]: True if exercise processing was applied
        """
        from core.models.relationship_names import RelationshipName

        # Check if the exercise is ASSIGNED scope and get group info
        # Accepts both Exercise and RevisedExercise entity types
        exercise_result = await self.backend.execute_query(
            """
            MATCH (exercise:Entity {uid: $exercise_uid})
            WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
            OPTIONAL MATCH (exercise)-[:FOR_GROUP]->(g:Group)
            RETURN exercise.entity_type as exercise_entity_type,
                   exercise.scope as scope,
                   exercise.user_uid as teacher_uid,
                   exercise.student_uid as student_uid,
                   exercise.title as exercise_title,
                   g.uid as group_uid
            """,
            {"exercise_uid": exercise_uid},
        )

        if exercise_result.is_error:
            self.logger.error(f"Error querying exercise: {exercise_result.error}")
            return Result.ok(False)  # Non-fatal

        records = exercise_result.value or []
        if not records:
            return Result.ok(False)  # Exercise not found — not an error

        exercise_entity_type = records[0]["exercise_entity_type"]
        teacher_uid = records[0]["teacher_uid"]
        exercise_title = records[0].get("exercise_title") or ""

        if exercise_entity_type == "revised_exercise":
            # RevisedExercise path: always "assigned", targets a specific student
            re_student_uid = records[0]["student_uid"]

            # Verify submitting student matches the targeted student
            submitter_result = await self.backend.execute_query(
                """
                MATCH (student:User)-[:OWNS]->(ku:Entity {uid: $ku_uid})
                RETURN student.uid as student_uid
                """,
                {"ku_uid": ku_uid},
            )
            if submitter_result.is_error:
                self.logger.error(f"Error querying submitter: {submitter_result.error}")
                return Result.ok(False)

            submitter_records = submitter_result.value or []
            if not submitter_records:
                return Result.ok(False)

            submitter_uid = submitter_records[0]["student_uid"]
            if submitter_uid != re_student_uid:
                self.logger.warning(
                    f"Student {submitter_uid} submitted against RevisedExercise "
                    f"{exercise_uid} targeting {re_student_uid}"
                )
                return Result.ok(False)
            # Skip group membership check — RevisedExercises target students directly
        else:
            # Standard Exercise path: check scope and group membership
            scope = records[0]["scope"]
            if scope != "assigned":
                return Result.ok(False)  # Not an assigned exercise

            group_uid = records[0]["group_uid"]

            # Verify student is a member of the target group (if group exists)
            if group_uid:
                student_result = await self.backend.execute_query(
                    """
                    MATCH (student:User)-[:OWNS]->(ku:Entity {uid: $ku_uid})
                    OPTIONAL MATCH (student)-[:MEMBER_OF]->(g:Group {uid: $group_uid})
                    RETURN student.uid as student_uid, g.uid as member_of_group
                    """,
                    {"ku_uid": ku_uid, "group_uid": group_uid},
                )

                if student_result.is_error:
                    self.logger.error(f"Error verifying student membership: {student_result.error}")
                    return Result.ok(False)

                student_records = student_result.value or []
                if student_records and not student_records[0]["member_of_group"]:
                    student_uid = student_records[0]["student_uid"]
                    self.logger.warning(
                        f"Student {student_uid} is not a member of group {group_uid} "
                        f"for exercise {exercise_uid}"
                    )
                    return Result.ok(False)

        # 0. Auto-generate canonical title from exercise
        if exercise_title:
            student_uid_result = await self.backend.execute_query(
                """
                MATCH (student:User)-[:OWNS]->(ku:Entity {uid: $ku_uid})
                RETURN student.uid as student_uid
                """,
                {"ku_uid": ku_uid},
            )
            if not student_uid_result.is_error:
                student_uid_records = student_uid_result.value or []
                if student_uid_records:
                    submitter_uid = student_uid_records[0]["student_uid"]

                    # Count prior submissions already linked to this exercise by this student
                    prior_count_result = await self.backend.execute_query(
                        f"""
                        MATCH (student:User {{uid: $student_uid}})-[:OWNS]->(s:Entity)
                            -[:{RelationshipName.FULFILLS_EXERCISE}]->(e:Entity {{uid: $exercise_uid}})
                        RETURN count(s) AS prior_count
                        """,
                        {"student_uid": submitter_uid, "exercise_uid": exercise_uid},
                    )
                    prior_count = 0
                    if not prior_count_result.is_error and prior_count_result.value:
                        prior_count = int(prior_count_result.value[0]["prior_count"])

                    from core.models.submissions.submission import Submission

                    new_title = Submission.generate_exercise_title(
                        exercise_title=exercise_title,
                        user_uid=submitter_uid,
                        revision_number=prior_count + 1,
                        revision_date=date.today(),
                    )
                    await self.backend.execute_query(
                        """
                        MATCH (s:Entity {uid: $ku_uid})
                        SET s.title = $new_title, s.updated_at = $now
                        """,
                        {
                            "ku_uid": ku_uid,
                            "new_title": new_title,
                            "now": datetime.now().isoformat(),
                        },
                    )
                    self.logger.info(f"Updated submission title to: {new_title}")

        # 1. Create FULFILLS_EXERCISE relationship
        # Accepts both Exercise and RevisedExercise entity types
        fulfills_result = await self.backend.execute_query(
            f"""
            MATCH (ku:Entity {{uid: $ku_uid}})
            MATCH (exercise:Entity {{uid: $exercise_uid}})
            WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
            MERGE (ku)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            RETURN true as success
            """,
            {"ku_uid": ku_uid, "exercise_uid": exercise_uid},
        )

        if fulfills_result.is_error:
            self.logger.warning(f"Failed to create FULFILLS_EXERCISE: {fulfills_result.error}")

        # 2. Auto-share with teacher
        share_result = await self.backend.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            MATCH (ku:Entity {uid: $ku_uid})
            MERGE (teacher)-[r:SHARES_WITH]->(ku)
            SET r.shared_at = datetime($now),
                r.role = 'teacher'
            RETURN true as success
            """,
            {
                "teacher_uid": teacher_uid,
                "ku_uid": ku_uid,
                "now": datetime.now().isoformat(),
            },
        )

        if share_result.is_error:
            self.logger.warning(f"Failed to auto-share with teacher: {share_result.error}")

        self.logger.info(
            f"Exercise submission processed: ku={ku_uid} -> exercise={exercise_uid}, "
            f"teacher={teacher_uid}"
        )
        return Result.ok(True)

    # Backward-compatible alias
    async def process_assignment_submission(self, ku_uid: str, project_uid: str) -> Result[bool]:
        """Alias for process_exercise_submission (backward compatibility)."""
        return await self.process_exercise_submission(ku_uid, project_uid)

    async def _enforce_fifo(self, user_uid: str, max_retention: int) -> Result[int]:
        """
        Enforce FIFO cleanup for ephemeral journals.

        When max_retention is set, delete oldest journal entries to maintain the limit.

        Args:
            user_uid: User identifier
            max_retention: Maximum number of journals to keep

        Returns:
            Result containing count of journals deleted
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL.value,
        )

        if result.is_error:
            self.logger.warning(f"Failed to get submission entities for FIFO: {result.error}")
            return Result.ok(0)

        reports = result.value or []
        # Filter to journals with FIFO retention
        journals = [k for k in reports if getattr(k, "max_retention", None) is not None]

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
                self.logger.info(f"FIFO cleanup: deleted journal {journal.uid}")

        return Result.ok(deleted_count)

    # ========================================================================
    # ASSESSMENT CRUD (Teacher Assessments → SUBMISSION_FEEDBACK entity)
    # ========================================================================

    @with_error_handling("create_assessment", error_type="database")
    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[SubmissionFeedback]:
        """
        Create a teacher assessment (feedback) for a student.

        Creates a submission with entity_type=SUBMISSION_FEEDBACK, auto-shares with student.
        Verifies teacher has authority over student via shared group membership.

        Args:
            teacher_uid: Teacher creating the assessment
            subject_uid: Student being assessed
            title: Assessment title
            content: Assessment content (markdown)
            metadata: Optional additional metadata

        Returns:
            Result containing the created submission, or forbidden error if no shared group
        """
        from core.models.enums.metadata_enums import Visibility

        # Verify teacher has authority over student (share an active group)
        authority_result = await self.backend.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group)
                  <-[:MEMBER_OF]-(student:User {uid: $subject_uid})
            WHERE g.is_active = true
            RETURN g.uid AS group_uid LIMIT 1
            """,
            {"teacher_uid": teacher_uid, "subject_uid": subject_uid},
        )

        if authority_result.is_error:
            self.logger.error(
                f"Failed to verify teacher-student authority: {authority_result.error}"
            )
            return Result.fail(Errors.database("create_assessment", str(authority_result.error)))

        authority_records = authority_result.value or []
        if not authority_records:
            return Result.fail(
                Errors.forbidden(
                    "create_assessment",
                    f"Teacher {teacher_uid} does not have authority over student {subject_uid} "
                    "(no shared group)",
                )
            )

        uid = UIDGenerator.generate_uid("ku")

        assessment = SubmissionFeedback(
            uid=uid,
            title=title,
            entity_type=EntityType.SUBMISSION_FEEDBACK,
            user_uid=teacher_uid,
            status=EntityStatus.COMPLETED,
            processor_type=ProcessorType.HUMAN,
            content=content,
            subject_uid=subject_uid,
            created_by=teacher_uid,
            visibility=Visibility.SHARED,
            metadata=metadata,
        )

        result = await self.backend.create(assessment)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Create ASSESSMENT_OF relationship
        assess_result = await self.backend.execute_query(
            """
            MATCH (k:Entity {uid: $ku_uid})
            MATCH (u:User {uid: $subject_uid})
            MERGE (k)-[:ASSESSMENT_OF]->(u)
            RETURN true AS success
            """,
            {"ku_uid": uid, "subject_uid": subject_uid},
        )

        if assess_result.is_error:
            self.logger.error(f"Failed to create ASSESSMENT_OF relationship: {assess_result.error}")
            return Result.fail(Errors.database("create_assessment", str(assess_result.error)))

        if not (assess_result.value or []):
            self.logger.error(f"ASSESSMENT_OF not created: student {subject_uid} not found")
            return Result.fail(
                Errors.database("create_assessment", "Failed to create ASSESSMENT_OF relationship")
            )

        # Auto-share with student
        share_result = await self.backend.execute_query(
            """
            MATCH (student:User {uid: $subject_uid})
            MATCH (k:Entity {uid: $ku_uid})
            MERGE (student)-[rel:SHARES_WITH]->(k)
            SET rel.shared_at = datetime($now),
                rel.role = 'student'
            RETURN true AS success
            """,
            {
                "subject_uid": subject_uid,
                "ku_uid": uid,
                "now": datetime.now().isoformat(),
            },
        )

        if share_result.is_error:
            self.logger.error(f"Failed to auto-share assessment with student: {share_result.error}")
            return Result.fail(Errors.database("create_assessment", str(share_result.error)))

        if not (share_result.value or []):
            self.logger.error(f"SHARES_WITH not created for student {subject_uid}")
            return Result.fail(
                Errors.database("create_assessment", "Failed to auto-share assessment with student")
            )

        # Publish event
        event = AssessmentCreated(
            submission_uid=uid,
            teacher_uid=teacher_uid,
            subject_uid=subject_uid,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        self.logger.info(f"Created assessment {uid}: teacher={teacher_uid}, student={subject_uid}")
        return Result.ok(assessment)

    @with_error_handling("get_assessments_for_student", error_type="database")
    async def get_assessments_for_student(
        self, student_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """
        Get assessments received by a student.

        Args:
            student_uid: Student user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of SUBMISSION_FEEDBACK entity entities
        """
        result = await self.backend.execute_query(
            """
            MATCH (k:Entity)-[:ASSESSMENT_OF]->(u:User {uid: $student_uid})
            WHERE k.entity_type = 'submission_feedback'
            RETURN k
            ORDER BY k.created_at DESC
            LIMIT $limit
            """,
            {"student_uid": student_uid, "limit": limit},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = []
        for record in result.value or []:
            node = record["k"]
            dto = SubmissionDTO.from_dict(node)
            reports.append(Entity.from_dto(dto))
        return Result.ok(reports)

    @with_error_handling("get_assessments_by_teacher", error_type="database")
    async def get_assessments_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """
        Get assessments authored by a teacher.

        Args:
            teacher_uid: Teacher user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of SUBMISSION_FEEDBACK entity entities
        """
        result = await self.backend.find_by(
            user_uid=teacher_uid,
            entity_type=EntityType.SUBMISSION_FEEDBACK.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        reports.sort(key=_get_created_at_key, reverse=True)
        return Result.ok(reports[:limit])

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """
        Create journal-type Ku when transcription completes.

        Pipeline:
        1. Try AI processing via ContentEnrichmentService (if available)
        2. Fall back to raw transcript if AI fails
        3. Create Ku with entity_type=JOURNAL and journal metadata via create_journal_entry()
        4. Triggers FIFO cleanup for VOICE journals

        Args:
            event: TranscriptionCompleted event with transcript data

        Note:
            Errors logged but not raised — journal creation is best-effort
            to prevent transcription failure if journal creation fails.
        """
        try:
            self.logger.info(
                f"Creating journal Ku from transcription {event.transcription_uid} "
                f"for user {event.user_uid}"
            )

            # Default to raw transcript
            title = f"Voice Journal - {event.occurred_at.strftime('%Y-%m-%d %H:%M')}"
            content = event.transcript_text
            key_topics: list[str] = []
            action_items: list[str] = []
            summary: str | None = None

            # Try AI processing if available
            if self.content_enrichment:
                insights_result = await self.content_enrichment.process_transcript(
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
            journal_metadata: dict[str, str] = {}
            if summary:
                journal_metadata["summary"] = summary

            # Create journal entity (triggers FIFO for VOICE journals)
            result = await self.create_journal_entry(
                user_uid=event.user_uid,
                title=title,
                content=content,
                max_retention=3,  # Audio-sourced = ephemeral with FIFO
                key_topics=key_topics if key_topics else None,
                action_items=action_items if action_items else None,
                source_type="audio",
                source_file=event.audio_file_path,
                transcription_uid=event.transcription_uid,
                metadata=journal_metadata,
            )

            if result.is_ok:
                self.logger.info(
                    f"Created journal Ku {result.value.uid} from transcription "
                    f"{event.transcription_uid}"
                )
            else:
                self.logger.error(
                    f"Failed to create journal Ku from {event.transcription_uid}: {result.error}"
                )

        except Exception as e:
            self.logger.error(
                f"Error handling TranscriptionCompleted for {event.transcription_uid}: {e!s}"
            )


def _get_entry_date_key(submission: SubmissionEntity) -> date:
    """Get entry_date from entity metadata for sorting, with fallback to date.min."""
    if submission.metadata:
        entry_date_str = submission.metadata.get("entry_date")
        if entry_date_str:
            try:
                return date.fromisoformat(entry_date_str)
            except (ValueError, TypeError):
                pass
    return date.min


def _get_created_at_key(submission: SubmissionEntity) -> datetime:
    """Get created_at from entity for sorting, with fallback to datetime.min."""
    return submission.created_at if submission.created_at else datetime.min
