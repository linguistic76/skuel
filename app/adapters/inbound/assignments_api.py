"""
Assignments API Routes
======================

REST API for file submission and processing pipeline.

Phase 1 Implementation:
- File upload (audio, text)
- List assignments with filters
- Get assignment details
- Process assignment
- Download original and processed files
- Assignment statistics

Routes:
- POST /api/assignments/upload - Upload file
- GET /api/assignments - List assignments
- GET /api/assignments/{uid} - Get assignment details
- POST /api/assignments/{uid}/process - Process assignment
- GET /api/assignments/{uid}/download - Download original file
- GET /api/assignments/{uid}/download-processed - Download processed file
- GET /api/assignments/statistics - Get user statistics
"""

import tempfile
from pathlib import Path
from typing import Any

from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse

from core.models.assignment import assignment_to_response
from core.models.assignment.assignment import AssignmentStatus, AssignmentType, ProcessorType
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.assignments.api")


# ============================================================================
# TEMP FILE CLEANUP HELPER
# ============================================================================


def cleanup_temp_file(filepath: str):
    """Background task to cleanup temp files after response"""
    try:
        Path(filepath).unlink()
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {filepath}: {e}")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_assignments_api_routes(
    _app, rt, assignment_service, processing_service, assignments_query_service=None
):
    """
    Create all assignment API routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        assignment_service: AssignmentSubmissionService
        processing_service: AssignmentProcessorService
        assignments_query_service: AssignmentsQueryService for cross-domain queries
    """

    # FAIL-FAST: Validate required services BEFORE any route registration
    missing = []
    if not assignment_service:
        missing.append("assignment_service")
    if not processing_service:
        missing.append("processing_service")
    if missing:
        raise ValueError(f"Required services missing for assignments API: {', '.join(missing)}")

    logger.info("Creating Assignments API routes")

    # ========================================================================
    # FILE UPLOAD
    # ========================================================================

    @rt("/api/assignments/upload")
    @boundary_handler(success_status=201)
    async def upload_assignment_route(request: Request) -> Result[Any]:
        """
        Upload file for processing.

        Form data:
        - file: File upload (required)
        - user_uid: User identifier (required)
        - assignment_type: Type (transcript, report, image_analysis, video_summary) (required)
        - processor_type: Processor (llm, human, hybrid, automatic) (default: automatic)
        - auto_process: Automatically process after upload (default: false)

        Returns:
        - 201 Created with assignment details
        """
        # Get form data
        form = await request.form()
        uploaded_file = form.get("file")

        if not uploaded_file:
            return Result.fail(Errors.validation("No file provided", field="file"))

        # Extract parameters
        user_uid = form.get("user_uid")
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        assignment_type_str = form.get("assignment_type", "transcript")

        # Debug logging
        logger.info(
            f"Received assignment_type from form: '{assignment_type_str}' (type: {type(assignment_type_str).__name__})"
        )
        logger.info(f"All form fields: {dict(form)}")

        # Validate assignment_type
        try:
            assignment_type = AssignmentType(assignment_type_str)
        except ValueError:
            return Result.fail(
                Errors.validation(
                    f"Invalid assignment type: '{assignment_type_str}' (received as {type(assignment_type_str).__name__})",
                    field="assignment_type",
                )
            )

        # Validate processor_type
        processor_type_str = form.get("processor_type", "automatic")
        try:
            processor_type = ProcessorType(processor_type_str)
        except ValueError:
            return Result.fail(
                Errors.validation(
                    f"Invalid processor type: {processor_type_str}", field="processor_type"
                )
            )

        # Type narrow auto_process to str
        auto_process_val = form.get("auto_process", "false")
        if isinstance(auto_process_val, str):
            auto_process = auto_process_val.lower() == "true"
        else:
            auto_process = False

        # Type narrow uploaded_file to UploadFile
        if not isinstance(uploaded_file, UploadFile):
            logger.error(
                f"Invalid file upload object: expected UploadFile, got {type(uploaded_file)}"
            )
            return Result.fail(Errors.validation("Invalid file upload"))

        file_content = await uploaded_file.read()
        filename = uploaded_file.filename

        # Size limit (100MB)
        if len(file_content) > 100_000_000:
            return Result.fail(Errors.validation("File too large (max 100MB)", field="file"))

        logger.info(
            f"File upload: {filename} ({len(file_content)} bytes, type={assignment_type.value})"
        )

        # Submit file
        result = await assignment_service.submit_file(
            file_content=file_content,
            original_filename=filename,
            user_uid=user_uid,
            assignment_type=assignment_type,
            processor_type=processor_type,
        )

        if result.is_error:
            return result

        assignment = result.value

        # Auto-process if requested
        if auto_process:
            logger.info(f"Auto-processing assignment: {assignment.uid}")
            process_result = await processing_service.process_assignment(assignment.uid)

            if process_result.is_error:
                # Return assignment anyway, but note processing failed
                error = process_result.expect_error()
                logger.warning(f"Auto-processing failed for {assignment.uid}: {error.message}")

                # Processing failed but upload succeeded
                return Result.ok(
                    {
                        "assignment": assignment_to_response(assignment),
                        "processing_status": "failed",
                        "processing_error": error.user_message or error.message,
                        "message": "File uploaded but processing failed",
                    }
                )

            assignment = process_result.value

        # Return success response
        return Result.ok(
            {
                "assignment": assignment_to_response(assignment),
                "message": "File uploaded successfully",
            }
        )

    # ========================================================================
    # LIST & QUERY
    # ========================================================================

    @rt("/api/assignments")
    @boundary_handler()
    async def list_assignments_route(
        request: Request,
        user_uid: str | None = None,
        assignment_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[Any]:
        """
        List assignments for a user with filters.

        Query parameters:
        - user_uid: User identifier (required)
        - assignment_type: Filter by type (optional)
        - status: Filter by status (optional)
        - limit: Max results (default: 50)
        - offset: Pagination offset (default: 0)

        Returns:
        - List of assignments
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        # Parse optional enum filters
        parsed_assignment_type = None
        if assignment_type:
            try:
                parsed_assignment_type = AssignmentType(assignment_type)
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        f"Invalid assignment type: {assignment_type}", field="assignment_type"
                    )
                )

        parsed_status = None
        if status:
            try:
                parsed_status = AssignmentStatus(status)
            except ValueError:
                return Result.fail(Errors.validation(f"Invalid status: {status}", field="status"))

        # List assignments
        result = await assignment_service.list_assignments(
            user_uid=user_uid,
            assignment_type=parsed_assignment_type,
            status=parsed_status,
            limit=limit,
            offset=offset,
        )

        if result.is_error:
            return result

        assignments = result.value

        return Result.ok(
            {
                "assignments": [assignment_to_response(a) for a in assignments],
                "count": len(assignments),
                "limit": limit,
                "offset": offset,
            }
        )

    # ========================================================================
    # GET ASSIGNMENT DETAILS
    # ========================================================================

    @rt("/api/assignments/get")
    @boundary_handler()
    async def get_assignment_route(request: Request, uid: str) -> Result[Any]:
        """
        Get assignment details by UID.

        Query parameters:
        - uid: Assignment UID

        Returns:
        - Assignment details
        """
        result = await assignment_service.get_assignment(uid)

        if result.is_error:
            return result

        assignment = result.value
        if not assignment:
            return Result.fail(Errors.not_found(resource="Assignment", identifier=uid))

        return Result.ok(assignment_to_response(assignment))

    # ========================================================================
    # GET ASSIGNMENT PROCESSED CONTENT
    # ========================================================================

    @rt("/api/assignments/content")
    @boundary_handler()
    async def get_assignment_content_route(request: Request, uid: str) -> Result[Any]:
        """
        Get processed content for an assignment.

        Query parameters:
        - uid: Assignment UID

        Returns:
        - Processed content (transcript text)
        """
        # Get assignment
        assignment_result = await assignment_service.get_assignment(uid)
        if assignment_result.is_error or not assignment_result.value:
            return Result.fail(Errors.not_found(resource="Assignment", identifier=uid))

        assignment = assignment_result.value

        # If not completed, return pending status
        if not assignment.is_completed:
            return Result.ok({"content": None, "message": "Assignment not yet processed"})

        # Return processed content
        if assignment.processed_content:
            return Result.ok(
                {
                    "content": assignment.processed_content,
                    "source": "assignment",
                }
            )

        # No processed_content
        return Result.ok(
            {
                "content": None,
                "message": "Processed content not available.",
            }
        )

    # ========================================================================
    # PROCESS ASSIGNMENT
    # ========================================================================

    @rt("/api/assignments/process")
    @boundary_handler()
    async def process_assignment_route(request: Request, uid: str) -> Result[Any]:
        """
        Process an assignment.

        Query parameters:
        - uid: Assignment UID

        JSON body (optional):
        - instructions: Processor-specific instructions

        Returns:
        - Updated assignment with processed content
        """
        # Get optional instructions
        instructions = None
        if request.method == "POST":
            try:
                body = await request.json()
                instructions = body.get("instructions")
            except Exception:
                pass  # No body provided

        result = await processing_service.process_assignment(uid, instructions)

        if result.is_error:
            return result

        assignment = result.value

        return Result.ok(
            {
                "assignment": assignment_to_response(assignment),
                "message": "Assignment processed successfully",
            }
        )

    # ========================================================================
    # FILE DOWNLOADS
    # ========================================================================

    @rt("/api/assignments/download")
    async def download_original_file_route(request: Request, uid: str):
        """
        Download original uploaded file.

        Query parameters:
        - uid: Assignment UID

        Returns:
        - File response with original file
        """
        from starlette.responses import Response

        # Get assignment
        assignment_result = await assignment_service.get_assignment(uid)
        if assignment_result.is_error:
            return Response(
                content=f"Error: {assignment_result.error.user_message if assignment_result.error else 'Assignment not found'}",
                status_code=404,
                media_type="text/plain",
            )

        assignment = assignment_result.value
        if not assignment:
            return Response(
                content="Error: Assignment not found", status_code=404, media_type="text/plain"
            )

        # Get file content
        file_result = await assignment_service.get_file_content(uid)
        if file_result.is_error:
            return Response(
                content=f"Error: {file_result.error.user_message if file_result.error else 'File not found'}",
                status_code=404,
                media_type="text/plain",
            )

        file_content = file_result.value

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(assignment.original_filename).suffix
        )
        temp_file.write(file_content)
        temp_file.close()

        # Return file with background cleanup task
        return FileResponse(
            path=temp_file.name,
            filename=assignment.original_filename,
            media_type=assignment.file_type,
            background=BackgroundTask(cleanup_temp_file, temp_file.name),
        )

    @rt("/api/assignments/download-processed")
    async def download_processed_file_route(request: Request, uid: str):
        """
        Download processed file (if available).

        Query parameters:
        - uid: Assignment UID

        Returns:
        - File response with processed file
        """
        from starlette.responses import Response

        # Get assignment
        assignment_result = await assignment_service.get_assignment(uid)
        if assignment_result.is_error:
            return Response(
                content=f"Error: {assignment_result.error.user_message if assignment_result.error else 'Assignment not found'}",
                status_code=404,
                media_type="text/plain",
            )

        assignment = assignment_result.value
        if not assignment:
            return Response(
                content="Error: Assignment not found", status_code=404, media_type="text/plain"
            )

        if not assignment.processed_file_path:
            return Response(
                content="Error: No processed file available",
                status_code=404,
                media_type="text/plain",
            )

        # Get processed file content
        file_result = await assignment_service.get_processed_file_content(uid)
        if file_result.is_error:
            return Response(
                content=f"Error: {file_result.error.user_message if file_result.error else 'Processed file not found'}",
                status_code=404,
                media_type="text/plain",
            )

        file_content = file_result.value

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        temp_file.write(file_content)
        temp_file.close()

        processed_filename = f"processed_{assignment.original_filename}"

        # Return file with background cleanup task
        return FileResponse(
            path=temp_file.name,
            filename=processed_filename,
            media_type="text/plain",
            background=BackgroundTask(cleanup_temp_file, temp_file.name),
        )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @rt("/api/assignments/statistics")
    @boundary_handler()
    async def get_statistics_route(request: Request, user_uid: str | None = None) -> Result[Any]:
        """
        Get assignment statistics for a user.

        Query parameters:
        - user_uid: User identifier (required)

        Returns:
        - Statistics by type and status
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        result = await assignment_service.get_assignment_statistics(user_uid)

        if result.is_error:
            return result

        return Result.ok(result.value)

    logger.info("Assignments API routes created successfully")

    return [
        upload_assignment_route,
        list_assignments_route,
        get_assignment_route,
        process_assignment_route,
        download_original_file_route,
        download_processed_file_route,
        get_statistics_route,
    ]
