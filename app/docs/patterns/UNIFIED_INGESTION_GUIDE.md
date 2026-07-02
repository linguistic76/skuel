---
title: Unified Ingestion Implementation Guide
updated: 2026-04-18
category: patterns
related_skills: []
related_docs:
- /docs/decisions/ADR-014-unified-ingestion.md
- /docs/decisions/ADR-054-user-entry-unified-submissions.md
---

# Unified Ingestion Implementation Guide

The "hips" of SKUEL - stability through clarity. Connects content (MD/YAML) to the knowledge graph (Neo4j).

**Decision context:** See [ADR-014](/docs/decisions/ADR-014-unified-ingestion.md) for architectural decisions.

---

## Default Vault

The default ingestion folder is `/home/mike/0bsidian/0vault/` (the Obsidian vault). This is where Ku YAMLs (`ku_*.yaml`), PathStep YAMLs (`ps_*.yaml`), Exercise YAMLs (`exercise_*.yaml`), edge YAMLs (`edges/edge_*.yaml`), and markdown content files live. Configurable via `INGESTION_PATH` env var.

### Endpoint Path Allowlist (default-deny)

The HTTP/WS ingestion endpoints (`/api/ingest/**`, `WS /ws/ingest/progress/{op_id}`) **do not accept arbitrary host paths**, even from an authenticated admin. `adapters/inbound/ingestion_api.py::_validate_ingestion_path` resolves the request path and rejects it unless it sits under at least one root from `_resolve_allowed_ingestion_roots()`. Precedence chain:

1. `SKUEL_INGESTION_ALLOWED_PATHS` — colon-separated explicit override (multi-vault / staging setups)
2. `INGESTION_PATH` — the single configured vault root (also the documented default)
3. Neither set → **empty list → reject every path** (fail closed)

The admin role gate authorizes *ownership of the action*, not *filesystem reach* — a compromised admin session still can't ingest from `/etc` or `/root`. CLI/programmatic ingestion via `UnifiedIngestionService` bypasses this check (it's HTTP-boundary defense, not a core-service check) — keep ad-hoc paths to scripts you trust.

## Quick Start

```python
from core.services.ingestion import UnifiedIngestionService

service = UnifiedIngestionService(driver)

# Ingest a single file
result = await service.ingest_file(Path("ku.machine-learning.md"))

# Ingest the default vault
stats = await service.ingest_directory(Path("data/vault"), pattern="ku_*.yaml")

# Ingest a directory (full ingestion)
stats = await service.ingest_directory(Path("/docs"), pattern="*.md")

# Incremental ingestion - skip unchanged files (recommended for large vaults)
stats = await service.ingest_directory(
    Path("/docs"),
    ingestion_mode="incremental",      # Skip files with unchanged content hash
    validate_targets=True,        # Validate relationship UIDs exist
)

# Acting-user hint (owner is resolved from the vault descriptor for the path)
result = await service.ingest_file(Path("task_example.yaml"), user_uid=UserUID("user_mike"))

# Ingest an Obsidian vault
stats = await service.ingest_vault(Path("/vault"), subdirs=["docs", "notes"])

# Ingest a bundle with manifest
stats = await service.ingest_bundle(Path("/bundles/mindfulness"))
```

---

## UserEntry YAMLs (`type: user_entry`) — ADR-054

`UserEntry` YAMLs take a dedicated path: `ingest_file()` detects
`type: user_entry` and delegates to
`core/services/ingestion/user_entry_ingestion.py`, which builds a
`UserEntryCreateRequest` and calls `UserEntryService.create_entry()` —
the same method the `/submit` form uses. Both front-ends share the
Interaction audit, TRANSFORMS edge, sharing fan-out, and compensation
delete.

### Required field: `pipeline`

Every UserEntry YAML must declare a pipeline. One of:

- `none` — persisted as-is, no downstream processing.
- `teacher_review` — queued for teacher feedback.
- `llm_summary` — sent to the LLM for a structured summary.
- `extract_activities` — DSL-parsed into real activities (the `/submissions/sync`
  daily-note path, ADR-069). Used by `periodic_notes/`.
- `knowledge` — "developed files": the user's own vault notes in the
  `knowledge/` doorway, shared to teach SKUEL about them. Persisted as-is (no
  processing) and, unlike `reference`, surfaced in the personal-notes context
  digest that informs UserContext. Not counted as a learning-loop submission.
- `reference` — archive/training material (`je_raw/`, `je_pro/`); stored as-is,
  excluded from UserContext counts and Askesis context.

Audio pipelines (`transcribe`, `transcribe_and_structure`) are not
valid in YAML-ingested UserEntry files.

### Optional field: `audience`

`audience:` declares who sees the submission. Defaults to `teachers`
when omitted. Accepted values:

| Value | Meaning |
|-------|---------|
| `teachers` (default) | Expand to every group the uploader is a student-member of (via `AudienceResolver.resolve_default_teachers`). Zero student-role groups → no shares (no silent broadcast). |
| `group:<group_uid>` | Share with exactly one group. |
| `public` | Set `visibility=PUBLIC` (portfolio). |
| `private` | No shares, no visibility change. |

Legacy aliases `je_input` / `je_output` / `exercise_submission` are
**rejected** with an ADR-054 error (no compat shim — One Path Forward).

### Optional field: `uid` (deterministic upsert)

By default a UserEntry is minted a random `ue_<...>` UID and **created**
fresh on every ingest. When a deterministic UID is known, the service
switches to **MERGE-on-uid upsert** instead: re-ingesting an edited file
updates the existing node in place rather than duplicating it.
`created_at` is preserved across re-syncs; `updated_at` and content are
refreshed. The exercise-linked turn-in path (`fulfills_exercise_uid`)
always mints a random UID and is unaffected.

**Periodic notes** (`entry_kind: daily | weekly | monthly`) get a
deterministic UID automatically — no explicit `uid:` needed:

| `entry_kind` | auto-derived UID |
|--------------|-----------------|
| `daily` | `ue:daily:{user_uid}:{date}` (e.g. `ue:daily:user_mike:2026-06-28`) |
| `weekly` | `ue:weekly:{user_uid}:{week_of}` |
| `monthly` | `ue:monthly:{user_uid}:{YYYY-MM}` |

This is the same UID the calendar routes use, so vault-synced daily notes
resolve to the correct SKUEL journal page automatically. You may still
supply an explicit `uid:` to override.

### Markdown body → `content`

For a `type: user_entry` **markdown** file, the parsed body (everything
after the frontmatter) becomes `content` when no explicit `content:` field
is present (explicit `content:` wins). This keeps the note prose — and the
`- [ ]` checkbox lines a periodic note carries — available to downstream
processing instead of being discarded.

### Example

```yaml
version: 1.0
type: user_entry
title: Reflection on Meditations chapter 3
pipeline: teacher_review
audience: teachers          # optional; this is the default

content: |
  My takeaways from Marcus Aurelius on impermanence…
tags: [reading, stoicism]

# Optional — link to an exercise this entry fulfills
# fulfills_exercise_uid: ex_marcus-aurelius_abc123
```

### Shared resolver

`AudienceResolver` (`core/services/user_entry/audience_resolver.py`) is
the single implementation of:

1. Pipeline/audience validation (ADR §3 + §5 guardrails — `teacher_review`
   needs a real audience; `transcribe_and_structure` is private by policy).
2. Share fan-out via `UnifiedSharingService` (explicit groups/users +
   auto-share to exercise groups).
3. `resolve_default_teachers(user_uid)` — used by the YAML preparer to
   expand `audience: teachers` into explicit group UIDs.

`UserEntryService` and the ingestion bridge both hold the same resolver
instance; there is no second code path.

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

**Security:** Requires admin session. Unauthorized connections are closed with code 4003 before `ws.accept()`.

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

### User Data Ingestion

Personal data enters SKUEL via:
- **`/submissions/sync`** — bidirectional Obsidian sync (primary path); daily notes with `pipeline: extract_activities` become Activity entities; task completions round-trip back to the vault. (`/settings/vault` → 301 redirect here; HTMX POST endpoints remain at `/settings/vault/sync` and `/settings/vault/consent`.)
- **`/submissions/exercise`** — exercise worksheet submission (single file, exercise-linked). (`/submit` → 302 redirect here.)

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

## Ownership: descriptor-by-path, not caller identity (ADR-070)

**Access rights are `f(EntityType)`, computed at read time — never materialized on
the node.** Curriculum (Ku/PathStep/LP/Exercise) is SHARED-by-type and receives *no*
owner; USER_OWNED types (the 6 activity domains, UserEntry) carry a `user_uid`.

The one thing ingest must get right uniformly is **who owns a USER_OWNED entity**, and
that is resolved from the **vault descriptor governing the file's path** — not from the
caller. Every `user_uid=` argument on `ingest_file` / `ingest_directory` / `ingest_vault`
is only an **acting-user hint**:

| File lives in… | Owner attributed | Hint |
|----------------|------------------|------|
| Content vault (`INGESTION_PATH`) | `content_owner_uid` ("acts-as" account) | ignored |
| A personal vault (`VAULT_ROOT`)  | the acting user (per-tenant)            | used |
| Neither root                     | content acts-as (safe default)          | ignored |

`VaultRegistry.resolve_by_path()` performs the resolution; `UnifiedIngestionService`
applies it at the ingestion **mechanism** — both the per-file `ingest_file` seams *and*
the `ingest_directory` bulk-upsert seam (activity domains are bulk-ingested and never
pass through `ingest_file`). The single-file door also resolves its fail-closed **wall**
from the file's descriptor, so a content `je_*` staging file is rejected consistently
with the directory/reconciler paths. Consequence: **the same file ingested via any
surface — the `/ingest` dashboard, the `VaultReconciler`, or a bare
script — yields the same owner.** The reconciler still passes `user_uid=`/`allowlist=`
explicitly; that is belt-and-suspenders — a by-path caller reproduces the same result.

A directory scan attributes one owner + one wall to the whole batch, so it must belong
to a single vault: a scan of an ancestor directory that **nests** another vault's root is
rejected fail-closed (`VaultRegistry.nested_vault_roots`) rather than sweeping and
mis-attributing the nested vault. Sibling / coincident roots do not trip this.

A file **cannot spoof ownership**: under descriptor-governed ingestion the resolved owner
is *authoritative* and overrides any `user_uid:` written into the frontmatter/YAML (so a
personal-vault task claiming `user_uid: someone_else` is still owned by the vault's owner).

> Stage-1 boundary (accepted): pointing the dashboard at *another* user's personal vault
> stamps the acting admin as owner — the shared personal descriptor is a template and the
> path alone cannot name the real user. The per-user local-agent topology (ADR-070 north
> star) is the future fix.

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

### ingest_vault(path, subdirs=None, *, user_uid=None)

Ingest an Obsidian vault. Optionally limit to specific subdirectories.
`user_uid` is an **acting-user hint**, not an owner override: the real owner of
each USER_OWNED entity is resolved from the vault descriptor governing its path
(see [Ownership](#ownership-descriptor-by-path-not-caller-identity-adr-070)). The
API routes pass `current_user.uid`, but for content-vault paths that hint is
ignored in favour of the content acts-as account.

```python
stats = await service.ingest_vault(
    Path("/home/mike/0bsidian/skuel"),
    subdirs=["docs", "curriculum"],  # Optional: limit to these folders
    user_uid=UserUID("user_mike"),   # Optional: override default user
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

Best for text-heavy content like PathSteps. **Requires an explicit `type` field in frontmatter** — markdown files without a `type` field are rejected:

```yaml
# /vault/ps_machine-learning.md
---
type: PathStep
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

15 entity configs — 13 of the 25 EntityTypes plus the two NonKuDomain types
(FINANCE, GROUP). Configuration in `config.py`. A `name:` field satisfies a
`title` requirement (the preparer renames `name` → `title`); `title`/`name`
also auto-fall back to the filename.

| Entity Type | Prefix | Neo4j Labels | Required Fields | Example File |
|-------------|--------|-------------|-----------------|--------------|
| `exercise` | `ex.` | `:Entity:Exercise` | title, instructions | `exercise_know-yourself.yaml` |
| `ku` | `ku.` | `:Entity:Ku` | title | `ku.python-basics.md` |
| `ps` | `ps.` | `:Entity:PathStep` | title | `ps.learn-variables.md` |
| `lp` | `lp.` | `:Entity:LearningPath` | title | `lp.python-journey.yaml` |
| `task` | `task.` | `:Entity:Task` | title | `task.complete-exercise.yaml` |
| `goal` | `goal.` | `:Entity:Goal` | title | `goal.learn-python.yaml` |
| `habit` | `habit.` | `:Entity:Habit` | title | `habit.daily-practice.yaml` |
| `event` | `event.` | `:Entity:Event` | title | `event.workshop.yaml` |
| `choice` | `choice.` | `:Entity:Choice` | title | `choice.career-path.yaml` |
| `principle` | `principle.` | `:Entity:Principle` | title, statement | `principle.consistency.yaml` |
| `user_entry` | `ue.` | `:Entity:UserEntry` | title | `ue.journal-2026-06-12.yaml` |
| `interaction` | `ia.` | `:Entity:Interaction` | interaction_type, target_uid | `ia.viewed-ps.yaml` |
| `expense` | `expense.` | `:Expense` | description, amount | `expense.books.yaml` |
| `group` | `group.` | `:Group` | name | `group.class-of-2026.yaml` |
| `lifepath` | `lifepath.` | `:Entity:LifePath` | user_uid | `lifepath.vision.yaml` |

**Multi-label architecture:** All domain entities get both `:Entity` (universal base) and a domain-specific label (e.g., `:Task`). This enables cross-domain queries via `:Entity` and fast indexed queries via domain labels. Finance (`Expense`) is the exception — no `:Entity` base label.

**Indexes:** Domain indexes (UID, user_uid, status, date, composite) are created automatically at bootstrap via `Neo4jSchemaManager.sync_domain_indexes()`. See `scripts/indexes.cypher` for the reference list.

### Entity Type Detection

The service detects entity type from:
1. **Explicit `type` field** in YAML or markdown frontmatter (required — no silent defaults)

**No implicit defaults:** Markdown files without an explicit `type` field are rejected. YAML files require an explicit `type` field.

### UID Format Validation

Explicit UIDs in vault files are validated against the expected prefix for their entity type. A `type: PathStep` file with `uid: ku.something` is rejected — the prefix must match (e.g., `ps.` for PathSteps, `ku.` for Kus, `ex.` for Exercises). If no UID is declared, one is auto-generated from the filename with the correct prefix.

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
| `requires` | REQUIRES_KNOWLEDGE | Entity | PathStep |
| `enables` | ENABLES_KNOWLEDGE | Entity | PathStep |
| `related` | RELATED_TO | Entity | PathStep |
| `depends_on` | DEPENDS_ON | Task | Task |
| `applies_knowledge` | APPLIES_KNOWLEDGE | Entity | Task, Event |
| `requires_knowledge` | REQUIRES_KNOWLEDGE | Entity | Goal |
| `reinforces_knowledge` | REINFORCES_KNOWLEDGE | Entity | Habit |
| `fulfills_goal` | FULFILLS_GOAL | Goal | Task |
| `reinforces_habit` | SUPPORTS_HABIT | Entity | Task |
| `supports_goal` | SUPPORTS_GOAL | Goal | Habit |
| `embodies_principle` | EMBODIES_PRINCIPLE | Principle | Habit |
| `prerequisite_habits` | REQUIRES_PREREQUISITE_HABIT | Entity | Habit |
| `aligned_with_principle` | GUIDED_BY_PRINCIPLE | Principle | Goal |
| `parent_goal` | SUBGOAL_OF | Goal | Goal |
| `sub_goals` | SUBGOAL_OF (incoming) | Goal | Goal |
| `supporting_habits` | SUPPORTS_GOAL (incoming) | Entity | Goal |
| `informed_by_knowledge` | INFORMED_BY_KNOWLEDGE | Entity | Choice |
| `guided_by_principle` | INFORMED_BY_PRINCIPLE | Principle | Choice |
| `affects_goal` | AFFECTS_GOAL | Goal | Choice |
| `impacts_habit` | IMPACTS_HABIT | Entity | Choice |
| `contributes_to_goal` | CONTRIBUTES_TO_GOAL | Goal | Event |
| `reinforces_habit` | REINFORCES_HABIT | Entity | Event |
| `executes_task` | EXECUTES_TASK | Task | Event |
| `grounded_in_knowledge` | GROUNDED_IN_KNOWLEDGE | Entity | Principle |
| `guides_goal` | GUIDES_GOAL | Goal | Principle |
| `inspires_habit` | INSPIRES_HABIT | Entity | Principle |
| `contains_steps` | HAS_STEP | Entity | LP |
| `organizes` | ORGANIZES | Entity | PathStep |

#### Path Step Fields (12 total)

| YAML Field | Relationship Type | Target | Direction |
|-----------|-------------------|--------|-----------|
| `knowledge_uids` | CONTAINS_KNOWLEDGE | Entity | outgoing |
| `trains_ku_uids` | TRAINS_KU | Ku | outgoing |
| `prerequisite_step_uids` | REQUIRES_STEP | Entity | outgoing |
| `prerequisite_knowledge_uids` | REQUIRES_KNOWLEDGE | Entity | outgoing |
| `principle_uids` | GUIDED_BY_PRINCIPLE | Principle | outgoing |
| `choice_uids` | INFORMS_CHOICE | Entity | outgoing |
| `habit_uids` | BUILDS_HABIT | Entity | outgoing |
| `task_uids` | ASSIGNS_TASK | Task | outgoing |
| `event_template_uids` | SCHEDULES_EVENT | Event | outgoing |
| `learning_path_uids` | HAS_STEP | Entity | incoming |

> **Note:** Single-value fields `learning_path_uid` and `knowledge_uid` are auto-converted
> to their list equivalents (`learning_path_uids`, `knowledge_uids`) during preparation.

> **Note:** Relationship types are unified with the Relationship Registry.
> Ingestion config is derived from the registry via `generate_ingestion_relationship_config()`.
> See `core/services/ingestion/config.py` for the full mapping.

---

## Edge Ingestion (Standalone Relationships)

Edge files declare relationships between existing entities. They create graph edges, not nodes.

```yaml
type: Edge
from: ku:caffeine
to: ku:tinnitus-buzzing
relationship: EXACERBATED_BY
confidence: 0.8
polarity: -1
temporality: hours
source: self_observation
evidence: "Buzzing consistently worse 30-60 min after coffee"
tags: [health, nervous-system]
```

**How it works:**
- `is_edge_type()` detects `type: Edge` before entity type detection
- `validate_edge_data()` validates required fields and value constraints
- `prepare_edge_data()` normalizes UIDs (colon→dot) and extracts evidence properties
- `ingest_edge()` uses `MERGE (a)-[r:REL_TYPE]->(b) SET r += $props` (idempotent)
- In batch mode, edges are processed AFTER entities (so referenced nodes exist)

**Validation rules:**
- Required: `from`, `to`, `relationship` (must be valid `RelationshipName`)
- `confidence`: 0.0–1.0
- `polarity`: -1, 0, or 1
- `temporality`: minutes, hours, days, chronic
- `source`: self_observation, research, teacher, clinical

**Evidence relationship types:** `EXACERBATED_BY`, `REDUCED_BY`, `CORRELATED_WITH`, `CAUSES`, `PRECEDES`

---

## API Endpoints

| Endpoint | Method | Request Body | Response |
|----------|--------|--------------|----------|
| `/api/ingest/file` | POST | `{"file_path": "/path/to/file"}` | Entity dict |
| `/api/ingest/vault` | POST | `{"vault_path": "/vault", "subdirs": ["docs"]}` | IngestionStats (full mode) |
| `/api/ingest/bundle` | POST | `{"bundle_path": "/bundle"}` | BundleStats |
| `/ingest` | GET | - | Dashboard UI |

All endpoints are admin-only and CSRF-protected — a scripted caller needs an authenticated
session plus the `X-CSRF-Token` header.

**Whole-vault incremental sync goes through the reconciler, not a raw ingest door** (ADR-070
Decision 9). The arbitrary-path `/api/ingest/directory` door was removed; ingest the content
vault via `POST /api/vault/sync/content` (admin) or the in-process
`scripts/vault_bridge_sync.py --vault content` (both run `VaultReconciler.sync` in `smart`
mode). Personal vaults sync via `POST /api/vault/sync`.

**Deletion propagation (incremental/smart only):** vault file deleted → graph entity deleted.
After processing, tracked files under the directory that no longer exist on disk have their
entity + content subtree (Content/ContentChunk/ContentMetadata) + IngestionMetadata removed
(`IngestionTracker.reconcile_deletions`). Edge YAMLs propagate too — tracked with the
relationship identity (`edge:{from}|{REL}|{to}`) in the uid slot, so deleting the file deletes
exactly that relationship (and unchanged edge files skip on later runs). Moved/renamed files
lose only the stale tracking row. Reconciliation honors the run's `pattern` — a `*.md`-scoped
run never deletes tracked YAML entities. The mass-deletion safety valve is GLOBAL: deletion is
refused only when NO tracked file under the directory exists at all (unmounted vault, sync
wipe); if any tracked file survives — in or out of scope — the vault is demonstrably mounted
and in-scope deletions propagate. Response fields: `entities_deleted`, `edges_deleted`,
`stale_metadata_removed`.

### Example: Human-initiated incremental vault sync

Ingestion is human-initiated per event — there is no background watcher (ADR-070
Decision 9). Sync when you decide to:

```bash
# One-shot content-vault sync (in-process reconciler, smart mode)
./dev vault-sync --vault content

# One-shot personal-vault sync as a given user
./dev vault-sync --user <user_uid>
```

Or from the UI: the personal-vault "Sync from Obsidian" button, or the admin
ingestion dashboard's "Sync content vault" button (`POST /api/vault/sync/content`).

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
    edges_created: int          # Standalone edge files ingested
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
- **Domain architecture:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`
