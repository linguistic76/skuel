"""EntityRelationshipsSection Component - Unified Relationships Section.

Provides a complete relationships section for entity detail pages across all 9 domains.
Combines blocking chain, alternatives grid, and relationship graph in a collapsible layout.

Features:
- Collapsible sections per relationship type
- HTMX lazy loading (staggered for performance)
- Responsive grid (1 col mobile, 2 col desktop)
- Empty states handled by child components
- Alpine.js collapsible state management

Usage:
    from ui.patterns.relationships import EntityRelationshipsSection

    # Add to any domain detail page
    EntityRelationshipsSection(
        entity_uid=task.uid,
        entity_type="tasks"
    )
"""

from fasthtml.common import Div, H2, H3

from ui.patterns.relationships.alternatives_grid import AlternativesComparisonGrid
from ui.patterns.relationships.blocking_chain import BlockingChainView
from ui.patterns.relationships.relationship_graph import RelationshipGraphView


def EntityRelationshipsSection(
    entity_uid: str,
    entity_type: str,
    show_blocking_chain: bool = True,
    show_alternatives: bool = True,
    show_graph: bool = True,
) -> Div:
    """Unified relationships section for entity detail pages.

    Args:
        entity_uid: Entity UID
        entity_type: Entity type (tasks, goals, habits, etc.)
        show_blocking_chain: Show blocking dependencies section
        show_alternatives: Show alternative approaches section
        show_graph: Show relationship network graph

    Returns:
        Div containing complete relationships section with all components

    Example:
        # Add to task detail page
        EntityRelationshipsSection(
            entity_uid=task.uid,
            entity_type="tasks"
        )

        # Add to goal detail page (hide alternatives if not applicable)
        EntityRelationshipsSection(
            entity_uid=goal.uid,
            entity_type="goals",
            show_alternatives=False
        )
    """
    sections = []

    # Blocking chain (loads immediately)
    if show_blocking_chain:
        sections.append(
            Div(
                **{"x-data": "{ expanded: false }"},
            )(
                # Header (clickable)
                Div(
                    H3("Blocking Dependencies", cls="text-lg font-semibold"),
                    Div(
                        **{
                            "x-text": "expanded ? '▼' : '▶'",
                            "x-on:click": "expanded = !expanded",
                            "class": "cursor-pointer text-2xl select-none hover:text-primary transition-colors",
                        },
                    ),
                    cls="flex items-center justify-between mb-2",
                ),
                # Content (collapsible)
                Div(
                    **{
                        "x-show": "expanded",
                        "x-collapse": True,
                    },
                )(BlockingChainView(entity_uid, entity_type)),
            )
        )

    # Alternatives (loads after 300ms)
    if show_alternatives:
        sections.append(
            Div(
                **{"x-data": "{ expanded: false }"},
            )(
                Div(
                    H3("Alternative Approaches", cls="text-lg font-semibold"),
                    Div(
                        **{
                            "x-text": "expanded ? '▼' : '▶'",
                            "x-on:click": "expanded = !expanded",
                            "class": "cursor-pointer text-2xl select-none hover:text-primary transition-colors",
                        },
                    ),
                    cls="flex items-center justify-between mb-2",
                ),
                Div(
                    **{
                        "x-show": "expanded",
                        "x-collapse": True,
                    },
                )(AlternativesComparisonGrid(entity_uid, entity_type)),
            )
        )

    # Relationship graph (loads after 600ms, expanded by default)
    if show_graph:
        sections.append(
            Div(
                **{"x-data": "{ expanded: true }"},  # Expanded by default
            )(
                Div(
                    H3("Relationship Network", cls="text-lg font-semibold"),
                    Div(
                        **{
                            "x-text": "expanded ? '▼' : '▶'",
                            "x-on:click": "expanded = !expanded",
                            "class": "cursor-pointer text-2xl select-none hover:text-primary transition-colors",
                        },
                    ),
                    cls="flex items-center justify-between mb-2",
                ),
                Div(
                    **{
                        "x-show": "expanded",
                        "x-collapse": True,
                    },
                )(RelationshipGraphView(entity_uid, entity_type)),
            )
        )

    # Return complete section
    return Div(
        H2("Relationships", cls="text-2xl font-bold mb-6"),
        Div(
            *sections,
            cls="space-y-6",  # Vertical stacking with spacing
        ),
        cls="mt-8 border-t border-base-200 pt-8",
    )


__all__ = ["EntityRelationshipsSection"]
