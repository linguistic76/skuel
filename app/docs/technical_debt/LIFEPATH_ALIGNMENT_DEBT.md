---
title: LifePath Alignment Debt
updated: 2026-08-28
status: resolved
category: technical-debt
tags: [lifepath, analytics, substance, cypher, technical-debt, graph-vocabulary]
related: [ANALYTICS_UNTYPED_SEAM_DEFECTS.md, knowledge_substance_philosophy.md]
---

# LifePath Alignment Debt

**Status**: ✅ RESOLVED (2026-08-12). Both items fixed and guarded.
**Item 1** — habits contributed nothing to any dimension, and the score inverted
— PR #1039. **Item 2** — a designated path's label and `entity_type` disagreed,
so its title read as `"Unknown"` — PR #1040.

This file is kept as the record of the *failure class*, not as an open backlog.
Read § [Finding more of this class](#finding-more-of-this-class) before writing
any hand-rolled scoring Cypher; that section is the reusable part.

## What was wrong, and what it is now

| | Was | Is |
|---|---|---|
| Habit→knowledge edge | `APPLIES_KNOWLEDGE` in 2 queries, absent from momentum | `REINFORCES_KNOWLEDGE`, via the shared alternation; momentum has a habit arm |
| Substance weights | `0.6*mastery + 0.05/task + 0.10/habit`, hand-copied into Cypher, 4 channels missing, no caps | `USER_SUBSTANCE_CHANNELS`, all six channels + per-channel caps, applied in the service |
| No-data default | `CASE WHEN total = 0 THEN 0.5`, in 4 queries | `0.0` for the four levels; momentum alone keeps `0.5` (it is a derivative) |
| Where scoring lives | Ratios, weights and bands inside Cypher | `LifePathAlignmentService`; the backend returns counts and mastery |
| Designation | `SET lp.entity_type = 'life_path'` in place, label untouched | The `ULTIMATE_PATH` edge alone; the node is never mutated |
| Failed reads | Logged, returned `0.0` / `0.5` / `None` | Propagate as `Result.fail` through the facade |

**Scores are not comparable across the fix.** Any stored
`ULTIMATE_PATH.alignment_score` or `ALIGNMENT_SNAPSHOT` predating 2026-08-12 is
on the old basis.

**Migration — none needed (verified 2026-08-28, deleted).** A one-shot repair for
nodes the old writer had promoted in place (`:LearningPath` carrying
`entity_type: 'life_path'`) was staged but never run; the live graph
(AuraDB `d2d160c4`) holds zero such nodes and zero `ULTIMATE_PATH` edges, and
the writer that could create them is gone (#1040). The script was deleted
rather than kept as a dead migration — should the mismatch ever reappear, the
fix is the same two-line `MATCH (n:Entity:LearningPath {entity_type: 'life_path'})
SET n.entity_type = 'learning_path'`, scoped by the `:LearningPath` label that
distinguishes a promoted path from an authored `type: life_path` entity.

## Three alignment metrics, one name

SKUEL computes "life path alignment" three times, and no two share code. Check
which one a caller means before comparing numbers.

| | `LifePathAlignmentService.calculate_alignment` | `AnalyticsLifePathService.calculate_life_path_alignment` | `user/intelligence/life_path_intelligence.py` |
|---|---|---|---|
| Shape | 5 weighted dimensions (knowledge .25, activity .25, goal .20, principle .15, momentum .15) | mean personal substance over the path's steps | the same 5 dimension names and weights, in memory |
| Input | Neo4j, via `LifePathBackend` | Neo4j, via the substance channels | `RichUserContext` — learning-goal prerequisites |
| Weights | `USER_SUBSTANCE_CHANNELS` | `USER_SUBSTANCE_CHANNELS` | its own |
| Written to | `ULTIMATE_PATH.alignment_score`, `ALIGNMENT_SNAPSHOT.score` | the analytics payload only | the intelligence payload only |
| State | **this file** — fixed 2026-08-12 | rewritten 2026-08-12 | untouched; no edge bug (it reads no Cypher) |

The third was found while fixing the first. It has no known defect, but it is a
third implementation of a metric the product presents as one number.

## 1. Habits contributed nothing to any dimension ✅

Habits link knowledge over **`REINFORCES_KNOWLEDGE`** (writer:
`HabitsCoreService`). Two queries matched them over `APPLIES_KNOWLEDGE` and a
third omitted them entirely. `APPLIES_KNOWLEDGE` *is* a registered
`RelationshipName`, so SKUEL030 and CYP011 both pass it — it is simply wrong for
that tail, and Neo4j answers an unwritten edge type with zero rows rather than an
error.

### The inversion

`calculate_activity_alignment` returned `task_ratio * 0.4 + habit_ratio * 0.6`,
and `habit_ratio` defaulted to **0.5 when the learner had no habits at all**.
Measured on `main` before the fix, seeding one habit reinforcing a Ku on the
learner's designated path:

| activity dimension | value |
|---|---|
| no habits at all (`habit_ratio` = 0.5 default) | **0.50** |
| 1 aligned habit, bug present (`aligned_habits` = 0) | **0.20** |
| 1 aligned habit, fixed | **0.67** |

**Building habits toward your life path strictly lowered your alignment** — on
the dimension carrying 25% of the total, through the channel the philosophy
calls the deepest form of applied knowledge.

⚠ **A test asserting the dimension "changed" is satisfied by 0.50 → 0.20 — by
the defect.** The guards therefore assert the *increase* and pin exact values, on
all three habit-dependent sites. Seeding `APPLIES_KNOWLEDGE` also passes against
the bug, and asserting "the result is non-empty" passes against both readings.

### Why it survived

Zero is a plausible reading. A learner with no habits and one with five
perfectly-aligned habits both produced a number the dashboard rendered without
complaint; only comparing them exposed it.

### The rulings taken

1. **Substance weights moved onto `USER_SUBSTANCE_CHANNELS`** — the Cypher spells
   no per-instance weight. This fixed the habit edge *by construction*: the
   channel read already matches `REINFORCES_KNOWLEDGE`.
2. **`0.0` for levels, `0.5` for momentum only.** A level with no evidence is not
   half-earned; a derivative with no data genuinely has no trend.
3. **Momentum gained a habit arm** on `created_at` — it measures the rate of new
   path-aligned *commitments*.
4. **Scoring policy left Cypher entirely**, so the no-data rule has one home.

Also fixed in passing: `status IN ['active','in_progress']` where `'in_progress'`
is not an `EntityStatus` member and no writer sets it; the discarded
`update_alignment_score` result; and `get_knowledge_substance_stats`, deleted for
re-running the identical traversal to band mastery the knowledge dimension
already reads.

**Guard:** `tests/integration/test_life_path_five_dimension_alignment.py`.

## 2. A designated life path's label and `entity_type` disagreed ✅

Designation promoted an existing LearningPath by mutating a property **in
place** (`SET lp.entity_type = 'life_path'`) and never changed the Neo4j label.
The node stayed `:Entity:LearningPath` while its `entity_type` said `life_path`,
so every reader saw a different answer depending on which it keyed on.

`LpBackend._get_by_uid` still MATCHed `(n:LearningPath {uid})`, then called
`from_neo4j_node(..., LearningPath)`, and `LearningPath.__post_init__` enforced
honest leaf identity (G6) and **raised**. `@safe_backend_operation`'s
`except Exception` safety net converted that into a `Result.fail`, so the failure
was indistinguishable from a database outage — exactly the amplifier
`ANALYTICS_UNTYPED_SEAM_DEFECTS.md` § 1 describes. `_get_life_path_details`
guarded with `if lp_result.is_ok` and returned `{"title": "Unknown"}`.

Reproduced against a real graph before fixing, driving the real writer: an
undesignated path read back fine; the same path after designation returned
`[critical] system:SYSTEM_ERROR - Unexpected error in get`.

### It cost three things, not one

The title was the visible one. Two more followed from the same mutation:

- **Re-designation was impossible.** The writer MATCHed its target only while
  `entity_type` was still `'learning_path'`, so designating the same path twice
  failed — which also meant no caller could retry after a mid-flow failure in
  `designate_and_calculate`, leaving the learner designated with no score.
- **A content-vault re-sync silently un-designated the path.** LearningPaths are
  vault-authored, and bulk ingest is
  `MERGE (n:Entity:LearningPath {uid}) ... ON MATCH SET n += props` with `props`
  carrying `entity_type: 'learning_path'`. The `ULTIMATE_PATH` edge survived
  while every property-keyed reader stopped matching.

That third one is what decided the ruling. It also ruled *out* the label-swap
option, which was the tidiest-looking of the three: the ingest `MERGE` could not
match a node whose `:LearningPath` label had been removed, so a re-sync would
have created a **duplicate node on the same uid**.

### The ruling taken: (b) stop mutating `entity_type`

The `ULTIMATE_PATH` edge alone carries the designation. The node stays an
ordinary LearningPath throughout, so `LpService` reads work, the designated path
stays visible on every LP surface, designation is idempotent, and a vault
re-sync cannot disturb it. `EntityType.LIFE_PATH` remains — it is still an
ingestible and searchable type — designation simply stops forging it.

⚠ **The invariant the guards assert is the TITLE, not any particular reader.**
The three options disagreed about which reader should succeed while designated;
asserting "`LpService.get` succeeds" would have ruled out option (a) by
construction. One test does assert that deliberately, labelled as pinning the
ruling rather than the invariant.

**Guard:** `tests/integration/test_life_path_designation_is_edge_only.py` —
title, round trip, idempotency, two users on one path, and a simulated vault
re-sync.

---

## Finding more of this class

Both items were silent-zero defects: the metric returns a number, the number is
wrong, and nothing distinguishes it from a learner who genuinely did nothing.
This section is why the file is kept.

- **A weighted term whose input is always zero is invisible.** For any
  hand-written scoring Cypher, check each `count(...)` arm can actually be
  non-zero — seed one row and assert the score *moves*, not that it is non-empty.
- **Assert the DIRECTION, not just movement.** The activity dimension moved on
  the defect; it moved the wrong way. "Changed" is the weakest assertion that
  looks adequate.
- **An edge name in Cypher is never validated by Neo4j** — a wrong one matches
  zero rows silently. SKUEL030 / CYP011 catch *unregistered* names;
  `APPLIES_KNOWLEDGE` is registered, just wrong for habits. Check the edge
  against its **writer**, not against a plausible reading of the name.
- **A hand-copied weight table drifts, and the drift is invisible too.** This one
  was missing four of six channels and every cap, and had been for long enough
  that nobody noticed the two it kept.
- **A no-data default is a claim.** `0.5` asserts "half aligned" about a learner
  the system knows nothing about, and it gives a broken metric a value to move
  away from. Decide it per dimension, and note that levels and rates want
  different answers.
- **When a label and a discriminator property both identify a node, they will
  diverge.** Ask which one each reader keys on before trusting either — and check
  what the *ingest upsert* does to the one you chose.
- **A broad error decorator makes a coding defect look like an outage.** Both
  items reached production behind one. See `ANALYTICS_UNTYPED_SEAM_DEFECTS.md`.

## Consequence still open

**`LifePathService.get_alignment_trend_data` has no non-test caller.** It is the
read half of a write that still happens in this domain (`update_alignment_score`
→ `record_alignment_snapshot`) and is covered by
`tests/integration/test_lifepath_designation_flow.py`, so it is kept as the
natural anchor for a LifePath-domain trend surface — not deleted as abandoned.
If that surface is never built, it should be revisited under One Path Forward.
