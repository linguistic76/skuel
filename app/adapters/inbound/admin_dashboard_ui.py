"""
Admin Dashboard UI Routes
==========================

Routes for the admin dashboard UI at /admin.

All routes require ADMIN role and use the AdminLayout for consistent navigation.

Routes:
- GET /admin - Overview dashboard with key stats
- GET /admin/users - User management with list/table view
- GET /admin/users/{uid} - User detail view (account management only)
- GET /admin/users/partial - HTMX partial for filtered user list
- GET /admin/users/{uid}/role-form - HTMX partial for role change form
- GET /admin/analytics - Analytics dashboard
- GET /admin/system - System health dashboard

Note: KU progress is accessible per-student at /teaching/students/{uid}?tab=ku.

Security:
- All routes require authentication (401 if not logged in)
- All routes require ADMIN role (403 if insufficient permissions)

Version: 1.0.0
Date: 2025-12-07
"""

from typing import Any

from fasthtml.common import H2, H3, A, Div, P, Span

from adapters.inbound.auth import make_service_getter, require_admin
from core.utils.logging import get_logger
from ui.admin.layout import create_admin_page
from ui.admin.types import UserCardData
from ui.admin.views import (
    AdminAnalyticsComponents,
    AdminSystemComponents,
    AdminUIComponents,
)
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card
from ui.layout import Size
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader

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
        system_status, status_error = await _get_system_status(services)

        system_status_content = (
            render_error_banner("System status unavailable", severity="warning")
            if status_error
            else _render_system_summary(system_status)
        )

        content = Div(
            PageHeader("Admin Dashboard", subtitle="System overview and management"),
            # Quick links
            Div(
                SectionHeader("Quick Actions"),
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
                system_status_content,
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
        if users_result.is_error:
            logger.error(f"Failed to load users: {users_result.error}")
        users_data = users_result.value if not users_result.is_error else []

        # Fetch stats for header via efficient Cypher COUNT query
        user_stats_result = await services.admin_stats.get_user_role_counts()
        stats_error = user_stats_result.is_error
        user_stats = (
            user_stats_result.value
            if not stats_error
            else {
                "total": 0,
                "admins": 0,
                "teachers": 0,
                "members": 0,
                "registered": 0,
            }
        )
        system_status, _status_error = await _get_system_status(services)

        users_error_banner = (
            render_error_banner(
                "Failed to load user list", str(users_result.error), severity="warning"
            )
            if users_result.is_error
            else None
        )

        subtitle = (
            "User statistics unavailable"
            if stats_error
            else f"{user_stats.get('total', 0)} total users"
        )

        stats_content = (
            render_error_banner("User statistics unavailable", severity="warning")
            if stats_error
            else AdminUIComponents.render_user_stats(user_stats)
        )

        content = Div(
            PageHeader("User Management", subtitle=subtitle),
            # Stats
            stats_content,
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
            # Error banner (if user list failed)
            users_error_banner,
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
        if users_result.is_error:
            logger.error(f"Failed to load users: {users_result.error}")
            return Div(
                render_error_banner("Failed to load user list", str(users_result.error)),
                id="user-list",
            )
        users_data = users_result.value or []

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
                render_error_banner(f"No user found with UID: {uid}"),
                ButtonLink(
                    "← Back to Users", href="/admin/users", variant=ButtonT.ghost, cls="mt-4"
                ),
            )
            return await create_admin_page(
                content=content,
                active_section="users",
                admin_username=current_user.display_name or current_user.title,
                title="User Not Found",
                request=request,
            )

        user = result.value
        user_data = UserCardData(
            uid=user.uid,
            username=user.title,
            email=user.email,
            display_name=user.display_name or "",
            role=user.role.value,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at.isoformat() if user.created_at else None,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else "Never",
        )

        system_status, _status_error = await _get_system_status(services)

        # Fetch user activity stats
        detail_stats_result = await services.admin_stats.get_user_detail_stats(uid)
        detail_stats_error = detail_stats_result.is_error
        if detail_stats_error:
            logger.warning(f"Failed to load detail stats for {uid}: {detail_stats_result.error}")
        detail_stats = detail_stats_result.value if not detail_stats_error else {}

        content = Div(
            # Back button
            ButtonLink(
                "← Back to Users",
                href="/admin/users",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mb-4",
            ),
            PageHeader(
                user_data.display_name or user_data.username,
                actions=Div(
                    AdminUIComponents.render_role_badge(user_data.role),
                    AdminUIComponents.render_status_badge(user_data.is_active),
                    cls="flex gap-2",
                ),
            ),
            # User details card
            Card(
                H2("User Details", cls="text-xl font-semibold mb-4"),
                Div(
                    _detail_row("UID", user_data.uid),
                    _detail_row("Username", f"@{user_data.username}"),
                    _detail_row("Email", user_data.email),
                    _detail_row("Created", user_data.created_at or "Unknown"),
                    _detail_row("Last Login", user_data.last_login_at),
                    _detail_row("Verified", "Yes" if user_data.is_verified else "No"),
                    cls="space-y-3",
                ),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Activity & session stats
            Card(
                H2("User Statistics", cls="text-xl font-semibold mb-4"),
                render_error_banner("User statistics unavailable", severity="warning")
                if detail_stats_error
                else AdminUIComponents.render_user_activity_stats(detail_stats, uid),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Link to teaching view for submission/learning data
            Card(
                H2("Student Work", cls="text-xl font-semibold mb-4"),
                Div(
                    P(
                        "Submissions, reports, and learning progress are managed in the Teaching section.",
                        cls="text-muted-foreground text-sm mb-3",
                    ),
                    ButtonLink(
                        "View submissions →",
                        href=f"/teaching/students/{uid}",
                        variant=ButtonT.outline,
                        size=Size.sm,
                    ),
                    ButtonLink(
                        "KU progress →",
                        href=f"/teaching/students/{uid}?tab=ku",
                        variant=ButtonT.outline,
                        size=Size.sm,
                        cls="ml-2",
                    ),
                ),
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
                        "Deactivate Account" if user_data.is_active else "Activate Account",
                        variant=ButtonT.error if user_data.is_active else ButtonT.success,
                        hx_post=f"/api/admin/users/{uid}/{'deactivate' if user_data.is_active else 'activate'}",
                        hx_confirm=f"Are you sure you want to {'deactivate' if user_data.is_active else 'activate'} this user?",
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
            title=f"User: {user_data.display_name or user_data.username}",
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
        user_data = UserCardData(
            uid=user.uid,
            username=user.title,
            email=user.email or "",
            role=user.role.value,
            is_active=user.is_active,
        )

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
        # Fetch user stats via efficient Cypher COUNT query
        user_stats_result = await services.admin_stats.get_user_role_counts()
        _stats_error = user_stats_result.is_error
        user_stats = (
            user_stats_result.value
            if not _stats_error
            else {
                "total": 0,
                "admins": 0,
                "teachers": 0,
                "members": 0,
                "registered": 0,
            }
        )
        system_status, _status_error = await _get_system_status(services)

        # Fetch activity entity counts via efficient Cypher COUNT query
        activity_result = await services.admin_stats.get_activity_entity_counts()
        if activity_result.is_error:
            logger.error(f"Error fetching activity stats: {activity_result.error}")
            activity_stats: dict[str, Any] = {
                k: "N/A"
                for k in ("tasks_created", "habits_active", "goals_active", "journals_submitted")
            }
        else:
            activity_stats = activity_result.value

        analytics_data = {
            "user_stats": user_stats,
            "activity_stats": activity_stats,
        }

        content = Div(
            PageHeader("Analytics", subtitle="Platform usage and user statistics"),
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
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Unexpected error fetching system health: {e}")
            health_data = {
                "status": "error",
                "components": {},
                "error_message": str(e),
            }

        content = Div(
            PageHeader("System Health", subtitle="Monitor system components and services"),
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

    logger.info("Admin dashboard UI routes registered")
    logger.info("   - GET /admin - Overview dashboard")
    logger.info("   - GET /admin/users - User management")
    logger.info("   - GET /admin/users/{uid} - User detail")
    logger.info("   - GET /admin/analytics - Analytics")
    logger.info("   - GET /admin/system - System health")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def _get_system_status(services) -> tuple[dict[str, Any], bool]:
    """Get system health status. Returns (status_dict, had_error)."""
    try:
        if services.system_service:
            result = await services.system_service.get_health_status()
            if not result.is_error:
                status = (
                    dict(result.value) if result.value else {"status": "unknown", "healthy": True}
                )
                return status, False
            return {"status": "unknown", "healthy": True}, True
    except Exception as e:  # safety-net: dashboard degrades gracefully on health check failure
        logger.warning(f"Failed to get system status: {e}")

    return {"status": "unknown", "healthy": True}, True


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
        "unknown": "bg-muted-foreground",
    }

    return Div(
        Div(
            Span(
                cls=f"w-3 h-3 rounded-full {dot_colors.get(status, 'bg-muted-foreground')} animate-pulse"
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
