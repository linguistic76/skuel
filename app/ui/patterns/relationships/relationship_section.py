"""EntityRelationshipsSection Component - Unified Relationships Section.

Provides a complete relationships section for entity detail pages across all 9 domains.
Combines blocking chain, alternatives grid, and relationship graph in a collapsible layout.

Features:
- Collapsible sections per relationship type (Alpine.js Accordion)
- HTMX lazy loading (staggered for performance)
- Responsive grid (1 col mobile, 2 col desktop)
- Empty states handled by child components

Usage:
    from ui.patterns.relationships import EntityRelationshipsSection

    # Add to any domain detail page
    EntityRelationshipsSection(
        entity_uid=task.uid,
        entity_type="tasks"
    )
"""

from fasthtml.common import Div

from core.models.type_hints import EntityUID
from ui.components import Accordion, AccordionItem
from ui.patterns.relationships.add_modal import PICKER_TYPES, AddRelationshipModal
from ui.patterns.relationships.alternatives_grid import AlternativesComparisonGrid
from ui.patterns.relationships.blocking_chain import BlockingChainView
from ui.patterns.relationships.manage_list import LateralManageContainer
from ui.patterns.relationships.relationship_graph import RelationshipGraphView
from ui.patterns.section_header import SectionHeader


def EntityRelationshipsSection(
    entity_uid: EntityUID,
    entity_type: str,
    show_blocking_chain: bool = True,
    show_alternatives: bool = True,
    show_graph: bool = True,
    authoring: bool = False,
) -> Div:
    """Unified relationships section for entity detail pages.

    Args:
        entity_uid: Entity UID
        entity_type: Entity type (tasks, goals, habits, etc.)
        show_blocking_chain: Show blocking dependencies section
        show_alternatives: Show alternative approaches section
        show_graph: Show relationship network graph
        authoring: Prepend a "Manage Relationships" panel with an add-relationship
            modal and a flat, deletable edge list. Only takes effect for entity
            types the EntityPicker supports (task/goal/habit) — ignored otherwise.

    Returns:
        Div containing complete relationships section with all components

    Example:
        # Add to task detail page (read-only)
        EntityRelationshipsSection(
            entity_uid=task.uid,
            entity_type="tasks"
        )

        # With authoring (add/delete) enabled
        EntityRelationshipsSection(
            entity_uid=task.uid,
            entity_type="tasks",
            authoring=True,
        )

        # Add to goal detail page (hide alternatives if not applicable)
        EntityRelationshipsSection(
            entity_uid=goal.uid,
            entity_type="goals",
            show_alternatives=False
        )
    """
    items = []

    if authoring and entity_type in PICKER_TYPES:
        items.append(
            AccordionItem(
                "Manage Relationships",
                Div(
                    AddRelationshipModal(entity_uid, entity_type),
                    LateralManageContainer(entity_uid, entity_type),
                    cls="space-y-4",
                ),
                open=True,
                title_cls="text-lg font-semibold flex justify-between items-center w-full",
            )
        )

    if show_blocking_chain:
        items.append(
            AccordionItem(
                "Blocking Dependencies",
                BlockingChainView(entity_uid, entity_type),
                title_cls="text-lg font-semibold flex justify-between items-center w-full",
            )
        )

    if show_alternatives:
        items.append(
            AccordionItem(
                "Alternative Approaches",
                AlternativesComparisonGrid(entity_uid, entity_type),
                title_cls="text-lg font-semibold flex justify-between items-center w-full",
            )
        )

    if show_graph:
        items.append(
            AccordionItem(
                "Relationship Network",
                RelationshipGraphView(entity_uid, entity_type),
                open=True,
                title_cls="text-lg font-semibold flex justify-between items-center w-full",
            )
        )

    return Div(
        SectionHeader("Relationships"),
        Accordion(*items, multiple=True, cls="space-y-6"),
        cls="mt-8 border-t border-border pt-8",
    )


__all__ = ["EntityRelationshipsSection"]
