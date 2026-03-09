"""
Query Analysis Models
=====================

Models for query parsing and analysis.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryElements:
    """
    Elements extracted from a parsed query.

    Used by CypherParser for query analysis.
    """

    nodes: list[dict[str, Any]] = (field(default_factory=list),)
    relationships: list[dict[str, Any]] = (field(default_factory=list),)
    properties: dict[str, Any] = (field(default_factory=dict),)
    conditions: list[str] = (field(default_factory=list),)
    return_items: list[str] = (field(default_factory=list),)
    order_by: str | None = (None,)
    limit: int | None = (None,)
    skip: int | None = None
