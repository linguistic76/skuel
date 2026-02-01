"""
Knowledge DTO (Tier 2 - Transfer)
==================================

Mutable data transfer object for moving knowledge data between layers.
No business logic, just data structure.

Phase 3 Graph-Native Migration (October 6, 2025):
- Relationship fields removed - relationships stored ONLY as Neo4j edges
- Use backend methods to fetch relationships when needed
- See: /docs/migrations/PHASE_3_GRAPH_NATIVE_COMPLETE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.shared_enums import Domain
from core.services.protocols import get_enum_value
from core.utils.uid_generator import UIDGenerator


@dataclass
class KuDTO:
    """
    Mutable data transfer object for knowledge.

    Used for:
    - Moving data between service and repository layers
    - Database operations (save/update)
    - Service-to-service communication
    """

    # Core fields (required)
    uid: str
    title: str
    content: str
    domain: Domain

    # Semantic fields (always present, may have defaults)
    quality_score: float = 0.0
    complexity: str = "medium"
    semantic_links: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)

    # =========================================================================
    # PHASE 3: RELATIONSHIP FIELDS REMOVED (October 6, 2025)
    # =========================================================================
    # Relationships are now stored ONLY as Neo4j graph edges.
    #
    # To fetch relationships with a DTO, use service methods:
    #   - service.get_knowledge_with_relationships(uid)
    #   - backend.get_prerequisites(uid)
    #   - backend.get_enables(uid)
    #   - backend.get_related(uid)
    #
    # OLD FIELDS REMOVED:
    # - prerequisites: list[str] = field(default_factory=list)
    # - enables: list[str] = field(default_factory=list)
    # - related_to: list[str] = field(default_factory=list)
    # =========================================================================

    # Optional enrichment data
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        title: str,
        content: str,
        domain: Domain,
        tags: list[str] | None = None,
        complexity: str = "medium",
    ) -> "KuDTO":
        """
        Factory method to create a new KuDTO with generated UID.

        Phase 3: prerequisites parameter removed - create relationships
        using backend.create_semantic_relationship() after entity creation.
        """
        return cls(
            uid=UIDGenerator.generate_uid("knowledge"),
            title=title,
            content=content,
            domain=domain,
            tags=tags or [],
            complexity=complexity,
        )

    def update_from(self, updates: dict[str, Any]) -> None:
        """
        Update DTO fields from a dictionary (for update operations).

        Phase 3: Relationship fields removed from allowed_fields.
        """
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                "title",
                "content",
                "domain",
                "quality_score",
                "complexity",
                "semantic_links",
                "tags",
                "metadata",
            },
        )

    def to_dict(
        self, include_relationships: bool = False, relationships: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Convert to dictionary for database operations or YAML export.

        Phase 3: Relationship fields removed - not serialized to database by default.
        For YAML export, pass include_relationships=True with relationships dict.

        Args:
            include_relationships: If True, include relationships in output (for YAML export)
            relationships: Dictionary of relationships (from graph queries)

        Returns:
            Dictionary representation
        """
        from core.models.dto_helpers import convert_datetimes_to_iso

        # Build dict manually to avoid deepcopy issues with enums (mappingproxy)
        data = {
            "uid": self.uid,
            "title": self.title,
            "content": self.content,
            "domain": get_enum_value(self.domain),
            "quality_score": self.quality_score,
            "complexity": self.complexity,
            "semantic_links": list(self.semantic_links),  # Copy list
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": list(self.tags),  # Copy list
            "metadata": dict(self.metadata),  # Copy dict
        }

        # Convert datetimes to ISO format
        convert_datetimes_to_iso(data, ["created_at", "updated_at"])

        # Phase 3: Add relationships for YAML export if provided
        if include_relationships and relationships:
            data["connections"] = relationships

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KuDTO":
        """
        Create DTO from dictionary (from database).

        Infrastructure fields (e.g., 'embedding', 'embedding_version') are
        automatically filtered out by dto_from_dict. Embeddings are search
        infrastructure stored in Neo4j for vector search, not domain data.

        Phase 3: Relationship fields removed - not loaded from database.
        Use backend methods to fetch relationships after loading.

        See: /docs/decisions/ADR-037-embedding-infrastructure-separation.md
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={"domain": Domain},
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "semantic_links"],
            deprecated_fields=["prerequisites", "enables", "related_to"],
        )

    def __eq__(self, other) -> bool:
        """Equality based on UID."""
        if not isinstance(other, KuDTO):
            return False
        return self.uid == other.uid
