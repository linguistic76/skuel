---
title: Relationships Architecture
updated: 2026-07-29
status: current
category: architecture
version: 2.0.0
tags: [architecture, relationships, unified-service, infrastructure, lateral-relationships]
related: [UNIFIED_RELATIONSHIP_SERVICE.md, ADR-028]
related_skills: [vis-network]
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

`UnifiedRelationshipService` is assembled from three focused mixins:

```
UnifiedRelationshipService[Ops, Model, DtoType]
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
- `create_relationship(relationship_key, from_uid, to_uid, properties)` → `Result[bool]` — **the single cross-domain link write path.** Routes through `backend.create_relationships_batch` with the registry `spec` for `relationship_key`, orients direction via `_orient_edge`, and **fails closed** on an unknown key. Facade `link_{domain}_to_{key}` methods call this with their explicit key. (Root-fixed PR #197: historically it dispatched to a dynamic `link_{domain}_to_{key}` backend method that existed for only two habit cases — that dispatch is gone.) See [UNIFIED_RELATIONSHIP_SERVICE.md](../patterns/UNIFIED_RELATIONSHIP_SERVICE.md).
- `delete_relationship(relationship_key, from_uid, to_uid)` → `Result[bool]`

> The `link_to_knowledge` / `link_to_goal` / `link_to_principle` candidate-list wrappers were **removed** — they guessed the key from a hand-maintained list and silently `Result.fail`-ed on a coverage gap or picked the wrong edge when a domain had several to the same target. Facades call `create_relationship` with the explicit key instead; coverage is guarded by `tests/unit/test_cross_domain_link_keys.py`.

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
- `create_semantic_relationship(...)` → `Result[bool]`
- `find_by_semantic_filter(semantic_type, context)` → `Result[list[Model]]`


---

## DomainRelationshipConfig

**Location:** `core/models/relationship_registry.py`

`DomainRelationshipConfig` is the single source of truth for a domain's relationship definitions. One config per domain, instantiated at module load.

```python
@dataclass(frozen=True)
class DomainRelationshipConfig:
    domain: Domain
    entity_label: NeoLabel
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
    is_shared_content: bool = False  # True for KU, PS, LP
```

**Named configs:** `TASKS_CONFIG`, `GOALS_CONFIG`, `HABITS_CONFIG`, `EVENTS_CONFIG`, `CHOICES_CONFIG`, `PRINCIPLES_CONFIG`, `KU_CONFIG`, `PS_CONFIG`, `LP_CONFIG`

---

## RelationshipName Enum

**Location:** `core/models/relationship_names.py`

80+ typed relationship names, organised by domain. SKUEL rule SKUEL013 requires using `RelationshipName` enum values — no string literals in relationship Cypher. Cypher query strings use f-string interpolation: `f"[:{RelationshipName.X.value}]"`.

**Key groupings:**

| Group | Count | Examples |
|-------|-------|---------|
| Knowledge | 18 | `REQUIRES_KNOWLEDGE`, `APPLIES_KNOWLEDGE`, `REINFORCES_KNOWLEDGE`, `ENABLES_KNOWLEDGE` |
| Task | 14 | `HAS_SUBTASK`, `SUBTASK_OF`, `DEPENDS_ON`, `BLOCKS`, `BLOCKED_BY`, `CONTRIBUTES_TO_GOAL`, `FULFILLS_GOAL` |
| Goal | 12 | `HAS_SUBGOAL`, `SUBGOAL_OF`, `GUIDED_BY_PRINCIPLE`, `SUPPORTS_GOAL`, `ALIGNED_WITH_PATH` |
| Habit | 12 | `HAS_SUBHABIT`, `SUBHABIT_OF`, `REQUIRES_PREREQUISITE_HABIT`, `ENABLES_HABIT`, `EMBODIES_PRINCIPLE`, `UNLOCKED_ACHIEVEMENT`, `EARNED_BADGE` |
| Event | 5 | `HAS_SUBEVENT`, `SUBEVENT_OF`, `CONFLICTS_WITH`, `FUNDS_EVENT`, `ATTENDS` |
| Principle | 9 | `HAS_SUBPRINCIPLE`, `SUBPRINCIPLE_OF`, `SUPPORTS_PRINCIPLE`, `GUIDES_GOAL`, `GUIDES_CHOICE`, `REFLECTS_ON`, `REVEALS_CONFLICT` |
| Choice | 8 | `HAS_SUBCHOICE`, `SUBCHOICE_OF`, `ALIGNED_WITH_PRINCIPLE`, `CONFLICTS_WITH_PRINCIPLE`, `AFFECTS_GOAL`, `INFORMS_CHOICE` |
| User / Ownership | 12 | `OWNS`, `MEMBER_OF`, `SHARES_WITH`, `SHARED_WITH_GROUP`, `ULTIMATE_PATH` |
| Curriculum | 5 | `ORGANIZES`, `REQUIRES_PREREQUISITE`, `HAS_NARROWER`, `HAS_BROADER` |
| Life Path | 3 | `SERVES_LIFE_PATH`, `ULTIMATE_PATH`, `ALIGNMENT_SNAPSHOT` |
| Exercise / Group | 3 | `FOR_GROUP`, `FULFILLS_EXERCISE`, `ASSIGNED_TO` |
| Resource | 1 | `CITES_RESOURCE` — `(PathStep/Ku)-[:CITES_RESOURCE {context}]->(Resource)` |
| Content / Processing | 3 | `REPORT_FOR`, `TRANSCRIBED_FOR`, `HAS_SCHEDULE` |
| Lateral | 13 | `BLOCKS`, `BLOCKED_BY`, `PREREQUISITE_FOR`, `DEPENDS_ON`, `ALTERNATIVE_TO`, `COMPLEMENTARY_TO`, `SIBLING`, `RELATED_TO` |

---

## Domain Coverage

| Category | Domains | `self.relationships` | Notes |
|----------|---------|----------------------|-------|
| **Activity (6)** | Tasks, Goals, Habits, Events, Choices, Principles | ✅ | Config-driven via registry |
| **Curriculum (3)** | KU, PS, LP | ✅ | `is_shared_content=True`; ordered relationships for hierarchy |
| **UserEntry** | UserEntry | ✅ | SHARES_WITH owned by the entity-agnostic `SharingBackend` (ADR-042) |
| **Life Path** | LifePath | ✅ | ULTIMATE_PATH + SERVES_LIFE_PATH + ALIGNMENT_SNAPSHOT |
| **Finance** | Finance | ❌ | Standalone bookkeeping — no relationship service |

---

## Domain Backends: Domain-Specific Relationship Cypher

Complex relationship Cypher that is domain-specific belongs on the domain backend, not in services.

**Rule:** domain-specific relationship Cypher → domain backend. Cross-domain aggregation → service.

| Backend | Domain-Specific Relationship Methods |
|---------|--------------------------------------|
| `TasksBackend` | Hierarchy via `_HierarchyMixin` (subtask ops) |
| `GoalsBackend` | Hierarchy via `_HierarchyMixin` (subgoal ops) |
| `KuBackend` | `organize()`, `unorganize()`, `reorder()`, `get_organized_children()`, `find_organizers()`, `list_root_organizers()`, `is_organizer()` |
| `SharingBackend` (entity-agnostic, ADR-042) | `create_share()`, `delete_share()`, `update_visibility()`, `query_access()`, `query_shareable_status()`, `query_shared_with_users()`, `query_shared_with_me()`, `create_group_share()` |
| `LpBackend` | `get_paths_containing_ku()`, `get_ku_mastery_progress()` |
| `ExerciseBackend` | `link_to_curriculum()`, `unlink_from_curriculum()`, `get_required_knowledge()` |

**Note:** Cross-domain relationship creation (task→knowledge, goal→habit, goal→principle, etc.) is handled by `UnifiedRelationshipService`, not domain backends. Service facades delegate to `self.relationships` (UnifiedRelationshipService).

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

Core queries, edge metadata, fluent `relate()` entry point:

- `get_related_entities(uid, relationship_type, direction, limit)` → `Result[list[T]]`
- `get_related_uids(uid, relationship_type, direction)` → `Result[list[str]]`
- `get_relationship_metadata(uid, relationship_type, direction)` → `Result[list[dict]]`
- `update_relationship_properties(from_uid, to_uid, relationship_type, properties)` → `Result[bool]`
- `get_relationships_batch(uids, relationship_type, direction)` → `Result[dict[str, list[T]]]`
- `count_relationships_batch(uids, relationship_type, direction)` → `Result[dict[str, int]]`
- `get_edge_metadata(uid, relationship_type, direction, target_uid)` → `Result[EdgeMetadata]`
- `update_edge_metadata(from_uid, to_uid, relationship_type, metadata)` → `Result[bool]`
- `relate()` → `RelationshipBuilder` (fluent API)

### `_RelationshipOrderedMixin` (`adapters/persistence/neo4j/_relationship_ordered_mixin.py`)

Ordered/hierarchical traversals and lateral-getter convenience wrappers:

- `get_ordered_related_uids(entity_label, entity_uid, relationship_type, direction, order_by_property, order_direction)` → `Result[list[str]]`
- `get_related_with_metadata(...)` → `Result[list[dict]]`
- `reorder_relationships(..., target_uid_sequence, sequence_property)` → `Result[int]`
- `create_relationship_with_properties(entity_uid, target_uid, relationship_type, direction, edge_properties)` → `Result[bool]`
- `get_hierarchical_children_single(...)` / `get_hierarchical_children_two_level(...)` / `get_hierarchical_children_deep(...)` → `Result[list[dict]]`
- Convenience wrappers: `get_prerequisites()`, `get_enables()`, `get_related()`, `get_children()`, `get_parent()`, `get_depends_on()`, `get_blocks()` — forward to `get_related_entities` via MRO

---

## Lateral Relationships

Lateral relationships capture semantics that hierarchies cannot: dependencies between siblings, alternatives, synergistic pairings, and semantic connections across branches. They are core architecture — graph databases excel at relationships precisely because a tree structure cannot express "A must complete before B", "A and B are alternatives", or "A and B complement each other".

**Location:** `core/services/lateral_relationships/lateral_relationship_service.py`
**Backend:** `adapters/persistence/neo4j/backends/collab_backends.py` → `LateralRelationshipBackend` (14 Cypher methods)
**Protocol:** `core/ports/service_protocols.py` → `LateralRelationshipBackendOperations`

### LateralRelationshipService API

**All 8 public methods.** The `own?` column is the `user_uid` / `domain_service` pair — the ownership hook that replaced the per-domain wrappers (below). This list is exhaustive on purpose: a partial enumeration is how a caller ends up on an unverified method.

| Method (trailing `user_uid=None, domain_service=None` where `own?` is ✅) | own? | Returns |
|---|:--:|---|
| `create_lateral_relationship(source_uid, target_uid, relationship_type, metadata=None, validate=True, auto_inverse=True, …)` | ✅ | `Result[bool]` |
| `delete_lateral_relationship(source_uid, target_uid, relationship_type, delete_inverse=True, …)` | ✅ | `Result[bool]` |
| `get_lateral_relationships(entity_uid, relationship_types=None, direction="outgoing", include_metadata=True, …)` | ✅ | `Result[list[LateralRelationshipItem]]` |
| `get_siblings(entity_uid, include_explicit_only=False, …)` | ✅ | `Result[list[dict[str, Any]]]` |
| `get_blocking_chain(entity_uid, max_depth=10, …)` | ✅ | `Result[BlockingChainResult]` |
| `get_alternatives_with_comparison(entity_uid, …)` | ✅ | `Result[list[AlternativeComparisonItem]]` |
| `get_relationship_graph(entity_uid, depth=2, relationship_types=None, …)` | ✅ | `Result[RelationshipGraphData]` |
| `get_cousins(entity_uid, degree=1)` | ❌ | `Result[list[dict[str, Any]]]` |

- `validate=True`: checks both entities exist, detects circular dependencies (`BLOCKS`/`PREREQUISITE_FOR`), rejects duplicates
- `auto_inverse=True` / `delete_inverse=True`: also writes/removes the inverse edge when the type is asymmetric
- `direction`: `"incoming"` / `"outgoing"` / `"both"`
- Returns are `TypedDict`s from `core/ports/query_types.py` **except** `get_siblings` / `get_cousins`, which still return raw `dict`s

> [!IMPORTANT]
> **The ownership check is opt-in and fails open.** Both parameters default to `None`, and every ✅ method guards with `if user_uid and domain_service:` — so verification runs only when **both** are supplied, and a caller that omits either performs the write or read with no enforcement at all. Passing both is what produces the required not-found; `None` is the deliberate shared-content path (curriculum KU/PS/LP). For a user-owned domain, always pass both.
>
> Every ✅ method routes its check through one private helper, `_verify_entity_access(entity_uid, user_uid, domain_service)` — the single gate on this service. Add a read method and call it; do not re-inline the guard.
>
> `get_cousins` is the one remaining ❌: it accepts neither parameter, so it cannot enforce ownership even when a caller wants to. No route exposes it and it has no caller anywhere in the tree, so it is reachable only by a direct caller — wire the pair in if you ever give it one.

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

**Phase 5 deployed types** (fully tested across 9 domains — Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP):
`BLOCKS/BLOCKED_BY`, `PREREQUISITE_FOR/DEPENDS_ON`, `ALTERNATIVE_TO`, `COMPLEMENTARY_TO`, `SIBLING`, `RELATED_TO`

The extended types (`ENABLES`, `SIMILAR_TO`, `CONFLICTS_WITH`, `COUSIN`, `RECOMMENDED_WITH`, `STACKS_WITH`) are defined in `RelationshipName` and available to services but not yet wired to Phase 5 UI endpoints.

### Per-Domain Wiring — One Service, No Wrappers

**There are no per-domain lateral services.** The 9 wrappers (`GoalsLateralService`, `TasksLateralService`, …) were deleted in `e8818dc26` ("Unify lateral relationships"), eliminating ~3,400 lines of boilerplate. Their two real jobs moved into shared machinery:

| Wrapper job | Now lives in |
|-------------|--------------|
| Relationship metadata (symmetry, inverses, constraints) | `RelationshipName` + `LateralRelationshipSpec` registry — `core/models/relationship_registry.py` (`get_lateral_spec`) |
| Ownership verification | `OwnershipVerifier` protocol (`core/ports/service_protocols.py`) — one `verify_ownership` method, satisfied structurally by all 6 Activity facades |

`LateralRelationshipService` stays domain-agnostic and takes an entity uid. `LateralRouteFactory` holds the domain's verifier and passes it per call, so the core service never learns about domains:

```python
# adapters/inbound/lateral_routes.py — the whole per-domain surface
_LATERAL_DOMAINS: list[tuple[str, str, str | None]] = [
    ("tasks", "Task", "tasks"),          # 3rd item = ownership-verifier attr
    ...
    ("ku", "Knowledge Unit", None),      # curriculum: shared, no ownership check
]

factory = LateralRouteFactory(
    domain=domain,
    lateral_service=orchestrator.lateral_service,  # the one LateralRelationshipService
    entity_name=entity_name,
    domain_service=domain_service,                 # OwnershipVerifier | None
)
```

The composition root exposes exactly one lateral field — `services.lateral` — plus `services.lateral_orchestrator`; there are no `services.{domain}_lateral` fields.

**Never reintroduce a `{domain}_lateral_service.py` wrapper** — that is the pattern One Path Forward removed.

**Adding a domain takes two edits, not one.** The `_LATERAL_DOMAINS` entry registers the routes; the third tuple item is only a *lookup key* into `LateralRelationshipsOrchestrator._domain_services`, which is a fixed map built from explicit constructor parameters:

```python
# core/orchestrator/lateral_relationships_orchestrator.py
self._domain_services: dict[str, OwnershipVerifier] = {
    "tasks": tasks_service, "goals": goals_service, "habits": habits_service,
    "events": events_service, "choices": choices_service, "principles": principles_service,
}
```

`get_domain_service()` is a plain `.get(domain)`, so a slug absent from that map returns `None` **silently** — and `None` means "shared/curriculum, no ownership check". For a **user-owned** domain you must also add the service to the orchestrator's constructor and map, and wire it in the composition root. Registering the route entry alone would expose the new domain's entities to every authenticated user.

### Ownership Coverage

`LateralRouteFactory` threads `domain_service` on **15 of its 15 routes** — all writes, the delete, every `get_lateral_relationships`-backed read (`blocking`, `blocked`, `prerequisites`, `alternatives`, `complementary`, `siblings`, `manage`), and the three enhanced-UX reads (`chain`, `alternatives/compare`, `graph`).

The last three were the gap: each called `require_authenticated_user(request)` and **discarded the return value**, because the service methods behind them accepted no verifier, so any authenticated user could read another user's blocking chain, alternatives, or relationship graph by entity UID. Closed by adding the `user_uid` / `domain_service` pair to those three service methods and threading it from the factory. Regression cover: `tests/integration/routes/test_lateral_route_ownership.py` (foreign entity → 404, owner → 200, curriculum → 200) and `TestOwnershipGate` in `tests/unit/test_lateral_graph_queries.py`.

Two properties the fix preserves, both asserted:

- **`domain_service is None` stays public.** Curriculum KU/PS/LP are shared content (`_LATERAL_DOMAINS` passes `None`), so every user keeps reading them — including the graph route's second job, the knowledge-dependency view (`?types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE`) behind the Explore sidebar graph.
- **Not-found, never forbidden.** A foreign entity returns 404 with the same error code and message as one that does not exist, so a UID cannot be probed for existence.

Scope of the graph check: ownership is verified on the **center** entity only. The depth-limited traversal is not owner-filtered, so a neighbour reached from an owned center is returned whoever owns it — the same reach the `get_lateral_relationships`-backed reads already have. Narrowing that is a separate change to the traversal Cypher, not to this gate.

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
| `RelationshipGraphView` | `ui/patterns/relationships/relationship_graph.py` | Interactive Vis.js force-directed graph |
| `AddRelationshipModal` | `ui/patterns/relationships/add_modal.py` | Authoring modal (add lateral edges) |
| `LateralManageContainer` / `render_lateral_manage_fragment` | `ui/patterns/relationships/manage_list.py` | Flat, deletable edge list (authoring) |
| `EntityRelationshipsSection` | `ui/patterns/relationships/__init__.py` | Drop-in section for any entity detail page (`authoring=True` opts into add/delete) |

### API Endpoints (per domain)

- `GET /api/{domain}/{uid}/lateral/chain` — Blocking chain (HTML fragment)
- `GET /api/{domain}/{uid}/lateral/alternatives/compare` — Comparison (HTML fragment)
- `GET /api/{domain}/{uid}/lateral/graph` — Vis.js format (nodes + edges, JSON)
- `GET /api/{domain}/{uid}/lateral/manage` — Flat deletable edge list (HTML fragment)
- `POST /api/{domain}/{uid}/lateral/{blocks,prerequisites,alternatives,complementary}` — Create (emits `HX-Trigger: relationships-changed`)
- `DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid}` — Delete (emits `HX-Trigger: relationships-changed`)

**Authoring** (add/delete UI) is live on all **6 Activity** detail pages (Tasks/Goals/Habits/Events/Choices/Principles) via `EntityRelationshipsSection(authoring=True)`, gated by `PICKER_TYPES`. Curriculum KU/PS/LP stay read-only (not in `PICKER_TYPES`). The `DEPENDS_ON` scheduling edge has its own task-scoped Dependencies section (`GET|POST /tasks/{uid}/dependencies*`), kept distinct from `BLOCKS` (see the task-relationships-authoring plan, R1). See [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md) § Authoring.

---

## See Also

- [UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) — complete service documentation
- [LATERAL_RELATIONSHIPS_VISUALIZATION.md](/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md) — Phase 5 vis.js integration
- [ADR-028](/docs/decisions/ADR-028.md) — KU & MOC migration rationale
