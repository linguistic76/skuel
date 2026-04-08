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

from fasthtml.common import Button, Div, NotStr, Span
from monsterui.franken import UkIcon

if TYPE_CHECKING:
    from fasthtml.common import FT


# Static SVG skeleton rendered inside explore-graph-container before Vis.js initialises.
# Five shimmer circles (hub + 4 satellites) with connecting lines — mirrors the shape
# of a force-directed graph so the Vis.js network paints into an already-shaped space.
# JS removes this element by id just before new vis.Network() is called.
_GRAPH_SKELETON = NotStr(
    '<svg id="explore-graph-skeleton" width="100%" height="100%"'
    ' viewBox="0 0 400 260" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    # Lines (drawn below nodes)
    '<g class="text-muted-foreground/20" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round">'
    "<line x1='200' y1='130' x2='100' y2='75'/>"
    "<line x1='200' y1='130' x2='305' y2='68'/>"
    "<line x1='200' y1='130' x2='88' y2='188'/>"
    "<line x1='200' y1='130' x2='312' y2='185'/>"
    "<line x1='100' y1='75' x2='305' y2='68'/>"
    "</g>"
    # Nodes
    '<g class="text-muted-foreground/30 animate-pulse" fill="currentColor">'
    "<circle cx='200' cy='130' r='12'/>"
    "<circle cx='100' cy='75' r='8'/>"
    "<circle cx='305' cy='68' r='8'/>"
    "<circle cx='88' cy='188' r='8'/>"
    "<circle cx='312' cy='185' r='8'/>"
    "</g>"
    "</svg>"
)

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
    standalone: bool = True,
) -> "FT":
    """Interactive Vis.js graph for the Explore sidebar.

    Args:
        mode: 'hub' for learning universe, 'entity' for entity-centered.
        entity_uid: UID of the current entity (entity mode only).
        entity_type: 'ku' or 'ps' (entity mode only).
        standalone: If True, emits x-data/x-init on outer Div. If False,
            expects a parent element to provide the Alpine scope.
    """
    alpine_args = f"'{mode}', '{entity_uid}', '{entity_type}'"

    # Single graph container — SVG skeleton is rendered here; JS removes it before
    # vis.Network paints (see renderNetwork() in skuel.js). CSS repositions when expanded.
    graph_container = Div(
        _GRAPH_SKELETON,
        id="explore-graph-container",
        cls="w-full h-full",
    )

    # Loading overlay — spinner only; SVG skeleton in the container is the visual cue
    loading_overlay = Div(
        Div(
            Span(cls="sr-only", aria_live="polite"),
            Span(
                cls="animate-spin inline-block w-5 h-5 border-2"
                " border-primary border-t-transparent rounded-full"
            ),
            cls="flex items-center",
        ),
        cls="absolute inset-0 flex items-center justify-center",
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

    # Empty state — shown when graph has no nodes
    empty_state = Div(
        UkIcon("share-2", height=32, width=32),
        Span(
            "Start exploring to see your graph",
            cls="text-xs text-muted-foreground mt-2",
        ),
        cls="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/40",
        x_show="!loading && !error && isEmpty",
        x_cloak=True,
    )

    # Sidebar graph wrapper — fixed height; expand creates a separate overlay on body
    graph_wrapper = Div(
        graph_container,
        expand_btn,
        loading_overlay,
        error_display,
        empty_state,
        cls="relative border border-border rounded-lg bg-muted/30 overflow-hidden w-full",
        style="height: 260px",
    )

    wrapper_attrs: dict[str, str] = {"cls": "px-2 pt-2"}
    if standalone:
        wrapper_attrs["x_data"] = f"exploreGraph({alpine_args})"
        wrapper_attrs["x_init"] = "init()"

    return Div(
        graph_wrapper,
        _filter_tabs(),
        **wrapper_attrs,
    )


__all__ = ["ExploreGraphView"]
