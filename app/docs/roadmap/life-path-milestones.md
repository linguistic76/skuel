---
title: "Life-Path Milestones — the Context Field Nothing Writes"
updated: 2026-10-09
status: "staged"
registered: "2026-10-09 (F8-3 — life-path knowledge and life-path goals)"
ruled: "2026-10-09 — the founder: life_path_milestones is marked for future development (staged)"
trigger: "the founder schedules milestones on the life path, or the Insights alignment card (F8-6) wants milestone progress"
check: "grep -rn 'life_path_milestones =' core/services/user/"
---

# Life-Path Milestones — the Context Field Nothing Writes

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What exists

- **The field.** `UserContext.life_path_milestones: list[str]`
  (`core/services/user/unified_user_context.py`): the major milestones on the user's life path.
  No builder, populator or service writes it, so every built context carries `[]`.
- **Its one reader: method 7.** `calculate_life_path_alignment()`
  (`core/services/user/intelligence/life_path_intelligence.py`) reports
  `life_path_milestones_total` (the field's length) and `life_path_milestones_completed`
  (`_count_completed_milestones`) on the `LifePathAlignment` record
  (`core/models/context_types.py`). A milestone uid counts as completed when it is a mastered Ku
  (`mastered_knowledge_uids`) or a goal at full progress (`goal_progress` ≥ 1.0).
- **What a user sees today:** 0 of 0 milestones, for every user. That answer is true, because no
  milestone has ever been set.

## Staged, not retired

The founder marked the field for future development. The capability is milestones along the life
path, counted toward its alignment. It stays, with its reader, until it gets a writer.

## The question the build answers first: what is a life-path milestone?

The reader already assumes a milestone is a Ku or a goal. Three populated notions sit near it:

1. **The designated path's milestone events.** `(LearningPath)-[:HAS_MILESTONE_EVENT]->(Event)`
   is a registry edge (`LearningPath.milestone_events`). Its completion would be the event's
   status, which `_count_completed_milestones` does not read.
2. **Milestone goals that serve the life path.** These are goals with `goal_type` `milestone`
   (`GoalType.MILESTONE`) that carry `SERVES_LIFE_PATH` (`life_path_goal_uids`, F8-3). This fits
   the reader's goal arm as written.
3. **Chosen Kus or steps of the path.** A set the user or the curriculum marks, read from
   `life_path_knowledge_uids`. This fits the reader's Ku arm.

Whichever is chosen, it is a new read in the rich build's `life_path_knowledge` statement (or its
own registry entry), and the reader's completion rule moves with it.
