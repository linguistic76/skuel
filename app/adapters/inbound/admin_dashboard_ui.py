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

from core.ui.daisy_components import Button, ButtonT

from components.admin_components import (
    AdminAnalyticsComponents,
    AdminSystemComponents,
    AdminUIComponents,
)
from core.auth import require_admin
from core.models.enums import UserRole
from core.utils.logging import get_logger
from ui.admin.layout import create_admin_page

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

    # Named function to replace lambda (SKUEL012 compliance)
    def get_user_service():
        """Get user service from services container (deferred access)."""
        return services.user_service

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
        # Fetch user stats
        user_stats = await _get_user_stats(services)

        # Fetch system health
        system_status = await _get_system_status(services)

        content = Div(
            # Page header
            Div(
                H1("Admin Dashboard", cls="text-3xl font-bold"),
                P(
                    "System overview and management",
                    cls="text-base-content/50 mt-1",
                ),
                cls="mb-8",
            ),
            # Stats cards
            Div(
                H2("User Overview", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_stats(user_stats),
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
                        cls="card bg-base-100 shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("📈", cls="text-2xl"),
                            Span("View Analytics", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/analytics",
                        cls="card bg-base-100 shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("⚙️", cls="text-2xl"),
                            Span("System Health", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/system",
                        cls="card bg-base-100 shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    A(
                        Div(
                            Span("💰", cls="text-2xl"),
                            Span("Finance Dashboard", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/finance",
                        cls="card bg-base-100 shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4",
                ),
                cls="mb-8",
            ),
            # System status summary
            Div(
                H2("System Status", cls="text-xl font-semibold mb-4"),
                _render_system_summary(system_status),
                cls="card bg-base-100 shadow-sm p-6",
            ),
        )

        return create_admin_page(
            content=content,
            active_section="overview",
            admin_username=current_user.display_name or current_user.title,
            title="Admin Dashboard",
            system_status=system_status.get("status", "unknown"),
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
        role_filter = UserRole.from_string(role) if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users
        result = await services.user_service.list_users(
            admin_user_uid=current_user.uid,
            limit=100,
            role_filter=role_filter,
            active_only=active_only,
        )

        users_data = []
        if not result.is_error and result.value:
            users_data = [
                {
                    "uid": u.uid,
                    "username": u.title,
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": u.role.value,
                    "is_active": u.is_active,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else "Never",
                }
                for u in result.value
            ]

        # Fetch stats for header
        user_stats = await _get_user_stats(services)
        system_status = await _get_system_status(services)

        content = Div(
            # Page header
            Div(
                H1("User Management", cls="text-3xl font-bold"),
                P(
                    f"{user_stats.get('total', 0)} total users",
                    cls="text-base-content/50 mt-1",
                ),
                cls="mb-6",
            ),
            # Stats
            AdminUIComponents.render_user_stats(user_stats),
            # Filters
            Div(
                H3("Filters", cls="text-lg font-semibold mb-3"),
                Div(
                    AdminUIComponents.render_role_filter(role),
                    AdminUIComponents.render_status_filter(status),
                    cls="flex flex-wrap gap-4",
                ),
                cls="card bg-base-100 shadow-sm p-4 mb-6",
            ),
            # User list
            Div(
                H3("Users", cls="text-lg font-semibold mb-3"),
                Div(
                    *[AdminUIComponents.render_user_card(user) for user in users_data],
                    id="user-list",
                    cls="space-y-4",
                )
                if users_data
                else P("No users found", cls="text-base-content/50 py-4"),
                cls="card bg-base-100 shadow-sm p-4",
            ),
        )

        return create_admin_page(
            content=content,
            active_section="users",
            admin_username=current_user.display_name or current_user.title,
            title="User Management",
            system_status=system_status.get("status", "unknown"),
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

        Returns just the user list HTML for HTMX swap.
        """
        # Parse filters
        role_filter = UserRole.from_string(role) if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users
        result = await services.user_service.list_users(
            admin_user_uid=current_user.uid,
            limit=100,
            role_filter=role_filter,
            active_only=active_only,
        )

        users_data = []
        if not result.is_error and result.value:
            users_data = [
                {
                    "uid": u.uid,
                    "username": u.title,
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": u.role.value,
                    "is_active": u.is_active,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else "Never",
                }
                for u in result.value
            ]

        if not users_data:
            return Div(
                P("No users found matching filters", cls="text-base-content/50 py-4"),
                id="user-list",
            )

        return Div(
            *[AdminUIComponents.render_user_card(user) for user in users_data],
            id="user-list",
            cls="space-y-4",
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
                P(f"No user found with UID: {uid}", cls="text-base-content/50"),
                A("← Back to Users", href="/admin/users", cls="btn btn-ghost mt-4"),
            )
            return create_admin_page(
                content=content,
                active_section="users",
                admin_username=current_user.display_name or current_user.title,
                title="User Not Found",
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
            Div(
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
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Role change section
            Div(
                H2("Change Role", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_role_change_form(user_data),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Actions
            Div(
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
                cls="card bg-base-100 shadow-sm p-6",
            ),
        )

        return create_admin_page(
            content=content,
            active_section="users",
            admin_username=current_user.display_name or current_user.title,
            title=f"User: {user_data['display_name'] or user_data['username']}",
            system_status=system_status.get("status", "unknown"),
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

        # Fetch real counts from services (no hasattr - use getattr with default)
        try:
            tasks_service = getattr(services, "tasks", None)
            if tasks_service:
                # Use list with limit as count method may not exist
                tasks_result = await tasks_service.list(user_uid=None, limit=10000)
                if not tasks_result.is_error:
                    activity_stats["tasks_created"] = len(tasks_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch task count: {tasks_result.expect_error().message}"
                    )

            habits_service = getattr(services, "habits", None)
            if habits_service:
                habits_result = await habits_service.list(user_uid=None, limit=10000)
                if not habits_result.is_error:
                    activity_stats["habits_active"] = len(habits_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch habit count: {habits_result.expect_error().message}"
                    )

            goals_service = getattr(services, "goals", None)
            if goals_service:
                goals_result = await goals_service.list(user_uid=None, limit=10000)
                if not goals_result.is_error:
                    activity_stats["goals_active"] = len(goals_result.value or [])
                else:
                    logger.warning(
                        f"Failed to fetch goal count: {goals_result.expect_error().message}"
                    )

            # Journals service
            journals_service = getattr(services, "journals", None)
            if journals_service:
                journal_result = await journals_service.list(user_uid=None, limit=10000)
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
                    cls="text-base-content/50 mt-1",
                ),
                cls="mb-8",
            ),
            # Analytics dashboard
            AdminAnalyticsComponents.render_analytics_dashboard(analytics_data),
        )

        return create_admin_page(
            content=content,
            active_section="analytics",
            admin_username=current_user.display_name or current_user.title,
            title="Analytics",
            system_status=system_status.get("status", "unknown"),
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
            system_service = getattr(services, "system_service", None)
            if system_service:
                result = await system_service.get_health_status()
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
                    cls="text-base-content/50 mt-1",
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

        return create_admin_page(
            content=content,
            active_section="system",
            admin_username=current_user.display_name or current_user.title,
            title="System Health",
            system_status=health_data.get("status", "unknown"),
        )

    logger.info("Admin dashboard UI routes registered")
    logger.info("   - GET /admin - Overview dashboard")
    logger.info("   - GET /admin/users - User management")
    logger.info("   - GET /admin/users/{uid} - User detail")
    logger.info("   - GET /admin/analytics - Analytics")
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
        system_service = getattr(services, "system_service", None)
        if system_service:
            result = await system_service.get_health_status()
            if not result.is_error:
                # result.value is typed as Any; cast to dict for return
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
        "unknown": "text-base-content/70",
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
                cls=f"font-semibold ml-2 {status_colors.get(status, 'text-base-content/70')}",
            ),
            cls="flex items-center",
        ),
        P(
            "All systems operational" if is_healthy else "Some components need attention",
            cls="text-base-content/50 text-sm mt-2",
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
        Span(label, cls="text-base-content/50 w-32 inline-block"),
        Span(value, cls="font-medium"),
        cls="text-sm",
    )


# Export the route creation function
__all__ = ["create_admin_dashboard_routes"]
