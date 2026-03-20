"""
Submissions Core Service
========================

Content management operations for submission entities.
Handles categories, tags, publish/archive workflow, bulk operations,
and the Exercise → Submission link that drives the core educational loop.

Delegates journal-specific and assessment-specific workflows to sub-services:
- JournalsCoreService: Journal CRUD, FIFO, transcription handling
- AssessmentService: Teacher assessment CRUD with authority verification

The Core Educational Loop
--------------------------
SKUEL's fundamental process for applied learning:

    Exercise (shared template, admin/teacher-created)
        ↓  user submits work against it
    ExerciseSubmission (user-owned, EntityType.EXERCISE_SUBMISSION)
        ↓  process_exercise_submission() called with exercise_uid
        ↓  creates FULFILLS_EXERCISE relationship
        ↓  auto-shares with teacher (SHARES_WITH role='teacher')
    Teacher review → ExerciseReport (EntityType.EXERCISE_REPORT)

The Exercise is a shared curriculum template. The moment a user creates
a Submission against it, the Submission is exclusively their own work product —
user-owned, privately scoped by default.

Four Entity Types
--------------------------
    EXERCISE_SUBMISSION → Student's work submitted against an Exercise (user-owned)
    JOURNAL_SUBMISSION  → Voice/text journal entries with metadata (user-owned)
    ACTIVITY_REPORT     → System-generated progress reports (user-owned)
    EXERCISE_REPORT     → Teacher feedback on a Submission (teacher-owned)

Service Responsibilities
--------------------------
- SubmissionsService: File upload and storage
- SubmissionsProcessingService: Content processing orchestration
- SubmissionsCoreService: Content management + exercise linking (THIS FILE)
- JournalsCoreService: Journal CRUD + FIFO + transcription (sub-service)
- AssessmentService: Teacher assessments (sub-service)
- SubmissionsSearchService: Read-only queries
- ExerciseService: Exercise CRUD (in exercises package)
- SubmissionReportService: AI report generation
"""

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted

from core.events import publish_event
from core.events.submission_events import SubmissionDeleted
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.models.report.submission_report import SubmissionReport
from core.models.submissions.journal import Journal
from core.models.submissions.submission_dto import SubmissionDTO
from core.ports import BackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.submissions.assessment_service import AssessmentService
from core.services.submissions.journals_core_service import (
    DEFAULT_JOURNAL_INSTRUCTIONS,
    JournalsCoreService,
    JournalUploadResult,
)
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_report_date

# ============================================================================
# KU CATEGORY CONSTANTS
# ============================================================================
# Categories for content organization (stored in metadata['category'])


class ReportCategory:
    """
    Categories for submission content organization.

    Stored in metadata['category'].
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


# Re-export for backward compatibility (moved to journals_core_service)
__all__ = [
    "DEFAULT_JOURNAL_INSTRUCTIONS",
    "JournalUploadResult",
    "ReportCategory",
    "SubmissionsCoreService",
]


class SubmissionsCoreService(BaseService[BackendOperations[Entity], Entity]):
    """
    Core submission service for content management operations.

    This service focuses on:
    - Retrieving submission entities with content
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
        Initialize submissions core service.

        Args:
            backend: Backend for submission persistence
            event_bus: Optional event bus for publishing events
            sharing_service: Optional sharing service for access control
            content_enrichment: Optional ContentEnrichmentService for AI processing
        """
        super().__init__(backend, "SubmissionsCoreService")
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.content_enrichment = content_enrichment

        # Sub-services (facade delegation pattern)
        self.journals = JournalsCoreService(
            backend=backend, event_bus=event_bus, content_enrichment=content_enrichment
        )
        self.assessments = AssessmentService(backend=backend, event_bus=event_bus)

    # Post-init field proxies — wired in services_bootstrap.py via .journals
    @property
    def submissions_service(self) -> Any | None:
        return self.journals.submissions_service

    @submissions_service.setter
    def submissions_service(self, value: Any) -> None:
        self.journals.submissions_service = value

    @property
    def processing_service(self) -> Any | None:
        return self.journals.processing_service

    @processing_service.setter
    def processing_service(self, value: Any) -> None:
        self.journals.processing_service = value

    @property
    def exercise_service(self) -> Any | None:
        return self.journals.exercise_service

    @exercise_service.setter
    def exercise_service(self, value: Any) -> None:
        self.journals.exercise_service = value

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
            uid: Submission unique identifier

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
        - Ownership (user owns the submission)
        - Visibility (PUBLIC submission visible to all)
        - Sharing (SHARED submission with SHARES_WITH relationship)

        Args:
            uid: Submission unique identifier
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
        Get recent submission entities.

        Args:
            limit: Maximum number of submission entities to return
            user_uid: Optional user filter
            entity_type: Optional type filter (e.g., EXERCISE_SUBMISSION, ACTIVITY_REPORT)

        Returns:
            Result containing list of submission entities
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
                submissions_list = result.value
                submissions_list.sort(key=get_report_date, reverse=True)
                return Result.ok(submissions_list[:limit])
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
            "report_content",
            "report_generated_at",
            "word_count",
            "visibility",
            "instructions",
            "max_retention",
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

        return Result.fail(Errors.system("Failed to delete submission"))

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

        Categories are stored in metadata['category'].

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
        Get submission entities by category.

        Args:
            category: Category to filter by
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of submission entities in category
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
                submissions_list = result.value
                # Filter by category in metadata
                filtered = [
                    s
                    for s in submissions_list
                    if s.metadata and s.metadata.get("category") == category
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by category in metadata
        filtered = [s for s in reports if s.metadata and s.metadata.get("category") == category]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    async def add_tags(self, uid: str, tags: list[str]) -> Result[SubmissionEntity]:
        """
        Add tags to an entity.

        Tags are stored in metadata['tags'].

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
        Get submission entities with a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of submission entities with the tag
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
                submissions_list = result.value
                # Filter by tag in metadata
                filtered = [
                    s
                    for s in submissions_list
                    if s.metadata and tag in (s.metadata.get("tags") or [])
                ]
                return Result.ok(filtered[:limit])
            return Result.ok([])

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        # Filter by tag in metadata
        filtered = [s for s in reports if s.metadata and tag in (s.metadata.get("tags") or [])]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """
        Bulk categorize multiple submission entities.

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
                error_msg = f"Failed to update submission {uid}: {result.error}"
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
        Bulk add tags to multiple submission entities.

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
                self.logger.debug(f"Added tags {tags} to submission {uid}")
            else:
                error_msg = f"Failed to tag submission {uid}: {result.error}"
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
        Bulk delete multiple submission entities.

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
                error_msg = f"Failed to delete submission {uid}"
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
    # EXERCISE SUBMISSION PROCESSING
    # ========================================================================

    async def process_exercise_submission(
        self,
        submission_uid: str,
        exercise_uid: str,
    ) -> Result[bool]:
        """
        Process an entity submitted against an ASSIGNED Exercise.

        When a student submits against an assigned exercise:
        1. Create FULFILLS_EXERCISE relationship
        2. Look up the exercise's owner (teacher)
        3. Auto-create SHARES_WITH from teacher to submission
        4. Set submission status to SUBMITTED if processor_type is HUMAN

        Called by routes after submission creation when exercise_uid is provided.

        Args:
            submission_uid: The submitted submission UID
            exercise_uid: The Exercise UID this submission fulfills

        Returns:
            Result[bool]: True if exercise processing was applied
        """
        # Check if the exercise is ASSIGNED scope and get group info
        # Accepts both Exercise and RevisedExercise entity types
        exercise_result = await self.backend.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid}})
            WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
            OPTIONAL MATCH (exercise)-[:{RelationshipName.FOR_GROUP.value}]->(g:Group)
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
                f"""
                MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission:Entity {{uid: $submission_uid}})
                RETURN student.uid as student_uid
                """,
                {"submission_uid": submission_uid},
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
                    f"""
                    MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission:Entity {{uid: $submission_uid}})
                    OPTIONAL MATCH (student)-[:{RelationshipName.MEMBER_OF.value}]->(g:Group {{uid: $group_uid}})
                    RETURN student.uid as student_uid, g.uid as member_of_group
                    """,
                    {"submission_uid": submission_uid, "group_uid": group_uid},
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
                f"""
                MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission:Entity {{uid: $submission_uid}})
                RETURN student.uid as student_uid
                """,
                {"submission_uid": submission_uid},
            )
            if not student_uid_result.is_error:
                student_uid_records = student_uid_result.value or []
                if student_uid_records:
                    submitter_uid = student_uid_records[0]["student_uid"]

                    # Count prior submissions already linked to this exercise by this student
                    prior_count_result = await self.backend.execute_query(
                        f"""
                        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
                            -[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity {{uid: $exercise_uid}})
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
                        MATCH (s:Entity {uid: $submission_uid})
                        SET s.title = $new_title, s.updated_at = $now
                        """,
                        {
                            "submission_uid": submission_uid,
                            "new_title": new_title,
                            "now": datetime.now().isoformat(),
                        },
                    )
                    self.logger.info(f"Updated submission title to: {new_title}")

        # 1. Create FULFILLS_EXERCISE relationship
        # Accepts both Exercise and RevisedExercise entity types
        fulfills_result = await self.backend.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})
            MATCH (exercise:Entity {{uid: $exercise_uid}})
            WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
            MERGE (submission)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            RETURN true as success
            """,
            {"submission_uid": submission_uid, "exercise_uid": exercise_uid},
        )

        if fulfills_result.is_error:
            self.logger.warning(f"Failed to create FULFILLS_EXERCISE: {fulfills_result.error}")

        # 2. Auto-share with teacher
        share_result = await self.backend.execute_query(
            f"""
            MATCH (teacher:User {{uid: $teacher_uid}})
            MATCH (submission:Entity {{uid: $submission_uid}})
            MERGE (teacher)-[r:{RelationshipName.SHARES_WITH.value}]->(submission)
            SET r.shared_at = datetime($now),
                r.role = 'teacher'
            RETURN true as success
            """,
            {
                "teacher_uid": teacher_uid,
                "submission_uid": submission_uid,
                "now": datetime.now().isoformat(),
            },
        )

        if share_result.is_error:
            self.logger.warning(f"Failed to auto-share with teacher: {share_result.error}")

        self.logger.info(
            f"Exercise submission processed: submission={submission_uid} -> exercise={exercise_uid}, "
            f"teacher={teacher_uid}"
        )
        return Result.ok(True)

    # ========================================================================
    # JOURNAL DELEGATION (→ JournalsCoreService)
    # ========================================================================

    async def _count_journals_for_date(self, user_uid: str, entry_date: date) -> int:
        """Delegate to journals sub-service."""
        return await self.journals._count_journals_for_date(user_uid, entry_date)

    async def _enforce_fifo(self, user_uid: str, max_retention: int) -> Result[int]:
        """Delegate to journals sub-service."""
        return await self.journals._enforce_fifo(user_uid, max_retention)

    async def generate_journal_title(
        self, user_uid: str, entry_date: date | None = None
    ) -> Result[str]:
        """Delegate to journals sub-service."""
        return await self.journals.generate_journal_title(user_uid, entry_date)

    async def submit_journal_file(
        self,
        file_content: bytes,
        filename: str,
        user_uid: str,
        custom_title: str = "",
        exercise_uid: str = "",
    ) -> Result[JournalUploadResult]:
        """Delegate to journals sub-service."""
        return await self.journals.submit_journal_file(
            file_content, filename, user_uid, custom_title, exercise_uid
        )

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
        source_type: str | None = None,
        source_file: str | None = None,
        transcription_uid: str | None = None,
    ) -> Result[Journal]:
        """Delegate to journals sub-service."""
        return await self.journals.create_journal_entry(
            user_uid=user_uid,
            title=title,
            content=content,
            max_retention=max_retention,
            entry_date=entry_date,
            tags=tags,
            mood=mood,
            energy_level=energy_level,
            key_topics=key_topics,
            action_items=action_items,
            project_uid=project_uid,
            metadata=metadata,
            enforce_fifo=enforce_fifo,
            source_type=source_type,
            source_file=source_file,
            transcription_uid=transcription_uid,
        )

    async def get_ephemeral_journals(self, user_uid: str, limit: int = 10) -> Result[list[Journal]]:
        """Delegate to journals sub-service."""
        return await self.journals.get_ephemeral_journals(user_uid, limit)

    async def get_permanent_journals(self, user_uid: str, limit: int = 50) -> Result[list[Journal]]:
        """Delegate to journals sub-service."""
        return await self.journals.get_permanent_journals(user_uid, limit)

    async def get_journals_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        limit: int = 100,
    ) -> Result[list[Journal]]:
        """Delegate to journals sub-service."""
        return await self.journals.get_journals_by_date_range(user_uid, start_date, end_date, limit)

    async def make_permanent(self, uid: str) -> Result[SubmissionEntity]:
        """Delegate to journals sub-service."""
        return await self.journals.make_permanent(uid)

    async def get_journal_with_insights(self, uid: str) -> Result[Journal | None]:
        """Delegate to journals sub-service."""
        return await self.journals.get_journal_with_insights(uid)

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """Delegate to journals sub-service."""
        await self.journals.handle_transcription_completed(event)

    # ========================================================================
    # ASSESSMENT DELEGATION (→ AssessmentService)
    # ========================================================================

    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[SubmissionReport]:
        """Delegate to assessments sub-service."""
        return await self.assessments.create_assessment(
            teacher_uid, subject_uid, title, content, metadata
        )

    async def get_assessments_for_student(
        self, student_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """Delegate to assessments sub-service."""
        return await self.assessments.get_assessments_for_student(student_uid, limit)

    async def get_assessments_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """Delegate to assessments sub-service."""
        return await self.assessments.get_assessments_by_teacher(teacher_uid, limit)
