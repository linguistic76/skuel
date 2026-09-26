"""The derived review standing of a UserEntry, read off a backend row (ADR-088 §1, R2).

One converter for every statement that composes the review-standing subquery
(``build_review_standing_subquery``): the Shared-page list reads, the
recipient card's one-entry read. The columns are ``reviewed_by`` (a
``ReportSource`` value or NULL) and ``revised_after_feedback``.
"""

from __future__ import annotations

from core.models.type_hints import Neo4jProperties
from core.ports.query_types import ReviewStanding
from core.utils.neo4j_props import neo4j_opt_str


def review_standing_from_row(record: Neo4jProperties) -> ReviewStanding:
    """The two derived columns as a ``ReviewStanding`` (absent columns read as unreviewed)."""
    return {
        "reviewed_by": neo4j_opt_str(record, "reviewed_by"),
        "revised_after_feedback": bool(record.get("revised_after_feedback")),
    }


__all__ = ["review_standing_from_row"]
