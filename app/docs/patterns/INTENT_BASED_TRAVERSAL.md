---
title: Intent-Based Graph Traversal
updated: 2026-08-15
category: patterns
related_skills: []
related_docs:
  - /docs/roadmap/intent-traversal-registry-convergence.md
---

# Intent-Based Graph Traversal Pattern

> **Read this first — SUPERSEDED below the line.** As of the curriculum-convergence teardown,
> **mechanism A (`GraphContextLoader`) is deleted**, along with the model-suggested
> `get_suggested_query_intent()` methods and the `_init_context_loader` wiring. **All 6 Activity
> Domains and all 3 curriculum domains (Ku/Ps/Lp) now read graph context through mechanism B**
> (registry-sourced `UnifiedRelationshipService.get_with_context`, inherited from the shared
> `_CoreIntelligenceMixin`). The "three intent-sourcing mechanisms" inventory below is retained as
> **historical context (pre-Phase-1, 2026-06-04)** and is no longer the wiring — a full rewrite is
> pending. (Further, the per-domain `get_<domain>_with_context` facade/alias methods referenced
> below were deleted in the 2026-06 tasks bloat campaign — generic `get_with_context` is the one
> path.) The authoritative current state is
> [`docs/roadmap/intent-traversal-registry-convergence.md`](../roadmap/intent-traversal-registry-convergence.md)
> (Phase 1 ✅ + the curriculum-convergence follow-up ✅). Per-domain intent *specialization* (bespoke
> lenses / analysis methods) remains **aspirational**, not built.

## Overview

A single generic engine, `GraphIntelligenceService.query_with_intent()` + the query builder,
traverses the graph around an entity; a `QueryIntent` selects which edge types it filters on. But
**which intent a call applies is decided by the entry point, and the wiring is inconsistent across
domains.** There are three intent-sourcing mechanisms, and different facades reach different ones.

**Core Principle:** "One generic engine; three inconsistent intent-sourcing mechanisms feeding it."

## The three intent-sourcing mechanisms

All three end at `query_with_intent(...)` and the same builder; they differ only in *where the intent
comes from*.

- **A — model-suggested (`GraphContextLoader`).** `GraphContextLoader.get_with_context`
  (`core/services/intelligence/graph_context_loader.py`, reached via the shared
  `_CoreIntelligenceMixin`, `core/services/intelligence/_core_intelligence_mixin.py`) passes **no
  explicit intent**, so it falls back to `entity.get_suggested_query_intent()`. Every Activity Domain
  model inherits `Entity.get_suggested_query_intent()` (`core/models/entity.py:233`) →
  `QueryIntent.EXPLORATORY` and **none override it** (only `Curriculum`/`Askesis` do). Result: the
  **EXPLORATORY else-branch — no edge filter** (every node within `depth`, `LIMIT 100`).
- **B — config-sourced (`UnifiedRelationshipService`).** `Service.relationships.get_with_context`
  (`core/services/relationships/_intelligence_mixin.py`) resolves the intent from the domain's
  **registry config** (`DomainRelationshipConfig`, `core/models/relationship_registry.py`):
  `default_context_intent`, or `intent_mappings` / `get_intent_for_operation(op)`. This is the **only**
  mechanism on which the per-domain config intents below take effect.
- **C — generic relationship (`get_entity_context`).** `GraphIntelligenceService.get_entity_context`
  (`graph_intelligence_service.py:504`) applies `QueryIntent.RELATIONSHIP` (its docstring: "uses
  RELATIONSHIP intent"). `RELATIONSHIP` is *also* an else-branch intent (no edge filter), so the
  practical result matches A — an unfiltered neighborhood — but the intent value and code path differ.
  **Caveat:** `get_entity_context` has several live, correct consumers —
  `ActivityKnowledgeIntelligenceService.discover_learning_opportunities`
  (`activity_knowledge_intelligence_service.py:292`) and the `core/utils/intelligence_queries.py`
  helpers (lines 76, 284) all call it with the real signature (`entity_uid`, `depth`) and work. Among
  the per-domain context *facades*, only Events is wired to mechanism C, and **that one call is broken**
  — see the table note below.

### Which facade reaches which mechanism (verified 2026-06-04)

The per-domain `get_<domain>_with_context()` facade methods do **not** route uniformly:

| Facade method | Delegates to | Mechanism | Intent actually applied |
|---------------|--------------|:---------:|--------------------------|
| `TasksService.get_task_with_context` | `self.relationships.get_with_context` (inline on `TasksService`) | **B** | `PREREQUISITE` (config) |
| `GoalsService.get_goal_with_context` | `self.intelligence` → loader | **A** | `EXPLORATORY` |
| `HabitsService.get_habit_with_context` | `self.intelligence` → loader | **A** | `EXPLORATORY` |
| `ChoicesService.get_choice_with_context` | `self.intelligence` → loader | **A** | `EXPLORATORY` |
| `PrinciplesService.get_principle_with_context` | `self.intelligence` → loader | **A** | `EXPLORATORY` |
| `EventsService.get_event_with_context` | `self.intelligence` → `get_entity_context` | **C** (intended) | **errors today** ⚠️ |

> ⚠️ **The Events facade context path is broken today.** `events/_core_intelligence_mixin.py:78` calls
> `get_entity_context(entity_uid=uid, entity_type="Entity", depth=depth)`, but `get_entity_context`
> accepts only `(entity_uid, depth)` (no `entity_type`, no `**kwargs`) — so the call raises `TypeError`
> before any traversal runs. Mechanism C *would* apply `RELATIONSHIP` if the call matched the
> signature. This is a latent bug to fix separately (out of scope for this doc PR).

> The `/api/<domain>/context` routes (`IntelligenceRouteFactory`) call the **intelligence service's**
> `get_with_context`, which can resolve to a *different* method than the same domain's facade — e.g.
> the Tasks facade method is mechanism B (via `self.relationships.get_with_context` on `TasksService`), while the Tasks *intelligence
> service* has no `get_with_context` override and so would inherit the shared loader (mechanism A). The
> exact per-route intent is **not exhaustively verified here**; a full per-entry-point audit is part of
> the convergence work.

### Per-domain config intent — applies on mechanism B only (registry truth)

| Domain | `default_context_intent` | Config | Clause it hits on mechanism B |
|--------|--------------------------|--------|-------------------------------|
| Tasks | `PREREQUISITE` | `TASKS_CONFIG` | `REQUIRES_KNOWLEDGE / PREREQUISITE_FOR / ENABLES` |
| Goals | `GOAL_ACHIEVEMENT` | `GOALS_CONFIG` | goal-tailored (`FULFILLS_GOAL / SUPPORTS_GOAL / …`) |
| Habits | `PRACTICE` | `HABITS_CONFIG` | `REINFORCES_KNOWLEDGE / APPLIES_KNOWLEDGE` |
| Events | `PRACTICE` | `EVENTS_CONFIG` | `REINFORCES_KNOWLEDGE / APPLIES_KNOWLEDGE` |
| Choices | `HIERARCHICAL` | `CHOICES_CONFIG` | `HAS_SUBTASK / HAS_SUBGOAL / HAS_SUBHABIT / HAS_SUBEVENT / HAS_SUBCHOICE / HAS_SUBPRINCIPLE / HAS_STEP / ORGANIZES` |
| Principles | `HIERARCHICAL` | `PRINCIPLES_CONFIG` | `HAS_SUBTASK / HAS_SUBGOAL / HAS_SUBHABIT / HAS_SUBEVENT / HAS_SUBCHOICE / HAS_SUBPRINCIPLE / HAS_STEP / ORGANIZES` |

> ⚠️ **Live defects the convergence roadmap targets.**
> 1. **The intent wiring is inconsistent and mostly bypasses the config.** Of the six facade
>    convenience methods, only Tasks (mechanism B) applies its config intent; four run unfiltered
>    `EXPLORATORY`; and the Events facade path **errors** (bad `get_entity_context` kwarg, above). So
>    the "specialized" per-domain intents reach almost no caller.
> 2. **Even on mechanism B, Choice/Principle surface ~nothing.** They resolve to `HIERARCHICAL`
>    (the `HAS_SUB*` composition edges) — tree edges those domains almost never write — so the traversal
>    misses their real neighbors (`AFFECTS_GOAL`, `INFORMED_BY_PRINCIPLE`, `GUIDES_CHOICE`,
>    `INFORMED_BY_KNOWLEDGE`, …).
>
> Phase 1 of the convergence roadmap sources the edge vocabulary from
> `config.cross_domain_relationship_types` (the registry single-source-of-truth) instead of the
> hard-coded per-intent list — and must target whichever mechanism the routes/facades actually use.

## QueryIntent Enum

**Location:** `core/models/query_types.py`

### Generic intents (reachable)

```python
class QueryIntent(str, Enum):
    EXPLORATORY = "exploratory"      # Broad search/discovery (default; else-branch, no edge filter)
    SPECIFIC = "specific"            # Specific concept (else-branch)
    HIERARCHICAL = "hierarchical"    # Parent/child context — the six HAS_SUB* edges + HAS_STEP/ORGANIZES
    PREREQUISITE = "prerequisite"    # Prerequisite chains — REQUIRES_KNOWLEDGE/PREREQUISITE_FOR/ENABLES
    PRACTICE = "practice"            # REINFORCES_KNOWLEDGE/APPLIES_KNOWLEDGE
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

> **Only `GOAL_ACHIEVEMENT` is reachable** among the domain-specific intents (it is `GOALS_CONFIG`'s
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
`adapters/persistence/neo4j/query/graph_context_query_builder.py`. The **seven filtered intent
clauses** (HIERARCHICAL, PREREQUISITE, PRACTICE, GOAL_ACHIEVEMENT, and the three dead ones) differ from
each other **only** in their `type(r) IN [...]` edge list — identical depth (`[*0..{depth}]`),
direction (bidirectional), return shape, and **no `LIMIT`**. The **generic `else` branch**
(EXPLORATORY / SPECIFIC / AGGREGATION / RELATIONSHIP) is the one different shape: it applies **no edge
filter** *and* adds `LIMIT 100`. So a Phase 1 override that supplies an edge list to the filtered
clauses is thin, but anything routing the else-branch through the same override must preserve (or
deliberately reconcile) that `LIMIT 100`.

### 2. UnifiedRelationshipService — Mechanism B (config-sourced)

**Location:** `core/services/relationships/unified_relationship_service.py`

One generic, configuration-driven service handles relationship operations for all domains. Its generic
`get_with_context()` (in `relationships/_intelligence_mixin.py`) resolves the intent from `self.config`
(`default_context_intent`, or `intent_mappings` via the optional `intent` arg) and calls
`query_with_intent`. This is the config-sourced mechanism (reached by the Tasks facade today).

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
        """Mechanism B: intent = self.config.default_context_intent (or intent_mappings)."""
```

### 3. GraphContextLoader — Mechanism A (model-suggested)

**Location:** `core/services/intelligence/graph_context_loader.py`

Most intelligence-service `get_with_context` paths (and the Goals/Habits/Choices/Principles facades)
load context through this. With no explicit `intent`, it uses `entity.get_suggested_query_intent()` —
which for every Activity Domain is the inherited `EXPLORATORY` (no edge filter). (`EventsService` is
wired to mechanism C — `get_entity_context` → `RELATIONSHIP` — instead, but that call is broken today;
see the facade table note.)

```python
async def get_with_context(self, uid, depth=2, intent: QueryIntent | None = None):
    ...
    chosen_intent = intent if intent is not None else entity.get_suggested_query_intent()
    return await self.graph_intel.query_with_intent(domain=..., node_uid=uid, intent=chosen_intent, depth=depth)
```

The `get_suggested_query_intent()` override exists on the base `Entity` (default `EXPLORATORY`) and is
used only by non-Activity types (`Curriculum`, `Askesis`).

### 4. Service wiring

Each facade wires the registry config + `graph_intel` into its relationship service (mechanism B is
always reachable via `self.relationships`), but the per-facade `get_<domain>_with_context()` convenience
method resolves to different mechanisms (see the verified table above):

```python
# In {Domain}Service.__init__():
self.relationships = UnifiedRelationshipService(            # Mechanism B (config intent), always available
    backend=backend, config=DOMAIN_CONFIG, graph_intel=graph_intel
)
# get_<domain>_with_context(): Tasks → self.relationships (B); Goals/Habits/Choices/Principles →
#   self.intelligence → GraphContextLoader (A, EXPLORATORY); Events → get_entity_context (C, intended) —
#   the Events call is broken today (passes an unsupported entity_type= kwarg → TypeError).
```

## Intent clause vocabularies

These are the `type(r) IN [...]` edge lists in `build_context_query_for_intent`, as wired today.

### Reachable clauses

- **HIERARCHICAL** — `HAS_SUBTASK`, `HAS_SUBGOAL`, `HAS_SUBHABIT`, `HAS_SUBEVENT`,
  `HAS_SUBCHOICE`, `HAS_SUBPRINCIPLE`, `HAS_STEP`, `ORGANIZES`
- **PREREQUISITE** — `REQUIRES_KNOWLEDGE`, `PREREQUISITE_FOR`, `ENABLES`
- **PRACTICE** — `REINFORCES_KNOWLEDGE`, `APPLIES_KNOWLEDGE`
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
- **SCHEDULED_ACTION** — `EXECUTES_TASK`, `REINFORCES_HABIT`,
  `MILESTONE_FOR_GOAL`, `CONFLICTS_WITH`, `SUPPORTS_GOAL`, `SCHEDULED_FOR`, `DERIVED_FROM_TASK`
  (the former `PRACTICES_KNOWLEDGE` edge was deleted in #259 — event→knowledge is `APPLIES_KNOWLEDGE`)

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
| UnifiedRelationshipService (mechanism B) | `core/services/relationships/unified_relationship_service.py` (+ `relationships/_intelligence_mixin.py`) |
| GraphContextLoader (mechanism A) | `core/services/intelligence/graph_context_loader.py` (+ `intelligence/_core_intelligence_mixin.py`) |
| `get_entity_context` (mechanism C) | `core/services/infrastructure/graph_intelligence_service.py:504` |
| `@requires_graph_intelligence` | `core/utils/decorators.py` |
| **Facades** | |
| TasksService | `core/services/tasks_service.py` |
| GoalsService | `core/services/goals_service.py` |
| PrinciplesService | `core/services/principles_service.py` |
| HabitsService | `core/services/habits_service.py` |
| ChoicesService | `core/services/choices_service.py` |
| EventsService | `core/services/events_service.py` |

Each facade exposes a thin `get_<domain>_with_context()` convenience method, but they route to
different mechanisms (see the verified table above): **Tasks → B** (`PREREQUISITE`),
**Goals/Habits/Choices/Principles → A** (`GraphContextLoader` → `EXPLORATORY`), **Events → C intended**
but **broken today** (`get_entity_context` called with an unsupported `entity_type=` kwarg → `TypeError`).
There is **no** bespoke per-domain "analysis method" (`get_goal_achievement_analysis`,
`get_principle_embodiment_analysis`, etc. do not exist).

## Usage

### Getting an entity with its graph context

```python
# Mechanism A — Goals facade convenience method. Goes through GraphContextLoader, which applies
# entity.get_suggested_query_intent() == EXPLORATORY → an unfiltered neighbourhood (LIMIT 100).
result = await goals_service.get_goal_with_context(uid="goal.123", depth=2)

# Mechanism B — config-sourced intent. Applies GOALS_CONFIG.default_context_intent (GOAL_ACHIEVEMENT),
# so the GOAL_ACHIEVEMENT edge filter is used. Pass intent=... to use an intent_mappings override.
# (This is also exactly what the Tasks *facade* method does — TasksService.get_task_with_context
#  delegates here, applying PREREQUISITE — whereas the Goals facade above does not.)
result = await goals_service.relationships.get_with_context(uid="goal.123", depth=2)

if result.is_error:
    return handle_error(result)
goal, context = result.value
# context.entities      — related nodes (filtered by the applied intent, or all within depth on A/C)
# context.relationships — edge data
```

> The two calls return **different** neighbourhoods today. For Choices/Principles, mechanism A returns
> an unfiltered set and mechanism B returns the (near-empty) `HIERARCHICAL` set — neither surfaces their
> real edges. See the defect note above and the convergence roadmap.

## Benefits (of the generic traversal engine as wired)

1. **One traversal engine** — a single `query_with_intent` + one query-builder function, not six.
2. **Config-driven (mechanism B)** — on the `UnifiedRelationshipService` path the intent comes from the
   registry; convergence Phase 1 extends this to the edge vocabulary and reconciles the three mechanisms.
3. **Type-safe intent** — `QueryIntent` enum prevents typos.

For the per-domain semantic lenses, uniform analysis shape, and "intents as life-questions" that this
pattern *aspires* to, see
[`docs/roadmap/intent-traversal-registry-convergence.md`](../roadmap/intent-traversal-registry-convergence.md).

---

**Last Updated:** June 4, 2026
**Status:** Partially wired — generic intent traversal is live; per-domain specialization is aspirational (see convergence roadmap).
