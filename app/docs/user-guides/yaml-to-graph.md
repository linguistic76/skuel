# YAML to Graph — A Creator's Guide to SKUEL Content

*Last updated: 2026-03-08*

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

A Ku is the smallest nameable concept in SKUEL. It's an atomic reference node — no content body, no paragraphs, no teaching narrative. If you can define it in one sentence, it's a Ku. If it needs explanation, it's an Article.

**Granularity decision:** "One sentence = Ku. Paragraphs = Article."

### ku_category Values

| Category | What it captures | Example |
|----------|-----------------|---------|
| `state` | Mental/physical state | Buzzing, Flow, Fatigue |
| `concept` | Abstract idea | Attention, Metacognition |
| `principle` | Guiding rule | Non-judgment, Impermanence |
| `intake` | Something consumed | Caffeine, Alcohol |
| `substance` | Physical substance | Cortisol, Dopamine |
| `practice` | Something you do | Breath awareness, Body scan |
| `value` | Something you hold | Compassion, Curiosity |

### Namespace Design

The `namespace` field groups related Kus without imposing hierarchy. UIDs are flat — hierarchy lives in ORGANIZES relationships, not in the UID itself.

Choose namespaces that reflect domains of knowledge: `mindfulness`, `nutrition`, `attention`, `emotion`. A Ku can belong to one namespace but be ORGANIZED by Kus from any namespace.

### Aliases

The `aliases` field provides alternative names that feed both text search and embedding generation. If users might search for "breathing" instead of "breath", add the alias.

### Three-Tier Alignment

**YAML** (`ku_breath.yaml`):

```yaml
version: 1.0
type: Ku

uid: ku:mindfulness:breath
title: Breath
namespace: mindfulness
ku_category: practice
aliases:
  - breathing
  - breath awareness
  - mindful breathing
source: research
description: >-
  The natural rhythm of inhalation and exhalation, used as the
  primary anchor for attention in mindfulness practice.
tags:
  - mindfulness
  - practice
  - foundational
```

**Python** — `Ku` dataclass (`core/models/ku/ku.py`) extends `Entity` directly (not Curriculum). Four Ku-specific fields: `namespace`, `ku_category`, `aliases` (tuple), `source`.

**Neo4j** — The ingestion engine generates:

```cypher
MERGE (n:Ku {uid: "ku.mindfulness.breath"})
  ON CREATE SET
    n.title = "Breath",
    n.namespace = "mindfulness",
    n.ku_category = "practice",
    n.aliases = ["breathing", "breath awareness", "mindful breathing"],
    n.source = "research",
    n.description = "The natural rhythm of ...",
    n.tags = ["mindfulness", "practice", "foundational"],
    n.entity_type = "KU",
    n.created_at = datetime()
  ON MATCH SET
    n.updated_at = datetime()
```

Note the UID normalization: colons in YAML (`ku:mindfulness:breath`) become dots in Neo4j (`ku.mindfulness.breath`). This happens automatically in the preparer.

---

## The Composition — Article

An Article is a teaching narrative. Where a Ku names a single concept, an Article weaves multiple Kus into a readable composition with full markdown content. Articles are the "textbook pages" of SKUEL.

### uses_kus — Composing Atoms

The `uses_kus` field declares which Kus an Article composes. Each entry becomes a `(Article)-[:USES_KU]->(Ku)` edge in the graph. This is how SKUEL knows which atomic concepts a piece of teaching content covers.

### connections — Structural Relationships

The `connections` block declares how Articles relate to each other:

| Key | Relationship Created | Meaning |
|-----|---------------------|---------|
| `requires` | `REQUIRES_KNOWLEDGE` | Must read this first |
| `enables` | `ENABLES_KNOWLEDGE` | Unlocks after reading |

### Three-Tier Alignment

**YAML** (`article_breath-awareness-basics.yaml`):

```yaml
version: 1.0
type: Article

uid: a:mindfulness:breath-awareness-basics
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
  - ku:mindfulness:breath
  - ku:mindfulness:attention

connections:
  requires: []
  enables:
    - a:mindfulness:posture-basics
    - a:mindfulness:mind-wandering-happens

tags:
  - breath
  - meditation
  - beginner
  - foundational
```

**Python** — `Article` extends `Curriculum`, which extends `Entity`. The `Curriculum` base adds ~21 fields including `content`, `complexity`, `domain`, and `quality_score`. Article adds no extra fields — Curriculum provides everything a teaching composition needs.

**How flattening works:** The preparer extracts the nested `connections` dict and flattens it to dotted keys:

```python
# Input:  {"connections": {"requires": [], "enables": ["a:mindfulness:posture-basics", ...]}}
# Output: {"connections.enables": ["a.mindfulness.posture-basics", ...]}
```

The BulkIngestionEngine then generates FOREACH patterns for each dotted key:

```cypher
MERGE (n:Entity {uid: "a.mindfulness.breath-awareness-basics"})
  ON CREATE SET n = props, n.created_at = datetime()
  ON MATCH SET n += props, n.updated_at = datetime()
WITH n, item

// uses_kus → USES_KU edges
FOREACH (target_uid IN coalesce(item.uses_kus, []) |
  MERGE (target:Entity {uid: target_uid})
  MERGE (n)-[:USES_KU]->(target)
)

// connections.enables → ENABLES_KNOWLEDGE edges
FOREACH (target_uid IN coalesce(item.`connections.enables`, []) |
  MERGE (target:Entity {uid: target_uid})
  MERGE (n)-[:ENABLES_KNOWLEDGE]->(target)
)
```

The backtick escaping (`` item.`connections.enables` ``) handles the dotted key in Cypher. Connection data is filtered from node properties in Python before reaching Neo4j — the dotted keys drive edge creation, they don't pollute the node.

---

## The Learning Structure — Steps and Paths

### LearningStep — The Cross-Domain Connector

A LearningStep is the richest entity type in SKUEL. It's where curriculum meets practice — connecting Articles (what to learn) with Habits, Tasks, Choices, Events, and Principles (how to live it).

Every UID-list field on a LearningStep becomes a set of edges in the graph:

| YAML Field | Relationship | Direction | Connects To |
|---|---|---|---|
| `primary_knowledge_uids` | `CONTAINS_KNOWLEDGE` | outgoing | Article |
| `supporting_knowledge_uids` | `CONTAINS_KNOWLEDGE` | outgoing | Article |
| `trains_ku_uids` | `TRAINS_KU` | outgoing | Ku |
| `prerequisite_step_uids` | `REQUIRES_STEP` | outgoing | LearningStep |
| `prerequisite_knowledge_uids` | `REQUIRES_KNOWLEDGE` | outgoing | Article |
| `principle_uids` | `GUIDED_BY_PRINCIPLE` | outgoing | Principle |
| `habit_uids` | `SUPPORTS_HABIT` | outgoing | Habit |
| `task_uids` | `ASSIGNS_TASK` | outgoing | Task |
| `choice_uids` | `GUIDES_CHOICE` | outgoing | Choice |
| `event_template_uids` | `SCHEDULES_EVENT` | outgoing | Event |

**YAML** (`ls_mindfulness-101_step-1.yaml`):

```yaml
version: 1.0
type: LearningStep

uid: ls:mindfulness-101:step-1
title: Two Minutes Today
intent: Try one two-minute breath session, note what you notice

primary_knowledge_uids:
  - a:mindfulness:breath-awareness-basics

supporting_knowledge_uids:
  - a:mindfulness:posture-basics

trains_ku_uids:
  - ku:mindfulness:breath

learning_path_uid: lp:mindfulness-101
sequence: 1

prerequisite_step_uids: []

principle_uids:
  - principle:small-steps

choice_uids:
  - choice:2-minutes-right-now
  - choice:2-minutes-before-bed

habit_uids:
  - habit:daily-2min-breath

task_uids:
  - task:log-first-5-sessions

event_template_uids:
  - event:practice-block-2min

mastery_threshold: 0.7
estimated_hours: 0.5
difficulty: easy
```

This single YAML file produces one node and up to 10 edges. That's the power of the LearningStep — it's the hub where knowledge, practice, and intention converge.

### LearningPath — The Sequence

A LearningPath sequences LearningSteps via `(LearningPath)-[:HAS_STEP]->(LearningStep)` edges. The `steps` list in YAML defines the order.

**YAML** (`lp_mindfulness-101.yaml`):

```yaml
version: 1.0
type: LearningPath

uid: lp:mindfulness-101
name: Mindfulness 101 — Light & Conversational
goal: >-
  Build a gentle daily starter practice with breath
  awareness and meta-cognition

path_type: structured
difficulty: beginner

steps:
  - ls:mindfulness-101:step-1
  - ls:mindfulness-101:step-2

outcomes:
  - Establish a daily 2-minute breath awareness practice
  - Develop the skill of noticing when attention wanders
  - Build meta-awareness through gentle labeling

estimated_hours: 1.0
```

### Prerequisite Chains

When `ls:mindfulness-101:step-2` declares `prerequisite_step_uids: [ls:mindfulness-101:step-1]`, the graph gains a `REQUIRES_STEP` edge. This enables "ready to learn" queries — the system can traverse prerequisite chains to determine which steps a user is prepared for based on their mastery state.

---

## Cross-Domain Linking

SKUEL's graph connects curriculum to life. Activity Domains — Task, Goal, Habit, Event, Choice, Principle — link to curriculum through UID references, and the ingestion engine wires them into edges.

### How a Goal Connects Everything

**YAML** (`goal_mindfulness-beginner.yaml`):

```yaml
uid: goal:mindfulness-beginner
title: Build a gentle daily starter practice

required_knowledge_uids:
  - a:mindfulness:breath-awareness-basics
  - a:mindfulness:posture-basics
  - a:mindfulness:mind-wandering-happens

supporting_habit_uids:
  - habit:daily-2min-breath
  - habit:label-wander-daily

guiding_principle_uids:
  - principle:small-steps
  - principle:attention-over-intensity
```

Each UID list becomes edges: `REQUIRES_KNOWLEDGE`, `SUPPORTS_HABIT`, `GUIDED_BY_PRINCIPLE`.

### The Mindfulness 101 Graph Fragment

```
                    ┌─────────────────────┐
                    │  goal:mindfulness-   │
                    │      beginner        │
                    └──────┬──┬──┬────────┘
           REQUIRES_       │  │  │    GUIDED_BY_
           KNOWLEDGE       │  │  │    PRINCIPLE
          ┌────────────────┘  │  └──────────────┐
          ▼                   │                  ▼
  ┌───────────────┐    SUPPORTS_    ┌─────────────────────┐
  │  a:breath-    │      HABIT      │ principle:small-steps│
  │  awareness    │           │     └─────────────────────┘
  │  -basics      │           ▼
  └───┬───────────┘   ┌──────────────────┐
      │ USES_KU       │ habit:daily-2min │
      ▼               │   -breath        │
  ┌────────────┐      └────────┬─────────┘
  │ ku:breath  │               │ linked_knowledge
  └────────────┘               │
                               ▼
                    ┌───────────────────┐
                    │  a:breath-        │
                    │  awareness-basics │
                    └───────────────────┘
```

This is how SKUEL answers "What should I work on today?" — by traversing from the user's goals through supporting habits, required knowledge, and guiding principles to find the most impactful next action.

### Habits Link Back to Knowledge

**YAML** (`habit_daily-2min-breath.yaml`):

```yaml
uid: habit:daily-2min-breath
name: Daily Two-Minute Breath

linked_knowledge_uids:
  - a:mindfulness:breath-awareness-basics

linked_goal_uids:
  - goal:mindfulness-beginner

linked_principle_uids:
  - principle:small-steps

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

from: ku:nutrition:caffeine
to: ku:attention:buzzing
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
| `connections:` block (on Articles) | Structural prerequisite/enablement | "Read Breath Basics before Mind Wandering" |
| `type: Edge` YAML file | Evidence-based observation with confidence | "Caffeine exacerbates buzzing (confidence: 0.8)" |

Use `connections:` when the relationship is structural and certain — ordering curriculum content. Use Edge YAML when the relationship carries evidence, confidence, and polarity — tracking observations about how things affect each other.

The `RelationshipName` enum (`core/models/relationship_names.py`) defines five evidence relationship types: `EXACERBATED_BY`, `REDUCED_BY`, `CORRELATED_WITH`, `CAUSES`, `PRECEDES`.

> **Note:** Edge ingestion is documented and validated but not yet wired into the automated pipeline. See `docs/roadmap/edge-ingestion-support.md` for status.

---

## What Makes Content Discoverable

SKUEL offers three discovery paths, and the fields you fill in your YAML determine which paths find your content.

### Text Search

Title, description, content, and tags are indexed for full-text search. A user searching "breath" will find any entity with that word in these fields. Ku `aliases` are also searchable — if you add "breathing" as an alias for the Breath Ku, text search for "breathing" finds it.

### Vector/Semantic Search

Embedding text is built from entity-specific field maps. Each entity type contributes different fields:

| Entity Type | Fields included in embedding |
|-------------|----------------------------|
| Article | title, content, summary |
| Ku | title, summary, description |
| LearningStep | title, intent, description |
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
- "What supports my current goal?" — follow `SUPPORTS_HABIT`, `GUIDED_BY_PRINCIPLE` from the goal
- "What does this Article teach?" — follow `USES_KU` to atomic concepts

### Discovery Matrix

| Field | Text Search | Vector Search | Graph Query |
|---|---|---|---|
| `title` | Yes | Yes | — |
| `description` | Yes | Yes | — |
| `content` | Yes | Yes | — |
| `tags` | Yes | — | — |
| `aliases` (Ku) | Yes | Yes | — |
| `namespace` | Filter | — | — |
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
  1_kus:                    # Kus first — referenced by Articles
    - ku:mindfulness:breath
    - ku:mindfulness:attention

  2_articles:               # Articles next — referenced by Steps
    - a:mindfulness:breath-awareness-basics
    - a:mindfulness:posture-basics
    - a:mindfulness:mind-wandering-happens

  3_supporting_entities:    # Activity entities — referenced by Steps
    - principle:small-steps
    - habit:daily-2min-breath
    - task:log-first-5-sessions
    - event:practice-block-2min
    - goal:mindfulness-beginner

  4_learning_steps:         # Steps — reference all of the above
    - ls:mindfulness-101:step-1
    - ls:mindfulness-101:step-2

  5_learning_paths:         # Paths last — reference Steps
    - lp:mindfulness-101
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
POST /api/ingest/directory     — Directory scan
POST /api/ingest/domain/{name} — Named domain bundle
WS   /ws/ingest/progress/{id}  — WebSocket progress
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
| Ku | `ku:{namespace}:{slug}` | `ku:mindfulness:breath` |
| Article | `a:{namespace}:{slug}` | `a:mindfulness:breath-awareness-basics` |
| LearningStep | `ls:{path}:{slug}` | `ls:mindfulness-101:step-1` |
| LearningPath | `lp:{slug}` | `lp:mindfulness-101` |
| Task | `task:{slug}` | `task:log-first-5-sessions` |
| Goal | `goal:{slug}` | `goal:mindfulness-beginner` |
| Habit | `habit:{slug}` | `habit:daily-2min-breath` |
| Event | `event:{slug}` | `event:practice-block-2min` |
| Choice | `choice:{slug}` | `choice:2-minutes-right-now` |
| Principle | `principle:{slug}` | `principle:small-steps` |
| Edge | (no UID) | N/A — relationship only |

### Required Fields by Type

| YAML `type:` | Required Fields |
|-------------|----------------|
| `Ku` | title |
| `Article` | title, content |
| `LearningStep` | title |
| `LearningPath` | name |
| `Task` | title |
| `Goal` | title |
| `Habit` | title |
| `Event` | title |
| `Choice` | title |
| `Principle` | name, statement |
| `Edge` | from, to, relationship |

### YAML `type:` Values

`Ku`, `Article`, `LearningStep`, `LearningPath`, `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `Edge`

---

## See Also

- `yaml_templates/README.md` — Template overview and ingestion instructions
- `yaml_templates/_schemas/` — Full field reference for every entity type
- `yaml_templates/domains/mindfulness_101/README.md` — Bundle design principles
- `docs/patterns/UNIFIED_INGESTION_GUIDE.md` — Ingestion API reference and modes
- `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — Ku, Article, LS, LP topology
- `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` — Complete relationship catalog
