"""
Feedback Progress, Schedule & Activity Review API Routes
=========================================================

REST API for progress feedback generation, scheduling, and admin activity review.

Progress/Schedule Routes:
- POST /api/feedback/progress/generate — on-demand generation
- GET /api/feedback/progress — list user's activity feedback
- POST /api/feedback/schedule — create/update schedule
- GET /api/feedback/schedule — get user's schedule
- PUT /api/feedback/schedule/{uid} — update schedule
- DELETE /api/feedback/schedule/{uid} — deactivate schedule

Activity Review Routes (admin):
- GET  /api/activity-review/snapshot — generate activity snapshot for review
- POST /api/activity-review/submit — admin submits written feedback
- POST /api/activity-review/request — user requests a review
- GET  /api/activity-review/queue — admin's pending review queue
- GET  /api/activity-review/history — user's received activity feedback

Annotation Routes (authenticated user):
- POST /api/activity-reports/annotate — save annotation or revision to owned report
- GET  /api/activity-reports/annotation — get current annotation state
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.feedback_protocols import (
        ActivityReviewOperations,
        ProgressFeedbackOperations,
        ProgressScheduleOperations,
    )
    from core.ports.submission_protocols import SubmissionOperations

from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.entity_converters import ku_to_response
from core.models.entity_requests import (
    ProgressReportGenerateRequest,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.submissions.progress")


def create_progress_feedback_api_routes(
    _app: Any,
    rt: Any,
    progress_generator: "ProgressFeedbackOperations",
    report_service: "SubmissionOperations",
    schedule_service: "ProgressScheduleOperations | None" = None,
    activity_review: "ActivityReviewOperations | None" = None,
) -> list[Any]:
    """
    Create progress feedback, schedule, and activity review API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        progress_generator: ProgressFeedbackGenerator for on-demand generation
        report_service: SubmissionsService for listing feedback entities
        schedule_service: ProgressScheduleService for schedule CRUD
        activity_review: ActivityReviewService for admin human feedback
    """

    logger.info("Creating Reports Progress API routes")

    # ========================================================================
    # PROGRESS REPORT GENERATION
    # ========================================================================

    @rt("/api/feedback/progress/generate")
    @boundary_handler(success_status=201)
    async def generate_progress_report(request: Request) -> Result[Any]:
        """Generate a progress report on demand."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        req = ProgressReportGenerateRequest.model_validate(body)

        result = await progress_generator.generate(
            user_uid=user_uid,
            time_period=req.time_period,
            domains=req.domains if req.domains else None,
            depth=req.depth,
            include_insights=req.include_insights,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "report": ku_to_response(result.value),
                "message": "Progress report generated successfully",
            }
        )

    @rt("/api/feedback/progress")
    @boundary_handler()
    async def list_progress_reports(request: Request) -> Result[Any]:
        """List user's progress reports."""
        user_uid = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", "20"))

        result = await report_service.list_submissions(
            user_uid=user_uid,
            ku_type="activity_report",
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        return Result.ok(
            {
                "reports": [ku_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    # ========================================================================
    # SCHEDULE CRUD
    # ========================================================================

    routes = [generate_progress_report, list_progress_reports]

    if schedule_service:

        @rt("/api/feedback/schedule")
        @boundary_handler(success_status=201)
        async def create_schedule(request: Request) -> Result[Any]:
            """Create or update a report generation schedule."""
            user_uid = require_authenticated_user(request)
            body = await request.json()
            req = ScheduleCreateRequest.model_validate(body)

            result = await schedule_service.create_schedule(
                user_uid=user_uid,
                schedule_type=req.schedule_type,
                day_of_week=req.day_of_week,
                domains=req.domains,
                depth=req.depth,
            )

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "schedule": result.value,
                    "message": "Schedule created successfully",
                }
            )

        @rt("/api/feedback/schedule/get")
        @boundary_handler()
        async def get_schedule(request: Request) -> Result[Any]:
            """Get user's report schedule."""
            user_uid = require_authenticated_user(request)

            result = await schedule_service.get_user_schedule(user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"schedule": result.value})

        @rt("/api/feedback/schedule/update")
        @boundary_handler()
        async def update_schedule(request: Request, uid: str) -> Result[Any]:
            """Update a report schedule."""
            _user_uid = require_authenticated_user(request)
            body = await request.json()
            req = ScheduleUpdateRequest.model_validate(body)

            updates = {k: v for k, v in req.model_dump().items() if v is not None}
            result = await schedule_service.update_schedule(uid, updates)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "schedule": result.value,
                    "message": "Schedule updated",
                }
            )

        @rt("/api/feedback/schedule/delete")
        @boundary_handler()
        async def deactivate_schedule(request: Request, uid: str) -> Result[Any]:
            """Deactivate a report schedule."""
            _user_uid = require_authenticated_user(request)

            result = await schedule_service.deactivate_schedule(uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"message": "Schedule deactivated"})

        routes.extend([create_schedule, get_schedule, update_schedule, deactivate_schedule])
        logger.info("Report schedule routes registered")

    # ========================================================================
    # ACTIVITY REVIEW ROUTES (admin writes human feedback on Activity Domains)
    # ========================================================================

    if activity_review:

        @rt("/api/activity-review/snapshot")
        @boundary_handler()
        async def get_activity_snapshot(request: Request) -> Result[Any]:
            """Generate activity snapshot for admin review.

            Admin-initiated path: admin selects a user + time window,
            system returns structured activity data for human assessment.
            """
            user_uid = require_authenticated_user(request)
            subject_uid = request.query_params.get("subject_uid", user_uid)
            time_period = request.query_params.get("time_period", "7d")
            domains_param = request.query_params.get("domains", "")
            domains = [d.strip() for d in domains_param.split(",") if d.strip()] or None

            result = await activity_review.create_activity_snapshot(
                subject_uid=subject_uid,
                time_period=time_period,
                domains=domains,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"snapshot": result.value})

        @rt("/api/activity-review/submit", methods=["POST"])
        @boundary_handler(success_status=201)
        async def submit_activity_feedback(request: Request) -> Result[Any]:
            """Admin submits written activity feedback.

            Creates ActivityReport entity with ProcessorType.HUMAN.
            Requires ADMIN role.
            """
            admin_uid = require_authenticated_user(request)
            body = await request.json()

            subject_uid = body.get("subject_uid")
            feedback_text = body.get("feedback_text", "").strip()
            time_period = body.get("time_period", "7d")
            domains = body.get("domains") or None
            snapshot_context = body.get("snapshot_context")

            if not subject_uid:
                return Result.fail(
                    Errors.validation("subject_uid is required", field="subject_uid")
                )
            if not feedback_text:
                return Result.fail(
                    Errors.validation("feedback_text is required", field="feedback_text")
                )

            result = await activity_review.submit_activity_feedback(
                admin_uid=admin_uid,
                subject_uid=subject_uid,
                feedback_text=feedback_text,
                time_period=time_period,
                domains=domains,
                snapshot_context=snapshot_context,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "feedback": ku_to_response(result.value),
                    "message": "Activity feedback submitted successfully",
                }
            )

        @rt("/api/activity-review/request", methods=["POST"])
        @boundary_handler(success_status=201)
        async def request_activity_review(request: Request) -> Result[Any]:
            """User requests an activity review from an admin."""
            user_uid = require_authenticated_user(request)
            body = await request.json()

            time_period = body.get("time_period", "7d")
            domains = body.get("domains") or None
            message = body.get("message")

            result = await activity_review.request_review(
                user_uid=user_uid,
                time_period=time_period,
                domains=domains,
                message=message,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "request": result.value,
                    "message": "Review request submitted. An admin will be in touch.",
                }
            )

        @rt("/api/activity-review/queue")
        @boundary_handler()
        async def get_review_queue(request: Request) -> Result[Any]:
            """Admin's pending review queue."""
            admin_uid = require_authenticated_user(request)
            limit = int(request.query_params.get("limit", "20"))

            result = await activity_review.get_pending_reviews(
                admin_uid=admin_uid,
                limit=limit,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"queue": result.value, "count": len(result.value or [])})

        @rt("/api/activity-review/history")
        @boundary_handler()
        async def get_activity_feedback_history(request: Request) -> Result[Any]:
            """User's received activity feedback (both LLM and human)."""
            user_uid = require_authenticated_user(request)
            subject_uid = request.query_params.get("subject_uid", user_uid)
            limit = int(request.query_params.get("limit", "20"))

            result = await activity_review.get_activity_reviews_for_user(
                subject_uid=subject_uid,
                limit=limit,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            feedbacks = result.value or []
            return Result.ok(
                {
                    "feedback": [ku_to_response(f) for f in feedbacks],
                    "count": len(feedbacks),
                }
            )

        @rt("/api/activity-reports/annotate", methods=["POST"])
        @boundary_handler()
        async def save_annotation(request: Request) -> Result[Any]:
            """Save user annotation or revision to an owned ActivityReport.

            Body fields:
                uid: ActivityReport uid
                annotation_mode: "additive" | "revision"
                user_annotation: Commentary text (required for additive mode)
                user_revision: Replacement text (required for revision mode)
            """
            user_uid = require_authenticated_user(request)
            body = await request.json()

            uid = body.get("uid", "").strip()
            if not uid:
                return Result.fail(Errors.validation("uid is required", field="uid"))

            annotation_mode = body.get("annotation_mode", "").strip()
            user_annotation = body.get("user_annotation")
            user_revision = body.get("user_revision")

            result = await activity_review.annotate(
                uid=uid,
                user_uid=user_uid,
                annotation_mode=annotation_mode,
                user_annotation=user_annotation,
                user_revision=user_revision,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"annotation": result.value, "message": "Annotation saved"})

        @rt("/api/activity-reports/annotation")
        @boundary_handler()
        async def get_annotation(request: Request) -> Result[Any]:
            """Get current annotation state for an owned ActivityReport."""
            user_uid = require_authenticated_user(request)
            uid = request.query_params.get("uid", "").strip()
            if not uid:
                return Result.fail(Errors.validation("uid is required", field="uid"))

            result = await activity_review.get_annotation(uid=uid, user_uid=user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"annotation": result.value})

        routes.extend(
            [
                get_activity_snapshot,
                submit_activity_feedback,
                request_activity_review,
                get_review_queue,
                get_activity_feedback_history,
                save_annotation,
                get_annotation,
            ]
        )
        logger.info("Activity review routes registered")

    logger.info("Feedback Progress API routes created successfully")
    return routes
