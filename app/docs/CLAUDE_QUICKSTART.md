---
title: Claude Quick Start Guide
created: 2025-12-04
updated: 2026-05-16
status: current
category: guides
tags: [claude, quickstart, onboarding, ai-assistant]
related: [README.md, INDEX.md]
---

# Claude Quick Start Guide

**For:** New Claude instances working on SKUEL
**Read time:** 5 minutes
**Last Updated:** 2025-12-04

---

## TL;DR - The Essentials

1. **Read CLAUDE.md first** - `/CLAUDE.md` (~1000 lines of project rules)
2. **Entity types + 5 systems** - All flow toward LifePath
3. **6 Activity Domains** use `UnifiedRelationshipService` - Tasks, Goals, Habits, Events, Choices, Principles
4. **Result[T] everywhere** - Use `.is_error` not `.is_err`
5. **uv for everything** - `uv run python`, `uv run pytest`

---

## Architecture at a Glance

### Entity Types

```
Activity (6)             Curriculum (4)      Content/Processing    Other
├── Tasks                ├── Ku              ├── Submission        ├── Resource
├── Goals                ├── PathStep        ├── Journal           ├── Finance
├── Habits               ├── LearningPath    ├── ActivityReport    ├── Groups
├── Events               └── Exercise        └── EntryReport    ├── MOC (emergent)
├── Choices                                                        └── LifePath
└── Principles
```

### Key Files to Know

| What | Where |
|------|-------|
| Project rules | `/CLAUDE.md` |
| Domain enums | `/core/models/enums/` (EntityType, NonKuDomain, EntityStatus, Priority) |
| Relationship configs | `/core/models/relationship_registry.py` |
| MEGA-QUERY | `/core/services/user/user_context_queries.py` |
| Service bootstrap | `/services_bootstrap/` |

---

## Current Patterns (December 2025)

### UnifiedRelationshipService (6 Activity Domains)

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

service = UnifiedRelationshipService(backend, graph_intel, TASKS_CONFIG)
await service.get_related_uids("knowledge", "task:123")
```

**Configs:** `TASKS_CONFIG`, `GOAPS_CONFIG`, `HABITS_CONFIG`, `EVENTS_CONFIG`, `CHOICES_CONFIG`, `PRINCIPLES_CONFIG` (from `core.models.relationship_registry`)

### Error Handling

```python
# Internal: Always Result[T]
async def get_task(self, uid: str) -> Result[Task]:
    if not uid:
        return Errors.validation("UID required")
    ...
    return Result.ok(task)

# Propagate errors with Result.fail(result)
if result.is_error:
    return Result.fail(result)
```

### Three-Tier Type System

| Tier | Type | Purpose |
|------|------|---------|
| External | Pydantic | HTTP validation |
| Transfer | DTO | Mutable, between layers |
| Core | Domain Model | Frozen, business logic |

---

## What NOT to Do

1. **Don't use `.is_err`** - Use `.is_error` (SKU001 linter rule)
2. **Don't use `hasattr()`** - Use proper protocols (SKU002)
3. **Don't use lambda** - Named functions only (SKU004)
4. **Don't create string error messages** - Use `Errors` factory (SKU003)
5. **Don't force Finance into Activity Domain patterns** - It's standalone
6. **Don't mix up 6 vs 7 Activity Domains** - Finance is NOT one of the 6

---

## Reading Priority

### Must Read (Before Any Work)

1. `/CLAUDE.md` - Project rules and patterns
2. This file - Quick orientation

### Read When Relevant

| Task | Read |
|------|------|
| Adding relationships | `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md` |
| Writing queries | `docs/patterns/query_architecture.md` |
| Understanding UserContext | `docs/architecture/UNIFIED_USER_ARCHITECTURE.md` |
| Working with DSL | `docs/dsl/DSL_SPECIFICATION.md` |
| Creating services | `docs/reference/templates/service_creation.md` |

### Reference (Look Up As Needed)

- `docs/architecture/ENUM_ARCHITECTURE.md` - Enum landscape (87 enums, 17 files)
- `docs/INDEX.md` - Curated document index (hand-maintained, not a full listing — an absent entry does NOT mean an absent doc)

---

## Common Tasks

### Find a Service

```bash
# Services are in /core/services/{domain}/
ls core/services/tasks/
# tasks_core_service.py, tasks_search_service.py, etc.
```

### Find Domain Config

```python
from core.models.relationship_registry import DOMAIN_CONFIGS, TASKS_CONFIG
from core.models.enums import Domain

config = DOMAIN_CONFIGS[Domain.TASKS]  # or use TASKS_CONFIG directly
```

### Check Relationship Names

```python
from core.models.relationship_names import RelationshipName

# All relationships are in this enum
RelationshipName.APPLIES_KNOWLEDGE
RelationshipName.FULFILLS_GOAL
```

### Run Tests

```bash
uv run pytest tests/integration/test_*.py -v
uv run pytest -k "test_task" -v  # Filter by name
```

---

## Architecture Decision Records (ADRs)

Recent decisions that affect current work:

| ADR | What It Decided |
|-----|-----------------|
| ADR-016 | Context builder split into 4 modules |
| ADR-015 | MEGA-QUERY fetches all user context in one query |
| ADR-014 | Unified ingestion for markdown/YAML files |
| ADR-013 | KU UIDs are flat (`ku.filename`), not hierarchical |

See `docs/decisions/` for all 16 ADRs.

---

## Quick Debugging

### Import Errors

```bash
# Check if file compiles
uv run python -m py_compile core/services/tasks/tasks_core_service.py
```

### Type Errors

```bash
# Run mypy on specific file
uv run mypy core/services/tasks/tasks_core_service.py

# Run mypy across the whole repo (the CI check)
uv run mypy .
```

**Zero is the enforced baseline.** Two gates catch regressions before you
get a chance to forget:

- **Pre-commit hook** runs `mypy --follow-imports=silent` on staged `.py`
  files (~10s warm). Bypass with `SKUEL_SKIP_MYPY=1 git commit ...` for
  WIP refactors. See `app/scripts/git-hooks/README.md`.
- **CI** (`.github/workflows/quality.yml`) runs the full
  `uv run mypy .` on every push/PR to `main` and `develop`. Posts a PR
  comment with the failing output.

### Linter Issues

```bash
./dev quality      # Run all checks (Ruff + SKUEL linter + Cypher + MyPy)
./dev quality-fix  # Auto-fix issues
```

---

## Questions?

- **Architecture questions:** Check `docs/architecture/`
- **Pattern questions:** Check `docs/patterns/`
- **"How do I...?":** Check `docs/guides/`
- **"What's the enum for...?":** Check `docs/architecture/ENUM_ARCHITECTURE.md`

---

**Welcome to SKUEL. Read CLAUDE.md, follow the patterns, and trust the types.**
