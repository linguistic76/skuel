---
title: LifePath Alignment Debt
updated: 2026-08-12
status: open
category: technical-debt
tags: [lifepath, analytics, substance, cypher, technical-debt, graph-vocabulary]
related: [ANALYTICS_UNTYPED_SEAM_DEFECTS.md, knowledge_substance_philosophy.md]
---

# LifePath Alignment Debt

**Status**: 🔶 OPEN (2 items, both found 2026-08-12 while rewriting a *different*
alignment metric)
**Surfaces affected**: `LifePathService.get_alignment` / `get_full_status` /
`designate_and_calculate`; the `/lifepath` dashboard; every stored
`ULTIMATE_PATH.alignment_score`
**Not affected**: `AnalyticsLifePathService.calculate_life_path_alignment` — a
*separate* metric, rewritten 2026-08-12 to score per-learner off
`core/services/knowledge/user_substance.py`. See
`docs/architecture/knowledge_substance_philosophy.md` § Ruling: what alignment
measures.

## Two alignment metrics, one name

SKUEL computes "life path alignment" twice, and the two share no code:

| | `LifePathAlignmentService.calculate_alignment` | `AnalyticsLifePathService.calculate_life_path_alignment` |
|---|---|---|
| Shape | 5 weighted dimensions (knowledge .25, activity .25, goal .20, principle .15, momentum .15) | mean personal substance over the path's steps |
| Weights | hand-rolled in Cypher (`0.6 * mastery + 0.05/task + 0.10/habit`) | `USER_SUBSTANCE_CHANNELS`, the one table |
| Written to | `ULTIMATE_PATH.alignment_score`, `ALIGNMENT_SNAPSHOT.score` | the analytics payload only |
| State | **this file** | rewritten 2026-08-12 |

Both items below are in the first one. That the *substance weights are hand-copied
into Cypher* is the through-line: it is the third copy of the table that
`user_substance.py` exists to prevent, and it has already drifted.

---

## 1. Habits contribute nothing to any dimension

**Site**: `adapters/persistence/neo4j/lifepath_backend.py`
**Severity**: the dimension weights say habits are the heaviest substance channel
(0.10/instance vs 0.05 for tasks); they are worth exactly zero in all three
dimensions that reference them.

Habits link to knowledge over **`REINFORCES_KNOWLEDGE`**. Two queries match them
over `APPLIES_KNOWLEDGE`, and a third omits them entirely:

| Line | Query | Defect |
|------|-------|--------|
| 290 | `calculate_knowledge_alignment` | `(ku)<-[:APPLIES_KNOWLEDGE]-(habit:Entity {entity_type: 'habit', ...})` — wrong edge, so `habit_count` is always 0 and the `* 0.10` term never fires |
| 321 | `calculate_activity_alignment` | `(u)-[:OWNS]->(habit:Entity {entity_type: 'habit'})-[:APPLIES_KNOWLEDGE]->(ku)` — wrong edge, so `aligned_habits` is always 0 |
| ~401 | `calculate_momentum` | no habit arm at all — momentum is task-only |

The writers are unambiguous: `HabitsCoreService` (`core/services/habits/habits_core_service.py:474`,
`RelationshipName.REINFORCES_KNOWLEDGE`), `query/cypher/domain_queries.py:523,573`,
the substance channel read `_USER_KNOWLEDGE_CHANNELS_QUERY`, and the YAML authoring
table in `knowledge_substance_philosophy.md` (`connections.reinforces_knowledge`).

### The sharp consequence

`calculate_activity_alignment` returns `task_ratio * 0.4 + habit_ratio * 0.6`, and
`habit_ratio` defaults to **0.5 when the learner has no habits at all**:

```
no habits:            habit_ratio = 0.5  →  contributes 0.30
five aligned habits:  habit_ratio = 0.0  →  contributes 0.00
```

**Building habits toward your life path strictly lowers your alignment score.** The
dimension carrying 25% of the total inverts on the channel the philosophy calls the
deepest form of applied knowledge.

### Why it survived

Zero is a plausible reading. A learner with no habits and a learner with five
perfectly-aligned habits both produce a number the dashboard renders without
complaint; only comparing them exposes it. Nothing seeds a `REINFORCES_KNOWLEDGE`
edge and asserts the dimension moves — and a test that seeded `APPLIES_KNOWLEDGE`
instead would pass against the bug.

### Decide, don't just swap the edge

1. **Replace the hand-rolled weights with `USER_SUBSTANCE_CHANNELS`.** `0.6 * mastery
   + 0.05/task + 0.10/habit` is a third hand-copy of the substance table, already
   missing entries (events, entries, choices, principles never appear). Correcting
   one edge preserves the duplication that produced the defect.
2. **`CASE WHEN total = 0 THEN 0.5`** reports a learner with no habits as half
   aligned. That default is what makes the inversion above possible; it needs a
   ruling of its own.
3. **Ownership is expressed two ways in sibling queries** — the `user_uid` *property*
   at lines 289-290, the `OWNS` *edge* at 317/321. Both are populated on every owned
   activity in the live graph today (91 tasks / 5 habits / 10 choices / 6 events /
   2 principles, all carrying both), so this is a consistency hazard rather than a
   live defect — but two mechanisms is one too many.

Any fix needs a real-Neo4j test that seeds a `REINFORCES_KNOWLEDGE` edge and asserts
the dimension **changes**; model it on
`tests/integration/test_life_path_alignment_learner_scope.py`.

---

## 2. A designated life path's label and `entity_type` disagree

**Site**: `adapters/persistence/neo4j/lifepath_backend.py:155` (`designate_life_path`),
`:190` (`remove_designation`)
**Severity**: raises for exactly the paths a caller means to read.

Designation promotes an existing LearningPath by mutating a property **in place**:

```cypher
MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'learning_path'})
...
SET lp.entity_type = 'life_path'
```

The Neo4j **label is never changed**. The node stays `:Entity:LearningPath` while its
`entity_type` says `life_path`, so the two disagree and every reader sees a different
answer depending on which it keys on:

- `LpBackend._get_by_uid` MATCHes `(n:LearningPath {uid})` — still matches.
- It then calls `from_neo4j_node(..., LearningPath)`, and `LearningPath.__post_init__`
  (`core/models/pathways/learning_path.py:45`) enforces honest leaf identity (G6) and
  **raises**:

```
ValueError: LearningPath constructed with entity_type=<EntityType.LIFE_PATH: 'life_path'>
            (uid='lp.x') — the writer persisted a wrong type (G6)
```

A `ValueError` is in `DATA_CONVERSION_EXCEPTIONS`, so callers that wrap it report a
system error; callers that do not, propagate.

### Known reachable site

`LifePathAlignmentService._get_life_path_details`
(`core/services/lifepath/lifepath_alignment_service.py:173`) calls
`self.lp_service.core.get(life_path_uid)` with a designated uid and guards with
`if lp_result.is_ok and lp_result.value` — but a raise is not a `Result`, so the
guard is not on the path the failure takes.

Sweep the rest before fixing: `git grep -n "lp_service" core/ adapters/ ui/`, then
check which call sites can receive a designated uid.

### Options

- **(a) Swap the label too** on designate/remove (`REMOVE lp:LearningPath SET lp:LifePath`).
  `NeoLabel.LIFE_PATH` already exists. Must round-trip — `remove_designation` reverts
  the type today and would have to revert the label.
- **(b) Stop mutating `entity_type`** and let the `ULTIMATE_PATH` edge alone carry the
  designation. Cleanest ontologically (a life path *is* a learning path you chose),
  but every `{entity_type: 'life_path'}` predicate in this backend moves to an edge
  traversal.
- **(c) Make every reader property-keyed**, as
  `LifePathBackend.get_life_path_composition` now is. Leaves the divergence in place
  and relies on discipline.

Whatever is chosen must round-trip through `remove_designation`, and the `:LifePath`
label's index (if any) has to move with it — an index holds a label alive at zero
nodes.

### Current mitigation

`AnalyticsLifePathService` no longer touches `LpService`; it reads through
`LifePathService.get_life_path_composition`, which is keyed on `entity_type` and
returns rows rather than a `LearningPath` model.
`tests/integration/test_life_path_alignment_learner_scope.py` drives the **real**
`designate_life_path` writer rather than hand-seeding the promoted state, so that
test fails if designation's output shape changes.

---

## Finding more of this class

Both items are silent-zero defects: the metric returns a number, the number is
wrong, and nothing distinguishes it from a learner who genuinely did nothing.

- **A weighted term whose input is always zero is invisible.** For any hand-written
  scoring Cypher, check each `count(...)` arm can actually be non-zero — seed one row
  and assert the score *moves*, not that it is non-empty.
- **An edge name in Cypher is never validated by Neo4j** — a wrong one matches zero
  rows silently (SKUEL030 / CYP011 catch *unregistered* names; `APPLIES_KNOWLEDGE` is
  registered, just wrong for habits). Check the edge against its **writer**, not
  against a plausible reading of the name.
- **When a label and a discriminator property both identify a node, they will
  diverge.** Ask which one each reader keys on before trusting either.
