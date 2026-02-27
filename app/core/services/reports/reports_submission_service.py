"""
Report Submission Service
==============================

Handles file uploads and report record creation.

Responsibilities:
- Store uploaded files (local or cloud)
- Create report records in Neo4j
- Basic CRUD for user-owned reports (SUBMISSION, AI_REPORT, FEEDBACK_REPORT)
- Query by type, status, user

Does NOT handle:
- Processing logic (ReportsProcessingService)
- AI content enrichment (ContentEnrichmentService)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.events import publish_event
from core.events.submission_events import SubmissionCreated
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.relationship_names import RelationshipName
from core.models.reports.submission import Submission
from core.models.reports.submission_dto import SubmissionDTO
from core.ports import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class ReportsSubmissionService(BaseService[BackendOperations[Entity], Entity]):
    """
    Service for file submission and report management.

    Handles file upload, storage, and report record creation for
    user-owned report types (SUBMISSION, AI_REPORT, FEEDBACK_REPORT).
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
        category_field="ku_type",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self,
        backend: BackendOperations[SubmissionEntity],
        storage_path: str = "/tmp/skuel_reports",
        event_bus=None,
    ) -> None:
        """
        Initialize report submission service.

        Args:
            backend: Backend for report storage
            storage_path: Base path for file storage (default: /tmp/skuel_reports)
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(backend, "ReportsSubmissionService")
        self.storage_path = Path(storage_path)
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.ku_submission")

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Report storage path: {self.storage_path}")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for report entities."""
        return "Entity"

    # ========================================================================
    # FILE SUBMISSION
    # ========================================================================

    @with_error_handling("submit_file")
    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        ku_type: EntityType = EntityType.SUBMISSION,
        processor_type: ProcessorType = ProcessorType.AUTOMATIC,
        file_type: str | None = None,
        title: str | None = None,
        parent_ku_uid: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
        fulfills_project_uid: str | None = None,
    ) -> Result[Entity]:
        """
        Submit a file for processing.

        Steps:
        1. Store file to disk/cloud
        2. Create report record in Neo4j
        3. Return report with SUBMITTED status

        Args:
            file_content: Raw file bytes
            original_filename: Original filename from upload
            user_uid: User submitting the file
            ku_type: Type of report (default: SUBMISSION)
            processor_type: Processor to use (default: AUTOMATIC)
            file_type: MIME type (optional, will detect from filename)
            title: Optional title (defaults to filename)
            parent_ku_uid: Optional parent report UID for derivation chain
            metadata: Additional metadata (optional)
            applies_knowledge_uids: Knowledge Units being applied

        Returns:
            Result containing created Ku
        """
        uid = UIDGenerator.generate_random_uid("ku")

        if not file_type:
            file_type = self._detect_mime_type(original_filename)

        # Store file
        file_path_result = await self._store_file(
            file_content=file_content, filename=original_filename, ku_uid=uid
        )

        if file_path_result.is_error:
            return Result.fail(file_path_result)

        file_path = file_path_result.value

        # Create report record — Submission accepts all 4 content-processing types
        report = Submission(
            uid=uid,
            title=title or original_filename,
            ku_type=ku_type,
            user_uid=user_uid,
            parent_ku_uid=parent_ku_uid,
            status=EntityStatus.SUBMITTED,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            processor_type=processor_type,
            metadata=metadata or {},
        )

        # Store in Neo4j
        create_result = await self.backend.create(report)

        if create_result.is_error:
            # Clean up file if Neo4j storage fails
            try:
                Path(file_path).unlink()
            except Exception as cleanup_error:
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
            f"Report submitted: {uid} "
            f"(type={ku_type.value}, size={len(file_content)} bytes, "
            f"applies_knowledge={len(applies_knowledge_uids or [])} KUs)"
        )

        # Publish event
        event = SubmissionCreated(
            submission_uid=uid,
            user_uid=user_uid,
            ku_type=ku_type.value,
            processor_type=processor_type.value,
            file_size=len(file_content),
            file_type=file_type,
            original_filename=original_filename,
            fulfills_project_uid=fulfills_project_uid,
            occurred_at=datetime.now(),
            metadata=metadata,
        )
        await publish_event(self.event_bus, event, self.logger)

        return create_result

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

        except Exception as e:
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

    @with_error_handling("list_reports")
    async def list_reports(
        self,
        user_uid: str,
        ku_type: EntityType | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Entity]]:
        """
        List reports for a user with optional filters.

        Args:
            user_uid: User UID
            ku_type: Filter by type (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)
            offset: Pagination offset (default 0)

        Returns:
            Result containing list of Ku
        """
        filters: dict[str, Any] = {"user_uid": user_uid}

        if ku_type:
            filters["ku_type"] = ku_type.value

        if status:
            filters["status"] = status.value

        result = await self.backend.find_by(
            **filters, limit=limit, offset=offset, sort_by="created_at", sort_order="desc"
        )

        if result.is_error:
            return result

        return Result.ok(result.value)

    @with_error_handling("get_report")
    async def get_report(self, uid: str) -> Result[Entity | None]:
        """Get report by UID."""
        return await self.backend.get(uid)

    @with_error_handling("count_reports")
    async def count_reports(
        self,
        user_uid: str,
        ku_type: EntityType | None = None,
        status: EntityStatus | None = None,
    ) -> Result[int]:
        """Count reports for a user with optional filters."""
        filters: dict[str, Any] = {"user_uid": user_uid}

        if ku_type:
            filters["ku_type"] = ku_type.value

        if status:
            filters["status"] = status.value

        return await self.backend.count(**filters)

    # ========================================================================
    # KU UPDATES
    # ========================================================================

    @with_error_handling("update_report_status")
    async def update_report_status(
        self, uid: str, new_status: EntityStatus, error_message: str | None = None
    ) -> Result[Entity]:
        """
        Update report status.

        Args:
            uid: Report UID
            new_status: New status
            error_message: Error message if status is FAILED

        Returns:
            Result containing updated Ku
        """
        updates: dict[str, Any] = {"status": new_status.value}

        if new_status == EntityStatus.PROCESSING:
            updates["processing_started_at"] = datetime.now()
        elif new_status in {EntityStatus.COMPLETED, EntityStatus.FAILED}:
            updates["processing_completed_at"] = datetime.now()

        if new_status == EntityStatus.FAILED and error_message:
            updates["processing_error"] = error_message

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Report {uid} status updated: {new_status.value}")

        return result

    async def update_report(self, uid: str, updates: dict[str, Any]) -> Result[Entity]:
        """
        Update report with arbitrary fields.

        Args:
            uid: Report UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Ku
        """
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates = dict(updates)
            updates["metadata"] = json.dumps(updates["metadata"])

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            field_names = ", ".join(updates.keys())
            self.logger.info(f"Report {uid} updated: {field_names}")

        return result

    @with_error_handling("update_processed_content")
    async def update_processed_content(
        self, uid: str, processed_content: str, processed_file_path: str | None = None
    ) -> Result[Entity]:
        """
        Update report with processed content.

        Args:
            uid: Report UID
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
            self.logger.info(f"Report {uid} processed content updated")

        return result

    # ========================================================================
    # DELETION AND CLEANUP
    # ========================================================================

    @with_error_handling("delete_report_with_file")
    async def delete_report_with_file(self, uid: str) -> Result[bool]:
        """
        Delete report record AND its associated file from disk.

        This is a hard delete - both the Neo4j record and the file are permanently removed.

        Args:
            uid: Report UID to delete

        Returns:
            Result containing True if deleted successfully
        """
        report_result = await self.get_report(uid)
        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", uid))

        report_file_path = getattr(report, "file_path", None)
        file_path = Path(report_file_path) if report_file_path else None
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

            except Exception as e:
                self.logger.warning(f"Failed to delete file {file_path}: {e}")

        self.logger.info(f"Ku deleted with file: {uid}")
        return Result.ok(True)

    # ========================================================================
    # FILE RETRIEVAL
    # ========================================================================

    @with_error_handling("get_file_content")
    async def get_file_content(self, ku_uid: str) -> Result[bytes]:
        """
        Retrieve original file content.

        Args:
            ku_uid: Report UID

        Returns:
            Result containing file bytes
        """
        report_result = await self.get_report(ku_uid)

        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", ku_uid))

        try:
            report_file_path = getattr(report, "file_path", None)
            if not report_file_path:
                return Result.fail(Errors.not_found(resource="File", identifier="no file_path"))
            file_path = Path(report_file_path)
            if not file_path.exists():
                return Result.fail(Errors.not_found(resource="File", identifier=str(file_path)))

            content = file_path.read_bytes()
            return Result.ok(content)

        except Exception as e:
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
            ku_uid: Report UID

        Returns:
            Result containing processed file bytes
        """
        report_result = await self.get_report(ku_uid)

        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", ku_uid))

        processed_path = getattr(report, "processed_file_path", None)
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

        except Exception as e:
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

    @with_error_handling("get_report_statistics")
    async def get_report_statistics(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get Ku statistics for a user.

        Returns counts by type and status.
        """
        total_result = await self.count_reports(user_uid)
        if total_result.is_error:
            return Result.fail(total_result.expect_error())

        statistics: dict[str, Any] = {"total": total_result.value, "by_type": {}, "by_status": {}}

        for ku_type in EntityType:
            count_result = await self.count_reports(user_uid, ku_type=ku_type)
            if count_result.is_ok:
                statistics["by_type"][ku_type.value] = count_result.value

        for status in EntityStatus:
            count_result = await self.count_reports(user_uid, status=status)
            if count_result.is_ok:
                statistics["by_status"][status.value] = count_result.value

        return Result.ok(statistics)
