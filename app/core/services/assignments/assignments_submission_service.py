"""
Assignment Submission Service
==============================

Handles file uploads and assignment record creation.

Responsibilities:
- Store uploaded files (local or cloud)
- Create Assignment records in Neo4j
- Basic CRUD for assignments
- Query by type, status, user

Does NOT handle:
- Processing logic (AssignmentProcessorService)
- AI transcript formatting (TranscriptProcessorService)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import publish_event
from core.events.assignment_events import AssignmentSubmitted
from core.models.assignment.assignment import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    ProcessorType,
)
from core.services.base_service import BaseService
from core.services.protocols.query_types import AssignmentUpdatePayload
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator


class AssignmentSubmissionService(BaseService[UniversalNeo4jBackend[Assignment], Assignment]):
    """
    Service for file submission and assignment management.

    Phase 1 Implementation:
    - File upload and storage
    - Assignment record creation
    - Basic CRUD operations
    - Query by type, status, user

    Future Enhancements:
    - Cloud storage integration (S3, GCS)
    - File validation and scanning
    - Automatic processor selection
    - Webhook notifications


    Source Tag: "assignment_submission_explicit"
    - Format: "assignment_submission_explicit" for user-created relationships
    - Format: "assignment_submission_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(
        self,
        backend: UniversalNeo4jBackend[Assignment],
        storage_path: str = "/tmp/skuel_assignments",
        event_bus=None,
    ) -> None:
        """
        Initialize assignment submission service.

        Args:
            backend: UniversalNeo4jBackend for Assignment storage
            storage_path: Base path for file storage (default: /tmp/skuel_assignments)
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(backend, "AssignmentSubmissionService")
        self.storage_path = Path(storage_path)
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.assignment_submission")

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Assignment storage path: {self.storage_path}")

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Assignment entities."""
        return "Assignment"

    # ========================================================================
    # FILE SUBMISSION
    # ========================================================================

    @with_error_handling("submit_file")
    async def submit_file(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        assignment_type: AssignmentType,
        processor_type: ProcessorType = ProcessorType.AUTOMATIC,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Assignment]:
        """
        Submit a file for processing.

        Steps:
        1. Store file to disk/cloud
        2. Create Assignment record in Neo4j
        3. Return Assignment with SUBMITTED status

        Args:
            file_content: Raw file bytes
            original_filename: Original filename from upload
            user_uid: User submitting the file
            assignment_type: Type of assignment (journal, transcript, etc.)
            processor_type: Processor to use (default: AUTOMATIC)
            file_type: MIME type (optional, will detect from filename)
            metadata: Additional metadata (optional)

        Returns:
            Result containing created Assignment
        """
        # Generate unique UID
        uid = UIDGenerator.generate_random_uid("assignment")

        # Determine file type if not provided
        if not file_type:
            file_type = self._detect_mime_type(original_filename)

        # Store file
        file_path_result = await self._store_file(
            file_content=file_content, filename=original_filename, assignment_uid=uid
        )

        if file_path_result.is_error:
            return Result.fail(file_path_result)

        file_path = file_path_result.value

        # Create assignment record
        assignment = Assignment(
            uid=uid,
            user_uid=user_uid,
            assignment_type=assignment_type,
            status=AssignmentStatus.SUBMITTED,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            file_type=file_type,
            processor_type=processor_type,
            metadata=metadata or {},
        )

        # Store in Neo4j
        create_result = await self.backend.create(assignment)

        if create_result.is_error:
            # Clean up file if Neo4j storage fails
            try:
                Path(file_path).unlink()
            except Exception as cleanup_error:
                self.logger.warning(f"Failed to clean up file after Neo4j error: {cleanup_error}")

            return create_result

        self.logger.info(
            f"Assignment submitted: {uid} "
            f"(type={assignment_type.value}, size={len(file_content)} bytes)"
        )

        # Publish AssignmentSubmitted event
        event = AssignmentSubmitted(
            assignment_uid=uid,
            user_uid=user_uid,
            assignment_type=assignment_type.value,
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
        self, file_content: bytes, filename: str, assignment_uid: str
    ) -> Result[Path]:
        """
        Store file to disk.

        File organization:
        /storage_path/
            YYYY-MM/
                assignment_uid/
                    original_filename

        Args:
            file_content: Raw file bytes
            filename: Original filename
            assignment_uid: Assignment UID (for directory organization)

        Returns:
            Result containing full file path
        """
        try:
            # Organize by month: /storage/2025-11/assignment.abc123/file.mp3
            month_dir = self.storage_path / datetime.now().strftime("%Y-%m")
            assignment_dir = month_dir / assignment_uid
            assignment_dir.mkdir(parents=True, exist_ok=True)

            # Store with original filename
            file_path = assignment_dir / filename

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
    # ASSIGNMENT QUERIES
    # ========================================================================

    @with_error_handling("list_assignments")
    async def list_assignments(
        self,
        user_uid: str,
        assignment_type: AssignmentType | None = None,
        status: AssignmentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Assignment]]:
        """
        List assignments for a user with optional filters.

        Args:
            user_uid: User UID
            assignment_type: Filter by type (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)
            offset: Pagination offset (default 0)

        Returns:
            Result containing list of assignments
        """
        filters = {"user_uid": user_uid}

        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        if status:
            filters["status"] = status.value

        result = await self.backend.find_by(
            **filters, limit=limit, offset=offset, sort_by="created_at", sort_order="desc"
        )

        if result.is_error:
            return result

        return Result.ok(result.value)

    @with_error_handling("get_assignment")
    async def get_assignment(self, uid: str) -> Result[Assignment | None]:
        """Get assignment by UID."""
        return await self.backend.get(uid)

    @with_error_handling("count_assignments")
    async def count_assignments(
        self,
        user_uid: str,
        assignment_type: AssignmentType | None = None,
        status: AssignmentStatus | None = None,
    ) -> Result[int]:
        """
        Count assignments for a user with optional filters.

        Args:
            user_uid: User UID
            assignment_type: Filter by type (optional)
            status: Filter by status (optional)

        Returns:
            Result containing count
        """
        filters = {"user_uid": user_uid}

        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        if status:
            filters["status"] = status.value

        return await self.backend.count(**filters)

    # ========================================================================
    # ASSIGNMENT UPDATES
    # ========================================================================

    @with_error_handling("update_assignment_status")
    async def update_assignment_status(
        self, uid: str, new_status: AssignmentStatus, error_message: str | None = None
    ) -> Result[Assignment]:
        """
        Update assignment status.

        Args:
            uid: Assignment UID
            new_status: New status
            error_message: Error message if status is FAILED

        Returns:
            Result containing updated assignment
        """
        updates: AssignmentUpdatePayload = {"status": new_status.value}

        # Set timestamps based on status transitions
        if new_status == AssignmentStatus.PROCESSING:
            updates["processing_started_at"] = datetime.now()
        elif new_status in {AssignmentStatus.COMPLETED, AssignmentStatus.FAILED}:
            updates["processing_completed_at"] = datetime.now()

        if new_status == AssignmentStatus.FAILED and error_message:
            updates["processing_error"] = error_message

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Assignment {uid} status updated: {new_status.value}")

        return result

    async def update_assignment(self, uid: str, updates: dict[str, Any]) -> Result[Assignment]:
        """
        Update assignment with arbitrary fields.

        Args:
            uid: Assignment UID
            updates: Dictionary of field updates (e.g., {"processed_content": ..., "metadata": ...})

        Returns:
            Result containing updated assignment
        """
        # Serialize metadata to JSON string for Neo4j storage
        # Neo4j cannot store nested dicts/maps as property values
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates = dict(updates)  # Don't mutate the original
            updates["metadata"] = json.dumps(updates["metadata"])

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            field_names = ", ".join(updates.keys())
            self.logger.info(f"Assignment {uid} updated: {field_names}")

        return result

    @with_error_handling("update_processed_content")
    async def update_processed_content(
        self, uid: str, processed_content: str, processed_file_path: str | None = None
    ) -> Result[Assignment]:
        """
        Update assignment with processed content.

        Args:
            uid: Assignment UID
            processed_content: Processed text content
            processed_file_path: Path to processed file (optional)

        Returns:
            Result containing updated assignment
        """
        updates = {"processed_content": processed_content}

        if processed_file_path:
            updates["processed_file_path"] = processed_file_path

        result = await self.backend.update(uid, updates)

        if result.is_ok:
            self.logger.info(f"Assignment {uid} processed content updated")

        return result

    # ========================================================================
    # DELETION AND CLEANUP
    # ========================================================================

    @with_error_handling("delete_assignment_with_file")
    async def delete_assignment_with_file(self, uid: str) -> Result[bool]:
        """
        Delete assignment record AND its associated file from disk.

        This is a hard delete - both the Neo4j record and the file are permanently removed.
        Used for FIFO cleanup of ephemeral journal types.

        Args:
            uid: Assignment UID to delete

        Returns:
            Result containing True if deleted successfully
        """
        # Get assignment to retrieve file_path
        assignment_result = await self.get_assignment(uid)
        if assignment_result.is_error:
            return Result.fail(assignment_result.expect_error())

        assignment = assignment_result.value
        if not assignment:
            return Result.fail(Errors.not_found("Assignment", uid))

        file_path = Path(assignment.file_path) if assignment.file_path else None
        assignment_dir = file_path.parent if file_path else None

        # Delete Neo4j record first
        delete_result = await self.backend.delete(uid)
        if delete_result.is_error:
            return delete_result

        # Delete file from disk
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info(f"Deleted file: {file_path}")

                # Also delete the assignment directory if empty
                if assignment_dir and assignment_dir.exists() and not any(assignment_dir.iterdir()):
                    assignment_dir.rmdir()
                    self.logger.debug(f"Removed empty directory: {assignment_dir}")

            except Exception as e:
                # Log but don't fail - Neo4j record is already deleted
                self.logger.warning(f"Failed to delete file {file_path}: {e}")

        self.logger.info(f"Assignment deleted with file: {uid}")
        return Result.ok(True)

    # ========================================================================
    # FILE RETRIEVAL
    # ========================================================================

    @with_error_handling("get_file_content")
    async def get_file_content(self, assignment_uid: str) -> Result[bytes]:
        """
        Retrieve original file content.

        Args:
            assignment_uid: Assignment UID

        Returns:
            Result containing file bytes
        """
        # Get assignment to find file path
        assignment_result = await self.get_assignment(assignment_uid)

        if assignment_result.is_error:
            return Result.fail(assignment_result.expect_error())

        assignment = assignment_result.value
        if not assignment:
            return Result.fail(Errors.not_found("Assignment", assignment_uid))

        # Read file
        try:
            file_path = Path(assignment.file_path)
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
    async def get_processed_file_content(self, assignment_uid: str) -> Result[bytes]:
        """
        Retrieve processed file content.

        Args:
            assignment_uid: Assignment UID

        Returns:
            Result containing processed file bytes
        """
        # Get assignment to find processed file path
        assignment_result = await self.get_assignment(assignment_uid)

        if assignment_result.is_error:
            return Result.fail(assignment_result.expect_error())

        assignment = assignment_result.value
        if not assignment:
            return Result.fail(Errors.not_found("Assignment", assignment_uid))

        if not assignment.processed_file_path:
            return Result.fail(
                Errors.validation(
                    message="No processed file available for this assignment",
                    field="processed_file_path",
                )
            )

        # Read processed file
        try:
            file_path = Path(assignment.processed_file_path)
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

    @with_error_handling("get_assignment_statistics")
    async def get_assignment_statistics(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get assignment statistics for a user.

        Returns counts by type and status.

        Args:
            user_uid: User UID

        Returns:
            Result containing statistics dictionary
        """
        # Count total assignments
        total_result = await self.count_assignments(user_uid)
        if total_result.is_error:
            return Result.fail(total_result.expect_error())

        statistics: dict[str, Any] = {"total": total_result.value, "by_type": {}, "by_status": {}}

        # Count by type
        for assignment_type in AssignmentType:
            count_result = await self.count_assignments(user_uid, assignment_type=assignment_type)
            if count_result.is_ok:
                statistics["by_type"][assignment_type.value] = count_result.value

        # Count by status
        for status in AssignmentStatus:
            count_result = await self.count_assignments(user_uid, status=status)
            if count_result.is_ok:
                statistics["by_status"][status.value] = count_result.value

        return Result.ok(statistics)
