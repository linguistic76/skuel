"""
Semantic Pattern Matching and Discovery
========================================

Utilities for pattern matching, graph traversal, and pattern discovery
in semantic knowledge graphs.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from core.infrastructure.relationships.semantic_relationships import (
    SemanticRelationship,
    SemanticRelationshipType,
)


@dataclass
class TriplePattern:
    """Pattern for matching semantic triples."""

    subject: str | None = None  # None means "any"
    predicate: SemanticRelationshipType | None = None
    object: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)

    def matches(self, triple: tuple[str, str, str]) -> bool:
        """Check if a triple matches this pattern."""
        subj, pred, obj = triple

        if self.subject and self.subject != subj:
            return False
        if self.predicate and self.predicate.value != pred:
            return False
        if self.object and self.object != obj:
            return False

        # Check additional constraints
        for _key, _value in self.constraints.items():
            # Would check metadata constraints here
            pass

        return True


class SemanticMatcher:
    """Matches semantic patterns in knowledge graphs."""

    @staticmethod
    def find_patterns(
        triples: list[tuple[str, str, str]], pattern: TriplePattern
    ) -> list[tuple[str, str, str]]:
        """Find all triples matching a pattern."""
        return [triple for triple in triples if pattern.matches(triple)]

    @staticmethod
    def find_path(
        triples: list[tuple[str, str, str]], start: str, end: str, max_depth: int = 5
    ) -> list[tuple[str, str, str]] | None:
        """Find a path between two nodes."""
        # Build adjacency list
        graph: dict[str, list[tuple[str, str]]] = {}
        for subj, pred, obj in triples:
            if subj not in graph:
                graph[subj] = []
            graph[subj].append((pred, obj))

        # BFS to find path
        queue: deque[tuple[str, list[tuple[str, str, str]]]] = deque([(start, [])])
        visited = {start}

        while queue and len(visited) < 1000:  # Prevent infinite loops
            current, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            if current == end:
                return path

            if current in graph:
                for pred, next_node in graph[current]:
                    if next_node not in visited:
                        visited.add(next_node)
                        new_path = [*path, (current, pred, next_node)]
                        queue.append((next_node, new_path))

        return None


class PatternDiscoverer:
    """Discovers patterns in semantic graphs."""

    @staticmethod
    def find_clusters(
        relationships: list[SemanticRelationship], min_cluster_size: int = 3
    ) -> list[set[str]]:
        """Find clusters of highly connected entities."""
        # Build adjacency list
        graph: dict[str, set[str]] = {}
        for rel in relationships:
            if rel.subject_uid not in graph:
                graph[rel.subject_uid] = set()
            if rel.object_uid not in graph:
                graph[rel.object_uid] = set()

            graph[rel.subject_uid].add(rel.object_uid)
            graph[rel.object_uid].add(rel.subject_uid)

        # Find clusters using simple connected components
        visited: set[str] = (set(),)
        clusters: list[set[str]] = []

        for node in graph:
            if node not in visited:
                cluster = PatternDiscoverer._dfs_cluster(node, graph, visited)
                if len(cluster) >= min_cluster_size:
                    clusters.append(cluster)

        return clusters

    @staticmethod
    def _dfs_cluster(node: str, graph: dict[str, set[str]], visited: set[str]) -> set[str]:
        """DFS to find connected component."""
        cluster = {node}
        visited.add(node)
        stack = [node]

        while stack:
            current = stack.pop()
            for neighbor in graph.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    cluster.add(neighbor)
                    stack.append(neighbor)

        return cluster

    @staticmethod
    def find_common_patterns(
        entities: list[str], relationships: list[SemanticRelationship]
    ) -> list[TriplePattern]:
        """Find common patterns among entities."""
        patterns = []

        # Count relationship types
        rel_counts = {}
        for rel in relationships:
            if rel.subject_uid in entities:
                rel_type = rel.predicate
                if rel_type not in rel_counts:
                    rel_counts[rel_type] = 0
                rel_counts[rel_type] += 1

        # Find frequent patterns
        total_entities = len(entities)
        for rel_type, count in rel_counts.items():
            # If more than 50% of entities have this relationship
            if count > total_entities * 0.5:
                pattern = TriplePattern(
                    subject=None,  # Any entity
                    predicate=rel_type,
                    object=None,  # Any target
                )
                patterns.append(pattern)

        return patterns
