"""Shared primitive components for profile domain views.

Reusable building blocks consumed by curriculum_views.py and overview.py.
"""

from typing import Any

from fasthtml.common import H3, A, Div, Label, Li, Option, P, Select, Span, Ul

from ui.buttons import Button, ButtonT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState


def DomainFilterControls(domain: str, total_count: int) -> Div:
    """Filter and sort controls for domain views.

    Args:
        domain: Domain name (tasks, goals, habits, etc.)
        total_count: Total number of items in the domain

    Returns:
        Div with filter/sort controls
    """
    # Domain-specific filter presets
    filter_presets = {
        "tasks": [
            ("all", "All Tasks"),
            ("overdue", "Overdue"),
            ("high_priority", "High Priority"),
            ("this_week", "This Week"),
        ],
        "goals": [
            ("all", "All Goals"),
            ("at_risk", "At Risk"),
            ("near_complete", "Almost Done"),
        ],
        "habits": [
            ("all", "All Habits"),
            ("at_risk", "At Risk"),
            ("keystone", "Keystone"),
        ],
        "events": [
            ("all", "All Events"),
            ("today", "Today"),
            ("this_week", "This Week"),
        ],
        "choices": [("all", "All Choices")],
        "principles": [("all", "All Principles")],
    }

    # Domain-specific sort options
    sort_options = {
        "tasks": [
            ("priority", "Priority"),
            ("due_date", "Due Date"),
            ("title", "Alphabetical"),
        ],
        "goals": [
            ("priority", "Priority"),
            ("target_date", "Target Date"),
            ("progress", "Progress"),
            ("title", "Alphabetical"),
        ],
        "habits": [
            ("streak", "Streak"),
            ("title", "Alphabetical"),
        ],
        "events": [
            ("start_date", "Date"),
            ("title", "Alphabetical"),
        ],
        "choices": [
            ("created", "Recent"),
            ("title", "Alphabetical"),
        ],
        "principles": [
            ("strength", "Strength"),
            ("title", "Alphabetical"),
        ],
    }

    presets = filter_presets.get(domain, [("all", "All")])
    sorts = sort_options.get(domain, [("title", "Alphabetical")])

    # Filter preset buttons
    filter_buttons = []
    for value, label in presets:
        filter_buttons.append(
            Button(
                label,
                variant=ButtonT.ghost,
                size=Size.sm,
                x_bind_class=f"{{'uk-btn-primary': filterPreset === '{value}', 'uk-btn-ghost': filterPreset !== '{value}'}}",
                x_on_click=f"filterPreset = '{value}'",
            )
        )

    return Div(
        Div(
            # Sort dropdown
            Div(
                Label("Sort by:", cls="text-sm font-medium text-foreground mr-2"),
                Select(
                    *[Option(label, value=value) for value, label in sorts],
                    cls="uk-select uk-form-sm",
                    x_model="sortBy",
                ),
                cls="flex items-center gap-2",
            ),
            # Filter buttons
            Div(
                Label("Filter:", cls="text-sm font-medium text-foreground mr-2"),
                Div(*filter_buttons, cls="flex gap-2 flex-wrap"),
                cls="flex items-center gap-2",
            ),
            # Show all toggle
            Div(
                Button(
                    Span(
                        "Show All",
                        x_show="!showAll",
                    ),
                    Span(
                        f"Show Less (showing {total_count})",
                        x_show="showAll",
                    ),
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    x_on_click="toggleShowAll()",
                ),
                cls="ml-auto",
            ),
            cls="flex items-center gap-4 flex-wrap",
        ),
        cls="p-4 bg-muted rounded-lg mb-4",
        x_data="domainFilter()",
    )


def DomainIntelligenceCard(
    title: str,
    recommendations: list[tuple[str, str]],
) -> Div:
    """Contextual intelligence card for domain-specific recommendations.

    Args:
        title: Card title (e.g., "Today's Focus", "Habit Synergies")
        recommendations: List of (text, type) tuples where type is "info", "warning", or "success"

    Returns:
        Intelligence card with recommendations
    """
    if not recommendations:
        return Div()  # No recommendations, return empty

    type_icons = {
        "info": "💡",
        "warning": "⚠️",
        "success": "✓",
        "priority": "⭐",
    }

    items = []
    for text, rec_type in recommendations:
        icon = type_icons.get(rec_type, "•")
        items.append(
            Li(
                Span(icon, cls="mr-2"),
                Span(text, cls="text-sm text-foreground"),
                cls="flex items-start py-2",
            )
        )

    return Div(
        H3(title, cls="text-md font-semibold text-foreground mb-3"),
        Ul(*items, cls="space-y-1"),
        cls="p-4 bg-primary/5 rounded-lg border border-primary/20 mb-6",
    )


def DomainSummaryCard(
    title: str,
    icon: str,
    stats: list[tuple[str, int | str]],
    status: str,
) -> Div:
    """Summary card with key stats for a domain.

    Args:
        title: Domain name
        icon: Emoji icon
        stats: List of (label, value) tuples
        status: "healthy", "warning", "critical"

    Returns:
        Card div with stats
    """
    from ui.badge_classes import health_bg_class

    status_bg = health_bg_class(status)

    stats_html = []
    for label, value in stats:
        stats_html.append(
            Div(
                Div(str(value), cls="text-2xl font-bold text-foreground"),
                Div(label, cls="text-sm text-muted-foreground"),
                cls="text-center",
            )
        )

    return Div(
        Div(
            Span(icon, cls="text-3xl"),
            H3(title, cls="text-xl font-semibold text-foreground"),
            cls="flex items-center gap-3 mb-4",
        ),
        Div(*stats_html, cls="grid grid-cols-3 gap-4"),
        cls=f"p-6 rounded-xl border-2 {status_bg}",
    )


def EmptyState_for_domain(domain: str, message: str) -> Div:
    """Actionable empty state for a domain.

    Args:
        domain: Domain name (tasks, habits, goals, etc.)
        message: Empty state message

    Returns:
        EmptyState with CTA button
    """
    domain_config = {
        "tasks": {
            "icon": "✅",
            "action_text": "Create your first task →",
            "action_href": "/tasks?view=create",
            "description": "Tasks help you track what needs to be done",
        },
        "habits": {
            "icon": "🔄",
            "action_text": "Create your first habit →",
            "action_href": "/habits?view=create",
            "description": "Habits build consistency over time",
        },
        "goals": {
            "icon": "🎯",
            "action_text": "Create your first goal →",
            "action_href": "/goals?view=create",
            "description": "Goals give you direction and purpose",
        },
        "events": {
            "icon": "📅",
            "action_text": "Create your first event →",
            "action_href": "/events?view=create",
            "description": "Events help you plan your time",
        },
        "choices": {
            "icon": "🤔",
            "action_text": "Record your first choice →",
            "action_href": "/choices?view=create",
            "description": "Choices track your decision-making patterns",
        },
        "principles": {
            "icon": "⚖️",
            "action_text": "Define your first principle →",
            "action_href": "/principles?view=create",
            "description": "Principles guide your decisions",
        },
    }

    config = domain_config.get(domain, {})
    return EmptyState(
        title=message,
        description=config.get("description", ""),
        action_text=config.get("action_text"),
        action_href=config.get("action_href"),
        icon=config.get("icon"),
    )


def _item_list(
    items: list[dict[str, Any]],
    empty_message: str,
    item_href_prefix: str = "",
    domain: str = "",
    focus_uid: str | None = None,
    limit: int = 50,
) -> Div:
    """Generic item list component.

    , Task 11: Added focus_uid support for deep linking with highlight.
    , Task 12: Added limit parameter and filter data attributes.

    Args:
        items: List of item dictionaries with title, uid, status
        empty_message: Message to show when no items
        item_href_prefix: URL prefix for item links (e.g., "/tasks")
        domain: Domain name for actionable empty states
        focus_uid: Optional entity UID to highlight
        limit: Maximum number of items to render (default 50)
    """
    if not items:
        # Use actionable empty state if domain is provided
        if domain:
            return EmptyState_for_domain(domain, empty_message)
        # Fallback to basic empty state
        return Div(
            P(empty_message, cls="text-muted-foreground italic text-center py-8"),
            cls="bg-muted rounded-lg",
        )

    list_items = []
    for idx, item in enumerate(items[:limit]):  # Limit to specified count
        title = item.get("title", "Untitled")
        uid = item.get("uid", "")
        status = item.get("status", "")
        href = f"{item_href_prefix}/{uid}" if item_href_prefix and uid else None

        # , Task 12: Extract filter metadata
        is_overdue = item.get("is_overdue", False)
        is_high_priority = item.get("is_high_priority", False)
        is_this_week = item.get("is_this_week", False)

        status_badge = ""
        if status:
            from ui.badge_classes import status_text_class

            status_color = status_text_class(status)
            status_badge = Span(
                status.replace("_", " ").title(),
                cls=f"text-xs font-medium {status_color}",
            )

        item_content = Div(
            Span(title, cls="font-medium text-foreground"),
            status_badge,
            cls="flex items-center justify-between",
        )

        # , Task 12: Build x-show expression for filtering
        # Show if: matches filter AND (showAll OR index < 10)
        x_show_expr = f"matchesFilter('{status}', {str(is_overdue).lower()}, {str(is_high_priority).lower()}, {str(is_this_week).lower()}) && (showAll || {idx} < 10)"

        # , Task 11 & 12: Add data attributes and x-show for filtering
        item_attrs = {
            "data_uid": uid,  # For focus targeting
            "x_show": x_show_expr,  # For filtering
        }

        if href:
            list_items.append(
                A(
                    item_content,
                    href=href,
                    cls="block p-3 hover:bg-muted rounded-lg transition-colors",
                    **item_attrs,
                )
            )
        else:
            list_items.append(
                Div(
                    item_content,
                    cls="p-3 rounded-lg",
                    **item_attrs,
                )
            )

    # , Task 11: Wrap in Alpine component for focus handling
    # , Task 12: Always wrap in domainFilter for filtering
    wrapper_attrs = {"x_data": "domainFilter()"}

    # , Task 11: Add focus handler if focus_uid present
    if focus_uid:
        wrapper_attrs["x_init"] = (
            f"$nextTick(() => {{ if (window.profileFocusHandler) {{ var handler = profileFocusHandler('{focus_uid}'); handler.scrollToFocused.call({{ $el: $el, focusUid: '{focus_uid}' }}); }} }})"
        )

    return Div(*list_items, cls="space-y-1", **wrapper_attrs)
