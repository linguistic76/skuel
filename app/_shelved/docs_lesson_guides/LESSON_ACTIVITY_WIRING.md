# PathStep Activity Wiring Guide

**Purpose:** How to wire Activity domains (Habits, Tasks, Events, Goals, Principles, Choices) to PathSteps so learners can practice what they learn.

**Audience:** Curriculum developers authoring YAML content for SKUEL.

**Prerequisite:** Familiarity with PathStep and Ku authoring (see [CURRICULUM_DEVELOPER_GUIDE.md](/docs/guides/CURRICULUM_DEVELOPER_GUIDE.md)).

**Last Updated:** 2026-04-12

> **Historical note:** Prior to 2026-04, curriculum content was split between `Lesson` (teaching) and `PathStep` (sequencing). The two types were merged — `PathStep` is now THE curriculum content entity. Activity-domain relationships that used to live on Lessons now live directly on PathSteps. Any historical reference to "Lesson → BUILDS_HABIT → Habit" should be read as "PathStep → BUILDS_HABIT → Habit".

---

## The Core Idea

A PathStep teaches concepts (by composing Kus). Activities put those concepts into practice. By wiring activities directly to PathSteps, each PathStep becomes a self-contained learning unit — it knows what to teach AND how to practice.

```
PathStep (what to learn)
  ├── USES_KU → Ku (atomic concept)
  ├── BUILDS_HABIT → Habit (behavior to repeat)
  ├── ASSIGNS_TASK → Task (work to complete)
  ├── SCHEDULES_EVENT → Event (time to commit)
  ├── SUPPORTS_GOAL → Goal (outcome to pursue)
  ├── GUIDED_BY_PRINCIPLE → Principle (value to embody)
  └── INFORMS_CHOICE → Choice (decision to consider)
```

All activity relationships are authored directly on the PathStep — there is no intermediate entity. LearningPaths inherit activities from their PathSteps automatically via graph traversal; you never wire activities to an LP directly.

---

## The 6 Activity YAML Fields

Add these fields to any PathStep YAML file. Each creates a Neo4j relationship from the PathStep to the referenced activity entity.

### `habit_uids` — Behaviors to Build

```yaml
habit_uids:
  - habit:daily-2min-breath
  - habit:evening-reflection
```

**Relationship:** `(PathStep)-[:BUILDS_HABIT]->(Habit)`

Use when the PathStep teaches a practice that requires daily repetition. The learner sees the suggested habit and can adopt it.

### `task_uids` — Work to Complete

```yaml
task_uids:
  - task:log-first-5-sessions
  - task:write-reflection-essay
```

**Relationship:** `(PathStep)-[:ASSIGNS_TASK]->(Task)`

Use when the PathStep has a concrete deliverable — something the learner produces once.

### `event_template_uids` — Time to Commit

```yaml
event_template_uids:
  - event:practice-block-2min
  - event:weekly-review-session
```

**Relationship:** `(PathStep)-[:SCHEDULES_EVENT]->(Event)`

Use when the PathStep requires scheduling dedicated practice time.

### `goal_uids` — Outcomes to Pursue

```yaml
goal_uids:
  - goal:mindfulness-beginner
  - goal:reduce-stress
```

**Relationship:** `(PathStep)-[:SUPPORTS_GOAL]->(Goal)`

Use when the PathStep contributes toward a larger outcome the learner is working toward.

### `principle_uids` — Values to Embody

```yaml
principle_uids:
  - principle:small-steps
  - principle:consistency-over-intensity
```

**Relationship:** `(PathStep)-[:GUIDED_BY_PRINCIPLE]->(Principle)`

Use when the PathStep is grounded in a guiding value that shapes how the learner approaches the material.

### `choice_uids` — Decisions to Consider

```yaml
choice_uids:
  - choice:2-minutes-right-now
  - choice:2-minutes-before-bed
```

**Relationship:** `(PathStep)-[:INFORMS_CHOICE]->(Choice)`

Use when the PathStep presents options the learner should actively decide between.

---

## Full Example: PathStep File (Markdown Format)

PathSteps are `.md` files with YAML frontmatter. Activity wiring fields go in the frontmatter alongside other metadata. The markdown body is the teaching content.

```markdown
---
type: PathStep
uid: ps:mindfulness:breath-awareness-basics
title: Breath Awareness — Basics
sel_category: self_awareness
learning_level: beginner
complexity: basic
domain: personal
estimated_time_minutes: 10

uses_kus:
  - ku:mindfulness:breath
  - ku:mindfulness:attention

connections:
  requires: []
  enables:
    - ps:mindfulness:posture-basics
    - ps:mindfulness:mind-wandering-happens

# Activity domain wiring
habit_uids:
  - habit:daily-2min-breath

task_uids:
  - task:log-first-5-sessions

event_template_uids:
  - event:practice-block-2min

goal_uids:
  - goal:mindfulness-beginner

principle_uids:
  - principle:small-steps

choice_uids:
  - choice:2-minutes-right-now
  - choice:2-minutes-before-bed

tags:
  - breath
  - meditation
  - beginner
---

## Why Breath?

You need an anchor — something to direct your attention toward...

## The Two-Minute Practice

1. **Sit comfortably.** Chair, floor, cushion — doesn't matter...
2. **Find the breath.** Don't change it. Just notice where you feel it most...

## Practice: Find Your Spot

Right now, take three natural breaths and answer one question:
where do you feel the breath most?
```

**Note:** The activity UID fields (`habit_uids`, `task_uids`, etc.) live in the YAML frontmatter, not in the markdown body. The ingestion system reads them from the frontmatter and creates the corresponding Neo4j relationships.

## Full Example: Activity Entity (YAML Format)

Activity entities are `.yaml` files. They wire back to PathSteps via the `connections` block — this is the reverse link that enables substance tracking.

```yaml
version: 1.0
type: Habit

uid: habit:daily-2min-breath
name: Daily Two-Minute Breath
description: One tiny session per day. That's it.

polarity: build
category: mindfulness
difficulty: easy
recurrence_pattern: daily
target_days_per_week: 7
preferred_time: morning
duration_minutes: 2

# Reverse connections — these create substance-tracking edges
connections:
  reinforces_knowledge:
    - ps:mindfulness:breath-awareness-basics
  supports_goal:
    - goal:mindfulness-beginner
  embodies_principle:
    - principle:small-steps

cue: After morning coffee / Right after waking
routine: |
  1. Sit comfortably
  2. Set 2-minute timer
  3. Close eyes, follow breath
  4. Return gently when mind wanders
reward: Calm start to day / Sense of accomplishment

status: active
priority: high
tags:
  - habit
  - mindfulness
  - breath
  - daily
```

**Two-directional wiring:** The PathStep points to the Habit via `habit_uids` (forward link). The Habit points back to the PathStep via `connections.reinforces_knowledge` (reverse link for substance tracking). Both are needed for the full graph.

---

## How LearningPath Inherits

A LearningPath is an ordered sequence of PathSteps. Practice and guidance coverage is authored at the PathStep level and automatically aggregates at the LP level via graph traversal:

```
(LP)-[:CONTAINS_STEP]->(PS)-[:BUILDS_HABIT]->(Habit)
(LP)-[:CONTAINS_STEP]->(PS)-[:ASSIGNS_TASK]->(Task)
(LP)-[:CONTAINS_STEP]->(PS)-[:SCHEDULES_EVENT]->(Event)
(LP)-[:CONTAINS_STEP]->(PS)-[:SUPPORTS_GOAL]->(Goal)
(LP)-[:CONTAINS_STEP]->(PS)-[:GUIDED_BY_PRINCIPLE]->(Principle)
(LP)-[:CONTAINS_STEP]->(PS)-[:INFORMS_CHOICE]->(Choice)
```

This means:

- **Do NOT** add `habit_uids`, `task_uids`, etc. to LearningPath YAML
- **DO** add them to the PathStep YAML files the LP references via `connections.contains_steps`
- An LP with 3 PathSteps automatically aggregates activities from all 3

### Example LP (no activity fields)

```yaml
version: 1.0
type: LearningPath

uid: lp:mindfulness-101
title: Mindfulness 101
description: A three-step introduction to mindful breath practice.

connections:
  contains_steps:
    - ps:mindfulness:breath-awareness-basics
    - ps:mindfulness:posture-basics
    - ps:mindfulness:mind-wandering-happens
```

---

## Substance Tracking

When learners create activities that link back to PathSteps, the Curriculum base class tracks substance counters:

| Counter | Incremented By |
|---|---|
| `times_applied_in_tasks` | Task with `APPLIES_KNOWLEDGE → PathStep` |
| `times_built_into_habits` | Habit with `REINFORCES_KNOWLEDGE → PathStep` |
| `times_practiced_in_events` | Event with `PRACTICES_KNOWLEDGE → PathStep` |
| `choices_informed_count` | Choice with `INFORMED_BY_KNOWLEDGE → PathStep` |
| `journal_reflections_count` | Journal with reflection on PathStep content |

These counters measure how much the knowledge is being *lived*, not just read. A PathStep with high substance means learners are actively practicing.

---

## The Authoring Pattern

1. **Define atomic Kus** — `.yaml` files, one concept each
2. **Write the PathStep** — `.md` file with frontmatter metadata and markdown body
3. **Define activity entities** — `.yaml` files for Habit, Task, Event, Goal, Principle, Choice
4. **Wire both directions:**
   - **Forward:** Add `habit_uids`, `task_uids`, etc. to the PathStep frontmatter
   - **Reverse:** Add `connections.reinforces_knowledge`, `connections.applies_knowledge`, etc. to each activity YAML
5. **Sequence PathSteps into LP** — `.yaml` file referencing steps via `connections.contains_steps`
6. **Write edge files** — `.yaml` files in `edges/` for curriculum structure and cross-domain connections

Not every PathStep needs all 6 activity types. Start with what fits the content. The Mindfulness 101 path wires all 6 to its primary step (breath awareness) but only 3 to the secondary (mind wandering). Distribute activities by relevance, not evenly across steps.

### Practical Tip: Which Activities to Write First

When building a new domain, start with the **Habit** and the **Task**. These are the most concrete — "what should the learner do every day?" and "what should the learner produce once?" The Goal, Principle, Choice, and Event can follow once the core practice is clear.

---

## Quick Reference

| YAML Field | Neo4j Relationship | Target Entity |
|---|---|---|
| `habit_uids` | `BUILDS_HABIT` | Habit |
| `task_uids` | `ASSIGNS_TASK` | Task |
| `event_template_uids` | `SCHEDULES_EVENT` | Event |
| `goal_uids` | `SUPPORTS_GOAL` | Goal |
| `principle_uids` | `GUIDED_BY_PRINCIPLE` | Principle |
| `choice_uids` | `INFORMS_CHOICE` | Choice |

**See:** [CURRICULUM_DEVELOPER_GUIDE.md](/docs/guides/CURRICULUM_DEVELOPER_GUIDE.md), [YAML_AUTHORING_GUIDE.md](/docs/guides/YAML_AUTHORING_GUIDE.md)
