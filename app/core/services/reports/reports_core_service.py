"""
Ku Core Service
========================

Content management operations for Ku entities.
Handles categories, tags, publish/archive workflow, bulk operations,
and journal-specific CRUD (create_journal_ku, FIFO cleanup, etc.).

ARCHITECTURE (February 2026):
------------------------------
Ku nodes are the SINGLE SOURCE OF TRUTH for all knowledge.
"Ku is the heartbeat of SKUEL."

Four manifestations:
    CURRICULUM      → Admin-created shared knowledge (no owner)
    SUBMISSION      → Student submission (user-owned), including journals
    AI_REPORT       → AI-derived from submission (user-owned)
    FEEDBACK_REPORT → Teacher feedback on submission (teacher-owned)

Journal-specific fields (mood, energy_level, entry_date, etc.) live in metadata.
max_retention is a first-class Ku field controlling FIFO cleanup (None = permanent).

Services:
- KuSubmissionService: File upload and storage
- KuProcessingService: Content processing orchestration
- KuCoreService: Content management + journal CRUD (THIS FILE)
- KuSearchService: Read-only queries
- AssignmentService: LLM instruction projects
- KuFeedbackService: AI feedback generation
"""

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted

from core.events import publish_event
from core.events.submission_events import AssessmentCreated, SubmissionDeleted
from core.models.enums.ku_enums import KuStatus, KuType, ProcessorType
from core.models.ku import FeedbackKu, JournalKu, Ku, KuBase, KuDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_report_date
from core.utils.uid_generator import UIDGenerator

# ============================================================================
# KU CATEGORY CONSTANTS
# ============================================================================
# Categories for content organization (stored in metadata['category'])


class KuCategory:
    """
    Categories for Ku content organization.

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


class KuCoreService(BaseService[BackendOperations[KuBase], KuBase]):
    """
    Core Ku service for content management operations.

    This service focuses on:
    - Retrieving Ku entities with content
    - Status workflow (publish, archive, draft)
    - Category management
    - Tag management
    - Bulk operations
    - Export functionality
    - Journal CRUD (create_journal_ku, FIFO cleanup)
    - Assessment CRUD (teacher feedback)

    NOTE: For file submission, use KuSubmissionService.
    NOTE: For processing, use KuProcessingService.

    Source Tag: "ku_core_service_explicit"

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification
    """

    # =========================================================================
    # DomainConfig
    # =========================================================================
    _config = DomainConfig(
        dto_class=KuDTO,
        model_class=KuBase,
        entity_label="Ku",
        search_fields=("title", "original_filename", "processed_content"),
        search_order_by="created_at",
        category_field="ku_type",
        user_ownership_relationship=RelationshipName.OWNS,  # User-owned content
    )

    def __init__(
        self,
        backend: BackendOperations[Ku] | None = None,
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
        super().__init__(backend, "KuCoreService")
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.content_enrichment = content_enrichment

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    def _validate_ku_exists(self, ku: Ku | None) -> Result[Ku]:
        """Validate Ku exists."""
        if ku:
            return Result.ok(ku)
        return Result.fail(Errors.not_found("Ku not found"))

    # ========================================================================
    # RETRIEVE
    # ========================================================================

    async def get_ku(self, uid: str) -> Result[Ku]:
        """
        Get a Ku by UID.

        Args:
            uid: Ku unique identifier

        Returns:
            Result containing the Ku or an error
        """
        result = await self.backend.get(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        ku = result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        return Result.ok(ku)

    async def get_with_access_check(self, uid: str, user_uid: str) -> Result[Ku]:
        """
        Get a Ku with access control verification.

        Checks if the user can view the Ku based on:
        - Ownership (user owns the Ku)
        - Visibility (PUBLIC Ku visible to all)
        - Sharing (SHARED Ku with SHARES_WITH relationship)

        Args:
            uid: Ku unique identifier
            user_uid: User requesting access

        Returns:
            Result containing the Ku or an error if access denied
        """
        if not self.sharing_service:
            # Fall back to simple get if no sharing service
            return await self.get_ku(uid)

        # Check access
        access_result = await self.sharing_service.check_access(uid, user_uid)
        if access_result.is_error:
            return Result.fail(access_result.expect_error())

        if not access_result.value:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # User has access, fetch the Ku
        return await self.get_ku(uid)

    async def get_ku_for_date(
        self, target_date: date, user_uid: str | None = None
    ) -> Result[Ku | None]:
        """
        Get the Ku for a specific date.

        Args:
            target_date: Date to find Ku for
            user_uid: Optional user filter

        Returns:
            Result containing the Ku if found, None otherwise
        """
        filters: dict[str, Any] = {}

        # Filter by user if provided
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result.expect_error())

        kus = result.value
        if not kus:
            return Result.ok(None)

        # Filter by date (checking created_at date portion)
        for ku in kus:
            if ku.created_at:
                ku_date = ku.created_at.date()
                if ku_date == target_date:
                    return Result.ok(ku)

        return Result.ok(None)

    async def get_recent_kus(
        self,
        limit: int = 10,
        user_uid: str | None = None,
        ku_type: KuType | None = None,
    ) -> Result[list[Ku]]:
        """
        Get recent Ku entities.

        Args:
            limit: Maximum number of Ku entities to return
            user_uid: Optional user filter
            ku_type: Optional type filter (e.g., SUBMISSION, AI_REPORT)

        Returns:
            Result containing list of Ku entities
        """
        filters: dict[str, Any] = {}

        if user_uid:
            filters["user_uid"] = user_uid
        if ku_type:
            filters["ku_type"] = ku_type.value

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

        kus = result.value or []
        # Sort by created_at descending
        kus.sort(key=get_report_date, reverse=True)

        return Result.ok(kus[:limit])

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update_ku(self, uid: str, updates: dict[str, Any]) -> Result[Ku]:
        """
        Update a Ku.

        Args:
            uid: Ku UID
            updates: Dictionary of updates to apply

        Returns:
            Result containing updated Ku or error
        """
        # Define allowed fields (Ku model first-class fields only)
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
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        return Result.ok(updated)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_ku(self, uid: str) -> Result[bool]:
        """
        Delete a Ku.

        Args:
            uid: Ku UID to delete

        Returns:
            Result indicating success or failure
        """
        # Get Ku for event data before deletion
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Delete
        delete_result = await self.backend.delete(uid)

        if delete_result.is_error:
            return Result.fail(delete_result.expect_error())

        if delete_result.value:
            event = SubmissionDeleted(
                submission_uid=uid,
                user_uid=ku.user_uid,
                ku_type=ku.ku_type.value,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.debug(f"Published SubmissionDeleted event for {uid}")
            return Result.ok(True)

        return Result.fail(Errors.system("Failed to delete Ku"))

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def publish_ku(self, uid: str) -> Result[Ku]:
        """Publish a Ku (set status to completed/published)."""
        return await self._update_ku_status(uid, KuStatus.COMPLETED)

    async def archive_ku(self, uid: str) -> Result[Ku]:
        """Archive a Ku by updating status in metadata."""
        # Get current Ku
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Update metadata to include archived flag
        current_metadata = ku.metadata or {}
        current_metadata["archived"] = True
        current_metadata["archived_at"] = datetime.now().isoformat()

        return await self.update_ku(uid, {"metadata": current_metadata})

    async def mark_as_draft(self, uid: str) -> Result[Ku]:
        """Mark a Ku as draft."""
        return await self._update_ku_status(uid, KuStatus.DRAFT)

    async def _update_ku_status(self, uid: str, status: KuStatus) -> Result[Ku]:
        """Update Ku status."""
        result = await self.backend.update(uid, {"status": status.value})

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        self.logger.info(f"Updated Ku {uid} status to {status.value}")
        return Result.ok(updated)

    # ========================================================================
    # CATEGORY MANAGEMENT
    # ========================================================================

    async def categorize_ku(self, uid: str, category: str) -> Result[Ku]:
        """
        Categorize a Ku.

        Categories are stored in Ku.metadata['category'].

        Args:
            uid: Ku UID
            category: Category to assign (use KuCategory constants)

        Returns:
            Updated Ku
        """
        # Validate category
        if category not in KuCategory.all_categories():
            self.logger.warning(f"Unknown category '{category}', using anyway")

        # Get current Ku to preserve metadata
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Update metadata with category
        current_metadata = ku.metadata or {}
        current_metadata["category"] = category

        return await self.update_ku(uid, {"metadata": current_metadata})

    async def get_kus_by_category(
        self, category: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Ku]]:
        """
        Get Ku entities by category.

        Args:
            category: Category to filter by
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of Ku entities in category
        """
        # Get all Ku entities and filter by metadata.category
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

        kus = result.value or []
        # Filter by category in metadata
        filtered = [k for k in kus if k.metadata and k.metadata.get("category") == category]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    async def add_tags(self, uid: str, tags: list[str]) -> Result[Ku]:
        """
        Add tags to a Ku.

        Tags are stored in Ku.metadata['tags'].

        Args:
            uid: Ku UID
            tags: Tags to add

        Returns:
            Updated Ku
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Merge with existing tags
        current_metadata = ku.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        new_tags = list(set(current_tags + tags))
        current_metadata["tags"] = new_tags

        return await self.update_ku(uid, {"metadata": current_metadata})

    async def remove_tags(self, uid: str, tags: list[str]) -> Result[Ku]:
        """
        Remove tags from a Ku.

        Args:
            uid: Ku UID
            tags: Tags to remove

        Returns:
            Updated Ku
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Remove specified tags
        current_metadata = ku.metadata or {}
        current_tags = current_metadata.get("tags", [])
        if not isinstance(current_tags, list):
            current_tags = []
        updated_tags = [t for t in current_tags if t not in tags]
        current_metadata["tags"] = updated_tags

        return await self.update_ku(uid, {"metadata": current_metadata})

    async def get_kus_by_tag(
        self, tag: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[Ku]]:
        """
        Get Ku entities with a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum results
            user_uid: Optional user filter

        Returns:
            List of Ku entities with the tag
        """
        # Get all Ku entities and filter by metadata.tags
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

        kus = result.value or []
        # Filter by tag in metadata
        filtered = [k for k in kus if k.metadata and tag in (k.metadata.get("tags") or [])]

        return Result.ok(filtered[:limit])

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    async def bulk_categorize(self, uids: list[str], category: str) -> Result[int]:
        """
        Bulk categorize multiple Ku entities.

        Args:
            uids: List of Ku UIDs to categorize
            category: Category to assign to all entities

        Returns:
            Result containing count of successfully updated entities
        """
        self.logger.info(f"Bulk categorizing {len(uids)} Ku entities to category: {category}")

        updated_count = 0
        errors = []

        for uid in uids:
            result = await self.categorize_ku(uid, category)
            if result.is_ok:
                updated_count += 1
                self.logger.debug(f"Updated Ku {uid} to category {category}")
            else:
                error_msg = f"Failed to update Ku {uid}: {result.error}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk categorization completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk categorization completed: {updated_count}/{len(uids)} Ku entities updated"
        )
        return Result.ok(updated_count)

    async def bulk_tag(self, uids: list[str], tags: list[str]) -> Result[int]:
        """
        Bulk add tags to multiple Ku entities.

        Args:
            uids: List of Ku UIDs to tag
            tags: List of tags to add to all entities

        Returns:
            Result containing count of successfully updated entities
        """
        self.logger.info(f"Bulk tagging {len(uids)} Ku entities with tags: {tags}")

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

        self.logger.info(f"Bulk tagging completed: {updated_count}/{len(uids)} Ku entities updated")
        return Result.ok(updated_count)

    async def bulk_delete(self, uids: list[str], soft_delete: bool = True) -> Result[int]:
        """
        Bulk delete multiple Ku entities.

        Args:
            uids: List of Ku UIDs to delete
            soft_delete: If True, archive instead of permanent delete

        Returns:
            Result containing count of successfully deleted entities
        """
        self.logger.info(f"Bulk deleting {len(uids)} Ku entities (soft_delete={soft_delete})")

        deleted_count = 0
        errors = []

        for uid in uids:
            if soft_delete:
                result = await self.archive_ku(uid)
                success = result.is_ok
            else:
                delete_result = await self.delete_ku(uid)
                success = delete_result.is_ok and bool(delete_result.value)

            if success:
                deleted_count += 1
                self.logger.debug(f"Deleted Ku {uid}")
            else:
                error_msg = f"Failed to delete Ku {uid}"
                errors.append(error_msg)
                self.logger.warning(error_msg)

        if errors:
            self.logger.warning(f"Bulk deletion completed with {len(errors)} errors")

        self.logger.info(
            f"Bulk deletion completed: {deleted_count}/{len(uids)} Ku entities deleted"
        )
        return Result.ok(deleted_count)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_to_markdown(self, uid: str) -> Result[str]:
        """
        Export Ku to markdown format.

        Args:
            uid: Ku UID

        Returns:
            Markdown formatted Ku content
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        # Extract metadata
        metadata = ku.metadata or {}
        category = metadata.get("category", "")
        tags_list = metadata.get("tags", [])

        # Format as markdown
        md_lines = [
            f"# {ku.title}",
            f"*{ku.created_at.strftime('%Y-%m-%d')}*" if ku.created_at else "",
            "",
            ku.processed_content or ku.content or "",
            "",
            f"**Type:** {ku.ku_type.value}" if ku.ku_type else "",
            f"**Category:** {category}" if category else "",
            f"**Tags:** {', '.join(tags_list)}" if tags_list else "",
            f"**Status:** {ku.status.value}" if ku.status else "",
        ]

        markdown = "\n".join(line for line in md_lines if line)
        return Result.ok(markdown)

    # ========================================================================
    # JOURNAL CRUD (merged from JournalsCoreService — February 2026)
    #
    # Journals are SUBMISSION Ku with journal-specific fields in metadata:
    #   metadata['journal_type'], metadata['journal_category'],
    #   metadata['entry_date'], metadata['mood'], metadata['energy_level'],
    #   metadata['key_topics'], metadata['action_items'],
    #   metadata['source_type'], metadata['source_file'],
    #   metadata['transcription_uid']
    # ========================================================================

    @with_error_handling("create_journal_ku", error_type="database")
    async def create_journal_ku(
        self,
        user_uid: str,
        title: str,
        content: str,
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
    ) -> Result[Ku]:
        """
        Create a journal-type Ku (JOURNAL with journal metadata).

        Journals are Ku entities with ku_type=JOURNAL. max_retention controls
        FIFO cleanup: when set (e.g., 3), oldest journals are deleted to
        maintain the limit. When None, journals are permanent.

        Args:
            user_uid: User who owns this journal
            title: Journal entry title
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
            Result containing the created Ku
        """
        uid = UIDGenerator.generate_uid("je", title)

        # Build journal metadata
        journal_metadata = metadata.copy() if metadata else {}
        journal_metadata["entry_date"] = (entry_date or date.today()).isoformat()
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

        journal = JournalKu(
            uid=uid,
            title=title,
            ku_type=KuType.JOURNAL,
            user_uid=user_uid,
            status=KuStatus.DRAFT,
            content=content,
            max_retention=max_retention,
            tags=tuple(tags) if tags else (),
            metadata=journal_metadata,
        )

        result = await self.backend.create(journal)
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.info(f"Created journal Ku: {uid} - {title}")

        # Enforce FIFO for ephemeral journals
        if enforce_fifo and max_retention is not None:
            await self._enforce_fifo(user_uid, max_retention)

        return Result.ok(journal)

    @with_error_handling("get_ephemeral_journals", error_type="database")
    async def get_ephemeral_journals(self, user_uid: str, limit: int = 10) -> Result[list[Ku]]:
        """Get journals with FIFO retention (max_retention is set) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            ku_type=KuType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        kus = result.value or []
        journals = [k for k in kus if k.max_retention is not None]
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_permanent_journals", error_type="database")
    async def get_permanent_journals(self, user_uid: str, limit: int = 50) -> Result[list[Ku]]:
        """Get permanent journals (no FIFO retention) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            ku_type=KuType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        kus = result.value or []
        journals = [k for k in kus if k.max_retention is None]
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_journals_by_date_range", error_type="database")
    async def get_journals_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        limit: int = 100,
    ) -> Result[list[Ku]]:
        """
        Get journal Ku entities within a date range.

        Args:
            user_uid: User identifier
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            limit: Maximum number to return

        Returns:
            Result containing list of journal Ku entities
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            ku_type=KuType.JOURNAL.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        kus = result.value or []
        journals = []
        for ku in kus:
            entry_date_str = (ku.metadata or {}).get("entry_date")
            if entry_date_str:
                try:
                    entry = date.fromisoformat(entry_date_str)
                    if start_date <= entry <= end_date:
                        journals.append(ku)
                except (ValueError, TypeError):
                    pass

        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("make_permanent", error_type="database")
    async def make_permanent(self, uid: str) -> Result[Ku]:
        """
        Make a journal permanent by clearing its max_retention.

        Removes the journal from FIFO cleanup.

        Args:
            uid: Ku UID to make permanent

        Returns:
            Result containing the updated Ku
        """
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        ku = get_result.value
        if not ku:
            return Result.fail(Errors.not_found("resource", f"Ku {uid} not found"))

        return await self.update_ku(uid, {"max_retention": None})

    async def get_journal_with_insights(self, uid: str) -> Result[Ku | None]:
        """
        Get a journal Ku with its extracted insights.

        Args:
            uid: Ku UID

        Returns:
            Result containing the Ku (includes insights in metadata)
        """
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        ku = result.value
        if not ku or ku.ku_type != KuType.JOURNAL:
            return Result.ok(None)

        return Result.ok(ku)

    # ========================================================================
    # FIFO CLEANUP FOR VOICE JOURNALS
    # ========================================================================

    async def process_assignment_submission(
        self,
        ku_uid: str,
        project_uid: str,
    ) -> Result[bool]:
        """
        Process a Ku submitted against an ASSIGNED Assignment.

        When a student submits against an assigned project:
        1. Create FULFILLS_PROJECT relationship
        2. Look up the project's owner (teacher)
        3. Auto-create SHARES_WITH from teacher to Ku
        4. Set Ku status to SUBMITTED if processor_type is HUMAN

        Called by routes after Ku creation when project_uid is provided.

        Args:
            ku_uid: The submitted Ku UID
            project_uid: The Assignment UID this Ku fulfills

        Returns:
            Result[bool]: True if assignment processing was applied
        """
        from core.models.relationship_names import RelationshipName

        # Check if the project is ASSIGNED scope and get group info
        project_result = await self.backend.execute_query(
            """
            MATCH (project:Assignment {uid: $project_uid})
            OPTIONAL MATCH (project)-[:FOR_GROUP]->(g:Group)
            RETURN project.scope as scope,
                   project.user_uid as teacher_uid,
                   project.processor_type as processor_type,
                   g.uid as group_uid
            """,
            {"project_uid": project_uid},
        )

        if project_result.is_error:
            self.logger.error(f"Error querying project: {project_result.error}")
            return Result.ok(False)  # Non-fatal

        records = project_result.value or []
        if not records:
            return Result.ok(False)  # Project not found — not an error, just not an assignment

        scope = records[0]["scope"]
        if scope != "assigned":
            return Result.ok(False)  # Not an assigned project

        teacher_uid = records[0]["teacher_uid"]
        processor_type = records[0]["processor_type"]
        group_uid = records[0]["group_uid"]

        # Verify student is a member of the target group (if group exists)
        if group_uid:
            # Find the student who owns this Ku
            student_result = await self.backend.execute_query(
                """
                MATCH (student:User)-[:OWNS]->(ku:Ku {uid: $ku_uid})
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
                    f"for assignment project {project_uid}"
                )
                return Result.ok(False)

        # 1. Create FULFILLS_PROJECT relationship
        fulfills_result = await self.backend.execute_query(
            f"""
            MATCH (ku:Ku {{uid: $ku_uid}})
            MATCH (project:Assignment {{uid: $project_uid}})
            MERGE (ku)-[:{RelationshipName.FULFILLS_PROJECT}]->(project)
            RETURN true as success
            """,
            {"ku_uid": ku_uid, "project_uid": project_uid},
        )

        if fulfills_result.is_error:
            self.logger.warning(f"Failed to create FULFILLS_PROJECT: {fulfills_result.error}")

        # 2. Auto-share with teacher
        share_result = await self.backend.execute_query(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            MATCH (ku:Ku {uid: $ku_uid})
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

        # 3. Set status to SUBMITTED if processor_type is HUMAN
        if processor_type in ("human", "hybrid"):
            status_result = await self.backend.execute_query(
                """
                MATCH (ku:Ku {uid: $ku_uid})
                SET ku.status = $status,
                    ku.processor_type = $processor_type,
                    ku.updated_at = datetime($now)
                RETURN true as success
                """,
                {
                    "ku_uid": ku_uid,
                    "status": KuStatus.SUBMITTED.value,
                    "processor_type": processor_type,
                    "now": datetime.now().isoformat(),
                },
            )

            if status_result.is_error:
                self.logger.warning(f"Failed to set status to SUBMITTED: {status_result.error}")

        self.logger.info(
            f"Assignment submission processed: ku={ku_uid} -> project={project_uid}, "
            f"teacher={teacher_uid}, processor={processor_type}"
        )
        return Result.ok(True)

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
            ku_type=KuType.JOURNAL.value,
        )

        if result.is_error:
            self.logger.warning(f"Failed to get Ku entities for FIFO: {result.error}")
            return Result.ok(0)

        kus = result.value or []
        # Filter to journals with FIFO retention
        journals = [k for k in kus if k.max_retention is not None]

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
    # ASSESSMENT CRUD (Teacher Assessments → FEEDBACK_REPORT Ku)
    # ========================================================================

    @with_error_handling("create_assessment", error_type="database")
    async def create_assessment(
        self,
        teacher_uid: str,
        subject_uid: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Ku]:
        """
        Create a teacher assessment (feedback) for a student.

        Creates a Ku with ku_type=FEEDBACK_REPORT, auto-shares with student.
        Verifies teacher has authority over student via shared group membership.

        Args:
            teacher_uid: Teacher creating the assessment
            subject_uid: Student being assessed
            title: Assessment title
            content: Assessment content (markdown)
            metadata: Optional additional metadata

        Returns:
            Result containing the created Ku, or forbidden error if no shared group
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

        assessment = FeedbackKu(
            uid=uid,
            title=title,
            ku_type=KuType.FEEDBACK_REPORT,
            user_uid=teacher_uid,
            status=KuStatus.COMPLETED,
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
            MATCH (k:Ku {uid: $ku_uid})
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
            MATCH (k:Ku {uid: $ku_uid})
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
    ) -> Result[list[Ku]]:
        """
        Get assessments received by a student.

        Args:
            student_uid: Student user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of FEEDBACK_REPORT Ku entities
        """
        result = await self.backend.execute_query(
            """
            MATCH (k:Ku)-[:ASSESSMENT_OF]->(u:User {uid: $student_uid})
            WHERE k.ku_type = 'feedback_report'
            RETURN k
            ORDER BY k.created_at DESC
            LIMIT $limit
            """,
            {"student_uid": student_uid, "limit": limit},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        kus = []
        for record in result.value or []:
            node = record["k"]
            dto = KuDTO.from_dict(node)
            kus.append(KuBase.from_dto(dto))
        return Result.ok(kus)

    @with_error_handling("get_assessments_by_teacher", error_type="database")
    async def get_assessments_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Ku]]:
        """
        Get assessments authored by a teacher.

        Args:
            teacher_uid: Teacher user UID
            limit: Maximum number of assessments to return

        Returns:
            Result containing list of FEEDBACK_REPORT Ku entities
        """
        result = await self.backend.find_by(
            user_uid=teacher_uid,
            ku_type=KuType.FEEDBACK_REPORT.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        kus = result.value or []
        kus.sort(key=_get_created_at_key, reverse=True)
        return Result.ok(kus[:limit])

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """
        Create journal-type Ku when transcription completes.

        Pipeline:
        1. Try AI processing via ContentEnrichmentService (if available)
        2. Fall back to raw transcript if AI fails
        3. Create Ku with ku_type=JOURNAL and journal metadata via create_journal_ku()
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

            # Create journal Ku (triggers FIFO for VOICE journals)
            result = await self.create_journal_ku(
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


def _get_entry_date_key(ku: Ku) -> date:
    """Get entry_date from Ku metadata for sorting, with fallback to date.min."""
    if ku.metadata:
        entry_date_str = ku.metadata.get("entry_date")
        if entry_date_str:
            try:
                return date.fromisoformat(entry_date_str)
            except (ValueError, TypeError):
                pass
    return date.min


def _get_created_at_key(ku: Ku) -> datetime:
    """Get created_at from Ku for sorting, with fallback to datetime.min."""
    return ku.created_at if ku.created_at else datetime.min
