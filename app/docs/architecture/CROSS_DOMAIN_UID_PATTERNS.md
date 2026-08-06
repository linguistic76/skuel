---
title: "Cross-Domain UID Patterns: Structural Anchors vs Enrichment Links"
updated: 2026-06-20
status: current
category: architecture
tags: [architecture, uid-patterns, cross-domain, structural-anchor, enrichment-link]
related:
  - CURRICULUM_GROUPING_PATTERNS
  - ENTITY_TYPE_ARCHITECTURE
  - ADR-061-spawn-layer-consolidation
---

# Cross-Domain UID Patterns

## The Rule

Every cross-domain UID field on an entity falls into exactly one of three categories:

| Category | Storage | Populated | Authority |
|----------|---------|-----------|-----------|
| **Structural anchor** | Persisted node property (via DTO) | At creation time | Property IS the source of truth |
| **Enrichment link** | Never a property — `DERIVED FROM EDGE` + skip-set | At read time (batch enrich step) | Graph edge is the source of truth |
| **Edge carrier** | Never a property — skip-set | Set on the entity at CREATE, read back from the edge | Graph edge is the source of truth |

**Structural anchor** — the UID encodes a permanent relationship the entity *is defined by*: hierarchy membership, spawn-time origin, scheduling appointment. It must survive restarts, queries, and graph traversal without a round-trip to read an edge.

**Enrichment link** — the UID is a scoring or analytics convenience read off a graph edge. It is populated by a dedicated enrich step (e.g., `enrich_habits_with_goal_links()`) only when the scoring path needs it, and nothing writes it.

**Edge carrier** — the same non-persistence as an enrichment link, but the create path *reads* the field to decide which edge to write (`Task.parent_uid` → HAS_SUBTASK, `Task.reinforces_habit_uid` → REINFORCES_HABIT). This exists because the generated CRUD route hands the service an ENTITY and no request: a link the entity cannot carry is a link that door can never write. It is not "sometimes persisted" — the property never exists in either direction; only the create-time *input* differs.

Confusing the two produces either stale denormalized data (writing what should be derived) or phantom traversal (reading a field that was never populated).

**See also:** `CURRICULUM_GROUPING_PATTERNS.md` — where the rule was first formalised for `Exercise.path_step_uid`.

---

## Activity Domains — Complete UID Field Inventory

### Structural anchors (persisted properties)

| Domain | Field | Direction | Why persisted |
|--------|-------|-----------|---------------|
| Task | `fulfills_goal_uid` | TASK → GOAL | Hierarchy membership — the task is part of this goal's action system |
| Task | `source_path_step_uid` | TASK → PS | Spawn-time PS origin; also set by non-template paths (see §below) |
| Task | `scheduled_event_uid` | TASK → EVENT | Scheduling appointment — the task is pinned to this Event |
| Goal | `fulfills_goal_uid` | GOAL → GOAL | Sub-goal hierarchy membership (parallel to `Exercise.path_step_uid`) |
| Goal | `source_path_step_uid` | GOAL → PS | Spawn-time PS origin |
| Goal | `selected_choice_option_uid` | GOAL → ChoiceOption | Which option within a Choice entity inspired this Goal (see §below) |
| Habit | `source_path_step_uid` | HABIT → PS | Spawn-time PS origin |
| Event | `source_path_step_uid` | EVENT → PS | Spawn-time PS origin |
| Choice | `source_path_step_uid` | CHOICE → PS | Spawn-time PS origin |
| Principle | `source_path_step_uid` | PRINCIPLE → PS | Spawn-time PS origin |

### Enrichment links (DERIVED FROM EDGE — never persisted)

| Domain | Field | Graph edge | Populated by |
|--------|-------|-----------|-------------|
| Task | `reinforces_habit_uid` | `(Task)-[:REINFORCES_HABIT]->(Habit)` | `get_habit_links_for_tasks()` |
| Habit | `supports_goal_uid` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` | `enrich_habits_with_goal_links()` |
| Event | `reinforces_habit_uid` | `(Event)-[:REINFORCES_HABIT]->(Habit)` | `enrich_events_with_habit_links()` |
| Event | `contributes_to_goal_uid` | `(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)` | `enrich_events_with_goal_links()` |

**How to identify an enrichment link in the code:** the field carries a `# DERIVED FROM EDGE` comment and its name is in `RELATIONSHIP_SKIP_FIELDS` (`adapters/persistence/neo4j/neo4j_mapper.py`). The graph edge is the single source of truth.

⚠ **Absence from the DTO is NOT what makes a field unpersistable** — that was the stated test here until 2026-08-06, and it was wrong. Only `create_*` paths that persist `to_dto().to_dict()` are covered by it; the generated CRUD route (`CRUDRouteFactory._register_create_route`) converts the request and persists the **ENTITY**, so `to_neo4j_node` reads the dataclass field directly. `reinforces_habit_uid` was landing as a junk node property on every task and event created through `POST /api/{tasks,events}/create`, while no edge was written. The skip-set entry is what actually enforces the rule; the DTO's silence merely hid the gap.

**On Tasks, `reinforces_habit_uid` is derived on READ but is the edge's INPUT on CREATE.** It rides on the `Task` because the generated route hands the service an entity and no request — a link the entity cannot carry is a link that door can never write — and `TasksCoreService._write_link_edges` turns it into the REINFORCES_HABIT edge for both doors. Events do not (yet) do this: their route door still drops the link.

---

## Curriculum — structural anchor recap

The rule applies identically to Curriculum entities. Quick reference:

| Domain | Field | Why persisted |
|--------|-------|---------------|
| Exercise | `path_step_uid` | Hierarchy membership — this exercise belongs to this PathStep. Dual-written with `HAS_EXERCISE` edge at creation. |
| Goal (spawned) | `source_path_step_uid` | Spawn-time PS origin (same as Activity Domain pattern above) |

**See:** `CURRICULUM_GROUPING_PATTERNS.md § Exercise — Applied Knowledge` for the full Curriculum treatment.

---

## `source_path_step_uid` in depth

This field appears on all 6 Activity Domains and deserves a precise statement because it serves two overlapping purposes with subtly different semantics.

### Two creation paths

**1. Template spawn path** (student engages a PathStep):

```
(PathStep)-[:HAS_*_TEMPLATE]->(ActivityTemplate)
                                     |
           _SpawnOrchestrator reads template, produces:
                                     ↓
                           (Activity) — source_path_step_uid = ps_uid
                               │
                               └─[:SPAWNED_FROM]──>(ActivityTemplate)
```

The `SPAWNED_FROM` edge encodes the template relationship. `source_path_step_uid` is a **read-optimization** — it saves a 2-hop traversal to find the owning PS. Since templates are immutable at engagement time (status `PUBLISHED`), the two cannot diverge.

**2. Non-template scheduling path** (teacher or user creates an Activity tied to a PathStep directly):

```
(Activity) — source_path_step_uid = ps_uid
    │
    └─ NO SPAWNED_FROM edge
```

Here the field is the **only** back-reference. There is no `SPAWNED_FROM` edge to traverse. This is why ADR-061 rejected dropping the field in favour of the 2-hop path: the field is the universal back-reference even when the template relationship is absent.

### Which is authoritative?

`source_path_step_uid` records the **spawn-time PS**. The `SPAWNED_FROM` edge reflects **current template ownership**. For a PUBLISHED template that was never moved, the two are identical. For non-template activities, only the field exists. Read the field; traverse the edge only when you need to interrogate the template itself.

---

## `Goal.selected_choice_option_uid` — the sub-entity variant

This is a structural anchor with an unusual target. The user picks a specific **ChoiceOption** within a `Choice` entity that inspires a Goal. The *Choice entity* connection is recorded as the graph edge `(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)`. But `ChoiceOption` objects are embedded in the Choice node (not separate Neo4j nodes), so there is no edge that can point to the specific option — the property is the only way to record which option was selected.

Pattern: **graph edge to the containing entity + property for the sub-entity selection.** Never add a `:ChoiceOption` Neo4j node to resolve this; the embedded pattern is intentional.

---

## Where this rule should NOT apply

**Edge metadata is never denormalized.** When a graph edge carries relationship-specific properties (e.g., `{essentiality}` on `SUPPORTS_GOAL`, `{order}` on `HAS_STEP`), those property values are **never** copied to a field on either endpoint node. The endpoint UIDs may appear as enrichment links (e.g., `Habit.supports_goal_uid` is derived from the `SUPPORTS_GOAL` edge endpoint) — the *UID* tells you which node; the *metadata* requires a Cypher traversal to read.

**Knowledge Substance connections** (`APPLIES_KNOWLEDGE`, `REINFORCES_KNOWLEDGE`, etc.) are write-once graph events. No UID field on the Activity model, no enrich step — the substance pipeline reads them directly from the graph via Cypher.

---

## Adding a new cross-domain UID field

Before adding a field, decide:

1. **Is this the entity's permanent identity or origin?** → structural anchor: add to model + DTO + write at creation.
2. **Is this a scoring signal read off a graph edge that already exists?** → enrichment link: add `DERIVED FROM EDGE` comment to the model, add the name to `RELATIONSHIP_SKIP_FIELDS`, populate in the scoring enrich step.
3. **Does a create REQUEST supply it, and does the graph own it?** → edge carrier: as (2), plus set it on the entity in both `from_request` and the `ConversionServiceV2` converter, and write the edge on the domain's shared `create()` primitive so both doors do it once. Every request-supplied endpoint must pass `keep_permitted_link_edges` (exists / owner / kind) before it becomes an edge.
4. **Is this a many-to-many relationship with metadata?** → pure graph edge, no UID field at all. A list-typed request field can only take this shape: it reaches no model field, so the generated route cannot carry it and the request door owns it alone.

A field that is "sometimes persisted and sometimes derived" is a design error — pick one. Adding the name to `RELATIONSHIP_SKIP_FIELDS` is what makes (2) and (3) enforceable rather than aspirational, and it is keyed on the NAME — census every dataclass carrying it before adding an entry.
