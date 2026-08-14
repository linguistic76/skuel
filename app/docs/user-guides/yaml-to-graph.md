# YAML to Graph — A Creator's Guide to SKUEL Content

*Last updated: 2026-07-06*

## Overview

Every YAML file you write becomes a node in a knowledge graph. Every relationship you declare becomes a traversable edge. This guide shows you how content flows from authoring to a living, queryable, semantically-connected graph.

The pipeline:

```
YAML file ─→ Parse ─→ Detect type ─→ Validate ─→ Prepare ─→ Ingest ─→ Neo4j
                                        │                      │
                                   Pydantic model        MERGE Cypher
                                   checks fields         creates nodes + edges
```

We'll use the **Mindfulness 101** bundle (21 entities across 10 types) as a running example throughout. You can find it at `yaml_templates/domains/mindfulness_101/`.

Every section follows a three-tier alignment: **YAML fields → Python model → Neo4j storage**. This is the contract. If a YAML field exists, there's a Python field that validates it and a Cypher property or edge that stores it.

---

## The Atom — Ku

A Ku is the smallest nameable concept in SKUEL. It's an atomic reference node — no content body, no paragraphs, no teaching narrative. If you can define it in one sentence, it's a Ku. If it needs explanation, it belongs in a PathStep.

**Granularity decision:** "One sentence = Ku. Paragraphs = PathStep."

### NOUS — Topic Membership

The `nous` field places a Ku in one or more of SKUEL's official topic sections. It's a list — a Ku can belong to several sections, or to none (an empty `nous` is valid; content may exist before it's assigned a section).

The eleven sections are: `stories`, `environment`, `intelligence`, `investment`, `words`, `relationships`, `social`, `body`, `exercises`, `self-management`, `self-awareness`.

`nous` powers topic-scoped search (e.g. `SearchRequest(nous="body")`). The vocabulary is *derived from the graph*, not enum-validated at ingestion — so spelling matters: use the exact section slugs above.

> **The UID's middle segment is not a field.** A Ku UID like `ku.mindfulness.breath` carries a middle grouping token (`mindfulness`), but it is opaque — nothing parses or validates it, and no field stores it (UIDs are opaque identity, ADR-013). Choose it for human readability; express real topic membership with `nous:`.

### Aliases

The `aliases` field provides alternative names that feed both text search and embedding generation. If users might search for "breathing" instead of "breath", add the alias.

### Three-Tier Alignment

**YAML** (`ku_breath.yaml`):

```yaml
version: 1.0
type: Ku

uid: ku.mindfulness.breath
title: Breath
aliases:
  - breathing
  - breath awareness
  - mindful breathing
nous:
  - body
description: >-
  The natural rhythm of inhalation and exhalation, used as the
  primary anchor for attention in mindfulness practice.
tags:
  - mindfulness
  - practice
  - foundational
```

**Python** — `Ku` dataclass (`core/models/ku/ku.py`) extends `Entity` directly (not Curriculum). Three Ku-specific fields: `aliases` (tuple), `nous` (tuple — topic sections), `sel_category` (optional SEL competency, SEL content only).

**Neo4j** — The ingestion engine generates:

```cypher
MERGE (n:Ku {uid: "ku.mindfulness.breath"})
  ON CREATE SET
    n.title = "Breath",
    n.aliases = ["breathing", "breath awareness", "mindful breathing"],
    n.nous = ["body"],
    n.description = "The natural rhythm of ...",
    n.tags = ["mindfulness", "practice", "foundational"],
    n.entity_type = "KU",
    n.created_at = datetime()
  ON MATCH SET
    n.updated_at = datetime()
```

Note the UID normalization: colons in YAML (`ku.mindfulness.breath`) become dots in Neo4j (`ku.mindfulness.breath`). This happens automatically in the preparer.

---

## The Composition — PathStep

A PathStep is THE curriculum content entity in SKUEL. Where a Ku names a single concept, a PathStep weaves multiple Kus into coherent learning content with full markdown. PathSteps are the "textbook pages" of SKUEL — and they also connect that content to practice (habits, tasks, choices, events, principles). See [PATHSTEP_CONTENT_ARCHITECTURE.md](/docs/architecture/PATHSTEP_CONTENT_ARCHITECTURE.md) for the full content model.

### uses_kus — Composing Atoms

The `uses_kus` field declares which Kus a PathStep composes. Each entry becomes a `(PathStep)-[:USES_KU]->(Ku)` edge in the graph. This is how SKUEL knows which atomic concepts a piece of teaching content covers.

### connections — Structural Relationships

The `connections` block declares how PathSteps relate to each other:

| Key | Relationship Created | Meaning |
|-----|---------------------|---------|
| `requires` | `REQUIRES_KNOWLEDGE` | Must read this first |
| `enables` | `ENABLES_KNOWLEDGE` | Unlocks after reading |

### YAML `type:` Alias

PathStep YAML files accept `type: PathStep` (canonical). The legacy `type: lesson` alias is still parsed for backward compatibility with older vault content — it resolves to `EntityType.PATH_STEP`. New content should use `PathStep`.

### Three-Tier Alignment

**YAML** (`ps_breath-awareness-basics.yaml`):

```yaml
version: 1.0
type: PathStep

uid: ps.mindfulness.breath-awareness-basics
title: Breath Awareness — Basics
content: |
  ## Introduction to Breath Awareness

  Breath awareness is the foundational practice of mindfulness meditation.
  It involves gently directing your attention to the natural rhythm of
  your breathing.
  ...

domain: personal
complexity: basic
quality_score: 0.85

uses_kus:
  - ku.mindfulness.breath
  - ku.mindfulness.attention

connections:
  requires: []
  enables:
    - ps.mindfulness.posture-basics
    - ps.mindfulness.mind-wandering-happens

tags:
  - breath
  - meditation
  - beginner
  - foundational
```

**Python** — `PathStep` extends `Curriculum`, which extends `Entity`. The `Curriculum` base adds ~21 fields including `content`, `complexity`, `domain`, and `quality_score`. PathStep adds activity-wiring fields (habit_uids, task_uids, choice_uids, event_template_uids, principle_uids) on top.

**How flattening works:** The preparer extracts the nested `connections` dict and flattens it to dotted keys:

```python
# Input:  {"connections": {"requires": [], "enables": ["ps.mindfulness.posture-basics", ...]}}
# Output: {"connections.enables": ["ps.mindfulness.posture-basics", ...]}
```

The BulkIngestionEngine then generates CALL subquery patterns for each dotted key:

```cypher
MERGE (n:Entity:PathStep {uid: "ps.mindfulness.breath-awareness-basics"})
  ON CREATE SET n = props, n.created_at = datetime()
  ON MATCH SET n += props, n.updated_at = datetime()
WITH n, item

// uses_kus → USES_KU edges
CALL {
  WITH n, item
  WITH n, coalesce(item.uses_kus, []) AS _target_uids
  UNWIND _target_uids AS _target_uid
  MATCH (target:Entity {uid: _target_uid})
  MERGE (n)-[:USES_KU]->(target)
}

// connections.enables → ENABLES_KNOWLEDGE edges
CALL {
  WITH n, item
  WITH n, coalesce(item.`connections.enables`, []) AS _target_uids
  UNWIND _target_uids AS _target_uid
  MATCH (target:Entity {uid: _target_uid})
  MERGE (n)-[:ENABLES_KNOWLEDGE]->(target)
}
```

The backtick escaping (`` item.`connections.enables` ``) handles the dotted key in Cypher. Connection data is filtered from node properties in Python before reaching Neo4j — the dotted keys drive edge creation, they don't pollute the node.

**Why MATCH (not MERGE) for targets:** Relationship targets use `MATCH` to only link nodes that already exist. The old `FOREACH`/`MERGE` pattern created stub nodes with incomplete labels (e.g., `:Entity` without `:PathStep`), causing duplicate nodes when the real entity was later ingested with its full multi-label set. `MATCH` silently skips missing targets — they will be linked on re-ingestion after both nodes exist.

---

## The Learning Structure — Steps and Paths

### PathStep — The Cross-Domain Connector

A PathStep is the richest entity type in SKUEL. It carries curriculum content (via the `content` field and `uses_kus`) and also wires that content into practice — Habits, Tasks, Choices, Events, and Principles (how to live it).

Every UID-list field on a PathStep becomes a set of edges in the graph:

| YAML Field | Relationship | Direction | Connects To |
|---|---|---|---|
| `uses_kus` | `USES_KU` | outgoing | Ku |
| `trains_ku_uids` | `TRAINS_KU` | outgoing | Ku |
| `prerequisite_step_uids` | `REQUIRES_STEP` | outgoing | PathStep |
| `prerequisite_knowledge_uids` | `REQUIRES_KNOWLEDGE` | outgoing | Ku |
| `principle_uids` | `GUIDED_BY_PRINCIPLE` | outgoing | Principle |
| `habit_uids` | `BUILDS_HABIT` | outgoing | Habit |
| `task_uids` | `ASSIGNS_TASK` | outgoing | Task |
| `choice_uids` | `INFORMS_CHOICE` | outgoing | Choice |
| `event_template_uids` | `SCHEDULES_EVENT` | outgoing | Event |

**YAML** (`ps_mindfulness-101_step-1.yaml`):

```yaml
version: 1.0
type: PathStep

uid: ps.mindfulness-101.step-1
title: Two Minutes Today
intent: Try one two-minute breath session, note what you notice

uses_kus:
  - ku.mindfulness.breath
  - ku.mindfulness.attention

trains_ku_uids:
  - ku.mindfulness.breath

learning_path_uid: lp.mindfulness-101
sequence: 1

prerequisite_step_uids: []

principle_uids:
  - principle.small-steps

choice_uids:
  - choice.2-minutes-right-now
  - choice.2-minutes-before-bed

habit_uids:
  - habit.daily-2min-breath

task_uids:
  - task.log-first-5-sessions

event_template_uids:
  - event.practice-block-2min

mastery_threshold: 0.7
estimated_hours: 0.5
difficulty: easy
```

This single YAML file produces one node and up to 10 edges. That's the power of the PathStep — it's the hub where knowledge, practice, and intention converge.

### LearningPath — The Sequence

A LearningPath sequences PathSteps via `(LearningPath)-[:HAS_STEP]->(PathStep)` edges. The `connections.contains_steps` list in YAML defines the order.

**YAML** (`lp_mindfulness-101.yaml`):

```yaml
version: 1.0
type: LearningPath

uid: lp.mindfulness-101
name: Mindfulness 101 — Light & Conversational
goal: >-
  Build a gentle daily starter practice with breath
  awareness and meta-cognition

path_type: structured
difficulty: beginner

connections:
  contains_steps:
    - ps.mindfulness-101.step-1
    - ps.mindfulness-101.step-2

outcomes:
  - Establish a daily 2-minute breath awareness practice
  - Develop the skill of noticing when attention wanders
  - Build meta-awareness through gentle labeling

estimated_hours: 1.0
```

### Prerequisite Chains

When `ps.mindfulness-101.step-2` declares `prerequisite_step_uids: [ps.mindfulness-101.step-1]`, the graph gains a `REQUIRES_STEP` edge. This enables "ready to learn" queries — the system can traverse prerequisite chains to determine which steps a user is prepared for based on their mastery state.

---

## Cross-Domain Linking

SKUEL's graph connects curriculum to life. Activity Domains — Task, Goal, Habit, Event, Choice, Principle — link to curriculum through UID references, and the ingestion engine wires them into edges.

### How a Goal Connects Everything

**YAML** (`goal_mindfulness-beginner.yaml`):

```yaml
uid: goal.mindfulness-beginner
title: Build a gentle daily starter practice

connections:
  requires_knowledge:
    - ps.mindfulness.breath-awareness-basics
    - ps.mindfulness.posture-basics
    - ps.mindfulness.mind-wandering-happens
  supporting_habits:
    - habit.daily-2min-breath
    - habit.label-wander-daily
  aligned_with_principle:
    - principle.small-steps
    - principle.attention-over-intensity
```

Each `connections.*` field becomes edges: `REQUIRES_KNOWLEDGE`, `SUPPORTS_GOAL` (incoming), `GUIDED_BY_PRINCIPLE`.

### The Mindfulness 101 Graph Fragment

```
                    ┌─────────────────────┐
                    │  goal.mindfulness-   │
                    │      beginner        │
                    └──────┬──┬──┬────────┘
           REQUIRES_       │  │  │    GUIDED_BY_
           KNOWLEDGE       │  │  │    PRINCIPLE
          ┌────────────────┘  │  └──────────────┐
          ▼                   │                  ▼
  ┌───────────────┐    SUPPORTS_    ┌─────────────────────┐
  │  l:breath-    │      GOAL       │ principle.small-steps│
  │  awareness    │           │     └─────────────────────┘
  │  -basics      │           ▼
  └───┬───────────┘   ┌──────────────────┐
      │ USES_KU       │ habit.daily-2min │
      ▼               │   -breath        │
  ┌────────────┐      └────────┬─────────┘
  │ ku.breath  │               │ REINFORCES_
  └────────────┘               │ KNOWLEDGE
                               ▼
                    ┌───────────────────┐
                    │  l:breath-        │
                    │  awareness-basics │
                    └───────────────────┘
```

This is how SKUEL answers "What should I work on today?" — by traversing from the user's goals through supporting habits, required knowledge, and guiding principles to find the most impactful next action.

### Habits Link Back to Knowledge

**YAML** (`habit_daily-2min-breath.yaml`):

```yaml
uid: habit.daily-2min-breath
name: Daily Two-Minute Breath

connections:
  reinforces_knowledge:
    - ps.mindfulness.breath-awareness-basics
  supports_goal:
    - goal.mindfulness-beginner
  embodies_principle:
    - principle.small-steps

cue: After morning coffee / Right after waking
routine: |
  1. Sit comfortably
  2. Set 2-minute timer
  3. Close eyes
  4. Follow breath
  5. Return gently when mind wanders
reward: Calm start to day / Sense of accomplishment
```

Every Activity Domain entity can reference curriculum and other domains through UID fields. The ingestion engine handles the wiring — you just declare the connections.

---

## Edges — Evidence-Based Relationships

Edges are standalone YAML files of `type: Edge` that create relationships with evidence properties. They're how SKUEL captures not just "these things are related" but *how* they're related, *how confident* we are, and *why* we believe it.

### The Five Evidence Properties

| Property | Type | What it captures |
|----------|------|-----------------|
| `evidence` | string | Plain-language description of the observation |
| `confidence` | float (0.0-1.0) | How certain we are |
| `polarity` | int (-1, 0, 1) | -1 reduces, 0 neutral, 1 enhances/exacerbates |
| `temporality` | string | Time scale: minutes, hours, days, chronic |
| `source` | string | Where the evidence comes from |

### Confidence Modeling

| Confidence | Meaning | When to use |
|------------|---------|-------------|
| 0.3 | Uncertain | "I think this might be true" |
| 0.5 | Plausible | "I've seen this a few times" |
| 0.7 | Probable | "This consistently seems to happen" |
| 0.9 | Very confident | "I've tracked this reliably" |
| 1.0 | Certain | "This is established fact" |

### Three-Tier Alignment

**YAML** (`caffeine_exacerbates_buzzing.yaml`):

```yaml
version: 1.0
type: Edge

from: ku.nutrition.caffeine
to: ku.attention.buzzing
relationship: EXACERBATED_BY

evidence: >-
  After coffee I feel more restless and mentally speedy. The buzzing
  intensifies within 30 minutes of consumption and lasts 2-4 hours.
confidence: 0.8
polarity: 1
temporality: hours
source: self_observation
observed_at: "2026-03-06T10:30:00+07:00"
tags:
  - stimulant
  - observation
  - caffeine
  - attention
```

**Neo4j** — This produces:

```cypher
MATCH (from:Ku {uid: "ku.nutrition.caffeine"})
MATCH (to:Ku {uid: "ku.attention.buzzing"})
MERGE (from)-[r:EXACERBATED_BY]->(to)
SET r.evidence = "After coffee I feel more restless...",
    r.confidence = 0.8,
    r.polarity = 1,
    r.temporality = "hours",
    r.source = "self_observation",
    r.observed_at = datetime("2026-03-06T10:30:00+07:00"),
    r.tags = ["stimulant", "observation", "caffeine", "attention"],
    r.updated_at = datetime()
```

### Evidence Relationships vs. Structural Connections

| Use | When | Example |
|-----|------|---------|
| `connections:` block (on PathSteps) | Structural prerequisite/enablement | "Read Breath Basics before Mind Wandering" |
| `type: Edge` YAML file | Evidence-based observation with confidence | "Caffeine exacerbates buzzing (confidence: 0.8)" |

Use `connections:` when the relationship is structural and certain — ordering curriculum content. Use Edge YAML when the relationship carries evidence, confidence, and polarity — tracking observations about how things affect each other.

The `RelationshipName` enum (`core/models/relationship_names.py`) defines five evidence relationship types: `EXACERBATED_BY`, `REDUCED_BY`, `CORRELATED_WITH`, `CAUSES`, `PRECEDES`.

> **Note:** Edge ingestion uses raw Cypher (MATCH/MERGE) rather than the BulkIngestionEngine, since edges create relationships, not nodes. Both single-file and batch ingestion detect `type: Edge` automatically.

---

## What Makes Content Discoverable

SKUEL offers three discovery paths, and the fields you fill in your YAML determine which paths find your content.

### Text Search

Title, description, content, and tags are indexed for full-text search. A user searching "breath" will find any entity with that word in these fields. Ku `aliases` are also searchable — if you add "breathing" as an alias for the Breath Ku, text search for "breathing" finds it.

### Vector/Semantic Search

Embedding text is built from entity-specific field maps. Each entity type contributes different fields:

| Entity Type | Fields included in embedding |
|-------------|----------------------------|
| Ku | title, summary, description |
| PathStep | title, content, intent, description |
| LearningPath | title, description, outcomes |
| Task | title, description |
| Goal | title, description, vision_statement |
| Habit | name, title, description, cue, reward |
| Event | title, description, location |
| Choice | title, description, decision_context, outcome |
| Principle | title, statement, description |
| Exercise | title, instructions, description |
| Resource | title, author, content, summary |

Curriculum types use double-newline separators between fields for stronger semantic boundaries. Activity types use single newlines.

### Graph-Aware Search

Relationships power the most sophisticated discovery. The graph answers questions that keyword and semantic search cannot:

- "What am I ready to learn?" — traverse `REQUIRES_STEP` prerequisite chains against mastery state
- "What supports my current goal?" — follow `SUPPORTS_GOAL`, `GUIDED_BY_PRINCIPLE` from the goal
- "What does this PathStep teach?" — follow `USES_KU` to atomic concepts

### Discovery Matrix

| Field | Text Search | Vector Search | Graph Query |
|---|---|---|---|
| `title` | Yes | Yes | — |
| `description` | Yes | Yes | — |
| `content` | Yes | Yes | — |
| `tags` | Yes | — | — |
| `aliases` (Ku) | Yes | Yes | — |
| `nous` (Ku/PS) | Filter | — | — |
| `uses_kus` | — | — | `USES_KU` edge |
| `connections.*` | — | — | Named edges |
| `*_uids` fields | — | — | Named edges |

The more fields you fill, the more discoverable your content becomes. A Ku with aliases, a clear description, and ORGANIZES relationships is findable from every direction.

---

## Bundles and Ingestion

### What a Bundle Is

A domain bundle is a directory containing YAML files and a `manifest.yaml`. The manifest declares every entity in the bundle, groups them by type, and specifies import order.

### Import Order Matters

Dependencies must exist before the entities that reference them. The manifest's `import_order` ensures this:

```yaml
import_order:
  1_kus:                    # Kus first — referenced by PathSteps
    - ku.mindfulness.breath
    - ku.mindfulness.attention

  2_supporting_entities:    # Activity entities — referenced by PathSteps
    - principle.small-steps
    - habit.daily-2min-breath
    - task.log-first-5-sessions
    - event.practice-block-2min
    - goal.mindfulness-beginner

  3_path_steps:             # PathSteps — reference all of the above
    - ps.mindfulness-101.step-1
    - ps.mindfulness-101.step-2

  4_learning_paths:         # Paths last — reference PathSteps
    - lp.mindfulness-101
```

MERGE semantics make ingestion idempotent — re-ingesting a bundle updates existing nodes without duplication.

### Running Ingestion

**Python API:**

```python
from core.services.ingestion import UnifiedIngestionService

# Single file
await service.ingest_file(Path("yaml_templates/domains/mindfulness_101/ku_breath.yaml"))

# Full directory
await service.ingest_directory(Path("yaml_templates/domains/mindfulness_101/"))

# Incremental (only changed files)
await service.ingest_directory(path, ingestion_mode="incremental", validate_targets=True)

# Bundle with manifest
await service.ingest_bundle(Path("yaml_templates/domains/mindfulness_101/"))
```

**REST API:**

```
POST /api/ingest/file          — Single file
POST /api/vault/sync/content   — Content-vault sync (reconciler; ADR-070 Decision 9)
POST /api/ingest/domain/{name} — Named domain bundle
```

### Dry-Run Mode

Preview what ingestion would do without writing to Neo4j:

```python
result = await service.dry_run(Path("yaml_templates/domains/mindfulness_101/"))
# Returns: files_to_create, files_to_update, files_to_skip, relationships_to_create
```

---

## Quick Reference

### UID Formats

| Entity Type | UID Format | Mindfulness 101 Example |
|-------------|-----------|------------------------|
| Ku | `ku.{namespace}.{slug}` | `ku.mindfulness.breath` |
| PathStep | `ps.{namespace}.{slug}` | `ps.mindfulness-101.step-1` |
| LearningPath | `lp:{slug}` | `lp.mindfulness-101` |
| Task | `task:{slug}` | `task.log-first-5-sessions` |
| Goal | `goal:{slug}` | `goal.mindfulness-beginner` |
| Habit | `habit:{slug}` | `habit.daily-2min-breath` |
| Event | `event:{slug}` | `event.practice-block-2min` |
| Choice | `choice:{slug}` | `choice.2-minutes-right-now` |
| Principle | `principle:{slug}` | `principle.small-steps` |
| Edge | (no UID) | N/A — relationship only |

### Required Fields by Type

| YAML `type:` | Required Fields |
|-------------|----------------|
| `Ku` | title |
| `PathStep` | title |
| `LearningPath` | title (`name:` accepted — renamed to title) |
| `Task` | title |
| `Goal` | title |
| `Habit` | title |
| `Event` | title |
| `Choice` | title |
| `Principle` | title (`name:` accepted), statement |
| `Edge` | from, to, relationship |

### YAML `type:` Values

`Ku`, `PathStep`, `LearningPath`, `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `Edge`

---

## See Also

- `yaml_templates/README.md` — Template overview and ingestion instructions
- `yaml_templates/_schemas/` — Full field reference for every entity type
- `yaml_templates/domains/mindfulness_101/README.md` — Bundle design principles
- `docs/patterns/UNIFIED_INGESTION_GUIDE.md` — Ingestion API reference and modes
- `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — Ku, PS, LP topology
- `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` — Complete relationship catalog
