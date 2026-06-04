---
title: Intent-Based Graph Traversal
updated: 2026-06-04
category: patterns
related_skills: []
related_docs:
  - /docs/roadmap/intent-traversal-registry-convergence.md
---

# Intent-Based Graph Traversal Pattern

> **Read this first.** This doc describes what is *actually wired today*. Per-domain intent
> *specialization* — bespoke per-domain lenses and analysis methods — is **aspirational**, not built.
> The direction (source the edge vocabulary from the registry, collapse the two graph readers into one)
> lives in [`docs/roadmap/intent-traversal-registry-convergence.md`](../roadmap/intent-traversal-registry-convergence.md).
> Where this doc previously asserted six per-domain analysis methods and a per-model intent, those were
> fiction; this rewrite removes them.

## Overview

A single generic entry point, `GraphIntelligenceService.query_with_intent()`, traverses the graph
around an entity. A `QueryIntent` selects which edge types the traversal filters on. **Which intent a
call applies depends on the entry path — there are two, and they source the intent differently.**

**Core Principle:** "One generic traversal engine; two entry paths choose the intent differently."

## How the intent is actually chosen — two entry paths

Both paths end at `GraphIntelligenceService.query_with_intent(...)` and the same query builder. They
differ only in *where the intent comes from*:

### Path A — model-suggested (what the facades and `/api/<domain>/context` routes use today)

`Service.get_<domain>_with_context()` → the domain intelligence service → shared
`_CoreIntelligenceMixin.get_with_context` (`core/services/intelligence/_core_intelligence_mixin.py`) →
`GraphContextLoader.get_with_context` (`core/services/intelligence/graph_context_loader.py`). The
loader passes **no explicit intent**, so it falls back to `entity.get_suggested_query_intent()`.

Every **Activity Domain** model (Task, Goal, Habit, Event, Choice, Principle) inherits
`Entity.get_suggested_query_intent()` (`core/models/entity.py:233`) → `QueryIntent.EXPLORATORY`, and
**none override it** (only `Curriculum` and `Askesis` do). So on Path A every Activity Domain runs the
**EXPLORATORY else-branch — no edge filter at all** (every node within `depth`, `LIMIT 100`). The
per-domain config intents below are **not** applied here. The `IntelligenceRouteFactory`-wired
`/api/<domain>/context` routes go through this path.

### Path B — config-sourced (`UnifiedRelationshipService.get_with_context`)

`Service.relationships.get_with_context()` (`core/services/relationships/_intelligence_mixin.py`)
resolves the intent from the domain's **registry config**
(`DomainRelationshipConfig` in `core/models/relationship_registry.py`):

- `default_context_intent` — the domain's default lens.
- `intent_mappings` + `get_intent_for_operation(operation)` — per-operation overrides
  (falls back to `default_context_intent`).

This is the **only** path on which the per-domain intents below actually take effect.

### Per-domain default intent — applies on Path B only (registry truth)

| Domain | `default_context_intent` | Config | Clause it hits on Path B |
|--------|--------------------------|--------|--------------------------|
| Tasks | `PREREQUISITE` | `TASKS_CONFIG` | `REQUIRES_KNOWLEDGE / PREREQUISITE_FOR / ENABLES` |
| Goals | `GOAL_ACHIEVEMENT` | `GOAPS_CONFIG` | goal-tailored (`FULFILLS_GOAL / SUPPORTS_GOAL / …`) |
| Habits | `PRACTICE` | `HABITS_CONFIG` | `PRACTICES / REINFORCES / APPLIES_KNOWLEDGE` |
| Events | `PRACTICE` | `EVENTS_CONFIG` | `PRACTICES / REINFORCES / APPLIES_KNOWLEDGE` |
| Choices | `HIERARCHICAL` | `CHOICES_CONFIG` | `HAS_CHILD / PARENT_OF / CHILD_OF` |
| Principles | `HIERARCHICAL` | `PRINCIPLES_CONFIG` | `HAS_CHILD / PARENT_OF / CHILD_OF` |

> ⚠️ **Two live defects the convergence roadmap targets.**
> 1. **The user-facing path ignores the config intent.** The facades and `/api/<domain>/context` routes
>    take Path A → `EXPLORATORY` → an unfiltered neighborhood (`LIMIT 100`), so the "specialized" intents
>    never reach those callers at all.
> 2. **Even on Path B, Choice/Principle surface ~nothing.** They resolve to `HIERARCHICAL`
>    (`HAS_CHILD/PARENT_OF/CHILD_OF`) — tree edges those domains almost never write — so the traversal
>    misses their real neighbors (`AFFECTS_GOAL`, `INFORMED_BY_PRINCIPLE`, `GUIDES_CHOICE`,
>    `INFORMED_BY_KNOWLEDGE`, …).
>
> Phase 1 of the convergence roadmap sources the edge vocabulary from
> `config.cross_domain_relationship_types` (the registry single-source-of-truth) instead of the
> hard-coded per-intent list — and must target whichever path the routes actually use.

## QueryIntent Enum

**Location:** `core/models/query_types.py`

### Generic intents (reachable)

```python
class QueryIntent(str, Enum):
    EXPLORATORY = "exploratory"      # Broad search/discovery (default; else-branch, no edge filter)
    SPECIFIC = "specific"            # Specific concept (else-branch)
    HIERARCHICAL = "hierarchical"    # Parent/child context — HAS_CHILD/PARENT_OF/CHILD_OF
    PREREQUISITE = "prerequisite"    # Prerequisite chains — REQUIRES_KNOWLEDGE/PREREQUISITE_FOR/ENABLES
    PRACTICE = "practice"            # PRACTICES/REINFORCES/APPLIES_KNOWLEDGE
    AGGREGATION = "aggregation"      # Statistical (else-branch)
    RELATIONSHIP = "relationship"    # Graph-traversal focused (else-branch)
```

### Domain-specific intents

```python
    GOAL_ACHIEVEMENT = "goal_achievement"          # LIVE — Goals' default_context_intent
    PRINCIPLE_EMBODIMENT = "principle_embodiment"  # DEAD — selected by no config (unreachable clause)
    PRINCIPLE_ALIGNMENT = "principle_alignment"    # DEAD — selected by no config (unreachable clause)
    SCHEDULED_ACTION = "scheduled_action"          # DEAD — selected by no config (unreachable clause)
```

> **Only `GOAL_ACHIEVEMENT` is reachable** among the domain-specific intents (it is `GOAPS_CONFIG`'s
> default). `PRINCIPLE_EMBODIMENT`, `PRINCIPLE_ALIGNMENT`, and `SCHEDULED_ACTION` are referenced
> **nowhere** outside the enum and their own builder clauses — no `default_context_intent` and no
> `intent_mappings` value selects them, so those clauses are dead code. (Note: `PRINCIPLE_ALIGNMENT`
> also appears as an `InsightType` value — a *different* enum, unrelated to this routing.)

## Architecture Components

### 1. GraphIntelligenceService

**Location:** `core/services/infrastructure/graph_intelligence_service.py`

```python
async def query_with_intent(
    self,
    domain: Any,        # Domain enum — currently used only for logging
    node_uid: str,
    intent: Any,        # QueryIntent
    depth: int = 2,
) -> Result[GraphContext]:
    ...
    # NOTE: `domain` is dropped before the backend call today — the backend receives only intent/depth/uid.
    result = await self.backend.query_with_intent(intent=intent, depth=depth, uid=node_uid)
```

The Cypher is built by the module-level function
`build_context_query_for_intent(intent, depth)` in
`adapters/persistence/neo4j/query/graph_context_query_builder.py`. It is a single function with one
clause per intent; **every clause differs only in its `type(r) IN [...]` edge list** — identical
depth (`[*0..{depth}]`), direction (bidirectional), and return shape.

### 2. UnifiedRelationshipService — Path B (config-sourced)

**Location:** `core/services/relationships/unified_relationship_service.py`

One generic, configuration-driven service handles relationship operations for all domains. Its generic
`get_with_context()` (in `relationships/_intelligence_mixin.py`) resolves the intent from `self.config`
(`default_context_intent`, or `intent_mappings` via the optional `intent` arg) and calls
`query_with_intent`. This is the config-sourced path.

```python
class UnifiedRelationshipService[Ops, Model, DtoType](...):
    def __init__(
        self,
        backend: Ops,
        config: DomainRelationshipConfig,   # REQUIRED — registry config (the single source of truth)
        graph_intel: Any | None = None,     # GraphIntelligenceService (optional)
    ) -> None:
        ...

    async def get_with_context(
        self, uid: str, depth: int = 2, intent: str | None = None
    ) -> Result[tuple[Any, GraphContext]]:
        """Path B: intent = self.config.default_context_intent (or intent_mappings)."""
```

### 3. GraphContextLoader — Path A (model-suggested)

**Location:** `core/services/intelligence/graph_context_loader.py`

The intelligence services and facade `get_<domain>_with_context()` methods load context through this.
With no explicit `intent`, it uses `entity.get_suggested_query_intent()` — which for every Activity
Domain is the inherited `EXPLORATORY` (no edge filter).

```python
async def get_with_context(self, uid, depth=2, intent: QueryIntent | None = None):
    ...
    chosen_intent = intent if intent is not None else entity.get_suggested_query_intent()
    return await self.graph_intel.query_with_intent(domain=..., node_uid=uid, intent=chosen_intent, depth=depth)
```

The `get_suggested_query_intent()` override exists on the base `Entity` (default `EXPLORATORY`) and is
used only by non-Activity types (`Curriculum`, `Askesis`).

### 4. Service wiring

Each facade wires the registry config + `graph_intel` into its relationship service, and exposes
**both** paths:

```python
# In {Domain}Service.__init__():
self.relationships = UnifiedRelationshipService(            # Path B (config intent)
    backend=backend, config=DOMAIN_CONFIG, graph_intel=graph_intel
)
# self.get_<domain>_with_context() delegates via self.intelligence → GraphContextLoader  (Path A: EXPLORATORY)
```

## Intent clause vocabularies

These are the `type(r) IN [...]` edge lists in `build_context_query_for_intent`, as wired today.

### Reachable clauses

- **HIERARCHICAL** — `HAS_CHILD`, `PARENT_OF`, `CHILD_OF`
- **PREREQUISITE** — `REQUIRES_KNOWLEDGE`, `PREREQUISITE_FOR`, `ENABLES`
- **PRACTICE** — `PRACTICES`, `REINFORCES`, `APPLIES_KNOWLEDGE`
- **GOAL_ACHIEVEMENT** — `FULFILLS_GOAL`, `SUPPORTS_GOAL`, `REQUIRES_KNOWLEDGE`, `SUBGOAL_OF`,
  `GUIDED_BY_PRINCIPLE`, `CONTRIBUTES_TO_GOAL`
- **else** (EXPLORATORY / SPECIFIC / AGGREGATION / RELATIONSHIP) — generic traversal, no edge filter

### Dead clauses (defined but selected by nothing — do not treat as live)

These are *hypotheses* the convergence roadmap may revive against real registry edges — not current
behavior. They are listed here only so the gap is visible.

- **PRINCIPLE_EMBODIMENT** — `GUIDED_BY_PRINCIPLE`, `ALIGNED_WITH_PRINCIPLE`, `INSPIRES_HABIT`,
  `GROUNDED_IN_KNOWLEDGE`, `GUIDES_GOAL`, `GUIDES_CHOICE`
- **PRINCIPLE_ALIGNMENT** — `ALIGNED_WITH_PRINCIPLE`, `INFORMED_BY_KNOWLEDGE`, `SUPPORTS_GOAL`,
  `CONFLICTS_WITH_GOAL`, `REQUIRES_KNOWLEDGE_FOR_DECISION`, `OPENS_LEARNING_PATH`, `GUIDED_BY_PRINCIPLE`
- **SCHEDULED_ACTION** — `EXECUTES_TASK`, `PRACTICES_KNOWLEDGE`, `REINFORCES_HABIT`,
  `MILESTONE_FOR_GOAL`, `CONFLICTS_WITH`, `SUPPORTS_GOAL`, `SCHEDULED_FOR`, `DERIVED_FROM_TASK`

> ⚠️ `CONFLICTS_WITH_GOAL` (and several others above) are written **nowhere** by any writer in the
> codebase — they exist only in this dead clause and the enum. Do not resurrect them; a real lens needs
> an edge a writer actually produces. See the convergence roadmap's guardrails.

## Key Files

| Component | File |
|-----------|------|
| QueryIntent enum | `core/models/query_types.py` |
| GraphIntelligenceService | `core/services/infrastructure/graph_intelligence_service.py` |
| `build_context_query_for_intent` | `adapters/persistence/neo4j/query/graph_context_query_builder.py` |
| Registry config (intent + edges) | `core/models/relationship_registry.py` (`DomainRelationshipConfig`, `default_context_intent`, `intent_mappings`, `cross_domain_relationship_types`) |
| UnifiedRelationshipService (Path B) | `core/services/relationships/unified_relationship_service.py` (+ `relationships/_intelligence_mixin.py`) |
| GraphContextLoader (Path A) | `core/services/intelligence/graph_context_loader.py` (+ `intelligence/_core_intelligence_mixin.py`) |
| `@requires_graph_intelligence` | `core/utils/decorators.py` |
| **Facades** | |
| TasksService | `core/services/tasks_service.py` |
| GoalsService | `core/services/goals_service.py` |
| PrinciplesService | `core/services/principles_service.py` |
| HabitsService | `core/services/habits_service.py` |
| ChoicesService | `core/services/choices_service.py` |
| EventsService | `core/services/events_service.py` |

Each facade exposes a thin `get_<domain>_with_context()` convenience method (e.g.
`GoalsService.get_goal_with_context` at `core/services/goals_service.py:403`) that delegates through
the domain intelligence service to **Path A** (`GraphContextLoader` → `EXPLORATORY`). There is **no**
bespoke per-domain "analysis method" (`get_goal_achievement_analysis`,
`get_principle_embodiment_analysis`, etc. do not exist).

## Usage

### Getting an entity with its graph context

```python
# Path A — facade convenience method. Goes through GraphContextLoader, which applies
# entity.get_suggested_query_intent() == EXPLORATORY → an unfiltered neighbourhood (LIMIT 100).
result = await goals_service.get_goal_with_context(uid="goal:123", depth=2)

# Path B — config-sourced intent. Applies GOAPS_CONFIG.default_context_intent (GOAL_ACHIEVEMENT),
# so the GOAL_ACHIEVEMENT edge filter is used. Pass intent=... to use an intent_mappings override.
result = await goals_service.relationships.get_with_context(uid="goal:123", depth=2)

if result.is_error:
    return handle_error(result)
goal, context = result.value
# context.entities      — related nodes (filtered by the applied intent, or all within depth on Path A)
# context.relationships — edge data
```

> The two calls return **different** neighbourhoods today. For Choices/Principles, Path A returns an
> unfiltered set and Path B returns the (near-empty) `HIERARCHICAL` set — neither surfaces their real
> edges. See the two-defect note above and the convergence roadmap.

## Benefits (of the generic traversal engine as wired)

1. **One traversal engine** — a single `query_with_intent` + one query-builder function, not six.
2. **Config-driven (Path B)** — on the `UnifiedRelationshipService` path the intent comes from the
   registry; convergence Phase 1 extends this to the edge vocabulary and reconciles the two paths.
3. **Type-safe intent** — `QueryIntent` enum prevents typos.

For the per-domain semantic lenses, uniform analysis shape, and "intents as life-questions" that this
pattern *aspires* to, see
[`docs/roadmap/intent-traversal-registry-convergence.md`](../roadmap/intent-traversal-registry-convergence.md).

---

**Last Updated:** June 4, 2026
**Status:** Partially wired — generic intent traversal is live; per-domain specialization is aspirational (see convergence roadmap).
