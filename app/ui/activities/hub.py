"""Activity Domain block definitions — Activities tab on /profile.

ACTIVITY_BLOCKS feeds the Activities tab in ui/profile/hub.py (accordion
blocks, lazy HTMX previews). render_domain_card_preview renders the
/api/profile/{slug}/preview fragments those blocks fetch.
"""

from typing import Any

from fasthtml.common import Div, Span

from core.models.enums import Priority
from ui.patterns.hub import HubBlockData, HubPreviewCard, HubPreviewEmpty, HubPreviewGrid

ACTIVITY_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Tasks", "tasks", "check-square", "#3B82F6", "/tasks", "/api/profile/tasks/preview"
    ),
    HubBlockData("Goals", "goals", "target", "#F59E0B", "/goals", "/api/profile/goals/preview"),
    HubBlockData("Habits", "habits", "repeat", "#10B981", "/habits", "/api/profile/habits/preview"),
    HubBlockData(
        "Events", "events", "calendar", "#8B5CF6", "/events", "/api/profile/events/preview"
    ),
    HubBlockData(
        "Choices", "choices", "git-branch", "#F97316", "/choices", "/api/profile/choices/preview"
    ),
    HubBlockData(
        "Principles",
        "principles",
        "compass",
        "#EC4899",
        "/principles",
        "/api/profile/principles/preview",
    ),
]


_PRIORITY_COLORS: dict[Priority, str] = {
    Priority.CRITICAL: "bg-red-500",
    Priority.HIGH: "bg-orange-500",
    Priority.MEDIUM: "bg-blue-500",
    Priority.LOW: "bg-gray-400",
}

_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.CRITICAL: "P1",
    Priority.HIGH: "P2",
    Priority.MEDIUM: "P3",
    Priority.LOW: "P4",
}


def _coerce_priority(item: Any) -> Priority:
    """Coerce an item's priority to the Priority enum (backends may return strings)."""
    raw = getattr(item, "priority", Priority.LOW)
    if isinstance(raw, Priority):
        return raw
    try:
        return Priority(str(raw).lower())
    except ValueError:
        return Priority.LOW


def _priority_badge(item: Any) -> Span:
    """Colored priority dot + P1–P4 label."""
    priority = _coerce_priority(item)
    color = _PRIORITY_COLORS.get(priority, "bg-gray-400")
    label = _PRIORITY_LABELS.get(priority, "P4")
    return Span(
        Span(cls=f"w-2 h-2 rounded-full {color} shrink-0"),
        Span(label, cls="text-10 font-medium text-muted-foreground"),
        cls="inline-flex items-center gap-1",
        title=f"Priority: {priority.value.title()}",
    )


def render_domain_card_preview(items: list[Any], slug: str) -> Div:
    """Render an Activity Domain preview fragment — up to 3 title-first cards.

    Called from the /api/profile/{slug}/preview endpoint. Items arrive
    pre-filtered (active only), priority-sorted, and capped at 3 by
    ProfileOrchestrator.get_domain_preview_items.
    """
    if not items:
        return HubPreviewEmpty(f"active {slug}")

    cards = [
        HubPreviewCard(
            title=getattr(item, "title", "Untitled") or "Untitled",
            href=(
                f"/{slug}/detail?uid={getattr(item, 'uid', '')}"
                if getattr(item, "uid", "")
                else f"/{slug}"
            ),
            badge=_priority_badge(item),
            description=getattr(item, "description", None),
        )
        for item in items
    ]
    return HubPreviewGrid(cards)
