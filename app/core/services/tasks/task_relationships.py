"""
Task Relationships Helper (Graph-Native Pattern)

Container for task relationship data fetched from graph.
Follows the Domain Relationships Pattern used across all activity domains.

See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.ports.knowledge_pattern_protocol import compute_knowledge_intensity
from core.services.relationships import UnifiedRelationshipService
from core.utils.generic_fetcher import fetch_relationships_parallel

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
    async def fetch(cls, task_uid: str, service: UnifiedRelationshipService) -> TaskRelationships:
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

    def get_combined_knowledge_uids(self) -> set[str]:
        """Get all unique knowledge UIDs (explicit + inferred)."""
        all_uids: set[str] = set()
        all_uids.update(self.applies_knowledge_uids)
        all_uids.update(self.prerequisite_knowledge_uids)
        all_uids.update(self.inferred_knowledge_uids)
        return all_uids

    # KnowledgeLinkedRelationships protocol --------------------------------

    @property
    def primary_knowledge_uids(self) -> list[str]:
        """Active knowledge application (APPLIES_KNOWLEDGE edges)."""
        return self.applies_knowledge_uids

    @property
    def secondary_knowledge_uids(self) -> list[str]:
        """Prerequisite and inferred knowledge connections."""
        return self.prerequisite_knowledge_uids + self.inferred_knowledge_uids

    def knowledge_intensity(self) -> float:
        """0-1 score: how knowledge-rich this task is by relationship count."""
        return compute_knowledge_intensity(
            self.primary_knowledge_uids, self.secondary_knowledge_uids
        )
