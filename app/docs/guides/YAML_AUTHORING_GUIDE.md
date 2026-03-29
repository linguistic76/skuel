---
title: YAML Authoring Guide
created: 2026-03-21
updated: 2026-03-28
status: current
category: guides
tags: [yaml, ingestion, authoring, substance, relationships, curriculum, activity-domains]
---

# YAML Authoring Guide

How to write YAML files that create SKUEL entities and their graph relationships. This guide covers entity structure, the `connections` system, substance tracking, and domain bundles.

---

## Entity Structure

Every YAML file starts with required fields:

```yaml
version: 1.0
type: Task              # Entity type (see table below)
uid: task:my-task-name  # Unique identifier (prefix:slug format)
title: My Task Title    # Display title
```

### Ingestible Entity Types

12 of SKUEL's 21 entity types are file-ingestible. The remaining 9 (Exercise, RevisedExercise, Resource, FormTemplate, FormSubmission, JeInput, JeOutput, ExerciseReport, ActivityReport) are created via API or internal pipelines.

| Type Value | Aliases | Prefix | Example UID |
|------------|---------|--------|-------------|
| `Ku` | — | `ku:` | `ku:attention:buzzing` |
| `Lesson` | `Article`, `KnowledgeUnit` | `l:` | `l:mindfulness:breath-awareness-basics` |
| `LearningStep` | `ls` | `ls:` | `ls:mindfulness-101:step-1` |
| `LearningPath` | `lp` | `lp:` | `lp:mindfulness-101` |
| `Task` | — | `task:` | `task:log-first-5-sessions` |
| `Goal` | — | `goal:` | `goal:mindfulness-beginner` |
| `Habit` | — | `habit:` | `habit:daily-2min-breath` |
| `Event` | — | `event:` | `event:practice-block-2min` |
| `Choice` | — | `choice:` | `choice:2-minutes-right-now` |
| `Principle` | — | `principle:` | `principle:small-steps` |
| `ExerciseSubmission` | `Submission` | `es:` | `es:my-work` |
| `LifePath` | — | `lifepath:` | `lifepath:my-direction` |
| `Expense` | `Finance` | `expense:` | `expense:books` |
| `Edge` | — | *(n/a)* | *(standalone relationship file)* |

The `type` value is case-insensitive. Aliases resolve to the canonical type during ingestion.

**UID format:** `prefix:slug` or `prefix:namespace:slug`. Colons are normalized to dots internally (`ku:attention:buzzing` becomes `ku.attention.buzzing` in Neo4j).

**What happens during ingestion:** The `type` field determines which Neo4j labels the node gets (e.g., `type: Task` creates a node with `:Entity:Task` labels) and sets the `entity_type` property on the node (e.g., `entity_type: "task"`). The `type` field itself is not stored — it is translated into labels and properties.

See `yaml_templates/_schemas/` for the complete field reference per entity type.

### Enum-Governed Fields

Many YAML fields are constrained by Python enums — using an invalid value will fail Pydantic validation during ingestion with a clear error message. These are not free-text fields; they accept only the values defined in the corresponding enum class.

**Quick reference — most common enum-governed fields:**

| YAML Field | Enum Class | Valid Values |
|------------|------------|-------------|
| `type` | `EntityType` | `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `Ku`, `Lesson`, `LearningStep`, `LearningPath`, `ExerciseSubmission`, `LifePath` |
| `status` | `EntityStatus` | Per-type subset (see [Entity Status](#entity-status) below) |
| `priority` | `Priority` | `low`, `medium`, `high`, `critical` |
| `polarity` | `HabitPolarity` | `build`, `break`, `neutral` |
| `category` (habit) | `HabitCategory` | `health`, `fitness`, `mindfulness`, `learning`, `productivity`, `creative`, `social`, `financial`, `other` |
| `difficulty` | `HabitDifficulty` | `trivial`, `easy`, `moderate`, `challenging`, `hard` |
| `goal_type` | `GoalType` | `outcome`, `process`, `learning`, `project`, `milestone`, `mastery` |
| `timeframe` | `GoalTimeframe` | `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, `multi_year` |
| `choice_type` | `ChoiceType` | `binary`, `multiple`, `ranking`, `allocation`, `strategic`, `operational` |
| `category` (principle) | `PrincipleCategory` | `spiritual`, `ethical`, `relational`, `personal`, `professional`, `intellectual`, `health`, `creative` |
| `source` (principle) | `PrincipleSource` | `philosophical`, `religious`, `cultural`, `personal`, `scientific`, `mentor`, `literature` |
| `strength` | `PrincipleStrength` | `core`, `strong`, `moderate`, `developing`, `exploring` |
| `recurrence_pattern` | `RecurrencePattern` | `none`, `daily`, `weekdays`, `weekends`, `weekly`, `biweekly`, `monthly`, `quarterly`, `yearly`, `custom` |
| `ku_category` | `KuCategory` | `state`, `concept`, `principle`, `intake`, `substance`, `practice`, `value` |
| `sel_category` | `SELCategory` | `self_awareness`, `self_management`, `social_awareness`, `relationship_skills`, `responsible_decision_making` |

All enum classes live in `core/models/enums/`. For the complete enum catalog and the field-to-enum mapping, see [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md).

### Entity Status

The `status` field is governed by `EntityStatus` (14 values). Not every status is valid for every entity type — each type has a constrained subset and a default. If you omit `status` from your YAML, the default for that entity type is used.

**Status categories:**

| Category | Statuses | Meaning |
|----------|----------|---------|
| Pending | `draft`, `submitted`, `queued`, `scheduled` | Not yet active |
| Active | `processing`, `active` | Work in progress |
| Paused | `paused`, `blocked`, `postponed` | Temporarily stopped |
| Terminal | `completed`, `failed`, `cancelled`, `archived` | No further progression |
| Special | `revision_requested` | Completed but sent back |

**Valid statuses and defaults per ingestible entity type:**

| Type | Valid Statuses | Default |
|------|---------------|---------|
| Ku, Lesson | `draft`, `completed`, `archived` | `draft` |
| LearningStep, LearningPath | `draft`, `active`, `completed`, `archived` | `draft` |
| Task | `draft`, `scheduled`, `active`, `paused`, `blocked`, `completed`, `cancelled`, `postponed`, `failed` | `draft` |
| Goal | `draft`, `active`, `paused`, `completed`, `cancelled`, `failed`, `archived` | `draft` |
| Habit | `active`, `paused`, `completed`, `cancelled`, `archived` | `active` |
| Event | `scheduled`, `active`, `completed`, `cancelled` | `scheduled` |
| Choice | `draft`, `active`, `completed`, `archived` | `draft` |
| Principle | `active`, `paused`, `archived` | `active` |
| ExerciseSubmission | `draft`, `submitted`, `queued`, `processing`, `completed`, `failed`, `revision_requested`, `archived` | `draft` |
| LifePath | `active`, `archived` | `active` |

Using a status not in the valid set for that entity type will fail validation during ingestion.

**Two lifecycle patterns** govern which statuses appear:

```
Content Processing (ExerciseSubmission, JeInput):
  draft → submitted → queued → processing → completed / failed
                                                 |
                                          revision_requested → resubmit

Activity (Task, Goal, Habit, Event, Choice, Principle):
  draft → scheduled → active → paused → completed
              |           |       |
              |           +→ blocked → active
              |           |
              +→ postponed    +→ cancelled / failed
```

See [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md) for the full transition map and status check methods.

### Ownership

Activity domains (Task, Goal, Habit, Event, Choice, Principle), ExerciseSubmission, and LifePath are **user-owned** — they require a `user_uid`. If the YAML file omits `user_uid`, the ingestion engine sets it to the default (`SKUEL_DEFAULT_USER_UID` env var, or `user:system`).

Curriculum types (Lesson, Ku, LearningStep, LearningPath) are **shared** — no `user_uid` needed; they are visible to all users.

Expense is **admin-only** and also requires `user_uid`.

---

## The Connections System

The `connections` block declares graph relationships. Each field maps to a `yaml_field_path` in the relationship registry (`core/models/relationship_registry.py`). The ingestion engine creates Neo4j edges from these declarations.

```yaml
connections:
  field_name:
    - target_uid_1
    - target_uid_2
```

**How it works:**
1. YAML author writes `connections.{field}: [uid1, uid2]`
2. `preparer.py` flattens the `connections` dict to dotted notation (`connections.field → [uids]`)
3. `generate_ingestion_relationship_config()` reads the `yaml_field_path` from the registry
4. `bulk_ingestion.py` generates `MERGE (n)-[:REL_TYPE]->(target)` Cypher
5. Edge created in Neo4j

---

## Knowledge Connections (Substance Tracking)

The substance tracking pipeline measures how knowledge is LIVED, not just learned. Each activity domain connects to knowledge via a specific relationship type:

| Domain | Connection Field | Relationship | Weight | Max |
|--------|-----------------|-------------|--------|-----|
| **Habit** | `reinforces_knowledge` | REINFORCES_KNOWLEDGE | 0.10 | 0.30 |
| **Choice** | `informed_by_knowledge` | INFORMED_BY_KNOWLEDGE | 0.07 | 0.15 |
| **Principle** | `grounded_in_knowledge` | GROUNDED_IN_KNOWLEDGE | 0.07 | 0.15 |
| **Event** | `applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 | 0.25 |
| **Task** | `applies_knowledge` | APPLIES_KNOWLEDGE | 0.05 | 0.25 |
| **Journal** | *(deferred)* | — | 0.07 | 0.20 |

**Total possible substance score: 1.0** (6 channels contribute up to 1.30 raw, capped at 1.0).

### Examples

```yaml
# Task applies knowledge
type: Task
uid: task:log-first-5-sessions
title: Log First 5 Sessions
connections:
  applies_knowledge:
    - l:mindfulness:breath-awareness-basics

# Habit reinforces knowledge (HIGHEST substance weight)
type: Habit
uid: habit:daily-2min-breath
title: Daily 2-Minute Breath
connections:
  reinforces_knowledge:
    - l:mindfulness:breath-awareness-basics

# Choice informed by knowledge
type: Choice
uid: choice:2-minutes-right-now
title: Do Two Minutes Right Now
connections:
  informed_by_knowledge:
    - l:mindfulness:breath-awareness-basics

# Principle grounded in knowledge
type: Principle
uid: principle:small-steps
name: Small Steps Beat Big Bursts
connections:
  grounded_in_knowledge:
    - l:mindfulness:breath-awareness-basics
    - l:mindfulness:mind-wandering-happens

# Event applies knowledge
type: Event
uid: event:practice-block-2min
title: 2-Minute Practice Block
connections:
  applies_knowledge:
    - l:mindfulness:breath-awareness-basics
```

**At runtime**, when a user completes a task, creates a habit, makes a choice, etc., domain events (`KnowledgeAppliedInTask`, `KnowledgeBuiltIntoHabit`, `KnowledgeInformedChoice`) increment substance counters on the knowledge node. The YAML connections define the *structural* links; runtime events track *usage* counts.

See: `/docs/architecture/knowledge_substance_philosophy.md`

---

## Cross-Domain Connections

Activities also connect to other activities:

### Task Connections

```yaml
connections:
  applies_knowledge: [l:namespace:lesson-slug]       # APPLIES_KNOWLEDGE → Lesson/Ku
  fulfills_goal: [goal:goal-name]                    # FULFILLS_GOAL → Goal (single)
  reinforces_habit: [habit:habit-name]               # SUPPORTS_HABIT → Habit (single)
  depends_on: [task:other-task]                      # DEPENDS_ON → Task
```

### Goal Connections

```yaml
connections:
  requires_knowledge: [l:namespace:lesson-slug]      # REQUIRES_KNOWLEDGE → Lesson/Ku
  aligned_with_principle: [principle:name]            # GUIDED_BY_PRINCIPLE → Principle
```

### Habit Connections

```yaml
connections:
  reinforces_knowledge: [l:namespace:lesson-slug]    # REINFORCES_KNOWLEDGE → Lesson/Ku
  supports_goal: [goal:goal-name]                    # SUPPORTS_GOAL → Goal
  embodies_principle: [principle:name]                # EMBODIES_PRINCIPLE → Principle
  prerequisite_habits: [habit:other-habit]            # REQUIRES_PREREQUISITE_HABIT → Habit
```

### Event Connections

```yaml
connections:
  applies_knowledge: [l:namespace:lesson-slug]       # APPLIES_KNOWLEDGE → Lesson/Ku
  contributes_to_goal: [goal:goal-name]              # CONTRIBUTES_TO_GOAL → Goal
  reinforces_habit: [habit:habit-name]               # REINFORCES_HABIT → Habit
  executes_task: [task:task-name]                    # EXECUTES_TASK → Task
```

### Choice Connections

```yaml
connections:
  informed_by_knowledge: [l:namespace:lesson-slug]   # INFORMED_BY_KNOWLEDGE → Lesson/Ku
  guided_by_principle: [principle:name]               # INFORMED_BY_PRINCIPLE → Principle
  affects_goal: [goal:goal-name]                     # AFFECTS_GOAL → Goal
  impacts_habit: [habit:habit-name]                  # IMPACTS_HABIT → Habit
```

### Principle Connections

```yaml
connections:
  grounded_in_knowledge: [l:namespace:lesson-slug]   # GROUNDED_IN_KNOWLEDGE → Lesson/Ku
  guides_goal: [goal:goal-name]                      # GUIDES_GOAL → Goal
  inspires_habit: [habit:habit-name]                 # INSPIRES_HABIT → Habit
```

### Curriculum Connections

```yaml
# Lesson
connections:
  requires: [l:namespace:prerequisite]               # REQUIRES_KNOWLEDGE → Lesson
  enables: [l:namespace:next-lesson]                 # ENABLES_KNOWLEDGE → Lesson
uses_kus:
  - ku:namespace:concept                             # USES_KU → Ku

# Learning Path
connections:
  contains_steps:                                    # HAS_STEP → LearningStep
    - ls:path:step-1
    - ls:path:step-2
```

### Learning Step Fields

Learning Steps group Lessons into collections within a learning path. They have two types of knowledge references:

- **`knowledge_uids`** — Lessons in this step. Creates `CONTAINS_KNOWLEDGE` edges. Activities on these Lessons are inherited by the LS via graph traversal.

Activity domain wiring (habits, tasks, events, goals, principles, choices) lives on **Lessons**, not on Learning Steps. See [Lesson Activity Wiring Guide](/docs/guides/LESSON_ACTIVITY_WIRING.md).

```yaml
type: LearningStep
uid: ls:mindfulness-101:step-1
knowledge_uids:
  - l:mindfulness:breath-awareness-basics
  - l:mindfulness:posture-basics
trains_ku_uids: [ku:mindfulness:breath]
learning_path_uid: lp:mindfulness-101
sequence: 1
# Activity fields (habit_uids, task_uids, etc.) belong on the Lesson YAML, not here
```

---

## Edge Files (Evidence Relationships)

Standalone relationship files create edges between existing entities with evidence metadata:

```yaml
type: Edge
from: ku:nutrition:caffeine
to: ku:attention:buzzing
relationship: EXACERBATED_BY
evidence: "After coffee I feel more restless."
confidence: 0.8
polarity: -1
temporality: hours
source: self_observation
```

**Fields:**
- `confidence`: 0.0–1.0
- `polarity`: -1 (negative), 0 (neutral), 1 (positive)
- `temporality`: minutes, hours, days, chronic
- `source`: self_observation, research, teacher, clinical

---

## Domain Bundles

A bundle is a complete, curated collection of related content. See `yaml_templates/mindfulness_101/` for a working example.

### Bundle Structure

```
mindfulness_101/
  manifest.yaml                          # Import order + entity inventory
  ku_breath.yaml                         # Atomic knowledge units (first)
  ku_attention.yaml
  lesson_breath-awareness-basics.yaml    # Lessons that compose Kus
  lesson_posture-basics.yaml
  habit_daily-2min-breath.yaml           # Activity domains (with connections)
  task_log-first-5-sessions.yaml
  event_practice-block-2min.yaml
  goal_mindfulness-beginner.yaml
  choice_2-minutes-right-now.yaml
  principle_small-steps.yaml
  ls_mindfulness-101_step-1.yaml         # Learning Steps (reference all above)
  ls_mindfulness-101_step-2.yaml
  lp_mindfulness-101.yaml               # Learning Path (sequences Steps)
```

### Manifest

```yaml
name: Mindfulness 101
description: Complete beginner mindfulness bundle
version: 1.0

import_order:
  1_kus: [ku:mindfulness:breath, ku:mindfulness:attention]
  2_lessons: [l:mindfulness:breath-awareness-basics, l:mindfulness:posture-basics]
  3_supporting: [habit:daily-2min-breath, task:log-first-5-sessions, ...]
  4_steps: [ls:mindfulness-101:step-1, ls:mindfulness-101:step-2]
  5_paths: [lp:mindfulness-101]
```

**Import order matters:** Kus first (referenced by Lessons), then Lessons (referenced by Activities), then Activities (referenced by Learning Steps), then Steps, then Paths.

### Ingestion

```python
# Single file
result = await service.ingest_file(Path("yaml_templates/mindfulness_101/ku_breath.yaml"))

# Full bundle
result = await service.ingest_directory(Path("yaml_templates/mindfulness_101"))

# Dry run (preview without writing)
result = await service.ingest_directory(path, dry_run=True)
```

**API:** `POST /api/ingest/file`, `POST /api/ingest/directory`

---

## Validation

Validation happens via **Pydantic Request models** in the Python code, not via YAML schemas. The `_schemas/` templates document what fields Pydantic expects.

---

## The Complete Picture

```
YAML Author writes type + connections.*
        ↓
    detector.py: type → EntityType enum
        ↓
    preparer.py: strip YAML metadata, inject entity_type property, normalize UIDs
        ↓
    config.py: EntityType → Neo4j label + UID prefix
        ↓
    BulkIngestionEngine: MERGE (n:Entity:Task {uid: ...}) + SET properties
        ↓
    Neo4j Node (with labels + entity_type property) + Edges (from connections.*)
        ↓
    User interacts (completes task, builds habit, makes choice...)
        ↓
    Domain Events fire (KnowledgeAppliedInTask, KnowledgeBuiltIntoHabit, ...)
        ↓
    Substance counters increment on knowledge node
        ↓
    UserContext MEGA-QUERY collects all 6 channels
        ↓
    calculate_user_substance() applies weights (Habits 0.10 > Choices 0.07 > Tasks 0.05)
        ↓
    Substance score (0.0–1.0): "How much is this knowledge LIVED?"
```

---

## Related Documentation

- [Knowledge Substance Philosophy](/docs/architecture/knowledge_substance_philosophy.md) — scoring model, decay, life path alignment
- [Unified Ingestion Guide](/docs/patterns/UNIFIED_INGESTION_GUIDE.md) — full ingestion API
- [Relationship Registry](/core/models/relationship_registry.py) — source of truth for `yaml_field_path` mappings
- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) — all 21 entity types
- [YAML Templates README](/yaml_templates/README.md) — directory structure and UID formats
- [Schema Templates](/yaml_templates/_schemas/) — complete field reference per entity type

### Ingestion Pipeline Source Files

| File | Role |
|------|------|
| `core/services/ingestion/detector.py` | `TYPE_MAPPING`: YAML `type` string → `EntityType` enum |
| `core/services/ingestion/config.py` | `ENTITY_CONFIGS`: `EntityType` → Neo4j label, UID prefix, required fields |
| `core/services/ingestion/preparer.py` | Data preparation: strip YAML metadata, inject `entity_type`, normalize UIDs |
| `core/services/ingestion/validator.py` | Required field and data validation |
| `core/ingestion/bulk_ingestion.py` | Cypher generation and Neo4j writes |
| `core/models/relationship_registry.py` | `yaml_field_path` → relationship type mappings |
