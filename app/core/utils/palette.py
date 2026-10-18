"""Centralized color palette for SKUEL.

Single source of truth for hex color constants used in visualization,
calendar rendering, and graph display. Domain-owned colors live on their
enums (Priority.get_color(), EntityStatus.get_color()); this module holds
colors that do not have a natural enum home.

Usage:
    from core.utils.palette import SemanticColor, RelationshipColor, CalendarFallback
"""

import re
from typing import ClassVar

_HEX_COLOUR = re.compile(r"#([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})")


def rgba(hex_colour: str, alpha: float) -> str:
    """Spell a six-digit hex colour with an alpha, the way Chart.js configs take it.

    ``rgba("#3B82F6", 0.8)`` is ``"rgba(59, 130, 246, 0.8)"``.
    """
    match = _HEX_COLOUR.fullmatch(hex_colour)
    if match is None:
        raise ValueError(f"rgba() takes a six-digit hex colour, got {hex_colour!r}")
    red, green, blue = (int(component, 16) for component in match.groups())
    return f"rgba({red}, {green}, {blue}, {alpha:g})"


class SemanticColor:
    """Chart color cycling palette — semantic names for visualization.

    Used by Chart.js formatters for dataset coloring when domain-specific
    enum colors are not applicable (e.g., generic completion/trend charts).
    """

    PRIMARY = "#3B82F6"  # Blue
    SUCCESS = "#10B981"  # Green
    WARNING = "#F59E0B"  # Amber
    DANGER = "#EF4444"  # Red
    INFO = "#6366F1"  # Indigo
    NEUTRAL = "#6B7280"  # Gray

    ALL: ClassVar[list[str]] = [PRIMARY, SUCCESS, WARNING, DANGER, INFO, NEUTRAL]


class ChartColor:
    """Series colours for the /insights charts and the life-path alignment radar.

    Tailwind shades, named by what they mark. Chart.js takes them through
    ``rgba()`` with one of the alphas below.
    """

    IMPACT_CRITICAL = "#DC2626"  # red-600
    IMPACT_HIGH = "#EA580C"  # orange-600
    IMPACT_MEDIUM = "#FACC15"  # yellow-400
    IMPACT_LOW = "#22C55E"  # green-500

    ACTIONED = "#22C55E"  # green-500
    NOT_ACTIONED = "#9CA3AF"  # gray-400

    # One colour per category, in order; Chart.js repeats the list past its end.
    CATEGORIES: ClassVar[list[str]] = [
        SemanticColor.INFO,  # indigo-500
        "#8B5CF6",  # violet-500
        "#A855F7",  # purple-500
        "#EC4899",  # pink-500
        "#F43F5E",  # rose-500
        SemanticColor.PRIMARY,  # blue-500
    ]

    POINT_BORDER = "#fff"

    FILL_ALPHA = 0.8  # bars and doughnut segments
    MUTED_ALPHA = 0.3  # the remainder of a gauge
    AREA_ALPHA = 0.2  # the area inside a radar line


class RelationshipColor:
    """Edge colors for lateral relationship graph visualization.

    Used by Vis.js Network graph to style edges by relationship type.
    """

    BLOCKS = "#EF4444"  # Red
    PREREQUISITE_FOR = "#F59E0B"  # Orange
    ALTERNATIVE_TO = "#3B82F6"  # Blue
    COMPLEMENTARY_TO = "#10B981"  # Green
    RELATED_TO = "#6B7280"  # Gray
    SIBLING = "#8B5CF6"  # Purple
    DEFAULT = "#6B7280"  # Gray fallback

    _MAP: ClassVar[dict[str, str]] = {
        "BLOCKS": BLOCKS,
        "PREREQUISITE_FOR": PREREQUISITE_FOR,
        "ALTERNATIVE_TO": ALTERNATIVE_TO,
        "COMPLEMENTARY_TO": COMPLEMENTARY_TO,
        "RELATED_TO": RELATED_TO,
        "SIBLING": SIBLING,
    }

    @classmethod
    def for_type(cls, rel_type: str) -> str:
        """Get color for a relationship type string (e.g., 'BLOCKS')."""
        return cls._MAP.get(rel_type, cls.DEFAULT)


class FrequencyColor:
    """Calendar habit colors by recurrence frequency."""

    DAILY = "#22c55e"  # Green
    WEEKLY = "#3b82f6"  # Blue
    MONTHLY = "#8b5cf6"  # Purple
    DEFAULT = "#22c55e"  # Green fallback

    _MAP: ClassVar[dict[str, str]] = {
        "daily": DAILY,
        "weekly": WEEKLY,
        "monthly": MONTHLY,
    }

    @classmethod
    def for_type(cls, frequency: str) -> str:
        """Get color for a frequency string (e.g., 'daily')."""
        return cls._MAP.get(frequency, cls.DEFAULT)


class StrengthColor:
    """Principle strength level colors."""

    CORE = "#7C3AED"  # Violet
    STRONG = "#2563EB"  # Blue
    MODERATE = "#0891B2"  # Cyan
    DEVELOPING = "#059669"  # Emerald
    EXPLORING = "#6B7280"  # Gray

    _MAP: ClassVar[dict[str, str]] = {
        "core": CORE,
        "strong": STRONG,
        "moderate": MODERATE,
        "developing": DEVELOPING,
        "exploring": EXPLORING,
    }

    @classmethod
    def for_level(cls, strength: str) -> str:
        """Get hex color for a strength level (e.g., 'core')."""
        return cls._MAP.get(strength, cls.EXPLORING)


class CalendarFallback:
    """Fallback colors when domain enum methods are unavailable.

    Used by calendar_service.py for cases where entities lack status/priority
    enum values, or for domain types that don't have enum color methods.
    """

    HABIT = "#8B5CF6"  # Purple
    DEFAULT = "#3B82F6"  # Blue


__all__ = [
    "CalendarFallback",
    "ChartColor",
    "FrequencyColor",
    "RelationshipColor",
    "SemanticColor",
    "StrengthColor",
    "rgba",
]
