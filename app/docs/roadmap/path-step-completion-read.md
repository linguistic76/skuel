---
title: "Path Step Completion Read"
updated: 2026-11-23
status: "open — ruled, not built: the read takes a learner's completion of a step from their MASTERED edge"
registered: "2026-11-23 (bootstrap typing residuals, row 2i-b-v)"
ruled: "2026-11-23 — a learner has completed a step when they have mastered it: their MASTERED edge to it; its own row"
trigger: "the row is taken up"
check: "grep -nE '(step|prereq_step|s)\\.completed' adapters/persistence/neo4j/user_context_queries.py — a hit means the statement still reads the property"
---

# Path Step Completion Read

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What it reads

The user-context statement for a learner's curriculum (`adapters/persistence/neo4j/user_context_queries.py`)
reads a `completed` property off `PathStep` nodes in three places:

- each enrolled path's `graph_context.steps[].completed`, from the path's `HAS_STEP` targets;
- the path's `completed_steps` and `progress_percentage`, counted from those steps' `completed = true`;
- each active step's `prerequisite_steps[].completed`, from its `REQUIRES_STEP` targets.

## Why it reads nothing

No writer stores `completed` on a `PathStep`, and none should: a step is shared curriculum, so a
property on it would mark it completed for every learner at once. The stored-value census, which
names every stored key that is neither a field nor registered node state, found none on the live
graph when this was registered. So every enrolled path reads `completed_steps: 0` and
`progress_percentage: 0.0`, and every step's `completed` is null.

`UserContext.enrolled_paths_rich` carries these to its readers. Askesis's grounding projection
(`core/services/askesis/grounding_projection.py`, `_path_entry`) prints each enrolled path as
"{title} ({completed}/{total} steps)", so the LLM is told the learner has completed no step of any
path.

## The ruling

A learner has completed a step when they have mastered it: `(user)-[:MASTERED]->(step)`. That is the
edge `PsMasteryService` writes when it publishes `PathStepCompleted`, and the one
`MASTERED_PATH_STEPS_QUERY` reads for `UserContext.mastered_ps_uids`. The statement binds `user`, so
each of the three sites can read the edge for this learner.

## The test that keeps it seeded

`tests/integration/test_rich_context_statement_equivalence.py` seeds `completed: true/false` on its
path steps, and its assertions (`completed_steps: 1`, `progress_percentage: 50.0`, a prerequisite
step `completed: true`) hold only because of that key. The integration graph census refuses it — a
key no field names — so the five tests over that seed carry `stores_undeclared_key`, naming this
file. Without the key they read what every learner reads: `0`, `0.0` and null.

## What the build changes

The three sites read the learner's `MASTERED` edge; the equivalence seed drops `completed` and
expresses each completion it wants as an edge, and its marker goes. The statement's size is held by
`tests/integration/test_user_context_plan_cache.py`.
