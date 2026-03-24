"""Centralized presentation palette for SKUEL.

Single source of truth for hex color constants used in visualization,
calendar rendering, and graph display. Domain-owned colors live on their
enums (Priority.get_color(), EntityStatus.get_color()); this module holds
colors that do not have a natural enum home.

Follows the same class-based grouping pattern as ui/tokens.py.

Usage:
    from ui.palette import SemanticColor, RelationshipColor, CalendarFallback

    # Chart color cycling
    colors = SemanticColor.ALL

    # Relationship edge color
    edge_color = RelationshipColor.for_type("BLOCKS")

    # Calendar fallback when no enum method available
    color = CalendarFallback.DEFAULT
"""


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

    ALL = [PRIMARY, SUCCESS, WARNING, DANGER, INFO, NEUTRAL]


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

    _MAP: dict[str, str] = {
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


class EventTypeColor:
    """Calendar item colors by event type."""

    MEETING = "#3b82f6"  # Blue
    DEADLINE = "#ef4444"  # Red
    PERSONAL = "#22c55e"  # Green
    WORK = "#f97316"  # Orange
    SOCIAL = "#8b5cf6"  # Purple
    LEARNING = "#06b6d4"  # Cyan
    DEFAULT = "#3b82f6"  # Blue fallback

    _MAP: dict[str, str] = {
        "meeting": MEETING,
        "deadline": DEADLINE,
        "personal": PERSONAL,
        "work": WORK,
        "social": SOCIAL,
        "learning": LEARNING,
    }

    @classmethod
    def for_type(cls, event_type: str) -> str:
        """Get color for an event type string (e.g., 'meeting')."""
        return cls._MAP.get(event_type, cls.DEFAULT)


class FrequencyColor:
    """Calendar habit colors by recurrence frequency."""

    DAILY = "#22c55e"  # Green
    WEEKLY = "#3b82f6"  # Blue
    MONTHLY = "#8b5cf6"  # Purple
    DEFAULT = "#22c55e"  # Green fallback

    _MAP: dict[str, str] = {
        "daily": DAILY,
        "weekly": WEEKLY,
        "monthly": MONTHLY,
    }

    @classmethod
    def for_type(cls, frequency: str) -> str:
        """Get color for a frequency string (e.g., 'daily')."""
        return cls._MAP.get(frequency, cls.DEFAULT)


class CalendarFallback:
    """Fallback colors when domain enum methods are unavailable.

    Used by calendar_service.py for cases where entities lack status/priority
    enum values, or for domain types that don't have enum color methods.
    """

    HABIT = "#8B5CF6"  # Purple
    DEFAULT = "#3B82F6"  # Blue
