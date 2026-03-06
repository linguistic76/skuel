"""
Relationship Registry
=====================

Single source of truth for ALL relationship configurations across domains.

**Architecture (February 2026 — Config Merge):**

DomainRelationshipConfig is consumed directly by UnifiedRelationshipService.
No intermediate translation layer — the registry IS the config.

**Usage:**
```python
from core.models.relationship_registry import (
    TASKS_CONFIG,
    LABEL_CONFIGS,
    generate_graph_enrichment,
)

# Pass config directly to relationship service
service = UnifiedRelationshipService(backend=backend, config=TASKS_CONFIG)

# Get graph enrichment for BaseService search
patterns = generate_graph_enrichment("Task")
```

**Architecture:**
- UnifiedRelationshipDefinition: One relationship's complete definition
- DomainRelationshipConfig: All relationships for one domain (consumed by services directly)
- LABEL_CONFIGS: All domains keyed by Neo4j label

See Also:
    - /docs/decisions/ADR-026-unified-relationship-registry.md
    - /core/services/base_service.py - Consumer of graph enrichment
"""

from dataclasses import dataclass, field
from typing import Any

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.choice.choice_dto import ChoiceDTO
from core.models.curriculum.curriculum_dto import CurriculumDTO
from core.models.curriculum.exercise_dto import ExerciseDTO
from core.models.curriculum.learning_path_dto import LearningPathDTO
from core.models.curriculum.learning_step_dto import LearningStepDTO

# Curriculum domain imports - (February 2026): LS/LP unified into Entity model
# NOTE (February 2026): Habit imports removed — Habit merged into Entity model
# NOTE (February 2026): Ku is now a Union type alias; use Entity (the actual class) for model_class
from core.models.entity import Entity
from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType
from core.models.event.event_dto import EventDTO
from core.models.goal.goal_dto import GoalDTO
from core.models.habit.habit_dto import HabitDTO
from core.models.principle.principle_dto import PrincipleDTO

# NOTE (February 2026): MOC is not a separate EntityType.
# Any KU can organize others via ORGANIZES relationships (emergent MOC identity).
from core.models.principle.reflection import PrincipleReflection
from core.models.principle.reflection_dto import PrincipleReflectionDTO
from core.models.query import QueryIntent
from core.models.relationship_names import RelationshipName
from core.models.task.task_dto import TaskDTO

# Task and Goal domains unified into Entity model (February 2026)
Task = Entity
Goal = Entity

# =============================================================================
# RELATIONSHIP DEFINITION DATACLASSES
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
class LateralRelationshipSpec:
    """
    Metadata for one lateral relationship type.

    Part of the RelationshipRegistry — THE single source of truth
    for lateral relationship behavior (symmetry, inverses, constraints).

    See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
    """

    relationship: RelationshipName
    is_symmetric: bool
    auto_inverse: bool
    inverse_type: RelationshipName | None = None
    requires_same_parent: bool = False
    requires_same_depth: bool = False
    check_cycles: bool = False  # BLOCKS, PREREQUISITE_FOR
    category: str = ""  # "structural", "dependency", "semantic", "associative"


@dataclass(frozen=True)
class UnifiedRelationshipDefinition:
    """
    Complete definition of one relationship type for a domain.

    This is THE single source of truth. Both graph enrichment patterns
    and RelationshipSpec objects are generated from this.

    **Core Fields:**
    - relationship: The RelationshipName enum (type-safe)
    - target_label: Neo4j label of related nodes (e.g., "Entity", "Goal")
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

    # Ingestion mapping (February 2026 - Config Unification)
    # YAML field path for ingestion (e.g., "connections.requires").
    # When set, this relationship is created during YAML/Markdown import.
    yaml_field_path: str | None = None
    # Scopes yaml_field_path to a specific EntityType.
    # Needed when multiple EntityTypes share a Neo4j label.
    # None means: applies to the default EntityType for this label.
    ingestion_entity_type: EntityType | None = None

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

    THE single config type consumed directly by UnifiedRelationshipService.
    Also provides graph enrichment and prerequisite/enables data for BaseService.

    **Sections:**
    - Identity: domain, labels, classes
    - Relationships: unified definitions (single source of truth)
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
    is_shared_content: bool = False  # True for KU, LS, LP

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

    # =========================================================================
    # SERVICE INTERFACE - Used by UnifiedRelationshipService directly
    # =========================================================================

    def get_relationship_by_method(self, method_key: str) -> UnifiedRelationshipDefinition | None:
        """
        Look up a relationship definition by method key.

        Args:
            method_key: Key like "knowledge", "principles", "subtasks"

        Returns:
            UnifiedRelationshipDefinition or None if not found
        """
        for rel in self.relationships:
            if rel.method_key == method_key:
                return rel
        return None

    def get_all_relationship_methods(self) -> list[str]:
        """Get all method keys for relationship enumeration."""
        return [rel.method_key for rel in self.relationships]

    def get_intent_for_operation(self, operation: str) -> QueryIntent:
        """Get QueryIntent for a specific operation, falling back to default."""
        return self.intent_mappings.get(operation, self.default_context_intent)

    @property
    def cross_domain_relationship_types(self) -> list[str]:
        """Get unique relationship type strings for cross-domain context queries."""
        return list({rel.relationship.value for rel in self.relationships})


# =============================================================================
# DOMAIN RELATIONSHIP CONFIGS - THE SINGLE SOURCE OF TRUTH
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
TASKS_CONFIG = DomainRelationshipConfig(
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
            "Entity",
            "outgoing",
            "applied_knowledge",
            "knowledge",
            use_confidence=True,  # Context: filter by confidence
            yaml_field_path="connections.applies_knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
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
            "Entity",
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
            yaml_field_path="connections.fulfills_goal",
        ),
        # Task → Habit: single result for context
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_HABIT,
            "Entity",
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
            yaml_field_path="connections.depends_on",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFERRED_KNOWLEDGE,
            "Entity",
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
            "Entity",
            "outgoing",
            "implemented_choices",
            "implements_choices",
            fields=("uid", "title", "status"),
        ),
        # Outgoing: Task → LifePath (task serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Entity",
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
GOALS_CONFIG = DomainRelationshipConfig(
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
            "Entity",
            "outgoing",
            "required_knowledge",
            "knowledge",
            use_confidence=True,  # Context: filter by confidence
            yaml_field_path="connections.requires_knowledge",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDED_BY_PRINCIPLE,
            "Principle",
            "outgoing",
            "aligned_principles",  # Context name: aligned_principles
            "principles",
            yaml_field_path="connections.aligned_with_principle",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ALIGNED_WITH_PATH,
            "Entity",
            "outgoing",
            "aligned_paths",
            "aligned_paths",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_PATH_COMPLETION,
            "Entity",
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
            "Entity",
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
            "Entity",
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
            "Entity",
            "incoming",
            "essential_habits",
            "essential_habits",
            filter_property="essentiality",
            filter_value="essential",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Entity",
            "incoming",
            "critical_habits",
            "critical_habits",
            filter_property="essentiality",
            filter_value="critical",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SUPPORTS_GOAL,
            "Entity",
            "incoming",
            "optional_habits",
            "optional_habits",
            filter_property="essentiality",
            filter_value="optional",
        ),
        # Outgoing: Goal → LifePath (goal serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Entity",
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
HABITS_CONFIG = DomainRelationshipConfig(
    domain=Domain.HABITS,
    entity_label="Entity",
    dto_class=HabitDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=RelationshipName.OWNS,
    relationships=(
        # Outgoing: Habit → Other (with context-specific fields)
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "reinforced_knowledge",
            "knowledge",
            yaml_field_path="connections.reinforces_knowledge",
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
            yaml_field_path="connections.supports_goal",
        ),
        # Incoming: Other → Habit
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_PREREQUISITE_HABIT,
            "Entity",
            "outgoing",
            "prerequisite_habits",
            "prerequisite_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_HABIT,
            "Entity",
            "incoming",
            "reinforcing_habits",
            "reinforcing_habits",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_HABIT,
            "Entity",
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
            "Entity",
            "both",
            "related_habits",
            "related_habits",
            fields=("uid", "title", "current_streak"),  # Context: include streak
        ),
        # Outgoing: Habit → LifePath (habit serves user's life path)
        UnifiedRelationshipDefinition(
            RelationshipName.SERVES_LIFE_PATH,
            "Entity",
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
            "Entity",
            "outgoing",
            "informed_choices",
            "informed_choices",
            fields=("uid", "title", "status"),
        ),
        # Incoming: Choice impacts habit
        UnifiedRelationshipDefinition(
            RelationshipName.IMPACTS_HABIT,
            "Entity",
            "incoming",
            "impacting_choices",
            "impacting_choices",
            fields=("uid", "title", "status"),
        ),
        # Shared-neighbor pattern: Related habits via shared knowledge or goals
        UnifiedRelationshipDefinition(
            RelationshipName.REINFORCES_KNOWLEDGE,  # Placeholder - uses shared_neighbor_config
            "Entity",
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
EVENTS_CONFIG = DomainRelationshipConfig(
    domain=Domain.EVENTS,
    entity_label="Event",
    dto_class=EventDTO,
    model_class=Entity,
    backend_get_method="get_event",
    ownership_relationship=RelationshipName.HAS_EVENT,
    relationships=(
        # Outgoing: Event → Other
        UnifiedRelationshipDefinition(
            RelationshipName.APPLIES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "applied_knowledge",
            "knowledge",
            yaml_field_path="connections.applies_knowledge",
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
            "Entity",
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
            "Entity",
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
            "Entity",
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
            "Entity",
            "outgoing",
            "triggered_choices",
            "triggered_choices",
            fields=("uid", "title", "status"),
        ),
        # Incoming: Choice schedules event
        UnifiedRelationshipDefinition(
            RelationshipName.SCHEDULES_EVENT,
            "Entity",
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
CHOICES_CONFIG = DomainRelationshipConfig(
    domain=Domain.CHOICES,
    entity_label="Entity",
    dto_class=ChoiceDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=RelationshipName.OWNS,
    relationships=(
        # Outgoing: Choice → Other
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMED_BY_KNOWLEDGE,
            "Entity",
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
            yaml_field_path="connections.guided_by_principle",
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
            "Entity",
            "outgoing",
            "opened_paths",
            "learning_paths",
        ),
        # Incoming: Other → Choice
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRED_BY_CHOICE,
            "Entity",
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
            "Entity",
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
            "Entity",
            "outgoing",
            "impacted_habits",
            "impacted_habits",
            fields=("uid", "title", "current_streak"),
        ),
        # Incoming: Habit informs choice
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMS_CHOICE,
            "Entity",
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
            "Entity",
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
                target_label="Entity",
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
PRINCIPLES_CONFIG = DomainRelationshipConfig(
    domain=Domain.PRINCIPLES,
    entity_label="Entity",
    dto_class=PrincipleDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=RelationshipName.OWNS,
    relationships=(
        # Outgoing: Principle → Other
        UnifiedRelationshipDefinition(
            RelationshipName.GROUNDED_IN_KNOWLEDGE,
            "Entity",
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
            yaml_field_path="connections.guides_goal",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDES_CHOICE,
            "Entity",
            "outgoing",
            "guided_choices",
            "guided_choices",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INSPIRES_HABIT,
            "Entity",
            "outgoing",
            "inspired_habits",
            "inspired_habits",
            yaml_field_path="connections.inspires_habit",
        ),
        # Incoming: Other → Principle
        UnifiedRelationshipDefinition(
            RelationshipName.EMBODIES_PRINCIPLE,
            "Entity",
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
            "Entity",
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

USER_CONFIG = DomainRelationshipConfig(
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
            "Entity",
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
            "Entity",
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

PRINCIPLE_REFLECTION_CONFIG = DomainRelationshipConfig(
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
            "Entity",
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
            "Entity",
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
# Complete - January 2026
# -----------------------------------------------------------------------------

# KU (Knowledge Unit)
ARTICLE_CONFIG = DomainRelationshipConfig(
    domain=Domain.KNOWLEDGE,
    entity_label="Entity",
    dto_class=CurriculumDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Ku → Ku (prerequisites with confidence)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "prerequisites",
            "requires",
            use_confidence=True,  # Context: filter by confidence
            yaml_field_path="connections.requires",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "enables_learning",
            "enables",
            yaml_field_path="connections.enables",
        ),
        # Incoming: Other Entity → This Entity (dependents)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
            "incoming",
            "dependents",
            "required_by",
        ),
        # Related KUs (bidirectional)
        UnifiedRelationshipDefinition(
            RelationshipName.RELATED_TO,
            "Entity",
            "both",
            "related",
            "related",
            yaml_field_path="connections.related",
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
            "Entity",
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
            "Entity",
            "incoming",
            "informs_choices",
            "informs_choices",
        ),
        # Curriculum relationships (LS is now :Entity with entity_type='learning_step')
        UnifiedRelationshipDefinition(
            RelationshipName.CONTAINS_KNOWLEDGE,
            "Entity",
            "incoming",
            "in_learning_steps",
            "in_steps",
        ),
        # Incoming: enables (other KU enables this KU)
        UnifiedRelationshipDefinition(
            RelationshipName.ENABLES_KNOWLEDGE,
            "Entity",
            "incoming",
            "enabled_by_kus",
            "enabled_by",
        ),
        # Organization (any KU can organize others via ORGANIZES relationships)
        UnifiedRelationshipDefinition(
            RelationshipName.ORGANIZES,
            "Entity",
            "outgoing",
            "organized_children",
            "organizes",
            order_by_property="order",
            order_direction="ASC",
            include_edge_properties=("order",),
            yaml_field_path="organizes",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ORGANIZES,
            "Entity",
            "incoming",
            "organized_by",
            "organized_by",
        ),
        # Composition: Article → atomic Ku
        UnifiedRelationshipDefinition(
            RelationshipName.USES_KU,
            "Ku",
            "outgoing",
            "used_kus",
            "uses_ku",
            yaml_field_path="uses_kus",
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

# Ku (Atomic Knowledge Unit) — lightweight ontology/reference node
# Relationships (USES_KU, TRAINS_KU) added in Phase 7
KU_CONFIG = DomainRelationshipConfig(
    domain=Domain.KNOWLEDGE,
    entity_label="Ku",
    dto_class=EntityDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Incoming: Articles that compose this atomic Ku
        UnifiedRelationshipDefinition(
            RelationshipName.USES_KU,
            "Entity",
            "incoming",
            "used_by_articles",
            "used_by",
        ),
    ),
    prerequisite_relationship_names=(),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(),
    scoring_weights=_build_scoring_weights(),
    default_context_intent=QueryIntent.EXPLORATORY,
    intent_mappings={},
)

# LS (Learning Step) — Entity with entity_type='learning_step'
LS_CONFIG = DomainRelationshipConfig(
    domain=Domain.LEARNING,
    entity_label="Entity",
    dto_class=LearningStepDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Ls → Other
        UnifiedRelationshipDefinition(
            RelationshipName.CONTAINS_KNOWLEDGE,
            "Entity",
            "outgoing",
            "knowledge_units",
            "knowledge",
            yaml_field_path="primary_knowledge_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.TRAINS_KU,
            "Ku",
            "outgoing",
            "trained_kus",
            "trains_ku",
            yaml_field_path="trains_ku_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_STEP,
            "Entity",
            "outgoing",
            "prerequisites",
            "prerequisite_steps",
            yaml_field_path="prerequisite_step_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "prerequisite_knowledge_units",
            "prerequisite_knowledge",
            yaml_field_path="prerequisite_knowledge_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "supporting_knowledge_units",
            "supporting_knowledge",
            yaml_field_path="supporting_knowledge_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.GUIDED_BY_PRINCIPLE,
            "Principle",
            "outgoing",
            "guiding_principles",
            "principles",
            yaml_field_path="principle_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.INFORMS_CHOICE,
            "Entity",
            "outgoing",
            "informed_choices",
            "choices",
            yaml_field_path="choice_uids",
        ),
        # Practice patterns
        UnifiedRelationshipDefinition(
            RelationshipName.BUILDS_HABIT,
            "Entity",
            "outgoing",
            "builds_habits",
            "practice_habits",
            yaml_field_path="habit_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.ASSIGNS_TASK,
            "Task",
            "outgoing",
            "assigned_tasks",
            "practice_tasks",
            yaml_field_path="task_uids",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.SCHEDULES_EVENT,
            "Event",
            "outgoing",
            "scheduled_events",
            "practice_events",
            yaml_field_path="event_template_uids",
        ),
        # Incoming: Other → Ls (LP is now also :Entity)
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_STEP,
            "Entity",
            "incoming",
            "learning_paths",
            "in_paths",
            yaml_field_path="learning_path_uids",
            single=True,
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

# LP (Learning Path) — Entity with entity_type='learning_path'
LP_CONFIG = DomainRelationshipConfig(
    domain=Domain.LEARNING,
    entity_label="Entity",
    dto_class=LearningPathDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=None,  # Shared content
    is_shared_content=True,
    relationships=(
        # Outgoing: Lp → Other (LS is now also :Entity)
        UnifiedRelationshipDefinition(
            RelationshipName.HAS_STEP,
            "Entity",
            "outgoing",
            "learning_steps",
            "steps",
            order_by_property="sequence",
            order_direction="ASC",
            include_edge_properties=("sequence", "completed"),
            yaml_field_path="connections.contains_steps",
        ),
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
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
            "Entity",
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

# -----------------------------------------------------------------------------
# EXERCISE (Instruction Templates - Curriculum Tier B)
# Exercises require curriculum knowledge and produce submissions
# -----------------------------------------------------------------------------
EXERCISE_CONFIG = DomainRelationshipConfig(
    domain=Domain.KNOWLEDGE,  # Curriculum tier
    entity_label="Entity",  # Exercise is a :Entity node with entity_type='exercise'
    dto_class=ExerciseDTO,
    model_class=Entity,
    backend_get_method="get",
    ownership_relationship=RelationshipName.OWNS,
    is_shared_content=False,  # Exercises are teacher-owned
    relationships=(
        # Outgoing: Exercise → Curriculum (what knowledge this exercise requires)
        UnifiedRelationshipDefinition(
            RelationshipName.REQUIRES_KNOWLEDGE,
            "Entity",
            "outgoing",
            "required_knowledge",
            "required_knowledge",
            fields=("uid", "title", "complexity", "learning_level"),
        ),
        # Outgoing: Exercise → Group (teacher assigns to group)
        UnifiedRelationshipDefinition(
            RelationshipName.FOR_GROUP,
            "Group",
            "outgoing",
            "target_group",
            "target_group",
            fields=("uid", "title"),
            single=True,
        ),
        # Incoming: Submission → Exercise (student submissions fulfilling this exercise)
        UnifiedRelationshipDefinition(
            RelationshipName.FULFILLS_EXERCISE,
            "Entity",
            "incoming",
            "submissions",
            "submissions",
            fields=("uid", "title", "status", "user_uid"),
        ),
    ),
    prerequisite_relationship_names=(RelationshipName.REQUIRES_KNOWLEDGE,),
    enables_relationship_names=(),
    bidirectional_relationships=(),
    semantic_types=(
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.PROVIDES_PRACTICAL_APPLICATION,
    ),
    scoring_weights=_build_scoring_weights(knowledge=0.5, goals=0.3, alignment=0.2),
    default_context_intent=QueryIntent.PREREQUISITE,
    intent_mappings={
        "context": QueryIntent.PREREQUISITE,
        "practice": QueryIntent.PRACTICE,
    },
)

# =============================================================================
# NOTE (February 2026): MOC_CONFIG REMOVED
# =============================================================================
# MOC is not a separate EntityType. Any KU can organize others via ORGANIZES.
# The KU config includes ORGANIZES relationship for organization functionality.


# =============================================================================
# DOMAIN CONFIGS - ALL DOMAINS
# =============================================================================
# Note: Finance domain is standalone (no relationship registry)
# Finance is a bookkeeping domain, not an Activity domain

DOMAIN_CONFIGS: dict[Domain, DomainRelationshipConfig] = {
    # Activity Domains (6) - User-owned entities
    Domain.TASKS: TASKS_CONFIG,
    Domain.GOALS: GOALS_CONFIG,
    Domain.HABITS: HABITS_CONFIG,
    Domain.EVENTS: EVENTS_CONFIG,
    Domain.CHOICES: CHOICES_CONFIG,
    Domain.PRINCIPLES: PRINCIPLES_CONFIG,
    # Note: Finance is standalone (not in registry)
    # Curriculum Domains - Shared content
    # Note: LS and LP both use Domain.LEARNING
    # Use LABEL_CONFIGS for unambiguous lookup
    Domain.KNOWLEDGE: ARTICLE_CONFIG,  # Primary for Domain.KNOWLEDGE
    Domain.LEARNING: LS_CONFIG,  # Primary for Domain.LEARNING
}

# Label-based lookup (THE authoritative way to get curriculum configs)
# (February 2026): "Ls" and "Lp" kept as virtual config keys.
# Their entity_label is now "Entity" (all curriculum nodes are :Entity in Neo4j).
LABEL_CONFIGS: dict[str, DomainRelationshipConfig] = {
    # Activity Domains (6)
    "Task": TASKS_CONFIG,
    "Goal": GOALS_CONFIG,
    "Habit": HABITS_CONFIG,
    "Event": EVENTS_CONFIG,
    "Choice": CHOICES_CONFIG,  # Virtual key — config lookup key for 'choice'}
    "Principle": PRINCIPLES_CONFIG,
    # Note: Finance/Expense is standalone (not in registry)
    # User (Identity Layer - January 2026)
    "User": USER_CONFIG,
    # Principle Reflection (January 2026)
    "PrincipleReflection": PRINCIPLE_REFLECTION_CONFIG,
    # Curriculum Domains — all :Entity in Neo4j, virtual keys for config lookup
    "Entity": ARTICLE_CONFIG,
    "Ku": KU_CONFIG,
    "Ls": LS_CONFIG,  # Virtual key — config lookup key for 'learning_step'}
    "Lp": LP_CONFIG,  # Virtual key — config lookup key for 'learning_path'}
    "Exercise": EXERCISE_CONFIG,  # Virtual key — config lookup key for 'exercise'}
}


# =============================================================================
# LATERAL RELATIONSHIP SPECS — Single source of truth for lateral metadata
# =============================================================================

LATERAL_RELATIONSHIP_SPECS: dict[RelationshipName, "LateralRelationshipSpec"] = {
    # --- Structural ---
    RelationshipName.SIBLING: LateralRelationshipSpec(
        relationship=RelationshipName.SIBLING,
        is_symmetric=True,
        auto_inverse=False,
        requires_same_parent=True,
        requires_same_depth=True,
        category="structural",
    ),
    RelationshipName.COUSIN: LateralRelationshipSpec(
        relationship=RelationshipName.COUSIN,
        is_symmetric=True,
        auto_inverse=False,
        requires_same_depth=True,
        category="structural",
    ),
    RelationshipName.AUNT_UNCLE: LateralRelationshipSpec(
        relationship=RelationshipName.AUNT_UNCLE,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.NIECE_NEPHEW,
        category="structural",
    ),
    RelationshipName.NIECE_NEPHEW: LateralRelationshipSpec(
        relationship=RelationshipName.NIECE_NEPHEW,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.AUNT_UNCLE,
        category="structural",
    ),
    # --- Dependency ---
    RelationshipName.BLOCKS: LateralRelationshipSpec(
        relationship=RelationshipName.BLOCKS,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.BLOCKED_BY,
        requires_same_parent=True,
        check_cycles=True,
        category="dependency",
    ),
    RelationshipName.BLOCKED_BY: LateralRelationshipSpec(
        relationship=RelationshipName.BLOCKED_BY,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.BLOCKS,
        category="dependency",
    ),
    RelationshipName.PREREQUISITE_FOR: LateralRelationshipSpec(
        relationship=RelationshipName.PREREQUISITE_FOR,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.REQUIRES_PREREQUISITE,
        check_cycles=True,
        category="dependency",
    ),
    RelationshipName.REQUIRES_PREREQUISITE: LateralRelationshipSpec(
        relationship=RelationshipName.REQUIRES_PREREQUISITE,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.PREREQUISITE_FOR,
        category="dependency",
    ),
    RelationshipName.LATERAL_ENABLES: LateralRelationshipSpec(
        relationship=RelationshipName.LATERAL_ENABLES,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.LATERAL_ENABLED_BY,
        category="dependency",
    ),
    RelationshipName.LATERAL_ENABLED_BY: LateralRelationshipSpec(
        relationship=RelationshipName.LATERAL_ENABLED_BY,
        is_symmetric=False,
        auto_inverse=True,
        inverse_type=RelationshipName.LATERAL_ENABLES,
        category="dependency",
    ),
    # --- Semantic ---
    RelationshipName.RELATED_TO: LateralRelationshipSpec(
        relationship=RelationshipName.RELATED_TO,
        is_symmetric=True,
        auto_inverse=False,
        requires_same_depth=True,
        category="semantic",
    ),
    RelationshipName.SIMILAR_TO: LateralRelationshipSpec(
        relationship=RelationshipName.SIMILAR_TO,
        is_symmetric=True,
        auto_inverse=False,
        category="semantic",
    ),
    RelationshipName.COMPLEMENTARY_TO: LateralRelationshipSpec(
        relationship=RelationshipName.COMPLEMENTARY_TO,
        is_symmetric=True,
        auto_inverse=False,
        category="semantic",
    ),
    RelationshipName.CONFLICTS_WITH: LateralRelationshipSpec(
        relationship=RelationshipName.CONFLICTS_WITH,
        is_symmetric=True,
        auto_inverse=False,
        category="semantic",
    ),
    # --- Associative ---
    RelationshipName.ALTERNATIVE_TO: LateralRelationshipSpec(
        relationship=RelationshipName.ALTERNATIVE_TO,
        is_symmetric=True,
        auto_inverse=False,
        requires_same_depth=True,
        category="associative",
    ),
    RelationshipName.RECOMMENDED_WITH: LateralRelationshipSpec(
        relationship=RelationshipName.RECOMMENDED_WITH,
        is_symmetric=True,
        auto_inverse=False,
        category="associative",
    ),
    RelationshipName.STACKS_WITH: LateralRelationshipSpec(
        relationship=RelationshipName.STACKS_WITH,
        is_symmetric=True,
        auto_inverse=False,
        requires_same_parent=True,
        category="associative",
    ),
}


def get_lateral_spec(rel_type: RelationshipName) -> LateralRelationshipSpec | None:
    """Get lateral spec by relationship type. None if not a lateral type."""
    return LATERAL_RELATIONSHIP_SPECS.get(rel_type)


# =============================================================================
# GENERATOR FUNCTIONS
# =============================================================================


def generate_graph_enrichment(entity_label: str) -> list[tuple[str, str, str, str]]:
    """
    Generate graph enrichment patterns for BaseService._graph_enrichment_patterns.

    Args:
        entity_label: Neo4j node label (e.g., "Task", "Entity", "Lp")

    Returns:
        List of tuples: (relationship_type, target_label, context_field, direction)
    """
    config = LABEL_CONFIGS.get(entity_label)
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
    config = LABEL_CONFIGS.get(entity_label)
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
    config = LABEL_CONFIGS.get(entity_label)
    if not config:
        return []

    return [rel.value for rel in config.enables_relationship_names]


def get_domain_config(domain: Domain) -> DomainRelationshipConfig | None:
    """
    Get the relationship config for a domain.

    Args:
        domain: Domain enum value

    Returns:
        DomainRelationshipConfig or None
    """
    return DOMAIN_CONFIGS.get(domain)


def get_config_by_label(entity_label: str) -> DomainRelationshipConfig | None:
    """
    Get the relationship config by Neo4j label.

    Args:
        entity_label: Neo4j node label (e.g., "Task", "Entity")

    Returns:
        DomainRelationshipConfig or None
    """
    return LABEL_CONFIGS.get(entity_label)


# =============================================================================
# ENTITY TYPE ↔ LABEL MAPPINGS
# =============================================================================

# Maps EntityType to registry config key (Neo4j label string).
# All domain entities are :Entity nodes; virtual config keys kept for lookup.
ENTITY_TYPE_TO_LABEL: dict[EntityType, str] = {
    EntityType.ARTICLE: "Entity",
    EntityType.KU: "Ku",
    EntityType.TASK: "Task",
    EntityType.GOAL: "Goal",
    EntityType.HABIT: "Habit",  # Virtual key — config lookup key for 'habit'}
    EntityType.EVENT: "Event",
    EntityType.CHOICE: "Choice",  # Virtual key — config lookup key for 'choice'}
    EntityType.PRINCIPLE: "Principle",
    EntityType.LEARNING_PATH: "Lp",
    EntityType.LEARNING_STEP: "Ls",
    EntityType.EXERCISE: "Exercise",  # Virtual key — config lookup key for 'exercise'}
}

LABEL_TO_DEFAULT_ENTITY_TYPE: dict[str, EntityType] = {
    "Entity": EntityType.ARTICLE,
    "Ku": EntityType.KU,
    "Task": EntityType.TASK,
    "Goal": EntityType.GOAL,
    "Habit": EntityType.HABIT,
    "Event": EntityType.EVENT,
    "Choice": EntityType.CHOICE,  # Virtual key — config lookup key for 'choice'}
    "Principle": EntityType.PRINCIPLE,
    "Lp": EntityType.LEARNING_PATH,
    "Ls": EntityType.LEARNING_STEP,
    "Exercise": EntityType.EXERCISE,  # Virtual key — config lookup key for 'exercise'}
}


# =============================================================================
# VALIDATION METHODS (Replaces old RelationshipRegistry validation)
# =============================================================================


def validate_relationship(source_label: str, relationship_type: str) -> bool:
    """
    Validate that a relationship type is valid for a given source label.

    Args:
        source_label: Neo4j node label (e.g., "Task", "Entity")
        relationship_type: Relationship type string (e.g., "APPLIES_KNOWLEDGE")

    Returns:
        True if the relationship is valid for the source label
    """
    config = LABEL_CONFIGS.get(source_label)
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
    config = LABEL_CONFIGS.get(source_label)
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
    config = LABEL_CONFIGS.get(source_label)
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
    return list(LABEL_CONFIGS.keys())


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
