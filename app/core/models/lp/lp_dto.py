"""
Learning Data Transfer Objects (Tier 2 - Transfer)
===================================================

Mutable DTOs for transferring learning data between layers.

Phase 3 Graph-Native Migration (January 2026):
- Relationship fields removed - relationships stored ONLY as Neo4j edges
- Use LpRelationships.fetch() to get prerequisites when needed
- See: /docs/migrations/PHASE_3_GRAPH_NATIVE_COMPLETE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain


@dataclass
class LearningStepDTO:
    """
    Mutable DTO for transferring learning step data within LP context.

    Used for data movement between service and backend layers.
    Note: This is a simplified DTO for LP's embedded steps. For full
    LearningStep operations, use core.models.ls.ls_dto.LearningStepDTO.
    """

    # Identity
    uid: str
    knowledge_uid: str  # Reference to Knowledge model
    sequence: int  # Order in the path

    # Requirements
    mastery_threshold: float = 0.7  # Required mastery level (0.0-1.0),
    estimated_hours: float = 1.0

    # Status
    current_mastery: float = 0.0
    completed: bool = False
    completed_at: datetime | None = None

    # Optional fields
    notes: str | None = None


@dataclass
class LpDTO:
    """
    Mutable DTO for transferring learning path data.

    Used for data movement between service and backend layers.
    """

    # Identity
    uid: str
    name: str
    goal: str  # What the learner will achieve
    domain: Domain

    # Configuration
    path_type: str = "structured"  # Using string for flexibility,
    difficulty: str = "intermediate"

    # Steps (mutable list)
    steps: list[LearningStepDTO] = field(default_factory=list)

    # Metadata
    created_at: datetime | None = None

    updated_at: datetime | None = None

    created_by: str | None = None

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
    # - prerequisites: list[str]  # Was graph-populated from (lp)-[:REQUIRES_KNOWLEDGE]->(ku)
    # =========================================================================

    # Outcomes (text strings, NOT relationships - kept)
    outcomes: list[str] = field(default_factory=list)  # Learning outcomes (text strings)

    # Time estimates
    estimated_hours: float = 0.0

    # Additional transfer fields
    user_uid: str | None = None  # For user-specific paths,
    source: str | None = None  # Where path originated,
    tags: list[str] = field(default_factory=list)  # For categorization
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Rich context storage (graph neighborhoods, etc.)
