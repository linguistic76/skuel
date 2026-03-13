"""
Activity Views Base Components
==============================

Shared components for Activity Domain three-view interfaces.
Provides reusable tab navigation, calendar navigation, and view switchers.

Usage:
    from ui.patterns.activity_views_base import ActivityViewTabs, ActivityCalendarNav

    tabs = ActivityViewTabs.render("goals", "list", [
        ("list", "List", "List"),
        ("create", "Create", "+"),
        ("calendar", "Calendar", "Cal"),
    ])
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H3,
    A,
    Div,
    Span,
)

from ui.buttons import Button, ButtonT
from ui.layout import Size


class ActivityViewTabs:
    """
    Generic three-tab navigation for Activity Domains.

    Uses DaisyUI tabs with HTMX for dynamic content loading.
    """

    @staticmethod
    def render(
        domain: str,
        active_view: str,
        tabs: list[tuple[str, str, str]],
    ) -> Div:
        """
        Render tab navigation for an activity domain.

        Matches the Tasks domain's superior UX with full-width tabs.

        Args:
            domain: Domain name (goals, habits, events, choices, principles)
            active_view: Currently active view (list, create, calendar, analytics)
            tabs: List of (view_id, desktop_label, mobile_label) tuples

        Returns:
            Div containing the tab navigation
        """

        def tab_class_base() -> str:
            # Base tab styling (active state managed by Alpine.js)
            return "flex-1 py-3 px-6 text-center font-medium text-base cursor-pointer transition-colors"

        tab_elements = []
        for view_id, desktop_label, mobile_label in tabs:
            is_active = view_id == active_view
            tab_elements.append(
                A(
                    Span(desktop_label, cls="hidden sm:inline"),
                    Span(mobile_label, cls="sm:hidden"),
                    href=f"/{domain}?view={view_id}",
                    role="tab",
                    cls=tab_class_base(),
                    **{
                        # HTMX attributes
                        "hx-get": f"/{domain}/view/{view_id}",
                        "hx-target": "#view-content",
                        "hx-push-url": f"/{domain}?view={view_id}",
                        # Alpine.js bindings for WCAG 2.1 Level AA compliance
                        ":aria-selected": f"activeTab === '{view_id}' ? 'true' : 'false'",
                        ":tabindex": f"activeTab === '{view_id}' ? 0 : -1",
                        # Dynamic classes for active state
                        ":class": f"{{'bg-blue-600 text-white rounded-lg': activeTab === '{view_id}', 'text-muted-foreground hover:bg-muted rounded-lg': activeTab !== '{view_id}'}}",
                        # Alpine.js event handlers
                        "@click": f"setActiveTab('{view_id}')",
                        "@keydown": f"handleTabKeydown($event, '{view_id}')",
                        # Initial ARIA state (before Alpine.js hydration)
                        "aria-selected": "true" if is_active else "false",
                        "tabindex": 0 if is_active else -1,
                    },
                )
            )

        return Div(
            Div(
                *tab_elements,
                role="tablist",
                cls="flex w-full",
                # Alpine.js accessible tabs component
                **{"x-data": f"accessibleTabs({{ activeTab: '{active_view}' }})"},
            ),
            cls="mb-6",
        )

    @staticmethod
    def list_create_calendar(domain: str, active_view: str = "list") -> Div:
        """
        Render standard List/Create/Calendar tabs.

        For time-based domains: Tasks, Goals, Habits.
        """
        return ActivityViewTabs.render(
            domain=domain,
            active_view=active_view,
            tabs=[
                ("list", "List", "List"),
                ("create", "Create", "+"),
                ("calendar", "Calendar", "Cal"),
            ],
        )

    @staticmethod
    def calendar_list_create(domain: str, active_view: str = "calendar") -> Div:
        """
        Render Calendar/List/Create tabs (calendar-first).

        For Events domain where calendar is the primary view.
        """
        return ActivityViewTabs.render(
            domain=domain,
            active_view=active_view,
            tabs=[
                ("calendar", "Calendar", "Cal"),
                ("list", "List", "List"),
                ("create", "Create", "+"),
            ],
        )

    @staticmethod
    def list_create_analytics(domain: str, active_view: str = "list") -> Div:
        """
        Render List/Create/Analytics tabs.

        For value-based domains: Choices, Principles.
        """
        return ActivityViewTabs.render(
            domain=domain,
            active_view=active_view,
            tabs=[
                ("list", "List", "List"),
                ("create", "Create", "+"),
                ("analytics", "Analytics", "Stats"),
            ],
        )


class ActivityCalendarNav:
    """
    Calendar navigation component with prev/next/today buttons.
    """

    @staticmethod
    def render(
        domain: str,
        current_date: date,
        view: str,  # month, week, day
    ) -> Div:
        """
        Render calendar navigation with prev/next buttons.

        Args:
            domain: Domain name for route URLs
            current_date: Current date being displayed
            view: Current calendar view (month, week, day)

        Returns:
            Div containing navigation buttons and date label
        """
        # Calculate prev/next dates based on view
        if view == "day":
            prev_date = current_date - timedelta(days=1)
            next_date = current_date + timedelta(days=1)
            date_label = current_date.strftime("%A, %B %d, %Y")
        elif view == "week":
            prev_date = current_date - timedelta(days=7)
            next_date = current_date + timedelta(days=7)
            # Show week range
            days_since_monday = current_date.weekday()
            week_start = current_date - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            date_label = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        else:  # month
            # Previous month
            if current_date.month == 1:
                prev_date = current_date.replace(year=current_date.year - 1, month=12, day=1)
            else:
                prev_date = current_date.replace(month=current_date.month - 1, day=1)
            # Next month
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1, day=1)
            date_label = current_date.strftime("%B %Y")

        return Div(
            Button(
                "<",
                variant=ButtonT.ghost,
                size=Size.sm,
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view={view}&date={prev_date.isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            H3(date_label, cls="text-xl font-bold mx-4"),
            Button(
                ">",
                variant=ButtonT.ghost,
                size=Size.sm,
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view={view}&date={next_date.isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            Button(
                "Today",
                variant=ButtonT.outline,
                size=Size.sm,
                cls="ml-2",
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view={view}&date={date.today().isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            cls="flex items-center",
        )


class ActivityViewSwitcher:
    """
    Month/Week/Day view switcher for calendar views.
    """

    @staticmethod
    def render(
        domain: str,
        current_date: date,
        active_view: str,  # month, week, day
    ) -> Div:
        """
        Render Month/Week/Day view switcher buttons.

        Args:
            domain: Domain name for route URLs
            current_date: Current date being displayed
            active_view: Currently active view (month, week, day)

        Returns:
            Div containing view switcher buttons
        """

        def btn_variant(view: str) -> ButtonT:
            return ButtonT.primary if view == active_view else ButtonT.ghost

        return Div(
            Button(
                "Month",
                variant=btn_variant("month"),
                size=Size.sm,
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view=month&date={current_date.isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            Button(
                "Week",
                variant=btn_variant("week"),
                size=Size.sm,
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view=week&date={current_date.isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            Button(
                "Day",
                variant=btn_variant("day"),
                size=Size.sm,
                **{
                    "hx-get": f"/{domain}/view/calendar?calendar_view=day&date={current_date.isoformat()}",
                    "hx-target": "#view-content",
                },
            ),
            cls="btn-group",
        )


class ActivityListFilters:
    """
    Common filter bar patterns for list views.
    """

    @staticmethod
    def render_status_filter(
        domain: str,
        statuses: list[tuple[str, str]],  # (value, label)
        current_status: str = "active",
    ) -> Div:
        """
        Render status filter pills.

        Args:
            domain: Domain name for route URLs
            statuses: List of (value, label) tuples
            current_status: Currently selected status

        Returns:
            Div containing status filter buttons
        """
        buttons = []
        for value, label in statuses:
            variant = ButtonT.primary if value == current_status else ButtonT.ghost
            buttons.append(
                Button(
                    label,
                    variant=variant,
                    size=Size.sm,
                    **{
                        "hx-get": f"/{domain}/list-fragment?filter_status={value}",
                        "hx-target": "#entity-list",
                    },
                )
            )

        return Div(*buttons, cls="btn-group")

    @staticmethod
    def render_sort_dropdown(
        domain: str,
        sort_options: list[tuple[str, str]],  # (value, label)
        current_sort: str = "created_at",
    ) -> Any:
        """
        Render sort dropdown.

        Args:
            domain: Domain name for route URLs
            sort_options: List of (value, label) tuples
            current_sort: Currently selected sort option

        Returns:
            Select element for sorting
        """
        from fasthtml.common import Option

        from ui.forms import Select

        options = [
            Option(label, value=value, selected=(value == current_sort))
            for value, label in sort_options
        ]

        return Select(
            *options,
            size=Size.sm,
            full_width=False,
            **{
                "hx-get": f"/{domain}/list-fragment",
                "hx-target": "#entity-list",
                "hx-include": "[name^='filter_']",
                "name": "sort_by",
            },
        )


__all__ = [
    "ActivityViewTabs",
    "ActivityCalendarNav",
    "ActivityViewSwitcher",
    "ActivityListFilters",
]
