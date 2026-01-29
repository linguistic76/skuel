"""
Journals Core Service
=====================

Core service for Journal entities - creates :Journal nodes in Neo4j.

Domain Separation (January 2026):
---------------------------------
- Journals: Personal reflections, metacognition, automatic LLM feedback
- Assignments: File submission, teacher review, gradebook

This service handles:
- CRUD operations for Journal entities
- Voice journal (PJ1) FIFO cleanup
- Curated journal (PJ2) permanent storage
- Journal-specific queries (by date, by type, by category)

Graph Node: :Journal
Relationships:
- (User)-[:OWNS]->(Journal)
- (Journal)-[:RELATED_TO]->(Journal)
- (Journal)-[:SUPPORTS_GOAL]->(Goal)

See: /docs/architecture/JOURNAL_ASSIGNMENT_SEPARATION.md
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted
    from core.services.transcript_processor_service import TranscriptProcessorService
from core.events import JournalCreated, JournalDeleted, JournalUpdated, publish_event
from core.models.enums.journal_enums import JournalType
from core.models.journal.journal_dto import JournalDTO
from core.models.journal.journal_pure import JournalPure
from core.services.base_service import BaseService
from core.services.protocols import BaseUpdatePayload, JournalsOperations
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


def _get_entry_date_key(journal: JournalPure) -> date:
    """Get entry_date from journal for sorting, with fallback to date.min."""
    return journal.entry_date if journal.entry_date else date.min


def _get_created_at_key(journal: JournalPure) -> datetime:
    """Get created_at from journal for sorting, with fallback to datetime.min."""
    return journal.created_at if journal.created_at else datetime.min


class JournalsCoreService(BaseService[JournalsOperations, JournalPure]):
    """
    Core service for Journal entities.

    Creates and manages :Journal nodes in Neo4j.

    Two-Tier Journal System:
    - VOICE (PJ1): Ephemeral voice journals, max 3 stored
    - CURATED (PJ2): Permanent curated text/markdown journals

    BaseService Configuration:
    - _dto_class: JournalDTO
    - _model_class: JournalPure
    - _user_ownership_relationship: "OWNS"
    """

    _dto_class = JournalDTO
    _model_class = JournalPure
    _user_ownership_relationship = "OWNS"
    _search_fields: ClassVar[list[str]] = ["title", "content", "key_topics"]
    _search_order_by = "entry_date"
    _category_field = "category"

    def __init__(
        self,
        backend: UniversalNeo4jBackend[JournalPure] | None = None,
        event_bus: EventBusOperations | None = None,
        transcript_processor: "TranscriptProcessorService | None" = None,
    ) -> None:
        """
        Initialize journals core service.

        Args:
            backend: UniversalNeo4jBackend[JournalPure] for persistence
            event_bus: Optional event bus for publishing domain events
            transcript_processor: Optional TranscriptProcessorService for AI-powered
                journal creation from transcriptions
        """
        super().__init__(backend, "JournalsCoreService")
        self.event_bus = event_bus
        self.transcript_processor = transcript_processor
        self.logger = get_logger("skuel.services.journals_core")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Journal entities."""
        return "Journal"

    # ========================================================================
    # CREATE
    # ========================================================================

    @with_error_handling("create_journal", error_type="database")
    async def create_journal(
        self,
        journal: JournalPure,
        enforce_fifo: bool = True,
    ) -> Result[JournalPure]:
        """
        Create a new journal entry.

        Creates a :Journal node in Neo4j with (User)-[:OWNS]->(Journal) relationship.

        Args:
            journal: Journal entity to create
            enforce_fifo: If True, enforce FIFO cleanup for VOICE journals (default: True)

        Returns:
            Result containing the created journal

        Note:
            For VOICE journals, this automatically enforces the max 3 retention
            limit by deleting oldest entries after creation.
        """
        # Create the journal
        result = await self.backend.create(journal)

        if result.is_error:
            return Result.fail(result.expect_error())

        created_journal = result.value

        # Publish event
        event = JournalCreated(
            journal_uid=created_journal.uid,
            user_uid=created_journal.user_uid,
            title=created_journal.title,
            content_length=len(created_journal.content) if created_journal.content else 0,
            has_summary=bool(
                created_journal.metadata.get("summary") if created_journal.metadata else False
            ),
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        # Enforce FIFO for voice journals
        if enforce_fifo and created_journal.journal_type == JournalType.VOICE:
            await self._enforce_voice_journal_fifo(created_journal.user_uid)

        self.logger.info(
            f"Created journal: uid={created_journal.uid}, type={created_journal.journal_type.value}"
        )
        return Result.ok(created_journal)

    async def create(self, journal: JournalPure) -> Result[JournalPure]:
        """Create journal - delegates to create_journal for event publishing."""
        return await self.create_journal(journal)

    # ========================================================================
    # READ
    # ========================================================================

    @with_error_handling("get_journal", error_type="database", uid_param="uid")
    async def get_journal(
        self, uid: str, user_uid: str | None = None
    ) -> Result[JournalPure | None]:
        """
        Get a journal by UID.

        Args:
            uid: Journal unique identifier
            user_uid: If provided, verifies the journal belongs to this user.
                Returns NotFound if ownership check fails (prevents IDOR attacks).

        Returns:
            Result containing the journal or None if not found
        """
        if user_uid:
            # Use inherited ownership verification from BaseService
            # Cast needed: verify_ownership returns Result[T], but this method
            # returns Result[T | None] to handle the no-user_uid case
            return cast("Result[JournalPure | None]", await self.verify_ownership(uid, user_uid))
        return await self.backend.get(uid)

    @with_error_handling("get_journal_for_date", error_type="database")
    async def get_journal_for_date(
        self,
        target_date: date,
        user_uid: str,
        journal_type: JournalType | None = None,
    ) -> Result[JournalPure | None]:
        """
        Get journal for a specific date.

        Args:
            target_date: Date to find journal for
            user_uid: User filter
            journal_type: Optional filter by journal type

        Returns:
            Result containing the journal if found, None otherwise
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "entry_date": target_date,
        }

        if journal_type:
            filters["journal_type"] = journal_type.value

        result = await self.backend.find_by(**filters, limit=1)

        if result.is_error:
            return Result.fail(result.expect_error())

        journals = result.value or []
        return Result.ok(journals[0] if journals else None)

    @with_error_handling("get_journals_by_type", error_type="database")
    async def get_journals_by_type(
        self,
        user_uid: str,
        journal_type: JournalType,
        limit: int = 50,
    ) -> Result[list[JournalPure]]:
        """
        Get journals by type for a user.

        Args:
            user_uid: User identifier
            journal_type: VOICE or CURATED
            limit: Maximum number of journals to return

        Returns:
            Result containing list of journals
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            journal_type=journal_type.value,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        journals = result.value or []
        # Sort by entry_date descending
        journals.sort(key=_get_entry_date_key, reverse=True)

        return Result.ok(journals[:limit])

    @with_error_handling("get_voice_journals", error_type="database")
    async def get_voice_journals(
        self,
        user_uid: str,
        limit: int = 3,
    ) -> Result[list[JournalPure]]:
        """
        Get voice journals (PJ1) for a user.

        Voice journals are ephemeral with max 3 retention.

        Args:
            user_uid: User identifier
            limit: Maximum number to return (default: 3)

        Returns:
            Result containing list of voice journals, newest first
        """
        return await self.get_journals_by_type(user_uid, JournalType.VOICE, limit)

    @with_error_handling("get_curated_journals", error_type="database")
    async def get_curated_journals(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[JournalPure]]:
        """
        Get curated journals (PJ2) for a user.

        Curated journals are permanent.

        Args:
            user_uid: User identifier
            limit: Maximum number to return

        Returns:
            Result containing list of curated journals, newest first
        """
        return await self.get_journals_by_type(user_uid, JournalType.CURATED, limit)

    @with_error_handling("get_journals_by_date_range", error_type="database")
    async def get_journals_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        journal_type: JournalType | None = None,
        limit: int = 100,
    ) -> Result[list[JournalPure]]:
        """
        Get journals within a date range.

        Args:
            user_uid: User identifier
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            journal_type: Optional filter by type
            limit: Maximum number to return

        Returns:
            Result containing list of journals
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
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

    # ========================================================================
    # UPDATE
    # ========================================================================

    @with_error_handling("update_journal", error_type="database", uid_param="uid")
    async def update_journal(
        self,
        uid: str,
        updates: dict[str, Any],
        user_uid: str | None = None,
    ) -> Result[JournalPure]:
        """
        Update a journal entry.

        Args:
            uid: Journal UID
            updates: Dictionary of updates to apply
            user_uid: If provided, verifies the journal belongs to this user
                before updating. Returns NotFound if ownership check fails.

        Returns:
            Result containing updated journal
        """
        # Verify ownership if user_uid provided
        if user_uid:
            ownership_result = await self.verify_ownership(uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(ownership_result.expect_error())

        # Always update updated_at
        updates["updated_at"] = datetime.now()

        result = await self.backend.update(uid, updates)

        if result.is_error:
            return Result.fail(result.expect_error())

        updated_journal = result.value
        if not updated_journal:
            return Result.fail(Errors.not_found("Journal", uid))

        # Publish event
        event = JournalUpdated(
            journal_uid=uid,
            user_uid=updated_journal.user_uid,
            updated_fields=updates,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(updated_journal)

    async def update(
        self, uid: str, updates: BaseUpdatePayload | dict[str, Any]
    ) -> Result[JournalPure]:
        """Update journal - delegates to update_journal for event publishing."""
        return await self.update_journal(uid, updates)

    # ========================================================================
    # DELETE
    # ========================================================================

    @with_error_handling("delete_journal", error_type="database", uid_param="uid")
    async def delete_journal(self, uid: str, user_uid: str | None = None) -> Result[bool]:
        """
        Delete a journal entry.

        Args:
            uid: Journal UID to delete
            user_uid: If provided, verifies the journal belongs to this user
                before deleting. Returns NotFound if ownership check fails.

        Returns:
            Result indicating success
        """
        # Get journal before deletion for event data (also verifies ownership if needed)
        if user_uid:
            get_result = await self.verify_ownership(uid, user_uid)
            if get_result.is_error:
                return Result.fail(get_result.expect_error())
            journal = get_result.value
            journal_title = journal.title
            journal_user_uid = journal.user_uid
        else:
            get_result = await self.backend.get(uid)
            journal_title = "Unknown"
            journal_user_uid = "unknown"
            if get_result.is_ok and get_result.value:
                journal = get_result.value
                journal_title = journal.title
                journal_user_uid = journal.user_uid

        # Delete with cascade (removes OWNS relationship)
        result = await self.backend.delete(uid, cascade=True)

        if result.is_error:
            return Result.fail(result.expect_error())

        if result.value:
            # Publish event
            event = JournalDeleted(
                journal_uid=uid,
                user_uid=journal_user_uid,
                title=journal_title,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event, self.logger)

            self.logger.info(f"Deleted journal: uid={uid}")
            return Result.ok(True)

        return Result.fail(Errors.system("Failed to delete journal"))

    async def delete(self, uid: str, cascade: bool = True) -> Result[bool]:
        """Delete journal - delegates to delete_journal for event publishing."""
        return await self.delete_journal(uid)

    # ========================================================================
    # FIFO CLEANUP FOR VOICE JOURNALS
    # ========================================================================

    async def _enforce_voice_journal_fifo(self, user_uid: str) -> Result[int]:
        """
        Enforce FIFO cleanup for voice journals.

        Voice journals (PJ1) have a max retention of 3.
        When a new voice journal is created, delete oldest entries
        to maintain the limit.

        Args:
            user_uid: User identifier

        Returns:
            Result containing count of journals deleted
        """
        max_retention = JournalType.VOICE.max_retention_count()
        if max_retention is None:
            return Result.ok(0)

        # Get all voice journals for user, sorted by created_at
        result = await self.backend.find_by(
            user_uid=user_uid,
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
    # SEARCH
    # ========================================================================

    @with_error_handling("search_journals", error_type="database")
    async def search_journals(
        self,
        query: str,
        user_uid: str | None = None,
        journal_type: JournalType | None = None,
        limit: int = 50,
    ) -> Result[list[JournalPure]]:
        """
        Search journals by text query.

        Searches title, content, and key_topics fields using database-level
        filtering (case-insensitive CONTAINS).

        Args:
            query: Search query string
            user_uid: Optional user filter
            journal_type: Optional type filter
            limit: Maximum results

        Returns:
            Result containing matching journals
        """
        if not query:
            return Result.fail(Errors.validation(message="Search query is required", field="query"))

        # Build dynamic WHERE clause for filters
        where_clauses = [
            "(toLower(j.title) CONTAINS toLower($query) OR "
            "toLower(j.content) CONTAINS toLower($query) OR "
            "any(topic IN j.key_topics WHERE toLower(topic) CONTAINS toLower($query)))"
        ]
        params: dict[str, Any] = {"query": query, "limit": limit}

        if user_uid:
            where_clauses.append("j.user_uid = $user_uid")
            params["user_uid"] = user_uid

        if journal_type:
            where_clauses.append("j.journal_type = $journal_type")
            params["journal_type"] = journal_type.value

        cypher_query = f"""
            MATCH (j:Journal)
            WHERE {" AND ".join(where_clauses)}
            RETURN j
            ORDER BY j.entry_date DESC
            LIMIT $limit
        """

        result = await self.backend.driver.execute_query(
            cypher_query,
            params,
            database_="neo4j",
        )

        journals = []
        for record in result.records:
            node = record["j"]
            dto = JournalDTO.from_dict(dict(node))
            journals.append(JournalPure.from_dto(dto))

        return Result.ok(journals)

    # ========================================================================
    # PROMOTE VOICE TO CURATED
    # ========================================================================

    @with_error_handling("promote_to_curated", error_type="database", uid_param="uid")
    async def promote_to_curated(self, uid: str) -> Result[JournalPure]:
        """
        Promote a voice journal to curated (permanent).

        Changes journal_type from VOICE to CURATED.
        This removes the journal from FIFO cleanup.

        Args:
            uid: Journal UID to promote

        Returns:
            Result containing the promoted journal
        """
        return await self.update_journal(
            uid,
            {"journal_type": JournalType.CURATED.value},
        )

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """
        Create journal entry when transcription completes.

        Pipeline:
        1. Try AI processing via TranscriptProcessorService (if available)
        2. Fall back to raw transcript if AI fails
        3. Create JournalPure using factory function
        4. Store via create_journal() (triggers FIFO cleanup)

        Args:
            event: TranscriptionCompleted event with transcript data

        Note:
            Errors logged but not raised - journal creation is best-effort
            to prevent transcription failure if journal creation fails.
        """
        from dataclasses import replace

        from core.models.journal.journal_pure import create_journal_from_transcription

        try:
            self.logger.info(
                f"Creating journal from transcription {event.transcription_uid} "
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

            # Generate UID with transcription reference
            timestamp = event.occurred_at.strftime("%Y%m%d%H%M%S")
            trans_suffix = event.transcription_uid.split(":")[-1][:8]
            journal_uid = f"journal:{event.user_uid}:{timestamp}:{trans_suffix}"

            # Create journal using factory
            journal = create_journal_from_transcription(
                uid=journal_uid,
                user_uid=event.user_uid,
                title=title,
                transcript_text=content,
                transcription_uid=event.transcription_uid,
                audio_file_path=event.audio_file_path,
                transcript_confidence=event.confidence_score,
                audio_duration=event.duration_seconds,
                journal_type=JournalType.VOICE,
            )

            # Add AI insights if available
            if key_topics or action_items or summary:
                metadata = dict(journal.metadata) if journal.metadata else {}
                if summary:
                    metadata["summary"] = summary
                journal = replace(
                    journal,
                    key_topics=key_topics,
                    action_items=action_items,
                    metadata=metadata,
                )

            # Create journal (triggers FIFO for VOICE journals)
            result = await self.create_journal(journal, enforce_fifo=True)

            if result.is_ok:
                self.logger.info(
                    f"Created journal {result.value.uid} from transcription "
                    f"{event.transcription_uid}"
                )
            else:
                self.logger.error(
                    f"Failed to create journal from {event.transcription_uid}: {result.error}"
                )

        except Exception as e:
            self.logger.error(
                f"Error handling transcription_completed for {event.transcription_uid}: {e}",
                exc_info=True,
            )
