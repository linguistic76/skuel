"""Activity Domains hub view — all 6 domains as HTMX-loaded preview blocks.

Each block has a colored domain header (icon + title + "View all" link)
and 3 priority-sorted cards loaded via HTMX from /api/profile/{slug}/preview.
"""

from fasthtml.common import A, Div, P, Span
from monsterui.franken import UkIcon

# (label, tab_id, icon, hex_color)
_ACTIVITY_TABS: list[tuple[str, str, str, str]] = [
    ("Tasks", "tasks", "check-square", "#3B82F6"),
    ("Goals", "goals", "target", "#F59E0B"),
    ("Habits", "habits", "repeat", "#10B981"),
    ("Events", "events", "calendar", "#8B5CF6"),
    ("Choices", "choices", "git-branch", "#F97316"),
    ("Principles", "principles", "compass", "#EC4899"),
]


def _activity_domain_block(label: str, tab_id: str, icon: str, color: str) -> Div:
    """A single Activity Domain block: colored header + HTMX-loaded card preview."""
    return Div(
        # Domain header — icon + title + "View all" link
        Div(
            A(
                UkIcon(icon, cls="size-4"),
                Span(
                    label,
                    cls="text-sm font-semibold uppercase tracking-wider",
                ),
                href=f"/{tab_id}",
                cls="flex items-center gap-2 no-underline hover:opacity-80 transition-opacity",
                style=f"color: {color};",
            ),
            A(
                "View all \u2192",
                href=f"/{tab_id}",
                cls="text-xs font-medium text-muted-foreground hover:text-primary transition-colors",
            ),
            cls="flex items-center justify-between mb-3",
        ),
        # HTMX lazy-loaded card content
        Div(
            P("Loading...", cls="text-center text-muted-foreground py-4"),
            id=f"act-panel-{tab_id}",
            hx_get=f"/api/profile/{tab_id}/preview",
            hx_trigger="load",
            hx_swap="innerHTML",
        ),
        cls="pb-5 mb-5 border-b border-border last:border-b-0 last:mb-0 last:pb-0",
    )


def ActivityHubView() -> Div:
    """All 6 Activity Domains as scrollable blocks with 3 preview cards each."""
    return Div(
        *[
            _activity_domain_block(label, tab_id, icon, color)
            for label, tab_id, icon, color in _ACTIVITY_TABS
        ],
    )
