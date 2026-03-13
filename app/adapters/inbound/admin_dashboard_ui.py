"""
Admin Dashboard UI Routes
==========================

Routes for the admin dashboard UI at /admin.

All routes require ADMIN role and use the AdminLayout for consistent navigation.

Routes:
- GET /admin - Overview dashboard with key stats
- GET /admin/users - User management with list/table view
- GET /admin/users/{uid} - User detail view
- GET /admin/users/partial - HTMX partial for filtered user list
- GET /admin/users/{uid}/role-form - HTMX partial for role change form
- GET /admin/analytics - Analytics dashboard
- GET /admin/system - System health dashboard

Security:
- All routes require authentication (401 if not logged in)
- All routes require ADMIN role (403 if insufficient permissions)

Version: 1.0.0
Date: 2025-12-07
"""

from typing import Any

from fasthtml.common import H1, H2, H3, A, Div, P, Span

from adapters.inbound.auth import make_service_getter, require_admin
from core.utils.logging import get_logger
from ui.admin.layout import create_admin_page
from ui.admin.views import (
    AdminAnalyticsComponents,
    AdminLearningComponents,
    AdminSystemComponents,
    AdminUIComponents,
)
from ui.buttons import Button, ButtonT
from ui.cards import Card

logger = get_logger("skuel.routes.admin.ui")


def create_admin_dashboard_routes(_app, rt, services):
    """
    Create admin dashboard UI routes.

    All routes require ADMIN role.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        services: Service container with user_service, system_service
    """

    get_user_service = make_service_getter(services.user_service)

    # ========================================================================
    # OVERVIEW DASHBOARD
    # ========================================================================

    @rt("/admin")
    @require_admin(get_user_service)
    async def admin_overview(request, current_user):
        """
        Admin dashboard overview with key stats.

        Returns:
            Admin page with overview content
        """
        # Fetch system health
        system_status = await _get_system_status(services)

        content = Div(
            # Page header
            Div(
                H1("Admin Dashboard", cls="text-3xl font-bold"),
                P(
                    "System overview and management",
                    cls="text-muted-foreground mt-1",
                ),
                cls="mb-8",
            ),
            # Quick links
            Div(
                H2("Quick Actions", cls="text-xl font-semibold mb-4"),
                Div(
                    A(
                        Div(
                            Span("👥", cls="text-2xl"),
                            Span("Manage Users", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/users",
                        cls="bg-background shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("📈", cls="text-2xl"),
                            Span("View Analytics", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/analytics",
                        cls="bg-background shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("⚙️", cls="text-2xl"),
                            Span("System Health", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/system",
                        cls="bg-background shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("💰", cls="text-2xl"),
                            Span("Finance Dashboard", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/finance",
                        cls="bg-background shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("📥", cls="text-2xl"),
                            Span("Content Ingestion", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/ingest",
                        cls="bg-background shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                ),
                cls="mb-8",
            ),
            # System status summary
            Card(
                H2("System Status", cls="text-xl font-semibold mb-4"),
                _render_system_summary(system_status),
                cls="bg-background shadow-sm p-6",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="overview",
            admin_username=current_user.display_name or current_user.title,
            title="Admin Dashboard",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    @rt("/admin/users")
    @require_admin(get_user_service)
    async def admin_users_list(
        request,
        current_user,
        role: str | None = None,
        status: str | None = None,
    ):
        """
        User management page with list view.

        Query Parameters:
            role: Filter by role (admin, teacher, member, registered)
            status: Filter by status (active, inactive, all)

        Returns:
            Admin page with user list
        """
        # Parse filters
        role_filter_str = role if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users with activity counts
        users_result = await services.admin_stats.get_users_with_activity_counts(
            role_filter=role_filter_str,
            active_only=active_only,
        )
        users_data = users_result.value if not users_result.is_error else []

        # Fetch stats for header
        user_stats = await _get_user_stats(services)
        system_status = await _get_system_status(services)

        content = Div(
            # Page header
            Div(
                H1("User Management", cls="text-3xl font-bold"),
                P(
                    f"{user_stats.get('total', 0)} total users",
                    cls="text-muted-foreground mt-1",
                ),
                cls="mb-6",
            ),
            # Stats
            AdminUIComponents.render_user_stats(user_stats),
            # Filters
            Card(
                H3("Filters", cls="text-lg font-semibold mb-3"),
                Div(
                    AdminUIComponents.render_role_filter(role),
                    AdminUIComponents.render_status_filter(status),
                    cls="flex flex-wrap gap-4",
                ),
                cls="bg-background shadow-sm p-4 mb-6",
            ),
            # User table
            Card(
                H3("Users", cls="text-lg font-semibold mb-3"),
                Div(
                    AdminUIComponents.render_users_table(users_data),
                    id="user-list",
                ),
                cls="bg-background shadow-sm p-4",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="users",
            admin_username=current_user.display_name or current_user.title,
            title="User Management",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    @rt("/admin/users/partial")
    @require_admin(get_user_service)
    async def admin_users_partial(
        request,
        current_user,
        role: str | None = None,
        status: str | None = None,
    ):
        """
        HTMX partial for filtered user list.

        Returns just the user table HTML for HTMX swap.
        """
        # Parse filters
        role_filter_str = role if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users with activity counts
        users_result = await services.admin_stats.get_users_with_activity_counts(
            role_filter=role_filter_str,
            active_only=active_only,
        )
        users_data = users_result.value if not users_result.is_error else []

        return Div(
            AdminUIComponents.render_users_table(users_data),
            id="user-list",
        )

    @rt("/admin/users/{uid}")
    @require_admin(get_user_service)
    async def admin_user_detail(request, uid: str, current_user):
        """
        User detail view.

        Returns:
            Admin page with user details and role form
        """
        result = await services.user_service.get_user(uid)

        if result.is_error or not result.value:
            content = Div(
                H1("User Not Found", cls="text-3xl font-bold text-error"),
                P(f"No user found with UID: {uid}", cls="text-muted-foreground"),
                A("← Back to Users", href="/admin/users", cls="btn btn-ghost mt-4"),
            )
            return await create_admin_page(
                content=content,
                active_section="users",
                admin_username=current_user.display_name or current_user.title,
                title="User Not Found",
                request=request,
            )

        user = result.value
        user_data = {
            "uid": user.uid,
            "username": user.title,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else "Never",
        }

        system_status = await _get_system_status(services)

        # Fetch user activity stats
        detail_stats_result = await services.admin_stats.get_user_detail_stats(uid)
        detail_stats = detail_stats_result.value if not detail_stats_result.is_error else {}

        # Fetch user's reports
        reports_data: list = []
        try:
            if services.submissions_core:
                reports_result = await services.submissions_core.get_recent_submissions(
                    user_uid=uid, limit=20
                )
                if not reports_result.is_error and reports_result.value:
                    reports_data = reports_result.value
        except Exception as e:
            logger.warning(f"Failed to fetch reports for {uid}: {e}")

        # Fetch user's assignments
        projects_data: list = []
        try:
            if services.assignments:
                projects_result = await services.assignments.list_user_projects(
                    user_uid=uid, active_only=False
                )
                if not projects_result.is_error and projects_result.value:
                    projects_data = projects_result.value
        except Exception as e:
            logger.warning(f"Failed to fetch report projects for {uid}: {e}")

        content = Div(
            # Back button
            A("← Back to Users", href="/admin/users", cls="btn btn-ghost btn-sm mb-4"),
            # Page header
            Div(
                H1(user_data["display_name"] or user_data["username"], cls="text-3xl font-bold"),
                Div(
                    AdminUIComponents.render_role_badge(user_data["role"]),
                    AdminUIComponents.render_status_badge(user_data["is_active"]),
                    cls="flex gap-2 mt-2",
                ),
                cls="mb-6",
            ),
            # User details card
            Card(
                H2("User Details", cls="text-xl font-semibold mb-4"),
                Div(
                    _detail_row("UID", user_data["uid"]),
                    _detail_row("Username", f"@{user_data['username']}"),
                    _detail_row("Email", user_data["email"]),
                    _detail_row("Created", user_data["created_at"] or "Unknown"),
                    _detail_row("Last Login", user_data["last_login_at"]),
                    _detail_row("Verified", "Yes" if user_data["is_verified"] else "No"),
                    cls="space-y-3",
                ),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Activity, Learning & Session stats
            Card(
                H2("User Statistics", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_activity_stats(detail_stats, uid),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Reports section
            Card(
                H2("Reports", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_reports_list(reports_data, uid),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Report Projects section
            Card(
                H2("Report Projects", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_projects_list(projects_data, uid),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Role change section
            Card(
                H2("Change Role", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_role_change_form(user_data),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Actions
            Card(
                H2("Account Actions", cls="text-xl font-semibold mb-4"),
                Div(
                    Button(
                        "Deactivate Account" if user_data["is_active"] else "Activate Account",
                        cls=f"btn {'btn-error' if user_data['is_active'] else 'btn-success'}",
                        hx_post=f"/api/admin/users/{uid}/{'deactivate' if user_data['is_active'] else 'activate'}",
                        hx_confirm=f"Are you sure you want to {'deactivate' if user_data['is_active'] else 'activate'} this user?",
                    ),
                    cls="flex gap-4",
                ),
                cls="bg-background shadow-sm p-6",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="users",
            admin_username=current_user.display_name or current_user.title,
            title=f"User: {user_data['display_name'] or user_data['username']}",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    @rt("/admin/users/{uid}/role-form")
    @require_admin(get_user_service)
    async def admin_user_role_form(request, uid: str, current_user):
        """
        HTMX partial for role change form.

        Returns role change form HTML.
        """
        result = await services.user_service.get_user(uid)

        if result.is_error or not result.value:
            return Div(
                P("User not found", cls="text-error"),
            )

        user = result.value
        user_data = {
            "uid": user.uid,
            "role": user.role.value,
        }

        return AdminUIComponents.render_role_change_form(user_data)

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    @rt("/admin/analytics")
    @require_admin(get_user_service)
    async def admin_analytics(request, current_user):
        """
        Analytics dashboard with user and activity stats.

        Returns:
            Admin page with analytics content
        """
        # Fetch user stats
        user_stats = await _get_user_stats(services)
        system_status = await _get_system_status(services)

        # Initialize activity stats with None to detect missing services
        activity_stats = {
            "tasks_created": None,
            "habits_active": None,
            "goals_active": None,
            "journals_submitted": None,
        }

        try:
            if services.tasks:
                tasks_result = await services.tasks.list(user_uid=None, limit=10000)
                if not tasks_result.is_error:
                    activity_stats["tasks_created"] = len(tasks_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch task count: {tasks_result.expect_error().message}"
                    )

            if services.habits:
                habits_result = await services.habits.list(user_uid=None, limit=10000)
                if not habits_result.is_error:
                    activity_stats["habits_active"] = len(habits_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch habit count: {habits_result.expect_error().message}"
                    )

            if services.goals:
                goals_result = await services.goals.list(user_uid=None, limit=10000)
                if not goals_result.is_error:
                    activity_stats["goals_active"] = len(goals_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch goal count: {goals_result.expect_error().message}"
                    )

            if services.journals:
                journal_result = await services.journals.list(user_uid=None, limit=10000)
                if not journal_result.is_error:
                    activity_stats["journals_submitted"] = len(journal_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch journal count: {journal_result.expect_error().message}"
                    )

        except Exception as e:
            logger.error(f"Error fetching activity stats: {e}")
            # Leave as None values to show "N/A" in UI

        # Transform None to display-friendly values
        display_stats = {k: v if v is not None else "N/A" for k, v in activity_stats.items()}
        activity_stats = display_stats

        analytics_data = {
            "user_stats": user_stats,
            "activity_stats": activity_stats,
        }

        content = Div(
            # Page header
            Div(
                H1("Analytics", cls="text-3xl font-bold"),
                P(
                    "Platform usage and user statistics",
                    cls="text-muted-foreground mt-1",
                ),
                cls="mb-8",
            ),
            # Analytics dashboard
            AdminAnalyticsComponents.render_analytics_dashboard(analytics_data),
        )

        return await create_admin_page(
            content=content,
            active_section="analytics",
            admin_username=current_user.display_name or current_user.title,
            title="Analytics",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    # ========================================================================
    # SYSTEM HEALTH
    # ========================================================================

    @rt("/admin/system")
    @require_admin(get_user_service)
    async def admin_system(request, current_user):
        """
        System health dashboard.

        Returns:
            Admin page with system health content
        """
        # Fetch detailed health status
        health_data = {"status": "unknown", "components": {}}

        try:
            if services.system_service:
                result = await services.system_service.get_health_status()
                if not result.is_error:
                    health_data = result.value
                else:
                    logger.warning(
                        f"Failed to fetch system health: {result.expect_error().message}"
                    )
                    health_data = {
                        "status": "error",
                        "components": {},
                        "error_message": result.expect_error().message,
                    }
        except Exception as e:
            logger.error(f"Unexpected error fetching system health: {e}")
            health_data = {
                "status": "error",
                "components": {},
                "error_message": str(e),
            }

        content = Div(
            # Page header
            Div(
                H1("System Health", cls="text-3xl font-bold"),
                P(
                    "Monitor system components and services",
                    cls="text-muted-foreground mt-1",
                ),
                cls="mb-8",
            ),
            # Health dashboard
            AdminSystemComponents.render_health_dashboard(health_data),
            # Refresh button
            Div(
                Button(
                    "Refresh",
                    variant=ButtonT.outline,
                    hx_get="/admin/system",
                    hx_target="body",
                    hx_swap="outerHTML",
                ),
                cls="text-center mt-6",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="system",
            admin_username=current_user.display_name or current_user.title,
            title="System Health",
            system_status=health_data.get("status", "unknown"),
            request=request,
        )

    # ========================================================================
    # LEARNING DASHBOARD
    # ========================================================================

    @rt("/admin/learning")
    @require_admin(get_user_service)
    async def admin_learning(request, current_user):
        """
        Admin learning dashboard with KU progression tracking.

        Shows system-wide KU metrics and per-user progress table.
        """
        system_status = await _get_system_status(services)
        ku_metrics_result = await services.admin_stats.get_entity_system_metrics()
        ku_metrics = ku_metrics_result.value if not ku_metrics_result.is_error else {}
        user_progress_result = await services.admin_stats.get_all_users_progress()
        user_progress = user_progress_result.value if not user_progress_result.is_error else []

        content = Div(
            # Page header
            Div(
                H1("Learning Dashboard", cls="text-3xl font-bold"),
                P(
                    "Track knowledge unit progression across all users",
                    cls="text-muted-foreground mt-1",
                ),
                cls="mb-8",
            ),
            # System-wide KU metrics
            Card(
                H2("Knowledge Unit Overview", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_ku_system_metrics(ku_metrics),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # User progress table
            Card(
                H2("User KU Progress", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_progress_table(user_progress),
                cls="bg-background shadow-sm p-6",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="learning",
            admin_username=current_user.display_name or current_user.title,
            title="Learning Dashboard",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    @rt("/admin/learning/user/{uid}")
    @require_admin(get_user_service)
    async def admin_learning_user_detail(request, uid: str, current_user):
        """
        Detailed KU progress for a specific user.

        Shows viewed, in-progress, and mastered KUs with timestamps.
        """
        system_status = await _get_system_status(services)

        # Get user info
        user_result = await services.user_service.get_user(uid)
        if user_result.is_error or not user_result.value:
            content = Div(
                H1("User Not Found", cls="text-3xl font-bold text-error"),
                P(f"No user found with UID: {uid}", cls="text-muted-foreground"),
                A(
                    "← Back to Learning Dashboard",
                    href="/admin/learning",
                    cls="btn btn-ghost mt-4",
                ),
            )
            return await create_admin_page(
                content=content,
                active_section="learning",
                admin_username=current_user.display_name or current_user.title,
                title="User Not Found",
                request=request,
            )

        user = user_result.value
        user_ku_detail_result = await services.admin_stats.get_user_ku_detail(uid)
        user_ku_detail = user_ku_detail_result.value if not user_ku_detail_result.is_error else {}

        content = Div(
            # Back button
            A(
                "← Back to Learning Dashboard",
                href="/admin/learning",
                cls="btn btn-ghost btn-sm mb-4",
            ),
            # Page header
            Div(
                H1(
                    f"{user.display_name or user.title} — KU Progress",
                    cls="text-3xl font-bold",
                ),
                cls="mb-6",
            ),
            # Summary stats
            Card(
                H2("Progress Summary", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_summary(user_ku_detail),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Detailed KU list
            Card(
                H2("Knowledge Units", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_detail_list(user_ku_detail),
                cls="bg-background shadow-sm p-6",
            ),
        )

        return await create_admin_page(
            content=content,
            active_section="learning",
            admin_username=current_user.display_name or current_user.title,
            title=f"Learning: {user.display_name or user.title}",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    logger.info("Admin dashboard UI routes registered")
    logger.info("   - GET /admin - Overview dashboard")
    logger.info("   - GET /admin/users - User management")
    logger.info("   - GET /admin/users/{uid} - User detail")
    logger.info("   - GET /admin/analytics - Analytics")
    logger.info("   - GET /admin/learning - Learning dashboard")
    logger.info("   - GET /admin/learning/user/{uid} - User KU detail")
    logger.info("   - GET /admin/system - System health")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def _get_user_stats(services) -> dict:
    """Get user statistics for dashboard."""
    stats = {
        "total": 0,
        "admins": 0,
        "teachers": 0,
        "members": 0,
        "registered": 0,
    }

    try:
        # Get all users (admin-only, so this is fine)
        result = await services.user_service.list_users(
            admin_user_uid="system",  # System call for stats
            limit=10000,
            active_only=False,
        )

        if not result.is_error and result.value:
            users = result.value
            stats["total"] = len(users)

            for user in users:
                role = user.role.value.lower()
                if role in stats:
                    stats[role] += 1
    except Exception:
        pass

    return stats


async def _get_system_status(services) -> dict[str, Any]:
    """Get system health status."""
    try:
        if services.system_service:
            result = await services.system_service.get_health_status()
            if not result.is_error:
                return (
                    dict(result.value) if result.value else {"status": "unknown", "healthy": True}
                )
    except Exception as e:
        logger.warning(f"Failed to get system status: {e}")

    return {"status": "unknown", "healthy": True}


def _render_system_summary(status_data: dict) -> Div:
    """Render a simple system status summary."""
    status = status_data.get("status", "unknown")
    is_healthy = status_data.get("healthy", True)

    status_colors = {
        "healthy": "text-success",
        "warning": "text-warning",
        "critical": "text-error",
        "degraded": "text-warning",
        "unknown": "text-muted-foreground",
    }

    dot_colors = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
        "degraded": "bg-warning",
        "unknown": "bg-base-content/50",
    }

    return Div(
        Div(
            Span(
                cls=f"w-3 h-3 rounded-full {dot_colors.get(status, 'bg-base-content/50')} animate-pulse"
            ),
            Span(
                status.upper(),
                cls=f"font-semibold ml-2 {status_colors.get(status, 'text-muted-foreground')}",
            ),
            cls="flex items-center",
        ),
        P(
            "All systems operational" if is_healthy else "Some components need attention",
            cls="text-muted-foreground text-sm mt-2",
        ),
        A(
            "View Details →",
            href="/admin/system",
            cls="text-primary hover:underline text-sm mt-2 inline-block",
        ),
    )


def _detail_row(label: str, value: str) -> Div:
    """Render a detail row for user info."""
    return Div(
        Span(label, cls="text-muted-foreground w-32 inline-block"),
        Span(value, cls="font-medium"),
        cls="text-sm",
    )


# Export the route creation function
__all__ = ["create_admin_dashboard_routes"]
