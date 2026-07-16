"""
Backend Helpers
===============

Shared validation and conversion helpers for domain backend mixins and classes.

Provides:
- ``_ALLOWED_ORDER_BY`` — whitelist for ORDER BY field names (prevents Cypher injection)
- ``_validate_rel_name()`` — rejects relationship names with non-``[A-Z0-9_]`` characters
- ``to_native_datetime()`` — Neo4j temporal → native datetime conversion

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


def to_native_datetime(value: object) -> datetime | None:
    """Convert a Neo4j temporal value to a native datetime (None passes through)."""
    if isinstance(value, Neo4jDateTime):
        return cast("datetime", value.to_native())
    if isinstance(value, datetime):
        return value
    return None
