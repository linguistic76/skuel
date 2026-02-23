"""
Reports API Routes
======================

REST API for file submission and processing pipeline.

Phase 1 Implementation:
- File upload (audio, text)
- List reports with filters
- Get report details
- Process report
- Download original and processed files
- Report statistics

Routes:
- POST /api/reports/upload - Upload file
- GET /api/reports - List reports
- GET /api/reports/{uid} - Get report details
- POST /api/reports/{uid}/process - Process report
- GET /api/reports/{uid}/download - Download original file
- GET /api/reports/{uid}/download-processed - Download processed file
- GET /api/reports/statistics - Get user statistics
"""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.reports_protocols import (
        KuContentOperations,
        KuContentSearchOperations,
        KuProcessingOperations,
        KuSubmissionOperations,
    )

from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse

from adapters.inbound.boundary import boundary_handler
from core.models.enums.ku_enums import EntityStatus, EntityType, ProcessorType
from core.models.ku import ku_to_response
from core.models.ku.ku_request import (
    AddTagsRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeEntityRequest,
    RemoveTagsRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.reports.api")


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


def create_reports_api_routes(
    _app: Any,
    rt: Any,
    report_service: "KuSubmissionOperations",
    processing_service: "KuProcessingOperations",
    reports_query_service: "KuContentSearchOperations | None" = None,
    reports_core_service: "KuContentOperations | None" = None,
) -> list[Any]:
    """
    Create all report API routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        report_service: ReportSubmissionService
        processing_service: ReportsProcessingService
        reports_query_service: ReportsSearchService for cross-domain queries
        reports_core_service: ReportsCoreService for content management
    """

    # FAIL-FAST: Validate required services BEFORE any route registration
    missing = []
    if not report_service:
        missing.append("report_service")
    if not processing_service:
        missing.append("processing_service")
    if missing:
        raise ValueError(f"Required services missing for reports API: {', '.join(missing)}")

    logger.info("Creating Reports API routes")

    # ========================================================================
    # FILE UPLOAD
    # ========================================================================

    @rt("/api/reports/upload")
    @boundary_handler(success_status=201)
    async def upload_report_route(request: Request) -> Result[Any]:
        """
        Upload file for processing.

        Form data:
        - file: File upload (required)
        - user_uid: User identifier (required)
        - report_type: Type (transcript, report, image_analysis, video_summary) (required)
        - processor_type: Processor (llm, human, hybrid, automatic) (default: automatic)
        - auto_process: Automatically process after upload (default: false)

        Returns:
        - 201 Created with report details
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

        # Extract fulfills_project_uid for assignment submissions
        fulfills_project_uid_val = form.get("fulfills_project_uid", "")
        fulfills_project_uid = (
            str(fulfills_project_uid_val).strip() if fulfills_project_uid_val else None
        )

        # Submit file
        result = await report_service.submit_file(
            file_content=file_content,
            original_filename=filename,
            user_uid=user_uid,
            ku_type=report_type,
            processor_type=processor_type,
            applies_knowledge_uids=applies_knowledge_uids if applies_knowledge_uids else None,
            fulfills_project_uid=fulfills_project_uid if fulfills_project_uid else None,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        report = result.value

        # Auto-process if requested
        if auto_process:
            logger.info(f"Auto-processing report: {report.uid}")
            process_result = await processing_service.process_report(report.uid)

            if process_result.is_error:
                # Return report anyway, but note processing failed
                error = process_result.expect_error()
                logger.warning(f"Auto-processing failed for {report.uid}: {error.message}")

                # Processing failed but upload succeeded
                return Result.ok(
                    {
                        "report": ku_to_response(report),
                        "processing_status": "failed",
                        "processing_error": error.user_message or error.message,
                        "message": "File uploaded but processing failed",
                    }
                )

            report = process_result.value

        # Return success response
        return Result.ok(
            {
                "report": ku_to_response(report),
                "message": "File uploaded successfully",
            }
        )

    # ========================================================================
    # LIST & QUERY
    # ========================================================================

    @rt("/api/reports")
    @boundary_handler()
    async def list_reports_route(
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
        result = await report_service.list_reports(
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

    @rt("/api/reports/get")
    @boundary_handler()
    async def get_report_route(request: Request, uid: str) -> Result[Any]:
        """
        Get report details by UID.

        Query parameters:
        - uid: Report UID

        Returns:
        - Report details
        """
        result = await report_service.get_report(uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        report = result.value
        if not report:
            return Result.fail(Errors.not_found(resource="Report", identifier=uid))

        return Result.ok(ku_to_response(report))

    # ========================================================================
    # GET REPORT PROCESSED CONTENT
    # ========================================================================

    @rt("/api/reports/content")
    @boundary_handler()
    async def get_report_content_route(request: Request, uid: str) -> Result[Any]:
        """
        Get processed content for a report.

        Query parameters:
        - uid: Report UID

        Returns:
        - Processed content (transcript text)
        """
        # Get report
        report_result = await report_service.get_report(uid)
        if report_result.is_error or not report_result.value:
            return Result.fail(Errors.not_found(resource="Report", identifier=uid))

        report = report_result.value

        # If not completed, return pending status
        if not report.is_completed:
            return Result.ok({"content": None, "message": "Report not yet processed"})

        # Return processed content
        if report.processed_content:
            return Result.ok(
                {
                    "content": report.processed_content,
                    "source": "report",
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

    @rt("/api/reports/process")
    @boundary_handler()
    async def process_report_route(request: Request, uid: str) -> Result[Any]:
        """
        Process a report.

        Query parameters:
        - uid: Report UID

        JSON body (optional):
        - instructions: Processor-specific instructions

        Returns:
        - Updated report with processed content
        """
        # Get optional instructions
        instructions = None
        if request.method == "POST":
            try:
                body = await request.json()
                instructions = body.get("instructions")
            except Exception:
                pass  # No body provided

        result = await processing_service.process_report(uid, instructions)

        if result.is_error:
            return Result.fail(result.expect_error())

        report = result.value

        return Result.ok(
            {
                "report": ku_to_response(report),
                "message": "Report processed successfully",
            }
        )

    # ========================================================================
    # FILE DOWNLOADS
    # ========================================================================

    @rt("/api/reports/download")
    async def download_original_file_route(request: Request, uid: str):
        """
        Download original uploaded file.

        Query parameters:
        - uid: Report UID

        Returns:
        - File response with original file
        """
        from starlette.responses import Response

        # Get report
        report_result = await report_service.get_report(uid)
        if report_result.is_error:
            return Response(
                content=f"Error: {report_result.error.user_message if report_result.error else 'Report not found'}",
                status_code=404,
                media_type="text/plain",
            )

        report = report_result.value
        if not report:
            return Response(
                content="Error: Report not found", status_code=404, media_type="text/plain"
            )

        # Get file content
        file_result = await report_service.get_file_content(uid)
        if file_result.is_error:
            return Response(
                content=f"Error: {file_result.error.user_message if file_result.error else 'File not found'}",
                status_code=404,
                media_type="text/plain",
            )

        file_content = file_result.value

        # Create temp file with context manager
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(report.original_filename).suffix
        ) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        # Return file with background cleanup task
        return FileResponse(
            path=temp_file_path,
            filename=report.original_filename,
            media_type=report.file_type,
            background=BackgroundTask(cleanup_temp_file, temp_file_path),
        )

    @rt("/api/reports/download-processed")
    async def download_processed_file_route(request: Request, uid: str):
        """
        Download processed file (if available).

        Query parameters:
        - uid: Report UID

        Returns:
        - File response with processed file
        """
        from starlette.responses import Response

        # Get report
        report_result = await report_service.get_report(uid)
        if report_result.is_error:
            return Response(
                content=f"Error: {report_result.error.user_message if report_result.error else 'Report not found'}",
                status_code=404,
                media_type="text/plain",
            )

        report = report_result.value
        if not report:
            return Response(
                content="Error: Report not found", status_code=404, media_type="text/plain"
            )

        if not report.processed_file_path:
            return Response(
                content="Error: No processed file available",
                status_code=404,
                media_type="text/plain",
            )

        # Get processed file content
        file_result = await report_service.get_processed_file_content(uid)
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

        processed_filename = f"processed_{report.original_filename}"

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

    @rt("/api/reports/statistics")
    @boundary_handler()
    async def get_statistics_route(request: Request, user_uid: str | None = None) -> Result[Any]:
        """
        Get report statistics for a user.

        Query parameters:
        - user_uid: User identifier (required)

        Returns:
        - Statistics by type and status
        """
        if not user_uid:
            return Result.fail(Errors.validation("user_uid is required", field="user_uid"))

        result = await report_service.get_report_statistics(user_uid)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(result.value)

    # ========================================================================
    # CONTENT MANAGEMENT ROUTES
    # ========================================================================

    if reports_core_service:

        @rt("/api/reports/categorize")
        @boundary_handler()
        async def categorize_report_route(
            request: Request, report_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Categorize a report.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - category: Category string
            """
            body = await request.json()
            req = CategorizeEntityRequest.model_validate(body)

            # Verify ownership through get_report
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.categorize_report(uid=report_uid, category=req.category)

        @rt("/api/reports/tags/add")
        @boundary_handler()
        async def add_tags_route(request: Request, report_uid: str, user_uid: str) -> Result[Any]:
            """
            Add tags to a report.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - tags: List of tag strings
            """
            body = await request.json()
            req = AddTagsRequest.model_validate(body)

            # Verify ownership
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.add_tags(uid=report_uid, tags=req.tags)

        @rt("/api/reports/tags/remove")
        @boundary_handler()
        async def remove_tags_route(
            request: Request, report_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Remove tags from a report.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID

            JSON body:
            - tags: List of tag strings to remove
            """
            body = await request.json()
            req = RemoveTagsRequest.model_validate(body)

            # Verify ownership
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.remove_tags(uid=report_uid, tags=req.tags)

        @rt("/api/reports/publish")
        @boundary_handler()
        async def publish_report_route(
            request: Request, report_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Publish a report.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.publish_report(uid=report_uid)

        @rt("/api/reports/archive")
        @boundary_handler()
        async def archive_report_route(
            request: Request, report_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Archive a report.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.archive_report(uid=report_uid)

        @rt("/api/reports/draft")
        @boundary_handler()
        async def mark_as_draft_route(
            request: Request, report_uid: str, user_uid: str
        ) -> Result[Any]:
            """
            Mark report as draft.

            Query parameters:
            - report_uid: Report UID
            - user_uid: User UID
            """
            # Verify ownership
            report_result = await report_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result.expect_error())

            report = report_result.value
            if report is None or report.user_uid != user_uid:
                return Result.fail(Errors.not_found(resource="Report", identifier=report_uid))

            return await reports_core_service.mark_as_draft(uid=report_uid)

        @rt("/api/reports/bulk/categorize")
        @boundary_handler()
        async def bulk_categorize_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk categorize reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - report_uids: List of report UIDs
            - category: Category string
            """
            body = await request.json()
            req = BulkCategorizeRequest.model_validate(body)

            # Verify user owns all reports
            for uid in req.ku_uids:
                report_result = await report_service.get_report(uid)
                if report_result.is_error:
                    return Result.fail(report_result.expect_error())

                report = report_result.value
                if report is None or report.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(f"You do not own report {uid}", field="report_uids")
                    )

            return await reports_core_service.bulk_categorize(
                uids=req.ku_uids, category=req.category
            )

        @rt("/api/reports/bulk/tag")
        @boundary_handler()
        async def bulk_tag_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk tag reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - report_uids: List of report UIDs
            - tags: List of tag strings
            """
            body = await request.json()
            req = BulkTagRequest.model_validate(body)

            # Verify ownership
            for uid in req.ku_uids:
                report_result = await report_service.get_report(uid)
                if report_result.is_error:
                    return Result.fail(report_result.expect_error())

                report = report_result.value
                if report is None or report.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(f"You do not own report {uid}", field="report_uids")
                    )

            return await reports_core_service.bulk_tag(uids=req.ku_uids, tags=req.tags)

        @rt("/api/reports/bulk/delete")
        @boundary_handler()
        async def bulk_delete_route(request: Request, user_uid: str) -> Result[Any]:
            """
            Bulk delete reports.

            Query parameters:
            - user_uid: User UID

            JSON body:
            - report_uids: List of report UIDs
            - soft_delete: Boolean (default True)
            """
            body = await request.json()
            req = BulkDeleteRequest.model_validate(body)

            # Verify ownership
            for uid in req.ku_uids:
                report_result = await report_service.get_report(uid)
                if report_result.is_error:
                    return Result.fail(report_result.expect_error())

                report = report_result.value
                if report is None or report.user_uid != user_uid:
                    return Result.fail(
                        Errors.validation(f"You do not own report {uid}", field="report_uids")
                    )

            return await reports_core_service.bulk_delete(
                uids=req.ku_uids, soft_delete=req.soft_delete
            )

        @rt("/api/reports/by-category")
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
            return await reports_core_service.get_reports_by_category(
                category=category, limit=limit, user_uid=user_uid
            )

        @rt("/api/reports/recent")
        @boundary_handler()
        async def get_recent_route(request: Request, user_uid: str, limit: int = 10) -> Result[Any]:
            """
            Get recent reports.

            Query parameters:
            - user_uid: User UID
            - limit: Max results (default 10)
            """
            return await reports_core_service.get_recent_reports(limit=limit, user_uid=user_uid)

        logger.info("Report content management routes registered (12 new routes)")

    logger.info("Reports API routes created successfully")

    return [
        upload_report_route,
        list_reports_route,
        get_report_route,
        process_report_route,
        download_original_file_route,
        download_processed_file_route,
        get_statistics_route,
    ]
