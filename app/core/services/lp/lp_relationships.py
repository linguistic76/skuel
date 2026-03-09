"""
Learning Path Relationships Helper (Graph-Native Pattern)

Container for learning path relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
LpRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
LP_QUERY_SPECS: list[tuple[str, str]] = [
    ("prerequisite_uids", "prerequisites"),
    ("milestone_event_uids", "milestones"),
    ("aligned_goal_uids", "goals"),
    ("embodied_principle_uids", "principles"),
    ("step_uids", "steps"),
]


@dataclass(frozen=True)
class LpRelationships:
    """
    Container for all learning path relationship data (fetched from Neo4j graph).

    Usage:
        rels = await LpRelationships.fetch(lp_uid, service.relationships)
        if rels.step_uids:
            step_count = len(rels.step_uids)
    """

    prerequisite_uids: list[str] = field(default_factory=list)
    milestone_event_uids: list[str] = field(default_factory=list)
    aligned_goal_uids: list[str] = field(default_factory=list)
    embodied_principle_uids: list[str] = field(default_factory=list)
    step_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, lp_uid: str, service: LpRelationshipService) -> LpRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=lp_uid,
            service=service,
            query_specs=LP_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> LpRelationships:
        """Create empty LpRelationships (for testing or new learning paths)."""
        return cls()

    def has_prerequisites(self) -> bool:
        """Check if learning path has prerequisite knowledge requirements."""
        return len(self.prerequisite_uids) > 0

    def has_milestones(self) -> bool:
        """Check if learning path has milestone events."""
        return len(self.milestone_event_uids) > 0

    def is_goal_aligned(self) -> bool:
        """Check if learning path aligns with any goals."""
        return len(self.aligned_goal_uids) > 0

    def embodies_principles(self) -> bool:
        """Check if learning path embodies principles."""
        return len(self.embodied_principle_uids) > 0

    def has_steps(self) -> bool:
        """Check if learning path has learning steps."""
        return len(self.step_uids) > 0

    def is_complete_path(self) -> bool:
        """Check if learning path is well-defined (has steps and at least one goal or principle)."""
        return self.has_steps() and (self.is_goal_aligned() or self.embodies_principles())

    def total_step_count(self) -> int:
        """Get total number of learning steps."""
        return len(self.step_uids)

    def total_milestone_count(self) -> int:
        """Get total number of milestone events."""
        return len(self.milestone_event_uids)

    def prerequisite_count(self) -> int:
        """Get total number of prerequisite knowledge units."""
        return len(self.prerequisite_uids)

    def motivational_score(self) -> float:
        """Calculate motivational score based on goal and principle alignment (0.0-1.0)."""
        score = 0.0
        if self.aligned_goal_uids:
            score += min(len(self.aligned_goal_uids) * 0.2, 0.5)
        if self.embodied_principle_uids:
            score += min(len(self.embodied_principle_uids) * 0.2, 0.5)
        return min(score, 1.0)

    def get_all_related_uids(self) -> set[str]:
        """Get all unique UIDs across all relationship types."""
        all_uids: set[str] = set()
        all_uids.update(self.prerequisite_uids)
        all_uids.update(self.milestone_event_uids)
        all_uids.update(self.aligned_goal_uids)
        all_uids.update(self.embodied_principle_uids)
        all_uids.update(self.step_uids)
        return all_uids
