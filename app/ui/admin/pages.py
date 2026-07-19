"""Admin page trees — pure rendering for the /admin route family.

Extracted from ``adapters/inbound/admin_dashboard_ui.py`` per the
routes-in-adapters / rendering-in-``ui/`` convention: routes gate ADMIN,
call the orchestrator, and wrap these trees in ``create_admin_page``.
"""

from typing import Any

from fasthtml.common import Div, P, Span

from core.models.type_hints import UserUID
from ui.admin.prereq_views import AdminPrereqComponents
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

_QUICK_LINK_CLS = (
    ButtonT.ghost,
    "bg-background shadow-sm p-4 hover:shadow-md transition-shadow h-auto no-underline",
)

#: (emoji, label, href) for the overview quick-action grid.
_QUICK_LINKS: tuple[tuple[str, str, str], ...] = (
    ("👥", "Manage Users", "/admin/users"),
    ("📈", "View Analytics", "/admin/analytics"),
    ("⚙️", "System Health", "/admin/system"),
    ("💰", "Finance Invoices", "/finance/invoices"),
    ("📥", "Content Ingestion", "/ingest"),
    ("🎙️", "Batch Transcription", "/admin/batch-transcribe"),
)


def _quick_link(emoji: str, label: str, href: str) -> Any:
    return ButtonLink(
        Div(
            Span(emoji, cls="text-2xl"),
            Span(label, cls="font-medium"),
            cls="flex items-center gap-3",
        ),
        href=href,
        cls=_QUICK_LINK_CLS,
    )


def overview_page(system_status: dict[str, Any]) -> Any:
    """/admin overview — quick links + system status summary."""
    system_status_content = (
        render_error_banner("System status unavailable", severity="warning")
        if not system_status.get("healthy", True)
        else system_summary(system_status)
    )

    return Div(
        PageHeader("Admin Dashboard", subtitle="System overview and management"),
        Div(
            SectionHeader("Quick Actions"),
            Div(
                *[_quick_link(emoji, label, href) for emoji, label, href in _QUICK_LINKS],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
            ),
            cls="mb-8",
        ),
        Card(
            CardHeader(CardTitle("System Status")),
            CardBody(system_status_content),
        ),
    )


def batch_transcribe_page() -> Any:
    """/admin/batch-transcribe — Alpine-driven batch transcription console."""
    return Div(
        PageHeader(
            "Batch Transcription",
            subtitle="Transcribe a server-side directory of audio files to text",
        ),
        render_batch_transcription_panel(),
    )


def users_list_page(
    users_data: list[Any],
    user_stats: dict[str, Any],
    stats_error: bool,
    users_error: str | None,
    role: str | None,
    status: str | None,
) -> Any:
    """/admin/users — stats, filters, and the user table."""
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

    users_error_banner = (
        render_error_banner("Failed to load user list", users_error, severity="warning")
        if users_error is not None
        else None
    )

    return Div(
        PageHeader("User Management", subtitle=subtitle),
        stats_content,
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
        users_error_banner,
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


def users_table_fragment(users_data: list[Any]) -> Any:
    """HTMX partial: the filtered user table."""
    return Div(
        AdminUIComponents.render_users_table(users_data),
        id="user-list",
    )


def users_table_error_fragment(message: str) -> Any:
    """HTMX partial: user-table load failure."""
    return Div(
        render_error_banner("Failed to load user list", message),
        id="user-list",
    )


def user_not_found_page(uid: str) -> Any:
    """/admin/users/{uid} — no such user."""
    return Div(
        render_error_banner(f"No user found with UID: {uid}"),
        ButtonLink("← Back to Users", href="/admin/users", cls=(ButtonT.ghost, "mt-4")),
    )


def user_detail_page(
    user_data: UserCardData,
    detail_stats: dict[str, Any],
    detail_stats_error: bool,
    uid: str,
) -> Any:
    """/admin/users/{uid} — account details, stats, role form, actions."""
    return Div(
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
        Card(
            CardHeader(CardTitle("User Statistics")),
            CardBody(
                render_error_banner("User statistics unavailable", severity="warning")
                if detail_stats_error
                else AdminUIComponents.render_user_activity_stats(detail_stats, UserUID(uid)),
            ),
            cls="mb-6",
        ),
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
        Card(
            CardHeader(CardTitle("Change Role")),
            CardBody(AdminUIComponents.render_role_change_form(user_data)),
            cls="mb-6",
        ),
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


def role_change_form(user_data: UserCardData) -> Any:
    """HTMX partial: the role change form."""
    return AdminUIComponents.render_role_change_form(user_data)


def analytics_page(analytics_data: dict[str, Any]) -> Any:
    """/admin/analytics — platform usage dashboard."""
    return Div(
        PageHeader("Analytics", subtitle="Platform usage and user statistics"),
        AdminAnalyticsComponents.render_analytics_dashboard(analytics_data),
    )


def prereq_suggestions_page(judge_available: bool) -> Any:
    """/admin/prereq-suggestions — the suggestion queue."""
    return Div(
        PageHeader(
            "Prereq Suggestions",
            subtitle="Inferred Ku↔Ku edges awaiting review — approve writes Edge YAML",
        ),
        AdminPrereqComponents.render_page(judge_available),
    )


def system_health_page(health_data: dict[str, Any]) -> Any:
    """/admin/system — component health + refresh."""
    return Div(
        PageHeader("System Health", subtitle="Monitor system components and services"),
        AdminSystemComponents.render_health_dashboard(health_data),
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


def system_summary(status_data: dict[str, Any]) -> Any:
    """Compact system status summary for the overview card."""
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


def _detail_row(label: str, value: str) -> Any:
    """Render a detail row for user info."""
    return Div(
        Span(label, cls="text-muted-foreground w-32 inline-block"),
        Span(value, cls="font-medium"),
        cls="text-sm",
    )
