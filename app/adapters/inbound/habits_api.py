"""
Habits API - Status, Analytics, and Domain-Specific Routes
============================================================

CRUD, Query, and Intelligence factories are now registered via config in
habits_routes.py.  This file contains only factories and routes that require
runtime closures or domain-specific handler logic:
- StatusRouteFactory (pause/resume/archive with request_builder closures)
- AnalyticsRouteFactory (custom async handlers)
- Manual domain routes (track, reminders, categories, search)
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user, require_ownership_query
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import (
    StatusRouteFactory,
    StatusTransition,
)
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.models.habit.habit_request import (
    ArchiveHabitRequest,
    PauseHabitRequest,
    ResumeHabitRequest,
    TrackHabitRequest,
    UntrackHabitRequest,
)
from core.services.protocols.facade_protocols import HabitsFacadeProtocol
from core.utils.result_simplified import Result

# ============================================================================
# REQUEST BUILDERS (SKUEL012 compliance - no lambda expressions)
# ============================================================================


def build_pause_habit_request(uid: str, fields: dict[str, Any]) -> PauseHabitRequest:
    """Build a PauseHabitRequest from UID and form fields."""
    return PauseHabitRequest(
        habit_uid=uid,
        reason=fields.get("reason", "Paused"),
        until_date=fields.get("until_date"),
    )


def build_resume_habit_request(uid: str, fields: dict[str, Any]) -> ResumeHabitRequest:
    """Build a ResumeHabitRequest from UID and form fields."""
    return ResumeHabitRequest(habit_uid=uid)


def build_archive_habit_request(uid: str, fields: dict[str, Any]) -> ArchiveHabitRequest:
    """Build an ArchiveHabitRequest from UID and form fields."""
    return ArchiveHabitRequest(
        habit_uid=uid,
        reason=fields.get("reason", "Archived"),
    )


def create_habits_api_routes(
    app: Any,
    rt: Any,
    habits_service: HabitsFacadeProtocol,
    **_kwargs: Any,
) -> list[Any]:
    """
    Create habit API routes that require runtime closures or domain-specific logic.

    CRUD, Query, and Intelligence routes are registered by register_domain_routes
    before this function is called (see habits_routes.py → HABITS_CONFIG).

    Args:
        app: FastHTML application instance
        rt: Route decorator
        habits_service: HabitsService instance (primary service)
        **_kwargs: Absorbs related services passed by register_domain_routes
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_habits_service():
        return habits_service

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================
    # SECURITY: All UID-based routes verify user owns the habit before operating

    # Habit Tracking Operations
    # -------------------------

    @rt("/api/habits/track")
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def track_habit_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Track a habit completion (requires ownership)."""
        body = await request.json()
        typed_request = TrackHabitRequest(
            habit_uid=entity.uid,
            completion_date=body.get("date"),
            value=body.get("value", 1),
            notes=body.get("notes", ""),
        )
        return await habits_service.track_habit(typed_request)

    @rt("/api/habits/untrack")
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def untrack_habit_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Remove a habit tracking entry (requires ownership)."""
        body = await request.json()
        typed_request = UntrackHabitRequest(
            habit_uid=entity.uid,
            completion_date=body.get("date"),
        )
        return await habits_service.untrack_habit(typed_request)

    @rt("/api/habits/streak")
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def get_habit_streak_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Get current streak for a habit (requires ownership)."""
        return await habits_service.get_habit_streak(entity.uid)

    @rt("/api/habits/progress")
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def get_habit_progress_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Get progress statistics for a habit (requires ownership)."""
        params = dict(request.query_params)
        period = params.get("period", "month")  # week, month, year

        return await habits_service.get_habit_progress(entity.uid, period)

    # ========================================================================
    # STATUS ROUTES (Factory-Generated)
    # ========================================================================
    # BEFORE: 3 manual routes (~35 lines) with NO ownership verification
    # AFTER: 1 factory config with AUTOMATIC ownership verification
    # Uses request_builder to construct typed request objects

    status_factory = StatusRouteFactory(
        service=habits_service,
        domain_name="habits",
        transitions={
            "pause": StatusTransition(
                target_status="paused",
                requires_body=True,
                body_fields=["reason", "until_date"],
                request_builder=build_pause_habit_request,
                method_name="pause_habit",
            ),
            "resume": StatusTransition(
                target_status="active",
                request_builder=build_resume_habit_request,
                method_name="resume_habit",
            ),
            "archive": StatusTransition(
                target_status="archived",
                requires_body=True,
                body_fields=["reason"],
                request_builder=build_archive_habit_request,
                method_name="archive_habit",
            ),
        },
        scope=ContentScope.USER_OWNED,
    )
    status_factory.register_routes(app, rt)

    # Habit Categories and Organization
    # ----------------------------------

    @rt("/api/habits/categories")
    @boundary_handler()
    async def list_habit_categories_route(request: Request) -> Result[Any]:
        """List habit categories for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await habits_service.list_habit_categories(user_uid)

    @rt("/api/habits/by-category")
    @boundary_handler()
    async def get_habits_by_category_route(request: Request, category: str) -> Result[Any]:
        """Get habits in a specific category."""
        params = dict(request.query_params)

        limit = int(params.get("limit", 100))

        return await habits_service.get_habits_by_category(category, limit)

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    # Analytics handler functions
    # NOTE: handle_habit_analytics removed - /api/habits/analytics now via IntelligenceRouteFactory

    async def handle_summary_analytics(service, params):
        """Handle summary analytics for all habits."""
        period = params.get("period", "month")
        return await service.get_habits_summary_analytics(period)

    async def handle_habit_trends(service, params):
        """Handle habit completion trends."""
        time_range = params.get("time_range", "30d")
        return await service.get_habit_trends(time_range)

    # Create analytics factory for domain-specific analytics
    # NOTE: /api/habits/analytics is now generated by IntelligenceRouteFactory
    analytics_factory = AnalyticsRouteFactory(
        service=habits_service,
        domain_name="habits",
        analytics_config={
            "summary": {
                "path": "/api/habits/analytics/summary",
                "handler": handle_summary_analytics,
                "description": "Get summary analytics for all habits",
                "methods": ["GET"],
            },
            "trends": {
                "path": "/api/habits/analytics/trends",
                "handler": handle_habit_trends,
                "description": "Get habit completion trends and patterns",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    # Habit Search and Filtering
    # ---------------------------

    @rt("/api/habits/search")
    @boundary_handler()
    async def search_habits_route(request: Request) -> Result[Any]:
        """Search habits by name or description."""
        params = dict(request.query_params)

        query = params.get("q", "")
        limit = int(params.get("limit", 50))

        return await habits_service.search_habits(query, limit)

    @rt("/api/habits/due-today")
    @boundary_handler()
    async def get_habits_due_today_route(request: Request) -> Result[Any]:
        """Get habits due today for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await habits_service.get_habits_due_today(user_uid)

    @rt("/api/habits/overdue")
    @boundary_handler()
    async def get_overdue_habits_route(request: Request) -> Result[Any]:
        """Get overdue habits."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))

        return await habits_service.get_overdue_habits(limit)

    # Habit Reminders
    # ---------------
    # SECURITY: All routes verify user owns the habit before operating

    @rt("/api/habits/reminders", methods=["POST"])
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def set_habit_reminder_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Set a reminder for a habit (requires ownership)."""
        body = await request.json()
        # Use facade protocol signature: (habit_uid, reminder_data)
        reminder_data = {
            "reminder_time": body.get("time", ""),
            "days": body.get("days", []),
            "enabled": body.get("enabled", True),
        }
        return await habits_service.set_habit_reminder(
            habit_uid=entity.uid, reminder_data=reminder_data
        )

    @rt("/api/habits/reminders", methods=["GET"])
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def get_habit_reminders_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get reminders for a habit (requires ownership)."""
        return await habits_service.get_habit_reminders(entity.uid)

    @rt("/api/habits/reminders", methods=["DELETE"])
    @require_ownership_query(get_habits_service)
    @boundary_handler()
    async def delete_habit_reminder_route(
        request: Request, user_uid: str, entity: Any, reminder_id: str
    ) -> Result[Any]:
        """Delete a habit reminder (requires ownership)."""
        # Use facade protocol signature: (habit_uid, reminder_uid)
        return await habits_service.delete_habit_reminder(
            habit_uid=entity.uid,
            reminder_uid=reminder_id,
        )

    return []  # Routes registered via @rt() decorators (no objects returned)
