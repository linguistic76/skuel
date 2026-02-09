"""
Learning Path DTO (Tier 2 - Transfer)
======================================

Mutable data transfer object for moving learning path data between layers.
No business logic, just data structure.

Phase 3 Graph-Native Migration (January 2026):
- Relationship fields removed - relationships stored ONLY as Neo4j edges
- Use LpRelationships.fetch() to get prerequisites when needed
- See: /docs/migrations/PHASE_3_GRAPH_NATIVE_COMPLETE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain
from core.services.protocols import get_enum_value

from .lp import LpType


@dataclass
class LpDTO:
    """
    Mutable data transfer object for learning paths.

    Used for:
    - Moving data between service and repository layers
    - Database operations (save/update)
    - Service-to-service communication
    """

    # Core fields (required)
    uid: str
    name: str
    goal: str
    domain: Domain

    # Configuration
    path_type: LpType = LpType.STRUCTURED
    difficulty: str = "intermediate"

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str | None = None

    # Outcomes (text strings, NOT relationships)
    outcomes: list[str] = field(default_factory=list)

    # Time estimates
    estimated_hours: float = 0.0

    # Milestone checkpoints
    checkpoint_week_intervals: list[int] = field(default_factory=list)

    # =========================================================================
    # PHASE 3: RELATIONSHIP FIELDS REMOVED (January 2026)
    # =========================================================================
    # Prerequisites are now stored ONLY as Neo4j graph edges.
    #
    # To fetch prerequisites, use LpRelationships.fetch():
    #   rels = await LpRelationships.fetch(lp_uid, service.relationships)
    #   prereqs = rels.prerequisite_uids
    #
    # OLD FIELDS REMOVED:
    # - prerequisites: list[str]
    # =========================================================================

    # Additional transfer fields
    user_uid: str | None = None
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for database operations.

        Returns:
            Dictionary representation with serialized enums and datetimes.
        """
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = {
            "uid": self.uid,
            "name": self.name,
            "goal": self.goal,
            "domain": get_enum_value(self.domain),
            "path_type": get_enum_value(self.path_type),
            "difficulty": self.difficulty,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "outcomes": list(self.outcomes),
            "estimated_hours": self.estimated_hours,
            "checkpoint_week_intervals": list(self.checkpoint_week_intervals),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

        convert_datetimes_to_iso(data, ["created_at", "updated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LpDTO":
        """
        Create DTO from dictionary (from database).

        Infrastructure fields (e.g., 'embedding', 'embedding_version') are
        automatically filtered out by dto_from_dict.

        See: /docs/decisions/ADR-037-embedding-infrastructure-separation.md
        """
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "domain": Domain,
                "path_type": LpType,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=["outcomes", "tags", "checkpoint_week_intervals"],
            deprecated_fields=["prerequisites"],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, LpDTO):
            return False
        return self.uid == other.uid
