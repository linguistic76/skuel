"""
UserEntryService — ADR-054
===========================

Facade over ``UserEntryBackend`` for the unified user-authored content
domain. Handles creation (with optional exercise link, TRANSFORMS edge,
and audience resolution), reads, updates, and deletion.

Create flow
-----------
1. Build ``UserEntry`` from ``UserEntryCreateRequest``
2. Persist node. Three mutually exclusive paths:
     - **Turn-in** (``fulfills_exercise_uid`` + no caller uid): fresh
       random-uid node via ``backend.create_with_exercise_link`` — writes
       the ``FULFILLS_EXERCISE {revision}`` edge atomically.
     - **Living entry** (caller-supplied deterministic uid, with or
       without ``fulfills_exercise_uid``): idempotent ``backend.upsert``.
       A declared ``fulfills_exercise_uid`` is stored as a node property
       (intent — "exercise in progress"), NEVER as an edge; re-syncing an
       edited vault file updates the same node in place.
     - **Plain create** (no uid, no exercise): ``backend.create``.
3. Auto-create ``Interaction`` audit record (turn-ins only, when
   ``interaction_service`` is wired)
4. Wire optional ``TRANSFORMS`` edge for multi-stage pipelines
5. Resolve audience + call ``UnifiedSharingService``:
     - ``pipeline=TEACHER_REVIEW`` + exercise link + no explicit audience
       → auto-share to exercise's assigned groups
     - ``pipeline=TEACHER_REVIEW`` + no audience + no exercise → validation
       error (ADR §3: no silent no-audience turn-ins)
     - otherwise → honor explicit ``share_with_groups`` / ``share_with_users``
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.embedding_publisher import publish_embedding_requested
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
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.query_types import (
        ExtractionTwinRow,
        KnowledgeEntryGroundingRow,
        OrganizerResult,
    )
    from core.services.exercises.exercise_service import ExerciseService
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
        audience_resolver: AudienceResolver | None = None,
        group_service: GroupService | None = None,
        user_service: UserService | None = None,
        exercise_service: ExerciseService | None = None,
    ) -> None:
        super().__init__(backend, "UserEntryService")  # protocol type
        self.sharing_service = sharing_service
        self.interaction_service = interaction_service
        self.event_bus = event_bus
        self.user_service = user_service
        self.exercise_service = exercise_service
        self.logger = get_logger("skuel.services.user_entry")  # type: ignore[assignment]
        # AudienceResolver owns audience validation + sharing fan-out so the
        # /upload ingestion path can reuse the same logic without going
        # through this facade. Construct one if a caller hasn't provided it.
        self.audience_resolver = audience_resolver or AudienceResolver(
            sharing_service=sharing_service,
            group_service=group_service,
        )

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

        # TEACHER_REVIEW status is service-owned: the review workflow
        # (queue → approve/request-revision) is the only writer after create,
        # and create always stamps SUBMITTED. An authored/caller status could
        # otherwise fake the lifecycle (`completed` reads as teacher-approved,
        # `archived` dodges the queue) — reject anything but a truthful
        # `submitted` on every entry point (JSON API, YAML door, /submit form).
        if (
            request.status is not None
            and request.pipeline == Pipeline.TEACHER_REVIEW
            and request.status != EntityStatus.SUBMITTED
        ):
            return Result.fail(
                Errors.validation(
                    f"status '{request.status.value}' is not allowed for "
                    "teacher_review submissions — status is service-owned "
                    "(SUBMITTED at create; the review workflow advances it). "
                    "Remove the status field.",
                    field="status",
                )
            )

        # TEACHER_REVIEW turn-ins are frozen artifacts — always a fresh node,
        # never an upsert. A deterministic uid would make the "pages handed to
        # the teacher" mutable after submission. The vault living channel
        # authors a non-review pipeline (e.g. knowledge) and flips
        # ``status: submitted`` to file a frozen copy through the no-uid path.
        if (
            request.uid
            and request.pipeline == Pipeline.TEACHER_REVIEW
            and request.fulfills_exercise_uid
        ):
            return Result.fail(
                Errors.validation(
                    "pipeline=teacher_review with fulfills_exercise_uid always "
                    "creates a fresh turn-in — remove the uid field. For a vault "
                    "living entry, use a non-review pipeline and flip "
                    "'status: submitted' to file a frozen copy.",
                    field="uid",
                )
            )

        # PUBLIC visibility is portfolio-publication and gated on TEACHER
        # role. This covers every entry point (YAML /upload, /submit form,
        # programmatic callers) so no path can set visibility=PUBLIC on a
        # REGISTERED user's entry.
        if request.visibility == Visibility.PUBLIC:
            public_check = await self._require_teacher_for_public(user_uid)
            if public_check.is_error:
                return Result.fail(public_check)

        # A turn-in is an exercise link WITHOUT a caller uid: it must always
        # create fresh (frozen copy, FULFILLS_EXERCISE edge, revision mint), so
        # it gets a random uid — the /submit form and /upload YAML paths.
        # A caller-supplied deterministic uid (vault-note ids like
        # ``ue:daily:2026-06-16``) routes to the idempotent upsert below so
        # re-syncing an edited note updates in place — WITH or without a
        # declared exercise. The deterministic-uid + fulfills combination is
        # the vault living channel: the declaration is stored as intent on the
        # node, never as an edge (the frozen copies carry the edges).
        turn_in_exercise_uid = None if request.uid else request.fulfills_exercise_uid
        if request.uid:
            uid = EntityUID(request.uid)
        else:
            uid = UIDGenerator.generate_random_uid("ue")
        now = datetime.now()

        # Propagate exercise.enrichment_mode into metadata so InstructionResolver
        # can select the right template during LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE
        # processing. Caller-supplied metadata["enrichment_mode"] wins (explicit beats
        # implicit); the exercise lookup is best-effort and a miss is non-fatal.
        # Keyed on the declared exercise (not just turn-ins): a living entry
        # that declares an exercise and later runs an LLM pipeline should
        # resolve the exercise-specific enrichment mode too (Kody #508).
        metadata: dict[str, Any] = dict(request.metadata or {})
        if (
            request.fulfills_exercise_uid
            and self.exercise_service is not None
            and "enrichment_mode" not in metadata
        ):
            ex_result = await self.exercise_service.get_exercise(request.fulfills_exercise_uid)
            if ex_result.is_ok:
                ex_em = ex_result.value.enrichment_mode
                if ex_em is not None:
                    metadata["enrichment_mode"] = ex_em.value

        entry = UserEntry(
            uid=uid,
            title=request.title,
            entity_type=EntityType.USER_ENTRY,
            user_uid=user_uid,
            content=request.content,
            description=request.description,
            status=request.status
            or (
                EntityStatus.SUBMITTED
                if request.pipeline == Pipeline.TEACHER_REVIEW
                else EntityStatus.ACTIVE
            ),
            tags=tuple(request.tags),
            metadata=metadata,
            pipeline=request.pipeline,
            private=request.private,
            modality=request.modality,
            instructions=request.instructions,
            journal_mode=request.journal_mode,
            original_filename=request.original_filename,
            file_path=request.file_path,
            file_size=request.file_size,
            file_type=request.file_type,
            visibility=request.visibility or Visibility.PRIVATE,
            fulfills_exercise_uid=request.fulfills_exercise_uid,
            created_at=now,
            updated_at=now,
        )

        # 2. Persist node (turn-in / living upsert / plain create)
        if turn_in_exercise_uid:
            revision = await self._next_revision(user_uid, turn_in_exercise_uid)
            create_result = await self.backend.create_with_exercise_link(
                entry=entry,
                exercise_uid=turn_in_exercise_uid,
                revision=revision,
            )
        elif request.uid:
            # Deterministic uid → idempotent MERGE-on-uid so vault re-sync of an
            # edited note updates in place instead of duplicating. A declared
            # ``fulfills_exercise_uid`` rides along as the intent property only
            # — no FULFILLS_EXERCISE edge, no revision mint (the living channel;
            # frozen copies file through the turn-in branch above).
            #
            # Ownership is enforced atomically inside `backend.upsert` (the MERGE
            # gates its write on the existing owner and returns not-found on a
            # mismatch). A separate preflight read here would reintroduce the
            # TOCTOU race the constraint-backed MERGE exists to close.
            create_result = await self.backend.upsert(entry)
        else:
            create_result = await self.backend.create(entry)

        if create_result.is_error:
            return Result.fail(create_result)
        created: UserEntry = create_result.value

        # 3. Auto-create Interaction audit record — turn-ins only. A living
        # entry's declared intent is not a submission event; the audit record
        # mints when the frozen copy files. The PathStep context is what
        # the PS submissions-and-feedback query anchors on (INTERACTION_DURING),
        # so about_path_step_uid must ride onto the record.
        if turn_in_exercise_uid and self.interaction_service is not None:
            await self._create_interaction_record(
                entry_uid=created.uid,
                user_uid=user_uid,
                exercise_uid=turn_in_exercise_uid,
                path_step_uid=request.about_path_step_uid,
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

        # Post-persist embedding refresh (ADR-074) — pipeline-scoped: only
        # knowledge entries (knowledge/ + consented je_pro/ notes) embed;
        # turn-ins, teacher-review submissions, and LLM outputs never do.
        # Private notes never do either (canon P3) — no vector may exist for
        # them; the upsert's null-serializing `ON MATCH SET n +=` retracts a
        # stale one on a flip-to-private re-sync.
        # Covers the living-channel upsert too (vault re-sync of an edited
        # note lands here); content-hash idempotency makes an unchanged
        # re-sync a no-op at the worker.
        if created.pipeline == Pipeline.KNOWLEDGE and not created.private:
            await publish_embedding_requested(
                self.event_bus, EntityType.USER_ENTRY, created, self.logger
            )

        # Event-side ``fulfills_exercise_uid`` means "a turn-in was filed" —
        # the exercise_handler subscriber runs the linker (scope validation +
        # revision title-stamp) off it. A living entry's declared intent must
        # NOT trigger that machinery, so the field rides only for turn-ins.
        await publish_event(
            self.event_bus,
            UserEntryCreated(
                entity_uid=created.uid,
                user_uid=user_uid,
                pipeline=request.pipeline.value,
                modality=request.modality.value if request.modality else None,
                fulfills_exercise_uid=turn_in_exercise_uid,
                transforms_of_uid=request.transforms_of_uid,
                file_type=request.file_type,
            ),
            self.logger,
        )

        return Result.ok((created, outcome))

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

    @with_error_handling("list_exercise_entries")
    async def list_exercise_entries(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[UserEntry]]:
        """List the user's exercise submissions (submission history).

        Defined by the FULFILLS_EXERCISE edge, not by pipeline — an AI-destined
        turn-in belongs in the submitter's history exactly like a teacher-review
        one (systems review, 2026-07-03).

        Backend: UserEntryBackend.get_exercise_entries_for_user.
        """
        result = await self.backend.get_exercise_entries_for_user(user_uid, limit)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(self._to_domain_models(result.value or [], UserEntryDTO, UserEntry))

    @with_error_handling("list_knowledge_entries_with_grounding")
    async def list_knowledge_entries_with_grounding(
        self,
        user_uid: UserUID,
        limit: int = 500,
    ) -> Result[list[KnowledgeEntryGroundingRow]]:
        """Knowledge-pipeline entries with their grounded-Ku chips.

        The read behind the knowledge-notes surface — the user reviews (and
        prunes) what SKUEL inferred about their notes; grounding edges are
        eager writes, the user is editor, not approver (ruling 2026-07-11).
        Each row carries a confidence-ordered ``grounded_kus`` list.

        Backend: _UserEntryContentMixin.get_knowledge_entries_with_grounding.
        """
        result = await self.backend.get_knowledge_entries_with_grounding(user_uid, limit)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    @with_error_handling("get_latest_entry_for_exercise")
    async def get_latest_entry_for_exercise(
        self,
        user_uid: UserUID,
        exercise_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """The user's newest turn-in (uid, content, revision) for an exercise.

        The vault exercise channel's dedup source: a frozen copy is filed only
        when the living file's content differs from this row's ``content``.
        Returns ``None`` when the user has never turned the exercise in.

        Backend: _UserEntryCrudMixin.get_latest_entry_for_exercise.
        """
        return await self.backend.get_latest_entry_for_exercise(user_uid, exercise_uid)

    @with_error_handling("get_organized_children")
    async def get_organized_children(self, uid: str) -> Result[list[OrganizerResult]]:
        """Ordered ORGANIZES children of an entry — the emergent-MOC map.

        A user entry with outgoing ORGANIZES edges (drawn by the vault MOC
        ingestion, ``moc: true``) is a Map of Content; /gradebook/{uid} renders
        its children as cards. NOT ownership-verified — callers gate on an
        owner-scoped :meth:`get_entry` first.

        Backend: _OrganizesMixin.get_organized_children (shared with PsBackend).
        """
        return await self.backend.get_organized_children(uid)

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
        result = await self.backend.update(uid, updates)
        if (
            result.is_ok
            and result.value.pipeline == Pipeline.KNOWLEDGE
            and not result.value.private
        ):
            # Post-persist embedding refresh (ADR-074) — non-private knowledge
            # entries only
            await publish_embedding_requested(
                self.event_bus,
                EntityType.USER_ENTRY,
                result.value,
                self.logger,
                changed_fields=updates,
            )
        return result

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
        result = await self.backend.update(uid, updates)
        if (
            result.is_ok
            and result.value.pipeline == Pipeline.KNOWLEDGE
            and not result.value.private
        ):
            # Post-persist embedding refresh (ADR-074) — non-private knowledge
            # entries only; the changed_fields gate skips tag/metadata-only edits.
            await publish_embedding_requested(
                self.event_bus,
                EntityType.USER_ENTRY,
                result.value,
                self.logger,
                changed_fields=updates,
            )
        return result

    # =========================================================================
    # JOURNAL CONTEXT
    # =========================================================================

    async def get_vault_notes_for_context(
        self, user_uid: UserUID, limit: int = 8
    ) -> Result[list[dict[str, Any]]]:
        """Vault-synced personal notes for the journal context digest.

        Returns up to ``limit`` notes (title + 300-char snippet) ordered by
        most-recently-updated. Only entries with ``pipeline`` journal or
        knowledge AND ``vault_file_path`` in metadata are returned — so
        vault-synced doorway notes qualify (including consented ``je_pro/``
        entries, which carry ``pipeline=knowledge``), while journal sessions
        and other pipelines stay out. Notes marked ``private: true`` are
        excluded — this read feeds journal prompts (canon P3 gate).

        Backend: _UserEntryContentMixin.get_vault_notes_for_context.
        """
        return await self.backend.get_vault_notes_for_context(user_uid, limit)

    # =========================================================================
    # VAULT BRIDGE (ADR-070)
    # =========================================================================

    async def get_extracted_entities(self, entry_uid: str) -> Result[list[dict[str, Any]]]:
        """Return extracted entity UIDs + EXTRACTED_FROM edge properties.

        Backend: UserEntryBackend.get_extracted_entities_for_entry.
        """
        return await self.backend.get_extracted_entities_for_entry(entry_uid)

    async def update_extracted_vault_id(
        self, entry_uid: str, entity_uid: str, vault_id: str
    ) -> Result[bool]:
        """Set vault_id on an EXTRACTED_FROM edge after ID injection (ADR-070).

        Backend: UniversalNeo4jBackend (via _RelationshipCrudMixin).update_extracted_from_vault_id.
        """
        return await self.backend.update_extracted_from_vault_id(entry_uid, entity_uid, vault_id)

    # =========================================================================
    # PROCESSING PIPELINE (UserEntryProcessingService)
    # =========================================================================

    async def get_user_active_extraction_twins(
        self, user_uid: UserUID, labels: list[str]
    ) -> Result[list[ExtractionTwinRow]]:
        """Return the user's OWNED, non-terminal entities for extraction dedup Guard 4.

        Backend: UserEntryBackend.get_user_active_extraction_twins.
        """
        return await self.backend.get_user_active_extraction_twins(user_uid, labels)

    async def create_extracted_from_links(
        self, entry_uid: str, links: list[tuple[str, str, str | None]]
    ) -> Result[int]:
        """Batch-write EXTRACTED_FROM provenance edges for DSL-created entities (ADR-069).

        Backend: UserEntryBackend.create_extracted_from_links.
        """
        return await self.backend.create_extracted_from_links(entry_uid, links)

    async def update_processing_state(
        self,
        uid: str,
        updates: dict[
            str, Any
        ],  # boundary: raw update patch — mixes scalars, datetimes, and a nested metadata dict that backend.update JSON-serializes into a string prop
    ) -> Result[UserEntry]:
        """Persist pipeline state on an entry (status, processing_error, run metadata).

        Internal to the processing pipeline — bypasses the ownership-verified
        ``update_entry`` path because the writer is the system, not the user,
        and the fields are processing bookkeeping, not user content.

        Backend: UserEntryBackend.update.
        """
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
        path_step_uid: str | None = None,
    ) -> None:
        """Fire-and-forget Interaction audit record.

        Ports the behavior from ``SubmissionsService._create_interaction_record``
        with the new entity type. The entry is already persisted; a failure
        here is logged but not propagated. ``path_step_uid`` becomes the
        INTERACTION_DURING context edge the PS feedback view anchors on.
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
                context_path_step_uid=path_step_uid,
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
