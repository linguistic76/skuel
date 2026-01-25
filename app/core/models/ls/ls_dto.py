"""
LearningStep DTO (Tier 2 - Transfer)
====================================

Mutable data transfer object for LearningStep.
Used for data movement between layers.

Phase 3 Graph-Native Migration (January 2026):
- Relationship fields removed - relationships stored ONLY as Neo4j edges
- Use LsRelationships.fetch() to get relationships when needed
- See: /docs/migrations/PHASE_3_GRAPH_NATIVE_COMPLETE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.shared_enums import Domain, Priority

from .ls import StepDifficulty, StepStatus


@dataclass
class LearningStepDTO:
    """
    Mutable DTO for LearningStep data transfer.

    Converts immutable tuples to mutable lists for easier manipulation
    during data transfer and API operations.
    """

    # Identity
    uid: str
    title: str
    intent: str
    description: str | None = None

    # Knowledge Content (mutable lists)
    primary_knowledge_uids: list[str] = None
    supporting_knowledge_uids: list[str] = None

    # Path Integration
    learning_path_uid: str | None = None
    sequence: int | None = None

    # =========================================================================
    # PHASE 3: RELATIONSHIP FIELDS REMOVED (January 2026)
    # =========================================================================
    # Relationships are now stored ONLY as Neo4j graph edges.
    #
    # To fetch relationships, use LsRelationships.fetch():
    #   rels = await LsRelationships.fetch(ls_uid, service.relationships)
    #   prereqs = rels.prerequisite_step_uids
    #   principles = rels.principle_uids
    #
    # OLD FIELDS REMOVED:
    # - prerequisite_step_uids: list[str]
    # - prerequisite_knowledge_uids: list[str]
    # - principle_uids: list[str]
    # - choice_uids: list[str]
    # - habit_uids: list[str]
    # - task_uids: list[str]
    # - event_template_uids: list[str]
    # =========================================================================

    # Mastery & Progress
    mastery_threshold: float = 0.7
    current_mastery: float = 0.0
    estimated_hours: float = 1.0
    difficulty: StepDifficulty = StepDifficulty.MODERATE

    # Status
    status: StepStatus = StepStatus.NOT_STARTED
    completed: bool = False
    completed_at: datetime | None = None

    # Domain & Priority
    domain: Domain = Domain.PERSONAL
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None
    updated_at: datetime = None
    notes: str | None = None
    tags: list[str] = None
    metadata: dict[str, Any] = None  # Rich context storage (graph neighborhoods, etc.)

    def __post_init__(self) -> None:
        """Initialize list fields to empty lists if None."""
        if self.primary_knowledge_uids is None:
            self.primary_knowledge_uids = []
        if self.supporting_knowledge_uids is None:
            self.supporting_knowledge_uids = []
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
