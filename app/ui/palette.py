"""Re-exports from core.utils.palette for backward compatibility.

Color constants live in core so both core services and UI can import them
without creating a core-imports-ui layering violation.

    from ui.palette import SemanticColor, RelationshipColor, CalendarFallback
"""

from core.utils.palette import (
    CalendarFallback,
    EventTypeColor,
    FrequencyColor,
    RelationshipColor,
    SemanticColor,
    StrengthColor,
)

__all__ = [
    "CalendarFallback",
    "EventTypeColor",
    "FrequencyColor",
    "RelationshipColor",
    "SemanticColor",
    "StrengthColor",
]
