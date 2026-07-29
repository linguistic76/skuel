"""
Goal Relationships Helper (Graph-Native Pattern)

Container for goal relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.ports.knowledge_pattern_protocol import compute_knowledge_intensity
from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Query specifications: (field_name, GOAPS_CONFIG relationship method key).
# Keys must match GOAPS_CONFIG exactly — validated by tests/unit/test_query_spec_keys.py.
GOAL_QUERY_SPECS: list[tuple[str, str]] = [
    ("aligned_learning_path_uids", "aligned_paths"),
    ("requires_completion_of_paths", "required_paths"),
    ("required_knowledge_uids", "knowledge"),
    ("sub_goal_uids", "subgoals"),
    ("supporting_habit_uids", "supporting_habits"),
    ("essential_habit_uids", "essential_habits"),
    ("critical_habit_uids", "critical_habits"),
    ("optional_habit_uids", "optional_habits"),
    ("guiding_principle_uids", "principles"),
    ("serves_life_path_uids", "life_path"),
]


@dataclass(frozen=True)
class GoalRelationships:
    """
    Container for all goal relationship data (fetched from Neo4j graph).

    Usage:
        rels = await GoalRelationships.fetch(goal_uid, service.relationships)
        if rels.required_knowledge_uids:
            knowledge_score = len(rels.required_knowledge_uids) * 0.2
    """

    # Learning path relationships
    aligned_learning_path_uids: list[str] = field(default_factory=list)
    requires_completion_of_paths: list[str] = field(default_factory=list)

    # Knowledge relationships
    required_knowledge_uids: list[str] = field(default_factory=list)

    # Goal hierarchy
    sub_goal_uids: list[str] = field(default_factory=list)

    # Habit relationships (James Clear: "You fall to the level of your systems")
    supporting_habit_uids: list[str] = field(default_factory=list)
    essential_habit_uids: list[str] = field(default_factory=list)
    critical_habit_uids: list[str] = field(default_factory=list)
    optional_habit_uids: list[str] = field(default_factory=list)

    # Principle relationships
    guiding_principle_uids: list[str] = field(default_factory=list)

    # Life path alignment
    serves_life_path_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, goal_uid: str, service: UnifiedRelationshipService) -> GoalRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=goal_uid,
            service=service,
            query_specs=GOAL_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> GoalRelationships:
        """Create empty GoalRelationships (for testing or new goals)."""
        return cls()

    def has_any_knowledge(self) -> bool:
        """Check if goal has any knowledge connections."""
        return len(self.required_knowledge_uids) > 0

    # KnowledgeLinkedRelationships protocol --------------------------------

    @property
    def primary_knowledge_uids(self) -> list[str]:
        """Knowledge required to achieve this goal (REQUIRES_KNOWLEDGE edges)."""
        return self.required_knowledge_uids

    @property
    def secondary_knowledge_uids(self) -> list[str]:
        """Goals have no secondary knowledge tier."""
        return []

    def knowledge_intensity(self) -> float:
        """0-1 score: how knowledge-rich this goal is by relationship count."""
        return compute_knowledge_intensity(
            self.primary_knowledge_uids, self.secondary_knowledge_uids
        )
