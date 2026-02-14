"""
Goal Relationships Helper (Graph-Native Pattern)

Container for goal relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
GoalsRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
# Defines the mapping between dataclass fields and service query methods
GOAL_QUERY_SPECS: list[tuple[str, str]] = [
    ("aligned_learning_path_uids", "aligned_learning_paths"),
    ("requires_completion_of_paths", "required_paths"),
    ("required_knowledge_uids", "knowledge"),
    ("sub_goal_uids", "subgoals"),
    ("supporting_habit_uids", "supporting_habits"),
    ("essential_habit_uids", "essential_habits"),
    ("critical_habit_uids", "critical_habits"),
    ("optional_habit_uids", "optional_habits"),
    ("guiding_principle_uids", "principles"),
    ("milestone_uids", "milestones"),
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

    # Milestone relationships
    milestone_uids: list[str] = field(default_factory=list)

    # Life path alignment
    serves_life_path_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, goal_uid: str, service: GoalsRelationshipService) -> GoalRelationships:
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

    def has_curriculum_alignment(self) -> bool:
        """Check if goal has aligned learning paths."""
        return len(self.aligned_learning_path_uids) > 0

    def total_curriculum_dependencies(self) -> int:
        """Calculate total curriculum dependencies."""
        return (
            len(self.aligned_learning_path_uids)
            + len(self.requires_completion_of_paths)
            + len(self.required_knowledge_uids)
        )

    def has_habit_support(self) -> bool:
        """Check if goal has supporting habits."""
        return len(self.supporting_habit_uids) > 0

    def has_subgoals(self) -> bool:
        """Check if goal has subgoals."""
        return len(self.sub_goal_uids) > 0

    def has_milestones(self) -> bool:
        """Check if goal has milestones."""
        return len(self.milestone_uids) > 0

    def milestone_count(self) -> int:
        """Get count of milestones for this goal."""
        return len(self.milestone_uids)

    def serves_life_path(self) -> bool:
        """Check if goal serves user's life path."""
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """Get the life path UID this goal serves (if any)."""
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None
