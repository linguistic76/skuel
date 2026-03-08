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

Privacy Audit Route (authenticated user):
- GET  /api/privacy/audit — admin snapshots, shares granted, active schedule
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.feedback_protocols import (
        ActivityReportOperations,
        ProgressFeedbackOperations,
        ProgressScheduleOperations,
        ReviewQueueOperations,
    )
    from core.ports.infrastructure_protocols import UserOperations
    from core.ports.submission_protocols import SubmissionOperations
    from core.services.user.user_context_builder import UserContextBuilder

from starlette.requests import Request

from adapters.inbound.auth import require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import parse_int_query_param
from core.models.entity_converters import entity_to_response
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
    activity_report: "ActivityReportOperations | None" = None,
    review_queue: "ReviewQueueOperations | None" = None,
    user_service: "UserOperations | None" = None,
    context_builder: "UserContextBuilder | None" = None,
) -> list[Any]:
    """
    Create progress feedback, schedule, and activity review API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        progress_generator: ProgressFeedbackGenerator for on-demand generation
        report_service: SubmissionsService for listing feedback entities
        schedule_service: ProgressScheduleService for schedule CRUD
        activity_report: ActivityReportService for ActivityReport CRUD
        review_queue: ReviewQueueService for review request queue management
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
                "report": entity_to_response(result.value),
                "message": "Progress report generated successfully",
            }
        )

    @rt("/api/feedback/progress")
    @boundary_handler()
    async def list_progress_reports(request: Request) -> Result[Any]:
        """List user's progress reports."""
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(request.query_params, "limit", 20, minimum=1, maximum=500)

        result = await report_service.list_submissions(
            user_uid=user_uid,
            entity_type="activity_report",
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        return Result.ok(
            {
                "reports": [entity_to_response(r) for r in reports],
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

    # Named getter for require_admin (SKUEL012: no lambdas)
    def get_user_service() -> Any:
        """Return user_service for role-checking decorator."""
        return user_service

    if activity_report:

        @rt("/api/activity-review/snapshot")
        @require_admin(get_user_service)
        @boundary_handler()
        async def get_activity_snapshot(request: Request, current_user: Any) -> Result[Any]:
            """Generate activity snapshot for admin review.

            Admin-initiated path: admin selects a user + time window,
            system returns structured activity data for human assessment.

            SECURITY: Requires ADMIN role. subject_uid must be explicitly supplied —
            there is no default to the caller's own uid. See ADR-042.
            """
            subject_uid = request.query_params.get("subject_uid", "").strip()
            if not subject_uid:
                return Result.fail(
                    Errors.validation("subject_uid is required", field="subject_uid")
                )
            if not context_builder:
                return Result.fail(
                    Errors.system(
                        message="context_builder required for snapshots",
                        operation="get_activity_snapshot",
                    )
                )
            time_period = request.query_params.get("time_period", "7d")
            domains_param = request.query_params.get("domains", "")
            domains = [d.strip() for d in domains_param.split(",") if d.strip()] or None

            ctx_result = await context_builder.build_rich(subject_uid, window=time_period)
            if ctx_result.is_error:
                return Result.fail(ctx_result.expect_error())

            result = await activity_report.create_snapshot(
                context=ctx_result.value,
                time_period=time_period,
                domains=domains,
                admin_uid=current_user.uid,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"snapshot": result.value})

        @rt("/api/activity-review/submit", methods=["POST"])
        @require_admin(get_user_service)
        @boundary_handler(success_status=201)
        async def submit_activity_feedback(request: Request, current_user: Any) -> Result[Any]:
            """Admin submits written activity feedback.

            Creates ActivityReport entity with ProcessorType.HUMAN.

            SECURITY: Requires ADMIN role. See ADR-042.
            """
            admin_uid = current_user.uid
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

            result = await activity_report.submit_feedback(
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
                    "feedback": entity_to_response(result.value),
                    "message": "Activity feedback submitted successfully",
                }
            )

        @rt("/api/activity-review/history")
        @boundary_handler()
        async def get_activity_feedback_history(request: Request) -> Result[Any]:
            """User's received activity feedback (both LLM and human).

            SECURITY: Always scoped to the authenticated user's own history.
            subject_uid cannot be overridden via query params. See ADR-042.
            """
            user_uid = require_authenticated_user(request)
            limit = parse_int_query_param(request.query_params, "limit", 20, minimum=1, maximum=500)

            result = await activity_report.get_history(
                subject_uid=user_uid,
                limit=limit,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            feedbacks = result.value or []
            return Result.ok(
                {
                    "feedback": [entity_to_response(f) for f in feedbacks],
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

            result = await activity_report.annotate(
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

            result = await activity_report.get_annotation(uid=uid, user_uid=user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"annotation": result.value})

        @rt("/api/privacy/audit")
        @boundary_handler()
        async def get_privacy_audit(request: Request) -> Result[Any]:
            """Return privacy-transparency summary for the authenticated user.

            User-facing endpoint — always scoped to the requesting user's own data.
            No admin privileges required.

            Response includes:
                admin_snapshots  — admin-generated reviews of this user's activity
                                   (timestamps + admin uid so user can see who, when)
                shares_granted   — other users currently holding SHARES_WITH access
                                   to this user's entities (entity, role, when shared)
                report_schedule  — active automatic report schedule + last generated

            See: Privacy declaration in /docs/architecture/FEEDBACK_ARCHITECTURE.md
            See: ADR-042 (Privacy as First-Class Citizen)
            """
            user_uid = require_authenticated_user(request)
            result = await activity_report.get_privacy_summary(user_uid=user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())
            return Result.ok({"privacy_summary": result.value})

        routes.extend(
            [
                get_activity_snapshot,
                submit_activity_feedback,
                get_activity_feedback_history,
                save_annotation,
                get_annotation,
                get_privacy_audit,
            ]
        )
        logger.info("Activity report routes registered")

    if review_queue:

        @rt("/api/activity-review/request", methods=["POST"])
        @boundary_handler(success_status=201)
        async def request_activity_review(request: Request) -> Result[Any]:
            """User requests an activity review from an admin."""
            user_uid = require_authenticated_user(request)
            body = await request.json()

            time_period = body.get("time_period", "7d")
            domains = body.get("domains") or None
            message = body.get("message")

            result = await review_queue.request_review(
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
            limit = parse_int_query_param(request.query_params, "limit", 20, minimum=1, maximum=500)

            result = await review_queue.get_pending_reviews(
                _admin_uid=admin_uid,
                limit=limit,
            )
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"queue": result.value, "count": len(result.value or [])})

        routes.extend([request_activity_review, get_review_queue])
        logger.info("Review queue routes registered")

    logger.info("Feedback Progress API routes created successfully")
    return routes
