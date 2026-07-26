"""
Event Relationships Helper (Graph-Native Pattern)

Container for event relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.ports.knowledge_pattern_protocol import compute_knowledge_intensity
from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Query specifications: (field_name, service_method_name)
# Keys must match EVENTS_CONFIG in core/models/relationship_registry.py exactly.
EVENT_QUERY_SPECS: list[tuple[str, str]] = [
    ("applies_knowledge_uids", "knowledge"),
    ("contributes_to_goal_uids", "goals"),
    ("reinforces_habit_uids", "habits"),
    ("celebrated_goal_uids", "celebrated_goals"),
    ("executed_task_uids", "tasks"),
    ("practiced_habit_uids", "practiced_habits"),
    ("conflicting_event_uids", "conflicting_events"),
    ("triggered_choice_uids", "triggered_choices"),
    ("scheduled_by_choice_uids", "scheduled_by_choices"),
    ("demonstrated_principle_uids", "demonstrated_principles"),
    ("related_event_uids", "related_events"),
]


@dataclass(frozen=True)
class EventRelationships:
    """
    Container for all event relationship data (fetched from Neo4j graph).

    Usage:
        rels = await EventRelationships.fetch(event_uid, service.relationships)
        if rels.applies_knowledge_uids:
            knowledge_score = len(rels.applies_knowledge_uids) * 0.2

    Note: ``life_path_uid`` is fetched separately (single=True in EVENTS_CONFIG)
    and excluded from the parallel batch to avoid type-mismatch with list fields.
    """

    # Outgoing: Event → Ku (APPLIES_KNOWLEDGE)
    applies_knowledge_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Goal (CONTRIBUTES_TO_GOAL)
    contributes_to_goal_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Habit (REINFORCES_HABIT)
    reinforces_habit_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Goal (CELEBRATES_GOAL)
    celebrated_goal_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Task (EXECUTES_TASK)
    executed_task_uids: list[str] = field(default_factory=list)

    # Incoming: Habit → Event (PRACTICED_AT_EVENT)
    practiced_habit_uids: list[str] = field(default_factory=list)

    # Bidirectional: Event ↔ Event (CONFLICTS_WITH)
    conflicting_event_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Choice (TRIGGERS_CHOICE)
    triggered_choice_uids: list[str] = field(default_factory=list)

    # Incoming: Choice → Event (SCHEDULES_EVENT)
    scheduled_by_choice_uids: list[str] = field(default_factory=list)

    # Outgoing: Event → Principle (DEMONSTRATES_PRINCIPLE)
    demonstrated_principle_uids: list[str] = field(default_factory=list)

    # Shared-neighbor: events sharing knowledge or goal context
    related_event_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(cls, event_uid: str, service: UnifiedRelationshipService) -> EventRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=event_uid,
            service=service,
            query_specs=EVENT_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> EventRelationships:
        """Create empty EventRelationships (for testing or new events)."""
        return cls()

    def has_any_knowledge(self) -> bool:
        """Check if event has any knowledge connections."""
        return len(self.applies_knowledge_uids) > 0

    # KnowledgeLinkedRelationships protocol --------------------------------

    @property
    def primary_knowledge_uids(self) -> list[str]:
        """Knowledge applied or explored during this event (APPLIES_KNOWLEDGE edges)."""
        return self.applies_knowledge_uids

    @property
    def secondary_knowledge_uids(self) -> list[str]:
        """Events have no secondary knowledge tier."""
        return []

    def knowledge_intensity(self) -> float:
        """0-1 score: how knowledge-rich this event is by relationship count."""
        return compute_knowledge_intensity(
            self.primary_knowledge_uids, self.secondary_knowledge_uids
        )
