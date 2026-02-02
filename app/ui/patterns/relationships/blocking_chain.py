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

from fasthtml.common import H3, A, Div, Span

from ui.primitives.card import Card


def BlockingChainView(entity_uid: str, entity_type: str) -> Div:
    """Vertical flow chart showing transitive blocking chain.

    Args:
        entity_uid: Entity UID to get blockers for
        entity_type: Entity type (tasks, goals, etc.)

    Returns:
        Div containing HTMX-loadable blocking chain view
    """
    return Card(
        # Header
        Div(
            H3("Blocking Chain", cls="text-lg font-bold"),
            Span(
                **{"x-text": "`${chain_depth} levels deep`"},
                cls="text-sm text-base-content/70",
            ),
            cls="flex items-center justify-between mb-4",
        ),
        # Chain container (HTMX loads)
        Div(
            Div("Loading blocking chain...", cls="skeleton h-32"),
            id=f"chain-{entity_uid}",
            **{
                "hx-get": f"/api/{entity_type}/{entity_uid}/lateral/chain",
                "hx-trigger": "load",
                "hx-swap": "innerHTML",
            },
        ),
        **{"x-data": "{ chain_depth: 0 }"},
        cls="bg-base-100 shadow-sm p-4",
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
            cls="text-base-content/70 text-sm",
        )

    levels_html = []
    for level in chain_data["levels"]:
        depth_label = Div(
            f"Depth {level['depth']}",
            cls="text-xs font-semibold text-base-content/60 mb-2",
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
                status_color = "text-base-content/60"
                status_icon = "•"

            entity_card = Div(
                A(
                    Div(
                        Span(status_icon, cls=f"{status_color} text-lg mr-2"),
                        Span(entity["title"], cls="font-medium"),
                        cls="flex items-center",
                    ),
                    Div(
                        f"Blocks {entity['blocks_count']} entities",
                        cls="text-xs text-base-content/60 ml-6",
                    ),
                    href=f"/{entity['entity_type']}/{entity['uid']}",
                    cls="hover:bg-base-200 p-2 rounded transition-colors block",
                ),
                cls="mb-2",
            )
            entity_cards.append(entity_card)

        levels_html.append(Div(depth_label, *entity_cards, cls="mb-4"))

    return Div(
        *levels_html,
        **{"x-init": f"chain_depth = {chain_data['chain_depth']}"},
    )


__all__ = ["BlockingChainView", "render_chain_fragment"]
