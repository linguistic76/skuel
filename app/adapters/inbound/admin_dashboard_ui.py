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

from components.admin_components import (
    AdminAnalyticsComponents,
    AdminLearningComponents,
    AdminSystemComponents,
    AdminUIComponents,
)
from core.auth import require_admin
from core.ui.daisy_components import Button, ButtonT
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
                    A(
                        Div(
                            Span("📥", cls="text-2xl"),
                            Span("Content Ingestion", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/ingest",
                        cls="card bg-base-100 shadow-sm p-4 hover:shadow-md transition-shadow",
                    ),
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
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
        role_filter_str = role if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users with activity counts
        users_data = await _get_users_with_activity_counts(
            services,
            role_filter=role_filter_str,
            active_only=active_only,
        )

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
            # User table
            Div(
                H3("Users", cls="text-lg font-semibold mb-3"),
                Div(
                    AdminUIComponents.render_users_table(users_data),
                    id="user-list",
                ),
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

        Returns just the user table HTML for HTMX swap.
        """
        # Parse filters
        role_filter_str = role if role and role != "all" else None
        active_only = status != "inactive" if status else True
        if status == "all":
            active_only = False

        # Fetch users with activity counts
        users_data = await _get_users_with_activity_counts(
            services,
            role_filter=role_filter_str,
            active_only=active_only,
        )

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

        # Fetch user activity stats
        detail_stats = await _get_user_detail_stats(services, uid)

        # Fetch user's reports
        reports_data: list = []
        try:
            if services.reports_core:
                reports_result = await services.reports_core.get_recent_reports(
                    user_uid=uid, limit=20
                )
                if not reports_result.is_error and reports_result.value:
                    reports_data = reports_result.value
        except Exception as e:
            logger.warning(f"Failed to fetch reports for {uid}: {e}")

        # Fetch user's report projects
        projects_data: list = []
        try:
            if services.report_projects:
                projects_result = await services.report_projects.list_user_projects(
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
            # Activity, Learning & Session stats
            Div(
                H2("User Statistics", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_activity_stats(detail_stats, uid),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Reports section
            Div(
                H2("Reports", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_reports_list(reports_data, uid),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Report Projects section
            Div(
                H2("Report Projects", cls="text-xl font-semibold mb-4"),
                AdminUIComponents.render_user_projects_list(projects_data, uid),
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
        ku_metrics = await _get_ku_system_metrics(services)
        user_progress = await _get_all_users_ku_progress(services)

        content = Div(
            # Page header
            Div(
                H1("Learning Dashboard", cls="text-3xl font-bold"),
                P(
                    "Track knowledge unit progression across all users",
                    cls="text-base-content/50 mt-1",
                ),
                cls="mb-8",
            ),
            # System-wide KU metrics
            Div(
                H2("Knowledge Unit Overview", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_ku_system_metrics(ku_metrics),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # User progress table
            Div(
                H2("User KU Progress", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_progress_table(user_progress),
                cls="card bg-base-100 shadow-sm p-6",
            ),
        )

        return create_admin_page(
            content=content,
            active_section="learning",
            admin_username=current_user.display_name or current_user.title,
            title="Learning Dashboard",
            system_status=system_status.get("status", "unknown"),
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
                P(f"No user found with UID: {uid}", cls="text-base-content/50"),
                A(
                    "← Back to Learning Dashboard",
                    href="/admin/learning",
                    cls="btn btn-ghost mt-4",
                ),
            )
            return create_admin_page(
                content=content,
                active_section="learning",
                admin_username=current_user.display_name or current_user.title,
                title="User Not Found",
            )

        user = user_result.value
        user_ku_detail = await _get_user_ku_detail(services, uid)

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
            Div(
                H2("Progress Summary", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_summary(user_ku_detail),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Detailed KU list
            Div(
                H2("Knowledge Units", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_detail_list(user_ku_detail),
                cls="card bg-base-100 shadow-sm p-6",
            ),
        )

        return create_admin_page(
            content=content,
            active_section="learning",
            admin_username=current_user.display_name or current_user.title,
            title=f"Learning: {user.display_name or user.title}",
            system_status=system_status.get("status", "unknown"),
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


# ============================================================================
# LEARNING DASHBOARD HELPERS
# ============================================================================


async def _get_ku_system_metrics(services) -> dict:
    """Get system-wide KU metrics via Cypher."""
    metrics = {
        "total_kus": 0,
        "total_viewed": 0,
        "total_in_progress": 0,
        "total_mastered": 0,
        "total_bookmarked": 0,
        "users_with_progress": 0,
    }

    if not services.neo4j_driver:
        return metrics

    try:
        records, _, _ = await services.neo4j_driver.execute_query(
            """
            OPTIONAL MATCH (ku:Ku)
            WITH count(DISTINCT ku) AS total_kus
            OPTIONAL MATCH (:User)-[v:VIEWED]->(:Ku)
            WITH total_kus, count(v) AS total_viewed
            OPTIONAL MATCH (:User)-[:IN_PROGRESS]->(:Ku)
            WITH total_kus, total_viewed, count(*) AS total_in_progress
            OPTIONAL MATCH (:User)-[:MASTERED]->(:Ku)
            WITH total_kus, total_viewed, total_in_progress, count(*) AS total_mastered
            OPTIONAL MATCH (:User)-[:BOOKMARKED]->(:Ku)
            WITH total_kus, total_viewed, total_in_progress, total_mastered, count(*) AS total_bookmarked
            OPTIONAL MATCH (u:User)
                WHERE EXISTS { (u)-[:VIEWED|IN_PROGRESS|MASTERED|BOOKMARKED]->(:Ku) }
            RETURN total_kus, total_viewed, total_in_progress, total_mastered, total_bookmarked,
                   count(DISTINCT u) AS users_with_progress
            """
        )

        if records:
            r = records[0]
            metrics["total_kus"] = r["total_kus"] or 0
            metrics["total_viewed"] = r["total_viewed"] or 0
            metrics["total_in_progress"] = r["total_in_progress"] or 0
            metrics["total_mastered"] = r["total_mastered"] or 0
            metrics["total_bookmarked"] = r["total_bookmarked"] or 0
            metrics["users_with_progress"] = r["users_with_progress"] or 0
    except Exception as e:
        logger.warning(f"Failed to get KU system metrics: {e}")

    return metrics


async def _get_all_users_ku_progress(services) -> list[dict]:
    """Get KU progress summary for all users."""
    if not services.neo4j_driver:
        return []

    try:
        records, _, _ = await services.neo4j_driver.execute_query(
            """
            MATCH (u:User)
            WHERE u.uid <> 'user_system'
            OPTIONAL MATCH (u)-[:VIEWED]->(ku1:Ku)
            WITH u, count(DISTINCT ku1) AS viewed_count
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(ku2:Ku)
            WITH u, viewed_count, count(DISTINCT ku2) AS in_progress_count
            OPTIONAL MATCH (u)-[:MASTERED]->(ku3:Ku)
            WITH u, viewed_count, in_progress_count, count(DISTINCT ku3) AS mastered_count
            OPTIONAL MATCH (u)-[:BOOKMARKED]->(ku4:Ku)
            WITH u, viewed_count, in_progress_count, mastered_count, count(DISTINCT ku4) AS bookmarked_count
            RETURN u.uid AS uid,
                   u.display_name AS display_name,
                   u.title AS username,
                   u.role AS role,
                   viewed_count,
                   in_progress_count,
                   mastered_count,
                   bookmarked_count,
                   (viewed_count + in_progress_count + mastered_count) AS total_interactions
            ORDER BY total_interactions DESC
            """
        )

        return [dict(r) for r in records]
    except Exception as e:
        logger.warning(f"Failed to get user KU progress: {e}")
        return []


async def _get_user_ku_detail(services, user_uid: str) -> dict:
    """Get detailed KU progress for a specific user."""
    detail: dict = {
        "viewed": [],
        "in_progress": [],
        "mastered": [],
        "bookmarked": [],
        "summary": {
            "viewed_count": 0,
            "in_progress_count": 0,
            "mastered_count": 0,
            "bookmarked_count": 0,
        },
    }

    if not services.neo4j_driver:
        return detail

    try:
        records, _, _ = await services.neo4j_driver.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[v:VIEWED]->(vku:Ku)
            WITH u, collect(DISTINCT {
                uid: vku.uid, title: vku.title,
                view_count: v.view_count,
                first_viewed_at: toString(v.first_viewed_at),
                last_viewed_at: toString(v.last_viewed_at)
            }) AS viewed_kus

            OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(pku:Ku)
            WITH u, viewed_kus, collect(DISTINCT {
                uid: pku.uid, title: pku.title,
                started_at: toString(p.started_at),
                progress_score: p.progress_score
            }) AS progress_kus

            OPTIONAL MATCH (u)-[m:MASTERED]->(mku:Ku)
            WITH u, viewed_kus, progress_kus, collect(DISTINCT {
                uid: mku.uid, title: mku.title,
                mastered_at: toString(m.mastered_at),
                mastery_score: m.mastery_score,
                method: m.method
            }) AS mastered_kus

            OPTIONAL MATCH (u)-[b:BOOKMARKED]->(bku:Ku)
            WITH viewed_kus, progress_kus, mastered_kus, collect(DISTINCT {
                uid: bku.uid, title: bku.title,
                bookmarked_at: toString(b.bookmarked_at)
            }) AS bookmarked_kus

            RETURN viewed_kus, progress_kus, mastered_kus, bookmarked_kus
            """,
            user_uid=user_uid,
        )

        if records:
            r = records[0]
            # Filter out entries with null uid (from OPTIONAL MATCH with no results)
            viewed = [ku for ku in r["viewed_kus"] if ku.get("uid")]
            in_progress = [ku for ku in r["progress_kus"] if ku.get("uid")]
            mastered = [ku for ku in r["mastered_kus"] if ku.get("uid")]
            bookmarked = [ku for ku in r["bookmarked_kus"] if ku.get("uid")]

            detail["viewed"] = viewed
            detail["in_progress"] = in_progress
            detail["mastered"] = mastered
            detail["bookmarked"] = bookmarked
            detail["summary"]["viewed_count"] = len(viewed)
            detail["summary"]["in_progress_count"] = len(in_progress)
            detail["summary"]["mastered_count"] = len(mastered)
            detail["summary"]["bookmarked_count"] = len(bookmarked)
    except Exception as e:
        logger.warning(f"Failed to get user KU detail for {user_uid}: {e}")

    return detail


async def _get_user_detail_stats(services, user_uid: str) -> dict:
    """Get comprehensive activity, learning, and session stats for a user.

    Returns counts across all entity types for the admin user detail page.
    Uses a single Cypher query with incremental WITHs to avoid multiple round trips.
    """
    stats: dict[str, int] = {
        "tasks_total": 0,
        "tasks_completed": 0,
        "goals_total": 0,
        "goals_active": 0,
        "habits_total": 0,
        "habits_active": 0,
        "events_total": 0,
        "choices_total": 0,
        "principles_total": 0,
        "ku_viewed": 0,
        "ku_in_progress": 0,
        "ku_mastered": 0,
        "session_count": 0,
        "login_count": 0,
    }

    if not services.neo4j_driver:
        return stats

    try:
        records, _, _ = await services.neo4j_driver.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS tasks_total
            OPTIONAL MATCH (u)-[:OWNS]->(tc:Task)
                WHERE tc.status IN ['completed', 'done']
            WITH u, tasks_total, count(DISTINCT tc) AS tasks_completed

            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            WITH u, tasks_total, tasks_completed, count(DISTINCT g) AS goals_total
            OPTIONAL MATCH (u)-[:OWNS]->(ga:Goal)
                WHERE ga.status IN ['active', 'in_progress']
            WITH u, tasks_total, tasks_completed, goals_total,
                 count(DISTINCT ga) AS goals_active

            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 count(DISTINCT h) AS habits_total
            OPTIONAL MATCH (u)-[:OWNS]->(ha:Habit)
                WHERE ha.status IN ['active', 'in_progress']
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, count(DISTINCT ha) AS habits_active

            OPTIONAL MATCH (u)-[:OWNS]->(e:Event)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, count(DISTINCT e) AS events_total

            OPTIONAL MATCH (u)-[:OWNS]->(c:Choice)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total,
                 count(DISTINCT c) AS choices_total

            OPTIONAL MATCH (u)-[:OWNS]->(p:Principle)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 count(DISTINCT p) AS principles_total

            OPTIONAL MATCH (u)-[:VIEWED]->(kv:Ku)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, count(DISTINCT kv) AS ku_viewed
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(kp:Ku)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed,
                 count(DISTINCT kp) AS ku_in_progress
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Ku)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress,
                 count(DISTINCT km) AS ku_mastered

            OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress, ku_mastered,
                 count(DISTINCT s) AS session_count
            OPTIONAL MATCH (u)-[:HAD_AUTH_EVENT]->(ae:AuthEvent)
                WHERE ae.event_type = 'LOGIN_SUCCESS'
            RETURN tasks_total, tasks_completed, goals_total, goals_active,
                   habits_total, habits_active, events_total, choices_total,
                   principles_total, ku_viewed, ku_in_progress, ku_mastered,
                   session_count, count(DISTINCT ae) AS login_count
            """,
            user_uid=user_uid,
        )

        if records:
            r = records[0]
            for key in stats:
                stats[key] = r[key] or 0
    except Exception as e:
        logger.warning(f"Failed to get user detail stats for {user_uid}: {e}")

    return stats


async def _get_users_with_activity_counts(
    services,
    role_filter: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """Get all users with entity counts for the admin users list table.

    Returns user info plus task/goal/habit/KU mastered counts.
    """
    if not services.neo4j_driver:
        return []

    where_clauses = ["u.uid <> 'user_system'"]
    params: dict[str, Any] = {}

    if role_filter:
        where_clauses.append("u.role = $role_filter")
        params["role_filter"] = role_filter
    if active_only:
        where_clauses.append("u.is_active = true")

    where_str = " AND ".join(where_clauses)

    try:
        records, _, _ = await services.neo4j_driver.execute_query(
            f"""
            MATCH (u:User)
            WHERE {where_str}

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS task_count
            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            WITH u, task_count, count(DISTINCT g) AS goal_count
            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, task_count, goal_count, count(DISTINCT h) AS habit_count
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Ku)
            WITH u, task_count, goal_count, habit_count,
                 count(DISTINCT km) AS ku_mastered

            RETURN u.uid AS uid,
                   u.title AS username,
                   u.display_name AS display_name,
                   u.email AS email,
                   u.role AS role,
                   u.is_active AS is_active,
                   u.updated_at AS last_login_at,
                   task_count, goal_count, habit_count, ku_mastered
            ORDER BY u.title
            """,
            **params,
        )

        return [dict(r) for r in records]
    except Exception as e:
        logger.warning(f"Failed to get users with activity counts: {e}")
        return []


# Export the route creation function
__all__ = ["create_admin_dashboard_routes"]
