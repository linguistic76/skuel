"""
Report Submission Service
==============================

Handles file uploads and report record creation.

Responsibilities:
- Store uploaded files (local or cloud)
- Create Report records in Neo4j
- Basic CRUD for reports
- Query by type, status, user

Does NOT handle:
- Processing logic (ReportsProcessingService)
- AI transcript formatting (TranscriptProcessorService)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.report_events import ReportSubmitted
from core.models.report.report import (
    Report,
    ReportDTO,
    ReportStatus,
    ReportType,
    ProcessorType,
)
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.services.protocols.query_types import ReportUpdatePayload
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class ReportSubmissionService(BaseService[BackendOperations[Report], Report]):
    """
    Service for file submission and report management.

    Phase 1 Implementation:
    - File upload and storage
    - Report record creation
    - Basic CRUD operations
    - Query by type, status, user

    Future Enhancements:
    - Cloud storage integration (S3, GCS)
    - File validation and scanning
    - Automatic processor selection
    - Webhook notifications


    Source Tag: "report_submission_explicit"
    - Format: "report_submission_explicit" for user-created relationships
    - Format: "report_submission_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    # =========================================================================
    # DomainConfig (January 2026 Phase 3)
    # =========================================================================
    _config = DomainConfig(
        dto_class=ReportDTO,
        model_class=Report,
        entity_label="Report",
        search_fields=("original_filename", "file_type", "processed_title"),
        search_order_by="submitted_at",
        category_field="report_type",
        user_ownership_relationship="OWNS",  # User-owned content
    )

    def __init__(
        self,
        backend: UniversalNeo4jBackend[Report],
        storage_path: str = "/tmp/skuel_reports",
        event_bus=None,
    ) -> None:
        """
        Initialize report submission service.

        Args:
            backend: UniversalNeo4jBackend for Report storage
            storage_path: Base path for file storage (default: /tmp/skuel_reports)
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(backend, "ReportSubmissionService")
        self.storage_path = Path(storage_path)
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.report_submission")

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Report storage path: {self.storage_path}")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Report entities."""
        return "Report"

    # ========================================================================
    # FILE SUBMISSION
    # ========================================================================

    @with_error_handling("submit_file")
    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        report_type: ReportType,
        processor_type: ProcessorType = ProcessorType.AUTOMATIC,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
    ) -> Result[Report]:
        """
        Submit a file for processing.

        Steps:
        1. Store file to disk/cloud
        2. Create Report record in Neo4j
        3. Return Report with SUBMITTED status

        Args:
            file_content: Raw file bytes
            original_filename: Original filename from upload
            user_uid: User submitting the file
            report_type: Type of report (journal, transcript, etc.)
            processor_type: Processor to use (default: AUTOMATIC)
            file_type: MIME type (optional, will detect from filename)
            metadata: Additional metadata (optional)
            applies_knowledge_uids: Knowledge Units being applied (MVP - Phase C)

        Returns:
            Result containing created Report
        """
        # Generate unique UID
        uid = UIDGenerator.generate_random_uid("report")

        # Determine file type if not provided
        if not file_type:
            file_type = self._detect_mime_type(original_filename)

        # Store file
        file_path_result = await self._store_file(
            file_content=file_content, filename=original_filename, report_uid=uid
        )

        if file_path_result.is_error:
            return Result.fail(file_path_result)

        file_path = file_path_result.value

        # Create report record
        report = Report(
            uid=uid,
            user_uid=user_uid,
            report_type=report_type,
            status=ReportStatus.SUBMITTED,
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

        # Create APPLIES_KNOWLEDGE relationships (MVP - Phase C)
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
                # Don't fail the whole submission, just log the warning

        self.logger.info(
            f"Report submitted: {uid} "
            f"(type={report_type.value}, size={len(file_content)} bytes, "
            f"applies_knowledge={len(applies_knowledge_uids or [])} KUs)"
        )

        # Publish ReportSubmitted event
        event = ReportSubmitted(
            report_uid=uid,
            user_uid=user_uid,
            report_type=report_type.value,
            processor_type=processor_type.value,
            file_size=len(file_content),
            file_type=file_type,
            original_filename=original_filename,
            occurred_at=datetime.now(),
            metadata=metadata,
        )
        await publish_event(self.event_bus, event, self.logger)

        return create_result

    async def _store_file(
        self, file_content: bytes, filename: str, report_uid: str
    ) -> Result[Path]:
        """
        Store file to disk.

        File organization:
        /storage_path/
            YYYY-MM/
                report_uid/
                    original_filename

        Args:
            file_content: Raw file bytes
            filename: Original filename
            report_uid: Report UID (for directory organization)

        Returns:
            Result containing full file path
        """
        try:
            # Organize by month: /storage/2025-11/report.abc123/file.mp3
            month_dir = self.storage_path / datetime.now().strftime("%Y-%m")
            report_dir = month_dir / report_uid
            report_dir.mkdir(parents=True, exist_ok=True)

            # Store with original filename
            file_path = report_dir / filename

            # Write file
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
        """
        Detect MIME type from filename extension.

        Returns generic type if unknown.
        """
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    # ========================================================================
    # REPORT QUERIES
    # ========================================================================

    @with_error_handling("list_reports")
    async def list_reports(
        self,
        user_uid: str,
        report_type: ReportType | None = None,
        status: ReportStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Report]]:
        """
        List reports for a user with optional filters.

        Args:
            user_uid: User UID
            report_type: Filter by type (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)
            offset: Pagination offset (default 0)

        Returns:
            Result containing list of reports
        """
        filters = {"user_uid": user_uid}

        if report_type:
            filters["report_type"] = report_type.value

        if status:
            filters["status"] = status.value

        result = await self.backend.find_by(
            **filters, limit=limit, offset=offset, sort_by="created_at", sort_order="desc"
        )

        if result.is_error:
            return result

        return Result.ok(result.value)

    @with_error_handling("get_report")
    async def get_report(self, uid: str) -> Result[Report | None]:
        """Get report by UID."""
        return await self.backend.get(uid)

    @with_error_handling("count_reports")
    async def count_reports(
        self,
        user_uid: str,
        report_type: ReportType | None = None,
        status: ReportStatus | None = None,
    ) -> Result[int]:
        """
        Count reports for a user with optional filters.

        Args:
            user_uid: User UID
            report_type: Filter by type (optional)
            status: Filter by status (optional)

        Returns:
            Result containing count
        """
        filters = {"user_uid": user_uid}

        if report_type:
            filters["report_type"] = report_type.value

        if status:
            filters["status"] = status.value

        return await self.backend.count(**filters)

    # ========================================================================
    # REPORT UPDATES
    # ========================================================================

    @with_error_handling("update_report_status")
    async def update_report_status(
        self, uid: str, new_status: ReportStatus, error_message: str | None = None
    ) -> Result[Report]:
        """
        Update report status.

        Args:
            uid: Report UID
            new_status: New status
            error_message: Error message if status is FAILED

        Returns:
            Result containing updated report
        """
        updates: ReportUpdatePayload = {"status": new_status.value}

        # Set timestamps based on status transitions
        if new_status == ReportStatus.PROCESSING:
            updates["processing_started_at"] = datetime.now()
        elif new_status in {ReportStatus.COMPLETED, ReportStatus.FAILED}:
            updates["processing_completed_at"] = datetime.now()

        if new_status == ReportStatus.FAILED and error_message:
            updates["processing_error"] = error_message

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Report {uid} status updated: {new_status.value}")

        return result

    async def update_report(self, uid: str, updates: dict[str, Any]) -> Result[Report]:
        """
        Update report with arbitrary fields.

        Args:
            uid: Report UID
            updates: Dictionary of field updates (e.g., {"processed_content": ..., "metadata": ...})

        Returns:
            Result containing updated report
        """
        # Serialize metadata to JSON string for Neo4j storage
        # Neo4j cannot store nested dicts/maps as property values
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates = dict(updates)  # Don't mutate the original
            updates["metadata"] = json.dumps(updates["metadata"])

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            field_names = ", ".join(updates.keys())
            self.logger.info(f"Report {uid} updated: {field_names}")

        return result

    @with_error_handling("update_processed_content")
    async def update_processed_content(
        self, uid: str, processed_content: str, processed_file_path: str | None = None
    ) -> Result[Report]:
        """
        Update report with processed content.

        Args:
            uid: Report UID
            processed_content: Processed text content
            processed_file_path: Path to processed file (optional)

        Returns:
            Result containing updated report
        """
        updates = {"processed_content": processed_content}

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
        Used for FIFO cleanup of ephemeral journal types.

        Args:
            uid: Report UID to delete

        Returns:
            Result containing True if deleted successfully
        """
        # Get report to retrieve file_path
        report_result = await self.get_report(uid)
        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", uid))

        file_path = Path(report.file_path) if report.file_path else None
        report_dir = file_path.parent if file_path else None

        # Delete Neo4j record first
        delete_result = await self.backend.delete(uid)
        if delete_result.is_error:
            return delete_result

        # Delete file from disk
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info(f"Deleted file: {file_path}")

                # Also delete the report directory if empty
                if report_dir and report_dir.exists() and not any(report_dir.iterdir()):
                    report_dir.rmdir()
                    self.logger.debug(f"Removed empty directory: {report_dir}")

            except Exception as e:
                # Log but don't fail - Neo4j record is already deleted
                self.logger.warning(f"Failed to delete file {file_path}: {e}")

        self.logger.info(f"Report deleted with file: {uid}")
        return Result.ok(True)

    # ========================================================================
    # FILE RETRIEVAL
    # ========================================================================

    @with_error_handling("get_file_content")
    async def get_file_content(self, report_uid: str) -> Result[bytes]:
        """
        Retrieve original file content.

        Args:
            report_uid: Report UID

        Returns:
            Result containing file bytes
        """
        # Get report to find file path
        report_result = await self.get_report(report_uid)

        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", report_uid))

        # Read file
        try:
            file_path = Path(report.file_path)
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
    async def get_processed_file_content(self, report_uid: str) -> Result[bytes]:
        """
        Retrieve processed file content.

        Args:
            report_uid: Report UID

        Returns:
            Result containing processed file bytes
        """
        # Get report to find processed file path
        report_result = await self.get_report(report_uid)

        if report_result.is_error:
            return Result.fail(report_result.expect_error())

        report = report_result.value
        if not report:
            return Result.fail(Errors.not_found("Report", report_uid))

        if not report.processed_file_path:
            return Result.fail(
                Errors.validation(
                    message="No processed file available for this report",
                    field="processed_file_path",
                )
            )

        # Read processed file
        try:
            file_path = Path(report.processed_file_path)
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
        Get report statistics for a user.

        Returns counts by type and status.

        Args:
            user_uid: User UID

        Returns:
            Result containing statistics dictionary
        """
        # Count total reports
        total_result = await self.count_reports(user_uid)
        if total_result.is_error:
            return Result.fail(total_result.expect_error())

        statistics: dict[str, Any] = {"total": total_result.value, "by_type": {}, "by_status": {}}

        # Count by type
        for report_type in ReportType:
            count_result = await self.count_reports(user_uid, report_type=report_type)
            if count_result.is_ok:
                statistics["by_type"][report_type.value] = count_result.value

        # Count by status
        for status in ReportStatus:
            count_result = await self.count_reports(user_uid, status=status)
            if count_result.is_ok:
                statistics["by_status"][status.value] = count_result.value

        return Result.ok(statistics)
