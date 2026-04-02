"""
Submission Service
==================

Handles file uploads and submission record creation.

Responsibilities:
- Store uploaded files (local or cloud)
- Create submission records in Neo4j
- Basic CRUD for user-owned submissions (SUBMISSION, ACTIVITY_REPORT, EXERCISE_REPORT)
- Query by type, status, user

Does NOT handle:
- Processing logic (SubmissionsProcessingService)
- AI content enrichment (ContentEnrichmentService)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.submission_events import SubmissionCreated
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.interaction_enums import InteractionType
from core.models.enums.submissions_enums import SubmissionModality
from core.models.interaction.interaction import Interaction
from core.models.relationship_names import RelationshipName
from core.models.submissions.submission import Submission
from core.models.submissions.submission_dto import SubmissionDTO
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.ports.query_types import SubmissionStatistics
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.services.interaction.interaction_service import InteractionService


class SubmissionsService(BaseService[BackendOperations[Entity], Entity]):
    """
    Service for file submission and submission management.

    Handles file upload, storage, and submission record creation for
    user-owned submission types (EXERCISE_SUBMISSION, JE_INPUT, ACTIVITY_REPORT).
    """

    # =========================================================================
    # DomainConfig
    # =========================================================================
    _config = DomainConfig(
        dto_class=SubmissionDTO,
        model_class=Entity,
        entity_label="Entity",
        search_fields=("title", "original_filename", "file_type"),
        search_order_by="created_at",
        category_field="entity_type",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self,
        backend: BackendOperations[SubmissionEntity],
        storage_path: str = "/tmp/skuel_reports",
        event_bus=None,
        interaction_service: "InteractionService | None" = None,
    ) -> None:
        """
        Initialize submission service.

        Args:
            backend: Backend for submission storage
            storage_path: Base path for file storage (default: /tmp/skuel_submissions)
            event_bus: Event bus for domain events (optional)
            interaction_service: InteractionService for creating Interaction audit records
                                 (optional — records not created when None, e.g. in tests)
        """
        super().__init__(backend, "SubmissionsService")
        self.storage_path = Path(storage_path)
        self.event_bus = event_bus
        self.interaction_service = interaction_service
        self.logger = get_logger("skuel.services.ku_submission")  # type: ignore[assignment]  # structlog BoundLogger

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Submission storage path: {self.storage_path}")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for submission entities."""
        return "Entity"

    # ========================================================================
    # FILE SUBMISSION
    # ========================================================================

    @with_error_handling("submit_file")
    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: UserUID,
        entity_type: EntityType = EntityType.EXERCISE_SUBMISSION,
        processor_type: ProcessorType = ProcessorType.AUTOMATIC,
        file_type: str | None = None,
        title: str | None = None,
        parent_entity_uid: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
        fulfills_exercise_uid: str | None = None,
        context_path_step_uid: str | None = None,
        context_learning_path_uid: str | None = None,
    ) -> Result[Entity]:
        """
        Submit a file for processing.

        Steps:
        1. Store file to disk/cloud
        2. Create submission record in Neo4j
        3. Auto-create Interaction audit record (if interaction_service is wired)
        4. Return submission with SUBMITTED status

        Args:
            file_content: Raw file bytes
            original_filename: Original filename from upload
            user_uid: User submitting the file
            entity_type: Type of submission (default: SUBMISSION)
            processor_type: Processor to use (default: AUTOMATIC)
            file_type: MIME type (optional, will detect from filename)
            title: Optional title (defaults to filename)
            parent_entity_uid: Optional parent submission UID for derivation chain
            metadata: Additional metadata (optional)
            applies_knowledge_uids: Knowledge Units being applied
            fulfills_exercise_uid: Exercise UID if this submission responds to an
                assigned exercise. Triggers FULFILLS_EXERCISE relationship and
                auto-sharing with the teacher.
            context_path_step_uid: PathStep the user was studying when submitting.
                Captured from UserContext.current_ps_uids by the route handler.
            context_learning_path_uid: LearningPath the user was enrolled in.
                Captured from UserContext.current_learning_path_uid by the route handler.

        Returns:
            Result containing created submission entity
        """
        uid = UIDGenerator.generate_random_uid("es")

        if not file_type:
            file_type = self._detect_mime_type(original_filename)

        # Store file
        file_path_result = await self._store_file(
            file_content=file_content, filename=original_filename, ku_uid=uid
        )

        if file_path_result.is_error:
            return Result.fail(file_path_result)

        file_path = file_path_result.value

        # Create submission record — Submission accepts all 4 content-processing types
        submission = Submission(
            uid=uid,
            title=title or original_filename,
            entity_type=entity_type,
            user_uid=user_uid,
            parent_entity_uid=parent_entity_uid or fulfills_exercise_uid,
            status=EntityStatus.SUBMITTED,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            processor_type=processor_type,
            modality=SubmissionModality.FILE_UPLOAD,
            metadata=metadata or {},
        )

        # Store in Neo4j
        create_result = await self.backend.create(submission)

        if create_result.is_error:
            # Clean up file if Neo4j storage fails
            try:
                Path(file_path).unlink()
            except OSError as cleanup_error:
                self.logger.warning(f"Failed to clean up file after Neo4j error: {cleanup_error}")

            return create_result

        # Create APPLIES_KNOWLEDGE relationships
        if applies_knowledge_uids:
            from core.models.relationship_names import RelationshipName

            relationships = [
                (uid, ku_uid, RelationshipName.APPLIES_KNOWLEDGE.value, None)
                for ku_uid in applies_knowledge_uids
            ]
            rel_result = await self.backend.create_relationships_batch(relationships)
            if rel_result.is_error:
                self.logger.warning(
                    f"Failed to create APPLIES_KNOWLEDGE relationships for {uid}: {rel_result.error}"
                )

        self.logger.info(
            f"Submission submitted: {uid} "
            f"(type={entity_type.value}, size={len(file_content)} bytes, "
            f"applies_knowledge={len(applies_knowledge_uids or [])} KUs)"
        )

        # Publish event
        event = SubmissionCreated(
            submission_uid=uid,
            user_uid=user_uid,
            entity_type=entity_type.value,
            processor_type=processor_type.value,
            file_size=len(file_content),
            file_type=file_type,
            original_filename=original_filename,
            fulfills_exercise_uid=fulfills_exercise_uid,
            metadata=metadata,
        )
        await publish_event(self.event_bus, event, self.logger)

        # Auto-create Interaction audit record for the User Interaction Contract.
        # Fire-and-forget: a failure here does not fail the submission itself.
        if entity_type == EntityType.EXERCISE_SUBMISSION and self.interaction_service:
            await self._create_interaction_record(
                submission_uid=uid,
                user_uid=user_uid,
                target_uid=fulfills_exercise_uid or "",
                context_path_step_uid=context_path_step_uid,
                context_learning_path_uid=context_learning_path_uid,
            )

        return create_result

    @with_error_handling("submit_form")
    async def submit_form(
        self,
        user_uid: UserUID,
        exercise_uid: str,
        form_data: dict[str, Any],
        title: str | None = None,
        context_path_step_uid: str | None = None,
        context_learning_path_uid: str | None = None,
    ) -> Result[Entity]:
        """
        Submit structured form responses (no file storage).

        Creates an ExerciseSubmission from inline form data, stores responses
        in metadata + processed_content, and triggers the same event pipeline
        as file submissions (FULFILLS_EXERCISE, auto-share with teacher).

        Args:
            user_uid: Student submitting the form
            exercise_uid: Exercise UID this submission responds to
            form_data: Form field values keyed by field name
            title: Optional title (defaults to "Form response — {date}")

        Returns:
            Result containing created submission entity
        """
        uid = UIDGenerator.generate_random_uid("es")

        submission = Submission(
            uid=uid,
            title=title or f"Form response — {datetime.now():%Y-%m-%d}",
            entity_type=EntityType.EXERCISE_SUBMISSION,
            user_uid=user_uid,
            parent_entity_uid=exercise_uid,
            status=EntityStatus.SUBMITTED,
            processed_content=json.dumps(form_data),
            metadata={"submission_mode": "form", "form_data": form_data},
            processor_type=ProcessorType.AUTOMATIC,
            modality=SubmissionModality.STRUCTURED_FORM,
        )

        create_result = await self.backend.create(submission)
        if create_result.is_error:
            return create_result

        self.logger.info(
            f"Form submission created: {uid} (exercise={exercise_uid}, fields={len(form_data)})"
        )

        # Publish event — same pipeline as file submissions
        event = SubmissionCreated(
            submission_uid=uid,
            user_uid=user_uid,
            entity_type=EntityType.EXERCISE_SUBMISSION.value,
            processor_type=ProcessorType.AUTOMATIC.value,
            fulfills_exercise_uid=exercise_uid,
            metadata={"submission_mode": "form"},
        )
        await publish_event(self.event_bus, event, self.logger)

        # Auto-create Interaction audit record for the User Interaction Contract.
        if self.interaction_service:
            await self._create_interaction_record(
                submission_uid=uid,
                user_uid=user_uid,
                target_uid=exercise_uid,
                context_path_step_uid=context_path_step_uid,
                context_learning_path_uid=context_learning_path_uid,
            )

        return create_result

    async def _create_interaction_record(
        self,
        submission_uid: str,
        user_uid: UserUID,
        target_uid: str,
        context_path_step_uid: str | None,
        context_learning_path_uid: str | None,
    ) -> None:
        """
        Auto-create an Interaction node after a successful ExerciseSubmission.

        Fire-and-forget: logs warnings on failure but never raises. The submission
        itself is already persisted; this is supplementary audit data.

        Args:
            submission_uid:            UID of the just-created ExerciseSubmission.
            user_uid:                  Submitting user.
            target_uid:                Exercise UID (the target of the interaction).
            context_path_step_uid:     PathStep the user was studying (may be None).
            context_learning_path_uid: LearningPath the user was enrolled in (may be None).
        """
        if self.interaction_service is None:
            return

        try:
            ia_uid = UIDGenerator.generate_random_uid("ia")
            interaction = Interaction(
                uid=ia_uid,
                title=f"exercise_submission — {target_uid or 'unknown'}",
                entity_type=EntityType.INTERACTION,
                user_uid=user_uid,
                interaction_type=InteractionType.EXERCISE_SUBMISSION,
                target_uid=target_uid,
                context_path_step_uid=context_path_step_uid,
                context_learning_path_uid=context_learning_path_uid,
                source_entity_uid=submission_uid,
            )
            result = await self.interaction_service.create_interaction(interaction)
            if result.is_error:
                self.logger.warning(
                    f"Failed to create Interaction record for submission {submission_uid}: "
                    f"{result.error}"
                )
        except Exception as e:  # safety-net: interaction creation must not fail the submission
            self.logger.warning(
                f"Unexpected error creating Interaction for submission {submission_uid}: {e}"
            )

    async def _store_file(self, file_content: bytes, filename: str, ku_uid: str) -> Result[Path]:
        """
        Store file to disk.

        File organization:
        /storage_path/
            YYYY-MM/
                ku_uid/
                    original_filename
        """
        try:
            month_dir = self.storage_path / datetime.now().strftime("%Y-%m")
            ku_dir = month_dir / ku_uid
            ku_dir.mkdir(parents=True, exist_ok=True)

            file_path = ku_dir / filename
            file_path.write_bytes(file_content)

            self.logger.info(f"File stored: {file_path}")
            return Result.ok(file_path)

        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to store file: {e!s}", operation="store_file", exception=e
                )
            )

    def _detect_mime_type(self, filename: str) -> str:
        """Detect MIME type from filename extension."""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    # ========================================================================
    # KU QUERIES
    # ========================================================================

    @with_error_handling("list_submissions")
    async def list_submissions(
        self,
        user_uid: UserUID,
        entity_type: EntityType | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Entity]]:
        """
        List submissions for a user with optional filters.

        Args:
            user_uid: User UID
            entity_type: Filter by type (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)
            offset: Pagination offset (default 0)

        Returns:
            Result containing list of Ku
        """
        filters: dict[str, Any] = {"user_uid": user_uid}

        if entity_type:
            filters["entity_type"] = entity_type.value

        if status:
            filters["status"] = status.value

        result = await self.backend.find_by(
            **filters, limit=limit, offset=offset, sort_by="created_at", sort_order="desc"
        )

        if result.is_error:
            return result

        return Result.ok(result.value)

    @with_error_handling("get_submission")
    async def get_submission(self, uid: str) -> Result[Entity | None]:
        """Get submission by UID."""
        return await self.backend.get(uid)

    @with_error_handling("count_submissions")
    async def count_submissions(
        self,
        user_uid: UserUID,
        entity_type: EntityType | None = None,
        status: EntityStatus | None = None,
    ) -> Result[int]:
        """Count submissions for a user with optional filters."""
        filters: dict[str, Any] = {"user_uid": user_uid}

        if entity_type:
            filters["entity_type"] = entity_type.value

        if status:
            filters["status"] = status.value

        return await self.backend.count(**filters)

    # ========================================================================
    # KU UPDATES
    # ========================================================================

    @with_error_handling("update_submission_status")
    async def update_submission_status(
        self, uid: str, new_status: EntityStatus, error_message: str | None = None
    ) -> Result[Entity]:
        """
        Update submission status with transition validation.

        Validates that the transition is allowed by the general transition map
        and that the target status is valid for the entity's type before persisting.

        Args:
            uid: Submission UID
            new_status: New status
            error_message: Error message if status is FAILED

        Returns:
            Result containing updated submission, or validation error if transition is invalid
        """
        # Fetch current entity to validate the transition
        current_result = await self.backend.get(uid)
        if current_result.is_error:
            return Result.fail(current_result)
        if not current_result.value:
            return Result.fail(Errors.not_found("Submission", uid))

        current = current_result.value
        if not current.status.can_transition_to(new_status, current.entity_type):
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Invalid status transition: {current.status.value} → {new_status.value} "
                        f"for {current.entity_type.value}"
                    ),
                    field="status",
                )
            )

        updates: dict[str, Any] = {"status": new_status.value}

        if new_status == EntityStatus.PROCESSING:
            updates["processing_started_at"] = datetime.now()
        elif new_status in {EntityStatus.COMPLETED, EntityStatus.FAILED}:
            updates["processing_completed_at"] = datetime.now()

        if new_status == EntityStatus.FAILED and error_message:
            updates["processing_error"] = error_message

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Submission {uid} status updated: {new_status.value}")

        return result

    async def update_submission(self, uid: str, updates: dict[str, Any]) -> Result[Entity]:
        """
        Update submission with arbitrary fields.

        Args:
            uid: Submission UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Ku
        """
        result = await self.backend.update(uid, updates)

        if result.is_ok:
            field_names = ", ".join(updates.keys())
            self.logger.info(f"Submission {uid} updated: {field_names}")

        return result

    @with_error_handling("update_processed_content")
    async def update_processed_content(
        self, uid: str, processed_content: str, processed_file_path: str | None = None
    ) -> Result[Entity]:
        """
        Update submission with processed content.

        Args:
            uid: Submission UID
            processed_content: Processed text content
            processed_file_path: Path to processed file (optional)

        Returns:
            Result containing updated Ku
        """
        updates: dict[str, Any] = {"processed_content": processed_content}

        if processed_file_path:
            updates["processed_file_path"] = processed_file_path

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Submission {uid} processed content updated")

        return result

    # ========================================================================
    # DELETION AND CLEANUP
    # ========================================================================

    @with_error_handling("delete_submission_with_file")
    async def delete_submission_with_file(self, uid: str) -> Result[bool]:
        """
        Delete submission record AND its associated file from disk.

        This is a hard delete - both the Neo4j record and the file are permanently removed.

        Args:
            uid: Submission UID to delete

        Returns:
            Result containing True if deleted successfully
        """
        submission_result = await self.get_submission(uid)
        if submission_result.is_error:
            return Result.fail(submission_result)

        submission = submission_result.value
        if not submission:
            return Result.fail(Errors.not_found("Submission", uid))

        submission_file_path = getattr(submission, "file_path", None)
        file_path = Path(submission_file_path) if submission_file_path else None
        ku_dir = file_path.parent if file_path else None

        # Delete Neo4j record first
        delete_result = await self.backend.delete(uid)
        if delete_result.is_error:
            return delete_result

        # Delete file from disk
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info(f"Deleted file: {file_path}")

                if ku_dir and ku_dir.exists() and not any(ku_dir.iterdir()):
                    ku_dir.rmdir()
                    self.logger.debug(f"Removed empty directory: {ku_dir}")

            except OSError as e:
                self.logger.warning(f"Failed to delete file {file_path}: {e}")

        self.logger.info(f"Submission deleted with file: {uid}")
        return Result.ok(True)

    # ========================================================================
    # FILE RETRIEVAL
    # ========================================================================

    @with_error_handling("get_file_content")
    async def get_file_content(self, ku_uid: str) -> Result[bytes]:
        """
        Retrieve original file content.

        Args:
            ku_uid: Submission UID

        Returns:
            Result containing file bytes
        """
        submission_result = await self.get_submission(ku_uid)

        if submission_result.is_error:
            return Result.fail(submission_result)

        submission = submission_result.value
        if not submission:
            return Result.fail(Errors.not_found("Submission", ku_uid))

        try:
            submission_file_path = getattr(submission, "file_path", None)
            if not submission_file_path:
                return Result.fail(Errors.not_found(resource="File", identifier="no file_path"))
            file_path = Path(submission_file_path)
            if not file_path.exists():
                return Result.fail(Errors.not_found(resource="File", identifier=str(file_path)))

            content = file_path.read_bytes()
            return Result.ok(content)

        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to read file: {e!s}", operation="get_file_content", exception=e
                )
            )

    @with_error_handling("get_processed_file_content")
    async def get_processed_file_content(self, ku_uid: str) -> Result[bytes]:
        """
        Retrieve processed file content.

        Args:
            ku_uid: Submission UID

        Returns:
            Result containing processed file bytes
        """
        submission_result = await self.get_submission(ku_uid)

        if submission_result.is_error:
            return Result.fail(submission_result)

        submission = submission_result.value
        if not submission:
            return Result.fail(Errors.not_found("Submission", ku_uid))

        processed_path = getattr(submission, "processed_file_path", None)
        if not processed_path:
            return Result.fail(
                Errors.validation(
                    message="No processed file available for this Ku",
                    field="processed_file_path",
                )
            )

        try:
            file_path = Path(processed_path)
            if not file_path.exists():
                return Result.fail(
                    Errors.not_found(resource="ProcessedFile", identifier=str(file_path))
                )

            content = file_path.read_bytes()
            return Result.ok(content)

        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message=f"Failed to read processed file: {e!s}",
                    operation="get_processed_file_content",
                    exception=e,
                )
            )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @with_error_handling("get_submission_statistics")
    async def get_submission_statistics(self, user_uid: UserUID) -> Result[SubmissionStatistics]:
        """
        Get submission statistics for a user.

        Returns counts by type and status.
        """
        total_result = await self.count_submissions(user_uid)
        if total_result.is_error:
            return Result.fail(total_result)

        statistics: dict[str, Any] = {"total": total_result.value, "by_type": {}, "by_status": {}}

        for entity_type in EntityType:
            count_result = await self.count_submissions(user_uid, entity_type=entity_type)
            if count_result.is_ok:
                statistics["by_type"][entity_type.value] = count_result.value

        for status in EntityStatus:
            count_result = await self.count_submissions(user_uid, status=status)
            if count_result.is_ok:
                statistics["by_status"][status.value] = count_result.value

        return Result.ok(statistics)
