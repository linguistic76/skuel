"""
UserEntryService — ADR-054
===========================

Facade over ``UserEntryBackend`` for the unified user-authored content
domain. Handles creation (with optional exercise link, TRANSFORMS edge,
and audience resolution), reads, updates, and deletion.

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
from core.models.enums.user_enums import UserRole
from core.models.interaction.interaction import Interaction
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_dto import UserEntryDTO
from core.models.user_entry.user_entry_request import (
    UserEntryCreateRequest,
    UserEntryUpdateRequest,
)
from core.ports.user_entry_protocols import UserEntryOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.user_entry.audience_resolver import AudienceResolver, ShareOutcome
from core.utils.decorators import with_error_handling
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.services.groups.group_service import GroupService
    from core.services.interaction.interaction_service import InteractionService
    from core.services.sharing.unified_sharing_service import UnifiedSharingService
    from core.services.user_service import UserService

# Re-exported for callers that import ``ShareOutcome`` from this module
# (the dataclass moved to ``audience_resolver`` during the /upload integration).
__all__ = ["ShareOutcome", "UserEntryService"]


class UserEntryService(BaseService[UserEntryOperations, UserEntry]):
    """Domain facade for ``UserEntry``.

    Composes ``UserEntryBackend`` + ``UnifiedSharingService`` +
    ``InteractionService`` to provide the single create/read/update/delete
    entry point for unified user-authored content.
    """

    _config = DomainConfig(
        dto_class=UserEntryDTO,
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
        audience_resolver: AudienceResolver | None = None,
        group_service: GroupService | None = None,
        user_service: UserService | None = None,
    ) -> None:
        super().__init__(backend, "UserEntryService")  # protocol type
        self.sharing_service = sharing_service
        self.interaction_service = interaction_service
        self.event_bus = event_bus
        self.user_service = user_service
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("skuel.services.user_entry")  # type: ignore[assignment]
        # AudienceResolver owns audience validation + sharing fan-out so the
        # /upload ingestion path can reuse the same logic without going
        # through this facade. Construct one if a caller hasn't provided it.
        self.audience_resolver = audience_resolver or AudienceResolver(
            sharing_service=sharing_service,
            group_service=group_service,
        )
        self.logger.info(f"UserEntry storage path: {self.storage_path}")

    # =========================================================================
    # CREATE
    # =========================================================================

    @with_error_handling("create_user_entry")
    async def create_entry(
        self,
        request: UserEntryCreateRequest,
        user_uid: UserUID,
    ) -> Result[tuple[UserEntry, ShareOutcome]]:
        """Create a ``UserEntry`` from a create request.

        Returns ``(entry, share_outcome)`` on success. The share outcome is
        empty when the pipeline does not require sharing; when sharing was
        attempted it carries the targets that landed and any that failed.

        For ``pipeline=TEACHER_REVIEW`` a total-share-failure (every requested
        target failed and none succeeded) is treated as compensation: the
        just-persisted entry is deleted and a validation error is returned,
        so ADR-054 §3's "no silent no-audience turn-ins" guarantee holds
        post-persist as well as pre-persist.

        See module docstring for the full create flow.
        """
        audience_check = self.audience_resolver.validate(request)
        if audience_check.is_error:
            return Result.fail(audience_check)

        # Verify the requester actually has a claim to any referenced entities —
        # otherwise a caller could attach this entry to another user's exercise
        # (cross-tenant leak via the auto-share fan-out) or masquerade a
        # TRANSFORMS chain over someone else's entry. The /upload ingestion path
        # already does this; create_entry must too (it's the shared write path).
        refs_check = await self.audience_resolver.validate_references(
            user_uid=user_uid,
            fulfills_exercise_uid=request.fulfills_exercise_uid,
            transforms_of_uid=request.transforms_of_uid,
        )
        if refs_check.is_error:
            return Result.fail(refs_check)

        # PUBLIC visibility is portfolio-publication and gated on TEACHER
        # role. This covers every entry point (YAML /upload, /submit form,
        # programmatic callers) so no path can set visibility=PUBLIC on a
        # REGISTERED user's entry.
        if request.visibility == Visibility.PUBLIC:
            public_check = await self._require_teacher_for_public(user_uid)
            if public_check.is_error:
                return Result.fail(public_check)

        # A caller-supplied uid (deterministic vault-note ids like
        # ``ue:daily:2026-06-16``) routes to an idempotent upsert below so
        # re-syncing an edited note updates in place; absent one we mint a
        # random uid and create fresh (the /submit form path).
        uid = EntityUID(request.uid) if request.uid else UIDGenerator.generate_random_uid("ue")
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
        elif request.uid:
            # Deterministic uid → idempotent MERGE-on-uid so vault re-sync of an
            # edited note updates in place instead of duplicating / violating the
            # uid constraint. Exercise-linked turn-ins always create fresh (they
            # mint a random uid), so this branch is mutually exclusive with the
            # FULFILLS_EXERCISE path above.
            create_result = await self.backend.upsert(entry)
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
        share_result = await self.audience_resolver.resolve_and_share(
            entry_uid=created.uid,
            user_uid=user_uid,
            request=request,
        )
        if share_result.is_error:
            return Result.fail(share_result)
        outcome: ShareOutcome = share_result.value

        # 5a. Compensation: a TEACHER_REVIEW entry with zero successful shares
        # and at least one failure would be an orphaned, invisible turn-in —
        # delete the entry and surface the failure (ADR §3 post-persist).
        if (
            request.pipeline == Pipeline.TEACHER_REVIEW
            and not outcome.any_success
            and outcome.any_failure
        ):
            failure_summary = ", ".join(f"{target}: {reason}" for target, reason in outcome.failed)
            self.logger.warning(
                f"Compensating orphaned TEACHER_REVIEW UserEntry {created.uid}: {failure_summary}"
            )
            cleanup = await self.backend.delete(created.uid, cascade=True)
            if cleanup.is_error:
                self.logger.error(
                    f"Compensation delete of {created.uid} failed: {cleanup.expect_error()}"
                )
            return Result.fail(
                Errors.validation(
                    "Submission could not be shared with any recipient; "
                    f"no audience was reached ({failure_summary})",
                    field="audience",
                )
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

        return Result.ok((created, outcome))

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
    ) -> Result[tuple[UserEntry, ShareOutcome]]:
        """Bytes-to-disk + UserEntry creation helper.

        Writes bytes to ``storage_path/YYYY-MM/{uid}/filename`` then delegates
        to :meth:`create_entry`. On persistence failure the file is best-effort
        removed.
        """
        file_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

        store_result = self._store_file(
            file_content, original_filename, UIDGenerator.generate_random_uid("ue")
        )
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
        return Result.ok(entity)

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
        return Result.ok(result.value or [])

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
        return await self.backend.update(uid, updates)

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
        for attr_name in ("title", "content", "summary", "description"):
            value = getattr(request, attr_name, None)
            if value is not None:
                updates[attr_name] = value
        if request.tags is not None:
            updates["tags"] = list(request.tags)
        if request.metadata is not None:
            updates["metadata"] = request.metadata
        if not updates:
            return Result.fail(Errors.validation("No updatable fields provided", field="request"))
        updates["updated_at"] = datetime.now()
        return await self.backend.update(uid, updates)

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

    @with_error_handling("delete_user_entry_as_teacher")
    async def delete_entry_as_teacher(self, uid: str, teacher_uid: UserUID) -> Result[bool]:
        """Cascade delete by a teacher who shares an active group with the entry's owner.

        Mirrors ``TeacherReviewService._verify_teacher_has_group_access``:
        empty access → ``not_found`` (404) so teachers outside the student's
        group cannot distinguish between "entry does not exist" and "entry
        belongs to another teacher's student."
        """
        access = await self.backend.verify_teacher_has_group_access(uid, teacher_uid)
        if access.is_error:
            return Result.fail(access)
        if not access.value:
            return Result.fail(Errors.not_found("UserEntry", uid))
        return await self.backend.delete(uid, cascade=True)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _require_teacher_for_public(self, user_uid: UserUID) -> Result[None]:
        """Gate ``visibility=PUBLIC`` on TEACHER role. Fail-closed if role cannot
        be resolved."""
        if self.user_service is None:
            return Result.fail(
                Errors.forbidden(
                    action="publish public UserEntry",
                    reason=(
                        "PUBLIC visibility requires TEACHER role but role cannot "
                        "be resolved (user_service unavailable)."
                    ),
                    required_role=UserRole.TEACHER.value,
                )
            )
        user_result = await self.user_service.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)
        user = user_result.value
        if user is None or not user.has_permission(UserRole.TEACHER):
            return Result.fail(
                Errors.forbidden(
                    action="publish public UserEntry",
                    reason="PUBLIC visibility requires TEACHER role.",
                    required_role=UserRole.TEACHER.value,
                )
            )
        return Result.ok(None)

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
