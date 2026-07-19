"""
Admin Dashboard UI Routes
==========================

Routes for the admin dashboard UI at /admin.

All routes require ADMIN role and wrap the page trees from
``ui/admin/pages.py`` in ``create_admin_page`` — rendering lives in ``ui/``.

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
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from ui.admin import pages
from ui.admin.layout import create_admin_page
from ui.admin.prereq_views import (
    CHOICE_COMPLEMENTARY,
    CHOICE_PREREQ_A_TO_B,
    CHOICE_PREREQ_B_TO_A,
    CHOICE_RELATED,
    AdminPrereqComponents,
)
from ui.admin.types import UserCardData
from ui.patterns.error_banner import render_error_banner

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


def _parse_user_filters(role: str | None, status: str | None) -> tuple[str | None, bool]:
    """Query-param filters → (role_filter, active_only) for the users query."""
    role_filter_str = role if role and role != "all" else None
    active_only = status != "inactive" if status else True
    if status == "all":
        active_only = False
    return role_filter_str, active_only


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
        """Admin dashboard overview with key stats."""
        system_status = await orchestrator.get_system_status()

        return create_admin_page(
            content=pages.overview_page(system_status),
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
    def admin_batch_transcribe(request, current_user):
        """Batch audio→text transcription console.

        Renders the Alpine-driven panel that drives
        POST /api/journals/batch-transcribe over a server-side directory.
        """
        return create_admin_page(
            content=pages.batch_transcribe_page(),
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
        """
        role_filter_str, active_only = _parse_user_filters(role, status)

        users_result = await orchestrator.get_users_with_activity_counts(
            role_filter=role_filter_str,
            active_only=active_only,
        )
        if users_result.is_error:
            logger.error(f"Failed to load users: {users_result.error}")
        users_data = users_result.value if not users_result.is_error else []
        users_error = str(users_result.error) if users_result.is_error else None

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

        return create_admin_page(
            content=pages.users_list_page(
                users_data, user_stats, stats_error, users_error, role, status
            ),
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
        """HTMX partial for filtered user list — just the table for the swap."""
        role_filter_str, active_only = _parse_user_filters(role, status)

        users_result = await orchestrator.get_users_with_activity_counts(
            role_filter=role_filter_str,
            active_only=active_only,
        )
        if users_result.is_error:
            logger.error(f"Failed to load users: {users_result.error}")
            return pages.users_table_error_fragment(str(users_result.error))
        return pages.users_table_fragment(users_result.value or [])

    @rt("/admin/users/{uid}")
    @require_admin(get_user_service)
    async def admin_user_detail(request, uid: str, current_user):
        """User detail view with role form and account actions."""
        user_uid = UserUID(uid)
        result = await orchestrator.get_user(user_uid)

        if result.is_error or not result.value:
            return create_admin_page(
                content=pages.user_not_found_page(uid),
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

        return create_admin_page(
            content=pages.user_detail_page(user_data, detail_stats, detail_stats_error, uid),
            active_section="users",
            admin_username=current_user.display_name or current_user.title,
            title=f"User: {user_data.display_name or user_data.username}",
            system_status=system_status.get("status", "unknown"),
            request=request,
        )

    @rt("/admin/users/{uid}/role-form")
    @require_admin(get_user_service)
    async def admin_user_role_form(request, uid: str, current_user):
        """HTMX partial for role change form."""
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

        return pages.role_change_form(user_data)

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    @rt("/admin/analytics")
    @require_admin(get_user_service)
    async def admin_analytics(request, current_user):
        """Analytics dashboard with user and activity stats."""
        system_status = await orchestrator.get_system_status()
        analytics_data = await orchestrator.get_analytics_data()

        return create_admin_page(
            content=pages.analytics_page(analytics_data),
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

        return create_admin_page(
            content=pages.prereq_suggestions_page(prereq_suggestions.judge_available),
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
        """System health dashboard."""
        health_data = await orchestrator.get_full_health_status()

        return create_admin_page(
            content=pages.system_health_page(health_data),
            active_section="system",
            admin_username=current_user.display_name or current_user.title,
            title="System Health",
            system_status=health_data.get("status", "unknown"),
            request=request,
        )

    logger.info("Admin dashboard UI routes registered")


# Export the route creation function
__all__ = ["create_admin_dashboard_routes"]
