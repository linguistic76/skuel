# KU Route Naming Standardization

**Date:** 2026-02-02
**Type:** Refactoring
**Impact:** Breaking changes to URLs and imports
**Migration Time:** N/A (no backward compatibility)

## Summary

Renamed all `knowledge_*` route files to `ku_*` to align with canonical naming conventions across the codebase.

## Motivation

The codebase had inconsistent naming for the Knowledge Unit domain:
- Service attribute: `services.ku` ✓
- Model directory: `/core/models/ku/` ✓
- Service files: `ku_*.py` ✓
- **Route files: `knowledge_*.py` ✗**
- **URL paths: `/knowledge/*` and `/api/knowledge/*` ✗**

Following the "One Path Forward" principle, all naming should use the canonical form `ku`.

## Changes Made

### File Renames (5 files)
1. `knowledge_routes.py` → `ku_routes.py`
2. `knowledge_api.py` → `ku_api.py`
3. `knowledge_ui.py` → `ku_ui.py`
4. `ui/patterns/ku_adaptive.py` → `ui/patterns/ku_adaptive.py`
5. `core/events/knowledge_events.py` → `core/events/ku_events.py`

### Route Configuration Updates
- Domain name: `"knowledge"` → `"ku"`
- Config object: `KNOWLEDGE_CONFIG` → `KU_CONFIG`
- Function names: `create_knowledge_routes()` → `create_ku_routes()`

### URL Path Changes
**API Routes:**
- `/api/knowledge/*` → `/api/ku/*`
- Examples:
  - `/api/knowledge/search` → `/api/ku/search`
  - `/api/knowledge/{uid}` → `/api/ku/{uid}`
  - `/api/knowledge/analytics/summary` → `/api/ku/analytics/summary`

**UI Routes:**
- `/knowledge/*` → `/ku/*`
- Examples:
  - `/knowledge` → `/ku`
  - `/knowledge/create` → `/ku/create`
  - `/knowledge/{uid}/details` → `/ku/{uid}/details`

### Code Updates
**Classes:**
- `KnowledgeUIComponents` → `KuUIComponents`
- `KnowledgeFilters` → `KuFilters`

**Functions:**
- `create_knowledge_api_routes()` → `create_ku_api_routes()`
- `create_knowledge_ui_routes()` → `create_ku_ui_routes()`
- `parse_knowledge_filters()` → `parse_ku_filters()`
- `render_knowledge_*()` → `render_ku_*()`

**Imports (8 files updated):**
```python
# Before
from core.events.knowledge_events import KnowledgeAppliedInTask

# After
from core.events.ku_events import KnowledgeAppliedInTask
```

Files updated:
- `core/events/__init__.py`
- `core/services/ku/ku_practice_service.py`
- `core/services/choices/choices_core_service.py`
- `core/services/habits/habits_learning_service.py`
- `core/services/tasks/tasks_core_service.py`
- `core/services/events_service.py`
- `services_bootstrap.py`
- `tests/integration/test_event_ku_practice_flow.py`

### Documentation Updates
Updated 15+ documentation files:
- `docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`
- `docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md`
- `docs/domains/ku.md`
- `docs/patterns/ROUTE_FACTORIES.md`
- `docs/patterns/OWNERSHIP_VERIFICATION.md`
- `docs/patterns/CLEAN_PATTERNS.md`
- `docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`
- `docs/architecture/knowledge_substance_philosophy.md`
- `docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md`
- `docs/architecture/UNIFIED_USER_ARCHITECTURE.md`
- `docs/development/GENAI_SETUP.md`
- `PHASE3_TASK3_TYPED_QUERY_PARAMS_COMPLETE.md`
- `PHASE3_TASK1_UNIVERSAL_VALIDATION_COMPLETE.md`

## Rationale

This change aligns with:
✓ Service attribute (`services.ku`)
✓ Canonical EntityType form (`KU`)
✓ Model directory (`/core/models/ku/`)
✓ Service files (`ku_*.py`)
✓ Phase 5 detail page URLs (`/ku/{uid}`)
✓ "One Path Forward" principle - no aliases, no backward compatibility

## Breaking Changes

⚠️ **URL Changes:** All bookmarks and external links to `/knowledge/*` and `/api/knowledge/*` will break.

**No backward compatibility** - SKUEL follows "One Path Forward" philosophy.

## Migration for External Consumers

If external systems consume SKUEL APIs:
1. Update all `/api/knowledge/*` references to `/api/ku/*`
2. No API behavior changes - only paths renamed

## Verification

```bash
# Verify imports
grep -r "from core.events.ku_events" core/services/ core/events/

# Verify route registration
grep "create_ku_routes" scripts/dev/bootstrap.py

# Check for missed references
grep -r "knowledge_routes\|knowledge_api\|knowledge_ui" --include="*.py" . --exclude-dir=__pycache__
```

## Related Documents
- ADR-013: KU UID Flat Identity
- `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`
- `/docs/domains/ku.md`
