"""
Schema Change Detection Models
=============================

Data models for tracking and responding to Neo4j schema evolution.
Provides fingerprinting, change detection, and migration tracking.
"""

__version__ = "2.1"


import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Protocols
from .schema import SchemaContext


class SchemaChangeType(Enum):
    """Types of schema changes that can occur"""

    # Node labels
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"

    # Indexes
    INDEX_ADDED = "index_added"
    INDEX_REMOVED = "index_removed"
    INDEX_MODIFIED = "index_modified"

    # Constraints
    CONSTRAINT_ADDED = "constraint_added"
    CONSTRAINT_REMOVED = "constraint_removed"
    CONSTRAINT_MODIFIED = "constraint_modified"

    # Properties
    PROPERTY_ADDED = "property_added"
    PROPERTY_REMOVED = "property_removed"
    PROPERTY_TYPE_CHANGED = "property_type_changed"

    # Relationships
    RELATIONSHIP_TYPE_ADDED = "relationship_type_added"
    RELATIONSHIP_TYPE_REMOVED = "relationship_type_removed"

    # Node counts (significant changes)
    NODE_COUNT_CHANGED = "node_count_changed"


class ChangeImpact(Enum):
    """Impact level of schema changes on query optimization"""

    LOW = "low"  # Minor changes, existing optimizations still valid
    MEDIUM = "medium"  # Some optimizations need refresh
    HIGH = "high"  # Major changes, full re-optimization needed
    CRITICAL = "critical"  # Breaking changes, queries may fail


@dataclass
class SchemaFingerprint:
    """
    Lightweight fingerprint of schema state for change detection.
    Uses hashing to efficiently detect when schema has changed.
    """

    timestamp: datetime
    version_hash: str  # Hash of entire schema structure
    label_hash: str  # Hash of node labels
    index_hash: str  # Hash of indexes
    constraint_hash: str  # Hash of constraints
    property_hash: str  # Hash of property mappings
    relationship_hash: str  # Hash of relationship types

    # Detailed counts for quick comparison
    label_count: int
    index_count: int
    constraint_count: int
    relationship_count: int

    @classmethod
    def from_schema_context(cls, schema: SchemaContext) -> "SchemaFingerprint":
        """Create fingerprint from a schema context"""
        timestamp = datetime.now()

        # Create sorted representations for consistent hashing
        labels = sorted(schema.node_labels)
        relationships = sorted(schema.relationship_types)

        # Index representation
        def get_index_name(idx) -> str:
            return idx.name

        indexes = [
            {
                "name": idx.name,
                "type": idx.type,
                "labels": sorted(idx.labels) if idx.labels else [],
                "properties": sorted(idx.properties) if idx.properties else [],
            }
            for idx in sorted(schema.indexes, key=get_index_name)
        ]

        # Constraint representation
        def get_constraint_name(constraint) -> str:
            return constraint.name

        constraints = [
            {
                "name": constraint.name,
                "type": constraint.type,
                "labels": sorted(constraint.labels) if constraint.labels else [],
                "properties": sorted(constraint.properties) if constraint.properties else [],
            }
            for constraint in sorted(schema.constraints, key=get_constraint_name)
        ]

        # Property mapping representation
        properties = {}
        for label, info in schema.node_label_info.items():
            properties[label] = {
                "properties": sorted(getattr(info, "properties", [])),
                "count": getattr(info, "count", 0),
            }

        # Create hashes
        label_hash = cls._hash_object(labels)
        index_hash = cls._hash_object(indexes)
        constraint_hash = cls._hash_object(constraints)
        property_hash = cls._hash_object(properties)
        relationship_hash = cls._hash_object(relationships)

        # Overall version hash
        version_data = {
            "labels": label_hash,
            "indexes": index_hash,
            "constraints": constraint_hash,
            "properties": property_hash,
            "relationships": relationship_hash,
        }
        version_hash = cls._hash_object(version_data)

        return cls(
            timestamp=timestamp,
            version_hash=version_hash,
            label_hash=label_hash,
            index_hash=index_hash,
            constraint_hash=constraint_hash,
            property_hash=property_hash,
            relationship_hash=relationship_hash,
            label_count=len(labels),
            index_count=len(indexes),
            constraint_count=len(constraints),
            relationship_count=len(relationships),
        )

    @staticmethod
    def _hash_object(obj: Any) -> str:
        """Create consistent hash of any object"""
        json_str = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]  # 16 char hash

    def has_changed(self, other: "SchemaFingerprint") -> bool:
        """Check if schema has changed compared to another fingerprint"""
        return self.version_hash != other.version_hash

    def get_changed_areas(self, other: "SchemaFingerprint") -> list[str]:
        """Get list of schema areas that have changed"""
        changes = []

        if self.label_hash != other.label_hash:
            changes.append("labels")
        if self.index_hash != other.index_hash:
            changes.append("indexes")
        if self.constraint_hash != other.constraint_hash:
            changes.append("constraints")
        if self.property_hash != other.property_hash:
            changes.append("properties")
        if self.relationship_hash != other.relationship_hash:
            changes.append("relationships")

        return changes


@dataclass
class SchemaChange:
    """Represents a specific schema change that was detected"""

    change_type: SchemaChangeType
    impact: ChangeImpact
    description: str
    affected_entity: str  # What was changed (index name, label, etc.)
    old_value: Any | None = (None,)
    new_value: Any | None = None
    detected_at: datetime = field(default_factory=datetime.now)

    # Context about what queries/optimizations are affected
    affected_templates: list[str] = field(default_factory=list)
    affected_builders: list[str] = field(default_factory=list)
    optimization_impact: str | None = None


@dataclass
class SchemaChangeReport:
    """Comprehensive report of schema changes between two points in time"""

    from_fingerprint: SchemaFingerprint
    to_fingerprint: SchemaFingerprint
    changes: list[SchemaChange]
    overall_impact: ChangeImpact
    recommendations: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def has_breaking_changes(self) -> bool:
        """Check if there are any breaking changes"""
        return any(change.impact == ChangeImpact.CRITICAL for change in self.changes)

    @property
    def requires_cache_invalidation(self) -> bool:
        """Check if schema cache should be invalidated"""
        return any(
            change.impact in [ChangeImpact.HIGH, ChangeImpact.CRITICAL] for change in self.changes
        )

    @property
    def requires_reoptimization(self) -> bool:
        """Check if query optimizations need to be refreshed"""
        return any(
            change.impact in [ChangeImpact.MEDIUM, ChangeImpact.HIGH, ChangeImpact.CRITICAL]
            for change in self.changes
        )

    def get_changes_by_type(self, change_type: SchemaChangeType) -> list[SchemaChange]:
        """Get all changes of a specific type"""
        return [change for change in self.changes if change.change_type == change_type]

    def get_changes_by_impact(self, impact: ChangeImpact) -> list[SchemaChange]:
        """Get all changes with a specific impact level"""
        return [change for change in self.changes if change.impact == impact]


@dataclass
class SchemaMigrationHistory:
    """Tracks history of schema changes over time"""

    schema_id: str  # Unique identifier for this schema instance
    initial_fingerprint: SchemaFingerprint
    current_fingerprint: SchemaFingerprint
    change_history: list[SchemaChangeReport] = field(default_factory=list)
    migration_count: int = 0

    def add_change_report(self, report: SchemaChangeReport):
        """Add a new change report to history"""
        self.change_history.append(report)
        self.current_fingerprint = report.to_fingerprint
        self.migration_count += 1

        # Keep only last 50 changes to prevent unbounded growth
        if len(self.change_history) > 50:
            self.change_history = self.change_history[-50:]

    def get_recent_changes(self, hours: int = 24) -> list[SchemaChangeReport]:
        """Get schema changes within the last N hours"""
        cutoff = datetime.now().timestamp() - (hours * 3600)
        return [
            report for report in self.change_history if report.generated_at.timestamp() >= cutoff
        ]

    def get_breaking_changes(self) -> list[SchemaChange]:
        """Get all breaking changes from history"""
        breaking_changes = []
        for report in self.change_history:
            breaking_changes.extend(
                change for change in report.changes if change.impact == ChangeImpact.CRITICAL
            )
        return breaking_changes


@dataclass
class SchemaEvolutionStats:
    """Statistics about schema evolution patterns"""

    total_changes: int
    changes_by_type: dict[SchemaChangeType, int] = field(default_factory=dict)
    changes_by_impact: dict[ChangeImpact, int] = field(default_factory=dict)
    average_changes_per_day: float = 0.0
    most_volatile_areas: list[str] = field(
        default_factory=list
    )  # Areas that change most frequently
    stability_score: float = 1.0  # 0.0 (very unstable) to 1.0 (very stable)

    @classmethod
    def from_history(cls, history: SchemaMigrationHistory) -> "SchemaEvolutionStats":
        """Generate statistics from migration history"""
        all_changes = []
        for report in history.change_history:
            all_changes.extend(report.changes)

        if not all_changes:
            return cls(total_changes=0)

        # Count by type
        changes_by_type = {}
        for change in all_changes:
            changes_by_type[change.change_type] = changes_by_type.get(change.change_type, 0) + 1

        # Count by impact
        changes_by_impact = {}
        for change in all_changes:
            changes_by_impact[change.impact] = changes_by_impact.get(change.impact, 0) + 1

        # Calculate time-based metrics
        if len(history.change_history) > 1:
            first_change = history.change_history[0].generated_at
            last_change = history.change_history[-1].generated_at
            days = (last_change - first_change).days or 1
            avg_changes_per_day = len(all_changes) / days
        else:
            avg_changes_per_day = 0

        # Calculate stability (fewer breaking changes = higher stability)
        breaking_changes = changes_by_impact.get(ChangeImpact.CRITICAL, 0)
        stability_score = max(0.0, 1.0 - (breaking_changes / max(1, len(all_changes))))

        return cls(
            total_changes=len(all_changes),
            changes_by_type=changes_by_type,
            changes_by_impact=changes_by_impact,
            average_changes_per_day=avg_changes_per_day,
            stability_score=stability_score,
        )


# Event system for schema change notifications
@dataclass
class SchemaChangeEvent:
    """Event triggered when schema changes are detected"""

    event_id: str
    change_report: SchemaChangeReport
    timestamp: datetime = field(default_factory=datetime.now)
    handled: bool = False

    def mark_handled(self):
        """Mark this event as handled"""
        self.handled = True
