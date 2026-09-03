---
title: UnifiedRelationshipService - Configuration-Driven Relationships
updated: 2026-09-03
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

**Scope:** 16 `DomainRelationshipConfig`s in `relationship_registry.py` — every searchable domain plus supporting configs:
- **Activity (6):** Tasks, Goals, Habits, Events, Choices, Principles (user-owned)
- **Curriculum (4):** KU, PS, LP, Exercise (shared content)
- **Learning loop (4):** RevisedExercise, UserEntry, EntryReport, Interaction
- **Supporting (2):** User, PrincipleReflection
- **Finance is NOT covered** — it's a Firefly III sidecar (ADR-052), outside the Entity graph

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
├── extended_config.py               # Extended specs (QuerySpec, PathAwareTypeSpec, etc.)
├── unified_relationship_service.py  # Shell: constructor, generic CRUD, typed links (~900 lines)
├── _batch_operations_mixin.py       # N+1 elimination (batch_has_relationship, batch_count_related, batch_get_related_uids)
├── _ordered_relationships_mixin.py  # Curriculum hierarchy + edge metadata
├── _intelligence_mixin.py           # Graph intelligence, semantic, cross-domain context
├── path_aware_factory.py            # Factory for path-aware entities
└── relationships_container.py       # Generic relationship container
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
| `PS_CONFIG` | LEARNING | PathStep | CONTAINS_KNOWLEDGE, TRAINS_KU, REQUIRES_STEP, BUILDS_HABIT, ASSIGNS_TASK |
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
uids = await service.get_related_uids("knowledge", "task.123")

# Check if relationship exists
has_goal = await service.has_relationship("goal", "task.123")

# Count related entities
count = await service.count_related("dependents", "task.123")

# Batch operations
has_batch = await service.batch_has_relationship("goal", ["task.1", "task.2"])
counts = await service.batch_count_related("knowledge", ["task.1", "task.2"])

# Get all relationships of a type
entities = await service.get_related_entities("knowledge", "task.123")

# Edge-property-FILTERED keys (e.g. essentiality tiers on SUPPORTS_GOAL).
essential = await service.get_related_uids("essential_habits", "goal.123")    # r.essentiality = "essential"
all_habits = await service.get_related_uids("supporting_habits", "goal.123")  # no filter → every tier
```

> **Filtered method-keys (`filter_property`/`filter_value`).** A
> `UnifiedRelationshipDefinition` may scope a relationship by an edge property — GOALS_CONFIG
> splits SUPPORTS_GOAL into `essential_habits`/`critical_habits`/`optional_habits` (filtered)
> plus the no-filter `supporting_habits`/`contributing_habits` catch-all. The filter applies
> on **every** read path: `get_related_uids`/`count_related`/`has_relationship` (backend
> `WHERE r.<prop> = $value`), `get_cross_domain_context` categorization (filtered mappings
> sort before the catch-all, matched on each node's `incident_rel_properties`), and
> `get_with_context`/`build_entity_with_context` (per-clause `WHERE`). **Catch-all semantics
> differ by path:** the no-filter key returns ALL on `get_related_uids` / `get_with_context`
> (independent queries) but the RESIDUAL on `get_cross_domain_context` (first-match `break`);
> the union is identical. **Writing through a filtered key stamps the property** (see
> create_relationship below) so create→read round-trips. Reconciled end-to-end PR #216.

### Relationship Creation (6 methods)

```python
# Batch create — canonical, every-domain-safe. Signature is
# (entity_uid, {relationship_key: [target_uids]}). Each key's targets go through
# one validated backend.create_relationships_batch (atomic per key). NOTE: a
# multi-key call iterates keys, so it is NOT all-or-nothing across keys — a
# per-key failure is skipped, not rolled back. Use one key for atomic semantics.
await service.create_relationships_batch(
    EntityUID("task.123"),
    {"knowledge": ["ku.py", "ku.js", "ku.sql"]},
)

# Delete relationship
await service.delete_relationship("task.123", "knowledge", "ku.py")

# Single edge — config-keyed, every-domain-safe (root-fixed PR #197)
await service.create_relationship("knowledge", "task.123", "ku.py", {"confidence": 0.9})
```

> **`create_relationship(key, from_uid, to_uid, properties)` is safe** (root-fixed
> PR #197). It looks up the registry `spec` for `key`, orients direction via
> `_orient_edge` (an *incoming* spec swaps endpoints on write/delete so direction-aware
> reads still match), and routes through the same `backend.create_relationships_batch`
> path create-flows use. It **fails closed** on an unknown key (`Result.fail`, no edge).
> It previously dispatched to a dynamic `link_{domain}_to_{key}` backend method that
> existed for only two habit cases and failed at runtime everywhere else — that whole
> dispatch is gone.
>
> **A filtered key stamps its property on write.** Creating through a `filter_property`
> key (e.g. `create_relationship("essential_habits", goal, habit)`) merges
> `{filter_property: filter_value}` onto the edge via `setdefault` (an explicit caller
> value wins), so the edge is readable back through the same filtered key — without the
> stamp the read filter would make the just-created edge invisible. No-op for unfiltered
> keys. The canonical `link_goal_to_habit` writes via the catch-all `supporting_habits`
> key with an explicit `essentiality`. (PR #216.)
>
> **For an edge whose type is NOT a config method-key** (e.g. an explicit
> `DEPENDS_ON` with edge properties), call the backend batch path directly:
> ```python
> await backend.create_relationships_batch(
>     [(from_uid, to_uid, RelationshipName.DEPENDS_ON.value, properties)]
> )
> ```
> This is what `TasksService.create_task_dependency` does. After any edge-only mutation,
> publish the domain's `*Updated` event (e.g. `TaskUpdated`) so `UnifiedUserContext`
> caches invalidate. See `/docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md`.

### ⚠️ Phantom methods & keys — the #1 relationship trap

`UnifiedRelationshipService` has **no `__getattr__`**, so calling a method it does not
define raises `AttributeError`. Several historical bugs (PRs #198/#200/#201) were
services calling **methods that exist nowhere** — `create_choice_relationships`,
`get_principle_goals`, `get_task_prerequisites`, `get_goal_tasks`. Some were even
declared on a `*RelationshipOperations` **protocol** with no implementation — a
landmine, because the call type-checks but blows up (or, behind a swallowing
`try/except`, silently does nothing).

- **`get_related_uids(method_key, uid)` takes a CONFIG METHOD-KEY**, not a
  `RelationshipName`. Resolution is **exact-match** (`get_relationship_by_method`, no
  aliases) and **fails closed**: a wrong key (e.g. `"habits"` when the config defines
  `"inspired_habits"`/`"embodying_habits"`) returns `Result.fail`, not an exception —
  so the feature silently returns nothing. Pull keys from the domain's
  `DomainRelationshipConfig` (see *Domain Configurations*).
- **Before calling a relationship method, confirm it is actually defined** on
  `UnifiedRelationshipService` (or its mixins) — not merely declared on a protocol.
  If you need "goals guided by this principle," it is `get_related_uids("guided_goals", uid)`,
  not a bespoke `get_principle_goals`.
- **Mocked backends/services hide all of this** — an `AsyncMock` resolves any attribute
  and returns success for any key. **Guard relationship reads/writes with a real-Neo4j
  round-trip** that creates the edge and reads it back, with a negative control. See
  `tests/integration/test_choice_knowledge_edge_roundtrip.py`,
  `test_principle_cascade_reads_roundtrip.py`.

### Domain Relationships

The live "fetch all relationships in parallel" path is the per-domain
`<Domain>Relationships.fetch()` classmethod — a standalone frozen dataclass whose
`fetch()` calls `core/utils/generic_fetcher.py::fetch_relationships_parallel()` with
the domain's `*_QUERY_SPECS` constant. (`UnifiedRelationshipService` is passed in as
the query backend.)

```python
from core.services.tasks.task_relationships import TaskRelationships

# Fetch all task relationships for an entity (parallel execution)
rels = await TaskRelationships.fetch("task.123", service)
# Returns a TaskRelationships dataclass with all relationship UID lists

# Check for any knowledge connections
if rels.has_any_knowledge():
    knowledge = rels.get_combined_knowledge_uids()

# Check prerequisites
if rels.has_prerequisites():
    prereqs = rels.prerequisite_task_uids
```

### Path-Aware Queries (4 methods)

```python
# Get cross-domain context with typed path-aware entities
context = await service.get_cross_domain_context_typed("task.123")
# Returns TaskCrossContext with PathAwareKnowledge, PathAwareGoal, etc.

# Access typed relationships
for ku in context.required_knowledge:
    print(f"{ku.title} (distance: {ku.distance}, strength: {ku.path_strength})")

# Direct path-aware entity creation
entity = await service.get_path_aware_entity("task.123", distance=1)
```

### UserContext Planning (6 methods)

```python
# Get actionable items based on user context
# include_learning=True applies 20% score boost for entities whose knowledge
# relationships overlap with context.in_progress_knowledge_uids
actionable = await service.get_actionable_for_user(
    context=user_context,  # ~240 fields
    limit=10,
    include_learning=True  # boosts learning-relevant entities via in_progress_knowledge_uids
)

# Get blocked items with reasons
blocked = await service.get_blocked_for_user(context)
for item in blocked:
    print(f"{item['task'].title}: {item['blocking_reasons']}")

# Get learning-related items
learning = await service.get_learning_related_for_user(
    context,
    knowledge_focus="ku.python"
)

# Get goal-aligned items
goal_aligned = await service.get_goal_aligned_for_user(context, goal_uid="goal.123")
```

### Cross-domain linking — `create_relationship(method_key, ...)`

There is **one** write path for cross-domain links: `create_relationship`, keyed off an
explicit registry `method_key`. The earlier `link_to_knowledge` / `link_to_goal` /
`link_to_principle` convenience wrappers (which guessed the key from a hand-maintained
candidate list and silently `Result.fail`-ed when none matched) were removed — the facade
already knows exactly which edge it means, so it names the key directly.

```python
# Facade method names the explicit key; create_relationship validates it against the
# registry (fails closed on a typo), orients direction, and writes via the batch path.
await service.create_relationship(
    "knowledge",            # method_key in this domain's config -> APPLIES_KNOWLEDGE
    "task.123",
    "ku.python",
    {"knowledge_score_required": 0.9, "is_learning_opportunity": True},
)

await service.create_relationship(
    "contributes_to_goal",  # -> CONTRIBUTES_TO_GOAL (Task config)
    "task.123",
    "goal.456",
    {"contribution_percentage": 0.1},
)
```

Each Activity/Curriculum facade exposes domain-named wrappers (`link_task_to_goal`,
`link_choice_to_habit`, …) that supply the explicit key. The (facade, key) coverage is
guarded by `tests/unit/test_cross_domain_link_keys.py`; the real-Neo4j round-trips live in
`tests/integration/test_relationship_link_roundtrip.py`.

### Ownership is written by the create doors, not here

This service has no user→entity ownership writer. `(User)-[:OWNS]->` is THE universal
ownership edge (ADR-086), composed by the door that persists the owned node alongside the
node itself — ADR-086 § 1 grades each door against that rule, and its § 2 records what the
rule replaced.

> **No `RelationshipCreator` helper.** This method used to delegate to a generic
> `RelationshipCreator` infrastructure helper whose `create_relationship(backend_method=…)`
> and `get_{singular}_cross_domain_context` paths dispatched to dynamically-named backend
> methods (`getattr(backend, backend_method)`) — the same phantom-dispatch class as the old
> single `create_relationship` (#197) and `create_user_{domain}_relationship` (#205). Those
> paths were already dead (superseded by the registry-validated `create_relationship` and the
> config-driven `get_cross_domain_context`); the helper was **deleted in #208** and its one
> live method inlined here. Do not reintroduce a dispatch helper — name the
> `RelationshipName`/`method_key` explicitly and let the registry validate it.

### Semantic Operations (4 methods)

```python
# Create semantic relationship
await service.create_semantic_relationship(
    "task.123",
    "ku.python",
    semantic_type=SemanticRelationshipType.APPLIES_KNOWLEDGE,
    confidence=0.9,
    strength=0.8,
    evidence=["code_review", "test_coverage"]
)

# Get relationships by semantic type
rels = await service.get_by_semantic_type(
    "task.123",
    SemanticRelationshipType.APPLIES_KNOWLEDGE
)

# Calculate semantic score
score = await service.calculate_semantic_score("task.123", "ku.python")
```

### Cross-Domain Intelligence (2 methods)

```python
# Get full cross-domain context
context = await service.get_cross_domain_context("task.123")
# Returns dict with all related entities across domains

# Analyze cross-domain connections
analysis = await service.analyze_cross_domain_connections("task.123")
```

**Categorization — incident-edge attribution (PR #212).** `get_cross_domain_context`
returns one bucket per config `context_field_name`, each entry a
`{"uid", "title", "distance", "path_strength", "via_relationships"}` dict. The
traversal **always goes both directions**, and each related node is bucketed by the
edge **incident to it** (its last hop), not by any earlier edge in the path:

- The backend emits `incident_rel_type` (type of the last hop) and
  `incident_into_related` (`True` when the edge points *into* the node — the node is
  the relationship's object). A node lands in a mapping's bucket iff its incident
  edge matches the mapping's `relationship` **and** `direction`
  (`outgoing ⟺ into_related True`, `incoming ⟺ False`, `both ⟺ either`).
- This makes `depth` a real knob: a node *N* hops out is attributed by the edge that
  actually touches it (each entry carries its `distance`, so callers can filter to
  `distance == 1` for direct-only). `depth=2` therefore includes correctly-attributed
  transitive context — without the depth≥2 over-inclusion that center-relative marker
  matching once produced. The source is excluded from its own context (no cycle leaks).
- The per-config `bidirectional_relationships` field is **not** the direction signal
  here — direction is decided per-mapping by the incident edge. Mappings that share a
  relationship but differ by `target_label` are tried specific-label-first (the generic
  `Entity` bucket is the catch-all), so e.g. a Task reinforcing a habit lands in
  `reinforcing_tasks`, not the catch-all `reinforcing_habits`.

> ⚠️ **Buckets are NOT de-duped by uid — a node can recur once per path.** The producer
> Cypher does `collect(DISTINCT {uid, distance, path_strength, via_relationships, …})` —
> DISTINCT over the **whole path-metadata map**, not the uid. So at `depth ≥ 2` a node
> reachable by several distinct paths appears **once per path** in its bucket, each entry
> carrying that path's own `distance`/`path_strength`. Consumers MUST de-dup by uid.
> The path-aware `*CrossContext` family (`core/models/graph/path_aware_types.py`, built via
> the per-domain `from_categorized` factory seam) de-dups AND picks the **strongest** entry
> per uid (lowest `distance`, then highest `path_strength`) — the query has **no
> `ORDER BY`**, so first-seen is not the direct/closest path. Keeping the wrong entry
> misreports `distance`, `path_strength`, direct-connection counts, max path depth, and
> the direct-vs-indirect cascade split (counts also inflate if you skip de-dup entirely).
> See `_union_buckets` / `_path_rank` in `choices/_core_intelligence_mixin.py` (PR #218).

See: `core/services/relationships/_intelligence_mixin.py` (`get_cross_domain_context`,
`_incident_matches`, `_generic_label_last`) and `build_domain_context_with_paths` in
`adapters/persistence/neo4j/query/cypher/semantic_queries.py`.

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
    raw_data={"uid": "task.123", "title": "Fix bug", "status": "pending"},
    distance=1,
    path_strength=0.9,
    via_relationships=["APPLIES_KNOWLEDGE"]
)

# Batch create
entities = create_path_aware_entities_batch(Domain.TASKS, raw_data_list)

# Create cross-context
context = create_cross_context(
    source_domain=Domain.TASKS,
    source_uid="task.123",
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
rels = await DomainRelationships.fetch("task.123", service)

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
| `get_task_goals()` | `get_related_uids("contributes_to_goal", uid)` |
| `get_task_dependencies()` | `get_task_dependencies_for_user(uid, context)` (context-enriched, supports transitive via `include_transitive=True, max_depth=N`) |
| `get_task_cross_domain_context()` | `get_cross_domain_context_typed(uid)` |
| `create_knowledge_link()` | `create_relationship("knowledge", uid, ku_uid, props)` |

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
rels = await DomainRelationships.fetch("task.123", service)
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
result = await service.get_related_uids("knowledge", "task.123")
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
- SemanticRelationshipLinker composition (semantic relationship operations)
- Cross-domain context with path-aware entities
- UserContext-aware methods (get_actionable_for_user, etc.)
- Semantic relationship operations

### Direct Driver Pattern (Domain-Specific Services)

**For:** Curriculum (3) + MOC - LP, PS, KU, and MOC (Content/Org navigation)

**Characteristics:**
- AsyncDriver + GraphQueryExecutor (raw Cypher)
- Does NOT inherit from BaseService
- Complex curriculum-specific calculations:
  - `calculate_motivational_strength()` (LP)
  - `calculate_guidance_strength()` (PS)
  - `practice_completeness_score()` (PS)
  - `is_ready(completed_step_uids)` (PS)
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
2. **Event-Driven Updates**: Publish relationship change events
3. **Performance Optimization**: Batch operations for cross-domain context

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
await service.get_related_uids("knowledge", "task.123")
```

**See Also:** ADR-026 for the consolidation decision and implementation details.

---

**Pattern By:** Claude Code
**Date:** December 3, 2025 (Updated February 2026)
**Impact:** HIGH (67% code reduction, architectural consistency, single source of truth)
**Risk:** LOW (incremental migration, no translation layer)
