"""
Neo4j Schema Context Models
==========================

Data models for representing Neo4j database schema information
including nodes, relationships, indexes, and constraints.
"""

__version__ = "1.0"


from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Neo4jIndex:
    """Represents a Neo4j index"""

    name: str
    type: str  # 'BTREE', 'FULLTEXT', etc.
    entity_type: str  # 'NODE' or 'RELATIONSHIP'
    labels: list[str]
    properties: list[str]
    state: str  # 'ONLINE', 'POPULATING', 'FAILED'


@dataclass
class Neo4jConstraint:
    """Represents a Neo4j constraint"""

    name: str
    type: str  # 'UNIQUE', 'NODE_PROPERTY_EXISTENCE', etc.
    entity_type: str  # 'NODE' or 'RELATIONSHIP'
    labels: list[str]
    properties: list[str]


@dataclass
class NodeLabelInfo:
    """Information about a specific node label"""

    label: str
    count: int
    properties: set[str]
    sample_properties: dict[str, Any]  # Sample values for property types


@dataclass
class RelationshipTypeInfo:
    """Information about a specific relationship type"""

    type: str
    count: int
    properties: set[str]
    sample_properties: dict[str, Any]


@dataclass
class SchemaContext:
    """
    Complete Neo4j schema context with all introspection data.

    This provides the foundation for schema-aware query building,
    validation, and optimization.
    """

    # Core schema elements
    node_labels: list[str]
    relationship_types: list[str]
    indexes: list[Neo4jIndex]
    constraints: list[Neo4jConstraint]

    # Detailed information
    node_label_info: dict[str, NodeLabelInfo]
    relationship_type_info: dict[str, RelationshipTypeInfo]

    # Property mappings
    property_names: set[str]  # All unique property names
    indexed_properties: dict[str, list[Neo4jIndex]]  # Property -> indexes
    unique_properties: dict[str, list[Neo4jConstraint]]  # Property -> constraints

    # Metadata
    introspection_timestamp: datetime
    schema_hash: str  # For change detection

    def has_unique_constraint_on(self, property_name: str) -> bool:
        """Check if a property has a unique constraint"""
        return property_name in self.unique_properties

    def get_indexes_for_property(self, property_name: str) -> list[Neo4jIndex]:
        """Get all indexes that include a specific property"""
        return self.indexed_properties.get(property_name, [])

    def has_fulltext_index_on(self, properties: list[str]) -> bool:
        """Check if there's a fulltext index covering these properties"""
        for index in self.indexes:
            if index.type == "FULLTEXT" and all(prop in index.properties for prop in properties):
                return True
        return False

    def get_searchable_properties(self) -> list[str]:
        """Get properties that have search-friendly indexes"""
        searchable = set()
        for index in self.indexes:
            if index.type in ["FULLTEXT", "TEXT"]:
                searchable.update(index.properties)
        return list(searchable)

    def validate_node_label(self, label: str) -> bool:
        """Validate that a node label exists in the schema"""
        return label in self.node_labels

    def validate_relationship_type(self, rel_type: str) -> bool:
        """Validate that a relationship type exists in the schema"""
        return rel_type in self.relationship_types

    def validate_property_on_label(self, label: str, property_name: str) -> bool:
        """Validate that a property exists on a specific label"""
        if label not in self.node_label_info:
            return False
        return property_name in self.node_label_info[label].properties
