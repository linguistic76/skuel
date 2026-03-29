# Lesson Activity Wiring Guide

**Purpose:** How to wire Activity domains (Habits, Tasks, Events, Goals, Principles, Choices) to Lessons so learners can practice what they learn.

**Audience:** Curriculum developers authoring YAML content for SKUEL.

**Prerequisite:** Familiarity with Lesson and Ku authoring (see [CURRICULUM_DEVELOPER_GUIDE.md](/docs/guides/CURRICULUM_DEVELOPER_GUIDE.md)).

**Last Updated:** 2026-03-29

---

## The Core Idea

A Lesson teaches concepts. Activities put those concepts into practice. By wiring activities directly to Lessons, each Lesson becomes a self-contained learning unit — it knows what to teach AND how to practice.

```
Lesson (what to learn)
  ├── BUILDS_HABIT → Habit (behavior to repeat)
  ├── ASSIGNS_TASK → Task (work to complete)
  ├── SCHEDULES_EVENT → Event (time to commit)
  ├── SUPPORTS_GOAL → Goal (outcome to pursue)
  ├── GUIDED_BY_PRINCIPLE → Principle (value to embody)
  └── INFORMS_CHOICE → Choice (decision to consider)
```

LearningSteps inherit activities from their Lessons automatically — you never wire activities to an LS directly.

---

## The 6 Activity YAML Fields

Add these fields to any Lesson YAML file. Each creates a Neo4j relationship from the Lesson to the referenced activity entity.

### `habit_uids` — Behaviors to Build

```yaml
habit_uids:
  - habit:daily-2min-breath
  - habit:evening-reflection
```

**Relationship:** `(Lesson)-[:BUILDS_HABIT]->(Habit)`

Use when the Lesson teaches a practice that requires daily repetition. The learner sees the suggested habit and can adopt it.

### `task_uids` — Work to Complete

```yaml
task_uids:
  - task:log-first-5-sessions
  - task:write-reflection-essay
```

**Relationship:** `(Lesson)-[:ASSIGNS_TASK]->(Task)`

Use when the Lesson has a concrete deliverable — something the learner produces once.

### `event_template_uids` — Time to Commit

```yaml
event_template_uids:
  - event:practice-block-2min
  - event:weekly-review-session
```

**Relationship:** `(Lesson)-[:SCHEDULES_EVENT]->(Event)`

Use when the Lesson requires scheduling dedicated practice time.

### `goal_uids` — Outcomes to Pursue

```yaml
goal_uids:
  - goal:mindfulness-beginner
  - goal:reduce-stress
```

**Relationship:** `(Lesson)-[:SUPPORTS_GOAL]->(Goal)`

Use when the Lesson contributes toward a larger outcome the learner is working toward.

### `principle_uids` — Values to Embody

```yaml
principle_uids:
  - principle:small-steps
  - principle:consistency-over-intensity
```

**Relationship:** `(Lesson)-[:GUIDED_BY_PRINCIPLE]->(Principle)`

Use when the Lesson is grounded in a guiding value that shapes how the learner approaches the material.

### `choice_uids` — Decisions to Consider

```yaml
choice_uids:
  - choice:2-minutes-right-now
  - choice:2-minutes-before-bed
```

**Relationship:** `(Lesson)-[:INFORMS_CHOICE]->(Choice)`

Use when the Lesson presents options the learner should actively decide between.

---

## Full Example: Lesson File (Markdown Format)

Lessons are `.md` files with YAML frontmatter. Activity wiring fields go in the frontmatter alongside other metadata. The markdown body is the teaching content.

```markdown
---
type: Lesson
uid: l:mindfulness:breath-awareness-basics
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
    - l:mindfulness:posture-basics
    - l:mindfulness:mind-wandering-happens

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

Activity entities are `.yaml` files. They wire back to lessons via the `connections` block — this is the reverse link that enables substance tracking.

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
    - l:mindfulness:breath-awareness-basics
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

**Two-directional wiring:** The Lesson points to the Habit via `habit_uids` (forward link). The Habit points back to the Lesson via `connections.reinforces_knowledge` (reverse link for substance tracking). Both are needed for the full graph.

---

## How LearningStep Inherits

When a LearningStep references Lessons via `knowledge_uids`, it automatically inherits all activity wiring through graph traversal:

```
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:BUILDS_HABIT]->(Habit)
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:ASSIGNS_TASK]->(Task)
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:SCHEDULES_EVENT]->(Event)
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:SUPPORTS_GOAL]->(Goal)
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:GUIDED_BY_PRINCIPLE]->(Principle)
(LS)-[:HAS_LESSON|CONTAINS_KNOWLEDGE]->(Lesson)-[:INFORMS_CHOICE]->(Choice)
```

This means:

- **Do NOT** add `habit_uids`, `task_uids`, etc. to LearningStep YAML
- **DO** add them to the Lesson YAML files that the LS references via `knowledge_uids`
- An LS with 3 Lessons automatically aggregates activities from all 3

### Example LS (no activity fields)

```yaml
version: 1.0
type: LearningStep

uid: ls:mindfulness-101:step-1
title: Two Minutes Today
intent: Try one two-minute breath session, note what you notice

knowledge_uids:
  - l:mindfulness:breath-awareness-basics   # Activities on this Lesson are inherited

trains_ku_uids:
  - ku:mindfulness:breath

learning_path_uid: lp:mindfulness-101
sequence: 1
```

---

## Substance Tracking

When learners create activities that link back to Lessons, the Curriculum base class tracks substance counters:

| Counter | Incremented By |
|---|---|
| `times_applied_in_tasks` | Task with `APPLIES_KNOWLEDGE → Lesson` |
| `times_built_into_habits` | Habit with `REINFORCES_KNOWLEDGE → Lesson` |
| `times_practiced_in_events` | Event with `PRACTICES_KNOWLEDGE → Lesson` |
| `choices_informed_count` | Choice with `INFORMED_BY_KNOWLEDGE → Lesson` |
| `journal_reflections_count` | Journal with reflection on Lesson content |

These counters measure how much the knowledge is being *lived*, not just read. A Lesson with high substance means learners are actively practicing.

---

## The Authoring Pattern

1. **Define atomic Kus** — `.yaml` files, one concept each
2. **Write the Lesson** — `.md` file with frontmatter metadata and markdown body
3. **Define activity entities** — `.yaml` files for Habit, Task, Event, Goal, Principle, Choice
4. **Wire both directions:**
   - **Forward:** Add `habit_uids`, `task_uids`, etc. to the Lesson frontmatter
   - **Reverse:** Add `connections.reinforces_knowledge`, `connections.applies_knowledge`, etc. to each activity YAML
5. **Group Lessons into LS** — `.yaml` files referencing Lessons via `knowledge_uids`
6. **Sequence LS into LP** — `.yaml` file referencing Steps via `connections.contains_steps`
7. **Write edge files** — `.yaml` files in `edges/` for curriculum structure and cross-domain connections

Not every Lesson needs all 6 activity types. Start with what fits the content. The Mindfulness 101 bundle wires all 6 to its primary lesson (breath awareness) but only 3 to the secondary (mind wandering). The Self-Reflection 101 bundle has 2 habits, 2 principles, 2 tasks, 2 choices, 1 goal, and 1 event across 3 lessons — distributed by relevance, not evenly spread.

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
