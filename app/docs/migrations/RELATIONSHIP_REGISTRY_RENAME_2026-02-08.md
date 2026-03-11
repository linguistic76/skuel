---
title: Relationship Registry Rename - _UNIFIED to _CONFIG
date: 2026-02-08
category: migrations
tags: [naming, refactor, one-path-forward]
---

# Relationship Registry Rename: `_UNIFIED` → `_CONFIG`

**Date:** 2026-02-08
**Scope:** Naming convention alignment with "One Path Forward" philosophy
**Impact:** Zero breaking changes (pure rename)

## Philosophy

The `_UNIFIED` suffix was historical baggage from when there were alternative relationship patterns. Under the "One Path Forward" philosophy, **unified is THE default mode** — there are no alternative patterns, so the suffix became redundant noise.

The `_CONFIG` suffix is more descriptive:
- `_UNIFIED` described the **pattern/approach** (unified vs some legacy approach)
- `_CONFIG` describes the **purpose** (configuration data)

## Changes

### Constants Renamed (11 total)

**Activity Domains (6):**
```python
# Before
TASKS_UNIFIED = DomainRelationshipConfig(...)
GOALS_UNIFIED = DomainRelationshipConfig(...)
HABITS_UNIFIED = DomainRelationshipConfig(...)
EVENTS_UNIFIED = DomainRelationshipConfig(...)
CHOICES_UNIFIED = DomainRelationshipConfig(...)
PRINCIPLES_UNIFIED = DomainRelationshipConfig(...)

# After
TASKS_CONFIG = DomainRelationshipConfig(...)
GOALS_CONFIG = DomainRelationshipConfig(...)
HABITS_CONFIG = DomainRelationshipConfig(...)
EVENTS_CONFIG = DomainRelationshipConfig(...)
CHOICES_CONFIG = DomainRelationshipConfig(...)
PRINCIPLES_CONFIG = DomainRelationshipConfig(...)
```

**Curriculum Domains (3):**
```python
# Before
KU_UNIFIED = DomainRelationshipConfig(...)
LS_UNIFIED = DomainRelationshipConfig(...)
LP_UNIFIED = DomainRelationshipConfig(...)

# After
KU_CONFIG = DomainRelationshipConfig(...)
LS_CONFIG = DomainRelationshipConfig(...)
LP_CONFIG = DomainRelationshipConfig(...)
```

**Identity Layer (2):**
```python
# Before
USER_UNIFIED = DomainRelationshipConfig(...)
PRINCIPLE_REFLECTION_UNIFIED = DomainRelationshipConfig(...)

# After
USER_CONFIG = DomainRelationshipConfig(...)
PRINCIPLE_REFLECTION_CONFIG = DomainRelationshipConfig(...)
```

### Registries Renamed (2)

```python
# Before
UNIFIED_REGISTRY: dict[Domain, DomainRelationshipConfig] = {...}
UNIFIED_REGISTRY_BY_LABEL: dict[str, DomainRelationshipConfig] = {...}

# After
DOMAIN_CONFIGS: dict[Domain, DomainRelationshipConfig] = {...}
LABEL_CONFIGS: dict[str, DomainRelationshipConfig] = {...}
```

**Rationale:** "Unified Registry" was redundant — it's just a registry of domain configs.

### Functions Renamed (2)

```python
# Before
def get_unified_config(domain: Domain) -> DomainRelationshipConfig | None:
def get_unified_config_by_label(entity_label: str) -> DomainRelationshipConfig | None:

# After
def get_domain_config(domain: Domain) -> DomainRelationshipConfig | None:
def get_config_by_label(entity_label: str) -> DomainRelationshipConfig | None:
```

## Migration Guide

### For Code

**Imports:**
```python
# Before
from core.models.relationship_registry import (
    TASKS_UNIFIED,
    GOALS_UNIFIED,
    KU_UNIFIED,
    UNIFIED_REGISTRY,
    UNIFIED_REGISTRY_BY_LABEL,
    get_unified_config,
    get_unified_config_by_label,
)

# After
from core.models.relationship_registry import (
    TASKS_CONFIG,
    GOALS_CONFIG,
    KU_CONFIG,
    DOMAIN_CONFIGS,
    LABEL_CONFIGS,
    get_domain_config,
    get_config_by_label,
)
```

**Usage:**
```python
# Before
service = UnifiedRelationshipService(backend=backend, config=TASKS_UNIFIED)
config = get_unified_config_by_label("Task")
all_configs = UNIFIED_REGISTRY_BY_LABEL

# After
service = UnifiedRelationshipService(backend=backend, config=TASKS_CONFIG)
config = get_config_by_label("Task")
all_configs = LABEL_CONFIGS
```

### For Documentation

- Replace `*_UNIFIED` with `*_CONFIG` in code examples
- Replace `UNIFIED_REGISTRY` with `DOMAIN_CONFIGS`
- Replace `UNIFIED_REGISTRY_BY_LABEL` with `LABEL_CONFIGS`
- Replace `get_unified_config` with `get_domain_config`
- Replace `get_unified_config_by_label` with `get_config_by_label`

## Files Updated

**Core (14 files):**
- `core/models/relationship_registry.py` - Constant definitions, registries, functions
- `core/utils/activity_domain_config.py` - 6 imports + 6 references
- `core/utils/curriculum_domain_config.py` - 3 imports + 5 references
- `core/services/relationships/__init__.py` - Docstring example
- `core/services/relationships/*.py` - All relationship service files
- `core/services/*_service.py` - Docstring references
- `core/services/*/` - Subdirectory service files

**Tests (2 files):**
- `tests/test_relationship_registry.py` - 29 tests
- `tests/unit/test_ingestion_relationship_config.py` - 7 tests

**Documentation (~20 files):**
- `docs/decisions/ADR-026-unified-relationship-registry.md`
- `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`
- Other ADRs, patterns, and skill documentation

## Verification

```bash
# No _UNIFIED references remaining (excluding memory files)
grep -r "_UNIFIED\|UNIFIED_REGISTRY" --include="*.py" --include="*.md" | \
  grep -v "CLAUDE.md\|MEMORY.md\|changelog" | wc -l
# Expected: 0

# All tests passing
uv run pytest tests/test_relationship_registry.py \
  tests/unit/test_ingestion_relationship_config.py -v
# Expected: 36 passed
```

## Impact Summary

- **Breaking changes:** None (pure rename, all references updated)
- **Performance impact:** None
- **Test coverage:** 100% (36 tests passing)
- **Documentation:** Fully updated
- **Lines changed:** ~250+ occurrences across ~36 files

## Related Documents

- **ADR-026:** Unified Relationship Registry (updated to reflect new names)
- **Memory:** Added entry documenting this rename
- **Philosophy:** Aligns with "One Path Forward" - no alternative patterns, so "unified" is redundant

## Historical Context

The `_UNIFIED` suffix originated from ADR-026 (January 2026) when the relationship registry was created to eliminate a dual-source problem. At the time, "unified" distinguished the new single-source pattern from the legacy dual-source approach.

As of February 2026, the legacy approach is fully removed. Under "One Path Forward," only one pattern exists — making "unified" redundant. The `_CONFIG` suffix is more descriptive of what these constants actually are: configuration data.
