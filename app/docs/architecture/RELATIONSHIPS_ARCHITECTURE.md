---
title: Relationships Architecture
updated: 2026-03-03
status: current
category: architecture
version: 2.0.0
tags: [architecture, relationships, unified-service, infrastructure, lateral-relationships]
related: [UNIFIED_RELATIONSHIP_SERVICE.md, ADR-028]
---

# Relationships Architecture

## Two Layers

SKUEL's relationship system operates at two levels:

| Layer | Where | Purpose |
|-------|-------|---------|
| **Service layer** | `UnifiedRelationshipService` | Config-driven CRUD, planning, intelligence, life-path |
| **Backend layer** | Domain backends + `_RelationshipCrudMixin` / `_RelationshipQueryMixin` | Low-level Cypher execution |

Domain-specific relationship Cypher belongs on the **domain backend**. Cross-domain aggregation belongs in **services**.

---

## UnifiedRelationshipService

**Location:** `core/services/relationships/unified_relationship_service.py`

All 13 entity-owning domains (Finance excluded — standalone bookkeeping) expose relationships via `self.relationships` on their facade service. Each instance is constructed with a backend + a `DomainRelationshipConfig` from the registry.

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

service = UnifiedRelationshipService(
    backend=tasks_backend,   # REQUIRED — domain protocol backend
    config=TASKS_CONFIG,     # REQUIRED — from relationship_registry
    graph_intel=graph_intel, # Optional — enables intent-based queries
)

# Usage (via domain facade)
knowledge = await tasks_service.relationships.get_related_uids("knowledge", task_uid)
context   = await tasks_service.relationships.get_cross_domain_context_typed(task_uid)
actionable = await tasks_service.relationships.get_actionable_for_user(user_context)
```

### Mixin Architecture

`UnifiedRelationshipService` is assembled from six focused mixins:

```
UnifiedRelationshipService[Ops, Model, DtoType]
    ├── PlanningMixin              (~430 lines) — UserContext-aware planning + scoring
    ├── DomainPlanningMixin        (~290 lines) — per-Activity-Domain planning methods
    ├── LifePathMixin              (~370 lines) — SERVES_LIFE_PATH management
    ├── IntelligenceMixin          (~400 lines) — cross-domain context, semantic queries
    ├── OrderedRelationshipsMixin  (~550 lines) — curriculum hierarchy + edge metadata
    ├── BatchOperationsMixin       (~190 lines) — N+1 elimination
    └── BaseService[Ops, Model]    — CRUD, search, config
```

### Key Methods by Mixin

**Shell (generic CRUD):**
- `get_related_uids(relationship_key, entity_uid)` → `Result[list[str]]`
- `has_relationship(relationship_key, entity_uid)` → `Result[bool]`
- `count_related(relationship_key, entity_uid)` → `Result[int]`
- `create_relationship(relationship_key, from_uid, to_uid, properties)` → `Result[bool]`
- `delete_relationship(relationship_key, from_uid, to_uid)` → `Result[bool]`
- `fetch_all_relationships(entity_uid)` → `Result[dict[str, list[str]]]`
- `link_to_knowledge(entity_uid, knowledge_uid, **properties)` → `Result[bool]`
- `link_to_goal(entity_uid, goal_uid, **properties)` → `Result[bool]`
- `link_to_principle(entity_uid, principle_uid, **properties)` → `Result[bool]`

**BatchOperationsMixin** — eliminates N+1 queries:
- `batch_has_relationship(relationship_key, entity_uids)` → `Result[dict[str, bool]]`
- `batch_count_related(relationship_key, entity_uids)` → `Result[dict[str, int]]`
- `batch_get_related_uids(relationship_key, entity_uids)` → `Result[dict[str, list[str]]]`

**OrderedRelationshipsMixin** — curriculum hierarchy:
- `get_ordered_related_uids(relationship_key, entity_uid)` → `Result[list[str]]`
- `get_related_with_metadata(relationship_key, entity_uid)` → `Result[list[dict]]`
- `reorder_relationships(relationship_key, entity_uid, new_order)` → `Result[bool]`
- `create_relationship_with_properties(...)` → `Result[bool]`
- `get_hierarchical_children(relationship_key, entity_uid, depth)` → `Result[list[dict]]`

**IntelligenceMixin** — graph intelligence:
- `get_cross_domain_context(entity_uid, depth, min_confidence)` → `Result[dict]`
- `get_cross_domain_context_typed(entity_uid, depth, min_confidence)` → `Result[dict]`
- `get_completion_impact(entity_uid, context)` → `Result[dict]`
- `get_with_semantic_context(entity_uid)` → `Result[dict]`
- `create_semantic_relationship(...)` → `Result[bool]`
- `find_by_semantic_filter(semantic_type, context)` → `Result[list[Model]]`

**LifePathMixin** — "everything flows toward the life path":
- `link_to_life_path(entity_uid, life_path_uid, contribution_type, score, notes)` → `Result[bool]`
- `get_life_path_contributors(life_path_uid, entity_types, min_score)` → `Result[list]`
- `calculate_contribution_score(entity_uid, life_path_uid)` → `Result[float]`
- `update_contribution_score(entity_uid, life_path_uid, new_score)` → `Result[bool]`
- `remove_life_path_link(entity_uid, life_path_uid)` → `Result[bool]`

**PlanningMixin** — generic UserContext-aware planning:
- `get_actionable_for_user(context, limit, include_learning)` → `Result[list[Any]]`
- `get_blocked_for_user(context, limit)` → `Result[list[dict]]`
- `get_learning_related_for_user(context, limit)` → `Result[list[Any]]`
- `get_goal_aligned_for_user(context, goal_uid, limit)` → `Result[list[Any]]`

**DomainPlanningMixin** — per-Activity-Domain planning (called by `DailyPlanningMixin`):
- `get_actionable_tasks_for_user(context, limit)` → `Result[list[ContextualTask]]`
- `get_at_risk_habits_for_user(context, limit)` → `Result[list[ContextualHabit]]`
- `get_upcoming_events_for_user(context, limit)` → `Result[list[ContextualEvent]]`
- `get_advancing_goals_for_user(context, limit)` → `Result[list[ContextualGoal]]`
- `get_pending_decisions_for_user(context, limit)` → `Result[list[ContextualChoice]]`
- `get_aligned_principles_for_user(context, limit)` → `Result[list[ContextualPrinciple]]`

---

## DomainRelationshipConfig

**Location:** `core/models/relationship_registry.py`

`DomainRelationshipConfig` is the single source of truth for a domain's relationship definitions. One config per domain, instantiated at module load.

```python
@dataclass(frozen=True)
class DomainRelationshipConfig:
    domain: Domain
    entity_label: str
    dto_class: type
    model_class: type
    ownership_relationship: RelationshipName | None
    relationships: tuple[UnifiedRelationshipDefinition, ...] = ()
    prerequisite_relationship_names: tuple[RelationshipName, ...] = ()
    enables_relationship_names: tuple[RelationshipName, ...] = ()
    bidirectional_relationships: tuple[RelationshipName, ...] = ()
    semantic_types: tuple[SemanticRelationshipType, ...] = ()
    scoring_weights: dict[str, float] = ...
    default_context_intent: QueryIntent = QueryIntent.HIERARCHICAL
    intent_mappings: dict[str, QueryIntent] = ...
    is_shared_content: bool = False  # True for KU, LS, LP
```

**Named configs:** `TASKS_CONFIG`, `GOALS_CONFIG`, `HABITS_CONFIG`, `EVENTS_CONFIG`, `CHOICES_CONFIG`, `PRINCIPLES_CONFIG`, `KU_CONFIG`, `LS_CONFIG`, `LP_CONFIG`

---

## RelationshipName Enum

**Location:** `core/models/relationship_names.py`

70+ typed relationship names, organised by domain. SKUEL rule SKUEL013 requires using `RelationshipName` enum values — no string literals in relationship Cypher.

**Key groupings:**

| Group | Count | Examples |
|-------|-------|---------|
| Knowledge | 18 | `REQUIRES_KNOWLEDGE`, `APPLIES_KNOWLEDGE`, `REINFORCES_KNOWLEDGE`, `ENABLES_KNOWLEDGE` |
| Task | 14 | `DEPENDS_ON`, `BLOCKS`, `BLOCKED_BY`, `CONTRIBUTES_TO_GOAL`, `FULFILLS_GOAL` |
| Goal | 12 | `SUBGOAL_OF`, `GUIDED_BY_PRINCIPLE`, `SUPPORTS_GOAL`, `ALIGNED_WITH_PATH` |
| Habit | 10 | `REQUIRES_PREREQUISITE_HABIT`, `ENABLES_HABIT`, `EMBODIES_PRINCIPLE` |
| Principle | 5 | `GROUNDS_PRINCIPLE`, `GUIDED_BY_KNOWLEDGE` |
| Choice | 6 | `INFORMS_CHOICE` |
| User / Ownership | 12 | `OWNS`, `MEMBER_OF`, `SHARES_WITH`, `SHARED_WITH_GROUP`, `ULTIMATE_PATH` |
| Curriculum | 5 | `ORGANIZES`, `REQUIRES_PREREQUISITE`, `HAS_NARROWER`, `HAS_BROADER` |
| Life Path | 2 | `SERVES_LIFE_PATH`, `ULTIMATE_PATH` |
| Exercise / Group | 3 | `FOR_GROUP`, `FULFILLS_EXERCISE`, `ASSIGNED_TO` |
| Content / Processing | 4 | `REPORT_FOR`, `FULFILLS_PROJECT`, `PROCESSED_BY` |
| Lateral | 13 | `BLOCKS`, `BLOCKED_BY`, `PREREQUISITE_FOR`, `DEPENDS_ON`, `ALTERNATIVE_TO`, `COMPLEMENTARY_TO`, `SIBLING`, `RELATED_TO` |

---

## Domain Coverage

| Category | Domains | `self.relationships` | Notes |
|----------|---------|----------------------|-------|
| **Activity (6)** | Tasks, Goals, Habits, Events, Choices, Principles | ✅ | Config-driven via registry |
| **Curriculum (3)** | KU, LS, LP | ✅ | `is_shared_content=True`; ordered relationships for hierarchy |
| **Submissions + Feedback** | Submissions, Journals | ✅ | `SubmissionsBackend` owns SHARES_WITH Cypher |
| **Life Path** | LifePath | ✅ | ULTIMATE_PATH + SERVES_LIFE_PATH |
| **Finance** | Finance | ❌ | Standalone bookkeeping — no relationship service |

---

## Domain Backends: Domain-Specific Relationship Cypher

Complex relationship Cypher that is domain-specific belongs on the domain backend, not in services.

**Rule:** domain-specific relationship Cypher → domain backend. Cross-domain aggregation → service.

| Backend | Domain-Specific Relationship Methods |
|---------|--------------------------------------|
| `TasksBackend` | `link_task_to_knowledge()`, `link_task_to_goal()`, `link_task_to_principle()` |
| `GoalsBackend` | `add_milestone()`, `link_goal_to_habit()`, `link_goal_to_knowledge()`, `link_goal_to_principle()` |
| `HabitsBackend` | `link_habit_to_knowledge()`, `link_habit_to_principle()` |
| `EventsBackend` | `link_event_to_task()`, `link_event_to_principle()` |
| `ChoicesBackend` | `link_choice_to_principle()`, `link_choice_to_goal()` |
| `KuBackend` | `organize()`, `unorganize()`, `reorder()`, `get_organized_children()`, `find_organizers()`, `list_root_organizers()`, `is_organizer()` |
| `SubmissionsBackend` | `share_submission()`, `unshare_submission()`, `get_shared_with_users()`, `get_submissions_shared_with_me()`, `set_visibility()`, `check_access()`, `verify_shareable()` |
| `LpBackend` | `get_paths_containing_ku()`, `get_ku_mastery_progress()` |
| `ExerciseBackend` | `link_to_curriculum()`, `unlink_from_curriculum()`, `get_required_knowledge()` |

---

## Backend Relationship Mixins

`UniversalNeo4jBackend` composes two relationship mixins at the persistence layer:

### `_RelationshipCrudMixin` (`adapters/persistence/neo4j/_relationship_crud_mixin.py`)

Creation, deletion, validation:

- `create_relationship(from_uid, to_uid, relationship_type, properties)` → `Result[bool]`
- `delete_relationship(from_uid, to_uid, relationship_type)` → `Result[bool]`
- `delete_relationships_batch(relationships_list)` → `Result[int]`
- `create_relationships_batch(relationships_list)` → `Result[int]`
- `create_user_relationship(user_uid, entity_uid, properties)` → `Result[bool]`
- `has_relationship(uid, relationship_type, direction)` → `Result[bool]`
- `count_related(uid, relationship_type, direction)` → `Result[int]`

### `_RelationshipQueryMixin` (`adapters/persistence/neo4j/_relationship_query_mixin.py`)

Queries, edge metadata, fluent API:

- `get_related_entities(uid, relationship_type, direction, limit)` → `Result[list[T]]`
- `get_related_uids(uid, relationship_type, direction)` → `Result[list[str]]`
- `get_relationship_metadata(uid, relationship_type, direction)` → `Result[list[dict]]`
- `update_relationship_properties(from_uid, to_uid, relationship_type, properties)` → `Result[bool]`
- `get_relationships_batch(uids, relationship_type, direction)` → `Result[dict[str, list[T]]]`
- `count_relationships_batch(uids, relationship_type, direction)` → `Result[dict[str, int]]`
- `get_edge_metadata(uid, relationship_type, direction, target_uid)` → `Result[EdgeMetadata]`
- `update_edge_metadata(from_uid, to_uid, relationship_type, metadata)` → `Result[bool]`
- `relate(uid)` → `RelationshipBuilder` (fluent API)
- Convenience wrappers: `get_prerequisites()`, `get_enables()`, `get_related()`, `get_children()`, `get_parent()`, `get_depends_on()`, `get_blocks()`

---

## Lateral Relationships

Lateral relationships capture semantics that hierarchies cannot: dependencies between siblings, alternatives, synergistic pairings, and semantic connections across branches. They are core architecture — graph databases excel at relationships precisely because a tree structure cannot express "A must complete before B", "A and B are alternatives", or "A and B complement each other".

**Location:** `core/services/lateral_relationships/lateral_relationship_service.py`

### LateralRelationshipService API

**Key methods:**
- `create_lateral_relationship(source_uid, target_uid, relationship_type, metadata, validate=True, auto_inverse=True)` → `Result[bool]`
  - `validate=True`: checks both entities exist, detects circular dependencies (`BLOCKS`/`PREREQUISITE_FOR`), rejects duplicates
  - `auto_inverse=True`: auto-creates the inverse (`BLOCKS` → also creates `BLOCKED_BY` in the reverse direction)
- `delete_lateral_relationship(source_uid, target_uid, relationship_type)` → `Result[bool]`
- `get_lateral_relationships(entity_uid, relationship_types, direction)` → `Result[list[dict]]` — filtered query with direction control (`"incoming"` / `"outgoing"` / `"both"`)
- `get_blocking_chain(entity_uid)` → `Result[list[dict]]` — transitive blocking dependency chain
- `get_alternatives_with_comparison(entity_uid)` → `Result[dict]` — side-by-side comparison data
- `get_relationship_graph(entity_uid, depth)` → `Result[dict]` — Vis.js network format (nodes + edges)

### Lateral Relationship Type Taxonomy

**Dependency relationships** (asymmetric — inverse created automatically):

| Type | Inverse | Use Case |
|------|---------|---------|
| `BLOCKS` | `BLOCKED_BY` | Task A must complete before Task B |
| `PREREQUISITE_FOR` | `DEPENDS_ON` | KU A required before KU B |
| `ENABLES` | `ENABLED_BY` | Completing A unlocks B |

**Semantic relationships** (symmetric):

| Type | Use Case |
|------|---------|
| `ALTERNATIVE_TO` | Mutually exclusive options (Career Path A vs B) |
| `COMPLEMENTARY_TO` | Synergistic pairing (Meditation + Exercise habits) |
| `RELATED_TO` | General association between related entities |
| `SIMILAR_TO` | Two learning paths covering similar content |
| `CONFLICTS_WITH` | Mutually exclusive choices |

**Structural relationships** (symmetric — derived from hierarchy, made explicit for performance):

| Type | Use Case |
|------|---------|
| `SIBLING` | Two entities sharing the same parent |
| `COUSIN` | Same depth, shared grandparent |

**Associative relationships:**

| Type | Direction | Use Case |
|------|-----------|---------|
| `RECOMMENDED_WITH` | Symmetric | Collaborative filtering — users who completed A also completed B |
| `STACKS_WITH` | Directional | Habit chaining — do habit A after habit B |

**Phase 5 deployed types** (fully tested across 9 domains — Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP):
`BLOCKS/BLOCKED_BY`, `PREREQUISITE_FOR/DEPENDS_ON`, `ALTERNATIVE_TO`, `COMPLEMENTARY_TO`, `SIBLING`, `RELATED_TO`

The extended types (`ENABLES`, `SIMILAR_TO`, `CONFLICTS_WITH`, `COUSIN`, `RECOMMENDED_WITH`, `STACKS_WITH`) are defined in `RelationshipName` and available to services but not yet wired to Phase 5 UI endpoints.

### Domain-Specific Lateral Services

Each domain wraps `LateralRelationshipService` to add ownership verification and domain business rules:

```python
class GoalsLateralService:
    def __init__(self, driver, goals_service):
        self.lateral_service = LateralRelationshipService(driver)
        self.goals_service = goals_service

    async def create_blocking_relationship(
        self, blocker_uid: str, blocked_uid: str, reason: str, user_uid: str
    ) -> Result[bool]:
        for uid in [blocker_uid, blocked_uid]:
            if (await self.goals_service.verify_ownership(uid, user_uid)).is_error:
                return Err(...)
        return await self.lateral_service.create_lateral_relationship(
            blocker_uid, blocked_uid, LateralRelationType.BLOCKS,
            metadata={"reason": reason}, auto_inverse=True
        )
```

### Key Cypher Patterns

**Transitive blocking chain:**
```cypher
MATCH path = (blocker)-[:BLOCKS*1..5]->(target {uid: $target_uid})
RETURN [node in nodes(path) | {uid: node.uid, title: node.title}] AS chain,
       length(path) AS depth
ORDER BY depth DESC
```

**Alternatives with comparison:**
```cypher
MATCH (choice {uid: $choice_uid})-[:ALTERNATIVE_TO]-(alternative)
RETURN alternative.uid, alternative.title, alternative.description
```

**Complementary recommendations:**
```cypher
MATCH (habit {uid: $habit_uid})-[:COMPLEMENTARY_TO]-(complementary)
WHERE NOT (user:User)-[:OWNS]->(complementary)
RETURN complementary.uid, complementary.title
ORDER BY complementary.synergy_score DESC
```

### Performance: Explicit vs. Derived

| Scenario | Approach | Reason |
|----------|----------|--------|
| Query siblings once | Derive from hierarchy | No storage overhead |
| Query siblings 100+/day | Create explicit `SIBLING` | Faster lookup |
| Blocking relationship | Always explicit | Carries semantic meaning |
| Semantic similarity | Always explicit | Cannot derive from hierarchy |
| First-time cousin query | Derive from hierarchy | Avoid premature optimisation |

**Rule:** Start with derived queries. Add explicit relationships when (a) query is performance-critical, (b) relationship has semantic meaning beyond structure, or (c) it enables domain features (habit stacking, alternatives).

### UI Components

| Component | File | Purpose |
|-----------|------|---------|
| `BlockingChainView` | `ui/patterns/relationships/blocking_chain.py` | Vertical flow chart with depth-based layout |
| `AlternativesComparisonGrid` | `ui/patterns/relationships/alternatives_grid.py` | Side-by-side comparison table |
| `RelationshipGraphView` | `ui/patterns/relationships/graph_view.py` | Interactive Vis.js force-directed graph |
| `EntityRelationshipsSection` | `ui/patterns/relationships/__init__.py` | Drop-in section for any entity detail page |

### API Endpoints (per domain)

- `GET /api/{domain}/{uid}/lateral/chain` — Blocking chain data
- `GET /api/{domain}/{uid}/lateral/alternatives/compare` — Comparison data
- `GET /api/{domain}/{uid}/lateral/graph` — Vis.js format (nodes + edges)

---

## See Also

- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) — complete service documentation
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md) — Phase 5 vis.js integration
- [ADR-028](/docs/decisions/ADR-028.md) — KU & MOC migration rationale
