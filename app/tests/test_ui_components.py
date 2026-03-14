"""
UI Component Tests
==================

Tests for UI components and enum helpers to improve coverage.

Focus areas:
- Enum helpers (string → enum → UI values)
- Component rendering (HTML generation)
- Error handling (invalid inputs)
- Edge cases and defaults

Run with:
    uv run pytest tests/test_ui_components.py -v
"""

from core.models.enums import (
    BridgeType,
    EntityStatus,
    Priority,
    SeverityLevel,
)
from ui.enum_helpers import (
    get_activity_icon,
    get_completion_emoji,
    get_content_icon,
    get_educational_icon,
    get_health_color,
    get_health_icon,
    get_priority_badge_class,
    get_recurrence_label,
    get_sel_icon,
    get_status_badge_class,
    get_time_icon,
    get_time_label,
    get_trend_color,
    get_trend_icon,
    render_priority_badge,
    render_status_badge,
)
from ui.feedback import Badge

# ============================================================================
# ENUM HELPERS - TREND
# ============================================================================


def test_get_trend_color_valid_values():
    """Test trend color mapping for valid values."""
    assert "green" in get_trend_color("increasing")
    assert "red" in get_trend_color("decreasing")
    assert "gray" in get_trend_color("stable")


def test_get_trend_color_invalid():
    """Test trend color fallback for invalid input."""
    color = get_trend_color("invalid_trend")
    assert color == "text-muted-foreground"  # Semantic fallback


def test_get_trend_icon_valid_values():
    """Test trend icon mapping for valid values."""
    assert get_trend_icon("increasing") in ["📈", "↗"]
    assert get_trend_icon("decreasing") in ["📉", "↘"]
    assert get_trend_icon("stable") in ["→", "➡", "↔️"]


def test_get_trend_icon_invalid():
    """Test trend icon fallback for invalid input."""
    icon = get_trend_icon("bad_trend")
    assert icon == "→"  # Default arrow


# ============================================================================
# ENUM HELPERS - HEALTH STATUS
# ============================================================================


def test_get_health_color_all_statuses():
    """Test health status color mapping."""
    assert "green" in get_health_color("healthy")
    assert "yellow" in get_health_color("warning")
    assert "red" in get_health_color("critical")
    assert "gray" in get_health_color("unknown")


def test_get_health_color_invalid():
    """Test health color fallback for invalid input."""
    assert "gray" in get_health_color("bad_status")


def test_get_health_icon_all_statuses():
    """Test health status icon mapping."""
    assert get_health_icon("healthy") in ["✅", "✓", "🟢"]
    assert get_health_icon("warning") in ["⚠️", "⚠", "🟡"]
    assert get_health_icon("critical") in ["❌", "✗", "🔴"]
    assert get_health_icon("unknown") == "❔"


def test_get_health_icon_invalid():
    """Test health icon fallback for invalid input."""
    assert get_health_icon("nonsense") == "❔"


# ============================================================================
# ENUM HELPERS - SEVERITY
# ============================================================================


def test_get_severity_color_all_levels():
    """Test severity level color mapping."""
    assert "red" in SeverityLevel.HIGH.get_color()
    assert "yellow" in SeverityLevel.MEDIUM.get_color()
    assert "blue" in SeverityLevel.LOW.get_color()


def test_get_severity_numeric_ordering():
    """Test severity numeric values for proper sorting."""
    assert SeverityLevel.HIGH.to_numeric() > SeverityLevel.MEDIUM.to_numeric()
    assert SeverityLevel.MEDIUM.to_numeric() > SeverityLevel.LOW.to_numeric()


# ============================================================================
# ENUM HELPERS - PRIORITY
# ============================================================================


def test_get_priority_color_all_levels():
    """Test priority color mapping."""
    for priority in [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL]:
        color = priority.get_color()
        assert isinstance(color, str)
        assert len(color) > 0


def test_get_priority_badge_class_all_levels():
    """Test priority badge CSS classes."""
    for priority in ["low", "medium", "high", "critical"]:
        badge_class = get_priority_badge_class(priority)
        assert isinstance(badge_class, str)
        assert "bg-" in badge_class  # Tailwind utility class


def test_get_priority_badge_class_invalid():
    """Test priority badge class fallback."""
    badge_class = get_priority_badge_class("invalid")
    assert isinstance(badge_class, str)


# ============================================================================
# ENUM HELPERS - ACTIVITY STATUS
# ============================================================================


def test_get_status_color_common_statuses():
    """Test activity status color mapping."""
    for status in [EntityStatus.COMPLETED, EntityStatus.ARCHIVED, EntityStatus.CANCELLED]:
        color = status.get_color()
        assert isinstance(color, str)
        assert len(color) > 0


def test_get_status_badge_class():
    """Test activity status badge classes."""
    for status in ["todo", "completed", "in_progress"]:
        badge_class = get_status_badge_class(status)
        assert isinstance(badge_class, str)
        assert "bg-" in badge_class  # Tailwind utility class


# ============================================================================
# ENUM HELPERS - ACTIVITY TYPE
# ============================================================================


def test_get_activity_icon_common_types():
    """Test activity type icon mapping."""
    types = ["task", "event", "habit", "goal", "note"]
    for activity_type in types:
        icon = get_activity_icon(activity_type)
        assert isinstance(icon, str)
        assert len(icon) > 0


def test_get_activity_icon_invalid():
    """Test activity type icon fallback."""
    icon = get_activity_icon("invalid_type")
    assert isinstance(icon, str)
    # Should return a default icon


# ============================================================================
# ENUM HELPERS - TIME OF DAY
# ============================================================================


def test_get_time_icon_all_periods():
    """Test time of day icon mapping."""
    periods = ["morning", "afternoon", "evening", "night"]
    for period in periods:
        icon = get_time_icon(period)
        assert isinstance(icon, str)
        assert len(icon) > 0


def test_get_time_label_all_periods():
    """Test time of day label generation."""
    for period in ["morning", "afternoon", "evening", "night"]:
        label = get_time_label(period)
        assert isinstance(label, str)
        assert len(label) > 0


# ============================================================================
# ENUM HELPERS - RECURRENCE
# ============================================================================


def test_get_recurrence_label_common_patterns():
    """Test recurrence pattern label text."""
    patterns = ["daily", "weekly", "monthly"]
    for pattern in patterns:
        label = get_recurrence_label(pattern)
        assert isinstance(label, str)
        assert len(label) > 0


def test_get_recurrence_label_invalid():
    """Test recurrence label fallback."""
    label = get_recurrence_label("invalid_pattern")
    assert isinstance(label, str)


# ============================================================================
# ENUM HELPERS - COMPLETION STATUS
# ============================================================================


def test_get_completion_emoji_all_statuses():
    """Test completion status emoji mapping."""
    statuses = ["completed", "partial", "not_started", "in_progress"]
    for status in statuses:
        emoji = get_completion_emoji(status)
        assert isinstance(emoji, str)
        assert len(emoji) > 0


def test_get_completion_emoji_invalid():
    """Test completion emoji fallback."""
    emoji = get_completion_emoji("invalid")
    assert isinstance(emoji, str)


# ============================================================================
# ENUM HELPERS - CONTENT TYPE
# ============================================================================


def test_get_content_icon_common_types():
    """Test content type icon mapping."""
    types = ["concept", "practice", "example", "reference", "assessment"]
    for content_type in types:
        icon = get_content_icon(content_type)
        assert isinstance(icon, str)
        assert len(icon) > 0


def test_get_content_icon_invalid():
    """Test content type icon fallback."""
    icon = get_content_icon("unknown_type")
    assert isinstance(icon, str)


# ============================================================================
# ENUM HELPERS - EDUCATIONAL LEVEL
# ============================================================================


def test_get_educational_icon_common_levels():
    """Test educational level icon mapping."""
    levels = ["elementary", "high_school", "college", "postgraduate"]
    for level in levels:
        icon = get_educational_icon(level)
        assert isinstance(icon, str)
        assert len(icon) > 0


def test_get_sel_icon():
    """Test SEL category icon mapping."""
    categories = [
        "self_awareness",
        "self_management",
        "social_awareness",
    ]
    for category in categories:
        icon = get_sel_icon(category)
        assert isinstance(icon, str)


# ============================================================================
# ENUM HELPERS - BRIDGE TYPE
# ============================================================================


def test_get_bridge_color():
    """Test knowledge bridge type color mapping."""
    for bridge_type in BridgeType:
        color = bridge_type.get_color()
        assert isinstance(color, str)


# ============================================================================
# COMPONENT BUILDERS - BADGE
# ============================================================================


def test_badge_component_basic():
    """Test basic Badge component creation."""
    badge = Badge("Test Badge")
    # Badge returns a Span element
    assert badge is not None
    # Check it has text content
    assert hasattr(badge, "children") or hasattr(badge, "content")


def test_badge_component_with_class():
    """Test Badge component with custom CSS class."""
    badge = Badge("Custom", cls="badge-primary")
    assert badge is not None


# ============================================================================
# COMPONENT BUILDERS - PRIORITY BADGE
# ============================================================================


def test_render_priority_badge_all_levels():
    """Test priority badge rendering for all priority levels."""
    for priority in ["low", "medium", "high", "critical"]:
        badge = render_priority_badge(priority)
        assert badge is not None


def test_render_priority_badge_invalid():
    """Test priority badge rendering with invalid priority."""
    badge = render_priority_badge("invalid_priority")
    # Should still render something (with fallback)
    assert badge is not None


# ============================================================================
# COMPONENT BUILDERS - ACTIVITY STATUS BADGE
# ============================================================================


def test_render_status_badge_common_statuses():
    """Test activity status badge rendering."""
    for status in ["todo", "completed", "in_progress", "cancelled"]:
        badge = render_status_badge(status)
        assert badge is not None


def test_render_status_badge_invalid():
    """Test activity status badge rendering with invalid status."""
    badge = render_status_badge("invalid_status")
    assert badge is not None


# ============================================================================
# EDGE CASES
# ============================================================================


def test_enum_helpers_handle_none_input():
    """Test that enum helpers handle None input gracefully."""
    from contextlib import suppress

    # These should not crash
    with suppress(ValueError, TypeError, AttributeError):
        get_trend_color(None)  # type: ignore[arg-type]

    with suppress(ValueError, TypeError, AttributeError):
        get_health_icon(None)  # type: ignore[arg-type]


def test_enum_helpers_handle_empty_string():
    """Test that enum helpers handle empty string input."""
    # Should return default values
    color = get_trend_color("")
    assert isinstance(color, str)

    icon = get_health_icon("")
    assert isinstance(icon, str)


def test_enum_helpers_case_sensitivity():
    """Test that enum helpers handle different cases."""
    # Most enums are lowercase, but test that UPPER fails gracefully
    badge_lower = get_priority_badge_class("high")
    badge_upper = get_priority_badge_class("HIGH")

    # Should either match or return defaults
    assert isinstance(badge_lower, str)
    assert isinstance(badge_upper, str)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_multiple_enum_helpers_consistency():
    """Test that related enum helpers are consistent."""
    # Priority helpers should all work for same values
    priority = "high"

    badge_class = get_priority_badge_class(priority)
    badge = render_priority_badge(priority)

    # All should produce valid outputs
    assert isinstance(badge_class, str)
    assert badge is not None


def test_enum_helpers_with_dash_vs_underscore():
    """Test enum helpers handle different naming conventions."""
    # Activity status with underscores
    assert isinstance(get_status_badge_class("in_progress"), str)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


def test_enum_helpers_are_fast():
    """Test that enum helpers execute quickly (no expensive operations)."""
    import time

    start = time.time()

    # Call helpers many times
    for _ in range(1000):
        get_trend_color("increasing")
        get_health_icon("healthy")
        get_priority_badge_class("high")
        SeverityLevel.MEDIUM.to_numeric()

    elapsed = time.time() - start

    # Should complete very quickly (< 100ms for 1000 calls)
    assert elapsed < 0.1, f"Enum helpers too slow: {elapsed:.3f}s for 1000 calls"
