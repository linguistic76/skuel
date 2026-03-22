# Lesson Activity Wiring Guide

**Purpose:** How to wire Activity domains (Habits, Tasks, Events, Goals, Principles, Choices) to Lessons so learners can practice what they learn.

**Audience:** Curriculum developers authoring YAML content for SKUEL.

**Prerequisite:** Familiarity with Lesson and Ku authoring (see [CURRICULUM_DEVELOPER_GUIDE.md](/docs/guides/CURRICULUM_DEVELOPER_GUIDE.md)).

**Last Updated:** 2026-03-22

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

## Full Example

```yaml
version: 1.0
type: Lesson

uid: l:mindfulness:breath-awareness-basics
title: Breath Awareness — Basics
content: |
  ## Introduction to Breath Awareness

  Breath awareness is the foundational practice of mindfulness meditation...

  ## The Basic Practice

  1. Find a comfortable position
  2. Close your eyes
  3. Notice your breath
  4. Follow the sensation
  5. When mind wanders — gently return

  ## Two Minutes is Enough

  Start small, be consistent.

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
```

---

## How LearningStep Inherits

When a LearningStep references Lessons via `primary_knowledge_uids`, it automatically inherits all activity wiring through graph traversal:

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
- **DO** add them to the Lesson YAML files that the LS references as primary knowledge
- An LS with 3 primary Lessons automatically aggregates activities from all 3

### Primary vs Supporting Knowledge

A LearningStep has two types of knowledge references, and they behave differently for activity inheritance:

| Field | Edge Created | Activity Inheritance | Purpose |
|---|---|---|---|
| `primary_knowledge_uids` | `CONTAINS_KNOWLEDGE` | **Yes** — activities roll up to LS | Core teaching content for this step |
| `supporting_knowledge_uids` | `REQUIRES_KNOWLEDGE` | **No** — activities stay on the Lesson | Supplementary reference material |

**Practical implication:** Wire activity fields (`habit_uids`, `task_uids`, etc.) to Lessons listed in `primary_knowledge_uids`. Activities on supporting Lessons exist but won't appear in the LS practice summary or completeness score.

**Example:** In the mindfulness bundle, `breath-awareness-basics` is the primary Lesson for step 1 — it carries the habit, task, and event wiring. `posture-basics` is supporting — it's useful context but has no practice activities.

### Example LS (no activity fields)

```yaml
version: 1.0
type: LearningStep

uid: ls:mindfulness-101:step-1
title: Two Minutes Today
intent: Try one two-minute breath session, note what you notice

primary_knowledge_uids:
  - l:mindfulness:breath-awareness-basics   # Activities on this Lesson are inherited

supporting_knowledge_uids:
  - l:mindfulness:posture-basics            # Enrichment only — activities NOT inherited

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

1. **Define atomic Kus** — the concepts your Lesson teaches
2. **Write the Lesson** — compose Kus into a teaching narrative
3. **Define activity entities** — create the Habit, Task, Event, Goal, Principle, Choice YAML files
4. **Wire activities to the Lesson** — add `habit_uids`, `task_uids`, etc. to the Lesson YAML
5. **Group Lessons into LS** — the LS references Lessons and inherits their activities
6. **Sequence LS into LP** — the Learning Path orders steps for the learner

Not every Lesson needs all 6 activity types. Start with what makes sense for the content. A Lesson on breath awareness might wire a Habit (daily practice) and a Task (log sessions). A Lesson on decision-making might wire Choices and Principles.

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
