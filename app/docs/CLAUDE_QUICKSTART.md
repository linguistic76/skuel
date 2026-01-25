---
title: Claude Quick Start Guide
created: 2025-12-04
updated: 2025-12-04
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

1. **Read CLAUDE.md first** - `/home/mike/skuel/app/CLAUDE.md` (~1000 lines of project rules)
2. **14 domains + 5 systems** - All flow toward LifePath (domain #14)
3. **6 Activity Domains** use `UnifiedRelationshipService` - Tasks, Goals, Habits, Events, Choices, Principles
4. **Result[T] everywhere** - Use `.is_error` not `.is_err`
5. **Poetry for everything** - `poetry run python`, `poetry run pytest`

---

## Architecture at a Glance

### The 14 Domains

```
Activity Domains (6)     Curriculum (3)      Content/Org (3)   Destination (1)
├── Tasks                ├── KU (point)      ├── Journals      └── LifePath
├── Goals                ├── LS (edge)       ├── Assignments
├── Habits               └── LP (path)       └── MOC (graph)
├── Events
├── Choices
└── Principles

+ Finance (standalone, NOT an Activity Domain)
```

### Key Files to Know

| What | Where |
|------|-------|
| Project rules | `/home/mike/skuel/app/CLAUDE.md` |
| Domain enums | `/core/models/shared_enums.py` (EntityType, Domain, Priority) |
| Relationship configs | `/core/services/relationships/domain_configs.py` |
| MEGA-QUERY | `/core/services/user/user_context_queries.py` |
| Service bootstrap | `/core/utils/services_bootstrap.py` |

---

## Current Patterns (December 2025)

### UnifiedRelationshipService (6 Activity Domains)

```python
from core.services.relationships import UnifiedRelationshipService, TASK_CONFIG

service = UnifiedRelationshipService(backend, graph_intel, TASK_CONFIG)
await service.get_related_uids("knowledge", "task:123")
```

**Configs:** `TASK_CONFIG`, `GOAL_CONFIG`, `HABIT_CONFIG`, `EVENT_CONFIG`, `CHOICE_CONFIG`, `PRINCIPLE_CONFIG`

### Error Handling

```python
# Internal: Always Result[T]
async def get_task(self, uid: str) -> Result[Task]:
    if not uid:
        return Errors.validation("UID required")
    ...
    return Result.ok(task)

# Check errors with .is_error (NOT .is_err)
if result.is_error:
    return result.expect_error()
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

1. `/home/mike/skuel/app/CLAUDE.md` - Project rules and patterns
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

- `docs/reference/ENUM_REFERENCE.md` - All enums (10,000+ lines)
- `docs/INDEX.md` - Complete document listing

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
from core.services.relationships import get_config_for_domain, ACTIVITY_DOMAIN_CONFIGS
from core.models.shared_enums import Domain

config = get_config_for_domain(Domain.TASKS)
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
poetry run pytest tests/integration/test_*.py -v
poetry run pytest -k "test_task" -v  # Filter by name
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
poetry run python -m py_compile core/services/tasks/tasks_core_service.py
```

### Type Errors

```bash
# Run mypy on specific file
poetry run mypy core/services/tasks/tasks_core_service.py
```

### Linter Issues

```bash
./dev quality      # Run all checks
./dev quality-fix  # Auto-fix issues
```

---

## Questions?

- **Architecture questions:** Check `docs/architecture/`
- **Pattern questions:** Check `docs/patterns/`
- **"How do I...?":** Check `docs/guides/`
- **"What's the enum for...?":** Check `docs/reference/ENUM_REFERENCE.md`

---

**Welcome to SKUEL. Read CLAUDE.md, follow the patterns, and trust the types.**
