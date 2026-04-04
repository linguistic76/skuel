"""Explore graph view — Vis.js graph component for the Explore sidebar.

Renders an interactive force-directed graph as the hero element of the
Explore sidebar. Supports two modes:
- Hub mode: user's learning universe (studying + in-progress + connections)
- Entity mode: centered on a specific Ku or PathStep with lateral relationships

Includes filter tabs (Learning/Saved/All) and a full-screen overlay expansion.

Usage:
    from ui.explore.graph import ExploreGraphView

    graph = ExploreGraphView(mode="entity", entity_uid="ku_abc", entity_type="ku")
"""

from typing import TYPE_CHECKING

from fasthtml.common import Button, Div, Span
from monsterui.franken import UkIcon

if TYPE_CHECKING:
    from fasthtml.common import FT


# Filter tab configuration
_FILTER_TABS = [
    ("all", "All"),
    ("learning", "Learning"),
    ("saved", "Saved"),
]


def _filter_tabs() -> "FT":
    """Render filter tab buttons below the graph."""
    tabs = []
    for filter_id, label in _FILTER_TABS:
        tabs.append(
            Button(
                label,
                type="button",
                cls="px-2.5 py-1 text-xs rounded-full border transition-colors cursor-pointer",
                **{
                    ":class": f"filter === '{filter_id}'"
                    " ? 'bg-primary text-primary-foreground border-primary'"
                    " : 'bg-background text-muted-foreground border-border hover:bg-accent'",
                    "@click": f"setFilter('{filter_id}')",
                },
            )
        )
    return Div(*tabs, cls="flex gap-1.5 px-2 py-2")


def ExploreGraphView(
    mode: str = "hub",
    entity_uid: str = "",
    entity_type: str = "",
) -> "FT":
    """Interactive Vis.js graph for the Explore sidebar.

    Args:
        mode: 'hub' for learning universe, 'entity' for entity-centered.
        entity_uid: UID of the current entity (entity mode only).
        entity_type: 'ku' or 'ps' (entity mode only).
    """
    alpine_args = f"'{mode}', '{entity_uid}', '{entity_type}'"

    # Single graph container — CSS repositions it when expanded
    graph_container = Div(
        id="explore-graph-container",
        cls="w-full h-full",
    )

    # Loading overlay
    loading_overlay = Div(
        Div(
            Span(
                cls="animate-spin inline-block w-5 h-5 border-2"
                " border-primary border-t-transparent rounded-full"
            ),
            Span("Loading...", cls="text-xs text-muted-foreground ml-2"),
            cls="flex items-center gap-2",
        ),
        cls="absolute inset-0 flex items-center justify-center bg-background/60",
        x_show="loading",
        x_cloak=True,
    )

    # Error display
    error_display = Div(
        Span("", cls="text-xs text-destructive", **{"x-text": "error"}),
        cls="absolute inset-0 flex items-center justify-center",
        x_show="error && !loading",
        x_cloak=True,
    )

    # Expand button (visible in sidebar mode)
    expand_btn = Button(
        UkIcon("maximize-2", height=14, width=14),
        type="button",
        cls="absolute top-2 right-2 w-7 h-7 flex items-center justify-center"
        " rounded-md bg-background/80 border border-border hover:bg-accent"
        " transition-colors cursor-pointer z-10",
        aria_label="Expand graph view",
        **{"@click": "expandGraph()", "x-show": "!expanded"},
    )

    # Close button (visible in expanded mode)
    close_btn = Button(
        UkIcon("x", height=18, width=18),
        type="button",
        cls="absolute top-3 right-3 w-8 h-8 flex items-center justify-center"
        " rounded-md bg-background border border-border hover:bg-accent"
        " transition-colors cursor-pointer z-10",
        aria_label="Close expanded graph",
        **{"@click": "collapseGraph()", "x-show": "expanded"},
    )

    # Backdrop (only visible when expanded)
    backdrop = Div(
        cls="fixed inset-0 bg-background/70 backdrop-blur-sm z-40",
        x_show="expanded",
        x_cloak=True,
        **{"@click": "collapseGraph()", "x-transition.opacity": ""},
    )

    # The graph wrapper — toggles between sidebar size and fullscreen overlay
    graph_wrapper = Div(
        graph_container,
        expand_btn,
        close_btn,
        loading_overlay,
        error_display,
        cls="relative border border-border rounded-lg bg-muted/30 overflow-hidden transition-all duration-300",
        **{
            ":class": "expanded"
            " ? 'fixed inset-4 z-50 shadow-2xl bg-background'"
            " : 'w-full h-[260px]'",
        },
    )

    return Div(
        backdrop,
        graph_wrapper,
        _filter_tabs(),
        x_data=f"exploreGraph({alpine_args})",
        x_init="init()",
        cls="px-2 pt-2",
    )


__all__ = ["ExploreGraphView"]
