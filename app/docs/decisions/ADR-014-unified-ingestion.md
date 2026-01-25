---
title: ADR-014: Unified Content Ingestion Service
updated: 2026-01-04
status: accepted
category: decisions
tags: [adr, decisions, ingestion, markdown, yaml, unified, modular]
related: [ADR-013-ku-uid-flat-identity.md, ADR-016-context-builder-decomposition.md]
---

# ADR-014: Unified Content Ingestion Service

**Status:** Accepted

**Date:** 2025-12-03

**Decision Type:** Architecture/Service Design

**Related ADRs:**
- ADR-013: KU UID Flat Identity Design

---

## Context

**What is the issue we're facing?**

SKUEL had two separate content ingestion services:

1. **MarkdownSyncService** (`markdown_sync_service.py`)
   - Production-wired in `services_bootstrap.py`
   - Handles `.md` files only
   - Supports 2 entity types: KU, MOC
   - Uses dot notation UIDs (`ku.filename`)
   - Uses BulkIngestionEngine for batch performance

2. **YamlIngestionService** (`yaml_ingestion_service.py`)
   - NOT production-wired (examples only)
   - Handles `.yaml`/`.yml` files only
   - Supports 10 entity types (all Activity + Curriculum)
   - Uses colon notation UIDs (`ku:filename`)
   - Per-file operations (slower)

**Problems:**
- Two code paths for similar functionality
- UID format inconsistency (dot vs colon notation)
- Markdown service missing many entity types
- YAML service missing batch performance
- No unified API for content ingestion

**Philosophical question:**
Should we have specialized services for each format, or one unified service?

SKUEL philosophy: "One path forward." A single, well-designed service is better than multiple specialized ones.

---

## Decision

**Create UnifiedIngestionService that merges both services.**

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Format Support | Both MD + YAML | First-class citizens for different use cases |
| Architecture | Single unified service | One path forward, reduce maintenance |
| UID Format | Dot notation (`ku.filename`) | Matches ADR-013, shorter, in production |
| Performance | BulkIngestionEngine | Batch operations (10-100x faster) |
| Entity Types | All 14 | Full domain coverage |

### UID Normalization

All UIDs normalized to dot notation:
```
ku:breath-awareness  →  ku.breath-awareness
task:log-sessions    →  task.log-sessions
```

### Service Interface

```python
class UnifiedIngestionService:
    async def ingest_file(path: Path) -> Result[dict[str, Any]]
    async def ingest_directory(path: Path, pattern: str = "*") -> Result[IngestionStats]
    async def ingest_vault(path: Path, subdirs: list[str] | None) -> Result[IngestionStats]
    async def ingest_bundle(path: Path) -> Result[BundleStats]
```

### Architecture

```
UnifiedIngestionService
├── Format Detection (MD vs YAML)
├── Entity Type Routing (14 types)
├── UID Generation (dot notation)
├── Relationship Extraction (graph-native)
└── BulkIngestionEngine (batch persistence)
```

---

## Alternatives Considered

### Alternative 1: Keep Both Services Separate

**Description:** Maintain MarkdownSyncService and YamlIngestionService independently.

**Pros:**
- No migration needed
- Clear separation of concerns

**Cons:**
- Two code paths to maintain
- UID format inconsistency persists
- Missing features in each service

**Why rejected:** Violates "one path forward" philosophy. Maintenance burden.

### Alternative 2: Extend MarkdownSyncService Only

**Description:** Add YAML support to MarkdownSyncService.

**Pros:**
- Leverage existing production code
- Already uses BulkIngestionEngine

**Cons:**
- Name becomes misleading
- Still missing most entity types
- Would require significant refactoring

**Why rejected:** Service name implies markdown-only. Better to create clean new service.

### Alternative 3: Extend YamlIngestionService Only

**Description:** Add markdown support and batch operations to YamlIngestionService.

**Pros:**
- Already supports 10 entity types
- Has per-entity converters

**Cons:**
- Not production-wired
- Missing BulkIngestionEngine
- Uses colon notation (non-standard)

**Why rejected:** Would require retrofitting batch operations. Cleaner to build new.

---

## Consequences

### Positive Consequences
- Single service for all content ingestion
- Consistent dot notation UIDs
- Full 14 entity type support
- Batch performance for all operations
- Unified API (`/api/ingest/*`)
- Dashboard UI for content creators

### Negative Consequences
- Migration needed for existing workflows
- Learning curve for new API

### Migration Path (One Path Forward)

**SKUEL does not maintain backward compatibility.** Old services were removed entirely:

```python
# ❌ OLD - Removed entirely (no deprecation period)
await markdown_sync.sync_file(path)
await yaml_ingestion.ingest_task(path)

# ✅ NEW - One path forward
await unified_ingestion.ingest_file(path)
```

### Timeline
- **2025-12-03:** UnifiedIngestionService created (monolithic)
- **2026-01-04:** Decomposed into modular package, old file deleted

---

## Implementation Details

### Code Location (January 2026 - Modular Package)

The service was decomposed from a 1,916-line monolith into a modular package following the ADR-016 pattern (UserContextBuilder decomposition).

**Package Structure:**
```
core/services/ingestion/           # THE path (one way forward)
├── __init__.py                    # Public API exports (~89 lines)
├── unified_ingestion_service.py   # Orchestration (~370 lines)
├── config.py                      # Entity configs + constants (~267 lines)
├── types.py                       # Data classes (~142 lines)
├── parser.py                      # MD/YAML parsing (~216 lines)
├── detector.py                    # Format/type detection (~118 lines)
├── preparer.py                    # Data preparation (~151 lines)
├── validator.py                   # Validation pipeline (~423 lines)
└── batch.py                       # Concurrent operations (~627 lines)
```

**Import (One Path Forward):**
```python
from core.services.ingestion import UnifiedIngestionService
```

**Related Files:**

| Component | File |
|-----------|------|
| Package | `/core/services/ingestion/` |
| Routes | `/adapters/inbound/ingestion_routes.py` |
| Bootstrap | `/core/utils/services_bootstrap.py` |

### Entity Configuration

Each entity type has configuration in `ENTITY_CONFIGS`:

```python
ENTITY_CONFIGS: dict[str, EntityIngestionConfig] = {
    "ku": EntityIngestionConfig(
        entity_label="Ku",
        uid_prefix="ku",
        required_fields=("title", "content"),
        relationship_config={
            "connections.requires": {"rel_type": "PREREQUISITE", ...},
            "connections.enables": {"rel_type": "ENABLES", ...},
        },
    ),
    # ... 13 more entity types
}
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ingest/file` | POST | Single file ingestion |
| `/api/ingest/directory` | POST | Directory batch ingestion |
| `/api/ingest/vault` | POST | Obsidian vault sync |
| `/api/ingest/bundle` | POST | Manifest-driven bundle |
| `/ingest` | GET | Dashboard UI |

---

## Testing Strategy

1. **Unit Tests:** Format detection, UID normalization, entity routing
2. **Integration Tests:** Full flow from file to Neo4j
3. **Performance Tests:** Batch operation benchmarks

---

## Documentation

### Updated Files
- `/CLAUDE.md` - Added Unified Ingestion section
- `/docs/decisions/ADR-014-unified-ingestion.md` - This document

### Related Documentation
- **Implementation guide:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` - How to use the ingestion service
- ADR-013: KU UID Flat Identity Design
- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-03 | Claude | Initial decision - monolithic service | 1.0 |
| 2026-01-04 | Claude | Decomposed into modular package (ADR-016 pattern) | 2.0 |

---

## Appendix

### Content Creator Workflow

**For markdown content:**
```yaml
# /docs/stories/machine-learning.md
---
title: Machine Learning
domain: tech
tags: [ml, ai]
---

Your content here...
```

**For YAML content:**
```yaml
# /curriculum/tasks/log-sessions.yaml
type: task
uid: task.log-sessions
title: Log First 5 Sessions
priority: high
connections:
  applies_knowledge:
    - ku.meditation-basics
```

**Ingest via API:**
```bash
curl -X POST http://localhost:5001/api/ingest/file \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/docs/stories/machine-learning.md"}'
```

**Or use the dashboard:**
Navigate to `/ingest` for the visual interface.
