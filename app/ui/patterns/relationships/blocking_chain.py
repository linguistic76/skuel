"""BlockingChainView Component - Vertical Flow Chart.

Displays transitive blocking chain with depth-based indentation and status color coding.
Uses HTMX lazy loading for performance.

Features:
- Depth-based layout
- Color coding by status (completed=green, in_progress=blue, pending=gray)
- Critical path highlighting
- Clickable entity cards
- HTMX lazy loading

Layout:
┌─────────────────────────┐
│ Blocking Chain  (3 deep)│
├─────────────────────────┤
│ [Depth 0]               │
│   ✓ Setup Environment   │
│ [Depth 1]               │
│   ○ Install Dependencies│
│ [Depth 2]               │
│   • Deploy App (YOU)    │
└─────────────────────────┘
"""

from typing import Any

from fasthtml.common import H3, Div, Span

from core.models.type_hints import EntityUID
from ui.components import Card, CardBody
from ui.patterns.skeleton import SkeletonLines


def BlockingChainView(entity_uid: EntityUID, entity_type: str) -> Div:
    """Vertical flow chart showing transitive blocking chain.

    Args:
        entity_uid: Entity UID to get blockers for
        entity_type: Entity type (tasks, goals, etc.)

    Returns:
        Div containing HTMX-loadable blocking chain view
    """
    return Card(
        CardBody(
            # Header
            Div(
                H3("Blocking Chain", cls="text-lg font-bold"),
                Span(
                    **{"x-text": "`${chain_depth} levels deep`"},
                    cls="text-sm text-muted-foreground",
                ),
                cls="flex items-center justify-between mb-4",
            ),
            # Chain container (HTMX loads)
            Div(
                SkeletonLines(count=3),
                id=f"chain-{entity_uid}",
                hx_get=f"/api/{entity_type}/{entity_uid}/lateral/chain",
                hx_trigger="load, relationships-changed from:body",
                hx_swap="innerHTML",
            ),
        ),
        **{"x-data": "{ chain_depth: 0 }"},
    )


def render_chain_fragment(chain_data: dict[str, Any]) -> Div:
    """Render loaded chain data as HTML fragment (called by HTMX endpoint).

    Args:
        chain_data: Chain data from get_blocking_chain service method

    Returns:
        Div containing rendered chain levels
    """
    if chain_data["total_blockers"] == 0:
        return Div(
            "No blockers found. This entity is ready to work on!",
            cls="text-muted-foreground text-sm",
        )

    levels_html = []
    for level in chain_data["levels"]:
        depth_label = Div(
            f"Depth {level['depth']}",
            cls="text-xs font-semibold text-muted-foreground mb-2",
        )

        entity_cards = []
        for entity in level["entities"]:
            # Status color coding
            status = entity.get("status", "unknown")
            if status == "completed":
                status_color = "text-success"
                status_icon = "✓"
            elif status in {"in_progress", "active"}:
                status_color = "text-info"
                status_icon = "○"
            else:
                status_color = "text-muted-foreground"
                status_icon = "•"

            # Plain text, not a link: the backend supplies a Neo4j label
            # (labels(blocker)[0], e.g. "Entity"/"Task") as entity_type, which does
            # not map to a real detail route (`/{domain}/detail?uid=...`). The graph
            # view provides reliable click-to-navigate.
            entity_card = Div(
                Div(
                    Span(status_icon, cls=f"{status_color} text-lg mr-2"),
                    Span(entity["title"], cls="font-medium"),
                    cls="flex items-center",
                ),
                Div(
                    f"Blocks {entity['blocks_count']} entities",
                    cls="text-xs text-muted-foreground ml-6",
                ),
                cls="mb-2 p-2 rounded",
            )
            entity_cards.append(entity_card)

        levels_html.append(Div(depth_label, *entity_cards, cls="mb-4"))

    return Div(
        *levels_html,
        **{"x-init": f"chain_depth = {chain_data['chain_depth']}"},
    )


__all__ = ["BlockingChainView", "render_chain_fragment"]
