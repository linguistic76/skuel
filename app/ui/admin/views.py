"""
Admin Dashboard UI Components
=============================

UI components for the admin dashboard, including:
- User management (cards, tables, role forms)
- Analytics displays
- System health indicators

Usage:
    from ui.admin.views import AdminUIComponents

    # Render user card
    card = AdminUIComponents.render_user_card(user_data)

    # Render user stats
    stats = AdminUIComponents.render_user_stats(stats_data)
"""

from typing import Any, ClassVar

from fasthtml.common import A, Div, Form, Option, P, Span

from core.models.type_hints import UserUID
from ui.admin.types import UserCardData
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.components.table import Td
from ui.data import TableFromDicts, TableT
from ui.feedback import Badge, BadgeT, Progress, ProgressT
from ui.forms import Select
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import ButtonLink


class AdminUIComponents:
    """User management UI components for admin dashboard."""

    @staticmethod
    def render_role_badge(role: str) -> Any:
        """Render a role badge with appropriate color."""
        from ui.enum_helpers import get_role_badge_class

        color_class = get_role_badge_class(role)
        return Badge(
            role.upper(),
            variant=None,
            cls=f"{color_class} font-semibold",
        )

    @staticmethod
    def render_status_badge(is_active: bool) -> Any:
        """Render active/inactive status badge."""
        if is_active:
            return Badge("Active", variant=BadgeT.success, cls="border-success/20")
        return Badge("Inactive", variant=BadgeT.ghost)

    @staticmethod
    def render_user_card(user: UserCardData, show_actions: bool = True) -> Div:
        """
        Render a user card with role badge and actions.

        Args:
            user: Typed user card data
            show_actions: Whether to show action buttons

        Returns:
            Div containing the user card
        """
        display_name = user.display_name or user.username
        last_login = user.last_login_at

        # Format last login - show date portion if it's a full datetime
        if last_login and last_login != "Never" and "T" in str(last_login):
            last_login = str(last_login).split("T")[0]

        uid_css = user.uid.replace(":", "-")

        # Action buttons
        actions = []
        if show_actions:
            actions = [
                ButtonLink(
                    "View",
                    href=f"/admin/users/{user.uid}",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                Button(
                    "Edit Role",
                    cls=ButtonT.primary,
                    size="sm",
                    hx_get=f"/admin/users/{user.uid}/role-form",
                    hx_target=f"#role-form-{uid_css}",
                    hx_swap="innerHTML",
                ),
            ]
            if user.is_active:
                actions.append(
                    Button(
                        "Deactivate",
                        cls=ButtonT.destructive,
                        size="sm",
                        hx_post=f"/api/admin/users/{user.uid}/deactivate",
                        hx_confirm="Are you sure you want to deactivate this user?",
                        hx_swap="outerHTML",
                        hx_target=f"#user-card-{uid_css}",
                    )
                )
            else:
                actions.append(
                    Button(
                        "Activate",
                        cls=ButtonT.primary,
                        size="sm",
                        hx_post=f"/api/admin/users/{user.uid}/activate",
                        hx_swap="outerHTML",
                        hx_target=f"#user-card-{uid_css}",
                    )
                )

        return Card(
            # Header with name and badges
            Div(
                Div(
                    Span(display_name, cls="text-lg font-semibold"),
                    Span(f"@{user.username}", cls="text-sm text-muted-foreground ml-2"),
                    cls="flex items-center gap-2",
                ),
                Div(
                    AdminUIComponents.render_role_badge(user.role),
                    AdminUIComponents.render_status_badge(user.is_active),
                    cls="flex items-center gap-2",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            # Details
            Div(
                P(
                    Span("Email: ", cls="text-muted-foreground"),
                    Span(user.email),
                    cls="text-sm",
                ),
                P(
                    Span("Last login: ", cls="text-muted-foreground"),
                    Span(last_login),
                    cls="text-sm",
                ),
                cls="space-y-1 mb-3",
            ),
            # Role form placeholder (for HTMX)
            Div(id=f"role-form-{uid_css}", cls="mb-3"),
            # Actions
            Div(*actions, cls="flex flex-wrap gap-2") if actions else None,
            id=f"user-card-{uid_css}",
            cls="bg-background shadow-xs p-4 border border-border",
        )

    @staticmethod
    def render_user_table(users: list[dict]) -> Div:
        """
        Render users as a table with sortable columns.

        Args:
            users: List of user data dicts

        Returns:
            Div containing the user table
        """
        if not users:
            return Card(
                EmptyState(title="No users found"),
                cls="bg-background shadow-xs",
            )

        def _user_cell_render(k: str, v: object) -> Any:
            styles = {
                "Username": "font-medium",
                "Email": "text-muted-foreground",
                "Last Login": "text-sm text-muted-foreground",
                "": "text-right",
            }
            return Td(v, cls=styles.get(k, ""))

        body_data = []
        for user in users:
            uid = user.get("uid", "")
            last_login = user.get("last_login_at", "Never")
            if last_login and last_login != "Never" and "T" in str(last_login):
                last_login = str(last_login).split("T")[0]

            body_data.append(
                {
                    "Username": user.get("username", "Unknown"),
                    "Email": user.get("email", ""),
                    "Role": AdminUIComponents.render_role_badge(user.get("role", "registered")),
                    "Status": AdminUIComponents.render_status_badge(user.get("is_active", True)),
                    "Last Login": last_login,
                    "": ButtonLink(
                        "View",
                        href=f"/admin/users/{uid}",
                        cls=ButtonT.ghost,
                        size="xs",
                    ),
                }
            )

        return Div(
            TableFromDicts(
                header_data=["Username", "Email", "Role", "Status", "Last Login", ""],
                body_data=body_data,
                body_cell_render=_user_cell_render,
                cls=(TableT.striped,),
            ),
            cls="overflow-x-auto",
        )

    @staticmethod
    def render_role_change_form(user: UserCardData) -> Form:
        """
        Render form for changing user role.

        Args:
            user: Typed user card data

        Returns:
            Form for role change with HTMX
        """
        uid = user.uid
        current_role = user.role

        roles = ["registered", "member", "teacher", "admin"]

        return Form(
            Div(
                Select(
                    *[
                        Option(
                            role.upper(),
                            value=role,
                            selected=(role == current_role),
                        )
                        for role in roles
                    ],
                    name="role",
                    size=Size.sm,
                    full_width=False,
                ),
                Button(
                    "Save",
                    type="submit",
                    cls=ButtonT.primary,
                    size="sm",
                ),
                Button(
                    "Cancel",
                    type="button",
                    cls=ButtonT.ghost,
                    size="sm",
                    onclick="this.closest('form').remove()",
                ),
                cls="flex items-center gap-2",
            ),
            hx_post=f"/api/admin/users/{uid}/role",
            hx_swap="outerHTML",
            hx_target=f"#user-card-{uid.replace(':', '-')}",
            cls="bg-muted p-2 rounded-lg",
        )

    @staticmethod
    def render_user_stats(stats: dict) -> Div:
        """
        Render user statistics cards.

        Args:
            stats: Dict with user counts by role

        Returns:
            Div with stats cards grid
        """
        return StatsGrid(
            [
                StatItem(label="Total Users", value=stats.get("total", 0), color="info"),
                StatItem(label="Admins", value=stats.get("admins", 0), color="error"),
                StatItem(label="Teachers", value=stats.get("teachers", 0), color="orange-600"),
                StatItem(label="Members", value=stats.get("members", 0), color="success"),
                StatItem(
                    label="Free Users", value=stats.get("registered", 0), color="muted-foreground"
                ),
            ]
        )

    @staticmethod
    def render_role_filter(current_role: str | None = None) -> Div:
        """Render role filter dropdown."""
        roles = ["all", "admin", "teacher", "member", "registered"]

        return Div(
            Select(
                *[
                    Option(
                        "All Roles" if r == "all" else r.upper(),
                        value=r,
                        selected=(r == current_role or (current_role is None and r == "all")),
                    )
                    for r in roles
                ],
                name="role",
                full_width=False,
                hx_get="/admin/users/partial",
                hx_target="#user-list",
                hx_trigger="change",
                hx_include="[name='status']",
            ),
            cls="space-y-2",
        )

    @staticmethod
    def render_status_filter(current_status: str | None = None) -> Div:
        """Render status filter dropdown."""
        statuses = ["all", "active", "inactive"]

        return Div(
            Select(
                *[
                    Option(
                        s.title() if s != "all" else "All Status",
                        value=s,
                        selected=(s == current_status or (current_status is None and s == "all")),
                    )
                    for s in statuses
                ],
                name="status",
                full_width=False,
                hx_get="/admin/users/partial",
                hx_target="#user-list",
                hx_trigger="change",
                hx_include="[name='role']",
            ),
            cls="space-y-2",
        )

    @staticmethod
    def render_users_table(users: list[dict]) -> Div:
        """Render users as a dense table with entity count columns.

        Args:
            users: List of user dicts from _get_users_with_activity_counts().
        """
        if not users:
            return EmptyState(title="No users found")

        centered_cols = {"Tasks", "Goals", "Habits", "KUs"}

        def _activity_header_render(col: str) -> object:
            from ui.components.table import Th

            if col in centered_cols:
                return Th(col, cls="text-center")
            if col == "":
                return Th("", cls="text-right")
            return Th(col)

        def _activity_cell_render(k: str, v: object) -> Any:
            if k in centered_cols:
                return Td(v, cls="text-center")
            styles = {
                "Email": "text-sm text-muted-foreground",
                "Last Login": "text-sm",
                "": "text-right",
            }
            return Td(v, cls=styles.get(k, ""))

        def _count_value(count: int) -> Span:
            if count > 0:
                return Span(str(count), cls="font-semibold")
            return Span("—", cls="text-foreground/30")

        body_data = []
        for user in users:
            uid = user.get("uid", "")
            username = user.get("username", "Unknown")
            display_name = user.get("display_name") or username
            last_login = user.get("last_login_at", "Never")
            if last_login and last_login != "Never" and "T" in str(last_login):
                last_login = str(last_login).split("T")[0]

            body_data.append(
                {
                    "User": A(
                        Div(
                            Span(display_name, cls="font-medium"),
                            Span(f"@{username}", cls="text-xs text-muted-foreground block"),
                        ),
                        href=f"/admin/users/{uid}",
                        cls="hover:underline",
                    ),
                    "Email": user.get("email", ""),
                    "Role": AdminUIComponents.render_role_badge(user.get("role", "registered")),
                    "Status": AdminUIComponents.render_status_badge(user.get("is_active", True)),
                    "Last Login": (
                        last_login
                        if last_login != "Never"
                        else Span("Never", cls="text-foreground/30")
                    ),
                    "Tasks": _count_value(user.get("task_count", 0) or 0),
                    "Goals": _count_value(user.get("goal_count", 0) or 0),
                    "Habits": _count_value(user.get("habit_count", 0) or 0),
                    "KUs": _count_value(user.get("ku_mastered", 0) or 0),
                    "": ButtonLink(
                        "View →",
                        href=f"/admin/users/{uid}",
                        cls=(ButtonT.ghost, "text-primary"),
                        size="xs",
                    ),
                }
            )

        return Div(
            TableFromDicts(
                header_data=[
                    "User",
                    "Email",
                    "Role",
                    "Status",
                    "Last Login",
                    "Tasks",
                    "Goals",
                    "Habits",
                    "KUs",
                    "",
                ],
                body_data=body_data,
                header_cell_render=_activity_header_render,
                body_cell_render=_activity_cell_render,
                cls=(TableT.striped,),
            ),
            cls="overflow-x-auto",
        )

    @staticmethod
    def render_user_activity_stats(stats: dict, user_uid: UserUID) -> Div:
        """Render comprehensive activity, learning, and session stats for a user.

        Args:
            stats: Dict from _get_user_detail_stats() with all count fields.
            user_uid: User UID for linking to learning detail page.
        """
        # Activity domains
        activity_stats = [
            StatItem(
                label=f"Tasks ({stats.get('tasks_completed', 0)} completed)",
                value=stats.get("tasks_total", 0),
                color="info",
            ),
            StatItem(
                label=f"Goals ({stats.get('goals_active', 0)} active)",
                value=stats.get("goals_total", 0),
                color="success",
            ),
            StatItem(
                label=f"Habits ({stats.get('habits_active', 0)} active)",
                value=stats.get("habits_total", 0),
                color="purple-600",
            ),
            StatItem(label="Events", value=stats.get("events_total", 0), color="orange-600"),
            StatItem(label="Choices", value=stats.get("choices_total", 0), color="indigo-600"),
            StatItem(label="Principles", value=stats.get("principles_total", 0), color="warning"),
        ]

        # Learning progress
        learning_stats = [
            StatItem(label="KUs Viewed", value=stats.get("ku_viewed", 0), color="muted-foreground"),
            StatItem(
                label="KUs In Progress", value=stats.get("ku_in_progress", 0), color="orange-600"
            ),
            StatItem(label="KUs Mastered", value=stats.get("ku_mastered", 0), color="success"),
        ]

        # Session stats
        session_stats = [
            StatItem(label="Total Logins", value=stats.get("login_count", 0), color="info"),
            StatItem(
                label="Total Sessions", value=stats.get("session_count", 0), color="purple-600"
            ),
        ]

        return Div(
            # Activity domains section
            Div(
                Div(
                    Span("Activity Domains", cls="text-lg font-semibold"),
                    cls="mb-3",
                ),
                StatsGrid(activity_stats),
                cls="mb-6",
            ),
            # Learning progress section
            Div(
                Div(
                    Span("Learning Progress", cls="text-lg font-semibold"),
                    ButtonLink(
                        "View Full KU Detail →",
                        href=f"/teaching/learning/user/{user_uid}",
                        cls=(ButtonT.ghost, "ml-4"),
                        size="sm",
                    ),
                    cls="flex items-center mb-3",
                ),
                StatsGrid(learning_stats),
                cls="mb-6",
            ),
            # Session activity section
            Div(
                Div(
                    Span("Session Activity", cls="text-lg font-semibold"),
                    cls="mb-3",
                ),
                StatsGrid(session_stats),
            ),
        )

    @staticmethod
    def render_user_reports_list(reports: list, _user_uid: UserUID) -> Div:
        """Render a list of user reports for admin user detail page.

        Args:
            reports: List of Report domain objects.
            _user_uid: User UID (reserved for future linking).
        """
        if not reports:
            return EmptyState(title="No reports submitted yet")

        from ui.enum_helpers import get_submission_status_badge_class

        def _report_cell_render(k: str, v: object) -> Any:
            if k == "Title":
                return Td(v, cls="font-medium text-sm")
            if k == "Created":
                return Td(v, cls="text-sm text-muted-foreground")
            return Td(v)

        body_data = []
        for report in reports:
            report_type = report.entity_type.value if report.entity_type else "unknown"
            status = report.status.value if report.status else "unknown"
            title = report.title or getattr(report, "original_filename", None) or report.uid
            created = report.created_at.strftime("%Y-%m-%d") if report.created_at else "Unknown"

            body_data.append(
                {
                    "Title": title,
                    "Type": Badge(report_type.upper(), variant=BadgeT.outline, size=Size.sm),
                    "Status": Badge(
                        status.replace("_", " ").upper(),
                        variant=None,
                        size=Size.sm,
                        cls=get_submission_status_badge_class(status),
                    ),
                    "Created": created,
                }
            )

        return Div(
            P(f"{len(reports)} report(s)", cls="text-sm text-muted-foreground mb-3"),
            Div(
                TableFromDicts(
                    header_data=["Title", "Type", "Status", "Created"],
                    body_data=body_data,
                    body_cell_render=_report_cell_render,
                    cls=(TableT.striped,),
                ),
                cls="overflow-x-auto",
            ),
        )


class AdminAnalyticsComponents:
    """Analytics components for admin dashboard."""

    # Phase-2 discovery analytics (clustering, temporal patterns) unlock at this
    # :SearchEvent volume — see /docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md
    PHASE_2_EVENT_TRIGGER: ClassVar[int] = 1000

    @staticmethod
    def render_analytics_dashboard(analytics_data: dict) -> Div:
        """
        Render full analytics dashboard.

        Args:
            analytics_data: Dict with user_stats, activity_stats, search_gaps, etc.

        Returns:
            Div with analytics sections
        """
        user_stats = analytics_data.get("user_stats", {})
        activity_stats = analytics_data.get("activity_stats", {})
        search_gaps = analytics_data.get("search_gaps", [])
        search_event_total = analytics_data.get("search_event_total", 0)

        return Div(
            # User distribution section
            Card(
                CardHeader(CardTitle("User Distribution")),
                CardBody(AdminAnalyticsComponents.render_user_distribution(user_stats)),
                cls="mb-6",
            ),
            # Activity stats section
            Card(
                CardHeader(CardTitle("Activity Statistics (30 days)")),
                CardBody(AdminAnalyticsComponents.render_activity_stats(activity_stats)),
                cls="mb-6",
            ),
            # Search gaps section — the content authoring queue
            Card(
                CardHeader(CardTitle("Search Gaps (content authoring queue)")),
                CardBody(
                    AdminAnalyticsComponents.render_search_gaps(search_gaps, search_event_total)
                ),
                cls="mb-6",
            ),
        )

    @staticmethod
    def render_user_distribution(stats: dict) -> Div:
        """
        Render user distribution by role as bar chart.

        Args:
            stats: Dict with counts by role

        Returns:
            Div with visual role distribution
        """
        roles = [
            ("Admin", stats.get("admins", 0), ProgressT.error),
            ("Teacher", stats.get("teachers", 0), ProgressT.warning),
            ("Member", stats.get("members", 0), ProgressT.success),
            ("Registered", stats.get("registered", 0), ProgressT.info),
        ]

        total = sum(r[1] for r in roles) or 1  # Avoid division by zero

        bars = []
        for role_name, count, variant in roles:
            pct = (count / total) * 100
            bars.append(
                Div(
                    Div(
                        Span(role_name, cls="text-sm font-medium"),
                        Span(str(count), cls="text-sm text-muted-foreground"),
                        cls="flex justify-between mb-1",
                    ),
                    Progress(value=pct, variant=variant),
                    cls="mb-3",
                )
            )

        return Div(*bars)

    @staticmethod
    def render_activity_stats(activity_data: dict) -> Div:
        """
        Render activity statistics cards.

        Args:
            activity_data: Dict with activity counts

        Returns:
            Div with activity stats grid
        """
        return StatsGrid(
            [
                StatItem(
                    label="Tasks Created",
                    value=activity_data.get("tasks_created", 0),
                    color="success",
                ),
                StatItem(
                    label="Active Habits",
                    value=activity_data.get("habits_active", 0),
                    color="purple-600",
                ),
                StatItem(
                    label="Active Goals",
                    value=activity_data.get("goals_active", 0),
                    color="orange-600",
                ),
            ]
        )

    @staticmethod
    def render_search_gaps(gaps: list[dict], event_total: int) -> Div:
        """
        Render the zero/low-result search queue plus the running event total.

        Args:
            gaps: SearchGapRow dicts (query, searches, zero_count, avg_results,
                  last_seen, entry_points) from AdminOrchestrator.get_analytics_data
            event_total: Running :SearchEvent count vs the Phase-2 trigger

        Returns:
            Div with the gap table (or empty state) and the event-total line
        """
        total_line = P(
            f"{event_total:,} search event(s) logged — Phase 2 analytics "
            f"(clustering, temporal patterns) unlock at "
            f"{AdminAnalyticsComponents.PHASE_2_EVENT_TRIGGER:,}+.",
            cls="text-sm text-muted-foreground mt-3",
        )

        if not gaps:
            return Div(
                P(
                    "No zero/low-result searches recorded yet",
                    cls="text-sm text-muted-foreground",
                ),
                total_line,
            )

        body_data = []
        for gap in gaps:
            body_data.append(
                {
                    "Query": gap.get("query", ""),
                    "Searches": gap.get("searches", 0),
                    "Zero Results": gap.get("zero_count", 0),
                    "Avg Results": f"{float(gap.get('avg_results', 0.0)):.1f}",
                    # last_seen is toString(datetime) — the date part is enough here
                    "Last Seen": str(gap.get("last_seen", ""))[:10],
                    "Entry Points": ", ".join(gap.get("entry_points", [])),
                }
            )

        return Div(
            P(
                f"{len(gaps)} low/zero-result quer{'y' if len(gaps) == 1 else 'ies'} "
                f"(≤2 results, last 90 days)",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Div(
                TableFromDicts(
                    header_data=[
                        "Query",
                        "Searches",
                        "Zero Results",
                        "Avg Results",
                        "Last Seen",
                        "Entry Points",
                    ],
                    body_data=body_data,
                    cls=(TableT.striped,),
                ),
                cls="overflow-x-auto",
            ),
            total_line,
        )


class AdminSystemComponents:
    """System health components for admin dashboard."""

    STATUS_COLORS: ClassVar[dict[str, str]] = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
        "unknown": "bg-gray-400",
    }

    STATUS_TEXT_COLORS: ClassVar[dict[str, str]] = {
        "healthy": "text-success",
        "warning": "text-warning",
        "critical": "text-error",
        "unknown": "text-muted-foreground",
    }

    @staticmethod
    def render_health_dashboard(health_data: dict) -> Div:
        """
        Render system health dashboard.

        Args:
            health_data: Dict with component health status

        Returns:
            Div with health status sections
        """
        overall_status = health_data.get("status", "unknown")
        components = health_data.get("components", {})

        return Div(
            # Overall status
            Card(
                CardHeader(CardTitle("System Status")),
                CardBody(AdminSystemComponents.render_overall_status(overall_status)),
                cls="mb-6",
            ),
            # Component status
            Card(
                CardHeader(CardTitle("Component Health")),
                CardBody(AdminSystemComponents.render_components_grid(components)),
                cls="mb-6",
            ),
        )

    @staticmethod
    def render_overall_status(status: str) -> Div:
        """Render overall system status indicator."""
        bg_color = AdminSystemComponents.STATUS_COLORS.get(status, "bg-gray-400")
        text_color = AdminSystemComponents.STATUS_TEXT_COLORS.get(status, "text-muted-foreground")

        return Div(
            Div(
                Span(cls=f"w-4 h-4 rounded-full {bg_color} animate-pulse"),
                Span(
                    status.upper(),
                    cls=f"text-2xl font-bold {text_color} ml-3",
                ),
                cls="flex items-center",
            ),
            P(
                "All systems operational" if status == "healthy" else "Some systems need attention",
                cls="text-muted-foreground mt-2",
            ),
        )

    @staticmethod
    def render_component_health_card(name: str, data: dict) -> Div:
        """
        Render individual component health card.

        Args:
            name: Component name
            data: Health data dict with status, message, etc.

        Returns:
            Div with component health card
        """
        is_healthy = data.get("healthy", False)
        status = "healthy" if is_healthy else data.get("status", "critical")
        message = data.get("message", "")
        response_time = data.get("response_time_ms")

        bg_color = AdminSystemComponents.STATUS_COLORS.get(status, "bg-gray-400")
        text_color = AdminSystemComponents.STATUS_TEXT_COLORS.get(status, "text-muted-foreground")

        return Div(
            Div(
                Span(cls=f"w-3 h-3 rounded-full {bg_color}"),
                Span(name.replace("_", " ").title(), cls="font-medium ml-2"),
                cls="flex items-center mb-2",
            ),
            Span(status.capitalize(), cls=f"text-sm {text_color}"),
            P(message, cls="text-xs text-muted-foreground mt-1") if message else None,
            (
                P(f"Response: {response_time}ms", cls="text-xs text-muted-foreground")
                if response_time
                else None
            ),
            cls="p-3 bg-muted rounded-lg",
        )

    @staticmethod
    def render_components_grid(components: dict) -> Div:
        """Render grid of component health cards."""
        if not components:
            return render_error_banner(
                "No component health data returned — health check may have failed.",
                severity="warning",
            )

        cards = [
            AdminSystemComponents.render_component_health_card(name, data)
            for name, data in components.items()
        ]

        return Div(
            *cards,
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        )

    @staticmethod
    def render_health_summary(summary: dict) -> Div:
        """Render health summary stats."""
        return StatsGrid(
            [
                StatItem(
                    label="Total Components", value=summary.get("components_total", 0), color="info"
                ),
                StatItem(
                    label="Healthy", value=summary.get("components_healthy", 0), color="success"
                ),
                StatItem(
                    label="Unhealthy", value=summary.get("components_unhealthy", 0), color="error"
                ),
            ]
        )


def _ku_state_section(title: str, badge_variant: BadgeT, kus: list[dict], date_field: str) -> Div:
    """Render a section of KUs grouped by learning state."""
    items = []
    for ku in kus:
        ku_title = ku.get("title") or ku.get("uid") or "Untitled"
        date_val = ku.get(date_field, "")
        if date_val and "T" in str(date_val):
            date_val = str(date_val).split("T")[0]

        extra_info = []
        view_count = ku.get("view_count")
        if view_count is not None:
            extra_info.append(f"{view_count} views")
        mastery_score = ku.get("mastery_score")
        if mastery_score is not None:
            extra_info.append(f"score: {mastery_score}")

        items.append(
            Div(
                Div(
                    Span(ku_title, cls="font-medium text-sm"),
                    Div(
                        Span(
                            " | ".join(extra_info),
                            cls="text-xs text-muted-foreground mr-3",
                        )
                        if extra_info
                        else None,
                        Span(date_val or "", cls="text-xs text-muted-foreground"),
                        cls="flex items-center",
                    ),
                    cls="flex items-center justify-between",
                ),
                cls="border-b border-border py-2 last:border-b-0",
            )
        )

    return Div(
        Div(
            Badge(title, variant=badge_variant, cls="font-semibold"),
            Span(f"({len(kus)})", cls="text-sm text-muted-foreground ml-2"),
            cls="flex items-center mb-3",
        ),
        *items,
    )


class AdminLearningComponents:
    """Learning dashboard components for admin KU progression tracking."""

    @staticmethod
    def render_ku_system_metrics(metrics: dict) -> Div:
        """Render system-wide KU metrics cards."""
        if metrics.get("total_kus", 0) == 0:
            return Div(
                P(
                    "No Knowledge Units have been ingested yet. ",
                    A(
                        "Start Ingestion",
                        href="/ingest",
                        cls="text-primary hover:underline",
                    ),
                    " to populate the knowledge graph.",
                    cls="text-muted-foreground py-4",
                ),
            )

        return StatsGrid(
            [
                StatItem(label="Total KUs", value=metrics.get("total_kus", 0), color="info"),
                StatItem(
                    label="Total Views",
                    value=metrics.get("total_viewed", 0),
                    color="muted-foreground",
                ),
                StatItem(
                    label="In Progress",
                    value=metrics.get("total_in_progress", 0),
                    color="orange-600",
                ),
                StatItem(label="Mastered", value=metrics.get("total_mastered", 0), color="success"),
                StatItem(
                    label="Bookmarked", value=metrics.get("total_bookmarked", 0), color="indigo-600"
                ),
                StatItem(
                    label="Active Learners",
                    value=metrics.get("users_with_progress", 0),
                    color="purple-600",
                ),
            ]
        )

    @staticmethod
    def render_user_progress_table(user_progress: list[dict]) -> Div:
        """Render per-user KU progress as a table."""
        if not user_progress:
            return Div(
                P(
                    "No user learning activity recorded yet.",
                    cls="text-muted-foreground py-4",
                ),
            )

        def has_interactions(row: dict) -> bool:
            return (row.get("total_interactions") or 0) > 0

        has_any = any(has_interactions(row) for row in user_progress)

        if not has_any:
            return Div(
                P(
                    "Users exist but no KU interactions have been recorded. "
                    "Knowledge Units must be ingested first, then users "
                    "interact via the reading interface.",
                    cls="text-muted-foreground py-4",
                ),
            )

        centered_cols = {"Viewed", "In Progress", "Mastered", "Bookmarked", "Total"}

        def _progress_header_render(col: str) -> object:
            from ui.components.table import Th

            if col in centered_cols:
                return Th(col, cls="text-center")
            return Th(col)

        def _progress_cell_render(k: str, v: object) -> Any:
            if k == "Mastered":
                return Td(v, cls="text-center font-semibold")
            if k in centered_cols:
                return Td(v, cls="text-center")
            return Td(v)

        body_data = []
        for row in user_progress:
            display = row.get("display_name") or row.get("username") or row.get("uid", "Unknown")
            uid = row.get("uid", "")

            body_data.append(
                {
                    "User": A(
                        display,
                        href=f"/teaching/learning/user/{uid}",
                        cls="text-primary hover:underline font-medium",
                    ),
                    "Viewed": str(row.get("viewed_count", 0)),
                    "In Progress": str(row.get("in_progress_count", 0)),
                    "Mastered": str(row.get("mastered_count", 0)),
                    "Bookmarked": str(row.get("bookmarked_count", 0)),
                    "Total": str(row.get("total_interactions", 0)),
                }
            )

        return Div(
            TableFromDicts(
                header_data=["User", "Viewed", "In Progress", "Mastered", "Bookmarked", "Total"],
                body_data=body_data,
                header_cell_render=_progress_header_render,
                body_cell_render=_progress_cell_render,
                cls=(TableT.striped,),
            ),
            cls="overflow-x-auto",
        )

    @staticmethod
    def render_user_ku_summary(detail: dict) -> Div:
        """Render summary stats for one user's KU progress."""
        summary = detail.get("summary", {})
        total = (
            summary.get("viewed_count", 0)
            + summary.get("in_progress_count", 0)
            + summary.get("mastered_count", 0)
            + summary.get("bookmarked_count", 0)
        )

        if total == 0:
            return Div(
                P(
                    "This user has no KU interactions yet.",
                    cls="text-muted-foreground py-4",
                ),
            )

        return StatsGrid(
            [
                StatItem(
                    label="Viewed", value=summary.get("viewed_count", 0), color="muted-foreground"
                ),
                StatItem(
                    label="In Progress",
                    value=summary.get("in_progress_count", 0),
                    color="orange-600",
                ),
                StatItem(label="Mastered", value=summary.get("mastered_count", 0), color="success"),
                StatItem(
                    label="Bookmarked", value=summary.get("bookmarked_count", 0), color="indigo-600"
                ),
            ]
        )

    @staticmethod
    def render_user_ku_detail_list(detail: dict) -> Div:
        """Render detailed KU list with states for a user."""
        viewed = detail.get("viewed", [])
        in_progress = detail.get("in_progress", [])
        mastered = detail.get("mastered", [])
        bookmarked = detail.get("bookmarked", [])

        if not viewed and not in_progress and not mastered and not bookmarked:
            return Div(
                P(
                    "No Knowledge Unit interactions recorded for this user.",
                    cls="text-muted-foreground py-4",
                ),
            )

        sections = []

        if bookmarked:
            sections.append(
                _ku_state_section("Bookmarked", BadgeT.info, bookmarked, "bookmarked_at")
            )

        if mastered:
            sections.append(_ku_state_section("Mastered", BadgeT.success, mastered, "mastered_at"))

        if in_progress:
            sections.append(
                _ku_state_section("In Progress", BadgeT.warning, in_progress, "started_at")
            )

        if viewed:
            sections.append(_ku_state_section("Viewed", BadgeT.ghost, viewed, "last_viewed_at"))

        return Div(*sections, cls="space-y-6")

    @staticmethod
    def render_user_submissions_list(submissions: list[dict]) -> Div:
        """Render exercise submissions for the admin learning user detail page."""
        if not submissions:
            return EmptyState(title="No exercise submissions yet")

        from ui.enum_helpers import get_submission_status_badge_class

        def _cell_render(k: str, v: object) -> Any:
            if k == "Title":
                return Td(v, cls="font-medium text-sm")
            if k in ("Submitted", "Exercise"):  # skuel-lint: disable=SKUEL014 -- column labels
                return Td(v, cls="text-sm text-muted-foreground")
            return Td(v)

        body_data = []
        for sub in submissions:
            status = sub.get("status") or "unknown"
            title = sub.get("title") or sub.get("submission_uid") or "Untitled"
            exercise_title = sub.get("exercise_title") or "—"
            submitted_at = (sub.get("submitted_at") or "")[:10] or "Unknown"
            report_count = sub.get("report_count", 0)

            body_data.append(
                {
                    "Title": title,
                    "Exercise": exercise_title,
                    "Status": Badge(
                        status.replace("_", " ").upper(),
                        variant=None,
                        size=Size.sm,
                        cls=get_submission_status_badge_class(status),
                    ),
                    "Reports": str(report_count),
                    "Submitted": submitted_at,
                }
            )

        return Div(
            P(f"{len(submissions)} submission(s)", cls="text-sm text-muted-foreground mb-3"),
            Div(
                TableFromDicts(
                    header_data=["Title", "Exercise", "Status", "Reports", "Submitted"],
                    body_data=body_data,
                    body_cell_render=_cell_render,
                    cls=(TableT.striped,),
                ),
                cls="overflow-x-auto",
            ),
        )


__all__ = [
    "AdminAnalyticsComponents",
    "AdminLearningComponents",
    "AdminSystemComponents",
    "AdminUIComponents",
]
