"""Admin page trees — pure rendering for the /admin route family.

Extracted from ``adapters/inbound/admin_dashboard_ui.py`` per the
routes-in-adapters / rendering-in-``ui/`` convention: routes gate ADMIN,
call the orchestrator, and wrap these trees in ``create_admin_page``.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Li, P, Span, Ul

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
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from core.ports.query_types import KnowledgeCoverageMetric, KnowledgeHealthReport

_QUICK_LINK_CLS = (
    ButtonT.ghost,
    "bg-background shadow-xs p-4 hover:shadow-md transition-shadow h-auto no-underline",
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


def _pct(fraction: float) -> str:
    """Render a 0.0-1.0 fraction as a whole-number percentage."""
    return f"{round(fraction * 100)}%"


def _coverage_stat(label: str, metric: "KnowledgeCoverageMetric", total_kus: int) -> StatItem:
    """A coverage slice as a StatItem: `edges · participating/total Kus`."""
    coverage = metric["coverage"]
    color = "success" if coverage >= 0.5 else ("warning" if coverage > 0 else "error")
    return StatItem(
        label=label,
        value=_pct(coverage),
        change=f"{metric['edge_count']} edges · {metric['participating_kus']}/{total_kus} Kus",
        color=color,
    )


def _readiness_banner(report: "KnowledgeHealthReport") -> Any:
    """The headline GDS-readiness score, badge, and progress bar (ADR-080)."""
    score_pct = round(report["gds_readiness_score"] * 100)
    ready = report["gds_ready"]
    badge_text = "GDS-ready" if ready else "Building density"
    badge_cls = (
        "bg-success/15 text-success" if ready else "bg-warning/15 text-warning"
    ) + " text-sm font-medium px-3 py-1 rounded-full"
    bar_cls = ("bg-success" if ready else "bg-warning") + " h-3 rounded-full"

    return Card(
        CardBody(
            Div(
                Div(
                    Span("GDS-Readiness Score", cls="text-sm text-muted-foreground uppercase"),
                    Div(
                        Span(f"{score_pct}%", cls="text-4xl font-bold text-foreground"),
                        Span(badge_text, cls=badge_cls),
                        cls="flex items-center gap-3 mt-1",
                    ),
                    cls="flex-1",
                ),
                cls="flex items-center justify-between",
            ),
            # Inline-style width keeps the bar prod-safe (no Tailwind JIT for
            # arbitrary widths). See reference_tailwind_prod_layout_verification.
            Div(
                Div(cls=bar_cls, style=f"width: {score_pct}%;"),
                cls="w-full bg-muted rounded-full h-3 mt-4",
            ),
            P(
                "Composite of connectivity, orphan health, prerequisite-DAG coverage, "
                "ORGANIZES/MOC coverage, and lateral density. GDS (centrality / "
                "shortest-path / community detection) becomes meaningful once this "
                "crosses the threshold — ADR-080 Horizon-2.",
                cls="text-sm text-muted-foreground mt-3",
            ),
        ),
    )


def _flags_card(flags: list[str]) -> Any:
    """Authoring-guidance flags — content gaps to fill (or a healthy note)."""
    return Card(
        CardHeader(CardTitle("Authoring guidance")),
        CardBody(
            Ul(
                *[Li(flag, cls="text-sm py-1") for flag in flags],
                cls="list-disc list-inside space-y-1",
            )
        ),
    )


def _orphan_card(orphan_kus: list[Any], orphan_count: int) -> Any:
    """The orphan-Ku list — the strongest authoring signal (isolated concepts)."""
    if not orphan_kus:
        body: Any = P("No orphan Kus — every concept is connected. 🎉", cls="text-sm text-success")
    else:
        body = Ul(
            *[
                Li(
                    A(
                        ku["title"],
                        href=f"/explore/ku/{ku['uid']}",
                        cls="text-primary hover:underline",
                    ),
                    Span(f"  ({ku['uid']})", cls="text-xs text-muted-foreground"),
                    cls="text-sm py-0.5",
                )
                for ku in orphan_kus
            ],
            cls="space-y-0.5 max-h-96 overflow-y-auto",
        )
    return Card(
        CardHeader(CardTitle(f"Orphan Kus ({orphan_count})")),
        CardBody(body),
    )


def knowledge_health_page(report: "KnowledgeHealthReport") -> Any:
    """/admin/knowledge-health — ADR-080 Horizon-1 structural-health gauge.

    One consolidated corpus-level report over the knowledge subgraph
    (Ku / PathStep / LearningPath / Exercise): node counts, Ku degree
    distribution, the orphan-Ku list, prerequisite-DAG depth/coverage,
    ORGANIZES/MOC coverage, lateral density, practice coverage, a composite
    GDS-readiness score, and authoring-guidance flags.
    """
    total_kus = report["total_kus"]
    orphan_color = "error" if report["orphan_fraction"] > 0.05 else "success"

    node_stats = [
        StatItem(label="Kus", value=total_kus, color="info"),
        StatItem(label="Path Steps", value=report["total_path_steps"], color="info"),
        StatItem(label="Learning Paths", value=report["total_learning_paths"], color="info"),
        StatItem(label="Exercises", value=report["total_exercises"], color="info"),
        # Drafts are counted INSIDE the four totals above, not subtracted from
        # them — surfaced so the author can read those totals correctly.
        StatItem(
            label="Draft (unpublished)",
            value=report["draft_curriculum_count"],
            color="warning" if report["draft_curriculum_count"] else "info",
        ),
    ]

    structural_stats = [
        StatItem(
            label="Avg Ku Degree",
            value=f"{report['avg_ku_degree']:.2f}",
            change=f"max {report['max_ku_degree']}",
            color="info",
        ),
        StatItem(
            label="Orphan Kus",
            value=report["orphan_ku_count"],
            change=_pct(report["orphan_fraction"]),
            color=orphan_color,
        ),
        _coverage_stat("Composition", report["composition"], total_kus),
        _coverage_stat("Prerequisite DAG", report["prerequisite_dag"], total_kus),
        StatItem(
            label="DAG Depth",
            value=report["dag_max_depth"],
            change="longest prereq chain",
            color="info",
        ),
        _coverage_stat("ORGANIZES / MOC", report["organizes"], total_kus),
        StatItem(
            label="Lateral Edges",
            value=report["lateral_edge_count"],
            change=f"{report['lateral_density']:.2f}/Ku · {report['enablement_edge_count']} enables",
            color="info",
        ),
        StatItem(
            label="Practice Coverage",
            value=_pct(report["practice_coverage"]),
            change=f"{report['path_steps_with_exercise']}/{report['total_path_steps']} steps",
            color="success" if report["practice_coverage"] >= 0.5 else "warning",
        ),
    ]

    return Div(
        PageHeader(
            "Knowledge Health",
            subtitle="Structural health of the knowledge subgraph — GDS-readiness gauge (ADR-080)",
        ),
        _readiness_banner(report),
        Div(cls="mt-6"),
        SectionHeader("Corpus"),
        StatsGrid(node_stats, cols=4),
        Div(cls="mt-6"),
        SectionHeader("Structural coverage"),
        StatsGrid(structural_stats, cols=4),
        Div(cls="mt-6"),
        _flags_card(report["flags"]),
        Div(cls="mt-6"),
        _orphan_card(report["orphan_kus"], report["orphan_ku_count"]),
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
