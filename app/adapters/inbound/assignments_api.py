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

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse

from adapters.inbound.response_helpers import error_response, success_response
from core.models.assignment import assignment_to_response
from core.models.assignment.assignment import AssignmentStatus, AssignmentType, ProcessorType
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.assignments.api")


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
    async def upload_assignment_route(request: Request):
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
        try:
            # Get form data
            form = await request.form()
            uploaded_file = form.get("file")

            if not uploaded_file:
                return error_response("No file provided", status_code=400)

            # Extract parameters
            user_uid = form.get("user_uid")
            if not user_uid:
                return error_response("user_uid is required", status_code=400)

            assignment_type_str = form.get("assignment_type", "transcript")

            # Debug logging
            logger.info(
                f"Received assignment_type from form: '{assignment_type_str}' (type: {type(assignment_type_str).__name__})"
            )
            logger.info(f"All form fields: {dict(form)}")

            try:
                assignment_type = AssignmentType(assignment_type_str)
            except ValueError:
                return error_response(
                    f"Invalid assignment type: '{assignment_type_str}' (received as {type(assignment_type_str).__name__})",
                    status_code=400,
                )

            processor_type_str = form.get("processor_type", "automatic")
            try:
                processor_type = ProcessorType(processor_type_str)
            except ValueError:
                return error_response(
                    f"Invalid processor type: {processor_type_str}", status_code=400
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
                return error_response(
                    "Invalid file upload - file must be uploadable", status_code=400
                )

            file_content = await uploaded_file.read()
            filename = uploaded_file.filename

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
                error = result.expect_error()
                return error_response(
                    error.user_message or error.message, details=error.details, status_code=500
                )

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
                    return success_response(
                        data={
                            "assignment": assignment_to_response(assignment),
                            "processing_status": "failed",
                            "processing_error": error.user_message or error.message,
                            "message": "File uploaded but processing failed",
                        },
                        status_code=201,
                    )

                assignment = process_result.value

            # Return success response
            return success_response(
                data={
                    "assignment": assignment_to_response(assignment),
                    "message": "File uploaded successfully",
                },
                status_code=201,
            )

        except Exception as e:
            logger.error(f"Error uploading file: {e}", exc_info=True)
            return error_response(f"Failed to upload file: {e!s}", status_code=500)

    # ========================================================================
    # LIST & QUERY
    # ========================================================================

    @rt("/api/assignments")
    async def list_assignments_route(
        request: Request,
        user_uid: str | None = None,
        assignment_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
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
        try:
            if not user_uid:
                return error_response("user_uid is required")

            # Parse optional enum filters
            parsed_assignment_type = None
            if assignment_type:
                try:
                    parsed_assignment_type = AssignmentType(assignment_type)
                except ValueError:
                    return error_response(f"Invalid assignment type: {assignment_type}")

            parsed_status = None
            if status:
                try:
                    parsed_status = AssignmentStatus(status)
                except ValueError:
                    return error_response(f"Invalid status: {status}")

            # List assignments
            result = await assignment_service.list_assignments(
                user_uid=user_uid,
                assignment_type=parsed_assignment_type,
                status=parsed_status,
                limit=limit,
                offset=offset,
            )

            if result.is_error:
                return error_response(
                    result.error.user_message if result.error else "Failed to list assignments",
                    status_code=500,
                )

            assignments = result.value

            return success_response(
                {
                    "assignments": [assignment_to_response(a) for a in assignments],
                    "count": len(assignments),
                    "limit": limit,
                    "offset": offset,
                }
            )

        except Exception as e:
            logger.error(f"Error listing assignments: {e}", exc_info=True)
            return error_response(f"Failed to list assignments: {e!s}", status_code=500)

    # ========================================================================
    # GET ASSIGNMENT DETAILS
    # ========================================================================

    @rt("/api/assignments/get")
    async def get_assignment_route(request: Request, uid: str):
        """
        Get assignment details by UID.

        Query parameters:
        - uid: Assignment UID

        Returns:
        - Assignment details
        """
        try:
            result = await assignment_service.get_assignment(uid)

            if result.is_error:
                return error_response(
                    result.error.user_message if result.error else "Failed to get assignment",
                    status_code=500,
                )

            assignment = result.value
            if not assignment:
                return error_response(f"Assignment not found: {uid}", status_code=404)

            return success_response(assignment_to_response(assignment))

        except Exception as e:
            logger.error(f"Error getting assignment: {e}", exc_info=True)
            return error_response(f"Failed to get assignment: {e!s}", status_code=500)

    # ========================================================================
    # GET ASSIGNMENT PROCESSED CONTENT
    # ========================================================================

    @rt("/api/assignments/content")
    async def get_assignment_content_route(request: Request, uid: str):
        """
        Get processed content for an assignment.

        Query parameters:
        - uid: Assignment UID

        Returns:
        - Processed content (transcript text)
        """
        try:
            # Get assignment
            assignment_result = await assignment_service.get_assignment(uid)
            if assignment_result.is_error or not assignment_result.value:
                return error_response(f"Assignment not found: {uid}", status_code=404)

            assignment = assignment_result.value

            # If not completed, return pending status
            if not assignment.is_completed:
                return success_response(
                    {"content": None, "message": "Assignment not yet processed"}
                )

            # Return processed content
            if assignment.processed_content:
                return success_response(
                    {
                        "content": assignment.processed_content,
                        "source": "assignment",
                    }
                )

            # No processed_content
            return success_response(
                {
                    "content": None,
                    "message": "Processed content not available.",
                }
            )

        except Exception as e:
            logger.error(f"Error getting assignment content: {e}", exc_info=True)
            return error_response(f"Failed to get assignment content: {e!s}", status_code=500)

    # ========================================================================
    # PROCESS ASSIGNMENT
    # ========================================================================

    @rt("/api/assignments/process")
    async def process_assignment_route(request: Request, uid: str):
        """
        Process an assignment.

        Query parameters:
        - uid: Assignment UID

        JSON body (optional):
        - instructions: Processor-specific instructions

        Returns:
        - Updated assignment with processed content
        """
        try:
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
                error = result.expect_error()
                return error_response(
                    error.user_message or error.message, details=error.details, status_code=500
                )

            assignment = result.value

            return success_response(
                {
                    "assignment": assignment_to_response(assignment),
                    "message": "Assignment processed successfully",
                }
            )

        except Exception as e:
            logger.error(f"Error processing assignment: {e}", exc_info=True)
            return error_response(f"Failed to process assignment: {e!s}", status_code=500)

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
        try:
            # Get assignment
            assignment_result = await assignment_service.get_assignment(uid)
            if assignment_result.is_error:
                return error_response("Assignment not found", status_code=404)

            assignment = assignment_result.value
            if not assignment:
                return error_response("Assignment not found", status_code=404)

            # Get file content
            file_result = await assignment_service.get_file_content(uid)
            if file_result.is_error:
                return error_response(
                    file_result.error.user_message if file_result.error else "File not found",
                    status_code=404,
                )

            file_content = file_result.value

            # Write to temporary file for response
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            return FileResponse(
                path=temp_path,
                filename=assignment.original_filename,
                media_type=assignment.file_type,
            )

        except Exception as e:
            logger.error(f"Error downloading file: {e}", exc_info=True)
            return error_response(f"Failed to download file: {e!s}", status_code=500)

    @rt("/api/assignments/download-processed")
    async def download_processed_file_route(request: Request, uid: str):
        """
        Download processed file (if available).

        Query parameters:
        - uid: Assignment UID

        Returns:
        - File response with processed file
        """
        try:
            # Get assignment
            assignment_result = await assignment_service.get_assignment(uid)
            if assignment_result.is_error:
                return error_response("Assignment not found", status_code=404)

            assignment = assignment_result.value
            if not assignment:
                return error_response("Assignment not found", status_code=404)

            if not assignment.processed_file_path:
                return error_response("No processed file available", status_code=404)

            # Get processed file content
            file_result = await assignment_service.get_processed_file_content(uid)
            if file_result.is_error:
                return error_response(
                    file_result.error.user_message
                    if file_result.error
                    else "Processed file not found",
                    status_code=404,
                )

            file_content = file_result.value

            # Write to temporary file for response
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            processed_filename = f"processed_{assignment.original_filename}"

            return FileResponse(
                path=temp_path, filename=processed_filename, media_type="text/plain"
            )

        except Exception as e:
            logger.error(f"Error downloading processed file: {e}", exc_info=True)
            return error_response(f"Failed to download processed file: {e!s}", status_code=500)

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @rt("/api/assignments/statistics")
    async def get_statistics_route(request: Request, user_uid: str | None = None):
        """
        Get assignment statistics for a user.

        Query parameters:
        - user_uid: User identifier (required)

        Returns:
        - Statistics by type and status
        """
        try:
            if not user_uid:
                return error_response("user_uid is required")

            result = await assignment_service.get_assignment_statistics(user_uid)

            if result.is_error:
                return error_response(
                    result.error.user_message if result.error else "Failed to get statistics",
                    status_code=500,
                )

            return success_response(result.value)

        except Exception as e:
            logger.error(f"Error getting statistics: {e}", exc_info=True)
            return error_response(f"Failed to get statistics: {e!s}", status_code=500)

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
