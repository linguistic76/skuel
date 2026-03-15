# SKUEL YAML Templates
## Clean, Human-Readable Curriculum Content

This directory contains YAML templates for creating SKUEL curriculum content and domain bundles.

## Directory Structure

```
yaml_templates/
  lessons/              # Lesson templates (units for learning)
  kus/                  # Ku templates (atomic knowledge units)
  edges/                # Edge templates (evidence relationships)
  learning_steps/       # Learning step (ls) templates
  learning_paths/       # Learning path (lp) templates
  habits/               # Habit templates
  principles/           # Principle templates
  choices/              # Choice templates
  goals/                # Goal templates
  tasks/                # Task templates
  events/               # Event templates
  _schemas/             # Template field reference (all entity types)
  domains/              # Complete domain bundles
    mindfulness_101/    # Example: Mindfulness 101 bundle
```

## Four-Entity Curriculum Model

SKUEL's curriculum is built on four entities:

| Prefix | Entity | Purpose | Content? |
|--------|--------|---------|----------|
| **ku** | Ku (atomic) | Single definable concept/state/practice | No (reference node) |
| **l** | Lesson | A unit for learning | Yes (markdown) |
| **ls** | Learning Step | A collection of lessons | No (references Lessons) |
| **lp** | Learning Path | Complete learning sequence | No (sequences Steps) |

### Composition

```
(Lesson)-[:USES_KU]->(Ku)       Lesson composes atomic Kus
(Ls)-[:TRAINS_KU]->(Ku)          Learning Step trains atomic Kus
(Ls)-[:PRIMARY_KNOWLEDGE]->(Lesson)  Step references Lesson for content
(Lp)-[:HAS_STEP]->(Ls)           Path sequences Steps
```

### UID Format

```yaml
# Curriculum entities
ku:{namespace}:{slug}            # Atomic Ku: ku:attention:buzzing
l:{namespace}:{slug}             # Lesson: l:mindfulness:breath-awareness-basics
ls:{path}:{step-id}              # Learning step: ls:mindfulness-101:step-1
lp:{path-name}                   # Learning path: lp:mindfulness-101

# Activity domains
task:{name}                      # task:log-first-5-sessions
habit:{name}                     # habit:daily-2min-breath
goal:{name}                      # goal:mindfulness-beginner
choice:{name}                    # choice:2-minutes-right-now
event:{name}                     # event:practice-block-2min
principle:{name}                 # principle:small-steps
```

## Creating Content

### 1. Ku (Atomic Knowledge Unit)

```yaml
type: Ku
uid: ku:attention:buzzing
title: Buzzing
namespace: attention
ku_category: state           # state/concept/principle/intake/substance/practice/value
aliases: [restlessness, mental agitation]
source: self_observation     # self_observation/research/teacher
```

Kus are lightweight reference nodes. No content body, no learning metadata.

### 2. Lesson (Teaching Composition)

```yaml
type: Lesson
uid: l:mindfulness:breath-awareness-basics
title: Breath Awareness -- Basics
content: |
  ## Full markdown teaching narrative...
complexity: basic            # basic/medium/advanced
uses_kus:
  - ku:mindfulness:breath
  - ku:mindfulness:attention
connections:
  requires: []
  enables: [l:mindfulness:posture-basics]
```

Lessons are units for learning that compose atomic Kus into coherent learning content.

### 3. Edge (Evidence Relationship)

```yaml
type: Edge
from: ku:nutrition:caffeine
to: ku:attention:buzzing
relationship: EXACERBATED_BY
evidence: "After coffee I feel more restless."
confidence: 0.8
source: self_observation
```

**Note:** Edge ingestion is fully wired — both single-file (`ingest_file`) and batch (`ingest_directory`) detect `type: Edge` and create relationships with evidence properties automatically.

### 4. Learning Step & Path

```yaml
# Learning Step
type: LearningStep
uid: ls:mindfulness-101:step-1
knowledge_uid: l:mindfulness:breath-awareness-basics  # Lesson UID
trains_ku_uids: [ku:mindfulness:breath]               # Atomic Kus trained

# Learning Path
type: LearningPath
uid: lp:mindfulness-101
steps: [ls:mindfulness-101:step-1, ls:mindfulness-101:step-2]
```

## Domain Bundles

A domain bundle is a complete, curated collection of related content. See `domains/mindfulness_101/` for a working example with 21 entities.

### Creating a Domain Bundle

1. Create directory: `domains/{bundle_name}/`
2. Add atomic Kus first (referenced by Lessons)
3. Add Lessons that compose Kus into teaching
4. Add supporting entities (principles, habits, tasks, events, goals, choices)
5. Add learning steps and paths
6. Create `manifest.yaml` with import order
7. Run ingestion

## Ingestion

Content is ingested via `UnifiedIngestionService`:

```python
from core.services.ingestion import UnifiedIngestionService

# Single file
result = await service.ingest_file(Path("yaml_templates/kus/ku_attention_buzzing.yaml"))

# Directory (auto-detects entity types)
result = await service.ingest_directory(Path("yaml_templates/domains/mindfulness_101"))

# Dry run (preview changes)
result = await service.ingest_directory(path, dry_run=True)
```

### API Endpoints

- `POST /api/ingest/file` - Single file
- `POST /api/ingest/directory` - Batch with optional dry-run
- `POST /api/ingest/vault` - Obsidian vault ingestion

## Validation

Validation happens via **Pydantic Request models** in the Python code, not via these templates. Templates are documentation showing what fields Pydantic expects.

See `_schemas/` for complete field reference for each entity type.
