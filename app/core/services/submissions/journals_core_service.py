"""
Journals Core Service
=====================

Journal-specific workflow operations extracted from SubmissionsCoreService.

Handles:
- Journal title generation with per-day sequence numbering
- Multi-step journal file upload orchestration (title → instructions → submit → process)
- Journal CRUD (create, ephemeral/permanent queries, date-range queries)
- FIFO cleanup for ephemeral voice journals
- Transcription-completed event handling (audio → journal entity)

Journals are SUBMISSION entities with entity_type=JOURNAL_SUBMISSION and
journal-specific fields in metadata: entry_date, mood, energy_level,
key_topics, action_items, source_type, source_file, transcription_uid.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.events.transcription_events import TranscriptionCompleted

from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.relationship_names import RelationshipName
from core.models.submissions.journal_submission import JournalSubmission
from core.ports import BackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.utils.decorators import with_error_handling
from core.utils.exception_types import LLM_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.submissions.journals")

# ============================================================================
# DEFAULT JOURNAL PROCESSING INSTRUCTIONS
# ============================================================================

DEFAULT_JOURNAL_INSTRUCTIONS = """# General Processing Instructions

## Purpose
Transform raw content into a well-formatted, readable document.

## Formatting Rules
1. **Structure**: Organize into coherent paragraphs
2. **Flow**: Remove verbal fillers ("um", "uh", "like")
3. **Clarity**: Improve sentence structure while preserving meaning
4. **Themes**: Identify main themes and group related content
5. **Action Items**: Extract concrete action items mentioned
6. **Title**: Generate concise, descriptive title

## Context Integration
- Reference active goals, tasks, habits when relevant
- Link to recent journal themes for continuity
- Identify learning opportunities from current paths

## Output Format
- Title (concise, descriptive)
- Summary (2-3 sentences)
- Main content (well-formatted paragraphs)
- Key themes (bullet list)
- Action items (if any)

Preserve the author's voice and authenticity while improving readability.
"""


@dataclass(frozen=True)
class JournalUploadResult:
    """Result of the multi-step journal upload orchestration."""

    submission_uid: str
    status: str
    processing_succeeded: bool
    message: str


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


class JournalsCoreService:
    """
    Journal-specific workflow operations.

    Standalone service (not BaseService) — receives backend, event_bus,
    content_enrichment in constructor. Post-init fields (submissions_service,
    processing_service, exercise_service) are wired in services_bootstrap.py
    to avoid circular dependencies.
    """

    def __init__(
        self,
        backend: BackendOperations[SubmissionEntity],
        event_bus: EventBusOperations | None = None,
        content_enrichment: Any | None = None,
    ) -> None:
        self.backend = backend
        self.event_bus = event_bus
        self.content_enrichment = content_enrichment
        self.logger = logger

        # Post-init wired in services_bootstrap.py (circular dep avoidance)
        self.submissions_service: Any | None = None
        self.processing_service: Any | None = None
        self.exercise_service: Any | None = None

    async def _count_journals_for_date(self, user_uid: str, entry_date: date) -> int:
        """Count journals owned by user on the given calendar day (for sequence ordering)."""

        day_start = datetime(entry_date.year, entry_date.month, entry_date.day, tzinfo=UTC)
        day_end = datetime(
            entry_date.year, entry_date.month, entry_date.day, 23, 59, 59, tzinfo=UTC
        )
        query = f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(j:Entity {{entity_type: 'journal_submission'}})
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
        return Result.ok(
            JournalSubmission.generate_title(user_uid, resolved_date, order=existing_count + 1)
        )

    async def submit_journal_file(
        self,
        file_content: bytes,
        filename: str,
        user_uid: str,
        custom_title: str = "",
        exercise_uid: str = "",
    ) -> Result[JournalUploadResult]:
        """Orchestrate multi-step journal file upload: title → instructions → submit → process.

        Steps:
        1. Resolve title (custom > auto-generated > filename fallback)
        2. Resolve processing instructions (exercise > DEFAULT_JOURNAL_INSTRUCTIONS)
        3. Submit file via SubmissionsService
        4. Auto-trigger AI processing via SubmissionsProcessingService

        Requires submissions_service and processing_service to be wired (post-init).
        exercise_service is optional — enables custom instructions from exercises.
        """
        if not self.submissions_service:
            return Result.fail(Errors.system("submissions_service not wired"))
        if not self.processing_service:
            return Result.fail(Errors.system("processing_service not wired"))

        # Step 1: Resolve title
        if custom_title:
            title = custom_title
        else:
            title_result = await self.generate_journal_title(user_uid)
            title = title_result.value if title_result.is_ok else filename

        # Step 2: Resolve processing instructions
        instructions_text = DEFAULT_JOURNAL_INSTRUCTIONS
        if exercise_uid and self.exercise_service:
            ex_result = await self.exercise_service.get_exercise(exercise_uid)
            if ex_result.is_ok and ex_result.value and ex_result.value.instructions:
                instructions_text = ex_result.value.instructions
                self.logger.info(f"Using exercise instructions: {exercise_uid}")

        self.logger.info(f"Journal upload: {filename} ({len(file_content)} bytes, title={title})")

        # Step 3: Submit file
        metadata: dict[str, Any] = {"project_uid": "__default__"}
        if exercise_uid:
            metadata["exercise_uid"] = exercise_uid

        result = await self.submissions_service.submit_file(
            file_content=file_content,
            original_filename=filename,
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL_SUBMISSION,
            processor_type=ProcessorType.LLM,
            title=title,
            metadata=metadata,
        )

        if result.is_error:
            return Result.fail(Errors.system(str(result.error)))

        report = result.value

        # Step 4: Auto-trigger AI processing
        # extract_activities=True enables DSL parsing: @context() tags → entities
        process_result = await self.processing_service.process_submission(
            report.uid,
            instructions={
                "custom_instructions": instructions_text,
                "extract_activities": True,
            },
        )

        if process_result.is_error:
            error_msg = "File uploaded but AI processing failed"
            if process_result.error:
                error_msg = f"{error_msg}: {process_result.error.user_message or process_result.error.message}"
            self.logger.warning(f"AI processing failed for {report.uid}: {error_msg}")
            return Result.ok(
                JournalUploadResult(
                    submission_uid=report.uid,
                    status="submitted",
                    processing_succeeded=False,
                    message=f"File uploaded. AI processing pending — {error_msg}",
                )
            )

        processed_report = process_result.value
        return Result.ok(
            JournalUploadResult(
                submission_uid=report.uid,
                status=processed_report.status if processed_report else "completed",
                processing_succeeded=True,
                message="File uploaded and processed by AI",
            )
        )

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
    ) -> Result[JournalSubmission]:
        """
        Create a journal submission entity.

        Journals are submission entities with entity_type=JOURNAL_SUBMISSION. max_retention controls
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

        journal = JournalSubmission(
            uid=uid,
            title=title,
            entity_type=EntityType.JOURNAL_SUBMISSION,
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
    async def get_ephemeral_journals(
        self, user_uid: str, limit: int = 10
    ) -> Result[list[JournalSubmission]]:
        """Get journals with FIFO retention (max_retention is set) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL_SUBMISSION.value,
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        reports = result.value or []
        journals = [k for k in reports if getattr(k, "max_retention", None) is not None]
        journals.sort(key=_get_entry_date_key, reverse=True)
        return Result.ok(journals[:limit])

    @with_error_handling("get_permanent_journals", error_type="database")
    async def get_permanent_journals(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[JournalSubmission]]:
        """Get permanent journals (no FIFO retention) for a user."""
        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=EntityType.JOURNAL_SUBMISSION.value,
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
    ) -> Result[list[JournalSubmission]]:
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
            entity_type=EntityType.JOURNAL_SUBMISSION.value,
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

        result = await self.backend.update(
            uid, {"max_retention": None, "updated_at": datetime.now()}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        updated = result.value
        if not updated:
            return Result.fail(Errors.not_found("resource", f"Submission {uid} not found"))

        return Result.ok(updated)

    async def get_journal_with_insights(self, uid: str) -> Result[JournalSubmission | None]:
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
        if not submission or submission.entity_type != EntityType.JOURNAL_SUBMISSION:
            return Result.ok(None)

        return Result.ok(submission)

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
            entity_type=EntityType.JOURNAL_SUBMISSION.value,
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

    async def handle_transcription_completed(self, event: "TranscriptionCompleted") -> None:
        """
        Create journal submission when transcription completes.

        Pipeline:
        1. Try AI processing via ContentEnrichmentService (if available)
        2. Fall back to raw transcript if AI fails
        3. Create submission with entity_type=JOURNAL_SUBMISSION and journal metadata via create_journal_entry()
        4. Triggers FIFO cleanup for VOICE journals

        Args:
            event: TranscriptionCompleted event with transcript data

        Note:
            Errors logged but not raised — journal creation is best-effort
            to prevent transcription failure if journal creation fails.
        """
        try:
            self.logger.info(
                f"Creating journal submission from transcription {event.transcription_uid} "
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
                    f"Created journal submission {result.value.uid} from transcription "
                    f"{event.transcription_uid}"
                )
            else:
                self.logger.error(
                    f"Failed to create journal submission from {event.transcription_uid}: {result.error}"
                )

        except (*NEO4J_EXCEPTIONS, *LLM_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling TranscriptionCompleted for {event.transcription_uid}: {e!s}"
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                f"Unexpected error handling TranscriptionCompleted for {event.transcription_uid}: {e!s}"
            )


def _get_created_at_key(submission: SubmissionEntity) -> datetime:
    """Get created_at from entity for sorting, with fallback to datetime.min."""
    return submission.created_at if submission.created_at else datetime.min
