"""
Admin Dashboard UI Components
=============================

UI components for the admin dashboard, including:
- User management (cards, tables, role forms)
- Analytics displays
- System health indicators

Usage:
    from components.admin_components import AdminUIComponents

    # Render user card
    card = AdminUIComponents.render_user_card(user_data)

    # Render user stats
    stats = AdminUIComponents.render_user_stats(stats_data)
"""

from typing import ClassVar

from fasthtml.common import A, Form, H2, P

from components.shared_ui_components import SharedUIComponents
from core.ui.daisy_components import (
    Button,
    Div,
    Option,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)


class AdminUIComponents:
    """User management UI components for admin dashboard."""

    # Role badge color mapping
    ROLE_COLORS: ClassVar[dict[str, str]] = {
        "admin": "badge-error",
        "teacher": "badge-warning",
        "member": "badge-success",
        "registered": "badge-info",
    }

    ROLE_BG_COLORS: ClassVar[dict[str, str]] = {
        "admin": "bg-red-100 text-red-800",
        "teacher": "bg-orange-100 text-orange-800",
        "member": "bg-green-100 text-green-800",
        "registered": "bg-blue-100 text-blue-800",
    }

    @staticmethod
    def render_role_badge(role: str) -> Span:
        """Render a role badge with appropriate color."""
        color_class = AdminUIComponents.ROLE_COLORS.get(role, "badge-neutral")
        return Span(
            role.upper(),
            cls=f"badge {color_class} font-semibold",
        )

    @staticmethod
    def render_status_badge(is_active: bool) -> Span:
        """Render active/inactive status badge."""
        if is_active:
            return Span("Active", cls="badge badge-success badge-outline")
        return Span("Inactive", cls="badge badge-ghost")

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
                A(
                    "View",
                    href=f"/admin/users/{uid}",
                    cls="btn btn-sm btn-ghost",
                ),
                Button(
                    "Edit Role",
                    cls="btn btn-sm btn-outline btn-primary",
                    hx_get=f"/admin/users/{uid}/role-form",
                    hx_target=f"#role-form-{uid.replace(':', '-')}",
                    hx_swap="innerHTML",
                ),
            ]
            if is_active:
                actions.append(
                    Button(
                        "Deactivate",
                        cls="btn btn-sm btn-outline btn-error",
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
                        cls="btn btn-sm btn-outline btn-success",
                        hx_post=f"/api/admin/users/{uid}/activate",
                        hx_swap="outerHTML",
                        hx_target=f"#user-card-{uid.replace(':', '-')}",
                    )
                )

        return Div(
            # Header with name and badges
            Div(
                Div(
                    Span(display_name, cls="text-lg font-semibold"),
                    Span(f"@{username}", cls="text-sm text-base-content/50 ml-2"),
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
                    Span("Email: ", cls="text-base-content/50"),
                    Span(email),
                    cls="text-sm",
                ),
                P(
                    Span("Last login: ", cls="text-base-content/50"),
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
            cls="card bg-base-100 shadow-sm p-4 border border-base-300",
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
            return Div(
                P("No users found", cls="text-center text-base-content/50 py-8"),
                cls="card bg-base-100 shadow-sm",
            )

        rows = []
        for user in users:
            uid = user.get("uid", "")
            username = user.get("username", "Unknown")
            email = user.get("email", "")
            role = user.get("role", "registered")
            is_active = user.get("is_active", True)
            last_login = user.get("last_login_at", "Never")

            if last_login and last_login != "Never" and "T" in str(last_login):
                last_login = str(last_login).split("T")[0]

            rows.append(
                Tr(
                    Td(username, cls="font-medium"),
                    Td(email, cls="text-base-content/70"),
                    Td(AdminUIComponents.render_role_badge(role)),
                    Td(AdminUIComponents.render_status_badge(is_active)),
                    Td(last_login, cls="text-sm text-base-content/50"),
                    Td(
                        A(
                            "View",
                            href=f"/admin/users/{uid}",
                            cls="btn btn-xs btn-ghost",
                        ),
                        cls="text-right",
                    ),
                    cls="hover:bg-base-200",
                )
            )

        return Div(
            Table(
                Thead(
                    Tr(
                        Th("Username"),
                        Th("Email"),
                        Th("Role"),
                        Th("Status"),
                        Th("Last Login"),
                        Th("", cls="text-right"),
                    ),
                    cls="bg-base-200",
                ),
                Tbody(*rows),
                cls="table table-zebra w-full",
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
                    cls="select select-bordered select-sm",
                ),
                Button(
                    "Save",
                    type="submit",
                    cls="btn btn-sm btn-primary",
                ),
                Button(
                    "Cancel",
                    type="button",
                    cls="btn btn-sm btn-ghost",
                    onclick="this.closest('form').remove()",
                ),
                cls="flex items-center gap-2",
            ),
            hx_post=f"/api/admin/users/{uid}/role",
            hx_swap="outerHTML",
            hx_target=f"#user-card-{uid.replace(':', '-')}",
            cls="bg-base-200 p-2 rounded-lg",
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
                cls="select select-bordered",
                hx_get="/admin/users/partial",
                hx_target="#user-list",
                hx_trigger="change",
                hx_include="[name='status']",
            ),
            cls="form-control",
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
                cls="select select-bordered",
                hx_get="/admin/users/partial",
                hx_target="#user-list",
                hx_trigger="change",
                hx_include="[name='role']",
            ),
            cls="form-control",
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
            Div(
                H2("User Distribution", cls="text-xl font-semibold mb-4"),
                AdminAnalyticsComponents.render_user_distribution(user_stats),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Activity stats section
            Div(
                H2("Activity Statistics (30 days)", cls="text-xl font-semibold mb-4"),
                AdminAnalyticsComponents.render_activity_stats(activity_stats),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
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
                        Span(str(count), cls="text-sm text-base-content/50"),
                        cls="flex justify-between mb-1",
                    ),
                    Div(
                        Div(
                            cls=f"{color} h-full rounded-full transition-all duration-300",
                            style=f"width: {pct}%",
                        ),
                        cls="h-4 bg-base-200 rounded-full overflow-hidden",
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
        "unknown": "text-gray-600",
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
            Div(
                H2("System Status", cls="text-xl font-semibold mb-4"),
                AdminSystemComponents.render_overall_status(overall_status),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
            # Component status
            Div(
                H2("Component Health", cls="text-xl font-semibold mb-4"),
                AdminSystemComponents.render_components_grid(components),
                cls="card bg-base-100 shadow-sm p-6 mb-6",
            ),
        )

    @staticmethod
    def render_overall_status(status: str) -> Div:
        """Render overall system status indicator."""
        bg_color = AdminSystemComponents.STATUS_COLORS.get(status, "bg-gray-400")
        text_color = AdminSystemComponents.STATUS_TEXT_COLORS.get(status, "text-gray-600")

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
                cls="text-base-content/50 mt-2",
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
        text_color = AdminSystemComponents.STATUS_TEXT_COLORS.get(status, "text-gray-600")

        return Div(
            Div(
                Span(cls=f"w-3 h-3 rounded-full {bg_color}"),
                Span(name.replace("_", " ").title(), cls="font-medium ml-2"),
                cls="flex items-center mb-2",
            ),
            Span(status.capitalize(), cls=f"text-sm {text_color}"),
            P(message, cls="text-xs text-base-content/50 mt-1") if message else None,
            (
                P(f"Response: {response_time}ms", cls="text-xs text-base-content/50")
                if response_time
                else None
            ),
            cls="p-3 bg-base-200 rounded-lg",
        )

    @staticmethod
    def render_components_grid(components: dict) -> Div:
        """Render grid of component health cards."""
        if not components:
            return P("No component data available", cls="text-base-content/50")

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


__all__ = [
    "AdminAnalyticsComponents",
    "AdminSystemComponents",
    "AdminUIComponents",
]
