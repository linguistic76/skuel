---
title: UnifiedRelationshipService - Configuration-Driven Relationships
updated: 2026-03-01
category: patterns
related_skills:
- base-analytics-service
- neo4j-cypher-patterns
related_docs:
- /docs/patterns/GENERIC_RELATIONSHIP_SERVICE.md
- /docs/patterns/RELATIONSHIPS_ARCHITECTURE.md
- /docs/decisions/ADR-026-unified-relationship-registry.md
- /docs/decisions/ADR-029-graphnative-service-removal.md
---

# UnifiedRelationshipService Pattern
**Date:** December 3, 2025 (Updated February 2026)
**Type:** Architectural Pattern
**Status:** ✅ IMPLEMENTED - All 9 Domains (6 Activity + 3 Curriculum)
**One Path Forward:** THE single service for all relationship operations (ADR-029)
## Related Skills

For implementation guidance, see:
- [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md)
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)


## Executive Summary

**UnifiedRelationshipService** consolidates the 6 Activity Domain relationship services into a single generic service + domain configurations.

**Key Innovation:** Configuration-driven approach where domain behavior is specified via `DomainRelationshipConfig` objects from the registry, eliminating the need for separate service classes per domain.

**February 2026 Update:** All consumers use `DomainRelationshipConfig` directly from `relationship_registry.py` — THE single source of truth. The intermediate `RelationshipConfig`/`domain_configs.py` translation layer has been removed (~395 lines deleted).

**Scope:** This service covers the **service layer** (graph enrichment, context queries, relationship operations). The **ingestion layer** (`core/services/ingestion/config.py`) also derives its config from the registry via its own `generate_ingestion_relationship_config()` function — see ADR-026 "Ingestion Config Unified" section.

**Scope:** All 10 searchable domains now have relationship configs:
- **Activity (6):** Tasks, Goals, Habits, Events, Choices, Principles (user-owned)
- **Curriculum (3):** KU, LS, LP (shared content)
- **Content/Organization Domains (3):** Journals, Assignments, MOC (MOC provides navigation across curriculum)
- **Finance is NOT an Activity Domain** - it's a standalone expense/budget tracker

**Before:**
```
6 Activity Domain files × ~800 lines each = ~4,800 lines
TasksRelationshipService, GoalsRelationshipService, HabitsRelationshipService...
```

**After:**
```
1 service + 9 configs = ~1,600 lines (67% reduction)
UnifiedRelationshipService + TASKS_CONFIG, GOALS_CONFIG, HABITS_CONFIG...
```

**Old services archived:** `zarchives/relationships/`

---

## One Path Forward Principle (ADR-029)

**January 8, 2026:** GraphNative services removed from Tasks and Goals domains (1,435 lines deleted).

**Architecture Alignment:**
- **UnifiedRelationshipService** is THE single path for all relationship queries
- **UserContext** provides cached cross-domain state for intelligence services
- **Domain services** use fresh Cypher queries when real-time data needed

**Deleted Paths:**
- ❌ `TasksGraphNativeService` - Duplicated UnifiedRelationshipService functionality
- ❌ `GoalsGraphNativeService` - Inconsistent with other 4 Activity domains
- ❌ `GraphNativeMixin` (User Intelligence) - Created third path for context queries

**Remaining Paths (Clear Decision Tree):**
```
Need relationship data?
├─ Cached analysis → context.get_ready_to_learn() (8 lines)
├─ Fresh queries → service.relationships.get_related_uids() (THE path)
└─ Cross-domain → service.relationships.get_cross_domain_context_typed()
```

**Result:** All 6 Activity domains now use identical UnifiedRelationshipService architecture.

**See:** [ADR-029](../decisions/ADR-029-graphnative-service-removal.md) for complete removal rationale.

---

## Architecture Overview

### Configuration-Driven Design

Instead of subclassing for each domain, we use configuration objects:

```python
from core.models.relationship_registry import TASKS_CONFIG, GOALS_CONFIG
from core.services.relationships import UnifiedRelationshipService

# Create relationship service for tasks
tasks_relationship_service = UnifiedRelationshipService(
    backend=tasks_backend,
    graph_intel=graph_intel,
    config=TASKS_CONFIG,
)

# Same service, same methods - different domain via configuration
goals_relationship_service = UnifiedRelationshipService(
    backend=goals_backend,
    graph_intel=graph_intel,
    config=GOALS_CONFIG,
)
```

### Module Structure

```
/core/models/
├── relationship_registry.py         # THE single source of truth (ADR-026)
└── relationship_names.py            # RelationshipName enum

/core/services/relationships/
├── __init__.py                      # Module exports
├── extended_config.py               # Extended specs (QuerySpec, LinkMethodSpec, etc.)
├── unified_relationship_service.py  # Shell: constructor, generic CRUD, typed links (~900 lines)
├── _batch_operations_mixin.py       # N+1 elimination (batch_has_relationship, batch_count_related, batch_get_related_uids)
├── _ordered_relationships_mixin.py  # Curriculum hierarchy + edge metadata
├── _intelligence_mixin.py           # Graph intelligence, semantic, cross-domain context
├── _life_path_mixin.py              # SERVES_LIFE_PATH ("everything flows toward the life path")
├── path_aware_factory.py            # Factory for path-aware entities
├── relationships_container.py       # Generic relationship container
├── planning_mixin.py                # Generic UserContext-aware planning + scoring (~430 lines)
└── _domain_planning_mixin.py        # 6 Activity Domain-specific planning methods (~290 lines)
```

### Single Source of Truth

All relationship configurations are `DomainRelationshipConfig` instances defined in the registry:

```python
from core.models.relationship_registry import (
    TASKS_CONFIG,              # Named config for Tasks domain
    DOMAIN_CONFIGS,           # Access by Domain enum
    LABEL_CONFIGS,  # Access by Neo4j label
    generate_graph_enrichment,  # For DomainConfig factories
)

# Direct named access (preferred)
config = TASKS_CONFIG

# Access by Domain enum
config = DOMAIN_CONFIGS[Domain.TASKS]

# Access by label (supports all domains)
config = LABEL_CONFIGS["Ku"]
```

---

## DomainRelationshipConfig

The configuration dataclass lives in `core.models.relationship_registry`:

```python
@dataclass(frozen=True)
class DomainRelationshipConfig:
    """Configuration consumed directly by UnifiedRelationshipService."""

    domain: Domain                    # e.g., Domain.TASKS
    entity_label: str                 # Neo4j label, e.g., "Task"
    relationships: tuple[UnifiedRelationshipDefinition, ...]  # All relationships
    ownership_relationship: RelationshipName | None = None
    is_shared_content: bool = False
    scoring_weights: dict[str, float] = ...
    intent_mappings: dict[str, QueryIntent] = ...

    # Convenience methods
    def get_relationship_by_method(self, method_key: str) -> UnifiedRelationshipDefinition | None
    def get_all_relationship_methods(self) -> list[str]
    def get_intent_for_operation(self, operation: str) -> QueryIntent
    cross_domain_relationship_types: list[str]  # property
```

### UnifiedRelationshipDefinition

Defines a single relationship type:

```python
@dataclass(frozen=True)
class UnifiedRelationshipDefinition:
    relationship: RelationshipName    # Type-safe enum, e.g., APPLIES_KNOWLEDGE
    target_label: str                 # Neo4j label, e.g., "Ku"
    direction: str = "outgoing"       # "outgoing", "incoming", or "both"
    method_key: str = ""              # e.g., "knowledge" → get_related_uids("knowledge", uid)
    context_field_name: str = ""      # e.g., "applied_knowledge"
    is_cross_domain_mapping: bool = False
    order_by_property: str | None = None
    include_edge_properties: tuple[str, ...] = ()
```

---

## Domain Configurations

All 9 domains have named configs in `core.models.relationship_registry`:

### All Available Configs

| Config | Domain | Entity Label | Key Relationships |
|--------|--------|--------------|-------------------|
| **Activity (6)** |
| `TASKS_CONFIG` | TASKS | Task | APPLIES_KNOWLEDGE, FULFILLS_GOAL, DEPENDS_ON |
| `GOALS_CONFIG` | GOALS | Goal | REQUIRES_KNOWLEDGE, SUPPORTS_GOAL, SUBGOAL_OF |
| `HABITS_CONFIG` | HABITS | Habit | REINFORCES_KNOWLEDGE, SUPPORTS_GOAL, EMBODIES_PRINCIPLE |
| `EVENTS_CONFIG` | EVENTS | Event | APPLIES_KNOWLEDGE, CONTRIBUTES_TO_GOAL, CONFLICTS_WITH |
| `CHOICES_CONFIG` | CHOICES | Choice | INFORMED_BY_KNOWLEDGE, INFORMED_BY_PRINCIPLE, AFFECTS_GOAL |
| `PRINCIPLES_CONFIG` | PRINCIPLES | Principle | GROUNDED_IN_KNOWLEDGE, GUIDES_GOAL, GUIDES_CHOICE |
| **Curriculum (3)** |
| `KU_CONFIG` | KNOWLEDGE | Ku | REQUIRES, ENABLES, ORGANIZES, HAS_NARROWER |
| `LS_CONFIG` | LEARNING | Ls | CONTAINS_KNOWLEDGE, BUILDS_HABIT, ASSIGNS_TASK |
| `LP_CONFIG` | LEARNING | Lp | HAS_STEP, ALIGNED_WITH_GOAL, HAS_MILESTONE_EVENT |

**Notes:**
- Finance is NOT an Activity Domain - it's a standalone expense/budget tracker
- All configs are `DomainRelationshipConfig` instances (frozen dataclasses)
- Curriculum domains have `is_shared_content=True` (no user ownership)
- MOC uses `KU_CONFIG` (MOC is a KU with ORGANIZES relationships)

**Registry Access:**

```python
from core.models.relationship_registry import DOMAIN_CONFIGS, TASKS_CONFIG

# Direct named access (preferred for known domains)
config = TASKS_CONFIG

# Dynamic access by Domain enum
config = DOMAIN_CONFIGS[Domain.TASKS]

# Dynamic access by label
config = LABEL_CONFIGS["Ku"]
```

---

## UnifiedRelationshipService Methods

The service provides 41 methods across categories:

### Basic Queries (8 methods)

```python
# Get related UIDs for a relationship type
uids = await service.get_related_uids("knowledge", "task:123")

# Check if relationship exists
has_goal = await service.has_relationship("goal", "task:123")

# Count related entities
count = await service.count_related("dependents", "task:123")

# Batch operations
has_batch = await service.batch_has_relationship("goal", ["task:1", "task:2"])
counts = await service.batch_count_related("knowledge", ["task:1", "task:2"])

# Get all relationships of a type
entities = await service.get_related_entities("knowledge", "task:123")
```

### Relationship Creation (6 methods)

```python
# Create single relationship
await service.create_relationship(
    "task:123",
    "knowledge",
    "ku:python-basics",
    properties={"confidence": 0.9}
)

# Batch create
await service.create_relationships_batch(
    "task:123",
    "knowledge",
    ["ku:py", "ku:js", "ku:sql"]
)

# Delete relationship
await service.delete_relationship("task:123", "knowledge", "ku:py")
```

### Domain Relationships (3 methods)

```python
# Fetch all relationships for an entity (parallel execution)
rels = await service.fetch_all_relationships("task:123")
# Returns DomainRelationships with all relationship data

# Check for any knowledge connections
if rels.has_any_knowledge():
    knowledge = rels.get_all_knowledge_uids()

# Check prerequisites
if rels.has_prerequisites():
    prereqs = rels.get_field("prerequisite_task_uids")
```

### Path-Aware Queries (4 methods)

```python
# Get cross-domain context with typed path-aware entities
context = await service.get_cross_domain_context_typed("task:123")
# Returns TaskCrossContext with PathAwareKnowledge, PathAwareGoal, etc.

# Access typed relationships
for ku in context.required_knowledge:
    print(f"{ku.title} (distance: {ku.distance}, strength: {ku.path_strength})")

# Direct path-aware entity creation
entity = await service.get_path_aware_entity("task:123", distance=1)
```

### UserContext Planning (6 methods)

```python
# Get actionable items based on user context
actionable = await service.get_actionable_for_user(
    context=user_context,  # ~240 fields
    limit=10,
    include_learning=True
)

# Get blocked items with reasons
blocked = await service.get_blocked_for_user(context)
for item in blocked:
    print(f"{item['task'].title}: {item['blocking_reasons']}")

# Get learning-related items
learning = await service.get_learning_related_for_user(
    context,
    knowledge_focus="ku:python"
)

# Get goal-aligned items
goal_aligned = await service.get_goal_aligned_for_user(context, goal_uid="goal:123")
```

### Typed Link Methods (8 methods)

```python
# Link to knowledge with properties
await service.link_to_knowledge(
    "task:123",
    "ku:python",
    semantic_type=SemanticRelationshipType.APPLIES_KNOWLEDGE,
    confidence=0.9,
    source_tag="manual"
)

# Link to goal
await service.link_to_goal(
    "task:123",
    "goal:456",
    relationship_type="fulfills"  # or "supports", "contributes"
)

# Link to principle
await service.link_to_principle("task:123", "principle:789", alignment_score=0.85)

# Link to habit
await service.link_to_habit("task:123", "habit:abc", reinforcement_type="practice")
```

### Semantic Operations (4 methods)

```python
# Create semantic relationship
await service.create_semantic_relationship(
    "task:123",
    "ku:python",
    semantic_type=SemanticRelationshipType.APPLIES_KNOWLEDGE,
    confidence=0.9,
    strength=0.8,
    evidence=["code_review", "test_coverage"]
)

# Get relationships by semantic type
rels = await service.get_by_semantic_type(
    "task:123",
    SemanticRelationshipType.APPLIES_KNOWLEDGE
)

# Calculate semantic score
score = await service.calculate_semantic_score("task:123", "ku:python")
```

### Cross-Domain Intelligence (2 methods)

```python
# Get full cross-domain context
context = await service.get_cross_domain_context("task:123")
# Returns dict with all related entities across domains

# Analyze cross-domain connections
analysis = await service.analyze_cross_domain_connections("task:123")
```

---

## Path-Aware Types

The service integrates with path-aware types for rich context:

### Type Mappings

```python
PATH_AWARE_TYPE_MAP = {
    Domain.TASKS: PathAwareTask,
    Domain.GOALS: PathAwareGoal,
    Domain.HABITS: PathAwareHabit,
    Domain.EVENTS: PathAwareEvent,
    Domain.CHOICES: PathAwareChoice,
    Domain.PRINCIPLES: PathAwarePrinciple,
    Domain.KNOWLEDGE: PathAwareKnowledge,
}

CROSS_CONTEXT_TYPE_MAP = {
    Domain.TASKS: TaskCrossContext,
    Domain.GOALS: GoalCrossContext,
    Domain.HABITS: HabitCrossContext,
    Domain.EVENTS: EventCrossContext,
    Domain.CHOICES: ChoiceCrossContext,
    Domain.PRINCIPLES: PrincipleCrossContext,
}
```

### Factory Usage

```python
from core.services.relationships import (
    create_path_aware_entity,
    create_path_aware_entities_batch,
    create_cross_context,
)

# Create single path-aware entity
entity = create_path_aware_entity(
    domain=Domain.TASKS,
    raw_data={"uid": "task:123", "title": "Fix bug", "status": "pending"},
    distance=1,
    path_strength=0.9,
    via_relationships=["APPLIES_KNOWLEDGE"]
)

# Batch create
entities = create_path_aware_entities_batch(Domain.TASKS, raw_data_list)

# Create cross-context
context = create_cross_context(
    source_domain=Domain.TASKS,
    source_uid="task:123",
    categorized_data={"prerequisites": [...], "required_knowledge": [...]},
    category_domain_map={"prerequisites": Domain.TASKS, "required_knowledge": Domain.KNOWLEDGE}
)
```

---

## DomainRelationships Container

Generic container for fetched relationship data:

```python
from core.services.relationships import DomainRelationships

# Fetch all relationships in parallel
rels = await DomainRelationships.fetch("task:123", service)

# Access fields dynamically
knowledge_uids = rels.get_field("knowledge_uids")
goal_uids = rels.get_field("goal_uids")

# Check for data
if rels.has_field("prerequisite_task_uids"):
    prereqs = rels.get_field("prerequisite_task_uids")

# Convenience methods
if rels.has_any_knowledge():
    all_ku = rels.get_all_knowledge_uids()  # Set of all knowledge UIDs

if rels.has_prerequisites():
    # Entity has blocking dependencies
    pass

# Total count across all relationships
total = rels.total_count()

# Get all data as dict
all_data = rels.all_fields
```

---

## Migration Guide

### From Domain-Specific Services

**Before (TasksRelationshipService):**
```python
from core.services.tasks.tasks_relationship_service import TasksRelationshipService

tasks_service = TasksRelationshipService(backend, graph_intel)
knowledge_uids = await tasks_service.get_task_knowledge(task_uid)
context = await tasks_service.get_task_cross_domain_context(task_uid)
```

**After (UnifiedRelationshipService):**
```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

tasks_service = UnifiedRelationshipService(backend, graph_intel, TASKS_CONFIG)
knowledge_uids = await tasks_service.get_related_uids("knowledge", task_uid)
context = await tasks_service.get_cross_domain_context_typed(task_uid)
```

### Method Mapping

| Old Method | New Method |
|------------|------------|
| `get_task_knowledge()` | `get_related_uids("knowledge", uid)` |
| `get_task_goals()` | `get_related_uids("goal", uid)` |
| `get_task_dependencies()` | `get_related_uids("prerequisite_tasks", uid)` |
| `get_task_cross_domain_context()` | `get_cross_domain_context_typed(uid)` |
| `create_knowledge_link()` | `link_to_knowledge(uid, ku_uid, ...)` |
| `TaskRelationships.fetch()` | `fetch_all_relationships(uid)` |

---

## Relationship with GenericRelationshipService

**GenericRelationshipService** (documented in `GENERIC_RELATIONSHIP_SERVICE.md`) remains useful for:
- Services still using inheritance pattern
- Gradual migration path
- Cases where subclassing is preferred

**UnifiedRelationshipService** is preferred for:
- New implementations
- Reducing code duplication
- Configuration-driven behavior
- Consistent API across all domains

The two patterns coexist:

| Pattern | Best For | Example |
|---------|----------|---------|
| GenericRelationshipService (inheritance) | Extending behavior, complex overrides | Custom analysis methods |
| UnifiedRelationshipService (configuration) | Standard operations, code reduction | Most relationship operations |

---

## Performance Characteristics

### Parallel Fetching

```python
# DomainRelationships.fetch() executes all queries in parallel
rels = await DomainRelationships.fetch("task:123", service)
# ↳ All relationship types fetched concurrently via asyncio.gather()
```

### Batch Operations

```python
# Batch queries minimize round-trips
has_goals = await service.batch_has_relationship("goal", task_uids)
# ↳ Single query with IN clause instead of N queries
```

### Lazy Loading

```python
# Cross-context is fetched on demand
context = await service.get_cross_domain_context_typed(uid)
# ↳ Only fetches what's needed based on config
```

---

## Testing

### Unit Testing

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

# Mock backend
mock_backend = Mock()
mock_backend.execute_query.return_value = Result.ok([...])

# Test service
service = UnifiedRelationshipService(mock_backend, None, TASKS_CONFIG)

# Test basic query
result = await service.get_related_uids("knowledge", "task:123")
assert result.is_ok
```

### Integration Testing

```bash
# Run relationship tests
uv run pytest tests/integration/test_relationships.py -v

# Validate configs
uv run python -c "from core.models.relationship_registry import DOMAIN_CONFIGS; print(len(DOMAIN_CONFIGS))"
```

---

## Two-Pattern Architecture (By Design)

**UnifiedRelationshipService is intentionally scoped to Activity Domains only.**

SKUEL uses two distinct relationship service patterns, each optimized for different workloads:

### Helper-Based Pattern (UnifiedRelationshipService)

**For:** Activity (6) - Tasks, Goals, Habits, Events, Choices, Principles

**Characteristics:**
- BackendOperations[T] protocol + BaseService inheritance
- RelationshipCreationHelper + SemanticRelationshipHelper composition
- Cross-domain context with path-aware entities
- UserContext-aware methods (get_actionable_for_user, etc.)
- Semantic relationship operations

### Direct Driver Pattern (Domain-Specific Services)

**For:** Curriculum (3) + MOC - LP, LS, KU, and MOC (Content/Org navigation)

**Characteristics:**
- AsyncDriver + GraphQueryExecutor (raw Cypher)
- Does NOT inherit from BaseService
- Complex curriculum-specific calculations:
  - `calculate_motivational_strength()` (LP)
  - `calculate_guidance_strength()` (LS)
  - `practice_completeness_score()` (LS)
  - `is_ready(completed_step_uids)` (LS)
- Recursive traversal patterns (MOC sections)
- Sequence management (step reordering)
- Read-heavy, traversal-oriented workloads

**Why Two Patterns:**
- Activity domains have semantic relationships ("entity relates-to X")
- Curriculum domains have structural relationships ("contains", "aggregates", "has ordered steps")
- Each pattern is optimized for its domain's query patterns
- The services themselves document this: *"This service is NOT compatible with GenericRelationshipService base class"*

**Services Using Each Pattern:**

| Pattern | Services |
|---------|----------|
| Helper-Based | UnifiedRelationshipService (all 6 Activity Domains) |
| Direct Driver | LpRelationshipService, LsRelationshipService, MocRelationshipService, KuGraphService |

---

## Future Enhancements

1. **Caching Layer**: Optional caching for frequently accessed relationships
2. **GraphQL Integration**: Auto-generated resolvers from config
3. **Event-Driven Updates**: Publish relationship change events
4. **Performance Optimization**: Batch operations for cross-domain context

---

## Summary

**UnifiedRelationshipService** transforms SKUEL's relationship layer from:
- 6 Activity Domain-specific services
- ~4,800 lines of duplicated code
- Inconsistent APIs across domains
- Dual-source configuration problem

To:
- 1 generic service + 9 configs (direct from registry)
- ~1,600 lines total
- Consistent API for all domains
- 67% code reduction
- Type-safe configuration
- Single source of truth (RelationshipRegistry)

**Key Files:**
- `/core/models/relationship_registry.py` - THE single source of truth
- `/core/services/relationships/unified_relationship_service.py`

**Usage:**
```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

service = UnifiedRelationshipService(backend, graph_intel, TASKS_CONFIG)
await service.get_related_uids("knowledge", "task:123")
```

**See Also:** ADR-026 for the consolidation decision and implementation details.

---

**Pattern By:** Claude Code
**Date:** December 3, 2025 (Updated February 2026)
**Impact:** HIGH (67% code reduction, architectural consistency, single source of truth)
**Risk:** LOW (incremental migration, no translation layer)
