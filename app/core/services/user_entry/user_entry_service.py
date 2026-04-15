"""
UserEntryService — ADR-054 Step 5
==================================

Facade over ``UserEntryBackend`` for the unified user-authored content
domain. Handles creation (with optional exercise link, TRANSFORMS edge,
and audience resolution), reads, updates, and deletion.

Additive through Step 13 — the legacy ``core/services/submissions/`` and
``core/services/journal/`` packages remain in place. Routes + processing
handlers are rewired in later steps.

Create flow
-----------
1. Build ``UserEntry`` from ``UserEntryCreateRequest``
2. Persist node (via ``backend.create_with_exercise_link`` when an
   exercise link is present, otherwise plain ``backend.create``)
3. Auto-create ``Interaction`` audit record (when linked to an exercise
   and ``interaction_service`` is wired)
4. Wire optional ``TRANSFORMS`` edge for multi-stage pipelines
5. Resolve audience + call ``UnifiedSharingService``:
     - ``pipeline=TEACHER_REVIEW`` + exercise link + no explicit audience
       → auto-share to exercise's assigned groups
     - ``pipeline=TEACHER_REVIEW`` + no audience + no exercise → validation
       error (ADR §3: no silent no-audience turn-ins)
     - otherwise → honor explicit ``share_with_groups`` / ``share_with_users``

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
"""

from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.user_entry_events import UserEntryCreated
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.interaction_enums import InteractionType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.interaction.interaction import Interaction
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryUpdateRequest,
)
from core.ports.user_entry_protocols import UserEntryOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.interaction.interaction_service import InteractionService
    from core.services.sharing.unified_sharing_service import UnifiedSharingService


class UserEntryService(BaseService[UserEntryOperations, UserEntry]):
    """Domain facade for ``UserEntry``.

    Composes ``UserEntryBackend`` + ``UnifiedSharingService`` +
    ``InteractionService`` to provide the single create/read/update/delete
    entry point for unified user-authored content.
    """

    _config = DomainConfig(
        dto_class=UserEntry,  # type: ignore[arg-type]  # UserEntry has from_dto/to_dto
        model_class=UserEntry,
        entity_label="Entity",
        search_fields=("title", "content", "processed_content", "original_filename"),
        search_order_by="created_at",
        category_field="pipeline",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self,
        backend: UserEntryOperations,
        sharing_service: UnifiedSharingService | None = None,
        interaction_service: InteractionService | None = None,
        event_bus: EventBusOperations | None = None,
        storage_path: str = "/tmp/skuel_user_entries",
    ) -> None:
        super().__init__(backend, "UserEntryService")  # type: ignore[arg-type]  # protocol type
        self.sharing_service = sharing_service
        self.interaction_service = interaction_service
        self.event_bus = event_bus
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("skuel.services.user_entry")  # type: ignore[assignment]
        self.logger.info(f"UserEntry storage path: {self.storage_path}")

    # =========================================================================
    # CREATE
    # =========================================================================

    @with_error_handling("create_user_entry")
    async def create_entry(
        self,
        request: UserEntryCreateRequest,
        user_uid: UserUID,
    ) -> Result[UserEntry]:
        """Create a ``UserEntry`` from a create request.

        See module docstring for the full create flow.
        """
        audience_check = self._validate_audience(request)
        if audience_check.is_error:
            return Result.fail(audience_check)

        uid = UIDGenerator.generate_random_uid("ue")
        now = datetime.now()

        entry = UserEntry(
            uid=uid,
            title=request.title,
            entity_type=EntityType.USER_ENTRY,
            user_uid=user_uid,
            content=request.content,
            status=EntityStatus.SUBMITTED
            if request.pipeline == Pipeline.TEACHER_REVIEW
            else EntityStatus.ACTIVE,
            tags=tuple(request.tags),
            metadata=request.metadata or {},
            pipeline=request.pipeline,
            modality=request.modality,
            instructions=request.instructions,
            original_filename=request.original_filename,
            file_path=request.file_path,
            file_size=request.file_size,
            file_type=request.file_type,
            visibility=request.visibility or Visibility.PRIVATE,
            created_at=now,
            updated_at=now,
        )

        # 2. Persist node (with or without exercise link)
        if request.fulfills_exercise_uid:
            revision = await self._next_revision(user_uid, request.fulfills_exercise_uid)
            create_result = await self.backend.create_with_exercise_link(
                entry=entry,
                exercise_uid=request.fulfills_exercise_uid,
                revision=revision,
            )
        else:
            create_result = await self.backend.create(entry)

        if create_result.is_error:
            return Result.fail(create_result)
        created: UserEntry = create_result.value

        # 3. Auto-create Interaction audit record
        if request.fulfills_exercise_uid and self.interaction_service is not None:
            await self._create_interaction_record(
                entry_uid=created.uid,
                user_uid=user_uid,
                exercise_uid=request.fulfills_exercise_uid,
            )

        # 4. Optional TRANSFORMS edge (multi-stage pipelines)
        if request.transforms_of_uid:
            transforms_result = await self.backend.add_relationship(
                from_uid=created.uid,
                to_uid=request.transforms_of_uid,
                relationship_type=RelationshipName.TRANSFORMS,
            )
            if transforms_result.is_error:
                self.logger.warning(
                    f"Failed to create TRANSFORMS edge {created.uid} -> "
                    f"{request.transforms_of_uid}: {transforms_result.expect_error()}"
                )

        # 5. Resolve audience + share
        await self._resolve_and_share(
            entry_uid=created.uid,
            user_uid=user_uid,
            request=request,
        )

        self.logger.info(
            f"UserEntry created: {created.uid} (pipeline={request.pipeline.value}, "
            f"fulfills_exercise={request.fulfills_exercise_uid or '-'})"
        )

        await publish_event(
            self.event_bus,
            UserEntryCreated(
                entity_uid=created.uid,
                user_uid=user_uid,
                pipeline=request.pipeline.value,
                modality=request.modality.value if request.modality else None,
                fulfills_exercise_uid=request.fulfills_exercise_uid,
                transforms_of_uid=request.transforms_of_uid,
                file_type=request.file_type,
            ),
            self.logger,
        )

        return Result.ok(created)

    @with_error_handling("submit_user_entry_file")
    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: UserUID,
        pipeline: Pipeline,
        title: str | None = None,
        instructions: str | None = None,
        fulfills_exercise_uid: str | None = None,
        transforms_of_uid: str | None = None,
        share_with_groups: list[str] | None = None,
        share_with_users: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[UserEntry]:
        """Bytes-to-disk + UserEntry creation helper.

        Writes bytes to ``storage_path/YYYY-MM/{uid}/filename`` then delegates
        to :meth:`create_entry`. On persistence failure the file is best-effort
        removed.
        """
        uid = UIDGenerator.generate_random_uid("ue")
        file_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

        store_result = self._store_file(file_content, original_filename, uid)
        if store_result.is_error:
            return Result.fail(store_result)
        file_path = store_result.value

        request = UserEntryCreateRequest(
            title=title or original_filename,
            pipeline=pipeline,
            instructions=instructions,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            fulfills_exercise_uid=fulfills_exercise_uid,
            transforms_of_uid=transforms_of_uid,
            share_with_groups=share_with_groups or [],
            share_with_users=share_with_users or [],
            metadata=metadata,
        )

        create_result = await self.create_entry(request=request, user_uid=user_uid)
        if create_result.is_error:
            try:
                file_path.unlink()
            except OSError as cleanup_error:
                self.logger.warning(
                    f"Failed to clean up file after UserEntry create error: {cleanup_error}"
                )
            return create_result
        return create_result

    def _store_file(self, file_content: bytes, filename: str, entry_uid: str) -> Result[Path]:
        """Write file bytes to ``storage_path/YYYY-MM/{entry_uid}/filename``."""
        try:
            month_dir = self.storage_path / datetime.now().strftime("%Y-%m")
            entry_dir = month_dir / entry_uid
            entry_dir.mkdir(parents=True, exist_ok=True)
            file_path = entry_dir / filename
            file_path.write_bytes(file_content)
            self.logger.info(f"UserEntry file stored: {file_path}")
            return Result.ok(file_path)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to store file: {e!s}",
                    operation="store_user_entry_file",
                    exception=e,
                )
            )

    # =========================================================================
    # READ
    # =========================================================================

    @with_error_handling("get_user_entry")
    async def get_entry(self, uid: str, user_uid: UserUID) -> Result[UserEntry | None]:
        """Ownership-verified fetch. Returns ``None`` when not owned by user."""
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result)
        entity = result.value
        if entity is None:
            return Result.ok(None)
        if getattr(entity, "user_uid", None) != user_uid:
            return Result.ok(None)
        return Result.ok(entity)  # type: ignore[return-value]

    @with_error_handling("list_user_entries")
    async def list_for_user(
        self,
        user_uid: UserUID,
        pipeline: Pipeline | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[UserEntry]]:
        """List entries owned by a user, optionally filtered by pipeline/status."""
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "entity_type": EntityType.USER_ENTRY.value,
        }
        if pipeline is not None:
            filters["pipeline"] = pipeline.value
        if status is not None:
            filters["status"] = status.value

        result = await self.backend.find_by(
            **filters,
            limit=limit,
            offset=offset,
            sort_by="created_at",
            sort_order="desc",
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])  # type: ignore[return-value]

    @with_error_handling("list_entries_for_exercise")
    async def list_for_exercise(
        self,
        user_uid: UserUID,
        exercise_uid: str,
    ) -> Result[int]:
        """Return the count of a user's entries against an exercise.

        Delegates to the backend's ``count_entries_for_exercise`` helper,
        which resolves ``RevisedExercise`` to the root ``Exercise`` first.
        """
        return await self.backend.count_entries_for_exercise(
            user_uid=user_uid,
            exercise_uid=exercise_uid,
        )

    @with_error_handling("get_review_queue")
    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Teacher review queue — entries shared to the teacher's groups."""
        return await self.backend.get_review_queue_by_groups(
            teacher_uid=teacher_uid,
            status_filter=status_filter,
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    @with_error_handling("update_processed_content")
    async def update_processed_content(
        self,
        uid: str,
        processed_content: str,
        processed_file_path: str | None = None,
    ) -> Result[UserEntry]:
        """Update an entry's processed content (LLM/Deepgram output)."""
        updates: dict[str, Any] = {
            "processed_content": processed_content,
            "processing_completed_at": datetime.now(),
            "status": EntityStatus.COMPLETED.value,
        }
        if processed_file_path:
            updates["processed_file_path"] = processed_file_path
        return await self.backend.update(uid, updates)  # type: ignore[return-value]

    @with_error_handling("update_user_entry")
    async def update_entry(
        self,
        uid: str,
        user_uid: UserUID,
        request: UserEntryUpdateRequest,
    ) -> Result[UserEntry]:
        """Ownership-verified update of content-level fields."""
        owned = await self.get_entry(uid, user_uid)
        if owned.is_error:
            return Result.fail(owned)
        if owned.value is None:
            return Result.fail(Errors.not_found("UserEntry", uid))

        updates: dict[str, Any] = {}
        for field in ("title", "content", "summary", "description"):
            value = getattr(request, field, None)
            if value is not None:
                updates[field] = value
        if request.tags is not None:
            updates["tags"] = list(request.tags)
        if request.metadata is not None:
            updates["metadata"] = request.metadata
        if not updates:
            return Result.fail(Errors.validation("No updatable fields provided", field="request"))
        updates["updated_at"] = datetime.now()
        return await self.backend.update(uid, updates)  # type: ignore[return-value]

    # =========================================================================
    # DELETE
    # =========================================================================

    @with_error_handling("delete_user_entry")
    async def delete_entry(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Ownership-verified cascade delete."""
        owned = await self.get_entry(uid, user_uid)
        if owned.is_error:
            return Result.fail(owned)
        if owned.value is None:
            return Result.fail(Errors.not_found("UserEntry", uid))
        return await self.backend.delete(uid, cascade=True)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _validate_audience(self, request: UserEntryCreateRequest) -> Result[bool]:
        """ADR §3 guardrail: TEACHER_REVIEW must resolve to a real audience.

        Allowed:
          - Explicit ``share_with_groups`` / ``share_with_users``
          - ``fulfills_exercise_uid`` set (we'll auto-share to exercise groups)

        Rejected:
          - ``pipeline=TEACHER_REVIEW`` with neither of the above
        """
        if request.pipeline != Pipeline.TEACHER_REVIEW:
            return Result.ok(True)
        has_audience = bool(
            request.share_with_groups or request.share_with_users or request.fulfills_exercise_uid
        )
        if not has_audience:
            return Result.fail(
                Errors.validation(
                    "pipeline=TEACHER_REVIEW requires an audience: set "
                    "fulfills_exercise_uid, share_with_groups, or share_with_users",
                    field="audience",
                )
            )
        return Result.ok(True)

    async def _next_revision(self, user_uid: UserUID, exercise_uid: str) -> int:
        """Compute the next revision number for (user, exercise)."""
        count_result = await self.backend.count_entries_for_exercise(
            user_uid=user_uid,
            exercise_uid=exercise_uid,
        )
        if count_result.is_error:
            return 1
        return int(count_result.value or 0) + 1

    async def _create_interaction_record(
        self,
        entry_uid: str,
        user_uid: UserUID,
        exercise_uid: str,
    ) -> None:
        """Fire-and-forget Interaction audit record.

        Ports the behavior from ``SubmissionsService._create_interaction_record``
        with the new entity type. The entry is already persisted; a failure
        here is logged but not propagated.
        """
        if self.interaction_service is None:
            return
        try:
            ia_uid = UIDGenerator.generate_random_uid("ia")
            interaction = Interaction(
                uid=ia_uid,
                title=f"user_entry — {exercise_uid}",
                entity_type=EntityType.INTERACTION,
                user_uid=user_uid,
                interaction_type=InteractionType.EXERCISE_SUBMISSION,
                target_uid=exercise_uid,
                source_entity_uid=entry_uid,
            )
            result = await self.interaction_service.create_interaction(interaction)
            if result.is_error:
                self.logger.warning(
                    f"Failed to create Interaction for UserEntry {entry_uid}: "
                    f"{result.expect_error()}"
                )
        except Exception as e:  # safety-net: audit must not fail the submission
            self.logger.warning(
                f"Unexpected error creating Interaction for UserEntry {entry_uid}: {e}"
            )

    async def _resolve_and_share(
        self,
        entry_uid: str,
        user_uid: UserUID,
        request: UserEntryCreateRequest,
    ) -> None:
        """Fire-and-forget audience resolution + share calls.

        Policy:
          1. Explicit ``share_with_groups`` / ``share_with_users`` — share
             directly via ``UnifiedSharingService``.
          2. ``pipeline=TEACHER_REVIEW`` + ``fulfills_exercise_uid`` + no
             explicit audience — auto-share to the exercise's assigned
             groups (discovered via ``get_groups_shared_with``).
          3. Otherwise — no sharing (default visibility=PRIVATE).
        """
        if self.sharing_service is None:
            return

        shared_any = False

        for group_uid in request.share_with_groups:
            result = await self.sharing_service.share_with_group(
                entity_uid=entry_uid,
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with group "
                    f"{group_uid}: {result.expect_error()}"
                )
            else:
                shared_any = True

        for recipient_uid in request.share_with_users:
            result = await self.sharing_service.share(
                entity_uid=entry_uid,
                owner_uid=user_uid,
                recipient_uid=recipient_uid,
            )
            if result.is_error:
                self.logger.warning(
                    f"Failed to share UserEntry {entry_uid} with user "
                    f"{recipient_uid}: {result.expect_error()}"
                )
            else:
                shared_any = True

        # Auto-share to exercise's assigned groups for TEACHER_REVIEW default
        if (
            not shared_any
            and request.pipeline == Pipeline.TEACHER_REVIEW
            and request.fulfills_exercise_uid
        ):
            groups_result = await self.sharing_service.get_groups_shared_with(
                entity_uid=request.fulfills_exercise_uid,
            )
            if groups_result.is_error:
                self.logger.warning(
                    f"Could not resolve exercise groups for auto-share: "
                    f"{groups_result.expect_error()}"
                )
                return
            for record in groups_result.value or []:
                raw = record.get("group_uid") if isinstance(record, dict) else None
                if not raw:
                    continue
                group_uid_str = str(raw)
                share_result = await self.sharing_service.share_with_group(
                    entity_uid=entry_uid,
                    owner_uid=user_uid,
                    group_uid=group_uid_str,
                )
                if share_result.is_error:
                    self.logger.warning(
                        f"Auto-share of {entry_uid} to group {group_uid_str} failed: "
                        f"{share_result.expect_error()}"
                    )
