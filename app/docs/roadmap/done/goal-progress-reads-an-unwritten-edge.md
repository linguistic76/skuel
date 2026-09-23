---
title: "Goal Progress Reads an Edge Nothing Writes"
updated: 2026-09-23
status: done
registered: "2026-09-06 (found while checking a Codex example on #1290)"
---

# Goal Progress Reads an Edge Nothing Writes

*Fixed 2026-09-23. Registered 2026-09-06 as a [deferred-work.md](../deferred-work.md) entry;
the defect as found is kept below, followed by [what shipped](#what-shipped).*

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

## What shipped

**The readers now match the registry.** Every `GoalsBackend` reader of an activity→goal link
puts the activity on the left: `(Task)-[:FULFILLS_GOAL]->(Goal)` for `find_linked_goals_for_task`
and `count_linked_tasks`, and `(Habit)-[:SUPPORTS_GOAL]->(Goal)` for `find_linked_goals_for_habit`
and `count_linked_habits_avg_streak`. `_find_linked_goals` takes the relationship as a parameter
now, so the two domains can no longer share the habit's edge type.

**There was a fifth reader.** `get_achievement_context`, which feeds the `GoalAchieved`
recommendations, matched `(goal)-[:SUPPORTS_GOAL]->(habit)`. It also filtered its knowledge
branch on `entity_type = 'knowledge_unit'`, a value no node carries (`EntityType.KU` is `'ku'`).
So two of the four recommendation strategies, habit reinforcement and knowledge expansion, had
never fired. Both are fixed.

**There was a third hand-seeded fixture.** `test_goal_recommendations_flow.py` seeded the
reversed habit edge, and it also overwrote its Kus' `entity_type` to `'knowledge_unit'` so the
broken filter would match. All three files now link through production writers:

- Task→Goal: `TasksCoreService.create` with `fulfills_goal_uid`.
- The other links: `UnifiedRelationshipService.create_relationship` over `GOALS_CONFIG`, which is
  the call `GoalsService.link_goal_to_habit`, `link_goal_to_knowledge` and
  `link_goal_to_principle` delegate to.

Nodes come from the domain backends, so they carry the domain labels the registry validates
against. Two task tests seeded one task fulfilling two goals, which no writer produces because the
link is `single`. They were deleted, and a habit→two-goals test now covers the handler's per-goal
loop.

**MIXED goals are no longer recomputed by completions.** With the readers fixed, each handler's
MIXED branch would have run for the first time. That branch blended one component into the
stored figure (`old × 0.7 + share × 30`), so every completion fed the previous result into the
next (Codex, #1407). Both branches were deleted. This changes no live behavior, since no MIXED goal
had ever moved. A real recompute is registered as
[mixed-goal-event-progress.md](../mixed-goal-event-progress.md).

**End to end:** `tests/integration/test_goal_progress_cascade.py` runs on the composed app
(`skuel_app`), so the handler is subscribed by the real event wiring. It checks three things, and
each assertion failed on the old readers:

- A task completed through `update_task` moves its goal.
- A habit completed through `complete_habit_with_quality` moves its goal.
- `get_achievement_context` returns the linked habits and Kus.

**Migration: none needed.** A read-only count on AuraDB (2026-09-23) found 0 edges in the reader
shape. The graph held 2 `(habit)-[:SUPPORTS_GOAL]->(goal)` and 2 `(task)-[:FULFILLS_GOAL]->(goal)`
edges, and both tasks' `fulfills_goal_uid` agreed with their edge.
