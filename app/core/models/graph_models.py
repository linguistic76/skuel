"""
Graph Models - Core Graph Structure Representations
===================================================

This module provides fundamental dataclasses for representing graph structures.

Extracted from base_service.py to promote reusability across:
- Services (relationship management)
- Backends (graph operations)
- Intelligence services (path analysis)
- Query utilities (traversal patterns)

Core Models:
- Relationship: Edge between two nodes
- GraphPath: Sequence of nodes and relationships forming a path

Philosophy:
- Immutable (frozen=True) for safety
- Simple, focused data structures
- No business logic (pure data models)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Relationship:
    """
    Represents a relationship (edge) between two entities in the graph.

    This is a fundamental building block of SKUEL's graph architecture.
    Every connection between entities is represented as a Relationship.

    Attributes:
        from_uid: UID of the source entity
        rel_type: Type of relationship (e.g., "REQUIRES", "ENABLES", "APPLIES_KNOWLEDGE")
        to_uid: UID of the target entity
        properties: Optional metadata about the relationship (e.g., confidence, weight)

    Examples:
        # Knowledge prerequisite relationship
        Relationship(
            from_uid="ku.advanced_python",
            rel_type="REQUIRES",
            to_uid="ku.basic_python",
            properties={"confidence": 0.95}
        )

        # Task applies knowledge relationship
        Relationship(
            from_uid="task.deploy_app",
            rel_type="APPLIES_KNOWLEDGE",
            to_uid="ku.docker",
            properties={"confidence": 0.8, "required": True}
        )

        # Habit contributes to goal relationship
        Relationship(
            from_uid="habit.daily_exercise",
            rel_type="CONTRIBUTES_TO",
            to_uid="goal.fitness",
            properties={"weight": 0.7}
        )
    """

    from_uid: str
    rel_type: str
    to_uid: str
    properties: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphPath:
    """
    Represents a path through the graph.

    A path is a sequence of nodes connected by relationships, useful for:
    - Prerequisite chains (knowledge dependencies)
    - Task dependency analysis
    - Learning path traversal
    - Goal hierarchy exploration

    Attributes:
        nodes: List of node UIDs forming the path (ordered)
        relationships: List of relationships connecting the nodes
        total_cost: Cumulative cost/weight for weighted traversals (default 0.0)

    Examples:
        # Knowledge prerequisite chain
        GraphPath(
            nodes=["ku.basic_python", "ku.functions", "ku.advanced_python"],
            relationships=[
                Relationship("ku.basic_python", "ENABLES", "ku.functions"),
                Relationship("ku.functions", "ENABLES", "ku.advanced_python")
            ],
            total_cost=0.0
        )

        # Task dependency path (with weights)
        GraphPath(
            nodes=["task.setup_env", "task.write_code", "task.deploy"],
            relationships=[
                Relationship("task.setup_env", "BLOCKS", "task.write_code", {"duration": 2}),
                Relationship("task.write_code", "BLOCKS", "task.deploy", {"duration": 5})
            ],
            total_cost=7.0  # Sum of durations
        )

    Note:
        - nodes[i] and nodes[i+1] are connected by relationships[i]
        - len(relationships) should be len(nodes) - 1
        - Empty paths are valid (nodes=[], relationships=[], total_cost=0.0)
    """

    nodes: list[str]  # UIDs of nodes in path
    relationships: list[Relationship]
    total_cost: float = 0.0  # For weighted traversals
