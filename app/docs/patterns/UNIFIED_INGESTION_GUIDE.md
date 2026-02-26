---
title: Unified Ingestion Implementation Guide
updated: 2026-01-20
category: patterns
related_skills: []
related_docs:
- /docs/decisions/ADR-014-unified-ingestion.md
---

# Unified Ingestion Implementation Guide

The "hips" of SKUEL - stability through clarity. Connects content (MD/YAML) to the knowledge graph (Neo4j).

**Decision context:** See [ADR-014](/docs/decisions/ADR-014-unified-ingestion.md) for architectural decisions.

---

## Quick Start

```python
from core.services.ingestion import UnifiedIngestionService

service = UnifiedIngestionService(driver)

# Ingest a single file
result = await service.ingest_file(Path("ku.machine-learning.md"))

# Ingest a directory (full ingestion)
stats = await service.ingest_directory(Path("/docs"), pattern="*.md")

# Incremental ingestion - skip unchanged files (recommended for large vaults)
stats = await service.ingest_directory(
    Path("/docs"),
    ingestion_mode="incremental",      # Skip files with unchanged content hash
    validate_targets=True,        # Validate relationship UIDs exist
)

# Ingest an Obsidian vault
stats = await service.ingest_vault(Path("/vault"), subdirs=["docs", "notes"])

# Ingest a bundle with manifest
stats = await service.ingest_bundle(Path("/bundles/mindfulness"))
```

---

## UX Guide: Using Ingestion Features (2026-02-06)

### Dry-Run Preview

Preview changes before ingesting to Neo4j:

```python
# Preview without writing
result = await service.ingest_directory(
    Path("/docs"),
    dry_run=True  # Preview mode
)

preview = result.value  # DryRunPreview object

# Inspect what would change
print(f"Would create: {len(preview.files_to_create)} files")
print(f"Would update: {len(preview.files_to_update)} files")
print(f"Would skip: {len(preview.files_to_skip)} files")
print(f"Relationships: {len(preview.relationships_to_create)}")
```

**Use Cases:**
- Verify file detection before large ingestion
- Check entity type classification
- Validate relationship targets
- Estimate ingestion impact (nodes/edges)

### Ingestion History & Audit Trail

Track all ingestion operations in Neo4j:

```python
from core.services.ingestion import IngestionHistoryService

history = IngestionHistoryService(driver)

# Create history entry before ingestion
operation_id = await history.create_entry(
    operation_type="directory",
    user_uid="user_admin",
    source_path="/vault/docs"
)

# Perform ingestion
result = await service.ingest_directory(Path("/vault/docs"))

# Update history with results
await history.update_entry(
    operation_id=operation_id,
    status="completed" if result.is_ok else "failed",
    stats=result.value.__dict__,
    errors=result.value.errors if result.is_ok else []
)

# Retrieve history (paginated)
entries = await history.get_history(limit=50, offset=0)
for entry in entries.value:
    print(f"{entry.started_at}: {entry.operation_type} - {entry.status}")
    print(f"  Files: {entry.stats['successful']}/{entry.stats['total_files']}")
```

**Graph Model:**
```cypher
(:IngestionHistory {
  operation_id: "uuid",
  operation_type: "directory",
  started_at: datetime(),
  completed_at: datetime(),
  status: "completed",
  total_files: 1000,
  successful: 995,
  failed: 5
})-[:HAD_ERROR]->(:IngestionError {
  file: "/vault/bad.md",
  error: "Missing title",
  stage: "validation"
})
```

### Real-Time Progress (WebSocket)

Monitor ingestion progress in real-time:

```python
from core.services.ingestion import ProgressTracker

# Create progress tracker with WebSocket callback
def broadcast_progress(operation_id, progress_data):
    # Broadcast to connected WebSocket clients
    # See /adapters/inbound/ingestion_api.py for implementation
    pass

# Use progress callback during ingestion
result = await service.ingest_directory(
    Path("/vault/docs"),
    progress_callback=lambda current, total, file: broadcast_progress(
        operation_id,
        {
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 1),
            "current_file": str(file),
        }
    )
)
```

**WebSocket Endpoint:**
```
ws://localhost:5001/ws/ingest/progress/{operation_id}
```

**Progress Data Format:**
```json
{
  "current": 100,
  "total": 1000,
  "percentage": 10.0,
  "current_file": "/vault/docs/file.md",
  "eta_seconds": 90
}
```

**Client-Side (Alpine.js):**
```html
<div x-data="ingestionProgress('operation-uuid')">
  <div x-text="percentage + '%'"></div>
  <div x-text="currentFile"></div>
  <div x-text="formatEta()"></div>
</div>
```

### Domain-Integrated Ingestion (Admin)

Trigger ingestion via the admin panel or API endpoints:

```bash
# Ingest a specific domain (admin only)
POST /api/ingest/domain/ku
```

**See:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md` for ingestion architecture

---

## Package Structure

```
core/services/ingestion/
├── __init__.py                    # Public API exports
├── unified_ingestion_service.py   # Orchestration (~370 lines)
├── config.py                      # Entity configs + constants
├── types.py                       # Data classes (Stats, Errors)
├── parser.py                      # MD/YAML parsing
├── detector.py                    # Format/type detection
├── preparer.py                    # Data preparation
├── validator.py                   # Validation pipeline
├── batch.py                       # Concurrent operations
└── ingestion_tracker.py           # Incremental ingestion state
```

**Import (One Path Forward):**
```python
from core.services.ingestion import UnifiedIngestionService
```

---

## Ingestion Modes

The service supports three ingestion strategies for directory and vault operations:

| Mode | Description | Use Case |
|------|-------------|----------|
| `"full"` | Process all files (default) | Initial import, clean slate |
| `"incremental"` | Skip files with unchanged content hash | Regular ingestion after initial import |
| `"smart"` | Use mtime for fast filtering, verify with hash | Large vaults, frequent ingestion |

### Incremental Ingestion

Tracks file state in Neo4j to skip unchanged files:

```python
# First ingestion - processes all files, stores ingestion metadata
stats = await service.ingest_directory(Path("/vault"), ingestion_mode="incremental")
# IncrementalStats: total_files=1000, files_ingested=1000, files_skipped=0

# Second ingestion - skips unchanged files
stats = await service.ingest_directory(Path("/vault"), ingestion_mode="incremental")
# IncrementalStats: total_files=1000, files_ingested=5, files_skipped=995, skip_efficiency=99.5%
```

**How it works:**
1. Computes SHA-256 hash of file content
2. Stores hash + mtime in Neo4j `IngestionMetadata` nodes
3. On subsequent ingestion, compares current hash/mtime to stored values
4. Only processes files where content has changed

### IncrementalStats Response

Incremental ingestion returns `IncrementalStats` instead of `IngestionStats`:

```python
@dataclass
class IncrementalStats:
    total_files: int          # Total files found
    files_checked: int        # Files examined for changes
    files_skipped: int        # Unchanged files (skipped)
    files_ingested: int       # Files actually processed
    files_failed: int         # Files with errors
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    duration_seconds: float
    skipped_unchanged: int    # Skipped due to mtime match
    skipped_hash_match: int   # Skipped due to hash match
    errors: list[dict]

    @property
    def skip_efficiency(self) -> float:  # Percentage of files skipped
```

---

## Relationship Validation

Validate that referenced UIDs exist before creating edges:

```python
stats = await service.ingest_directory(
    Path("/docs"),
    validate_targets=True,  # Enable validation
)

# Warnings logged for missing targets:
# [ku] 'ku.nonexistent' referenced by 3 entities but does not exist
```

### Direct Validation API

```python
from core.services.ingestion import validate_relationship_targets

result = await validate_relationship_targets(
    entities=[{"uid": "ku.test", "connections.requires": ["ku.prereq"]}],
    relationship_config=ENTITY_CONFIGS[EntityType.CURRICULUM].relationship_config,
    driver=driver,
)

if not result.value.valid:
    print(f"Missing UIDs: {result.value.missing_uids}")
    for entity_uid, missing in result.value.missing_by_entity.items():
        print(f"  {entity_uid} references: {missing}")
```

---

## Progress Reporting

Monitor progress during large ingestion operations:

```python
def on_progress(current: int, total: int, file_path: str):
    print(f"[{current}/{total}] Processing: {file_path}")

stats = await service.ingest_directory(
    Path("/vault"),
    progress_callback=on_progress,
)
```

---

## Service Methods

### ingest_file(path)

Ingest a single file (Markdown or YAML).

```python
result = await service.ingest_file(Path("/docs/ku.python-basics.md"))

if result.is_ok:
    entity = result.value
    print(f"Ingested: {entity['uid']}")
else:
    print(f"Error: {result.error.message}")
```

### ingest_directory(path, ...)

Batch ingest all matching files in a directory.

```python
stats = await service.ingest_directory(
    Path("/docs/curriculum"),
    pattern="*.md",              # Or "*.yaml" or "*" for all
    ingestion_mode="incremental",     # Skip unchanged files
    validate_targets=True,       # Validate relationship UIDs exist
    progress_callback=on_progress,
)

if stats.is_ok:
    print(f"Ingested: {stats.value.files_ingested}")
    print(f"Skipped: {stats.value.files_skipped}")
    for error in stats.value.errors or []:
        print(f"  - {error['file']}: {error['error']}")
```

### ingest_vault(path, subdirs=None)

Ingest an Obsidian vault. Optionally limit to specific subdirectories.

```python
stats = await service.ingest_vault(
    Path("/home/mike/0bsidian/skuel"),
    subdirs=["docs", "curriculum"]  # Optional: limit to these folders
)
```

### ingest_bundle(path)

Ingest a manifest-driven bundle.

```python
# Bundle structure:
# /bundles/mindfulness/
# ├── manifest.yaml          # Lists files to ingest
# ├── ku.breath-awareness.md
# ├── ku.body-scan.md
# └── lp.mindfulness-basics.yaml

stats = await service.ingest_bundle(Path("/bundles/mindfulness"))
```

---

## Configuration

### Default User UID

Configurable via environment variable:

```bash
export SKUEL_DEFAULT_USER_UID="user:admin"
```

Falls back to `"user:system"` if not set.

```python
from core.services.ingestion import DEFAULT_USER_UID
print(DEFAULT_USER_UID)  # "user:admin" or "user:system"
```

---

## Content Formats

### Markdown Files (.md)

Best for text-heavy content like Knowledge Units:

```yaml
# /docs/ku.machine-learning.md
---
title: Machine Learning
domain: tech
tags: [ml, ai, algorithms]
connections:
  requires:
    - ku.python-basics
    - ku.statistics
  enables:
    - ku.deep-learning
---

Your markdown content here...

## Key Concepts
- Supervised learning
- Unsupervised learning
```

### YAML Files (.yaml, .yml)

Best for structured entities like Tasks, Goals, Events:

```yaml
# /curriculum/task.log-sessions.yaml
type: task
uid: task.log-sessions
title: Log First 5 Sessions
description: Record your meditation sessions
priority: high
status: pending
connections:
  applies_knowledge:
    - ku.meditation-basics
  fulfills_goal:
    - goal.establish-practice
```

---

## Entity Configuration

All 14 entity types are supported. Configuration in `config.py`:

| Entity Type | Prefix | Required Fields | Example File |
|-------------|--------|-----------------|--------------|
| `ku` | `ku.` | title, content | `ku.python-basics.md` |
| `ls` | `ls.` | title | `ls.learn-variables.yaml` |
| `lp` | `lp.` | name | `lp.python-journey.yaml` |
| `moc` | `moc.` | title | `moc.programming.yaml` |
| `task` | `task.` | title | `task.complete-exercise.yaml` |
| `goal` | `goal.` | title | `goal.learn-python.yaml` |
| `habit` | `habit.` | title | `habit.daily-practice.yaml` |
| `event` | `event.` | title | `event.workshop.yaml` |
| `choice` | `choice.` | title | `choice.career-path.yaml` |
| `principle` | `principle.` | name, statement | `principle.consistency.yaml` |
| `journal` | `journal.` | content | `journal.2026-01-07.yaml` |
| `assignment` | `assignment.` | title | `assignment.homework.yaml` |
| `expense` | `expense.` | description, amount | `expense.books.yaml` |
| `lifepath` | `lifepath.` | user_uid | `lifepath.vision.yaml` |

### Entity Type Detection

The service auto-detects entity type from:
1. **Explicit `type` field** in YAML frontmatter
2. **UID prefix** (e.g., `ku.name` → KU)
3. **File name prefix** (e.g., `ku.name.md` → KU)
4. **`moc: true` flag** → MOC

---

## UID Format

**Standard:** Dot notation (`entity.name`)

```
ku.breath-awareness      ✅ Correct
task.log-sessions        ✅ Correct
ku:breath-awareness      ❌ Auto-normalized to ku.breath-awareness
```

### Auto-Normalization

The service automatically normalizes:
- Colon notation: `ku:name` → `ku.name`
- Spaces: `ku.my name` → `ku.my-name`
- Case: Preserved (lowercase recommended)

---

## Relationships (Graph-Native)

Define relationships in the `connections` field:

```yaml
connections:
  requires:                    # REQUIRES_KNOWLEDGE relationship
    - ku.python-basics
  enables:                     # ENABLES_KNOWLEDGE relationship
    - ku.advanced-ml
  applies_knowledge:           # APPLIES_KNOWLEDGE relationship
    - ku.statistics
  fulfills_goal:               # FULFILLS_GOAL relationship
    - goal.learn-ml
```

### Available Relationship Types

| Connection Field | Relationship Type | Target Entity | Used By |
|-----------------|-------------------|---------------|---------|
| `requires` | REQUIRES_KNOWLEDGE | KU | KU |
| `enables` | ENABLES_KNOWLEDGE | KU | KU |
| `related` | RELATED_TO | KU | KU |
| `depends_on` | DEPENDS_ON | Task | Task |
| `applies_knowledge` | APPLIES_KNOWLEDGE | KU | Task, Event |
| `requires_knowledge` | REQUIRES_KNOWLEDGE | KU | Goal |
| `reinforces_knowledge` | REINFORCES_KNOWLEDGE | KU | Habit |
| `fulfills_goal` | FULFILLS_GOAL | Goal | Task |
| `supports_goal` | SUPPORTS_GOAL | Goal | Habit |
| `aligned_with_principle` | GUIDED_BY_PRINCIPLE | Principle | Goal |
| `guided_by_principle` | ALIGNED_WITH_PRINCIPLE | Principle | Choice |
| `guides_goal` | GUIDES_GOAL | Goal | Principle |
| `inspires_habit` | INSPIRES_HABIT | Habit | Principle |
| `contains_steps` | HAS_STEP | LS | LP |
| `teaches_knowledge` | CONTAINS_KNOWLEDGE | KU | LS |
| `organizes` | ORGANIZES | KU | MOC |

> **Note:** KU-to-KU relationship types are unified with the Relationship Registry.
> Ingestion config is derived from the registry, so `requires` maps to
> `REQUIRES_KNOWLEDGE` and `enables` maps to `ENABLES_KNOWLEDGE` — the same
> types used across all domains. See `core/services/ingestion/config.py` for the
> full mapping.

---

## API Endpoints

| Endpoint | Method | Request Body | Response |
|----------|--------|--------------|----------|
| `/api/ingest/file` | POST | `{"file_path": "/path/to/file"}` | Entity dict |
| `/api/ingest/directory` | POST | `{"path": "/dir", "pattern": "*.md", "ingestion_mode": "incremental"}` | IngestionStats/IncrementalStats |
| `/api/ingest/vault` | POST | `{"path": "/vault", "subdirs": ["docs"]}` | IngestionStats |
| `/api/ingest/bundle` | POST | `{"path": "/bundle"}` | BundleStats |
| `/ingest` | GET | - | Dashboard UI |

### Example: Incremental ingestion via curl

```bash
# Incremental directory ingestion
curl -X POST http://localhost:5001/api/ingest/directory \
  -H "Content-Type: application/json" \
  -d '{"path": "/docs/curriculum", "pattern": "*.md", "ingestion_mode": "incremental"}'
```

---

## Response Types

### IngestionStats (Full Ingestion)

```python
@dataclass
class IngestionStats:
    total_files: int
    successful: int
    failed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    duration_seconds: float
    errors: list[dict] | None
```

### IncrementalStats (Incremental Ingestion)

```python
@dataclass
class IncrementalStats:
    total_files: int
    files_checked: int
    files_skipped: int
    files_ingested: int
    files_failed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    duration_seconds: float
    skipped_unchanged: int
    skipped_hash_match: int
    errors: list[dict] | None

    @property
    def skip_efficiency(self) -> float
```

### RelationshipValidationResult

```python
@dataclass
class RelationshipValidationResult:
    valid: bool
    total_references: int
    valid_references: int
    missing_references: int
    missing_by_entity: dict[str, list[str]]
    missing_uids: set[str]
    warnings: list[str]
```

### ValidationResult

```python
@dataclass
class ValidationResult:
    valid: bool
    file_path: str
    entity_type: str
    uid: str
    title: str | None
    format: str
    warnings: list[str]
    errors: list[str]
    prepared_data: dict | None
    relationship_targets: dict[str, list[str]]
```

---

## Validation

Pre-validate files before ingestion:

```python
from core.services.ingestion import validate_file, validate_directory

# Single file
result = await service.validate_file(Path("/docs/ku.test.md"))
if result.value.valid:
    print(f"Valid: {result.value.entity_type} - {result.value.uid}")
else:
    for error in result.value.errors:
        print(f"Error: {error}")

# Directory
dir_result = await service.validate_directory(Path("/docs"))
print(f"Valid: {dir_result.value.valid_files}")
print(f"Invalid: {dir_result.value.invalid_files}")
```

---

## Direct Module Usage

For advanced use cases, import modules directly:

```python
from core.services.ingestion import (
    # Parsing
    parse_markdown,
    parse_yaml,

    # Detection
    detect_format,
    detect_entity_type,

    # Preparation
    generate_uid,
    normalize_uid,
    prepare_entity_data,

    # Validation
    validate_file,
    validate_entity_data,
    validate_required_fields,
    validate_relationship_targets,

    # Ingestion tracking
    IngestionTracker,
    FileIngestionMetadata,
    IngestionDecision,

    # Configuration
    ENTITY_CONFIGS,
    EntityIngestionConfig,
    DEFAULT_USER_UID,
)

# Example: Check if file needs ingestion
tracker = IngestionTracker(driver)
metadata_map = await tracker.get_ingestion_metadata([Path("/docs/ku.test.md")])
decision = tracker.needs_ingestion(Path("/docs/ku.test.md"), metadata_map.get("/docs/ku.test.md"))
print(f"Needs ingestion: {decision.needs_ingestion} ({decision.reason})")
```

---

## See Also

- **Decision context:** [ADR-014](/docs/decisions/ADR-014-unified-ingestion.md) - Architecture decisions
- **UID format:** [ADR-013](/docs/decisions/ADR-013-ku-uid-flat-identity.md) - Why dot notation
- **Domain architecture:** `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`
