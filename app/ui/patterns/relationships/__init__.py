"""Lateral Relationship UI Components

Provides interactive components for visualizing and navigating lateral relationships
across all 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP).

Components:
- BlockingChainView - Vertical flow chart showing transitive blocking chain
- AlternativesComparisonGrid - Side-by-side comparison table
- RelationshipGraphView - Interactive force-directed graph (Vis.js)
- EntityRelationshipsSection - Unified section for entity detail pages

Usage:
    from ui.patterns.relationships import EntityRelationshipsSection

    # Add to any domain detail page
    EntityRelationshipsSection(
        entity_uid=task.uid,
        entity_type="tasks"
    )
"""

from ui.patterns.relationships.alternatives_grid import AlternativesComparisonGrid
from ui.patterns.relationships.blocking_chain import BlockingChainView
from ui.patterns.relationships.relationship_graph import RelationshipGraphView
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection

__all__ = [
    "BlockingChainView",
    "AlternativesComparisonGrid",
    "RelationshipGraphView",
    "EntityRelationshipsSection",
]
