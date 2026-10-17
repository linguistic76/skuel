r"""RelationshipGraphView Component - Interactive Force-Directed Graph.

Displays lateral relationships using Vis.js Network library with interactive features.
Supports drag, zoom, pan, and click-to-navigate.

Features:
- Vis.js Network force-directed layout
- Drag nodes
- Zoom/pan
- Click node to navigate
- Depth control (1-3 levels)
- Relationship type filtering
- Color-coded by relationship type

Layout:
┌─────────────────────────┐
│ Relationship Graph  [▼2]│
├─────────────────────────┤
│     ○────○              │
│    /      \             │
│   ○        ○ (YOU)      │
│    \      /             │
│     ○────○              │
└─────────────────────────┘

Color Scheme:
- BLOCKS → Red (#EF4444)
- PREREQUISITE_FOR → Orange (#F59E0B)
- ALTERNATIVE_TO → Blue (#3B82F6)
- COMPLEMENTARY_TO → Green (#10B981)
- RELATED_TO → Gray (#6B7280)
- SIBLING → Purple (#8B5CF6)
"""

from fasthtml.common import H3, Div, Option, P

from core.constants import GraphDepth
from core.models.type_hints import EntityUID
from ui.components import Card, CardBody
from ui.forms import Select


def RelationshipGraphView(
    entity_uid: EntityUID,
    entity_type: str,
    depth: int = 2,
) -> Div:
    """Interactive force-directed graph using Vis.js Network.

    Args:
        entity_uid: Center entity UID
        entity_type: Entity type (tasks, goals, etc.)
        depth: Initial graph depth (1-3, the route's cap)

    Returns:
        Div containing interactive Vis.js graph
    """
    depth_options = [
        Option(f"Depth {level}", value=str(level), selected=(level == depth))
        for level in range(GraphDepth.DIRECT, GraphDepth.DEFAULT + 1)
    ]
    return Card(
        CardBody(
            # Header with depth control
            Div(
                H3("Relationship Graph", cls="text-lg font-bold"),
                Select(
                    *depth_options,
                    name="graph_depth",
                    full_width=False,
                    aria_label="Graph depth",
                    **{"x-on:change": "changeDepth($event.target.value)"},
                ),
                cls="flex items-center justify-between mb-4",
            ),
            # Canvas container
            Div(
                id=f"network-{entity_uid}",
                cls="w-full h-96 border border-border rounded-sm",
            ),
            P(
                cls="text-sm text-destructive mt-2",
                role="alert",
                x_show="error",
                x_text="error",
                x_cloak=True,
            ),
            # Legend
            Div(
                Div(
                    Div(cls="w-3 h-3 rounded-full bg-error inline-block"),
                    " Blocks",
                    cls="text-sm mr-4",
                ),
                Div(
                    Div(cls="w-3 h-3 rounded-full bg-warning inline-block"),
                    " Prerequisites",
                    cls="text-sm mr-4",
                ),
                Div(
                    Div(cls="w-3 h-3 rounded-full bg-info inline-block"),
                    " Alternatives",
                    cls="text-sm mr-4",
                ),
                Div(
                    Div(cls="w-3 h-3 rounded-full bg-success inline-block"),
                    " Complementary",
                    cls="text-sm",
                ),
                cls="flex flex-wrap items-center gap-y-1 mt-4 pt-4 border-t border-border",
            ),
            # One scope holds the select, the canvas and the error, so Alpine
            # binds every directive above; Alpine calls the component's init().
            **{
                "x-data": f"relationshipGraph('{entity_uid}', '{entity_type}', {depth})",
                # Reload the network whenever an add/delete fires relationships-changed.
                "x-on:relationships-changed.window": "loadGraph(depth)",
            },
        ),
    )


__all__ = ["RelationshipGraphView"]
