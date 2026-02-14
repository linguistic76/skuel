"""
Principle Relationships Helper (Graph-Native Pattern)

Container for principle relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
PrinciplesRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
PRINCIPLE_QUERY_SPECS: list[tuple[str, str]] = [
    ("grounded_knowledge_uids", "knowledge"),
    ("guided_goal_uids", "goals"),
    ("inspired_habit_uids", "habits"),
    ("related_principle_uids", "related_principles"),
    ("guided_choice_uids", "guided_choices"),
    ("guided_task_uids", "aligned_tasks"),
    ("serves_life_path_uids", "life_path"),
    ("demonstrating_event_uids", "demonstrating_events"),
    ("practice_event_uids", "practice_events"),
]


@dataclass(frozen=True)
class PrincipleRelationships:
    """
    Container for all principle relationship data (fetched from Neo4j graph).

    Usage:
        rels = await PrincipleRelationships.fetch(principle_uid, service.relationships)
        if rels.guided_goal_uids:
            integration_score += len(rels.guided_goal_uids) * 0.3
    """

    grounded_knowledge_uids: list[str] = field(default_factory=list)
    guided_goal_uids: list[str] = field(default_factory=list)
    inspired_habit_uids: list[str] = field(default_factory=list)
    related_principle_uids: list[str] = field(default_factory=list)
    guided_choice_uids: list[str] = field(default_factory=list)
    guided_task_uids: list[str] = field(default_factory=list)
    serves_life_path_uids: list[str] = field(default_factory=list)

    # Event relationships
    demonstrating_event_uids: list[str] = field(default_factory=list)
    practice_event_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(
        cls, principle_uid: str, service: PrinciplesRelationshipService
    ) -> PrincipleRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=principle_uid,
            service=service,
            query_specs=PRINCIPLE_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> PrincipleRelationships:
        """Create empty PrincipleRelationships (for testing or new principles)."""
        return cls()

    def has_any_knowledge(self) -> bool:
        """Check if principle has any knowledge grounding."""
        return len(self.grounded_knowledge_uids) > 0

    def guides_goals(self) -> bool:
        """Check if principle guides any goals."""
        return len(self.guided_goal_uids) > 0

    def inspires_habits(self) -> bool:
        """Check if principle inspires any habits."""
        return len(self.inspired_habit_uids) > 0

    def guides_choices(self) -> bool:
        """Check if principle guides any choices."""
        return len(self.guided_choice_uids) > 0

    def guides_tasks(self) -> bool:
        """Check if principle guides any tasks."""
        return len(self.guided_task_uids) > 0

    def is_integrated(self) -> bool:
        """Check if principle is integrated into life."""
        return (
            self.guides_goals()
            or self.inspires_habits()
            or self.guides_choices()
            or self.guides_tasks()
        )

    def has_related_principles(self) -> bool:
        """Check if principle has relationships with other principles."""
        return len(self.related_principle_uids) > 0

    def integration_score(self) -> float:
        """Calculate integration score (0.0-1.0) based on relationship counts."""
        score = 0.0
        if self.grounded_knowledge_uids:
            score += min(len(self.grounded_knowledge_uids) * 0.08, 0.20)
        if self.guided_goal_uids:
            score += min(len(self.guided_goal_uids) * 0.10, 0.25)
        if self.inspired_habit_uids:
            score += min(len(self.inspired_habit_uids) * 0.10, 0.20)
        if self.guided_choice_uids:
            score += min(len(self.guided_choice_uids) * 0.08, 0.15)
        if self.guided_task_uids:
            score += min(len(self.guided_task_uids) * 0.08, 0.20)
        return min(score, 1.0)

    def total_influence_count(self) -> int:
        """Get total count of goals, habits, choices, and tasks influenced."""
        return (
            len(self.guided_goal_uids)
            + len(self.inspired_habit_uids)
            + len(self.guided_choice_uids)
            + len(self.guided_task_uids)
        )

    def get_all_related_uids(self) -> set[str]:
        """Get all unique UIDs across all relationship types."""
        all_uids: set[str] = set()
        all_uids.update(self.grounded_knowledge_uids)
        all_uids.update(self.guided_goal_uids)
        all_uids.update(self.inspired_habit_uids)
        all_uids.update(self.related_principle_uids)
        all_uids.update(self.guided_choice_uids)
        all_uids.update(self.guided_task_uids)
        return all_uids

    def serves_life_path(self) -> bool:
        """Check if principle serves user's life path."""
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """Get the life path UID this principle serves (if any)."""
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None

    def has_event_relationship(self) -> bool:
        """Check if principle has any event relationships."""
        return len(self.demonstrating_event_uids) > 0 or len(self.practice_event_uids) > 0

    def demonstrated_at_events(self) -> bool:
        """Check if this principle was demonstrated at any events."""
        return len(self.demonstrating_event_uids) > 0

    def practiced_at_events(self) -> bool:
        """Check if this principle has practice events."""
        return len(self.practice_event_uids) > 0
