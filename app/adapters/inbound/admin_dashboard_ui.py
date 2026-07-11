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
- GET /admin/prereq-suggestions - Prerequisite-edge suggestion queue (Discovery Analytics PR 4)
- POST /admin/prereq-suggestions/generate - HTMX: run candidates → LLM judge, return queue fragment
- POST /admin/prereq-suggestions/approve - HTMX: write ONE Edge YAML into the content vault
- GET /admin/system - System health dashboard

Note: KU progress is accessible per-student at /teaching/students/{uid}?tab=ku.

Security:
- All routes require authentication (401 if not logged in)
- All routes require ADMIN role (403 if insufficient permissions)

Version: 1.0.0
Date: 2025-12-07
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P, Span

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from ui.admin.layout import create_admin_page
from ui.admin.prereq_views import (
    CHOICE_COMPLEMENTARY,
    CHOICE_PREREQ_A_TO_B,
    CHOICE_PREREQ_B_TO_A,
    CHOICE_RELATED,
    AdminPrereqComponents,
)
from ui.admin.types import UserCardData
from ui.admin.views import (
    AdminAnalyticsComponents,
    AdminSystemComponents,
    AdminUIComponents,
)
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.journals.components import render_batch_transcription_panel
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from core.orchestrator.admin_orchestrator import AdminOrchestrator
    from core.services.prereq_suggestion_service import PrereqSuggestionService

logger = get_logger("skuel.routes.admin.ui")

#: Queue-form choice value → (swap a/b before writing, relationship name).
#: Direction is expressed by from/to ordering in the Edge YAML, so both
#: prereq choices resolve to PREREQUISITE_FOR.
APPROVE_CHOICES: dict[str, tuple[bool, str]] = {
    CHOICE_PREREQ_A_TO_B: (False, RelationshipName.PREREQUISITE_FOR.value),
    CHOICE_PREREQ_B_TO_A: (True, RelationshipName.PREREQUISITE_FOR.value),
    CHOICE_RELATED: (False, RelationshipName.RELATED_TO.value),
    CHOICE_COMPLEMENTARY: (False, RelationshipName.COMPLEMENTARY_TO.value),
}


def create_admin_dashboard_routes(
    _app: Any,
    rt: Any,
    orchestrator: "AdminOrchestrator",
    prereq_suggestions: "PrereqSuggestionService",
) -> None:
    """
    Create admin dashboard UI routes.

    All routes require ADMIN role.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        orchestrator: AdminOrchestrator facade (user_service, admin_stats, system_service)
        prereq_suggestions: Prerequisite-edge suggestion queue service (PR 4)
    """

    get_user_service = make_service_getter(orchestrator.user_service)

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
        system_status = await orchestrator.get_system_status()

        system_status_content = (
            render_error_banner("System status unavailable", severity="warning")
            if not system_status.get("healthy", True)
            else _render_system_summary(system_status)
        )

        content = Div(
            PageHeader("Admin Dashboard", subtitle="System overview and management"),
            # Quick links
            Div(
                SectionHeader("Quick Actions"),
                Div(
                    ButtonLink(
                        Div(
                            Span("👥", cls="text-2xl"),
                            Span("Manage Users", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/users",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    ButtonLink(
                        Div(
                            Span("📈", cls="text-2xl"),
                            Span("View Analytics", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/analytics",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    ButtonLink(
                        Div(
                            Span("⚙️", cls="text-2xl"),
                            Span("System Health", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/system",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    ButtonLink(
                        Div(
                            Span("💰", cls="text-2xl"),
                            Span("Finance Invoices", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/finance/invoices",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    ButtonLink(
                        Div(
                            Span("📥", cls="text-2xl"),
                            Span("Content Ingestion", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/ingest",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    ButtonLink(
                        Div(
                            Span("🎙️", cls="text-2xl"),
                            Span("Batch Transcription", cls="font-medium"),
                            cls="flex items-center gap-3",
                        ),
                        href="/admin/batch-transcribe",
                        cls=(
                            ButtonT.ghost,
                            "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
                        ),
                    ),
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                ),
                cls="mb-8",
            ),
            # System status summary
            Card(
                CardHeader(CardTitle("System Status")),
                CardBody(system_status_content),
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
    # BATCH TRANSCRIPTION
    # ========================================================================

    @rt("/admin/batch-transcribe")
    @require_admin(get_user_service)
    async def admin_batch_transcribe(request, current_user):
        """Batch audio→text transcription console.

        Renders the Alpine-driven panel that drives
        POST /api/journals/batch-transcribe over a server-side directory.
        """
        content = Div(
            PageHeader(
                "Batch Transcription",
                subtitle="Transcribe a server-side directory of audio files to text",
            ),
            render_batch_transcription_panel(),
        )

        return await create_admin_page(
            content=content,
            active_section="transcription",
            admin_username=current_user.display_name or current_user.title,
            title="Batch Transcription",
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
        users_result = await orchestrator.get_users_with_activity_counts(
            role_filter=role_filter_str,
            active_only=active_only,
        )
        if users_result.is_error:
            logger.error(f"Failed to load users: {users_result.error}")
        users_data = users_result.value if not users_result.is_error else []

        # Fetch stats for header via efficient Cypher COUNT query
        user_stats_result = await orchestrator.get_user_role_counts()
        stats_error = user_stats_result.is_error
        user_stats: dict[str, Any] = (
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
        system_status = await orchestrator.get_system_status()

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
                CardHeader(CardTitle("Filters")),
                CardBody(
                    Div(
                        AdminUIComponents.render_role_filter(role),
                        AdminUIComponents.render_status_filter(status),
                        cls="flex flex-wrap gap-4",
                    ),
                ),
                cls="mb-6",
            ),
            # Error banner (if user list failed)
            users_error_banner,
            # User table
            Card(
                CardHeader(CardTitle("Users")),
                CardBody(
                    Div(
                        AdminUIComponents.render_users_table(users_data),
                        id="user-list",
                    ),
                ),
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

        users_result = await orchestrator.get_users_with_activity_counts(
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
        user_uid = UserUID(uid)
        result = await orchestrator.get_user(user_uid)

        if result.is_error or not result.value:
            content = Div(
                render_error_banner(f"No user found with UID: {uid}"),
                ButtonLink("← Back to Users", href="/admin/users", cls=(ButtonT.ghost, "mt-4")),
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

        system_status = await orchestrator.get_system_status()

        # Fetch user activity stats
        detail_stats_result = await orchestrator.get_user_detail_stats(user_uid)
        detail_stats_error = detail_stats_result.is_error
        if detail_stats_error:
            logger.warning(f"Failed to load detail stats for {uid}: {detail_stats_result.error}")
        detail_stats = detail_stats_result.value if not detail_stats_error else {}

        content = Div(
            # Back button
            ButtonLink(
                "← Back to Users",
                href="/admin/users",
                cls=(ButtonT.ghost, "mb-4"),
                size="sm",
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
                CardHeader(CardTitle("User Details")),
                CardBody(
                    Div(
                        _detail_row("UID", user_data.uid),
                        _detail_row("Username", f"@{user_data.username}"),
                        _detail_row("Email", user_data.email),
                        _detail_row("Created", user_data.created_at or "Unknown"),
                        _detail_row("Last Login", user_data.last_login_at),
                        _detail_row("Verified", "Yes" if user_data.is_verified else "No"),
                        cls="space-y-3",
                    ),
                ),
                cls="mb-6",
            ),
            # Activity & session stats
            Card(
                CardHeader(CardTitle("User Statistics")),
                CardBody(
                    render_error_banner("User statistics unavailable", severity="warning")
                    if detail_stats_error
                    else AdminUIComponents.render_user_activity_stats(detail_stats, user_uid),
                ),
                cls="mb-6",
            ),
            # Link to teaching view for submission/learning data
            Card(
                CardHeader(CardTitle("Student Work")),
                CardBody(
                    Div(
                        P(
                            "Submissions, reports, and learning progress are managed in the Teaching section.",
                            cls="text-muted-foreground text-sm mb-3",
                        ),
                        ButtonLink(
                            "View submissions →",
                            href=f"/teaching/students/{uid}",
                            cls=ButtonT.secondary,
                            size="sm",
                        ),
                        ButtonLink(
                            "KU progress →",
                            href=f"/teaching/students/{uid}?tab=ku",
                            cls=(ButtonT.secondary, "ml-2"),
                            size="sm",
                        ),
                    ),
                ),
                cls="mb-6",
            ),
            # Role change section
            Card(
                CardHeader(CardTitle("Change Role")),
                CardBody(AdminUIComponents.render_role_change_form(user_data)),
                cls="mb-6",
            ),
            # Actions
            Card(
                CardHeader(CardTitle("Account Actions")),
                CardBody(
                    Div(
                        Button(
                            "Deactivate Account" if user_data.is_active else "Activate Account",
                            cls=ButtonT.destructive if user_data.is_active else ButtonT.primary,
                            hx_post=f"/api/admin/users/{uid}/{'deactivate' if user_data.is_active else 'activate'}",
                            hx_confirm=f"Are you sure you want to {'deactivate' if user_data.is_active else 'activate'} this user?",
                        ),
                        cls="flex gap-4",
                    ),
                ),
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
        result = await orchestrator.get_user(UserUID(uid))

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
        system_status = await orchestrator.get_system_status()
        analytics_data = await orchestrator.get_analytics_data()

        content = Div(
            PageHeader("Analytics", subtitle="Platform usage and user statistics"),
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
    # PREREQUISITE-EDGE SUGGESTIONS (Discovery Analytics PR 4)
    # ========================================================================

    @rt("/admin/prereq-suggestions")
    @require_admin(get_user_service)
    async def admin_prereq_suggestions(request: Request, current_user: Any = None) -> Any:
        """Prerequisite-edge suggestion queue — generate, review, approve to Edge YAML."""
        system_status = await orchestrator.get_system_status()

        content = Div(
            PageHeader(
                "Prereq Suggestions",
                subtitle="Inferred Ku↔Ku edges awaiting review — approve writes Edge YAML",
            ),
            AdminPrereqComponents.render_page(prereq_suggestions.judge_available),
        )

        return await create_admin_page(
            content=content,
            active_section="prereq",
            admin_username=current_user.display_name or current_user.title,
            title="Prereq Suggestions",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    @rt("/admin/prereq-suggestions/generate", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def admin_prereq_generate(request: Request, current_user: Any = None) -> Any:
        """HTMX: run the full pipeline (candidates → judge), return the queue fragment.

        Suggestions are EPHEMERAL — computed on demand, held in the returned
        HTML (hidden form fields), never persisted as nodes.
        """
        run_result = await prereq_suggestions.generate_suggestions()
        if run_result.is_error:
            err = run_result.expect_error()
            return render_error_banner(err.user_message or err.message, severity="warning")
        return AdminPrereqComponents.render_queue(run_result.value)

    @rt("/admin/prereq-suggestions/approve", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def admin_prereq_approve(request: Request, current_user: Any = None) -> Any:
        """HTMX: approve one suggestion — writes ONE Edge YAML file into the content vault.

        The single sanctioned vault-write (Mike's ruling 2026-07-10): explicit
        admin approve only, containment-guarded, never overwrites. No graph
        writes — the edge lands via the next content-vault sync.
        """
        form = await request.form()
        a_uid = str(form.get("a_uid", "")).strip()
        b_uid = str(form.get("b_uid", "")).strip()
        a_title = str(form.get("a_title", "")).strip()
        b_title = str(form.get("b_title", "")).strip()
        rationale = str(form.get("rationale", "")).strip()
        choice = APPROVE_CHOICES.get(str(form.get("choice", "")))

        if choice is None or not a_uid or not b_uid:
            return AdminPrereqComponents.render_row_error(
                "Invalid approve request (missing pair or unknown relation choice)",
                a_title,
                b_title,
            )

        swap, relationship = choice
        from_uid, to_uid = (b_uid, a_uid) if swap else (a_uid, b_uid)
        result = await prereq_suggestions.approve(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship=relationship,
            rationale=rationale or None,
        )
        if result.is_error:
            err = result.expect_error()
            return AdminPrereqComponents.render_row_error(
                err.user_message or err.message, a_title, b_title
            )
        return AdminPrereqComponents.render_approved_row(Path(result.value).name, a_title, b_title)

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
        health_data = await orchestrator.get_full_health_status()

        content = Div(
            PageHeader("System Health", subtitle="Monitor system components and services"),
            AdminSystemComponents.render_health_dashboard(health_data),
            # Refresh button
            Div(
                Button(
                    "Refresh",
                    cls=ButtonT.secondary,
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
        ButtonLink(
            "View Details →",
            href="/admin/system",
            cls=(ButtonT.ghost, "mt-2"),
            size="sm",
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
