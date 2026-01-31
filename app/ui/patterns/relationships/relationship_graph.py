"""RelationshipGraphView Component - Interactive Force-Directed Graph.

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
"""

from fasthtml.common import Div, H3, Option, Select

from ui.primitives.card import Card


def RelationshipGraphView(
    entity_uid: str,
    entity_type: str,
    depth: int = 2,
) -> Div:
    """Interactive force-directed graph using Vis.js Network.

    Args:
        entity_uid: Center entity UID
        entity_type: Entity type (tasks, goals, etc.)
        depth: Initial graph depth (1-3 recommended)

    Returns:
        Div containing interactive Vis.js graph
    """
    return Card(
        # Header with depth control
        Div(
            H3("Relationship Graph", cls="text-lg font-bold"),
            Select(
                Option("Depth 1", value="1"),
                Option("Depth 2", value="2", selected=(depth == 2)),
                Option("Depth 3", value="3"),
                name="graph_depth",
                cls="select select-sm select-bordered",
                **{"x-on:change": "changeDepth($event.target.value)"},
            ),
            cls="flex items-center justify-between mb-4",
        ),
        # Canvas container
        Div(
            Div(
                id=f"network-{entity_uid}",
                cls="w-full h-96 border border-base-300 rounded",
            ),
            **{
                "x-data": f"relationshipGraph('{entity_uid}', '{entity_type}', {depth})",
                "x-init": "init()",
            },
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
            cls="flex items-center mt-4 pt-4 border-t border-base-200",
        ),
        cls="bg-base-100 shadow-sm p-4",
    )


__all__ = ["RelationshipGraphView"]
