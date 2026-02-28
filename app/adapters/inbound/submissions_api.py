"""
Submissions API Routes
======================

REST API for file submission and processing pipeline.

- File upload (audio, text)
- List submissions with filters
- Get submission details
- Process submission
- Download original and processed files
- Submission statistics

Routes:
- POST /api/submissions/upload - Upload file
- GET /api/submissions - List submissions
- GET /api/submissions/get?uid=... - Get submission details
- POST /api/submissions/process?uid=... - Process submission
- GET /api/submissions/download?uid=... - Download original file
- GET /api/submissions/download-processed?uid=... - Download processed file
- GET /api/submissions/statistics - Get user statistics
"""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.group_protocols import TeacherReviewOperations
    from core.ports.submission_protocols import (
        SubmissionOperations,
        SubmissionProcessingOperations,
        SubmissionSearchOperations,
    )

from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.entity_converters import ku_to_response
from core.models.entity_requests import (
    AddTagsRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeEntityRequest,
    RemoveTagsRequest,
)
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.submissions.api")


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


def create_submissions_api_routes(
    _app: Any,
    rt: Any,
    submission_service: "SubmissionOperations",
    processing_service: "SubmissionProcessingOperations",
    submissions_search_service: "SubmissionSearchOperations | None" = None,
    submissions_core_service: "SubmissionOperations | None" = None,
    teacher_review_service: "TeacherReviewOperations | None" = None,
) -> list[Any]:
    """
    Create all submissions API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        submission_service: SubmissionsService for upload and retrieval
        processing_service: SubmissionsProcessingService for content processing
        submissions_search_service: SubmissionsSearchService for cross-domain queries
        submissions_core_service: SubmissionsCoreService for content management
        teacher_review_service: TeacherReviewService for feedback history queries
    """

    # FAIL-FAST: Validate required services BEFORE any route registration
    missing = []
    if not submission_service:
        missing.append("submission_service")
    if not processing_service:
        missing.append("processing_service")
    if missing:
        raise ValueError(f"Required services missing for submissions API: {', '.join(missing)}")

    logger.info("Creating Submissions API routes")

    # ========================================================================
    # FILE UPLOAD
    # ========================================================================

    @rt("/api/submissions/upload")
    @boundary_handler(success_status=201)
    async def upload_submission_route(request: Request) -> Result[Any]:
        """
        Upload file for processing.

        Form data:
        - file: File upload (required)
        - user_uid: User identifier (required)
        - report_type: Type (transcript, report, image_analysis, video_summary) (required)
        - processor_type: Processor (llm, human, hybrid, automatic) (default: automatic)
        - auto_process: Automatically process after upload (default: false)

        Returns:
        - 201 Created with submission details
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

        report_type_str = form.get("report_type", "transcript")

        # Debug logging
        logger.info(
            f"Received report_type from form: '{report_type_str}' (type: {type(report_type_str).__name__})"
        )
        logger.info(f"All form fields: {dict(form)}")

        # Validate report_type
        try:
            report_type = EntityType(report_type_str)
        except ValueError:
            return Result.fail(
                Errors.validation(
                    f"Invalid report type: '{report_type_str}' (received as {type(report_type_str).__name__})",
                    field="report_type",
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

        # Extract applies_knowledge_uids (MVP - Phase C)
        applies_knowledge_uids = []
        applies_knowledge_str = form.get("applies_knowledge_uids", "")
        if isinstance(applies_knowledge_str, str) and applies_knowledge_str:
            # Parse comma-separated UIDs or JSON array
            if applies_knowledge_str.startswith("["):
                # JSON array format
                import json

                try:
                    applies_knowledge_uids = json.loads(applies_knowledge_str)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse applies_knowledge_uids JSON: {applies_knowledge_str}"
                    )
            else:
                # Comma-separated format
                applies_knowledge_uids = [
                    uid.strip() for uid in applies_knowledge_str.split(",") if uid.strip()
                ]

        logger.info(
            f"File upload: {filename} ({len(file_content)} bytes, type={report_type.value}, "
            f"applies_knowledge={len(applies_knowledge_uids)} KUs)"
        )

        # Extract fulfills_exercise_uid for assigned exercise submissions
        fulfills_exercise_uid_val = form.get("fulfills_exercise_uid", "")
        fulfills_exercise_uid = (
            str(fulfills_exercise_uid_val).strip() if fulfills_exercise_uid_val else None
        )

        # Submit file
        result = await submission_service.submit_file(
            file_content=file_content,
            original_filename=filename,
            user_uid=user_uid,
            ku_type=report_type,
            processor_type=processor_type,
            applies_knowledge_uids=applies_knowledge_uids if applies_knowledge_uids else None,
            fulfills_exercise_uid=fulfills_exercise_uid if fulfills_exercise_uid else None,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        submission = result.value

        # Auto-process if requested
        if auto_process:
            logger.info(f"Auto-processing submission: {submission.uid}")
            process_result = await processing_service.process_submission(submission.uid)

            if process_result.is_error:
                # Return submission anyway, but note processing failed
                error = process_result.expect_error()
                logger.warning(f"Auto-processing failed for {submission.uid}: {error.message}")

                # Processing failed but upload succeeded
                return Result.ok(
                    {
                        "submission": ku_to_response(submission),
                        "processing_status": "failed",
                        "processing_error": error.user_message or error.message,
                        "message": "File uploaded but processing failed",
                    }
                )

            submission = process_result.value

        # Return success response
        return Result.ok(
            {
                "submission": ku_to_response(submission),
                "message": "File uploaded successfully",
            }
        )

    # ========================================================================
    # LIST & QUERY
    # ========================================================================

    @rt("/api/submissions")
    @boundary_handler()
    async def list_submissions_route(
        request: Request,
        user_uid: str | None = None,
        report_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[Any]:
        """
        List reports for a user with filters.

        Query parameters:
        - user_uid: User identifier (required)
        - report_type: Filter by type (optional)
        - status: Filter by status (optional)
        - limit: Max results (default: 50)
        - offset: Pagination offset (default: 0)

        Returns:
        - List of reports
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        # Parse optional enum filters
        parsed_report_type = None
        if report_type:
            try:
                parsed_report_type = EntityType(report_type)
            except ValueError:
                return Result.fail(
                    Errors.validation(f"Invalid report type: {report_type}", field="report_type")
                )

        parsed_status = None
        if status:
            try:
                parsed_status = EntityStatus(status)
            except ValueError:
                return Result.fail(Errors.validation(f"Invalid status: {status}", field="status"))

        # List reports
        result = await submission_service.list_submissions(
            user_uid=user_uid,
            ku_type=parsed_report_type,
            status=parsed_status,
            limit=limit,
            offset=offset,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value

        return Result.ok(
            {
                "reports": [ku_to_response(a) for a in reports],
                "count": len(reports),
                "limit": limit,
                "offset": offset,
            }
        )

    # ========================================================================
    # GET REPORT DETAILS
    # ========================================================================

    @rt("/api/submissions/get")
    @boundary_handler()
    async def get_submission_route(request: Request, uid: str) -> Result[Any]:
        """
        Get submission details by UID.

        Query parameters:
        - uid: Report UID

        Returns:
        - Report details
        """
        result = await submission_service.get_submission(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        submission = result.value
        if not submission:
            return Result.fail(Errors.not_found(resource="Submission", identifier=uid))

        return Result.ok(ku_to_response(submission))

    # ========================================================================
    # GET REPORT PROCESSED CONTENT
    # ========================================================================

    @rt("/api/submissions/content")
    @boundary_handler()
    async def get_submission_content_route(request: Request, uid: str) -> Result[Any]:
        """
        Get processed content for a submission.

        Query parameters:
        - uid: Report UID

        Returns:
        - Processed content (transcript text)
        """
        # Get submission
        submission_result = await submission_service.get_submission(uid)
        if submission_result.is_error or not submission_result.value:
            return Result.fail(Errors.not_found(resource="Submission", identifier=uid))

        submission = submission_result.value

        # If not completed, return pending status
        if not submission.is_completed:
            return Result.ok({"content": None, "message": "Submission not yet processed"})

        # Return processed content
        if submission.processed_content:
            return Result.ok(
                {
                    "content": submission.processed_content,
                    "source": "submission",
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
    # PROCESS REPORT
    # ========================================================================

    @rt("/api/submissions/process")
    @boundary_handler()
    async def process_submission_route(request: Request, uid: str) -> Result[Any]:
        """
        Process a submission.

        Query parameters:
        - uid: Report UID

        JSON body (optional):
        - instructions: Processor-specific instructions

        Returns:
        - Updated submission with processed content
        """
        # Get optional instructions
        instructions = None
        if request.method == "POST":
            try:
                body = await request.json()
                instructions = body.get("instructions")
            except Exception:
                pass  # No body provided

        result = await processing_service.process_submission(uid, instructions)

        if result.is_error:
            return Result.fail(result.expect_error())

        submission = result.value

        return Result.ok(
            {
                "submission": ku_to_response(submission),
                "message": "Submission processed successfully",
            }
        )

    # ========================================================================
    # FILE DOWNLOADS
    # ========================================================================

    @rt("/api/submissions/download")
    async def download_original_file_route(request: Request, uid: str):
        """
        Download original uploaded file.

        Query parameters:
        - uid: Report UID

        Returns:
        - File response with original file
        """
        from starlette.responses import Response

        # Get submission
        submission_result = await submission_service.get_submission(uid)
        if submission_result.is_error:
            return Response(
                content=f"Error: {submission_result.error.user_message if submission_result.error else 'Submission not found'}",
                status_code=404,
                media_type="text/plain",
            )

        submission = submission_result.value
        if not submission:
            return Response(
                content="Error: Submission not found", status_code=404, media_type="text/plain"
            )

        # Get file content
        file_result = await submission_service.get_file_content(uid)
        if file_result.is_error:
            return Response(
                content=f"Error: {file_result.error.user_message if file_result.error else 'File not found'}",
                status_code=404,
                media_type="text/plain",
            )

        file_content = file_result.value

        # Create temp file with context manager
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(submission.original_filename).suffix
        ) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        # Return file with background cleanup task
        return FileResponse(
            path=temp_file_path,
            filename=submission.original_filename,
            media_type=submission.file_type,
            background=BackgroundTask(cleanup_temp_file, temp_file_path),
        )

    @rt("/api/submissions/download-processed")
    async def download_processed_file_route(request: Request, uid: str):
        """
        Download processed file (if available).

        Query parameters:
        - uid: Report UID

        Returns:
        - File response with processed file
        """
        from starlette.responses import Response

        # Get submission
        submission_result = await submission_service.get_submission(uid)
        if submission_result.is_error:
            return Response(
                content=f"Error: {submission_result.error.user_message if submission_result.error else 'Submission not found'}",
                status_code=404,
                media_type="text/plain",
            )

        submission = submission_result.value
        if not submission:
            return Response(
                content="Error: Submission not found", status_code=404, media_type="text/plain"
            )

        if not submission.processed_file_path:
            return Response(
                content="Error: No processed file available",
                status_code=404,
                media_type="text/plain",
            )

        # Get processed file content
        file_result = await submission_service.get_processed_file_content(uid)
        if file_result.is_error:
            return Response(
                content=f"Error: {file_result.error.user_message if file_result.error else 'Processed file not found'}",
                status_code=404,
                media_type="text/plain",
            )

        file_content = file_result.value

        # Create temp file with context manager
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        processed_filename = f"processed_{submission.original_filename}"

        # Return file with background cleanup task
        return FileResponse(
            path=temp_file_path,
            filename=processed_filename,
            media_type="text/plain",
            background=BackgroundTask(cleanup_temp_file, temp_file_path),
        )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @rt("/api/submissions/statistics")
    @boundary_handler()
    async def get_statistics_route(request: Request, user_uid: str | None = None) -> Result[Any]:
        """
        Get submission statistics for a user.

        Query parameters:
        - user_uid: User identifier (required)

        Returns:
        - Statistics by type and status
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        result = await submission_service.get_submission_statistics(user_uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(result.value)

    # ========================================================================
    # CONTENT MANAGEMENT ROUTES
    # ========================================================================

    if submissions_core_service:

        @rt("/api/submissions/categorize")
        @boundary_handler()
        async def categorize_submission_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Categorize a submission.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - category: Category string
            """
            body = await request.json()
            req = CategorizeEntityRequest.model_validate(body)

            # Verify ownership through get_submission
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.categorize_submission(
                uid=submission_uid, category=req.category
            )

        @rt("/api/submissions/tags/add")
        @boundary_handler()
        async def add_tags_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Add tags to a submission.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - tags: List of tag strings
            """
            body = await request.json()
            req = AddTagsRequest.model_validate(body)

            # Verify ownership
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.add_tags(uid=submission_uid, tags=req.tags)

        @rt("/api/submissions/tags/remove")
        @boundary_handler()
        async def remove_tags_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Remove tags from a submission.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - tags: List of tag strings to remove
            """
            body = await request.json()
            req = RemoveTagsRequest.model_validate(body)

            # Verify ownership
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.remove_tags(uid=submission_uid, tags=req.tags)

        @rt("/api/submissions/publish")
        @boundary_handler()
        async def publish_submission_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Publish a submission.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.publish_submission(uid=submission_uid)

        @rt("/api/submissions/archive")
        @boundary_handler()
        async def archive_submission_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Archive a submission.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.archive_submission(uid=submission_uid)

        @rt("/api/submissions/draft")
        @boundary_handler()
        async def mark_as_draft_route(
            request: Request, submission_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Mark submission as draft.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            submission_result = await submission_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result.expect_error())

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    Errors.not_found(resource="Submission", identifier=submission_uid)
                )

            return await submissions_core_service.mark_as_draft(uid=submission_uid)

        @rt("/api/submissions/bulk/categorize")
        @boundary_handler()
        async def bulk_categorize_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk categorize reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - ku_uids: List of submission UIDs
            - category: Category string
            """
            body = await request.json()
            req = BulkCategorizeRequest.model_validate(body)

            # Verify user owns all reports
            for uid in req.ku_uids:
                submission_result = await submission_service.get_submission(uid)
                if submission_result.is_error:
                    return Result.fail(submission_result.expect_error())

                submission = submission_result.value
                if submission is None or submission.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(
                            f"You do not own submission {uid}", field="submission_uids"
                        )
                    )

            return await submissions_core_service.bulk_categorize(
                uids=req.ku_uids, category=req.category
            )

        @rt("/api/submissions/bulk/tag")
        @boundary_handler()
        async def bulk_tag_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk tag reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - ku_uids: List of submission UIDs
            - tags: List of tag strings
            """
            body = await request.json()
            req = BulkTagRequest.model_validate(body)

            # Verify ownership
            for uid in req.ku_uids:
                submission_result = await submission_service.get_submission(uid)
                if submission_result.is_error:
                    return Result.fail(submission_result.expect_error())

                submission = submission_result.value
                if submission is None or submission.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(
                            f"You do not own submission {uid}", field="submission_uids"
                        )
                    )

            return await submissions_core_service.bulk_tag(uids=req.ku_uids, tags=req.tags)

        @rt("/api/submissions/bulk/delete")
        @boundary_handler()
        async def bulk_delete_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk delete reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - ku_uids: List of submission UIDs
            - soft_delete: Boolean (default True)
            """
            body = await request.json()
            req = BulkDeleteRequest.model_validate(body)

            # Verify ownership
            for uid in req.ku_uids:
                submission_result = await submission_service.get_submission(uid)
                if submission_result.is_error:
                    return Result.fail(submission_result.expect_error())

                submission = submission_result.value
                if submission is None or submission.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(
                            f"You do not own submission {uid}", field="submission_uids"
                        )
                    )

            return await submissions_core_service.bulk_delete(
                uids=req.ku_uids, soft_delete=req.soft_delete
            )

        @rt("/api/submissions/by-category")
        @boundary_handler()
        async def get_by_category_route(
            request: Request, user_uid: str, category: str, limit: int = 50
        ) -> Result[Any]:
            """
            Get reports by category.

            Query parameters:
            - user_uid: User UID
            - category: Category string
            - limit: Max results (default 50)
            """
            return await submissions_core_service.get_submissions_by_category(
                category=category, limit=limit, user_uid=user_uid
            )

        @rt("/api/submissions/recent")
        @boundary_handler()
        async def get_recent_route(request: Request, user_uid: str, limit: int = 10) -> Result[Any]:
            """
            Get recent reports.

            Query parameters:
            - user_uid: User UID
            - limit: Max results (default 10)
            """
            return await submissions_core_service.get_recent_submissions(
                limit=limit, user_uid=user_uid
            )

        logger.info("Submission content management routes registered (12 new routes)")

    # ========================================================================
    # STUDENT FEEDBACK HISTORY (student-accessible, ownership-verified)
    # ========================================================================

    if teacher_review_service:

        @rt("/api/submissions/{uid}/feedback")
        @boundary_handler()
        async def get_submission_feedback_route(request: Request, uid: str) -> Result[Any]:
            """
            Get all feedback rounds for a specific submission (student-facing).

            Ownership-verified: returns 404 if the requesting user does not own
            the submission — no information leakage about other students' work.

            Returns:
            - 200 with {submission_uid, feedback: [...], count: N}
            - 404 if submission not found or not owned by requester
            """
            user_uid = require_authenticated_user(request)

            ownership = await submission_service.verify_ownership(uid, user_uid)
            if ownership.is_error:
                return Result.fail(Errors.not_found("submission", uid))

            result = await teacher_review_service.get_feedback_history(uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            feedback = result.value or []
            return Result.ok(
                {
                    "submission_uid": uid,
                    "feedback": feedback,
                    "count": len(feedback),
                }
            )

        logger.info("Student feedback history route registered (/api/submissions/{uid}/feedback)")

    logger.info("Submissions API routes created successfully")

    return [
        upload_submission_route,
        list_submissions_route,
        get_submission_route,
        process_submission_route,
        download_original_file_route,
        download_processed_file_route,
        get_statistics_route,
    ]
