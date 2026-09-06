---
title: "Goal Progress Reads an Edge Nothing Writes"
updated: 2026-09-06
status: "open — live bug, fix scoped"
trigger: "none — this is a defect, not a deferral; scheduled for immediately after the vault-door completion-cascade arc"
check: "`git grep -n 'SUPPORTS_GOAL' adapters/persistence/neo4j/backends/activity_backends.py` — four reader queries put the Goal on the LEFT of the arrow; every production writer puts it on the right, and for Tasks uses FULFILLS_GOAL instead"
registered: "2026-09-06 (found while checking a Codex example on #1290)"
---

# Goal Progress Reads an Edge Nothing Writes

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What is wrong

Four reader queries in `adapters/persistence/neo4j/backends/activity_backends.py` match

```
(goal:Entity {entity_type: 'goal'})-[:SUPPORTS_GOAL]->(activity:Entity)
```

- `_find_linked_goals` — behind `find_linked_goals_for_task` and `find_linked_goals_for_habit`
- `count_linked_tasks`
- `count_linked_habits_avg_streak`

No production writer produces that shape, for either domain:

| Link | What the registry declares and the writers write | What the readers match |
|---|---|---|
| Task → Goal | `(Task)-[:FULFILLS_GOAL]->(Goal)` — `GOALS_CONFIG` `contributing_tasks`, incoming; dual-written with `Task.fulfills_goal_uid` on every door (#1260) | `(Goal)-[:SUPPORTS_GOAL]->(Task)` — **wrong relationship type** *and* wrong direction |
| Habit → Goal | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` — `GOALS_CONFIG` `contributing_habits`, incoming; `link_goal_to_habit`, `GoalsCoreService._write_link_edges` | `(Goal)-[:SUPPORTS_GOAL]->(Habit)` — right type, **reversed** |

`SUPPORTS_GOAL` is the Habit→Goal edge. `FULFILLS_GOAL` is the Task→Goal edge. The readers use the
habit's relationship for tasks, and reverse both.

## What it costs

`GoalsProgressService` subscribes to `TaskCompleted` and `HabitCompleted` unconditionally
(`_event_wiring.py`, no tier gate). Both handlers call these readers, get an empty list, log
*"is not linked to any goals"* at DEBUG and return. So **event-driven goal progress never updates
from a task or habit completion**, on any door — API, UI, DSL, and now the vault. The progress
recompute that counts linked tasks/habits has the same blindness.

This is not a vault-door problem. The vault door is only where it was noticed: a Codex finding on
#1290 cited `find_linked_goals_for_task` as a subscriber that would miss ingest-written edges, and
checking whether the ingest config writes that edge showed nothing writes it.

## Why the tests are green

`tests/integration/test_task_goal_event_flow.py` and `test_habit_goal_event_flow.py` seed the
**reader's** shape by hand:

```cypher
MERGE (goal)-[:SUPPORTS_GOAL]->(task)   -- test_task_goal_event_flow.py:163
MERGE (goal)-[:SUPPORTS_GOAL]->(habit)  -- test_habit_goal_event_flow.py:159
```

Raw Cypher, not a production writer — so the fixtures agree with the query and disagree with the
graph. This is exactly the failure mode `feedback_fixtures_mirror_writer_shapes` names: a fixture
that mirrors the reader proves the reader runs, never that anything produces what it reads.

## Fixing it

1. **Decide the direction from the registry, not from the query.** `GOALS_CONFIG` is the source of
   truth: both links are declared *incoming* to Goal, so the activity is the edge source.
2. Rewrite the four readers: `(Task)-[:FULFILLS_GOAL]->(Goal)` for the task paths,
   `(Habit)-[:SUPPORTS_GOAL]->(Goal)` for the habit paths.
3. **Re-seed both integration tests through the production writers** (`link_goal_to_habit`, the task
   create/update door's `fulfills_goal_uid`) rather than raw Cypher. Rewriting the queries while
   leaving hand-seeded fixtures in place would move the lie, not remove it.
4. Check for existing graph data in the reader's shape before assuming there is none to migrate —
   the migration `scripts/migrations/merge_lesson_into_pathstep_2026_04.cypher` copies
   `SUPPORTS_GOAL` edges wholesale and is not direction-aware.
5. Then confirm the cascade end to end: complete a task linked to a goal through the real door and
   assert the goal's progress moved.

⚠ Do **not** "fix" this by making the writers match the readers. The registry declaration and every
writer already agree with each other; only the four queries disagree.
