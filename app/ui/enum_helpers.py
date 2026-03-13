"""
UI Enum Helpers
================

Helper functions to convert string values from API/data to enum instances
and retrieve dynamic presentation values (colors, icons).

This module bridges UI components (which receive string data) with
shared_enums.py (which provides dynamic methods).

Architecture (3 tiers):
    1. Basic Helpers - String to color/icon conversion
    2. Tailwind Mappers - Hex colors to Tailwind CSS classes
    3. Component Builders - Full UI components (badges, chips, indicators)

Usage in UI components:
    from ui.enum_helpers import (
        get_trend_color,           # Basic helper
        get_priority_badge_class,  # Tailwind mapper
        render_priority_badge      # Component builder
    )

    # Tier 1: Basic helper
    color = get_trend_color("increasing")  # Returns "text-green-600"

    # Tier 2: Tailwind mapper
    badge_class = get_priority_badge_class("high")  # Returns "badge-warning"

    # Tier 3: Component builder
    badge_component = render_priority_badge("high")  # Returns DaisyUI Badge
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H4, Div, P, Span

from core.models.enums import (
    ActivityType,
    BridgeType,
    CompletionStatus,
    ContentType,
    EducationalLevel,
    EntityStatus,
    HealthStatus,
    Priority,
    RecurrencePattern,
    SELCategory,
    SeverityLevel,
    TimeOfDay,
    TrendDirection,
)
from core.models.event.calendar_models import CalendarItemType
from ui.buttons import Button
from ui.cards import Card, CardBody


# Simple Badge component (local helper for this module)
def Badge(text: str, cls: str = "badge") -> Span:
    """Simple badge component using Span with DaisyUI classes."""
    return Span(text, cls=cls)


# ============================================================================
# TREND HELPERS
# ============================================================================


def get_trend_color(trend: str) -> str:
    """
    Get Tailwind color class for a trend direction string.

    Args:
        trend: Trend direction string ("increasing", "decreasing", "stable"),

    Returns:
        Tailwind CSS color class (e.g., "text-green-600")
    """
    try:
        trend_enum = TrendDirection(trend)
        return trend_enum.get_color()
    except ValueError:
        return "text-muted-foreground"  # Default for unknown trends


def get_trend_icon(trend: str) -> str:
    """
    Get emoji icon for a trend direction string.

    Args:
        trend: Trend direction string ("increasing", "decreasing", "stable"),

    Returns:
        Emoji icon (e.g., "📈")
    """
    try:
        trend_enum = TrendDirection(trend)
        return trend_enum.get_icon()
    except ValueError:
        return "→"  # Default arrow for unknown trends


# ============================================================================
# HEALTH STATUS HELPERS
# ============================================================================


def get_health_color(status: str) -> str:
    """
    Get color for a health status string.

    Args:
        status: Health status string ("healthy", "warning", "critical", "unknown"),

    Returns:
        Tailwind base color name (e.g., "green", "red")
    """
    try:
        status_enum = HealthStatus(status)
        return status_enum.get_color()
    except ValueError:
        return "gray"  # Default for unknown status


def get_health_icon(status: str) -> str:
    """
    Get emoji icon for a health status string.

    Args:
        status: Health status string ("healthy", "warning", "critical", "unknown"),

    Returns:
        Emoji icon (e.g., "✅", "⚠️")
    """
    try:
        status_enum = HealthStatus(status)
        return status_enum.get_icon()
    except ValueError:
        return "❔"  # Default for unknown status


# ============================================================================
# SEVERITY HELPERS
# ============================================================================


def get_severity_color(severity: str) -> str:
    """
    Get color for a severity level string.

    Args:
        severity: Severity level string ("high", "medium", "low"),

    Returns:
        Tailwind base color name (e.g., "red", "yellow", "blue")
    """
    try:
        severity_enum = SeverityLevel(severity)
        return severity_enum.get_color()
    except ValueError:
        return "gray"  # Default for unknown severity


def get_severity_numeric(severity: str) -> int:
    """
    Get numeric value for severity level (for sorting).

    Args:
        severity: Severity level string ("high", "medium", "low"),

    Returns:
        Numeric value (1-3, higher is more severe)
    """
    try:
        severity_enum = SeverityLevel(severity)
        return severity_enum.to_numeric()
    except ValueError:
        return 2  # Default to medium


# ============================================================================
# BRIDGE TYPE HELPERS
# ============================================================================


def get_bridge_color(bridge_type: str) -> str:
    """
    Get color for a knowledge bridge type string.

    Args:
        bridge_type: Bridge type string ("direct", "analogical", "methodological", "skill_transfer"),

    Returns:
        Tailwind base color name (e.g., "green", "blue", "purple")
    """
    try:
        bridge_enum = BridgeType(bridge_type)
        return bridge_enum.get_color()
    except ValueError:
        return "gray"  # Default for unknown bridge type


# ============================================================================
# PRIORITY HELPERS (from existing enums)
# ============================================================================


def get_priority_color(priority: str) -> str:
    """
    Get hex color for a priority level string.

    Args:
        priority: Priority level string ("low", "medium", "high", "critical"),

    Returns:
        Hex color code (e.g., "#F59E0B")
    """
    try:
        priority_enum = Priority(priority)
        return priority_enum.get_color()
    except ValueError:
        return "#6B7280"  # Default gray


def get_priority_numeric(priority: str) -> int:
    """
    Get numeric value for priority level (for sorting).

    Args:
        priority: Priority level string ("low", "medium", "high", "critical"),

    Returns:
        Numeric value (1-4, higher is more important)
    """
    try:
        priority_enum = Priority(priority)
        return priority_enum.to_numeric()
    except ValueError:
        return 2  # Default to medium


# ============================================================================
# STATUS HELPERS (from existing enums)
# ============================================================================


def get_status_color(status: str) -> str:
    """
    Get hex color for an activity status string.

    Args:
        status: Activity status string ("completed", "active", "blocked", etc.),

    Returns:
        Hex color code (e.g., "#10B981")
    """
    try:
        status_enum = EntityStatus(status)
        return status_enum.get_color()
    except ValueError:
        return "#6B7280"  # Default gray


def get_completion_emoji(status: str) -> str:
    """
    Get emoji for a completion status string.

    Args:
        status: Completion status string ("done", "partial", "skipped", "missed", "paused"),

    Returns:
        Emoji icon (e.g., "✅", "❌")
    """
    try:
        status_enum = CompletionStatus(status)
        return status_enum.get_emoji()
    except ValueError:
        return "❓"  # Default question mark


# ============================================================================
# GENERIC HELPER
# ============================================================================


def safe_enum_method(enum_class, value: str, method_name: str, default):
    """
    Generic helper to safely call enum methods.

    Args:
        enum_class: The enum class to instantiate,
        value: String value to convert to enum
        method_name: Name of method to call on enum instance,
        default: Default value if conversion or method call fails

    Returns:
        Result of calling the method, or default value
    """
    try:
        enum_instance = enum_class(value)
        method = getattr(enum_instance, method_name, None)
        if method and callable(method):
            return method()
        return default
    except (ValueError, AttributeError):
        return default


# ============================================================================
# ACTIVITY TYPE HELPERS
# ============================================================================


def get_activity_icon(activity_type: str) -> str:
    """
    Get emoji icon for an activity type string.

    Args:
        activity_type: Activity type string ("task", "habit", "event", "learning", etc.),

    Returns:
        Emoji icon (e.g., "📝", "🔄")
    """
    try:
        activity_enum = ActivityType(activity_type)
        return activity_enum.get_icon()
    except ValueError:
        return "📋"  # Default activity icon


# ============================================================================
# CONTENT TYPE HELPERS
# ============================================================================


def get_content_icon(content_type: str) -> str:
    """
    Get emoji icon for a content type string.

    Args:
        content_type: Content type string ("concept", "practice", "example", etc.),

    Returns:
        Emoji icon (e.g., "💡", "🎯")
    """
    try:
        content_enum = ContentType(content_type)
        return content_enum.get_icon()
    except ValueError:
        return "📄"  # Default content icon


def get_content_color(content_type: str) -> str:
    """
    Get hex color for a content type string.

    Args:
        content_type: Content type string ("concept", "practice", "example", etc.),

    Returns:
        Hex color code (e.g., "#3B82F6")
    """
    try:
        content_enum = ContentType(content_type)
        return content_enum.get_color()
    except ValueError:
        return "#6B7280"  # Default gray


# ============================================================================
# EDUCATIONAL LEVEL HELPERS
# ============================================================================


def get_educational_icon(level: str) -> str:
    """
    Get emoji icon for an educational level string.

    Args:
        level: Educational level string ("elementary", "college", etc.),

    Returns:
        Emoji icon (e.g., "🎒", "🏛️")
    """
    try:
        level_enum = EducationalLevel(level)
        return level_enum.get_icon()
    except ValueError:
        return "📚"  # Default education icon


def get_educational_color(level: str) -> str:
    """
    Get hex color for an educational level string.

    Args:
        level: Educational level string ("elementary", "college", etc.),

    Returns:
        Hex color code (e.g., "#F59E0B")
    """
    try:
        level_enum = EducationalLevel(level)
        return level_enum.get_color()
    except ValueError:
        return "#6B7280"  # Default gray


# ============================================================================
# SEL CATEGORY HELPERS
# ============================================================================


def get_sel_icon(category: str) -> str:
    """
    Get emoji icon for an SEL category string.

    Args:
        category: SEL category string ("self_awareness", "self_management", etc.),

    Returns:
        Emoji icon (e.g., "🧘", "🎯")
    """
    try:
        sel_enum = SELCategory(category)
        return sel_enum.get_icon()
    except ValueError:
        return "📚"  # Default SEL icon


def get_sel_color(category: str) -> str:
    """
    Get hex color for an SEL category string.

    Args:
        category: SEL category string ("self_awareness", "self_management", etc.),

    Returns:
        Hex color code (e.g., "#8B5CF6")
    """
    try:
        sel_enum = SELCategory(category)
        return sel_enum.get_color()
    except ValueError:
        return "#6B7280"  # Default gray


# ============================================================================
# RECURRENCE PATTERN HELPERS
# ============================================================================


def get_recurrence_label(pattern: str) -> str:
    """
    Get human-readable label for a recurrence pattern.

    Args:
        pattern: Recurrence pattern string ("daily", "weekly", "monthly", "custom"),

    Returns:
        Human-readable label (e.g., "Every day", "Every week")

    Example:
        >>> get_recurrence_label("daily")
        "Every day"
    """
    labels = {
        "none": "One-time",
        "daily": "Every day",
        "weekdays": "Weekdays only",
        "weekends": "Weekends only",
        "weekly": "Every week",
        "biweekly": "Every 2 weeks",
        "monthly": "Every month",
        "quarterly": "Every 3 months",
        "yearly": "Every year",
        "custom": "Custom schedule",
    }
    return labels.get(pattern, pattern.title())


def get_recurrence_rrule(pattern: str) -> str:
    """
    Get RRULE string for a recurrence pattern.

    Args:
        pattern: Recurrence pattern string,

    Returns:
        RRULE string (e.g., "FREQ=DAILY")

    Example:
        >>> get_recurrence_rrule("daily")
        "FREQ=DAILY"
    """
    try:
        pattern_enum = RecurrencePattern(pattern)
        return pattern_enum.to_rrule_base()
    except ValueError:
        return ""  # No RRULE for unknown pattern


# ============================================================================
# TIME OF DAY HELPERS
# ============================================================================


def get_time_label(time_of_day: str) -> str:
    """
    Get human-readable label for time of day.

    Args:
        time_of_day: Time of day string ("morning", "afternoon", "evening", etc.),

    Returns:
        Human-readable time range (e.g., "7:00 - 12:00")

    Example:
        >>> get_time_label("morning")
        "7:00 - 12:00"
    """
    try:
        time_enum = TimeOfDay(time_of_day)
        start, end = time_enum.get_hour_range()
        return f"{start}:00 - {end}:00"
    except ValueError:
        return time_of_day.replace("_", " ").title()


def get_time_icon(time_of_day: str) -> str:
    """
    Get emoji icon for time of day.

    Args:
        time_of_day: Time of day string,

    Returns:
        Emoji icon representing the time period

    Example:
        >>> get_time_icon("morning")
        "🌅"
    """
    icons = {
        "early_morning": "🌅",
        "morning": "☀️",
        "afternoon": "🌤️",
        "evening": "🌆",
        "night": "🌙",
        "late_night": "🌃",
        "anytime": "⏰",
    }
    return icons.get(time_of_day, "🕐")


# ============================================================================
# CALENDAR ITEM TYPE HELPERS
# ============================================================================


def get_calendar_icon(item_type: str) -> str:
    """
    Get emoji icon for a calendar item type.

    Args:
        item_type: Calendar item type string ("event", "task_work", "habit", etc.),

    Returns:
        Emoji icon (e.g., "📅", "📋", "🔄")

    Example:
        >>> get_calendar_icon("event")
        "📅"
    """
    try:
        item_enum = CalendarItemType(item_type)
        return item_enum.get_icon()
    except ValueError:
        return "📅"  # Default calendar icon


# ============================================================================
# TAILWIND CLASS MAPPERS (Tier 2)
# ============================================================================


def get_priority_border_class(priority: str | Priority) -> str:
    """
    Get Tailwind border class for a priority level.

    Args:
        priority: Priority level string or enum,

    Returns:
        Tailwind CSS border class (e.g., "border-yellow-500")
    """
    if isinstance(priority, str):
        try:
            priority = Priority(priority)
        except ValueError:
            return "border-border"

    color = priority.get_color()
    color_to_class = {
        "#10B981": "border-green-500",  # Low
        "#3B82F6": "border-blue-500",  # Medium
        "#F59E0B": "border-yellow-500",  # High
        "#DC2626": "border-red-500",  # Critical
    }
    return color_to_class.get(color, "border-border")


def get_priority_badge_class(priority: str | Priority) -> str:
    """
    Get DaisyUI badge class for a priority level.

    Args:
        priority: Priority level string or enum,

    Returns:
        Badge CSS class (e.g., "badge-warning")
    """
    from ui.badge_classes import priority_badge_class

    if isinstance(priority, str):
        return priority_badge_class(priority)
    return priority_badge_class(priority.value)


def get_status_badge_class(status: str | EntityStatus) -> str:
    """
    Get DaisyUI badge class for an activity status.

    Args:
        status: Activity status string or enum,

    Returns:
        Badge CSS class (e.g., "badge-success")
    """
    from ui.badge_classes import status_badge_class

    if isinstance(status, str):
        return status_badge_class(status)
    return status_badge_class(status.value)


def get_status_text_color(status: str | EntityStatus) -> str:
    """
    Get Tailwind text color class for an activity status.

    Args:
        status: Activity status string or enum,

    Returns:
        Tailwind CSS text color class (e.g., "text-green-600")
    """
    if isinstance(status, str):
        try:
            status = EntityStatus(status)
        except ValueError:
            return "text-muted-foreground"

    color = status.get_color()
    color_to_class = {
        "#10B981": "text-green-600",  # Completed
        "#06B6D4": "text-cyan-600",  # In Progress
        "#F59E0B": "text-amber-600",  # Paused
        "#DC2626": "text-red-600",  # Blocked
        "#EF4444": "text-red-600",  # Failed
        "#3B82F6": "text-blue-600",  # Scheduled
        "#6B7280": "text-muted-foreground",  # Cancelled
        "#9CA3AF": "text-muted-foreground",  # Draft/Archived
    }
    return color_to_class.get(color, "text-muted-foreground")


# ============================================================================
# COMPONENT BUILDERS (Tier 3)
# ============================================================================


def render_priority_badge(priority: str | Priority) -> Span:
    """
    Render priority as styled DaisyUI badge component.

    Args:
        priority: Priority enum or string value,

    Returns:
        DaisyUI Badge component

    Example:
        >>> render_priority_badge("high")
        <Badge cls="badge badge-warning">High</Badge>
    """
    if isinstance(priority, str):
        try:
            priority = Priority(priority)
        except ValueError:
            return Badge("Unknown", cls="badge badge-neutral")

    badge_class = get_priority_badge_class(priority)
    label = priority.value.title()

    return Badge(label, cls=f"badge {badge_class}")


def render_status_chip(status: str | EntityStatus) -> Span:
    """
    Render status as styled chip with color indicator.

    Args:
        status: Activity status enum or string value,

    Returns:
        Span component with colored dot and label

    Example:
        >>> render_status_chip("active")
        <Span cls="status-chip inline-flex items-center">
            <Span style="color: #06B6D4">●</Span> In Progress
        </Span>
    """
    if isinstance(status, str):
        try:
            status = EntityStatus(status)
        except ValueError:
            return Span("Unknown", cls="status-chip inline-flex items-center")

    color = status.get_color()
    label = status.value.replace("_", " ").title()

    return Span(
        Span("●", style=f"color: {color}; margin-right: 0.5rem", cls="text-lg"),
        label,
        cls="status-chip inline-flex items-center gap-1",
    )


def render_status_badge(status: str | EntityStatus) -> Span:
    """
    Render status as styled DaisyUI badge component.

    Args:
        status: Activity status enum or string value,

    Returns:
        DaisyUI Badge component

    Example:
        >>> render_status_badge("completed")
        <Badge cls="badge badge-success">Completed</Badge>
    """
    if isinstance(status, str):
        try:
            status = EntityStatus(status)
        except ValueError:
            return Badge("Unknown", cls="badge badge-neutral")

    badge_class = get_status_badge_class(status)
    label = status.value.replace("_", " ").title()

    return Badge(label, cls=f"badge {badge_class}")


def render_trend_indicator(trend: str, value: float | None = None) -> Div:
    """
    Render trend with icon, color, and optional value.

    Args:
        trend: Trend direction string ("increasing", "decreasing", "stable"),
        value: Optional numeric value to display (e.g., 15.3 for +15.3%)

    Returns:
        Div component with icon and optional value,

    Example:
        >>> render_trend_indicator("increasing", 15.3)
        <Div cls="trend-indicator flex items-center gap-2">
            <Span cls="text-2xl">📈</Span>
            <Span cls="text-green-600 font-bold">+15.3%</Span>
        </Div>
    """
    color = get_trend_color(trend)
    icon = get_trend_icon(trend)

    content = [Span(icon, cls="text-2xl")]

    if value is not None:
        sign = "+" if trend == "increasing" else "-" if trend == "decreasing" else ""
        content.append(Span(f"{sign}{value}%", cls=f"{color} font-bold"))

    return Div(*content, cls="trend-indicator flex items-center gap-2")


def render_completion_badge(status: str | CompletionStatus) -> Span:
    """
    Render completion status as badge with emoji.

    Args:
        status: Completion status string or enum,

    Returns:
        Badge component with emoji and label

    Example:
        >>> render_completion_badge("done")
        <Badge cls="badge badge-success">✅ Done</Badge>
    """
    if isinstance(status, str):
        try:
            status = CompletionStatus(status)
        except ValueError:
            return Badge("❓ Unknown", cls="badge badge-neutral")

    emoji = status.get_emoji()
    label = status.value.title()

    # Map completion status to badge classes
    status_to_class = {
        CompletionStatus.DONE: "badge-success",
        CompletionStatus.PARTIAL: "badge-info",
        CompletionStatus.SKIPPED: "badge-warning",
        CompletionStatus.MISSED: "badge-error",
        CompletionStatus.PAUSED: "badge-neutral",
    }
    badge_class = status_to_class.get(status, "badge-neutral")

    return Badge(f"{emoji} {label}", cls=f"badge {badge_class}")


# ============================================================================
# COMPOSITE COMPONENTS (High-level)
# ============================================================================


def render_entity_metadata(
    priority: str | Priority, status: str | EntityStatus, due_date: str | None = None
) -> Div:
    """
    Render combined metadata display for tasks/events/habits.

    Args:
        priority: Priority level,
        status: Activity status,
        due_date: Optional due date string

    Returns:
        Div with priority badge, status chip, and optional due date,

    Example:
        >>> render_entity_metadata("high", "active", "2025-10-20")
        <Div cls="flex items-center gap-2 flex-wrap">
            <Badge>High</Badge>
            <Span>● In Progress</Span>
            <Span cls="text-sm text-muted-foreground">📅 2025-10-20</Span>
        </Div>
    """
    components = [render_priority_badge(priority), render_status_chip(status)]

    if due_date:
        components.append(Span(f"📅 {due_date}", cls="text-sm text-muted-foreground"))

    return Div(*components, cls="flex items-center gap-2 flex-wrap")


# ============================================================================
# ADDITIONAL COMPONENT BUILDERS (Tier 3 Extended)
# ============================================================================


def render_due_date_display(due_date: str | None, overdue: bool = False) -> Span | str:
    """
    Render due date with conditional styling.

    Args:
        due_date: Due date string (ISO format or human-readable),
        overdue: Whether the date is overdue

    Returns:
        Styled Span with date, or empty string if no date,

    Example:
        >>> render_due_date_display("2025-10-20", overdue=True)
        <Span cls="text-sm text-red-600 font-semibold">📅 2025-10-20</Span>
    """
    if not due_date:
        return ""

    color_class = "text-red-600 font-semibold" if overdue else "text-muted-foreground"
    return Span(f"📅 {due_date}", cls=f"text-sm {color_class}")


def render_duration_display(duration_minutes: int | None) -> Span | str:
    """
    Render duration in human-readable format.

    Args:
        duration_minutes: Duration in minutes,

    Returns:
        Styled Span with duration, or empty string if no duration

    Example:
        >>> render_duration_display(90)
        <Span cls="text-sm text-muted-foreground">⏱ 1h 30m</Span>
    """
    if not duration_minutes:
        return ""

    hours = duration_minutes // 60
    minutes = duration_minutes % 60

    if hours > 0 and minutes > 0:
        duration_str = f"{hours}h {minutes}m"
    elif hours > 0:
        duration_str = f"{hours}h"
    else:
        duration_str = f"{minutes}m"

    return Span(f"⏱ {duration_str}", cls="text-sm text-muted-foreground")


def render_tag_list(tags: list[str] | None) -> Div | str:
    """
    Render list of tags as small badges.

    Args:
        tags: List of tag strings,

    Returns:
        Div containing badge elements, or empty string if no tags

    Example:
        >>> render_tag_list(["urgent", "work"])
        <Div cls="flex gap-1 flex-wrap">
            <Badge cls="badge badge-sm badge-outline">urgent</Badge>
            <Badge cls="badge badge-sm badge-outline">work</Badge>
        </Div>
    """
    if not tags:
        return ""

    tag_badges = [Badge(tag, cls="badge badge-sm badge-outline") for tag in tags]

    return Div(*tag_badges, cls="flex gap-1 flex-wrap")


def render_activity_type_label(activity_type: str) -> Span:
    """
    Render activity type with icon.

    Args:
        activity_type: Activity type string,

    Returns:
        Span with icon and label

    Example:
        >>> render_activity_type_label("task")
        <Span cls="text-sm text-muted-foreground">📝 Task</Span>
    """
    icon = get_activity_icon(activity_type)
    label = activity_type.replace("_", " ").title()
    return Span(f"{icon} {label}", cls="text-sm text-muted-foreground")


def render_recurrence_display(pattern: str | None) -> Span | str:
    """
    Render recurrence pattern with human-readable label.

    Args:
        pattern: Recurrence pattern string,

    Returns:
        Span with recurrence icon and label, or empty string if no pattern

    Example:
        >>> render_recurrence_display("daily")
        <Span cls="text-sm text-muted-foreground">🔄 Every day</Span>
    """
    if not pattern or pattern == "none":
        return ""

    label = get_recurrence_label(pattern)
    return Span(f"🔄 {label}", cls="text-sm text-muted-foreground")


def render_time_of_day_display(time_of_day: str | None) -> Span | str:
    """
    Render time of day with icon and label.

    Args:
        time_of_day: Time of day string,

    Returns:
        Span with time icon and label, or empty string if no time

    Example:
        >>> render_time_of_day_display("morning")
        <Span cls="text-sm text-muted-foreground">☀️ 7:00 - 12:00</Span>
    """
    if not time_of_day:
        return ""

    icon = get_time_icon(time_of_day)
    label = get_time_label(time_of_day)
    return Span(f"{icon} {label}", cls="text-sm text-muted-foreground")


# ============================================================================
# ENTITY CARD COMPONENTS (Tier 4 - Domain Entities)
# ============================================================================


def render_entity_card(
    entity_type: str,
    uid: str,
    title: str,
    description: str | None = None,
    priority: str | Priority | None = None,
    status: str | EntityStatus | None = None,
    due_date: str | None = None,
    duration_minutes: int | None = None,
    tags: list[str] | None = None,
    recurrence: str | None = None,
    time_of_day: str | None = None,
    custom_metadata: list[Span | str] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> Any:
    """
    Generic entity card component for tasks, habits, events, goals.

    Args:
        entity_type: Type of entity ("task", "habit", "event", "goal"),
        uid: Entity unique identifier,
        title: Entity title,
        description: Optional description text,
        priority: Optional priority level,
        status: Optional activity status,
        due_date: Optional due date string,
        duration_minutes: Optional duration in minutes,
        tags: Optional list of tags,
        recurrence: Optional recurrence pattern,
        time_of_day: Optional time of day,
        custom_metadata: Optional list of additional metadata components,
        actions: Optional list of action button configs

    Returns:
        DaisyUI Card component,

    Example:
        >>> render_entity_card(
        ...     entity_type="task",
        ...     uid="task-123",
        ...     title="Complete refactoring",
        ...     priority="high",
        ...     status="active",
        ...     due_date="2025-10-20",
        ... )
    """
    # Border styling based on priority
    border_class = get_priority_border_class(priority) if priority else "border-border"

    # Card header with title and status
    header_components = [
        H4(title, cls="text-base font-semibold mb-1"),
    ]
    if status:
        header_components.append(render_status_badge(status))

    header = Div(*header_components, cls="flex justify-between items-start gap-2")

    # Description
    description_elem = (
        P(description, cls="text-sm text-muted-foreground mb-3") if description else ""
    )

    # Metadata row
    metadata_components = []

    if priority:
        metadata_components.append(render_priority_badge(priority))

    if due_date:
        overdue = False  # Could add date comparison logic here
        metadata_components.append(render_due_date_display(due_date, overdue))

    if duration_minutes:
        metadata_components.append(render_duration_display(duration_minutes))

    if recurrence:
        metadata_components.append(render_recurrence_display(recurrence))

    if time_of_day:
        metadata_components.append(render_time_of_day_display(time_of_day))

    if custom_metadata:
        metadata_components.extend(custom_metadata)

    metadata = (
        Div(*metadata_components, cls="flex gap-2 items-center flex-wrap mb-2")
        if metadata_components
        else ""
    )

    # Tags
    tags_elem = render_tag_list(tags) if tags else ""

    # Action buttons
    buttons = []
    if actions:
        for action in actions:
            btn = Button(
                action.get("label", "Action"),
                cls=action.get("class", "btn btn-sm btn-outline"),
                **{k: v for k, v in action.items() if k not in ["label", "class"]},
            )
            buttons.append(btn)
    else:
        # Default actions
        buttons = [
            Button(
                "View",
                cls="btn btn-sm btn-outline",
                hx_get=f"/{entity_type}s/{uid}",
                hx_target="#modal",
            ),
            Button(
                "Edit",
                cls="btn btn-sm btn-primary",
                hx_get=f"/{entity_type}s/{uid}/edit",
                hx_target="#modal",
            ),
        ]

    actions_row = Div(*buttons, cls="flex gap-2 mt-3") if buttons else ""

    # Build card
    card_content = [header, description_elem, metadata, tags_elem, actions_row]

    return Card(
        CardBody(*[c for c in card_content if c]),  # Filter out empty strings
        id=f"{entity_type}-{uid}",
        cls=f"border-l-4 {border_class} hover:shadow-md transition-shadow",
    )


def render_task_card(
    uid: str,
    title: str,
    description: str | None = None,
    priority: str | Priority = "medium",
    status: str | EntityStatus = "todo",
    due_date: str | None = None,
    duration_minutes: int | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
) -> Any:
    """
    Specialized task card component.

    Args:
        uid: Task unique identifier,
        title: Task title,
        description: Optional description,
        priority: Task priority,
        status: Task status,
        due_date: Optional due date,
        duration_minutes: Optional estimated duration,
        tags: Optional tags,
        project: Optional project name

    Returns:
        Task card component,

    Example:
        >>> render_task_card(
        ...     uid="task-123",
        ...     title="Complete refactoring",
        ...     priority="high",
        ...     status="active",
        ... )
    """
    custom_metadata = []
    if project:
        custom_metadata.append(Span(f"📁 {project}", cls="text-sm text-muted-foreground"))

    return render_entity_card(
        entity_type="task",
        uid=uid,
        title=title,
        description=description,
        priority=priority,
        status=status,
        due_date=due_date,
        duration_minutes=duration_minutes,
        tags=tags,
        custom_metadata=custom_metadata,
    )


def render_habit_card(
    uid: str,
    title: str,
    description: str | None = None,
    recurrence: str = "daily",
    time_of_day: str | None = None,
    status: str | EntityStatus = "scheduled",
    streak: int | None = None,
    completion_rate: float | None = None,
) -> Any:
    """
    Specialized habit card component.

    Args:
        uid: Habit unique identifier,
        title: Habit title,
        description: Optional description,
        recurrence: Recurrence pattern,
        time_of_day: Preferred time of day,
        status: Habit status,
        streak: Current streak count,
        completion_rate: Completion rate percentage

    Returns:
        Habit card component,

    Example:
        >>> render_habit_card(
        ...     uid="habit-123", title="Morning meditation", recurrence="daily", streak=7
        ... )
    """
    custom_metadata = []
    if streak is not None:
        custom_metadata.append(
            Span(f"🔥 {streak} day streak", cls="text-sm font-semibold text-orange-600")
        )
    if completion_rate is not None:
        custom_metadata.append(
            Span(f"✓ {completion_rate:.0f}% completion", cls="text-sm text-green-600")
        )

    return render_entity_card(
        entity_type="habit",
        uid=uid,
        title=title,
        description=description,
        status=status,
        recurrence=recurrence,
        time_of_day=time_of_day,
        custom_metadata=custom_metadata,
    )


def render_event_card(
    uid: str,
    title: str,
    description: str | None = None,
    event_date: str | None = None,
    time_of_day: str | None = None,
    duration_minutes: int | None = None,
    calendar_type: str | None = None,
    status: str | EntityStatus = "scheduled",
    location: str | None = None,
) -> Any:
    """
    Specialized event card component.

    Args:
        uid: Event unique identifier,
        title: Event title,
        description: Optional description,
        event_date: Event date,
        time_of_day: Time of day,
        duration_minutes: Event duration,
        calendar_type: Calendar item type,
        status: Event status,
        location: Optional location

    Returns:
        Event card component,

    Example:
        >>> render_event_card(
        ...     uid="event-123",
        ...     title="Team meeting",
        ...     event_date="2025-10-20",
        ...     time_of_day="morning",
        ... )
    """
    custom_metadata = []
    if calendar_type:
        icon = get_calendar_icon(calendar_type)
        custom_metadata.append(
            Span(
                f"{icon} {calendar_type.replace('_', ' ').title()}",
                cls="text-sm text-muted-foreground",
            )
        )
    if location:
        custom_metadata.append(Span(f"📍 {location}", cls="text-sm text-muted-foreground"))

    return render_entity_card(
        entity_type="event",
        uid=uid,
        title=title,
        description=description,
        status=status,
        due_date=event_date,  # Reuse due_date for event_date
        duration_minutes=duration_minutes,
        time_of_day=time_of_day,
        custom_metadata=custom_metadata,
    )


def render_goal_card(
    uid: str,
    title: str,
    description: str | None = None,
    priority: str | Priority = "medium",
    status: str | EntityStatus = "active",
    target_date: str | None = None,
    progress_percentage: float | None = None,
    domain: str | None = None,
) -> Any:
    """
    Specialized goal card component.

    Args:
        uid: Goal unique identifier,
        title: Goal title,
        description: Optional description,
        priority: Goal priority,
        status: Goal status,
        target_date: Target completion date,
        progress_percentage: Progress percentage,
        domain: Goal domain

    Returns:
        Goal card component,

    Example:
        >>> render_goal_card(
        ...     uid="goal-123",
        ...     title="Learn Python",
        ...     priority="high",
        ...     progress_percentage=65.0,
        ... )
    """
    custom_metadata = []
    if progress_percentage is not None:
        custom_metadata.append(
            Span(
                f"📊 {progress_percentage:.0f}% complete", cls="text-sm font-semibold text-blue-600"
            )
        )
    if domain:
        custom_metadata.append(Span(f"🎯 {domain.title()}", cls="text-sm text-muted-foreground"))

    return render_entity_card(
        entity_type="goal",
        uid=uid,
        title=title,
        description=description,
        priority=priority,
        status=status,
        due_date=target_date,  # Reuse due_date for target_date
        custom_metadata=custom_metadata,
    )


# ============================================================================
# PUBLIC API - All exported functions
# ============================================================================


__all__ = [
    # Tier 1: Basic Helpers (String → Color/Icon)
    "get_trend_color",
    "get_trend_icon",
    "get_health_color",
    "get_health_icon",
    "get_severity_color",
    "get_severity_numeric",
    "get_bridge_color",
    "get_priority_color",
    "get_priority_numeric",
    "get_status_color",
    "get_completion_emoji",
    "get_activity_icon",
    "get_content_icon",
    "get_content_color",
    "get_educational_icon",
    "get_educational_color",
    "get_sel_icon",
    "get_sel_color",
    "get_recurrence_label",
    "get_recurrence_rrule",
    "get_time_label",
    "get_time_icon",
    "get_calendar_icon",
    # Tier 2: Tailwind Class Mappers
    "get_priority_border_class",
    "get_priority_badge_class",
    "get_status_badge_class",
    "get_status_text_color",
    # Tier 3: Component Builders (Core)
    "render_priority_badge",
    "render_status_chip",
    "render_status_badge",
    "render_trend_indicator",
    "render_completion_badge",
    "render_entity_metadata",
    # Tier 3: Component Builders (Extended)
    "render_due_date_display",
    "render_duration_display",
    "render_tag_list",
    "render_activity_type_label",
    "render_recurrence_display",
    "render_time_of_day_display",
    # Tier 4: Entity Card Components
    "render_entity_card",
    "render_task_card",
    "render_habit_card",
    "render_event_card",
    "render_goal_card",
    # Generic Helper
    "safe_enum_method",
]
