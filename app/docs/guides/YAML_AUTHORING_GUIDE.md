---
title: YAML Authoring Guide
created: 2026-03-21
updated: 2026-03-29
status: current
category: guides
tags: [yaml, ingestion, authoring, substance, relationships, curriculum, activity-domains]
---

# YAML Authoring Guide

How to write content files that create SKUEL entities and their graph relationships. This guide covers entity structure, file format conventions, the `connections` system, substance tracking, and domain bundles.

---

## File Format: YAML vs Markdown

The ingestion system supports two file formats. Use the one that matches the entity:

| Format | Extension | Best For | How Content Works |
|--------|-----------|----------|-------------------|
| **YAML** | `.yaml` | Kus, LP, activities, edges | All fields in YAML. Content (if any) is a `content: \|` string block. |
| **Markdown** | `.md` | PathSteps | Metadata in YAML frontmatter (`---` delimiters), **must include `type: PathStep`**. Markdown body automatically becomes the `content` field. |

**Why this split?** PathSteps are content-heavy — long prose, headers, lists, emphasis. Writing that inside a YAML `|` block is awkward to author and impossible to preview in Obsidian. Everything else is metadata-heavy with little or no prose, so YAML is cleaner.

### Markdown PathStep Example

```markdown
---
type: PathStep
uid: ps:self-reflection:noticing-patterns
title: Noticing Your Patterns
sel_category: self_awareness
learning_level: beginner

uses_kus:
  - ku:self-reflection:self-observation
  - ku:self-reflection:emotional-patterns

connections:
  requires: []
  enables:
    - ps:self-reflection:emotional-awareness

tags:
  - self-reflection
  - patterns
---

## From Noticing Breath to Noticing Yourself

If you've practiced breath awareness, you already have the core skill...

## Practice: One Pattern, One Day

Pick one pattern you already suspect you have...
```

The frontmatter contains all the PathStep fields — `type`, `uid`, `uses_kus`, `connections`, `tags`, activity wiring fields. The only difference from a pure YAML file is that `content` is not in the frontmatter — it's the markdown body below the closing `---`.

### YAML Entity Example

```yaml
version: 1.0
type: Ku

uid: ku:self-reflection:self-observation
title: Self-Observation
namespace: self_reflection
ku_category: practice
aliases:
  - introspection
  - self-watching
description: The practice of watching your own thoughts, emotions, and behavioral patterns without immediately reacting.
tags:
  - self-reflection
  - practice
```

### Exercise YAML Example

```yaml
version: 1.0
type: Exercise

uid: ex:sel:know-yourself-check-in
title: Know Yourself Check-In
description: A structured self-awareness exercise
scope: personal
model: claude-sonnet-4-6
mastery_impact: moderate
sel_category: SELF_AWARENESS
learning_level: BEGINNER
tags: [self-awareness, reflection]

instructions: |
  You are a self-awareness coach. Review the student's responses
  and provide warm, specific feedback. Keep it to 3-5 sentences.

form_schema:
  - name: emotion_check
    type: textarea
    label: "Name one emotion you felt strongly today. What triggered it?"
    required: true
  - name: daily_habit
    type: text
    label: "What daily habit will you build to increase self-awareness?"
    required: true
```

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

13 of SKUEL's 20 entity types are file-ingestible. The remaining are created via API or internal pipelines (RevisedExercise, Resource, FormTemplate, FormSubmission, EntryReport, ActivityReport).

| Type Value | Aliases | Prefix | Example UID |
|------------|---------|--------|-------------|
| `Ku` | `KnowledgeUnit` | `ku:` | `ku:attention:buzzing` |
| `PathStep` | `ps`, `Lesson` (legacy) | `ps:` | `ps:mindfulness:breath-awareness-basics` |
| `Exercise` | — | `ex:` | `ex:sel:know-yourself-check-in` |
| `LearningPath` | `lp` | `lp:` | `lp:mindfulness-101` |
| `Task` | — | `task:` | `task:log-first-5-sessions` |
| `Goal` | — | `goal:` | `goal:mindfulness-beginner` |
| `Habit` | — | `habit:` | `habit:daily-2min-breath` |
| `Event` | — | `event:` | `event:practice-block-2min` |
| `Choice` | — | `choice:` | `choice:2-minutes-right-now` |
| `Principle` | — | `principle:` | `principle:small-steps` |
| `UserEntry` | `UserEntry` | `ue:` | `ue:my-work` |
| `LifePath` | — | `lifepath:` | `lifepath:my-direction` |
| `Expense` | `Finance` | `expense:` | `expense:books` |
| `Edge` | — | *(n/a)* | *(standalone relationship file)* |

The `type` value is case-insensitive. Aliases resolve to the canonical type during ingestion.

**UID format:** `prefix:slug` or `prefix:namespace:slug`. Colons are normalized to dots internally (`ku:attention:buzzing` becomes `ku.attention.buzzing` in Neo4j). **UID prefix validation:** Explicit UIDs must start with the correct prefix for their entity type (e.g., `ps:` for PathSteps, `ku:` for Kus, `ex:` for Exercises). A mismatched prefix is rejected during ingestion.

**What happens during ingestion:** The `type` field determines which Neo4j labels the node gets (e.g., `type: Task` creates a node with `:Entity:Task` labels) and sets the `entity_type` property on the node (e.g., `entity_type: "task"`). The `type` field itself is not stored — it is translated into labels and properties.

See `yaml_templates/_schemas/` for the complete field reference per entity type.

### Enum-Governed Fields

Many YAML fields are constrained by Python enums — using an invalid value will fail Pydantic validation during ingestion with a clear error message. These are not free-text fields; they accept only the values defined in the corresponding enum class.

**Quick reference — most common enum-governed fields:**

| YAML Field | Enum Class | Valid Values |
|------------|------------|-------------|
| `type` | `EntityType` | `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `Ku`, `PathStep`, `LearningPath`, `Exercise`, `UserEntry`, `LifePath` |
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
| Ku | `draft`, `completed`, `archived` | `draft` |
| PathStep, LearningPath | `draft`, `active`, `completed`, `archived` | `draft` |
| Task | `draft`, `scheduled`, `active`, `paused`, `blocked`, `completed`, `cancelled`, `postponed`, `failed` | `draft` |
| Goal | `draft`, `active`, `paused`, `completed`, `cancelled`, `failed`, `archived` | `draft` |
| Habit | `active`, `paused`, `completed`, `cancelled`, `archived` | `active` |
| Event | `scheduled`, `active`, `completed`, `cancelled` | `scheduled` |
| Choice | `draft`, `active`, `completed`, `archived` | `draft` |
| Principle | `active`, `paused`, `archived` | `active` |
| UserEntry | `draft`, `submitted`, `queued`, `processing`, `completed`, `failed`, `revision_requested`, `archived` | `draft` |
| LifePath | `active`, `archived` | `active` |

Using a status not in the valid set for that entity type will fail validation during ingestion.

**Two lifecycle patterns** govern which statuses appear:

```
Content Processing (UserEntry):
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

Activity domains (Task, Goal, Habit, Event, Choice, Principle), UserEntry, and LifePath are **user-owned** — they require a `user_uid`. If the YAML file omits `user_uid`, the ingestion engine sets it to the default (`SKUEL_DEFAULT_USER_UID` env var, or `user:system`).

Curriculum types (Ku, PathStep, LearningPath, Exercise) are **shared** — no `user_uid` needed; they are visible to all users.

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
    - ps:mindfulness:breath-awareness-basics

# Habit reinforces knowledge (HIGHEST substance weight)
type: Habit
uid: habit:daily-2min-breath
title: Daily 2-Minute Breath
connections:
  reinforces_knowledge:
    - ps:mindfulness:breath-awareness-basics

# Choice informed by knowledge
type: Choice
uid: choice:2-minutes-right-now
title: Do Two Minutes Right Now
connections:
  informed_by_knowledge:
    - ps:mindfulness:breath-awareness-basics

# Principle grounded in knowledge
type: Principle
uid: principle:small-steps
name: Small Steps Beat Big Bursts
connections:
  grounded_in_knowledge:
    - ps:mindfulness:breath-awareness-basics
    - ps:mindfulness:mind-wandering-happens

# Event applies knowledge
type: Event
uid: event:practice-block-2min
title: 2-Minute Practice Block
connections:
  applies_knowledge:
    - ps:mindfulness:breath-awareness-basics
```

**At runtime**, when a user completes a task, creates a habit, makes a choice, etc., domain events (`KnowledgeAppliedInTask`, `KnowledgeBuiltIntoHabit`, `KnowledgeInformedChoice`) increment substance counters on the knowledge node. The YAML connections define the *structural* links; runtime events track *usage* counts.

See: `/docs/architecture/knowledge_substance_philosophy.md`

---

## Cross-Domain Connections

Activities also connect to other activities:

### Task Connections

```yaml
connections:
  applies_knowledge: [ps:namespace:path-step-slug]       # APPLIES_KNOWLEDGE → PathStep/Ku
  fulfills_goal: [goal:goal-name]                    # FULFILLS_GOAL → Goal (single)
  reinforces_habit: [habit:habit-name]               # SUPPORTS_HABIT → Habit (single)
  depends_on: [task:other-task]                      # DEPENDS_ON → Task
```

### Goal Connections

```yaml
connections:
  requires_knowledge: [ps:namespace:path-step-slug]      # REQUIRES_KNOWLEDGE → PathStep/Ku
  aligned_with_principle: [principle:name]            # GUIDED_BY_PRINCIPLE → Principle
```

### Habit Connections

```yaml
connections:
  reinforces_knowledge: [ps:namespace:path-step-slug]    # REINFORCES_KNOWLEDGE → PathStep/Ku
  supports_goal: [goal:goal-name]                    # SUPPORTS_GOAL → Goal
  embodies_principle: [principle:name]                # EMBODIES_PRINCIPLE → Principle
  prerequisite_habits: [habit:other-habit]            # REQUIRES_PREREQUISITE_HABIT → Habit
```

### Event Connections

```yaml
connections:
  applies_knowledge: [ps:namespace:path-step-slug]       # APPLIES_KNOWLEDGE → PathStep/Ku
  contributes_to_goal: [goal:goal-name]              # CONTRIBUTES_TO_GOAL → Goal
  reinforces_habit: [habit:habit-name]               # REINFORCES_HABIT → Habit
  executes_task: [task:task-name]                    # EXECUTES_TASK → Task
```

### Choice Connections

```yaml
connections:
  informed_by_knowledge: [ps:namespace:path-step-slug]   # INFORMED_BY_KNOWLEDGE → PathStep/Ku
  guided_by_principle: [principle:name]               # INFORMED_BY_PRINCIPLE → Principle
  affects_goal: [goal:goal-name]                     # AFFECTS_GOAL → Goal
  impacts_habit: [habit:habit-name]                  # IMPACTS_HABIT → Habit
```

### Principle Connections

```yaml
connections:
  grounded_in_knowledge: [ps:namespace:path-step-slug]   # GROUNDED_IN_KNOWLEDGE → PathStep/Ku
  guides_goal: [goal:goal-name]                      # GUIDES_GOAL → Goal
  inspires_habit: [habit:habit-name]                 # INSPIRES_HABIT → Habit
```

### Curriculum Connections

```yaml
# PathStep
connections:
  requires: [ps:namespace:prerequisite]              # REQUIRES_KNOWLEDGE → PathStep
  enables: [ps:namespace:next-path-step]             # ENABLES_KNOWLEDGE → PathStep
uses_kus:
  - ku:namespace:concept                             # USES_KU → Ku

# Learning Path
connections:
  contains_steps:                                    # HAS_STEP → PathStep
    - ps:path:step-1
    - ps:path:step-2
```

### PathStep Fields

PathSteps are the teaching narrative layer. They sit inside a LearningPath, compose Kus into coherent content, and carry activity domain wiring (habits, tasks, events, goals, principles, choices) directly.

See [PathStep Activity Wiring Guide](/docs/guides/LESSON_ACTIVITY_WIRING.md).

```yaml
type: PathStep
uid: ps:mindfulness-101:breath-awareness-basics
uses_kus:
  - ku:mindfulness:breath
  - ku:mindfulness:attention
trains_ku_uids: [ku:mindfulness:breath]
learning_path_uid: lp:mindfulness-101
sequence: 1
# Activity fields (habit_uids, task_uids, etc.) belong on this PathStep YAML/frontmatter directly
habit_uids: [habit:daily-2min-breath]
task_uids: [task:log-first-5-sessions]
```

---

## Edge Files

Standalone edge files in `{vault}/edges/` create relationships between entities. There are two patterns: **evidence edges** (observed connections between Kus) and **curriculum structure edges** (wiring up the three-entity curriculum stack and cross-domain connections).

### Evidence Edges (Ku-to-Ku Observations)

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

### Curriculum Structure Edges (Batch Relationship Files)

For curriculum bundles, edge files declare multiple relationships in a single file. This keeps the individual entity files clean and makes the relationship structure visible in one place.

```yaml
# edges/edge_mindfulness-101-curriculum.yaml
version: 1.0

edges:
  # PathSteps → Kus (USES_KU)
  - from: ps:mindfulness:breath-awareness-basics
    to: ku:mindfulness:breath
    type: USES_KU
  - from: ps:mindfulness:breath-awareness-basics
    to: ku:mindfulness:attention
    type: USES_KU

  # Learning Path → PathSteps (CONTAINS_STEP)
  - from: lp:mindfulness-101
    to: ps:mindfulness:breath-awareness-basics
    type: CONTAINS_STEP
    properties:
      order: 1

  # Ku lateral relationships
  - from: ku:mindfulness:breath
    to: ku:mindfulness:attention
    type: RELATED_TO
```

### Cross-Domain Edge Files

When two domain bundles connect (e.g., Mindfulness 101 → Self-Reflection 101), declare the connections in a dedicated cross-domain edge file:

```yaml
# edges/edge_mindfulness-to-self-reflection.yaml
version: 1.0

edges:
  - from: lp:mindfulness-101
    to: lp:self-reflection-101
    type: PREREQUISITE_FOR

  - from: ku:mindfulness:attention
    to: ku:self-reflection:self-observation
    type: PREREQUISITE_FOR

  - from: ps:mindfulness:mind-wandering-happens
    to: ps:self-reflection:noticing-patterns
    type: ENABLES
```

**Naming convention:** `edge_{from-domain}-to-{to-domain}.yaml` for cross-domain, `edge_{domain}-curriculum.yaml` for internal structure.

**Note:** Relationships can also be declared inline via `connections` blocks and `uses_kus` fields on individual entity files. Edge files are an alternative for bulk declarations and cross-domain wiring. Both approaches create the same Neo4j edges — use whichever is clearer for your content.

---

## Domain Bundles

A bundle is a complete, curated collection of related content. The default ingestion vault is `/home/mike/0bsidian/0vault/` (configurable via `INGESTION_PATH`).

### Bundle Structure

A domain bundle in the vault uses the format convention — `.md` for PathSteps (content-heavy), `.yaml` for everything else:

```
/home/mike/0bsidian/0vault/
  # Kus (YAML — metadata only, no prose)
  ku_breath.yaml
  ku_attention.yaml
  # PathSteps (Markdown — frontmatter + prose body)
  ps_breath-awareness-basics.md
  ps_posture-basics.md
  ps_mind-wandering-happens.md
  # Activity entities (YAML — with connections blocks)
  habit_daily-2min-breath.yaml
  task_log-first-5-sessions.yaml
  event_practice-block-2min.yaml
  goal_mindfulness-beginner.yaml
  choice_2-minutes-right-now.yaml
  principle_small-steps.yaml
  # Learning Path (YAML)
  lp_mindfulness-101.yaml
  # Edges (YAML — relationship declarations)
  edges/edge_mindfulness-101-curriculum.yaml
```

### Manifest

```yaml
name: Mindfulness 101
description: Complete beginner mindfulness bundle
version: 1.0

import_order:
  1_kus: [ku:mindfulness:breath, ku:mindfulness:attention]
  2_path_steps: [ps:mindfulness:breath-awareness-basics, ps:mindfulness:posture-basics]
  3_supporting: [habit:daily-2min-breath, task:log-first-5-sessions, ...]
  4_paths: [lp:mindfulness-101]
```

**Import order matters:** Kus first (referenced by PathSteps), then PathSteps (referenced by Activities), then Activities, then LearningPaths.

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
- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) — all 20 entity types
- [YAML Templates README](/yaml_templates/README.md) — directory structure and UID formats
- [Schema Templates](/yaml_templates/_schemas/) — complete field reference per entity type

### Ingestion Pipeline Source Files

| File | Role |
|------|------|
| `core/services/ingestion/detector.py` | `TYPE_MAPPING`: YAML `type` string → `EntityType` enum |
| `core/services/ingestion/config.py` | `ENTITY_CONFIGS`: `EntityType` → Neo4j label, UID prefix, required fields |
| `core/services/ingestion/preparer.py` | Data preparation: strip YAML metadata, inject `entity_type`, normalize UIDs |
| `core/services/ingestion/validator.py` | Required field validation, UID format validation, data validation |
| `core/ingestion/bulk_ingestion.py` | Cypher generation and Neo4j writes |
| `core/models/relationship_registry.py` | `yaml_field_path` → relationship type mappings |
