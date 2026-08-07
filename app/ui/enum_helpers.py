"""
UI Enum Helpers
================

Bridge layer between UI templates (which receive raw strings) and core enums
(which own presentation data via dynamic methods).

Three tiers:
    1. Bridge Functions — str → enum → method() with ValueError fallback
    2. Non-Tailwind Helpers — icons, emojis, labels from enum methods
    3. Component Builders — reusable FastHTML components (badges, chips)

Usage in UI components:
    from ui.enum_helpers import (
        get_status_badge_class,    # Bridge function
        get_trend_color,           # Non-Tailwind helper
        render_priority_badge,     # Component builder
    )
"""

from __future__ import annotations

from enum import Enum

from fasthtml.common import Div, Span

from core.models.enums import (
    ActivityType,
    CompletionStatus,
    ContentType,
    EducationalLevel,
    EntityStatus,
    HealthStatus,
    Priority,
    SELCategory,
    TimeOfDay,
    TrendDirection,
)
from core.models.enums.goal_enums import HabitEssentiality
from core.models.enums.user_enums import UserRole
from core.models.event.calendar_models import CalendarItemType
from ui.feedback import Badge, BadgeT


def _enum_method[E: Enum](
    value: str, enum_cls: type[E], method_name: str, fallback: str, *, normalize: bool = True
) -> str:
    """Bridge a raw string to an enum method with ValueError fallback.

    The repeated try/except pattern across all bridge functions is unified here.
    """
    try:
        resolved = enum_cls(value.lower().strip() if normalize else value)
        return getattr(resolved, method_name)()
    except ValueError:
        return fallback


# ============================================================================
# BRIDGE FUNCTIONS — str → enum → Tailwind class
# ============================================================================


def get_status_badge_class(status: str) -> str:
    """Get Tailwind badge class for any entity status string."""
    return _enum_method(
        status, EntityStatus, "get_badge_class", "bg-base-200 text-base-content/70 border-base-200"
    )


def get_status_text_class(status: str) -> str:
    """Get Tailwind text color class for any entity status string."""
    return _enum_method(status, EntityStatus, "get_text_class", "text-muted-foreground")


def get_status_border_class(status: str) -> str:
    """Get Tailwind border-left class for any entity status string."""
    return _enum_method(status, EntityStatus, "get_border_class", "border-l-border")


def get_priority_badge_class(priority: str) -> str:
    """Get Tailwind badge class for a priority level."""
    return _enum_method(
        priority, Priority, "get_badge_class", "bg-muted text-muted-foreground border-border"
    )


def get_priority_text_class(priority: str) -> str:
    """Get Tailwind text color class for a priority level."""
    return _enum_method(priority, Priority, "get_text_class", "text-muted-foreground")


def get_priority_border_class(priority: str) -> str:
    """Get border-left class for a priority/impact level."""
    return _enum_method(priority, Priority, "get_border_class", "border-l-border")


def get_priority_dot_class(priority: str) -> str:
    """Get background dot class for a priority/impact level."""
    return _enum_method(priority, Priority, "get_dot_class", "bg-muted")


def get_essentiality_badge_class(essentiality: str) -> str:
    """Get Tailwind badge class for a habit essentiality level."""
    return _enum_method(
        essentiality,
        HabitEssentiality,
        "get_badge_class",
        "bg-base-200 text-base-content/70 border-base-200",
    )


def get_essentiality_styled(essentiality: str) -> tuple[str, str, str]:
    """Get (emoji, border_class, bg_class) for a habit essentiality level."""
    try:
        return HabitEssentiality(essentiality.lower().strip()).get_styled()
    except ValueError:
        return ("\u26aa", "border-border", "bg-muted")


def get_health_bg_class(status: str) -> str:
    """Get background/border classes for a domain health status."""
    return _enum_method(
        status, HealthStatus, "get_bg_class", "bg-background border-border shadow-xs"
    )


def get_health_dot_class(status: str) -> str:
    """Get dot background class for a domain health status."""
    return _enum_method(status, HealthStatus, "get_dot_class", "bg-muted-foreground")


def get_role_badge_class(role: str) -> str:
    """Get Tailwind badge class for a user role."""
    return _enum_method(
        role, UserRole, "get_badge_class", "bg-muted text-muted-foreground border-border"
    )


def get_submission_status_badge_class(status: str) -> str:
    """Get Tailwind badge class for a submission/report status."""
    return get_status_badge_class(status)


# ============================================================================
# NON-TAILWIND HELPERS — icons, emojis, labels
# ============================================================================


def get_trend_color(trend: str) -> str:
    """Get Tailwind text color class for a trend direction string."""
    return _enum_method(trend, TrendDirection, "get_text_class", "text-muted-foreground")


def get_trend_icon(trend: str) -> str:
    """Get emoji icon for a trend direction string."""
    return _enum_method(trend, TrendDirection, "get_icon", "\u2192")


def get_health_color(status: str) -> str:
    """Get base color name for a health status string."""
    return _enum_method(status, HealthStatus, "get_color", "gray")


def get_health_icon(status: str) -> str:
    """Get emoji icon for a health status string."""
    return _enum_method(status, HealthStatus, "get_icon", "\u2754")


def get_completion_emoji(status: str) -> str:
    """Get emoji for a completion status string."""
    return _enum_method(status, CompletionStatus, "get_emoji", "\u2753")


def get_activity_icon(activity_type: str) -> str:
    """Get emoji icon for an activity type string."""
    return _enum_method(activity_type, ActivityType, "get_icon", "\U0001f4cb")


def get_content_icon(content_type: str) -> str:
    """Get emoji icon for a content type string."""
    return _enum_method(content_type, ContentType, "get_icon", "\U0001f4c4")


def get_educational_icon(level: str) -> str:
    """Get emoji icon for an educational level string."""
    return _enum_method(level, EducationalLevel, "get_icon", "\U0001f4da")


def get_sel_icon(category: str) -> str:
    """Get emoji icon for an SEL category string."""
    return _enum_method(category, SELCategory, "get_icon", "\U0001f4da")


def get_recurrence_label(pattern: str) -> str:
    """Get human-readable label for a recurrence pattern."""
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


def get_time_label(time_of_day: str) -> str:
    """Get human-readable label for time of day."""
    try:
        time_enum = TimeOfDay(time_of_day)
        start, end = time_enum.get_hour_range()
        return f"{start}:00 - {end}:00"
    except ValueError:
        return time_of_day.replace("_", " ").title()


def get_time_icon(time_of_day: str) -> str:
    """Get emoji icon for time of day."""
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


def get_calendar_icon(item_type: str) -> str:
    """Get emoji icon for a calendar item type."""
    return _enum_method(item_type, CalendarItemType, "get_icon", "\U0001f4c5")


# ============================================================================
# COMPONENT BUILDERS
# ============================================================================


def render_priority_badge(priority: str | Priority) -> Span:
    """Render priority as styled badge component."""
    if isinstance(priority, str):
        try:
            priority = Priority(priority)
        except ValueError:
            return Badge("Unknown", variant=BadgeT.neutral)

    badge_class = priority.get_badge_class()
    label = priority.value.title()
    return Badge(label, variant=None, cls=badge_class)


def render_status_badge(status: str | EntityStatus) -> Span:
    """Render status as styled badge component."""
    if isinstance(status, str):
        try:
            status = EntityStatus(status)
        except ValueError:
            return Badge("Unknown", variant=BadgeT.neutral)

    badge_class = status.get_badge_class()
    label = status.value.replace("_", " ").title()
    return Badge(label, variant=None, cls=badge_class)


def render_status_chip(status: str | EntityStatus) -> Span:
    """Render status as styled chip with color indicator."""
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


def render_trend_indicator(trend: str, value: float | None = None) -> Div:
    """Render trend with icon, color, and optional value."""
    color = get_trend_color(trend)
    icon = get_trend_icon(trend)

    content = [Span(icon, cls="text-2xl")]

    if value is not None:
        sign = "+" if trend == "increasing" else "-" if trend == "decreasing" else ""
        content.append(Span(f"{sign}{value}%", cls=f"{color} font-bold"))

    return Div(*content, cls="trend-indicator flex items-center gap-2")


def render_completion_badge(status: str | CompletionStatus) -> Span:
    """Render completion status as badge with emoji."""
    if isinstance(status, str):
        try:
            status = CompletionStatus(status)
        except ValueError:
            return Badge("❓ Unknown", variant=BadgeT.neutral)

    emoji = status.get_emoji()
    label = status.value.title()

    status_to_variant: dict[CompletionStatus, BadgeT] = {
        CompletionStatus.DONE: BadgeT.success,
        CompletionStatus.PARTIAL: BadgeT.info,
        CompletionStatus.SKIPPED: BadgeT.warning,
        CompletionStatus.MISSED: BadgeT.error,
        CompletionStatus.PAUSED: BadgeT.neutral,
    }
    variant = status_to_variant.get(status, BadgeT.neutral)
    return Badge(f"{emoji} {label}", variant=variant)


def render_entity_metadata(
    priority: str | Priority, status: str | EntityStatus, due_date: str | None = None
) -> Div:
    """Render combined metadata display for tasks/events/habits."""
    components = [render_priority_badge(priority), render_status_chip(status)]

    if due_date:
        components.append(Span(f"📅 {due_date}", cls="text-sm text-muted-foreground"))

    return Div(*components, cls="flex items-center gap-2 flex-wrap")
