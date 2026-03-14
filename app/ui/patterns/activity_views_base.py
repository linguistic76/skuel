"""
Activity Views Base Components
==============================

Shared components for Activity Domain three-view interfaces.
Provides reusable tab navigation, calendar navigation, view switchers,
filter bars, create form wrappers, and calendar view helpers.

Usage:
    from ui.patterns.activity_views_base import (
        ActivityViewTabs, ActivityCalendarNav, ActivityListFilters,
        ActivityCreateForm, render_activity_calendar,
    )

    tabs = ActivityViewTabs.render("goals", "list", [
        ("list", "List", "List"),
        ("create", "Create", "+"),
        ("calendar", "Calendar", "Cal"),
    ])
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H2,
    H3,
    A,
    Div,
    Form,
    Option,
    Span,
)

from ui.buttons import Button, ButtonLink, ButtonT
from ui.layout import Size


class ActivityViewTabs:
    """
    Generic three-tab navigation for Activity Domains.

    Uses Tabs with HTMX for dynamic content loading.
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
    """Unified filter bar for activity domain list views."""

    @staticmethod
    def render(
        domain: str,
        status_options: list[tuple[str, str]],
        sort_options: list[tuple[str, str]],
        current_status: str = "active",
        current_sort: str = "created_at",
        list_target: str | None = None,
        filter_name: str = "filter_status",
        filter_label: str = "Status",
        extra_filters: list[Any] | None = None,
    ) -> Div:
        """Render the full filter bar with status/type dropdown, sort dropdown, and extras.

        Args:
            domain: Domain name for route URLs
            status_options: (value, label) tuples for the primary filter
            sort_options: (value, label) tuples for the sort dropdown
            current_status: Currently selected primary filter value
            current_sort: Currently selected sort value
            list_target: HTMX target ID (defaults to #{domain}-list)
            filter_name: Name attribute for the primary filter (default: filter_status)
            filter_label: Display label for the primary filter (default: Status)
            extra_filters: Additional filter Divs to insert between primary and sort
        """
        from ui.forms import Label, Select

        target = list_target or f"#{domain}-list"

        primary_filter = Div(
            Label(f"{filter_label}:", cls="mr-2 text-sm"),
            Select(
                *[
                    Option(label, value=value, selected=(value == current_status))
                    for value, label in status_options
                ],
                name=filter_name,
                size=Size.sm,
                full_width=False,
                **{
                    "hx-get": f"/{domain}/list-fragment",
                    "hx-target": target,
                    "hx-include": "[name^='filter_'], [name='sort_by']",
                },
            ),
            cls="mr-4",
        )

        sort_filter = Div(
            Label("Sort:", cls="mr-2 text-sm"),
            Select(
                *[
                    Option(label, value=value, selected=(value == current_sort))
                    for value, label in sort_options
                ],
                name="sort_by",
                size=Size.sm,
                full_width=False,
                **{
                    "hx-get": f"/{domain}/list-fragment",
                    "hx-target": target,
                    "hx-include": "[name^='filter_']",
                },
            ),
        )

        children = [primary_filter]
        if extra_filters:
            children.extend(extra_filters)
        children.append(sort_filter)

        return Div(*children, cls="flex items-center mb-4")


def ActivityCreateForm(
    domain: str,
    entity_label: str,
    left_column: Any,
    right_column: Any,
    extra_sections: list[Any] | None = None,
    form_attrs: dict[str, str] | None = None,
    include_default_submit: bool = True,
) -> Div:
    """Shared create form wrapper for activity domains.

    Args:
        domain: URL path segment (e.g. "goals")
        entity_label: Display name (e.g. "Goal")
        left_column: Left column content (Div)
        right_column: Right column content (Div)
        extra_sections: Additional sections after columns (before default submit)
        form_attrs: Extra attributes on the Form element (e.g. x-data)
        include_default_submit: If False, skips the default Cancel/Create/Create & Add Another buttons
    """
    form_children: list[Any] = [
        Div(left_column, right_column, cls="flex flex-col lg:flex-row gap-8"),
    ]
    if extra_sections:
        form_children.extend(extra_sections)

    if include_default_submit:
        submit_section = Div(
            ButtonLink("Cancel", href=f"/{domain}", variant=ButtonT.ghost, size=Size.lg),
            Button(f"Create {entity_label}", type="submit", variant=ButtonT.primary, size=Size.lg),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                variant=ButtonT.outline,
                size=Size.lg,
            ),
            cls="flex justify-end gap-2 pt-6 border-t border-border",
        )
        form_children.append(submit_section)

    form_kwargs: dict[str, Any] = {
        "hx-post": f"/{domain}/quick-add",
        "hx-target": "#view-content",
        "hx-swap": "innerHTML",
    }
    if form_attrs:
        form_kwargs.update(form_attrs)

    return Div(
        H2(f"Create New {entity_label}", cls="text-2xl font-bold mb-6"),
        Form(*form_children, cls="bg-background shadow-lg p-6", **form_kwargs),
        id="create-view",
    )


def render_activity_calendar(
    domain: str,
    entities: list[Any],
    converter: Callable[[Any], Any],
    current_date: date | None = None,
    calendar_view: str = "month",
    converter_returns_list: bool = False,
    converter_extra_args: tuple[Any, ...] = (),
) -> Div:
    """Shared calendar rendering for activity domains.

    Args:
        domain: Domain name for route URLs
        entities: List of domain entities to display
        converter: Function to convert entity -> CalendarItem (or list)
        current_date: Current date (defaults to today)
        calendar_view: "month", "week", or "day"
        converter_returns_list: True if converter returns list[CalendarItem]
        converter_extra_args: Extra positional args passed to converter after entity
    """
    from core.models.event.calendar_models import CalendarData, CalendarView
    from core.utils.logging import get_logger
    from ui.calendar.components import (
        create_day_timeline,
        create_month_grid,
        create_reschedule_form,
        create_week_grid,
    )

    logger = get_logger(f"skuel.components.{domain}_views")
    current_date = current_date or date.today()

    # Convert entities to CalendarItems
    calendar_items: list[Any] = []
    for entity in entities:
        try:
            result = converter(entity, *converter_extra_args)
            if converter_returns_list:
                calendar_items.extend(result)
            elif result is not None:
                calendar_items.append(result)
        except Exception as e:
            logger.warning(f"Failed to convert {domain} entity to calendar item: {e}")
            continue

    # Calculate date range
    if calendar_view == "day":
        start_date = current_date
        end_date = current_date
        view_type = CalendarView.DAY
    elif calendar_view == "week":
        days_since_monday = current_date.weekday()
        start_date = current_date - timedelta(days=days_since_monday)
        end_date = start_date + timedelta(days=6)
        view_type = CalendarView.WEEK
    else:  # month
        start_date = current_date.replace(day=1)
        if current_date.month == 12:
            end_date = current_date.replace(
                year=current_date.year + 1, month=1, day=1
            ) - timedelta(days=1)
        else:
            end_date = current_date.replace(
                month=current_date.month + 1, day=1
            ) - timedelta(days=1)
        view_type = CalendarView.MONTH

    # Filter items to date range
    filtered_items = [
        item
        for item in calendar_items
        if start_date <= item.start_time.date() <= end_date
        or (hasattr(item, "end_time") and start_date <= item.end_time.date() <= end_date)
    ]

    calendar_data = CalendarData(
        items=filtered_items,
        occurrences={},
        view=view_type,
        start_date=start_date,
        end_date=end_date,
        metadata={},
    )

    nav_header = ActivityCalendarNav.render(domain, current_date, calendar_view)
    view_switcher = ActivityViewSwitcher.render(domain, current_date, calendar_view)

    if calendar_view == "day":
        grid = create_day_timeline(calendar_data)
    elif calendar_view == "week":
        grid = create_week_grid(calendar_data)
    else:
        grid = create_month_grid(calendar_data)

    return Div(
        Div(
            nav_header,
            view_switcher,
            cls="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-4",
        ),
        Div(grid, id="calendar-grid"),
        create_reschedule_form(),
        id="calendar-view",
        **{"x-data": "calendarDrag()"},
    )


__all__ = [
    "ActivityViewTabs",
    "ActivityCalendarNav",
    "ActivityViewSwitcher",
    "ActivityListFilters",
    "ActivityCreateForm",
    "render_activity_calendar",
]
