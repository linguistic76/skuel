"""
Habit Relationships Helper (Graph-Native Pattern)

Container for habit relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Query specifications: (field_name, service_method_name)
# Defines the mapping between dataclass fields and service query methods
HABIT_QUERY_SPECS: list[tuple[str, str]] = [
    ("linked_goal_uids", "supported_goals"),
    ("knowledge_reinforcement_uids", "knowledge"),
    ("serves_life_path_uids", "life_path"),
    ("informed_choice_uids", "informed_choices"),
    ("impacting_choice_uids", "impacting_choices"),
]


@dataclass(frozen=True)
class HabitRelationships:
    """
    Container for all habit relationship data (fetched from Neo4j graph).

    Usage:
        rels = await HabitRelationships.fetch(habit_uid, service.relationships)
        if rels.linked_goal_uids:
            goal_count = len(rels.linked_goal_uids)
    """

    # Goal relationships (James Clear: "You fall to the level of your systems")
    linked_goal_uids: list[str] = field(default_factory=list)

    # Knowledge relationships (practice reinforces mastery)
    knowledge_reinforcement_uids: list[str] = field(default_factory=list)

    # Life path alignment
    serves_life_path_uids: list[str] = field(default_factory=list)

    # Choice relationships (January 2026)
    informed_choice_uids: list[str] = field(default_factory=list)
    impacting_choice_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, habit_uid: str, service: UnifiedRelationshipService) -> HabitRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=habit_uid,
            service=service,
            query_specs=HABIT_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> HabitRelationships:
        """Create empty HabitRelationships (for testing or new habits)."""
        return cls()

    def has_goal_support(self) -> bool:
        """Check if habit supports any goals."""
        return len(self.linked_goal_uids) > 0

    def supports_goal_count(self) -> int:
        """Count how many goals this habit supports."""
        return len(self.linked_goal_uids)

    def informs_choices(self) -> bool:
        """Check if this habit has informed any choices."""
        return len(self.informed_choice_uids) > 0
