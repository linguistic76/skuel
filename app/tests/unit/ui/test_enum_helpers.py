"""
Tests for UI Enum Helpers
==========================

Tests bridge functions, non-Tailwind helpers, and component builders.
"""

from ui.enum_helpers import (
    get_activity_icon,
    get_calendar_icon,
    get_completion_emoji,
    get_content_icon,
    get_educational_icon,
    get_essentiality_badge_class,
    get_essentiality_styled,
    get_health_bg_class,
    get_health_color,
    get_health_dot_class,
    get_health_icon,
    get_priority_badge_class,
    get_priority_border_class,
    get_priority_dot_class,
    get_priority_text_class,
    get_recurrence_label,
    get_role_badge_class,
    get_sel_icon,
    get_status_badge_class,
    get_status_text_class,
    get_submission_status_badge_class,
    get_time_icon,
    get_time_label,
    get_trend_color,
    get_trend_icon,
    render_completion_badge,
    render_priority_badge,
    render_status_badge,
    render_status_chip,
    render_trend_indicator,
)

# ============================================================================
# BRIDGE FUNCTIONS — str → Tailwind class
# ============================================================================


class TestStatusBridgeFunctions:
    def test_status_badge_class_active(self) -> None:
        result = get_status_badge_class("active")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_status_badge_class_with_whitespace(self) -> None:
        result = get_status_badge_class("  active  ")
        assert isinstance(result, str)
        assert "gray" not in result  # Should not be fallback

    def test_status_badge_class_invalid(self) -> None:
        result = get_status_badge_class("nonexistent_status")
        assert result == "bg-base-200 text-base-content/70 border-base-200"

    def test_status_text_class_active(self) -> None:
        result = get_status_text_class("active")
        assert isinstance(result, str)

    def test_status_text_class_invalid(self) -> None:
        result = get_status_text_class("bogus")
        assert result == "text-muted-foreground"


class TestPriorityBridgeFunctions:
    def test_priority_badge_class_high(self) -> None:
        result = get_priority_badge_class("high")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_priority_badge_class_invalid(self) -> None:
        result = get_priority_badge_class("super_duper")
        assert result == "bg-muted text-muted-foreground border-border"

    def test_priority_text_class_medium(self) -> None:
        result = get_priority_text_class("medium")
        assert isinstance(result, str)

    def test_priority_text_class_invalid(self) -> None:
        result = get_priority_text_class("invalid")
        assert result == "text-muted-foreground"

    def test_priority_border_class_low(self) -> None:
        result = get_priority_border_class("low")
        assert isinstance(result, str)

    def test_priority_border_class_invalid(self) -> None:
        result = get_priority_border_class("invalid")
        assert result == "border-l-border"

    def test_priority_dot_class_critical(self) -> None:
        result = get_priority_dot_class("critical")
        assert isinstance(result, str)

    def test_priority_dot_class_invalid(self) -> None:
        result = get_priority_dot_class("invalid")
        assert result == "bg-muted"


class TestEssentialityBridge:
    def test_essentiality_badge_class_valid(self) -> None:
        result = get_essentiality_badge_class("essential")
        assert isinstance(result, str)

    def test_essentiality_badge_class_invalid(self) -> None:
        result = get_essentiality_badge_class("invalid")
        assert result == "bg-base-200 text-base-content/70 border-base-200"

    def test_essentiality_styled_valid(self) -> None:
        emoji, border, bg = get_essentiality_styled("essential")
        assert isinstance(emoji, str)
        assert isinstance(border, str)
        assert isinstance(bg, str)

    def test_essentiality_styled_invalid(self) -> None:
        emoji, border, bg = get_essentiality_styled("invalid")
        assert emoji == "\u26aa"
        assert border == "border-border"
        assert bg == "bg-muted"


class TestHealthBridge:
    def test_health_bg_class_valid(self) -> None:
        result = get_health_bg_class("healthy")
        assert isinstance(result, str)

    def test_health_bg_class_invalid(self) -> None:
        result = get_health_bg_class("invalid")
        assert result == "bg-background border-border shadow-xs"

    def test_health_dot_class_valid(self) -> None:
        result = get_health_dot_class("healthy")
        assert isinstance(result, str)

    def test_health_dot_class_invalid(self) -> None:
        result = get_health_dot_class("invalid")
        assert result == "bg-muted-foreground"


class TestRoleBridge:
    def test_role_badge_class_admin(self) -> None:
        result = get_role_badge_class("admin")
        assert isinstance(result, str)

    def test_role_badge_class_invalid(self) -> None:
        result = get_role_badge_class("superadmin")
        assert result == "bg-muted text-muted-foreground border-border"


class TestSubmissionStatusBridge:
    def test_delegates_to_status_badge(self) -> None:
        result = get_submission_status_badge_class("completed")
        expected = get_status_badge_class("completed")
        assert result == expected


# ============================================================================
# NON-TAILWIND HELPERS — icons, emojis, labels
# ============================================================================


class TestTrendHelpers:
    def test_trend_color_valid(self) -> None:
        result = get_trend_color("increasing")
        assert isinstance(result, str)

    def test_trend_color_invalid(self) -> None:
        result = get_trend_color("zigzag")
        assert result == "text-muted-foreground"

    def test_trend_icon_valid(self) -> None:
        result = get_trend_icon("increasing")
        assert isinstance(result, str)

    def test_trend_icon_invalid(self) -> None:
        result = get_trend_icon("zigzag")
        assert result == "→"


class TestHealthHelpers:
    def test_health_color_valid(self) -> None:
        result = get_health_color("healthy")
        assert isinstance(result, str)

    def test_health_color_invalid(self) -> None:
        result = get_health_color("invalid")
        assert result == "gray"

    def test_health_icon_valid(self) -> None:
        result = get_health_icon("healthy")
        assert isinstance(result, str)

    def test_health_icon_invalid(self) -> None:
        result = get_health_icon("invalid")
        assert result == "❔"


class TestCompletionEmoji:
    def test_valid_status(self) -> None:
        result = get_completion_emoji("done")
        assert isinstance(result, str)

    def test_invalid_status(self) -> None:
        result = get_completion_emoji("invalid")
        assert result == "❓"


class TestActivityIcon:
    def test_valid_type(self) -> None:
        result = get_activity_icon("task")
        assert isinstance(result, str)

    def test_invalid_type(self) -> None:
        result = get_activity_icon("invalid")
        assert result == "📋"


class TestContentIcon:
    def test_valid_type(self) -> None:
        result = get_content_icon("article")
        assert isinstance(result, str)

    def test_invalid_type(self) -> None:
        result = get_content_icon("invalid")
        assert result == "📄"


class TestEducationalIcon:
    def test_valid_level(self) -> None:
        result = get_educational_icon("beginner")
        assert isinstance(result, str)

    def test_invalid_level(self) -> None:
        result = get_educational_icon("invalid")
        assert result == "📚"


class TestSELIcon:
    def test_valid_category(self) -> None:
        result = get_sel_icon("self_awareness")
        assert isinstance(result, str)

    def test_invalid_category(self) -> None:
        result = get_sel_icon("invalid")
        assert result == "📚"


class TestRecurrenceLabel:
    def test_known_patterns(self) -> None:
        assert get_recurrence_label("daily") == "Every day"
        assert get_recurrence_label("weekly") == "Every week"
        assert get_recurrence_label("monthly") == "Every month"
        assert get_recurrence_label("none") == "One-time"

    def test_unknown_pattern(self) -> None:
        result = get_recurrence_label("biannually")
        assert result == "Biannually"  # Falls back to .title()


class TestTimeLabel:
    def test_valid_time(self) -> None:
        result = get_time_label("morning")
        assert ":" in result  # Contains hour range

    def test_invalid_time(self) -> None:
        result = get_time_label("invalid_time")
        assert result == "Invalid Time"


class TestTimeIcon:
    def test_known_times(self) -> None:
        assert get_time_icon("morning") == "☀️"
        assert get_time_icon("evening") == "🌆"
        assert get_time_icon("night") == "🌙"

    def test_unknown_time(self) -> None:
        assert get_time_icon("invalid") == "🕐"


class TestCalendarIcon:
    def test_valid_type(self) -> None:
        result = get_calendar_icon("event")
        assert isinstance(result, str)

    def test_invalid_type(self) -> None:
        result = get_calendar_icon("invalid")
        assert result == "📅"


# ============================================================================
# COMPONENT BUILDERS
# ============================================================================


class TestRenderPriorityBadge:
    def test_string_input(self) -> None:
        result = render_priority_badge("high")
        assert result is not None

    def test_enum_input(self) -> None:
        from core.models.enums import Priority

        result = render_priority_badge(Priority.HIGH)
        assert result is not None

    def test_invalid_string(self) -> None:
        result = render_priority_badge("invalid")
        assert result is not None  # Returns "Unknown" badge


class TestRenderStatusBadge:
    def test_string_input(self) -> None:
        result = render_status_badge("active")
        assert result is not None

    def test_enum_input(self) -> None:
        from core.models.enums import EntityStatus

        result = render_status_badge(EntityStatus.ACTIVE)
        assert result is not None

    def test_invalid_string(self) -> None:
        result = render_status_badge("invalid")
        assert result is not None


class TestRenderStatusChip:
    def test_string_input(self) -> None:
        result = render_status_chip("active")
        assert result is not None

    def test_invalid_string(self) -> None:
        result = render_status_chip("invalid")
        assert result is not None


class TestRenderTrendIndicator:
    def test_without_value(self) -> None:
        result = render_trend_indicator("increasing")
        assert result is not None

    def test_with_value(self) -> None:
        result = render_trend_indicator("increasing", value=15.0)
        assert result is not None


class TestRenderCompletionBadge:
    def test_string_input(self) -> None:
        result = render_completion_badge("done")
        assert result is not None

    def test_enum_input(self) -> None:
        from core.models.enums import CompletionStatus

        result = render_completion_badge(CompletionStatus.DONE)
        assert result is not None

    def test_invalid_string(self) -> None:
        result = render_completion_badge("invalid")
        assert result is not None
