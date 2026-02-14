"""
Choice Relationships Helper (Graph-Native Pattern)

Container for choice relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
ChoicesRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
# Defines the mapping between dataclass fields and service query methods
CHOICE_QUERY_SPECS: list[tuple[str, str]] = [
    ("informed_by_knowledge_uids", "informed_knowledge"),
    ("opens_learning_path_uids", "learning_paths"),
    ("required_knowledge_uids", "required_knowledge"),
    ("aligned_principle_uids", "principles"),
    ("implementing_task_uids", "implementing_tasks"),
    ("serves_life_path_uids", "life_path"),
    ("impacted_habit_uids", "impacted_habits"),
    ("informing_habit_uids", "informing_habits"),
    ("scheduled_event_uids", "scheduled_events"),
    ("triggering_event_uids", "triggering_events"),
]


@dataclass(frozen=True)
class ChoiceRelationships:
    """
    Container for all choice relationship data (fetched from Neo4j graph).

    Usage:
        rels = await ChoiceRelationships.fetch(choice_uid, service.relationships)
        if rels.informed_by_knowledge_uids:
            knowledge_score = len(rels.informed_by_knowledge_uids) * 0.2
    """

    informed_by_knowledge_uids: list[str] = field(default_factory=list)
    opens_learning_path_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)
    implementing_task_uids: list[str] = field(default_factory=list)
    serves_life_path_uids: list[str] = field(default_factory=list)

    # Habit relationships
    impacted_habit_uids: list[str] = field(default_factory=list)
    informing_habit_uids: list[str] = field(default_factory=list)

    # Event relationships
    scheduled_event_uids: list[str] = field(default_factory=list)
    triggering_event_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(
        cls, choice_uid: str, service: ChoicesRelationshipService
    ) -> ChoiceRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=choice_uid,
            service=service,
            query_specs=CHOICE_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> ChoiceRelationships:
        """Create empty ChoiceRelationships (for testing or new choices)."""
        return cls()

    def has_any_knowledge(self) -> bool:
        """Check if choice has any knowledge connections."""
        return (
            len(self.informed_by_knowledge_uids) > 0
            or len(self.required_knowledge_uids) > 0
            or len(self.opens_learning_path_uids) > 0
        )

    def total_knowledge_count(self) -> int:
        """Get total count of all knowledge connections."""
        return (
            len(self.informed_by_knowledge_uids)
            + len(self.required_knowledge_uids)
            + len(self.opens_learning_path_uids)
        )

    def is_principle_aligned(self) -> bool:
        """Check if choice aligns with any principles."""
        return len(self.aligned_principle_uids) > 0

    def is_informed_decision(self) -> bool:
        """Check if choice was informed by knowledge."""
        return len(self.informed_by_knowledge_uids) > 0

    def opens_learning(self) -> bool:
        """Check if choice opens learning opportunities."""
        return len(self.opens_learning_path_uids) > 0

    def has_implementing_tasks(self) -> bool:
        """Check if choice has tasks that implement it."""
        return len(self.implementing_task_uids) > 0

    def is_actionable(self) -> bool:
        """Check if choice has been converted to actionable tasks."""
        return self.has_implementing_tasks() or self.opens_learning()

    def get_all_knowledge_uids(self) -> set[str]:
        """Get all unique knowledge UIDs across all relationship types."""
        all_uids: set[str] = set()
        all_uids.update(self.informed_by_knowledge_uids)
        all_uids.update(self.required_knowledge_uids)
        return all_uids

    def serves_life_path(self) -> bool:
        """Check if choice serves user's life path."""
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """Get the life path UID this choice serves (if any)."""
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None

    def has_habit_impact(self) -> bool:
        """Check if choice has any habit relationships."""
        return len(self.impacted_habit_uids) > 0 or len(self.informing_habit_uids) > 0

    def impacts_habits(self) -> bool:
        """Check if this choice impacted any habits."""
        return len(self.impacted_habit_uids) > 0

    def informed_by_habits(self) -> bool:
        """Check if this choice was informed by any habits."""
        return len(self.informing_habit_uids) > 0

    def has_event_relationship(self) -> bool:
        """Check if choice has any event relationships."""
        return len(self.scheduled_event_uids) > 0 or len(self.triggering_event_uids) > 0

    def schedules_events(self) -> bool:
        """Check if this choice scheduled any events."""
        return len(self.scheduled_event_uids) > 0

    def triggered_by_events(self) -> bool:
        """Check if this choice was triggered by any events."""
        return len(self.triggering_event_uids) > 0
