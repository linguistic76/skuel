"""
Relationship Filter Intent - Graph-Aware Search Transport
=========================================================

THE transport object carrying the *intent* of a graph-aware faceted search
across the hexagonal boundary (ADR-044).

Core Principle: "Pass intent down, author Cypher below the boundary"

``SearchRequest`` exposes a set of boolean relationship-filter flags (ready to
learn, builds on mastered, supports goals, ...). The Cypher WHERE-clause
fragments that *realize* each flag are graph queries and therefore must NOT be
authored in ``core/`` (SKUEL021). Instead, ``SearchRequest.to_relationship_filters()``
captures just the active-flag set into this frozen dataclass, the backend port
receives it, and the flag→Cypher mapping lives below the boundary in
``adapters/persistence/neo4j/query/cypher/relationship_filter_fragments.py``.

This is the "inverted boundary" fix: a core model must not build a Cypher
string and hand it to a passthrough adapter — it hands down the domain intent
and lets the adapter author the query.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

__all__ = ["RelationshipFilters"]


@dataclass(frozen=True)
class RelationshipFilters:
    """Active relationship-filter flags for a graph-aware faceted search.

    Pure data — no Cypher, no persistence concern. Each field mirrors the
    matching boolean on ``SearchRequest``; the field *order* defines the
    deterministic order in which the below-boundary builder emits fragments.

    All flags default to ``False`` so a request with no relationship filters
    yields an "empty" instance (``bool(filters) is False``).
    """

    # Graph-aware relationship filters
    ready_to_learn: bool = False
    builds_on_mastered: bool = False
    in_active_path: bool = False
    supports_goals: bool = False
    builds_on_habits: bool = False
    applied_in_tasks: bool = False
    aligned_with_principles: bool = False
    next_logical_step: bool = False

    # Pedagogical filters (learning-progress tracking)
    not_yet_viewed: bool = False
    viewed_not_mastered: bool = False
    ready_to_review: bool = False

    def has_any(self) -> bool:
        """True if at least one relationship filter is active."""
        return any(getattr(self, f.name) for f in fields(self))

    def __bool__(self) -> bool:
        """An instance is truthy iff any filter is active."""
        return self.has_any()
