"""
Graph Relationship Models
=========================

Simple dataclasses for representing relationships and paths in the Neo4j graph.
These are used by the Neo4j backend for graph traversal operations.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Relationship:
    """
    Represents a relationship/edge in the graph.

    Used by Neo4j backend for relationship operations.
    """

    from_uid: str
    to_uid: str
    relationship_type: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"({self.from_uid})-[:{self.relationship_type}]->({self.to_uid})"


@dataclass(frozen=True)
class GraphPath:
    """
    Represents a path through the graph.

    Contains nodes and relationships that form a connected path.
    """

    nodes: list[dict[str, Any]]  # List of node properties
    relationships: list[Relationship]

    @property
    def length(self) -> int:
        """Get the number of relationships in the path"""
        return len(self.relationships)

    @property
    def node_uids(self) -> list[str]:
        """Extract UIDs from nodes"""
        return [node.get("uid", "") for node in self.nodes if "uid" in node]

    def __repr__(self) -> str:
        if not self.relationships:
            return "GraphPath(empty)"
        return f"GraphPath(length={self.length}, start={self.relationships[0].from_uid})"
