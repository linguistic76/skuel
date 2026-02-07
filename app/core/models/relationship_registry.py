"""
Relationship Registry
=====================

Single source of truth for ALL relationship configurations across domains.

**January 2026 Consolidation (ADR-026):**

THE single source of truth for relationship configurations.
All consumers call generator functions directly:
1. Graph enrichment patterns → for BaseService._graph_enrichment_patterns (via DomainConfig factories)
2. RelationshipConfig objects → for UnifiedRelationshipService (via domain_configs.py)

**Usage:**
```python
from core.models.relationship_registry import (
    generate_graph_enrichment,
    generate_relationship_config,
    UNIFIED_REGISTRY,
)

# Get graph enrichment for search services
patterns = generate_graph_enrichment("Task")

# Get full config for relationship services
config = generate_relationship_config(Domain.TASKS)
```

**Architecture:**
- UnifiedRelationshipDefinition: One relationship's complete definition
- DomainRelationshipConfig: All relationships for one domain
- UNIFIED_REGISTRY: All domains (Activity + Curriculum)

See Also:
    - /docs/decisions/ADR-026-unified-relationship-registry.md
    - /core/services/relationships/relationship_config.py - Output format
    - /core/services/base_service.py - Consumer of graph enrichment
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.relationships.relationship_config import RelationshipConfig

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO

# Curriculum domain imports - Phase 2 (January 2026)
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.lp.lp import Lp
from core.models.lp.lp_dto import LpDTO
from core.models.ls.ls import Ls
from core.models.ls.ls_dto import LearningStepDTO

# NOTE (January 2026): MOC imports removed - MOC is now KU-based.
# MOC is a KU with ORGANIZES relationships, not a separate entity.
# See /docs/domains/moc.md for the new architecture.
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.principle.reflection import PrincipleReflection
from core.models.principle.reflection_dto import PrincipleReflectionDTO
from core.models.query import QueryIntent
from core.models.relationship_names import RelationshipName
from core.models.shared_enums import Domain
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO

# =============================================================================
# UNIFIED DEFINITION DATACLASSES
# =============================================================================


@dataclass(frozen=True)
class SharedNeighborConfig:
    """
    Configuration for finding related entities through shared connections.

    Shared-neighbor patterns find entities that share intermediate connections,
    enabling "related_*" queries like:
    - Related tasks (share knowledge or goals)
    - Related goals (share contributing tasks/habits)
    - Related habits (share knowledge or goals)

    **Example Cypher Pattern:**
    ```cypher
    OPTIONAL MATCH (entity)-[:APPLIES_KNOWLEDGE|FULFILLS_GOAL]->(shared)
                  <-[:APPLIES_KNOWLEDGE|FULFILLS_GOAL]-(related:Task)
    WHERE related <> entity
    WITH entity, ...,
         collect(DISTINCT {uid: related.uid, title: related.title, shared_count: 1})[0..5] as related_tasks
    ```

    **Usage in UnifiedRelationshipDefinition:**
    ```python
    UnifiedRelationshipDefinition(
        relationship=RelationshipName.APPLIES_KNOWLEDGE,
        target_label="Task",
        direction="outgoing",
        context_field_name="related_tasks",
        method_key="related_tasks",
        shared_neighbor_config=SharedNeighborConfig(
            intermediate_relationships=(
                RelationshipName.APPLIES_KNOWLEDGE,
                RelationshipName.FULFILLS_GOAL,
            ),
            target_label="Task",
            result_alias="related_tasks",
        ),
    )
    ```

    Attributes:
        intermediate_relationships: Relationship types to traverse through shared nodes.
                                   Uses RelationshipName enum for type safety.
        target_label: Neo4j label of related entities to find (e.g., "Task", "Goal")
        result_alias: Field name in graph_context results (e.g., "related_tasks")
        result_fields: Fields to return from related entities
        limit: Maximum number of related entities to return (default: 5)
    """

    intermediate_relationships: tuple[RelationshipName, ...]
    target_label: str
    result_alias: str
    result_fields: tuple[str, ...] = ("uid", "title", "shared_count")
    limit: int = 5

    def get_relationship_pattern(self) -> str:
        """Generate the Cypher relationship pattern string (e.g., 'APPLIES_KNOWLEDGE|FULFILLS_GOAL')."""
        return "|".join(rel.value for rel in self.intermediate_relationships)


@dataclass(frozen=True)
class PostProcessor:
    """
    Post-query Python calculation for computed fields.

    Some context fields can't be computed in Cypher and need Python processing
    after the query returns. PostProcessors define these calculations.

    **Example: Milestone Progress**
    Goals have a `milestones` relationship that returns milestone data.
    The `milestone_progress` field is calculated from this data:
    ```python
    PostProcessor(
        source_field="milestones",
        target_field="milestone_progress",
        processor_name="calculate_milestone_progress",
    )
    ```

    **Available Processors:**
    Processors are registered in `core/models/query/cypher/post_processors.py`:
    - calculate_milestone_progress: Count total/completed milestones
    - (add more as needed)

    Attributes:
        source_field: Field in graph_context to read from (e.g., "milestones")
        target_field: Field to add to graph_context (e.g., "milestone_progress")
        processor_name: Name of processor function in post_processors module
    """

    source_field: str
    target_field: str
    processor_name: str


@dataclass(frozen=True)
class UnifiedRelationshipDefinition:
    """
    Complete definition of one relationship type for a domain.

    This is THE single source of truth. Both graph enrichment patterns
    and RelationshipSpec objects are generated from this.

    **Core Fields:**
    - relationship: The RelationshipName enum (type-safe)
    - target_label: Neo4j label of related nodes (e.g., "Ku", "Goal")
    - direction: "outgoing", "incoming", or "both"
    - context_field_name: Field name in _graph_context (for search enrichment)
    - method_key: Key for RelationshipConfig methods (e.g., "knowledge")

    **Context Query Fields (for get_with_context):**
    - fields: Fields to return from target nodes (default: ("uid", "title"))
    - use_confidence: Apply confidence filtering (default: False)
    - include_rel_type: Include relationship type in results (default: False)
    - single: Expect single result vs list (default: False)
    - limit: Max results to return (default: None = unlimited)

    **Edge Filtering:**
    - filter_property/filter_value: Optional edge property filtering
    - is_cross_domain_mapping: Include in cross_domain_mappings?
    - use_directional_markers: Use ->REL / <-REL markers in context

    **Shared-Neighbor Pattern (January 2026):**
    - shared_neighbor_config: Configuration for finding related entities through
      shared connections (e.g., related_tasks via shared knowledge/goals)
    """

    relationship: RelationshipName
    target_label: str
    direction: str  # "outgoing", "incoming", "both"
    context_field_name: str  # For graph enrichment (e.g., "applied_knowledge")
    method_key: str  # For RelationshipConfig (e.g., "knowledge")

    # Context query fields (for get_with_context)
    fields: tuple[str, ...] = ("uid", "title")
    use_confidence: bool = False
    include_rel_type: bool = False
    single: bool = False  # Single result vs list
    limit: int | None = None  # Max results (None = unlimited)

    # Edge filtering
    filter_property: str | None = None
    filter_value: str | None = None
    is_cross_domain_mapping: bool = True  # Include in cross_domain_mappings
    use_directional_markers: bool = False

    # Shared-neighbor pattern (for related_* queries - January 2026)
    shared_neighbor_config: SharedNeighborConfig | None = None

    # Ordering support (February 2026 - Curriculum Domains)
    # Enables ordered relationship queries (e.g., HAS_STEP ordered by sequence)
    order_by_property: str | None = None
    order_direction: str = "ASC"

    # Edge metadata (February 2026 - Curriculum Domains)
    # Specifies which edge properties to include in generated RelationshipSpec
    include_edge_properties: tuple[str, ...] = ()

    def to_graph_enrichment_tuple(self) -> tuple[str, str, str, str]:
        """Generate graph enrichment pattern tuple for BaseService._graph_enrichment_patterns."""
        return (
            self.relationship.value,
            self.target_label,
            self.context_field_name,
            self.direction,
        )

    def to_relationship_spec(self) -> dict[str, Any]:
        """
        Generate RelationshipSpec dict for build_entity_with_context().

        This is THE method that eliminates domain-specific build_*_with_context() functions.
        The returned dict matches the RelationshipSpec TypedDict format expected by
        build_entity_with_context() in domain_queries.py.

        Returns:
            Dict with keys: rel_types, target_label, alias, direction, fields,
            use_confidence, include_rel_type, single, limit
        """
        spec: dict[str, Any] = {
            "rel_types": self.relationship.value,
            "target_label": self.target_label,
            "alias": self.context_field_name,
            "direction": self.direction,
            "fields": list(self.fields),
            "use_confidence": self.use_confidence,
            "include_rel_type": self.include_rel_type,
            "single": self.single,
        }
        if self.limit is not None:
            spec["limit"] = self.limit
        return spec


@dataclass(frozen=True)
class DomainRelationshipConfig:
    """
    Complete relationship configuration for one domain.

    Contains ALL information needed to generate:
    1. Graph enrichment patterns (for BaseService search)
    2. RelationshipConfig object (for UnifiedRelationshipService)
    3. Prerequisite/enables relationships

    **Sections:**
    - Identity: domain, labels, classes
    - Relationships: unified definitions (generated from single source)
    - Semantic: semantic types for context queries
    - Scoring: weights for relevance calculations
    - Intent: query intent configuration
    """

    # Identity
    domain: Domain
    entity_label: str
    dto_class: type
    model_class: type
    backend_get_method: str = "get"

    # Ownership (None for shared content like KU)
    ownership_relationship: RelationshipName | None = None

    # All relationships - THE SINGLE SOURCE
    relationships: tuple[UnifiedRelationshipDefinition, ...] = ()

    # Prerequisite relationships (subset of relationships)
    prerequisite_relationship_names: tuple[RelationshipName, ...] = ()

    # Enables relationships (subset of relationships)
    enables_relationship_names: tuple[RelationshipName, ...] = ()

    # Bidirectional relationships
    bidirectional_relationships: tuple[RelationshipName, ...] = ()

    # Semantic types for get_with_semantic_context()
    semantic_types: tuple[SemanticRelationshipType, ...] = ()

    # Scoring weights for relevance calculations
    scoring_weights: dict[str, float] = field(default_factory=dict)

    # Intent configuration
    default_context_intent: QueryIntent = QueryIntent.HIERARCHICAL
    intent_mappings: dict[str, QueryIntent] = field(default_factory=dict)

    # Relationship creation map for batch operations
    relationship_creation_map: dict[str, tuple[RelationshipName, str, dict[str, Any] | None]] = (
        field(default_factory=dict)
    )

    # Feature flags
    use_semantic_helper: bool = True
    is_shared_content: bool = False  # True for KU, LS, LP, MOC

    # Post-query processors for calculated fields (January 2026)
    post_processors: tuple[PostProcessor, ...] = ()

    def get_outgoing_relationships(self) -> tuple[UnifiedRelationshipDefinition, ...]:
        """Get only outgoing relationships."""
        return tuple(r for r in self.relationships if r.direction == "outgoing")

    def get_incoming_relationships(self) -> tuple[UnifiedRelationshipDefinition, ...]:
        """Get only incoming relationships."""
        return tuple(r for r in self.relationships if r.direction == "incoming")

    def get_bidirectional_definitions(self) -> tuple[UnifiedRelationshipDefinition, ...]:
        """Get only bidirectional relationships."""
        return tuple(r for r in self.relationships if r.direction == "both")


# =============================================================================
# UNIFIED REGISTRY - THE SINGLE SOURCE OF TRUTH
# =============================================================================


def _build_scoring_weights(
    urgency: float = 0.0,
    dependencies: float = 0.0,
    knowledge: float = 0.0,
    goals: float = 0.0,
    habits: float = 0.0,
    tasks: float = 0.0,
    alignment: float = 0.0,
    progress: float = 0.0,
    impact: float = 0.0,
    consistency: float = 0.0,
    timing: float = 0.0,
    principles: float = 0.0,
) -> dict[str, float]:
    """Build scoring weights dict, excluding zero values."""
    weights = {
        "urgency": urgency,
        "dependencies": dependencies,
        "knowledge": knowledge,
        "goals": goals,
        "habits": habits,
        "tasks": tasks,
        "alignment": alignment,
        "progress": progress,
        "impact": impact,
        "consistency": consistency,
        "timing": timing,
        "principles": principles,
    }
    return {k: v for k, v in weights.items() if v > 0}


# -----------------------------------------------------------------------------
# TASKS
# -----------------------------------------------------------------------------
TASKS_UNIFIED = DomainRelationshipConfig(
    domain=Domain.TASKS,
    entity_label="Task",
    dto_class=TaskDTO,
    model_class=Task,
    backend_get_method="get_task",
    ownership_relationship=RelationshipName.HAS_TASK,
    relationships=(
        # Outgoing: Task → Knowledge (with confidence filtering)
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "applied_knowledge",
            "knowledge",
            use_confidence=True,  # Context: filter by confidence
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "required_knowledge",  # Renamed from prerequisite_knowledge for context consistency
            "prerequisite_knowledge",
            use_confidence=True,  # Context: filter by confidence
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ALIGNED_WITH_PRINCIPLE,
            "Principle",
            "outgoing",
            "aligned_principles",
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_TASK,
            "Task",
            "outgoing",
            "enabled_tasks",
            "enables",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERS_ON_COMPLETION,
            "Task",
            "outgoing",
            "triggered_tasks",
            "triggers",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.UNLOCKS_KNOWLEDGE,
            "Ku",
            "outgoing",
            "unlocked_knowledge",
            "unlocks_knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.CONTRIBUTES_TO_GOAL,
            "Goal",
            "outgoing",
            "contributing_goals",
            "contributes_to_goal",
        ),
        # Task → Goal: single result for context
        UnifiedRelationshipDefinition(
            RelationshipName.FULFILLS_GOAL,
            "Goal",
            "outgoing",
            "goal_context",  # Renamed for context view
            "fulfills_goal",
            fields=("uid", "title", "progress_percentage"),  # Context: include progress
            single=True,  # Context: expect single goal
        ),
        # Task → Habit: single result for context
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_HABIT,
            "Habit",
            "outgoing",
            "habit_context",  # Renamed for context view
            "supports_habit",
            fields=("uid", "title", "current_streak"),  # Context: include streak
            single=True,  # Context: expect single habit
        ),
        # Task dependencies with status/priority fields
        UnifiedRelationshipDefinition(
            RelationshipName.BLOCKED_BY,
            "Task",
            "outgoing",
            "blocked_by",
            "blocked_by",
            fields=("uid", "title", "status", "priority"),  # Context: include status/priority
            include_rel_type=True,  # Context: include relationship type
            use_directional_markers=True,
        ),
        # Incoming: Other → Task
        UnifiedRelationshipDefinition(
            RelationshipName.BLOCKED_BY,
            "Task",
            "incoming",
            "dependents",
            "dependents",
            fields=("uid", "title", "status"),  # Context: include status
            use_directional_markers=True,
        ),
        # Subtasks (incoming child relationships)
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_CHILD,
            "Task",
            "outgoing",
            "subtasks",
            "subtasks",
            fields=("uid", "title", "status", "priority"),  # Context: include status/priority
        ),
        # Dependencies (outgoing prerequisite tasks)
        UnifiedRelationshipDefinition(
            RelationshipName.DEPENDS_ON,
            "Task",
            "outgoing",
            "dependencies",
            "prerequisite_tasks",
            fields=("uid", "title", "status", "priority"),  # Context: include status/priority
            include_rel_type=True,  # Context: include relationship type
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFERRED_KNOWLEDGE,
            "Ku",
            "outgoing",
            "inferred_knowledge",
            "inferred_knowledge",
        ),
        # Incoming: Event → Task (events that executed this task)
        UnifiedRelationshipDefinition(
            RelationshipName.EXECUTES_TASK,
            "Event",
            "incoming",
            "execution_events",
            "execution_events",
            fields=("uid", "title", "start_time"),
        ),
        # Outgoing: Task → Choice (choices implemented by this task)
        UnifiedRelationshipDefinition(
            RelationshipName.IMPLEMENTS_CHOICE,
            "Choice",
            "outgoing",
            "implemented_choices",
            "implements_choices",
            fields=("uid", "title", "status"),
        ),
        # Outgoing: Task → LifePath (task serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Shared-neighbor pattern: Related tasks via shared knowledge or goals
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,  # Placeholder - uses shared_neighbor_config
            "Task",
            "both",
            "related_tasks",
            "related_tasks",
            fields=("uid", "title", "status"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.APPLIES_KNOWLEDGE,
                    RelationshipName.FULFILLS_GOAL,
                ),
                target_label="Task",
                result_alias="related_tasks",
                result_fields=("uid", "title", "status", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(
        RelationshipName.BLOCKED_BY,
        RelationshipName.REQUIRES_TASK,
    ),
    enables_relationship_names=(
        RelationshipName.BLOCKS,
        RelationshipName.ENABLES_TASK,
    ),
    bidirectional_relationships=(RelationshipName.DEPENDS_ON,),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL,
        SemanticRelationshipType.PROVIDES_PRACTICAL_APPLICATION,
    ),
    scoring_weights=_build_scoring_weights(
        urgency=0.3, dependencies=0.4, knowledge=0.3, goals=0.4, habits=0.3, tasks=0.1
    ),
    default_context_intent=QueryIntent.PREREQUISITE,
    intent_mappings={
        "context": QueryIntent.PREREQUISITE,
        "dependencies": QueryIntent.PREREQUISITE,
        "impact": QueryIntent.HIERARCHICAL,
        "practice": QueryIntent.PRACTICE,
    },
)

# -----------------------------------------------------------------------------
# GOALS
# -----------------------------------------------------------------------------
GOALS_UNIFIED = DomainRelationshipConfig(
    domain=Domain.GOALS,
    entity_label="Goal",
    dto_class=GoalDTO,
    model_class=Goal,
    backend_get_method="get",
    ownership_relationship=RelationshipName.HAS_GOAL,
    relationships=(
        # Outgoing: Goal → Knowledge (with confidence filtering)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "required_knowledge",
            "knowledge",
            use_confidence=True,  # Context: filter by confidence
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDED_BY_PRINCIPLE,
            "Principle",
            "outgoing",
            "aligned_principles",  # Context name: aligned_principles
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ALIGNED_WITH_PATH,
            "Lp",
            "outgoing",
            "aligned_paths",
            "aligned_paths",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_PATH_COMPLETION,
            "Lp",
            "outgoing",
            "required_paths",
            "required_paths",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUBGOAL_OF,
            "Goal",
            "outgoing",
            "parent_goal",
            "parent_goal",
            fields=("uid", "title", "progress_percentage"),
            single=True,  # Single parent goal, not a list
        ),
        # Choice that inspired this goal
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRED_BY_CHOICE,
            "Choice",
            "outgoing",
            "inspired_by_choice",
            "inspired_by_choice",
            fields=("uid", "title"),
            single=True,  # Single choice
        ),
        # Incoming: Other → Goal (with context-specific fields)
        UnifiedRelationshipDefinition(
            RelationshipName.SUBGOAL_OF,
            "Goal",
            "incoming",
            "sub_goals",
            "subgoals",
            fields=(
                "uid",
                "title",
                "status",
                "progress_percentage",
            ),  # Context: include status/progress
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Habit",
            "incoming",
            "contributing_habits",  # Context name: contributing_habits
            "supporting_habits",
            fields=("uid", "title", "current_streak"),  # Context: include streak
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.FULFILLS_GOAL,
            "Task",
            "incoming",
            "contributing_tasks",  # Context name: contributing_tasks
            "fulfilling_tasks",
            fields=("uid", "title", "status", "priority"),  # Context: include status/priority
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_MILESTONE,
            "Milestone",  # Target is Milestone, not Goal
            "outgoing",
            "milestones",
            "milestones",
            fields=(
                "uid",
                "title",
                "is_completed",
                "target_date",
                "order",
            ),  # Context: milestone fields
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_GOAL,
            "Principle",
            "incoming",
            "guiding_principles_incoming",
            "guided_by_principles",
        ),
        # Essentiality-filtered habits
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Habit",
            "incoming",
            "essential_habits",
            "essential_habits",
            filter_property="essentiality",
            filter_value="essential",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Habit",
            "incoming",
            "critical_habits",
            "critical_habits",
            filter_property="essentiality",
            filter_value="critical",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Habit",
            "incoming",
            "optional_habits",
            "optional_habits",
            filter_property="essentiality",
            filter_value="optional",
        ),
        # Outgoing: Goal → LifePath (goal serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Shared-neighbor pattern: Related goals via shared contributors (tasks, habits)
        UnifiedRelationshipDefinition(
            RelationshipName.FULFILLS_GOAL,  # Placeholder - uses shared_neighbor_config
            "Goal",
            "both",
            "related_goals",
            "related_goals",
            fields=("uid", "title", "status"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.FULFILLS_GOAL,
                    RelationshipName.SUPPORTS_GOAL,
                ),
                target_label="Goal",
                result_alias="related_goals",
                result_fields=("uid", "title", "status", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(
        RelationshipName.REQUIRES_KNOWLEDGE,
        RelationshipName.DEPENDS_ON_GOAL,
    ),
    enables_relationship_names=(RelationshipName.ENABLES_GOAL,),
    bidirectional_relationships=(RelationshipName.SUBGOAL_OF,),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
        SemanticRelationshipType.CONTRIBUTES_TO_GOAL,
        SemanticRelationshipType.ENABLES_ACHIEVEMENT,
    ),
    scoring_weights=_build_scoring_weights(
        alignment=0.5, progress=0.3, impact=0.2, goals=0.4, habits=0.3, knowledge=0.2, tasks=0.1
    ),
    default_context_intent=QueryIntent.GOAL_ACHIEVEMENT,
    intent_mappings={
        "context": QueryIntent.GOAL_ACHIEVEMENT,
        "achievement": QueryIntent.GOAL_ACHIEVEMENT,
        "impact": QueryIntent.HIERARCHICAL,
    },
    # Post-query processors for calculated fields
    post_processors=(
        PostProcessor(
            source_field="milestones",
            target_field="milestone_progress",
            processor_name="calculate_milestone_progress",
        ),
    ),
)

# -----------------------------------------------------------------------------
# HABITS
# -----------------------------------------------------------------------------
HABITS_UNIFIED = DomainRelationshipConfig(
    domain=Domain.HABITS,
    entity_label="Habit",
    dto_class=HabitDTO,
    model_class=Habit,
    backend_get_method="get_habit",
    ownership_relationship=RelationshipName.HAS_HABIT,
    relationships=(
        # Outgoing: Habit → Other (with context-specific fields)
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "reinforced_knowledge",
            "knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.EMBODIES_PRINCIPLE,
            "Principle",
            "outgoing",
            "embodied_principles",
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Goal",
            "outgoing",
            "supported_goals",
            "supported_goals",
            fields=("uid", "title", "progress_percentage"),  # Context: include progress
        ),
        # Incoming: Other → Habit
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_PREREQUISITE_HABIT,
            "Habit",
            "outgoing",
            "prerequisite_habits",
            "prerequisite_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_HABIT,
            "Habit",
            "incoming",
            "reinforcing_habits",
            "reinforcing_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_HABIT,
            "Habit",
            "incoming",
            "enabling_habits",
            "enabling_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRES_HABIT,
            "Principle",
            "incoming",
            "inspiring_principles",
            "inspiring_principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_HABIT,
            "Event",
            "incoming",
            "reinforcing_events",
            "reinforcing_events",
        ),
        # Task → Habit (reinforcing tasks)
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_HABIT,
            "Task",
            "incoming",
            "reinforcing_tasks",
            "reinforcing_tasks",
            fields=("uid", "title", "status"),  # Context: include status
        ),
        # Related habits (bidirectional)
        UnifiedRelationshipDefinition(
            RelationshipName.RELATED_TO,
            "Habit",
            "both",
            "related_habits",
            "related_habits",
            fields=("uid", "title", "current_streak"),  # Context: include streak
        ),
        # Outgoing: Habit → LifePath (habit serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Habit ↔ Choice bidirectional relationships (January 2026)
        # Outgoing: Habit informs choices
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMS_CHOICE,
            "Choice",
            "outgoing",
            "informed_choices",
            "informed_choices",
            fields=("uid", "title", "status"),
        ),
        # Incoming: Choice impacts habit
        UnifiedRelationshipDefinition(
            RelationshipName.IMPACTS_HABIT,
            "Choice",
            "incoming",
            "impacting_choices",
            "impacting_choices",
            fields=("uid", "title", "status"),
        ),
        # Shared-neighbor pattern: Related habits via shared knowledge or goals
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_KNOWLEDGE,  # Placeholder - uses shared_neighbor_config
            "Habit",
            "both",
            "related_habits_shared",
            "related_habits_shared",
            fields=("uid", "title", "current_streak"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.REINFORCES_KNOWLEDGE,
                    RelationshipName.SUPPORTS_GOAL,
                ),
                target_label="Habit",
                result_alias="related_habits_shared",
                result_fields=("uid", "title", "current_streak", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.REQUIRES_PREREQUISITE_HABIT,),
    enables_relationship_names=(RelationshipName.ENABLES_HABIT,),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.REINFORCES_KNOWLEDGE,
        SemanticRelationshipType.PROVIDES_PRACTICAL_APPLICATION,
        SemanticRelationshipType.DEVELOPS_SKILL,
    ),
    scoring_weights=_build_scoring_weights(consistency=0.4, goals=0.3, knowledge=0.2, habits=0.1),
    default_context_intent=QueryIntent.PRACTICE,
    intent_mappings={
        "context": QueryIntent.PRACTICE,
        "practice": QueryIntent.PRACTICE,
        "impact": QueryIntent.HIERARCHICAL,
    },
)

# -----------------------------------------------------------------------------
# EVENTS
# -----------------------------------------------------------------------------
EVENTS_UNIFIED = DomainRelationshipConfig(
    domain=Domain.EVENTS,
    entity_label="Event",
    dto_class=EventDTO,
    model_class=Event,
    backend_get_method="get_event",
    ownership_relationship=RelationshipName.HAS_EVENT,
    relationships=(
        # Outgoing: Event → Other
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "applied_knowledge",
            "knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.CONTRIBUTES_TO_GOAL,
            "Goal",
            "outgoing",
            "supported_goals",
            "goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_HABIT,
            "Habit",
            "outgoing",
            "reinforced_habits",
            "habits",
        ),
        # Outgoing: Event → Task (tasks executed in this event)
        UnifiedRelationshipDefinition(
            RelationshipName.EXECUTES_TASK,
            "Task",
            "outgoing",
            "executed_tasks",
            "tasks",
            fields=("uid", "title", "status", "priority"),
        ),
        # Incoming: Other → Event
        UnifiedRelationshipDefinition(
            RelationshipName.PRACTICED_AT_EVENT,
            "Habit",
            "incoming",
            "practiced_habits",
            "practiced_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.CELEBRATED_BY_EVENT,
            "Goal",
            "incoming",
            "celebrated_goals",
            "celebrated_goals",
        ),
        # Bidirectional
        UnifiedRelationshipDefinition(
            RelationshipName.CONFLICTS_WITH,
            "Event",
            "both",
            "conflicting_events",
            "conflicting_events",
        ),
        # Outgoing: Event → LifePath (event serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Event ↔ Choice bidirectional relationships (January 2026)
        # Outgoing: Event triggers choice
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERS_CHOICE,
            "Choice",
            "outgoing",
            "triggered_choices",
            "triggered_choices",
            fields=("uid", "title", "status"),
        ),
        # Incoming: Choice schedules event
        UnifiedRelationshipDefinition(
            RelationshipName.SCHEDULES_EVENT,
            "Choice",
            "incoming",
            "scheduled_by_choices",
            "scheduled_by_choices",
            fields=("uid", "title", "status"),
        ),
        # Event ↔ Principle bidirectional relationships (January 2026)
        # Outgoing: Event demonstrates principle
        UnifiedRelationshipDefinition(
            RelationshipName.DEMONSTRATES_PRINCIPLE,
            "Principle",
            "outgoing",
            "demonstrated_principles",
            "demonstrated_principles",
            fields=("uid", "title", "strength"),
        ),
        # Shared-neighbor pattern: Related events via shared knowledge or goals
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,  # Placeholder - uses shared_neighbor_config
            "Event",
            "both",
            "related_events",
            "related_events",
            fields=("uid", "title", "start_time"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.APPLIES_KNOWLEDGE,
                    RelationshipName.CONTRIBUTES_TO_GOAL,
                ),
                target_label="Event",
                result_alias="related_events",
                result_fields=("uid", "title", "start_time", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.REQUIRES_KNOWLEDGE,),
    enables_relationship_names=(),
    bidirectional_relationships=(RelationshipName.CONFLICTS_WITH,),
    semantic_types=(
        SemanticRelationshipType.PROVIDES_PRACTICAL_APPLICATION,
        SemanticRelationshipType.DEEPENS_UNDERSTANDING,
    ),
    scoring_weights=_build_scoring_weights(timing=0.4, goals=0.3, knowledge=0.2, habits=0.1),
    default_context_intent=QueryIntent.PRACTICE,
    intent_mappings={
        "context": QueryIntent.PRACTICE,
        "impact": QueryIntent.HIERARCHICAL,
    },
)

# -----------------------------------------------------------------------------
# CHOICES
# -----------------------------------------------------------------------------
CHOICES_UNIFIED = DomainRelationshipConfig(
    domain=Domain.CHOICES,
    entity_label="Choice",
    dto_class=ChoiceDTO,
    model_class=Choice,
    backend_get_method="get_choice",
    ownership_relationship=RelationshipName.HAS_CHOICE,
    relationships=(
        # Outgoing: Choice → Other
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMED_BY_KNOWLEDGE,
            "Ku",
            "outgoing",
            "informed_by_knowledge",
            "knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMED_BY_PRINCIPLE,
            "Principle",
            "outgoing",
            "aligned_principles",
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.AFFECTS_GOAL,
            "Goal",
            "outgoing",
            "affected_goals",
            "goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.OPENS_LEARNING_PATH,
            "Lp",
            "outgoing",
            "opened_paths",
            "learning_paths",
        ),
        # Incoming: Other → Choice
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRED_BY_CHOICE,
            "Choice",
            "incoming",
            "inspired_choices",
            "inspired_choices",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.IMPLEMENTS_CHOICE,
            "Task",
            "incoming",
            "implementing_tasks",
            "implementing_tasks",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_CHOICE,
            "Principle",
            "incoming",
            "guiding_principles",
            "guided_by_principles",
        ),
        # Outgoing: Choice → LifePath (choice serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Choice ↔ Habit bidirectional relationships (January 2026)
        # Outgoing: Choice impacts habit
        UnifiedRelationshipDefinition(
            RelationshipName.IMPACTS_HABIT,
            "Habit",
            "outgoing",
            "impacted_habits",
            "impacted_habits",
            fields=("uid", "title", "current_streak"),
        ),
        # Incoming: Habit informs choice
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMS_CHOICE,
            "Habit",
            "incoming",
            "informing_habits",
            "informing_habits",
            fields=("uid", "title", "current_streak"),
        ),
        # Choice ↔ Event bidirectional relationships (January 2026)
        # Outgoing: Choice schedules event
        UnifiedRelationshipDefinition(
            RelationshipName.SCHEDULES_EVENT,
            "Event",
            "outgoing",
            "scheduled_events",
            "scheduled_events",
            fields=("uid", "title", "start_time"),
        ),
        # Incoming: Event triggers choice
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERS_CHOICE,
            "Event",
            "incoming",
            "triggering_events",
            "triggering_events",
            fields=("uid", "title", "start_time"),
        ),
        # Shared-neighbor pattern: Related choices via shared principles or goals
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMED_BY_PRINCIPLE,  # Placeholder - uses shared_neighbor_config
            "Choice",
            "both",
            "related_choices",
            "related_choices",
            fields=("uid", "title", "status"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.INFORMED_BY_PRINCIPLE,
                    RelationshipName.AFFECTS_GOAL,
                ),
                target_label="Choice",
                result_alias="related_choices",
                result_fields=("uid", "title", "status", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.REQUIRES_KNOWLEDGE_FOR_DECISION,),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.INFORMED_BY_KNOWLEDGE,
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
    ),
    scoring_weights=_build_scoring_weights(principles=0.4, knowledge=0.3, goals=0.2, habits=0.1),
    default_context_intent=QueryIntent.HIERARCHICAL,
    intent_mappings={
        "context": QueryIntent.HIERARCHICAL,
        "impact": QueryIntent.HIERARCHICAL,
    },
)

# -----------------------------------------------------------------------------
# PRINCIPLES
# -----------------------------------------------------------------------------
PRINCIPLES_UNIFIED = DomainRelationshipConfig(
    domain=Domain.PRINCIPLES,
    entity_label="Principle",
    dto_class=PrincipleDTO,
    model_class=Principle,
    backend_get_method="get_principle",
    ownership_relationship=RelationshipName.HAS_PRINCIPLE,
    relationships=(
        # Outgoing: Principle → Other
        UnifiedRelationshipDefinition(
            RelationshipName.GROUNDED_IN_KNOWLEDGE,
            "Ku",
            "outgoing",
            "grounding_knowledge",
            "knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_GOAL,
            "Goal",
            "outgoing",
            "guided_goals",
            "guided_goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_CHOICE,
            "Choice",
            "outgoing",
            "guided_choices",
            "guided_choices",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRES_HABIT,
            "Habit",
            "outgoing",
            "inspired_habits",
            "inspired_habits",
        ),
        # Incoming: Other → Principle
        UnifiedRelationshipDefinition(
            RelationshipName.EMBODIES_PRINCIPLE,
            "Habit",
            "incoming",
            "embodying_habits",
            "embodying_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_PRINCIPLE,
            "Principle",
            "incoming",
            "supporting_principles",
            "supporting_principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.CONFLICTS_WITH_PRINCIPLE,
            "Principle",
            "incoming",
            "conflicting_principles",
            "conflicting_principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ALIGNED_WITH_PRINCIPLE,
            "Task",
            "incoming",
            "aligned_tasks",
            "aligned_tasks",
        ),
        # Bidirectional
        UnifiedRelationshipDefinition(
            RelationshipName.RELATED_TO,
            "Principle",
            "both",
            "related_principles",
            "related_principles",
        ),
        # Principle ↔ Event bidirectional relationships (January 2026)
        # Incoming: Event demonstrates principle
        UnifiedRelationshipDefinition(
            RelationshipName.DEMONSTRATES_PRINCIPLE,
            "Event",
            "incoming",
            "demonstrating_events",
            "demonstrating_events",
            fields=("uid", "title", "start_time"),
        ),
        # Outgoing: Principle practiced at event
        UnifiedRelationshipDefinition(
            RelationshipName.PRACTICED_AT_EVENT,
            "Event",
            "outgoing",
            "practice_events",
            "practice_events",
            fields=("uid", "title", "start_time"),
        ),
        # Outgoing: Principle → LifePath (principle serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Lp",
            "outgoing",
            "life_path",
            "life_path",
            fields=("uid", "title"),
            single=True,
        ),
        # Shared-neighbor pattern: Related principles via shared goals or knowledge
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_GOAL,  # Placeholder - uses shared_neighbor_config
            "Principle",
            "both",
            "related_principles_shared",
            "related_principles_shared",
            fields=("uid", "title", "strength"),
            limit=5,
            shared_neighbor_config=SharedNeighborConfig(
                intermediate_relationships=(
                    RelationshipName.GUIDES_GOAL,
                    RelationshipName.GROUNDED_IN_KNOWLEDGE,
                ),
                target_label="Principle",
                result_alias="related_principles_shared",
                result_fields=("uid", "title", "strength", "shared_count"),
                limit=5,
            ),
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.GROUNDED_IN_KNOWLEDGE,),
    enables_relationship_names=(
        RelationshipName.GUIDES_GOAL,
        RelationshipName.INSPIRES_HABIT,
        RelationshipName.GUIDES_CHOICE,
    ),
    bidirectional_relationships=(
        RelationshipName.SUPPORTS_PRINCIPLE,
        RelationshipName.CONFLICTS_WITH_PRINCIPLE,
    ),
    semantic_types=(
        SemanticRelationshipType.BUILDS_ON_FOUNDATION,
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
    ),
    scoring_weights=_build_scoring_weights(alignment=0.5, goals=0.3, knowledge=0.2),
    default_context_intent=QueryIntent.HIERARCHICAL,
    intent_mappings={
        "context": QueryIntent.HIERARCHICAL,
        "impact": QueryIntent.HIERARCHICAL,
    },
)

# -----------------------------------------------------------------------------
# USER (Identity Layer - Minimal Config for Relationship Validation)
# User is the identity layer, not a domain entity. This minimal config
# enables validation of User -> Entity relationships like MADE_REFLECTION.
# -----------------------------------------------------------------------------

USER_UNIFIED = DomainRelationshipConfig(
    domain=Domain.SYSTEM,  # User is part of system infrastructure
    entity_label="User",
    dto_class=None,  # User has its own DTO system
    model_class=None,  # User has its own model system
    backend_get_method="get",
    ownership_relationship=None,  # User doesn't have ownership
    relationships=(
        # User creates reflections on principles
        UnifiedRelationshipDefinition(
            RelationshipName.MADE_REFLECTION,
            "PrincipleReflection",
            "outgoing",
            "reflections",
            "reflections",
        ),
        # User owns Activity Domain entities (HAS_*)
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_TASK,
            "Task",
            "outgoing",
            "tasks",
            "tasks",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_GOAL,
            "Goal",
            "outgoing",
            "goals",
            "goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_HABIT,
            "Habit",
            "outgoing",
            "habits",
            "habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_EVENT,
            "Event",
            "outgoing",
            "events",
            "events",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_CHOICE,
            "Choice",
            "outgoing",
            "choices",
            "choices",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_PRINCIPLE,
            "Principle",
            "outgoing",
            "principles",
            "principles",
        ),
    ),
    prerequisite_relationship_names=(),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(),
    scoring_weights=_build_scoring_weights(),
    default_context_intent=QueryIntent.SPECIFIC,
    intent_mappings={},
)

# -----------------------------------------------------------------------------
# PRINCIPLE REFLECTION (January 2026 - Graph-Connected Reflections)
# Reflections track alignment between user actions and their principles
# -----------------------------------------------------------------------------

PRINCIPLE_REFLECTION_UNIFIED = DomainRelationshipConfig(
    domain=Domain.PRINCIPLES,  # Part of Principles domain
    entity_label="PrincipleReflection",
    dto_class=PrincipleReflectionDTO,
    model_class=PrincipleReflection,
    backend_get_method="get",
    ownership_relationship=RelationshipName.MADE_REFLECTION,
    relationships=(
        # Outgoing: PrincipleReflection → Principle
        UnifiedRelationshipDefinition(
            RelationshipName.REFLECTS_ON,
            "Principle",
            "outgoing",
            "reflected_principle",
            "principle",
        ),
        # Outgoing: PrincipleReflection → Trigger Entity (Goal/Habit/Event/Choice)
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERED_BY,
            "Goal",
            "outgoing",
            "trigger_goal",
            "trigger",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERED_BY,
            "Habit",
            "outgoing",
            "trigger_habit",
            "trigger",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERED_BY,
            "Event",
            "outgoing",
            "trigger_event",
            "trigger",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.TRIGGERED_BY,
            "Choice",
            "outgoing",
            "trigger_choice",
            "trigger",
        ),
        # Outgoing: PrincipleReflection → Principle (conflict revelation)
        UnifiedRelationshipDefinition(
            RelationshipName.REVEALS_CONFLICT,
            "Principle",
            "outgoing",
            "conflicting_principles",
            "conflicts",
        ),
        # Incoming: User → PrincipleReflection
        UnifiedRelationshipDefinition(
            RelationshipName.MADE_REFLECTION,
            "User",
            "incoming",
            "creator",
            "user",
        ),
    ),
    prerequisite_relationship_names=(),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(),
    scoring_weights=_build_scoring_weights(),
    default_context_intent=QueryIntent.SPECIFIC,
    intent_mappings={},
)

# -----------------------------------------------------------------------------
# CURRICULUM DOMAINS (Shared Content - No User Ownership)
# Phase 2 Complete - January 2026
# -----------------------------------------------------------------------------

# KU (Knowledge Unit)
KU_UNIFIED = DomainRelationshipConfig(
    domain=Domain.KNOWLEDGE,
    entity_label="Ku",
    dto_class=KuDTO,
    model_class=Ku,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Ku → Ku (prerequisites with confidence)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "prerequisites",
            "requires",
            use_confidence=True,  # Context: filter by confidence
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "enables_learning",
            "enables",
        ),
        # Incoming: Other Ku → This Ku (dependents)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "incoming",
            "dependents",
            "required_by",
        ),
        # Related KUs (bidirectional)
        UnifiedRelationshipDefinition(
            RelationshipName.RELATED_TO,
            "Ku",
            "both",
            "related",
            "related",
        ),
        # Incoming: Activity domains applying knowledge
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,
            "Task",
            "incoming",
            "applied_in_tasks",
            "applied_in_tasks",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_KNOWLEDGE,
            "Habit",
            "incoming",
            "reinforced_by_habits",
            "reinforced_by_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Goal",
            "incoming",
            "supports_goals",
            "supports_goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMED_BY_KNOWLEDGE,
            "Choice",
            "incoming",
            "informs_choices",
            "informs_choices",
        ),
        # Curriculum relationships
        UnifiedRelationshipDefinition(
            RelationshipName.CONTAINS_KNOWLEDGE,
            "Ls",
            "incoming",
            "in_learning_steps",
            "in_steps",
        ),
        # Incoming: enables (other KU enables this KU)
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_KNOWLEDGE,
            "Ku",
            "incoming",
            "enabled_by_kus",
            "enabled_by",
        ),
        # MOC Navigation (January 2026 - KU-based MOC)
        # A KU "is" a MOC when it has outgoing ORGANIZES relationships
        UnifiedRelationshipDefinition(
            RelationshipName.ORGANIZES,
            "Ku",
            "outgoing",
            "organized_children",
            "organizes",
            order_by_property="order",
            order_direction="ASC",
            include_edge_properties=("order",),
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ORGANIZES,
            "Ku",
            "incoming",
            "organized_by",
            "organized_by",
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.REQUIRES_KNOWLEDGE,),
    enables_relationship_names=(RelationshipName.ENABLES_KNOWLEDGE,),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_ON_FOUNDATION,
    ),
    scoring_weights=_build_scoring_weights(knowledge=0.5, goals=0.3, tasks=0.2),
    default_context_intent=QueryIntent.PREREQUISITE,
    intent_mappings={
        "context": QueryIntent.PREREQUISITE,
        "learning": QueryIntent.HIERARCHICAL,
    },
)

# LS (Learning Step)
LS_UNIFIED = DomainRelationshipConfig(
    domain=Domain.LEARNING,
    entity_label="Ls",
    dto_class=LearningStepDTO,
    model_class=Ls,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Ls → Other
        UnifiedRelationshipDefinition(
            RelationshipName.CONTAINS_KNOWLEDGE,
            "Ku",
            "outgoing",
            "knowledge_units",
            "knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_STEP,
            "Ls",
            "outgoing",
            "prerequisites",
            "prerequisite_steps",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "prerequisite_knowledge_units",
            "prerequisite_knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDED_BY_PRINCIPLE,
            "Principle",
            "outgoing",
            "guiding_principles",
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMS_CHOICE,
            "Choice",
            "outgoing",
            "informed_choices",
            "choices",
        ),
        # Practice patterns
        UnifiedRelationshipDefinition(
            RelationshipName.BUILDS_HABIT,
            "Habit",
            "outgoing",
            "builds_habits",
            "practice_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ASSIGNS_TASK,
            "Task",
            "outgoing",
            "assigned_tasks",
            "practice_tasks",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SCHEDULES_EVENT,
            "Event",
            "outgoing",
            "scheduled_events",
            "practice_events",
        ),
        # Incoming: Other → Ls
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_STEP,
            "Lp",
            "incoming",
            "learning_paths",
            "in_paths",
        ),
    ),
    prerequisite_relationship_names=(
        RelationshipName.REQUIRES_STEP,
        RelationshipName.REQUIRES_KNOWLEDGE,
    ),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.PROVIDES_PRACTICAL_APPLICATION,
    ),
    scoring_weights=_build_scoring_weights(knowledge=0.4, goals=0.3, habits=0.2, tasks=0.1),
    default_context_intent=QueryIntent.PREREQUISITE,
    intent_mappings={
        "context": QueryIntent.PREREQUISITE,
        "practice": QueryIntent.PRACTICE,
    },
)

# LP (Learning Path)
LP_UNIFIED = DomainRelationshipConfig(
    domain=Domain.LEARNING,
    entity_label="Lp",
    dto_class=LpDTO,
    model_class=Lp,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Lp → Other
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_STEP,
            "Ls",
            "outgoing",
            "learning_steps",
            "steps",
            order_by_property="sequence",
            order_direction="ASC",
            include_edge_properties=("sequence", "completed"),
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Ku",
            "outgoing",
            "required_knowledge",
            "prerequisites",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ALIGNED_WITH_GOAL,
            "Goal",
            "outgoing",
            "aligned_goals",
            "goals",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.EMBODIES_PRINCIPLE,
            "Principle",
            "outgoing",
            "embodied_principles",
            "principles",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_MILESTONE_EVENT,
            "Event",
            "outgoing",
            "milestone_events",
            "milestones",
        ),
        # Incoming: Other → Lp
        UnifiedRelationshipDefinition(
            RelationshipName.OPENS_LEARNING_PATH,
            "Choice",
            "incoming",
            "opened_by_choices",
            "opened_by",
        ),
    ),
    prerequisite_relationship_names=(
        RelationshipName.REQUIRES_KNOWLEDGE,
        RelationshipName.REQUIRES_STEP,
    ),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.ENABLES_ACHIEVEMENT,
    ),
    scoring_weights=_build_scoring_weights(knowledge=0.4, goals=0.4, alignment=0.2),
    default_context_intent=QueryIntent.PREREQUISITE,
    intent_mappings={
        "context": QueryIntent.PREREQUISITE,
        "achievement": QueryIntent.GOAL_ACHIEVEMENT,
    },
)

# =============================================================================
# NOTE (January 2026): MOC_UNIFIED and MOC_SECTION_UNIFIED REMOVED
# =============================================================================
# MOC is now KU-based - not a separate entity type.
# A KU "is" a MOC when it has outgoing ORGANIZES relationships.
# The KU config includes ORGANIZES relationship for MOC functionality.
# See /docs/domains/moc.md and /core/services/moc_service.py


# =============================================================================
# UNIFIED REGISTRY - ALL DOMAINS (Phase 1 + Phase 2 Complete)
# =============================================================================
# Note: Finance domain is standalone (no unified relationship registry)
# Finance is a bookkeeping domain, not an Activity domain

UNIFIED_REGISTRY: dict[Domain, DomainRelationshipConfig] = {
    # Activity Domains (6) - User-owned entities
    Domain.TASKS: TASKS_UNIFIED,
    Domain.GOALS: GOALS_UNIFIED,
    Domain.HABITS: HABITS_UNIFIED,
    Domain.EVENTS: EVENTS_UNIFIED,
    Domain.CHOICES: CHOICES_UNIFIED,
    Domain.PRINCIPLES: PRINCIPLES_UNIFIED,
    # Note: Finance is standalone (not in unified registry)
    # Curriculum Domains - Shared content (Phase 2)
    # Note: KU and MOC both use Domain.KNOWLEDGE, LS and LP both use Domain.LEARNING
    # Use UNIFIED_REGISTRY_BY_LABEL for unambiguous lookup
    Domain.KNOWLEDGE: KU_UNIFIED,  # Primary for Domain.KNOWLEDGE
    Domain.LEARNING: LS_UNIFIED,  # Primary for Domain.LEARNING
}

# Label-based lookup (THE authoritative way to get curriculum configs)
UNIFIED_REGISTRY_BY_LABEL: dict[str, DomainRelationshipConfig] = {
    # Activity Domains (6)
    "Task": TASKS_UNIFIED,
    "Goal": GOALS_UNIFIED,
    "Habit": HABITS_UNIFIED,
    "Event": EVENTS_UNIFIED,
    "Choice": CHOICES_UNIFIED,
    "Principle": PRINCIPLES_UNIFIED,
    # Note: Finance/Expense is standalone (not in unified registry)
    # User (Identity Layer - January 2026)
    "User": USER_UNIFIED,
    # Principle Reflection (January 2026)
    "PrincipleReflection": PRINCIPLE_REFLECTION_UNIFIED,
    # Curriculum Domains (3) - MOC removed (now KU-based, January 2026)
    "Ku": KU_UNIFIED,
    "Ls": LS_UNIFIED,
    "Lp": LP_UNIFIED,
    # Note: MapOfContent and MOCSection removed - MOC is now KU with ORGANIZES relationships
}


# =============================================================================
# GENERATOR FUNCTIONS
# =============================================================================


def generate_graph_enrichment(entity_label: str) -> list[tuple[str, str, str, str]]:
    """
    Generate graph enrichment patterns for BaseService._graph_enrichment_patterns.

    Args:
        entity_label: Neo4j node label (e.g., "Task", "Ku", "Lp")

    Returns:
        List of tuples: (relationship_type, target_label, context_field, direction)
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(entity_label)
    if not config:
        return []

    return [rel.to_graph_enrichment_tuple() for rel in config.relationships]


def generate_prerequisite_relationships(entity_label: str) -> list[str]:
    """
    Generate prerequisite relationship types for BaseService.

    Args:
        entity_label: Neo4j node label

    Returns:
        List of relationship type strings
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(entity_label)
    if not config:
        return []

    return [rel.value for rel in config.prerequisite_relationship_names]


def generate_enables_relationships(entity_label: str) -> list[str]:
    """
    Generate enables relationship types for BaseService.

    Args:
        entity_label: Neo4j node label

    Returns:
        List of relationship type strings
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(entity_label)
    if not config:
        return []

    return [rel.value for rel in config.enables_relationship_names]


def _generate_from_config(config: DomainRelationshipConfig) -> "RelationshipConfig":
    """
    Generate a RelationshipConfig from a DomainRelationshipConfig.

    Core logic shared by generate_relationship_config() and
    generate_relationship_config_by_label().
    """
    from core.services.relationships.relationship_config import (
        CrossDomainMapping,
        RelationshipConfig,
        RelationshipSpec,
    )

    # Build outgoing/incoming relationships dicts
    outgoing: dict[str, RelationshipSpec] = {}
    incoming: dict[str, RelationshipSpec] = {}

    for rel in config.relationships:
        spec = RelationshipSpec(
            relationship=rel.relationship,
            direction=rel.direction,
            filter_property=rel.filter_property,
            filter_value=rel.filter_value,
            order_by_property=rel.order_by_property,
            order_direction=rel.order_direction,
            include_edge_properties=rel.include_edge_properties,
        )
        if rel.direction == "outgoing":
            outgoing[rel.method_key] = spec
        elif rel.direction == "incoming":
            incoming[rel.method_key] = spec
        elif rel.direction == "both":
            # Bidirectional goes in outgoing (convention)
            outgoing[rel.method_key] = spec

    # Build cross-domain mappings
    cross_domain_mappings: list[CrossDomainMapping] = [
        CrossDomainMapping(
            category_name=rel.context_field_name,
            target_label=rel.target_label,
            via_relationships=[rel.relationship],
            use_directional_markers=rel.use_directional_markers,
        )
        for rel in config.relationships
        if rel.is_cross_domain_mapping
    ]

    # Build cross-domain relationship types list
    cross_domain_types = list({rel.relationship.value for rel in config.relationships})

    return RelationshipConfig(
        domain=config.domain,
        entity_label=config.entity_label,
        dto_class=config.dto_class,
        model_class=config.model_class,
        backend_get_method=config.backend_get_method,
        use_semantic_helper=config.use_semantic_helper,
        ownership_relationship=config.ownership_relationship,
        outgoing_relationships=outgoing,
        incoming_relationships=incoming,
        bidirectional_relationships=list(config.bidirectional_relationships),
        cross_domain_relationship_types=cross_domain_types,
        cross_domain_mappings=cross_domain_mappings,
        semantic_types=list(config.semantic_types),
        scoring_weights=dict(config.scoring_weights),
        default_context_intent=config.default_context_intent,
        intent_mappings=dict(config.intent_mappings),
        relationship_creation_map=dict(config.relationship_creation_map),
    )


def generate_relationship_config(domain: Domain) -> "RelationshipConfig | None":
    """
    Generate a RelationshipConfig object for UnifiedRelationshipService.

    Args:
        domain: Domain enum value

    Returns:
        RelationshipConfig object or None if domain not in registry
    """
    config = UNIFIED_REGISTRY.get(domain)
    if not config:
        return None
    return _generate_from_config(config)


def generate_relationship_config_by_label(label: str) -> "RelationshipConfig | None":
    """
    Generate a RelationshipConfig by Neo4j node label.

    Uses UNIFIED_REGISTRY_BY_LABEL for unambiguous lookup (e.g., "Lp" vs Domain.LEARNING
    which maps to LS).

    Args:
        label: Neo4j node label (e.g., "Ku", "Ls", "Lp")

    Returns:
        RelationshipConfig object or None if label not in registry
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(label)
    if not config:
        return None
    return _generate_from_config(config)


def get_unified_config(domain: Domain) -> DomainRelationshipConfig | None:
    """
    Get the unified config for a domain.

    Args:
        domain: Domain enum value

    Returns:
        DomainRelationshipConfig or None
    """
    return UNIFIED_REGISTRY.get(domain)


def get_unified_config_by_label(entity_label: str) -> DomainRelationshipConfig | None:
    """
    Get the unified config by Neo4j label.

    Args:
        entity_label: Neo4j node label (e.g., "Task", "Ku")

    Returns:
        DomainRelationshipConfig or None
    """
    return UNIFIED_REGISTRY_BY_LABEL.get(entity_label)


# =============================================================================
# VALIDATION METHODS (Replaces old RelationshipRegistry validation)
# =============================================================================


def validate_relationship(source_label: str, relationship_type: str) -> bool:
    """
    Validate that a relationship type is valid for a given source label.

    Args:
        source_label: Neo4j node label (e.g., "Task", "Ku")
        relationship_type: Relationship type string (e.g., "APPLIES_KNOWLEDGE")

    Returns:
        True if the relationship is valid for the source label
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(source_label)
    if not config:
        return False

    return any(rel.relationship.value == relationship_type for rel in config.relationships)


def get_valid_relationships(source_label: str) -> dict[str, "ValidationRelationshipSpec"]:
    """
    Get all valid relationships for a source label.

    Args:
        source_label: Neo4j node label

    Returns:
        Dict mapping relationship type to spec (direction, target_labels)
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(source_label)
    if not config:
        return {}

    return {
        rel.relationship.value: ValidationRelationshipSpec(
            direction=rel.direction,
            target_labels=[rel.target_label] if rel.target_label else None,
        )
        for rel in config.relationships
    }


def get_relationship_metadata(
    source_label: str, relationship_type: str
) -> "ValidationRelationshipSpec | None":
    """
    Get metadata for a specific relationship type.

    Args:
        source_label: Neo4j node label
        relationship_type: Relationship type string

    Returns:
        ValidationRelationshipSpec with direction and target_labels, or None
    """
    config = UNIFIED_REGISTRY_BY_LABEL.get(source_label)
    if not config:
        return None

    for rel in config.relationships:
        if rel.relationship.value == relationship_type:
            return ValidationRelationshipSpec(
                direction=rel.direction,
                target_labels=[rel.target_label] if rel.target_label else None,
            )
    return None


def get_all_labels() -> list[str]:
    """
    Get all registered domain labels.

    Returns:
        List of all Neo4j labels in the registry
    """
    return list(UNIFIED_REGISTRY_BY_LABEL.keys())


@dataclass(frozen=True)
class ValidationRelationshipSpec:
    """
    Simplified relationship spec for validation.

    Provides the essential information needed for validation:
    - direction: "outgoing", "incoming", or "both"
    - target_labels: Valid target node labels (or None for any)
    """

    direction: str
    target_labels: list[str] | None = None
