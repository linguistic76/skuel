"""
Task Relationships Helper (Graph-Native Pattern)

Container for task relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

# Type alias for backward compatibility
TasksRelationshipService = UnifiedRelationshipService


# Query specifications: (field_name, service_method_name)
# Defines the mapping between dataclass fields and service query methods
TASK_QUERY_SPECS: list[tuple[str, str]] = [
    ("subtask_uids", "subtasks"),
    ("applies_knowledge_uids", "knowledge"),
    ("aligned_principle_uids", "principles"),
    ("prerequisite_knowledge_uids", "prerequisite_knowledge"),
    ("prerequisite_task_uids", "prerequisite_tasks"),
    ("enables_task_uids", "enables"),
    ("completion_triggers_tasks", "triggers"),
    ("completion_unlocks_knowledge", "unlocks_knowledge"),
    ("inferred_knowledge_uids", "inferred_knowledge"),
    ("executed_in_event_uids", "execution_events"),
    ("implements_choice_uids", "implements_choices"),
    ("serves_life_path_uids", "life_path"),
]


@dataclass(frozen=True)
class TaskRelationships:
    """
    Container for all task relationship data (fetched from Neo4j graph).

    Usage:
        rels = await TaskRelationships.fetch(task_uid, service.relationships)
        if rels.applies_knowledge_uids:
            knowledge_score = len(rels.applies_knowledge_uids) * 0.2
    """

    subtask_uids: list[str] = field(default_factory=list)
    applies_knowledge_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)
    prerequisite_knowledge_uids: list[str] = field(default_factory=list)
    prerequisite_task_uids: list[str] = field(default_factory=list)
    enables_task_uids: list[str] = field(default_factory=list)
    completion_triggers_tasks: list[str] = field(default_factory=list)
    completion_unlocks_knowledge: list[str] = field(default_factory=list)
    inferred_knowledge_uids: list[str] = field(default_factory=list)
    executed_in_event_uids: list[str] = field(default_factory=list)
    implements_choice_uids: list[str] = field(default_factory=list)
    serves_life_path_uids: list[str] = field(default_factory=list)

    @classmethod
    async def fetch(
        cls, task_uid: str, service: TasksRelationshipService
    ) -> TaskRelationships:
        """Fetch all relationship data from graph in parallel."""
        return await fetch_relationships_parallel(
            uid=task_uid,
            service=service,
            query_specs=TASK_QUERY_SPECS,
            dataclass_type=cls,
        )

    @classmethod
    def empty(cls) -> TaskRelationships:
        """Create empty TaskRelationships (for testing or new tasks)."""
        return cls()

    def has_any_knowledge(self) -> bool:
        """Check if task has any knowledge connections."""
        return (
            len(self.applies_knowledge_uids) > 0
            or len(self.prerequisite_knowledge_uids) > 0
            or len(self.inferred_knowledge_uids) > 0
        )

    def total_knowledge_count(self) -> int:
        """Get total count of all knowledge connections."""
        return (
            len(self.applies_knowledge_uids)
            + len(self.prerequisite_knowledge_uids)
            + len(self.inferred_knowledge_uids)
        )

    def has_prerequisites(self) -> bool:
        """Check if task has any prerequisites (tasks or knowledge)."""
        return len(self.prerequisite_task_uids) > 0 or len(self.prerequisite_knowledge_uids) > 0

    def is_milestone(self) -> bool:
        """Check if task unlocks knowledge (milestone indicator)."""
        return len(self.completion_unlocks_knowledge) > 0

    def get_combined_knowledge_uids(self) -> set[str]:
        """Get all unique knowledge UIDs (explicit + inferred)."""
        all_uids: set[str] = set()
        all_uids.update(self.applies_knowledge_uids)
        all_uids.update(self.prerequisite_knowledge_uids)
        all_uids.update(self.inferred_knowledge_uids)
        return all_uids

    def has_event_execution(self) -> bool:
        """Check if task has been executed in any events."""
        return len(self.executed_in_event_uids) > 0

    def is_event_driven(self) -> bool:
        """Check if task is event-driven (executed through events)."""
        return self.has_event_execution()

    def implements_choices(self) -> bool:
        """Check if task implements any choices."""
        return len(self.implements_choice_uids) > 0

    def is_choice_driven(self) -> bool:
        """Check if task is choice-driven (created to implement a decision)."""
        return self.implements_choices()

    def serves_life_path(self) -> bool:
        """Check if task serves user's life path."""
        return len(self.serves_life_path_uids) > 0

    def get_life_path_uid(self) -> str | None:
        """Get the life path UID this task serves (if any)."""
        return self.serves_life_path_uids[0] if self.serves_life_path_uids else None
