"""
JournalInputService — CRUD and file upload for JeInput entities
================================================================

Standalone facade implementing JournalInputOperations protocol.
Handles journal entry creation (text and file upload), retrieval,
lifecycle management, and title generation.

Pipeline position: User → **JournalInputService** → JeInput → JournalOutputService → JeOutput

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import mimetypes
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.journal_events import JeInputCreated, JeInputDeleted
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.journal.je_input import JeInput
from core.models.journal.je_input_dto import JeInputDTO
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import JournalInputBackend
    from core.ports.infrastructure_protocols import EventBusOperations

logger = get_logger("skuel.services.journal.input")


class JournalInputService:
    """CRUD and file upload facade for JeInput entities.

    Implements JournalInputOperations protocol. Does NOT extend BaseService —
    follows the standalone facade pattern established by JournalOutputService.
    """

    def __init__(
        self,
        backend: JournalInputBackend,
        storage_base: str,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        self.backend = backend
        self.storage_base = storage_base
        self.event_bus = event_bus

    # =========================================================================
    # CREATION
    # =========================================================================

    async def create_journal_entry(
        self,
        user_uid: UserUID,
        content: str | None = None,
        mood: str | None = None,
        energy_level: str | None = None,
        entry_date: date | None = None,
        instructions: str | None = None,
        max_retention: int | None = None,
    ) -> Result[JeInput]:
        """Create a text-based journal entry."""
        effective_date = entry_date or date.today()
        now = datetime.now(tz=UTC)

        # Generate sequential title
        title_result = await self.generate_journal_title(user_uid, effective_date)
        if title_result.is_error:
            return Result.fail(title_result)

        uid = UIDGenerator.generate_random_uid("ji")

        # Build metadata with journal-specific fields
        metadata: dict[str, Any] = {"entry_date": effective_date.isoformat()}
        if mood:
            metadata["mood"] = mood
        if energy_level:
            metadata["energy_level"] = energy_level

        entity = JeInput(
            uid=uid,
            entity_type=EntityType.JE_INPUT,
            title=title_result.value,
            content=content,
            status=EntityStatus.SUBMITTED,
            user_uid=user_uid,
            instructions=instructions,
            max_retention=max_retention,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

        create_result = await self.backend.create(entity)
        if create_result.is_error:
            logger.error(f"Failed to create JeInput: {create_result.error}")
            return Result.fail(create_result)

        je_input = create_result.value

        if self.event_bus:
            await publish_event(
                self.event_bus,
                JeInputCreated(
                    je_input_uid=uid,
                    user_uid=user_uid,
                    metadata=metadata,
                ),
                logger,
            )

        logger.info(f"JeInput created: {uid} (text entry)")
        return Result.ok(je_input)

    async def submit_journal_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: UserUID,
        file_type: str | None = None,
        instructions: str | None = None,
        max_retention: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[JeInput]:
        """Upload an audio/text file as journal entry."""
        if not file_content:
            return Result.fail(Errors.validation(message="File content is empty"))

        effective_date = date.today()
        now = datetime.now(tz=UTC)

        # Generate sequential title
        title_result = await self.generate_journal_title(user_uid, effective_date)
        if title_result.is_error:
            return Result.fail(title_result)

        uid = UIDGenerator.generate_random_uid("ji")

        # Determine file type from extension if not provided
        if not file_type:
            guessed, _ = mimetypes.guess_type(original_filename)
            file_type = guessed or "application/octet-stream"

        # Save file to disk
        ext = Path(original_filename).suffix or ".bin"
        file_path = Path(self.storage_base) / now.strftime("%Y-%m") / f"je_input_{uid}{ext}"

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(file_content)
        except OSError as e:
            logger.error(f"Failed to write je_input file {file_path}: {e}")
            return Result.fail(Errors.system(message=f"File write failed: {e}", service="journal"))

        # Build metadata
        entry_metadata: dict[str, Any] = {"entry_date": effective_date.isoformat()}
        if metadata:
            entry_metadata.update(metadata)

        entity = JeInput(
            uid=uid,
            entity_type=EntityType.JE_INPUT,
            title=title_result.value,
            status=EntityStatus.SUBMITTED,
            user_uid=user_uid,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            instructions=instructions,
            max_retention=max_retention,
            metadata=entry_metadata,
            created_at=now,
            updated_at=now,
        )

        create_result = await self.backend.create(entity)
        if create_result.is_error:
            # Clean up file on failure
            file_path.unlink(missing_ok=True)
            logger.error(f"Failed to create JeInput: {create_result.error}")
            return Result.fail(create_result)

        je_input = create_result.value

        if self.event_bus:
            await publish_event(
                self.event_bus,
                JeInputCreated(
                    je_input_uid=uid,
                    user_uid=user_uid,
                    file_type=file_type,
                    file_size=len(file_content),
                    original_filename=original_filename,
                    metadata=entry_metadata,
                ),
                logger,
            )

        logger.info(f"JeInput created: {uid} (file: {original_filename})")
        return Result.ok(je_input)

    # =========================================================================
    # RETRIEVAL
    # =========================================================================

    async def get_je_input(self, uid: str) -> Result[JeInput | None]:
        """Get a journal entry input by UID."""
        return await self.backend.get(uid)

    async def list_je_inputs(
        self,
        user_uid: UserUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[JeInput]]:
        """List journal entry inputs for a user."""
        filters: dict[str, Any] | None = None
        if status:
            filters = {"status": status}

        result = await self.backend.get_user_entities(
            user_uid=user_uid,
            filters=filters,
            limit=limit,
            offset=offset,
            sort_by="created_at",
            sort_order="desc",
        )
        if result.is_error:
            return Result.fail(result)

        entities, _total = result.value
        return Result.ok(entities)

    async def get_je_inputs_by_date_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
    ) -> Result[list[JeInput]]:
        """Get journal entries within a date range."""
        result = await self.backend.get_je_inputs_by_date_range(
            user_uid=user_uid,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            [JeInput.from_dto(JeInputDTO.from_dict(record)) for record in result.value]
        )

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def make_permanent(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Make an ephemeral journal entry permanent (disable FIFO cleanup)."""
        # Verify ownership
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if get_result.value is None:
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        je_input = get_result.value
        if je_input.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        update_result = await self.backend.update(uid, {"max_retention": None})
        if update_result.is_error:
            return Result.fail(update_result)

        logger.info(f"JeInput made permanent: {uid}")
        return Result.ok(True)

    async def delete_je_input(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Delete a journal entry input and its associated files."""
        # Verify ownership
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if get_result.value is None:
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        je_input = get_result.value
        if je_input.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="JeInput", identifier=uid))

        # Delete associated files
        for path_attr in ("file_path", "processed_file_path"):
            file_path_str = getattr(je_input, path_attr, None)
            if file_path_str:
                try:
                    Path(file_path_str).unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"Failed to delete {path_attr} {file_path_str}: {e}")

        # Delete Neo4j node
        delete_result = await self.backend.delete(uid, cascade=True)
        if delete_result.is_error:
            return Result.fail(delete_result)

        if self.event_bus:
            await publish_event(
                self.event_bus,
                JeInputDeleted(
                    je_input_uid=uid,
                    user_uid=user_uid,
                ),
                logger,
            )

        logger.info(f"JeInput deleted: {uid}")
        return Result.ok(True)

    # =========================================================================
    # TITLE GENERATION
    # =========================================================================

    async def generate_journal_title(
        self, user_uid: UserUID, entry_date: date | None = None
    ) -> Result[str]:
        """Generate a sequential title for a new journal entry."""
        effective_date = entry_date or date.today()

        count_result = await self.backend.count_je_inputs_for_date(
            user_uid=user_uid, entry_date=effective_date.isoformat()
        )
        if count_result.is_error:
            return Result.fail(count_result)

        order = count_result.value + 1
        return Result.ok(JeInput.generate_title(user_uid, effective_date, order))
