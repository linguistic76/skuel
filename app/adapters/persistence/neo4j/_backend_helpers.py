"""
Backend Helpers
===============

Shared validation and conversion helpers for domain backend mixins and classes.

Provides:
- ``_ALLOWED_ORDER_BY`` — whitelist for ORDER BY field names (prevents Cypher injection)
- ``_validate_rel_name()`` — rejects relationship names with non-``[A-Z0-9_]`` characters
- ``to_native_datetime()`` — Neo4j temporal → native datetime conversion
- ``direction_clause()`` — THE single builder for direction arrow segments

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from neo4j.time import DateTime as Neo4jDateTime

# Allowed property names for ORDER BY clauses (prevents Cypher injection)
_ALLOWED_ORDER_BY = frozenset(
    {
        "uid",
        "created_at",
        "updated_at",
        "title",
        "status",
        "priority",
        "start_time",
        "due_date",
        "completed_at",
        "name",
        "target_date",
        "strength",
    }
)


def _validate_rel_name(rel_name: str) -> None:
    """Validate a relationship name contains only safe characters (A-Z, 0-9, _)."""
    if not rel_name or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in rel_name):
        msg = f"Invalid relationship name: {rel_name!r}"
        raise ValueError(msg)


def direction_clause(
    direction: str,
    rel_var: str | None = "r",
    rel_type: str | None = None,
) -> str:
    """
    Build the arrow segment of a Cypher relationship pattern.

    THE single home for the ``"-[r]->" if direction == "outgoing" else ...``
    ternary that was copy-pasted across the persistence layer. Node parts stay
    at the call site::

        f"(n){direction_clause(direction)}(related)"  # (n)-[r]->(related)
        f"(a){direction_clause('incoming', None, 'OWNS')}(b)"  # (a)<-[:OWNS]-(b)

    Args:
        direction: "outgoing", "incoming", or "both"
        rel_var: Relationship variable name, or None for an anonymous edge
        rel_type: Optional relationship type (caller-validated — this helper
                  interpolates it verbatim, so pass only RelationshipName
                  values or identifier-validated strings)

    Returns:
        Arrow segment like ``-[r:TYPE]->``, ``<-[r]-``, or ``-[:TYPE]-``.

    Raises:
        ValueError: On an unknown direction (fail-fast, matching the
        query-builder modules' historical behavior).
    """
    rel_part = f"[{rel_var or ''}{f':{rel_type}' if rel_type else ''}]"
    match direction:
        case "outgoing":
            return f"-{rel_part}->"
        case "incoming":
            return f"<-{rel_part}-"
        case "both":
            return f"-{rel_part}-"
        case _:
            raise ValueError(
                f"Invalid direction: {direction}. Valid options: outgoing, incoming, both"
            )


def to_native_datetime(value: object) -> datetime | None:
    """Convert a Neo4j temporal value to a native datetime (None passes through)."""
    if isinstance(value, Neo4jDateTime):
        return cast("datetime", value.to_native())
    if isinstance(value, datetime):
        return value
    return None
