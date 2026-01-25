# SKUEL YAML Templates
## Clean, Human-Readable Curriculum Content

This directory contains YAML templates for creating SKUEL curriculum content and domain bundles.

## Directory Structure

```
yaml_templates/
├── knowledge/           # Knowledge unit (ku) templates
├── learning_steps/      # Learning step (ls) templates
├── learning_paths/      # Learning path (lp) templates
├── habits/              # Habit templates
├── principles/          # Principle templates
├── choices/             # Choice templates
├── goals/               # Goal templates
├── tasks/               # Task templates
├── events/              # Event templates
├── conversations/       # Conversation templates
├── _schemas/            # JSON schemas for validation
└── domains/             # Complete domain bundles
    └── mindfulness_101/ # Example: Mindfulness 101 bundle
```

## Core Curriculum Entities

SKUEL's curriculum is built on three core entities with abbreviated UID prefixes:

| Prefix | Entity | Full Names | Purpose |
|--------|--------|------------|---------|
| **ku** | Knowledge Unit | `knowledge`, `knowledgeunit` | Atomic knowledge content |
| **ls** | Learning Step | `learningstep`, `pathstep` | Learning journey step |
| **lp** | Learning Path | `learningpath` | Complete learning sequence |

### UID Format

```yaml
# Core curriculum (abbreviated prefixes)
ku:{descriptive-slug}         # Knowledge units
ls:{path}:{step-id}          # Learning steps (sequenced)
ls:{standalone-id}           # Learning steps (standalone)
lp:{path-name}               # Learning paths

# Other domains (full names)
principle:{name}
choice:{name}
habit:{name}
goal:{name}
task:{name}
event:{name}
conversation:{date}:{topic}
```

## Creating Content

### 1. Knowledge Unit (ku)

```yaml
version: 1.0
type: KnowledgeUnit
uid: ku:your-topic
title: Your Topic Title
content: |
  Markdown content here
domain: personal
complexity: basic
prerequisites: []
enables: []
tags: [tag1, tag2]
```

### 2. Learning Step (ls)

```yaml
version: 1.0
type: LearningStep
uid: ls:path:step-id
title: Step Title
intent: What learner will achieve

primary_knowledge_uids:
  - ku:main-concept

learning_path_uid: lp:parent-path
sequence: 1

principle_uids: []
choice_uids: []
habit_uids: []
task_uids: []
```

### 3. Learning Path (lp)

```yaml
version: 1.0
type: LearningPath
uid: lp:path-name
name: Path Name
goal: Learning goal
path_type: structured

steps:
  - ls:path:step-1
  - ls:path:step-2
```

## Domain Bundles

A domain bundle is a complete, curated collection of related content.

### Example: Mindfulness 101

Located in `domains/mindfulness_101/`:

- **3 Knowledge Units** (ku:breath-awareness-basics, ku:posture-basics, ku:mind-wandering-happens)
- **2 Learning Steps** (ls:mindfulness-101:step-1, ls:mindfulness-101:step-2)
- **1 Learning Path** (lp:mindfulness-101)
- **Supporting entities** (principles, choices, habits, tasks, events)
- **Manifest file** (import order, entity count)

### Creating a Domain Bundle

1. Create directory: `domains/{bundle_name}/`
2. Add core curriculum YAMLs (ku, ls, lp)
3. Add supporting entity YAMLs (principles, habits, etc.)
4. Create `manifest.yaml` with import order
5. Run YAML ingestion service (see below)

## YAML → Neo4j Ingestion

Content flows through SKUEL's three-tier architecture:

```
YAML File
    ↓
Read & Parse (Python dict)
    ↓
Tier 1: Pydantic Validation (Request models)
    ↓
Tier 2: DTO (mutable data transfer)
    ↓
Tier 3: Pure Model (immutable domain logic)
    ↓
UniversalNeo4jBackend
    ↓
Neo4j Graph Database
```

### Using the Ingestion Service

#### Basic Usage

```python
from core.services.yaml_ingestion_service import YamlIngestionService
from pathlib import Path
from neo4j import AsyncGraphDatabase

# Connect to Neo4j
driver = AsyncGraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password")
)

service = YamlIngestionService(driver)

# Ingest single file (auto-detects entity type)
result = await service.ingest_yaml(
    Path("yaml_templates/domains/mindfulness_101/ku_breath-awareness-basics.yaml")
)

if result.is_ok:
    entity = result.value
    print(f"✅ Created: {entity.uid}")
else:
    print(f"❌ Error: {result.error.message}")
```

#### Domain Bundle Ingestion (Recommended)

```python
# Ingest entire domain bundle using manifest
result = await service.ingest_domain_bundle(
    Path("yaml_templates/domains/mindfulness_101")
)

if result.is_ok:
    stats = result.value
    print(f"📦 Bundle: {stats['bundle_name']}")
    print(f"   ✅ Successful: {stats['total_successful']}/{stats['total_attempted']}")
    print(f"   Entities created: {stats['entities_created']}")
```

#### Entity-Specific Methods

```python
# Knowledge Unit
result = await service.ingest_knowledge_yaml(Path("ku_example.yaml"))

# Learning Step
result = await service.ingest_learning_step_yaml(Path("ls_example.yaml"))

# Learning Path
result = await service.ingest_learning_path_yaml(Path("lp_example.yaml"))
```

#### Complete Examples

See `/examples/yaml_ingestion_example.py` for comprehensive examples including:
- Single file ingestion
- Auto-detection
- Domain bundle ingestion
- Bulk ingestion with error handling
- Learning step relationship handling

## Benefits of YAML Templates

1. **Human-Readable** - Easy to read, write, and version control
2. **Type-Safe** - Validated through Pydantic before entering system
3. **Three-Tier Flow** - Properly flows through SKUEL architecture
4. **Relationship-First** - UIDs create clean graph relationships
5. **Bundled Content** - Domain bundles provide complete learning modules
6. **Portable** - Share curriculum as YAML files

## Validation

JSON schemas in `_schemas/` validate YAML structure before ingestion:

- `knowledge_schema.json` - Knowledge unit validation
- `learning_step_schema.json` - Learning step validation
- `learning_path_schema.json` - Learning path validation

Use these for pre-ingestion validation to catch errors early.

## Next Steps

1. **Review Templates** - Examine `knowledge/ku_template.yaml`, `learning_steps/ls_template.yaml`, etc.
2. **Study Example** - Explore `domains/mindfulness_101/` for complete bundle
3. **Create Content** - Copy templates and create your own curriculum
4. **Ingest to Neo4j** - Use YamlIngestionService to import content
5. **Query Graph** - APOC queries discover relationships dynamically

---

**Architecture Documentation**: See `/home/mike/skuel0/CLAUDE.md` section 1.4 for UID conventions.
