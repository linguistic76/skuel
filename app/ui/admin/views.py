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

from fasthtml.common import H2, A, Div, Form, Option, P, Span, Td

from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card
from ui.data import TableFromDicts, TableT
from ui.feedback import Badge, BadgeT
from ui.forms import Select
from ui.layout import Size
from ui.patterns.entity_dashboard import SharedUIComponents


class AdminUIComponents:
    """User management UI components for admin dashboard."""

    @staticmethod
    def render_role_badge(role: str) -> Any:
        """Render a role badge with appropriate color."""
        from ui.badge_classes import role_badge_class

        color_class = role_badge_class(role)
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
    def render_user_card(user: dict, show_actions: bool = True) -> Div:
        """
        Render a user card with role badge and actions.

        Args:
            user: User data dict with uid, username, email, role, is_active, etc.
            show_actions: Whether to show action buttons

        Returns:
            Div containing the user card
        """
        uid = user.get("uid", "")
        username = user.get("username", "Unknown")
        email = user.get("email", "")
        role = user.get("role", "registered")
        is_active = user.get("is_active", True)
        display_name = user.get("display_name", username)
        last_login = user.get("last_login_at", "Never")

        # Format last login - show date portion if it's a full datetime
        if last_login and last_login != "Never" and "T" in str(last_login):
            last_login = str(last_login).split("T")[0]

        # Action buttons
        actions = []
        if show_actions:
            actions = [
                ButtonLink(
                    "View",
                    href=f"/admin/users/{uid}",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                Button(
                    "Edit Role",
                    variant=ButtonT.outline,
                    size=Size.sm,
                    cls="uk-btn-primary",
                    hx_get=f"/admin/users/{uid}/role-form",
                    hx_target=f"#role-form-{uid.replace(':', '-')}",
                    hx_swap="innerHTML",
                ),
            ]
            if is_active:
                actions.append(
                    Button(
                        "Deactivate",
                        variant=ButtonT.outline,
                        size=Size.sm,
                        cls="uk-btn-destructive",
                        hx_post=f"/api/admin/users/{uid}/deactivate",
                        hx_confirm="Are you sure you want to deactivate this user?",
                        hx_swap="outerHTML",
                        hx_target=f"#user-card-{uid.replace(':', '-')}",
                    )
                )
            else:
                actions.append(
                    Button(
                        "Activate",
                        variant=ButtonT.outline,
                        size=Size.sm,
                        cls="uk-btn-primary",
                        hx_post=f"/api/admin/users/{uid}/activate",
                        hx_swap="outerHTML",
                        hx_target=f"#user-card-{uid.replace(':', '-')}",
                    )
                )

        return Card(
            # Header with name and badges
            Div(
                Div(
                    Span(display_name, cls="text-lg font-semibold"),
                    Span(f"@{username}", cls="text-sm text-muted-foreground ml-2"),
                    cls="flex items-center gap-2",
                ),
                Div(
                    AdminUIComponents.render_role_badge(role),
                    AdminUIComponents.render_status_badge(is_active),
                    cls="flex items-center gap-2",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            # Details
            Div(
                P(
                    Span("Email: ", cls="text-muted-foreground"),
                    Span(email),
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
            Div(id=f"role-form-{uid.replace(':', '-')}", cls="mb-3"),
            # Actions
            Div(*actions, cls="flex flex-wrap gap-2") if actions else None,
            id=f"user-card-{uid.replace(':', '-')}",
            cls="bg-background shadow-sm p-4 border border-border",
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
                P("No users found", cls="text-center text-muted-foreground py-8"),
                cls="bg-background shadow-sm",
            )

        def _user_cell_render(k: str, v: object) -> Td:
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
                        variant=ButtonT.ghost,
                        size=Size.xs,
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
    def render_role_change_form(user: dict) -> Form:
        """
        Render form for changing user role.

        Args:
            user: User data dict

        Returns:
            Form for role change with HTMX
        """
        uid = user.get("uid", "")
        current_role = user.get("role", "registered")

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
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                Button(
                    "Cancel",
                    type="button",
                    variant=ButtonT.ghost,
                    size=Size.sm,
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
        stats_config = {
            "total": {
                "label": "Total Users",
                "value": stats.get("total", 0),
                "color": "blue",
            },
            "admins": {
                "label": "Admins",
                "value": stats.get("admins", 0),
                "color": "red",
            },
            "teachers": {
                "label": "Teachers",
                "value": stats.get("teachers", 0),
                "color": "orange",
            },
            "members": {
                "label": "Members",
                "value": stats.get("members", 0),
                "color": "green",
            },
            "registered": {
                "label": "Free Users",
                "value": stats.get("registered", 0),
                "color": "gray",
            },
        }
        return SharedUIComponents.render_stats_cards(stats_config)

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
            return Div(
                P("No users found", cls="text-center text-muted-foreground py-8"),
            )

        centered_cols = {"Tasks", "Goals", "Habits", "KUs"}

        def _activity_header_render(col: str) -> object:
            from fasthtml.common import Th

            if col in centered_cols:
                return Th(col, cls="text-center")
            if col == "":
                return Th("", cls="text-right")
            return Th(col)

        def _activity_cell_render(k: str, v: object) -> Td:
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
                        variant=ButtonT.ghost,
                        size=Size.xs,
                        cls="text-primary",
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
    def render_user_activity_stats(stats: dict, user_uid: str) -> Div:
        """Render comprehensive activity, learning, and session stats for a user.

        Args:
            stats: Dict from _get_user_detail_stats() with all count fields.
            user_uid: User UID for linking to learning detail page.
        """
        # Activity domains
        activity_stats = {
            "tasks": {
                "label": f"Tasks ({stats.get('tasks_completed', 0)} completed)",
                "value": stats.get("tasks_total", 0),
                "color": "blue",
            },
            "goals": {
                "label": f"Goals ({stats.get('goals_active', 0)} active)",
                "value": stats.get("goals_total", 0),
                "color": "green",
            },
            "habits": {
                "label": f"Habits ({stats.get('habits_active', 0)} active)",
                "value": stats.get("habits_total", 0),
                "color": "purple",
            },
            "events": {
                "label": "Events",
                "value": stats.get("events_total", 0),
                "color": "orange",
            },
            "choices": {
                "label": "Choices",
                "value": stats.get("choices_total", 0),
                "color": "indigo",
            },
            "principles": {
                "label": "Principles",
                "value": stats.get("principles_total", 0),
                "color": "yellow",
            },
        }

        # Learning progress
        learning_stats = {
            "viewed": {
                "label": "KUs Viewed",
                "value": stats.get("ku_viewed", 0),
                "color": "gray",
            },
            "in_progress": {
                "label": "KUs In Progress",
                "value": stats.get("ku_in_progress", 0),
                "color": "orange",
            },
            "mastered": {
                "label": "KUs Mastered",
                "value": stats.get("ku_mastered", 0),
                "color": "green",
            },
        }

        # Session stats
        session_stats = {
            "logins": {
                "label": "Total Logins",
                "value": stats.get("login_count", 0),
                "color": "blue",
            },
            "sessions": {
                "label": "Total Sessions",
                "value": stats.get("session_count", 0),
                "color": "purple",
            },
        }

        return Div(
            # Activity domains section
            Div(
                Div(
                    Span("Activity Domains", cls="text-lg font-semibold"),
                    cls="mb-3",
                ),
                SharedUIComponents.render_stats_cards(activity_stats),
                cls="mb-6",
            ),
            # Learning progress section
            Div(
                Div(
                    Span("Learning Progress", cls="text-lg font-semibold"),
                    A(
                        "View Full KU Detail →",
                        href=f"/admin/learning/user/{user_uid}",
                        cls="text-primary hover:underline text-sm ml-4",
                    ),
                    cls="flex items-center mb-3",
                ),
                SharedUIComponents.render_stats_cards(learning_stats),
                cls="mb-6",
            ),
            # Session activity section
            Div(
                Div(
                    Span("Session Activity", cls="text-lg font-semibold"),
                    cls="mb-3",
                ),
                SharedUIComponents.render_stats_cards(session_stats),
            ),
        )

    @staticmethod
    def render_user_reports_list(reports: list, _user_uid: str) -> Div:
        """Render a list of user reports for admin user detail page.

        Args:
            reports: List of Report domain objects.
            _user_uid: User UID (reserved for future linking).
        """
        if not reports:
            return Div(
                P("No reports submitted yet.", cls="text-muted-foreground text-sm py-4"),
            )

        from ui.badge_classes import submission_status_badge_class

        def _report_cell_render(k: str, v: object) -> Td:
            if k == "Title":
                return Td(v, cls="font-medium text-sm")
            if k == "Created":
                return Td(v, cls="text-sm text-muted-foreground")
            return Td(v)

        body_data = []
        for report in reports:
            report_type = report.report_type.value if report.report_type else "unknown"
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
                        cls=submission_status_badge_class(status),
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

    @staticmethod
    def render_user_projects_list(projects: list, _user_uid: str) -> Div:
        """Render a list of user assignments for admin user detail page.

        Args:
            projects: List of Assignment domain objects.
            _user_uid: User UID (reserved for future linking).
        """
        if not projects:
            return Div(
                P("No report projects found.", cls="text-muted-foreground text-sm py-4"),
            )

        def _project_cell_render(k: str, v: object) -> Td:
            if k == "Name":
                return Td(v, cls="font-medium text-sm")
            if k == "Created":
                return Td(v, cls="text-sm text-muted-foreground")
            return Td(v)

        body_data = []
        for project in projects:
            name = project.name or project.uid
            scope = getattr(project, "scope", "personal")
            is_active = getattr(project, "is_active", True)
            created = ""
            raw_created = getattr(project, "created_at", None)
            if raw_created:
                strftime_fn = getattr(raw_created, "strftime", None)
                created = strftime_fn("%Y-%m-%d") if strftime_fn else str(raw_created)[:10]

            body_data.append(
                {
                    "Name": name,
                    "Scope": Badge(str(scope).upper(), variant=BadgeT.outline, size=Size.sm),
                    "Status": (
                        Badge("Active", variant=BadgeT.success, size=Size.sm)
                        if is_active
                        else Badge("Inactive", variant=BadgeT.ghost, size=Size.sm)
                    ),
                    "Created": created,
                }
            )

        return Div(
            P(f"{len(projects)} project(s)", cls="text-sm text-muted-foreground mb-3"),
            Div(
                TableFromDicts(
                    header_data=["Name", "Scope", "Status", "Created"],
                    body_data=body_data,
                    body_cell_render=_project_cell_render,
                    cls=(TableT.striped,),
                ),
                cls="overflow-x-auto",
            ),
        )


class AdminAnalyticsComponents:
    """Analytics components for admin dashboard."""

    @staticmethod
    def render_analytics_dashboard(analytics_data: dict) -> Div:
        """
        Render full analytics dashboard.

        Args:
            analytics_data: Dict with user_stats, activity_stats, etc.

        Returns:
            Div with analytics sections
        """
        user_stats = analytics_data.get("user_stats", {})
        activity_stats = analytics_data.get("activity_stats", {})

        return Div(
            # User distribution section
            Card(
                H2("User Distribution", cls="text-xl font-semibold mb-4"),
                AdminAnalyticsComponents.render_user_distribution(user_stats),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Activity stats section
            Card(
                H2("Activity Statistics (30 days)", cls="text-xl font-semibold mb-4"),
                AdminAnalyticsComponents.render_activity_stats(activity_stats),
                cls="bg-background shadow-sm p-6 mb-6",
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
            ("Admin", stats.get("admins", 0), "bg-red-500"),
            ("Teacher", stats.get("teachers", 0), "bg-orange-500"),
            ("Member", stats.get("members", 0), "bg-green-500"),
            ("Registered", stats.get("registered", 0), "bg-blue-500"),
        ]

        total = sum(r[1] for r in roles) or 1  # Avoid division by zero

        bars = []
        for role_name, count, color in roles:
            pct = (count / total) * 100
            bars.append(
                Div(
                    Div(
                        Span(role_name, cls="text-sm font-medium"),
                        Span(str(count), cls="text-sm text-muted-foreground"),
                        cls="flex justify-between mb-1",
                    ),
                    Div(
                        Div(
                            cls=f"{color} h-full rounded-full transition-all duration-300",
                            style=f"width: {pct}%",
                        ),
                        cls="h-4 bg-muted rounded-full overflow-hidden",
                    ),
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
        stats_config = {
            "tasks": {
                "label": "Tasks Created",
                "value": activity_data.get("tasks_created", 0),
                "color": "green",
            },
            "habits": {
                "label": "Active Habits",
                "value": activity_data.get("habits_active", 0),
                "color": "purple",
            },
            "goals": {
                "label": "Active Goals",
                "value": activity_data.get("goals_active", 0),
                "color": "orange",
            },
            "journals": {
                "label": "Journals Submitted",
                "value": activity_data.get("journals_submitted", 0),
                "color": "blue",
            },
        }
        return SharedUIComponents.render_stats_cards(stats_config)


class AdminSystemComponents:
    """System health components for admin dashboard."""

    STATUS_COLORS: ClassVar[dict[str, str]] = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
        "unknown": "bg-gray-400",
    }

    STATUS_TEXT_COLORS: ClassVar[dict[str, str]] = {
        "healthy": "text-green-600",
        "warning": "text-yellow-600",
        "critical": "text-red-600",
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
                H2("System Status", cls="text-xl font-semibold mb-4"),
                AdminSystemComponents.render_overall_status(overall_status),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            # Component status
            Card(
                H2("Component Health", cls="text-xl font-semibold mb-4"),
                AdminSystemComponents.render_components_grid(components),
                cls="bg-background shadow-sm p-6 mb-6",
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
            return P("No component data available", cls="text-muted-foreground")

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
        stats_config = {
            "total": {
                "label": "Total Components",
                "value": summary.get("components_total", 0),
                "color": "blue",
            },
            "healthy": {
                "label": "Healthy",
                "value": summary.get("components_healthy", 0),
                "color": "green",
            },
            "unhealthy": {
                "label": "Unhealthy",
                "value": summary.get("components_unhealthy", 0),
                "color": "red",
            },
        }
        return SharedUIComponents.render_stats_cards(stats_config)


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

        stats_config = {
            "total": {
                "label": "Total KUs",
                "value": metrics.get("total_kus", 0),
                "color": "blue",
            },
            "viewed": {
                "label": "Total Views",
                "value": metrics.get("total_viewed", 0),
                "color": "gray",
            },
            "in_progress": {
                "label": "In Progress",
                "value": metrics.get("total_in_progress", 0),
                "color": "orange",
            },
            "mastered": {
                "label": "Mastered",
                "value": metrics.get("total_mastered", 0),
                "color": "green",
            },
            "bookmarked": {
                "label": "Bookmarked",
                "value": metrics.get("total_bookmarked", 0),
                "color": "indigo",
            },
            "active_learners": {
                "label": "Active Learners",
                "value": metrics.get("users_with_progress", 0),
                "color": "purple",
            },
        }
        return SharedUIComponents.render_stats_cards(stats_config)

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
            from fasthtml.common import Th

            if col in centered_cols:
                return Th(col, cls="text-center")
            return Th(col)

        def _progress_cell_render(k: str, v: object) -> Td:
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
                        href=f"/admin/learning/user/{uid}",
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

        stats_config = {
            "viewed": {
                "label": "Viewed",
                "value": summary.get("viewed_count", 0),
                "color": "gray",
            },
            "in_progress": {
                "label": "In Progress",
                "value": summary.get("in_progress_count", 0),
                "color": "orange",
            },
            "mastered": {
                "label": "Mastered",
                "value": summary.get("mastered_count", 0),
                "color": "green",
            },
            "bookmarked": {
                "label": "Bookmarked",
                "value": summary.get("bookmarked_count", 0),
                "color": "indigo",
            },
        }
        return SharedUIComponents.render_stats_cards(stats_config)

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


__all__ = [
    "AdminAnalyticsComponents",
    "AdminLearningComponents",
    "AdminSystemComponents",
    "AdminUIComponents",
]
