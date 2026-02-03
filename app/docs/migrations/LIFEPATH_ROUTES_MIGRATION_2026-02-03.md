# LifePath Routes DomainRouteConfig Migration

**Date:** 2026-02-03
**Status:** ✅ Complete
**Impact:** 94.6% reduction in main routes file (589 → 32 lines)

## Summary

Successfully migrated `/adapters/inbound/lifepath_routes.py` to use the DomainRouteConfig pattern, splitting into 3 focused files:

| File | Lines | Purpose |
|------|-------|---------|
| `lifepath_routes.py` | 32 | Configuration factory (589 → 32 = 94.6% reduction) |
| `lifepath_api.py` | 121 | 4 JSON API routes |
| `lifepath_ui.py` | 501 | 5 UI routes + 7 helper functions |
| **Total** | **654** | Similar to original 589, but organized |

## Migration Details

### Files Created

1. **`lifepath_api.py`** (121 lines)
   - 4 JSON API routes extracted from lines 250-327
   - Factory: `create_lifepath_api_routes(app, rt, lifepath_service)`
   - Routes:
     - `GET /api/lifepath/status` → api_get_status()
     - `POST /api/lifepath/vision` → api_capture_vision()
     - `POST /api/lifepath/designate` → api_designate()
     - `GET /api/lifepath/alignment` → api_get_alignment()

2. **`lifepath_ui.py`** (501 lines)
   - 5 UI routes extracted from lines 86-244
   - 7 helper functions preserved from lines 337-589
   - Factory: `create_lifepath_ui_routes(_app, rt, lifepath_service, services=None)`
   - Routes:
     - `GET /lifepath` → lifepath_dashboard()
     - `GET /lifepath/vision` → vision_capture_page()
     - `POST /lifepath/vision` → process_vision_capture()
     - `POST /lifepath/designate` → designate_life_path()
     - `GET /lifepath/alignment` → alignment_dashboard()
   - Helpers:
     - `_lifepath_drawer_layout()` - Drawer wrapper
     - `_service_unavailable_page()` - Error state
     - `_error_page()` - Generic error
     - `_build_dashboard_content()` - Main dashboard
     - `_build_recommendations_page()` - LP recommendations
     - `_build_alignment_dashboard()` - 5-dimension view
     - `_build_daily_focus()` - Daily focus card

3. **`lifepath_routes.py`** (32 lines - replaced)
   - Configuration factory using DomainRouteConfig
   - Philosophy docstring preserved
   - Configuration:
     ```python
     LIFEPATH_CONFIG = DomainRouteConfig(
         domain_name="lifepath",
         primary_service_attr="lifepath",
         api_factory=create_lifepath_api_routes,
         ui_factory=create_lifepath_ui_routes,
         api_related_services={},
     )
     ```

### Files Unchanged

- `/scripts/dev/bootstrap.py` - Registration remains identical:
  ```python
  if services.lifepath:
      from adapters.inbound.lifepath_routes import create_lifepath_routes
      create_lifepath_routes(app, rt, services)
      logger.info("✅ LifePath routes registered (Vision→Action bridge)")
  ```

## Verification Results

### Import Tests
✅ All imports successful
- `create_lifepath_routes` function imports correctly
- `create_lifepath_api_routes` function imports correctly
- `create_lifepath_ui_routes` function imports correctly
- `LIFEPATH_CONFIG` object validates correctly

### Route Registration Tests
✅ All 9 routes registered correctly:
```
/api/lifepath/alignment -> api_get_alignment
/api/lifepath/designate methods=['POST'] -> api_designate
/api/lifepath/status -> api_get_status
/api/lifepath/vision methods=['POST'] -> api_capture_vision
/lifepath -> lifepath_dashboard
/lifepath/alignment -> alignment_dashboard
/lifepath/designate methods=['POST'] -> designate_life_path
/lifepath/vision -> vision_capture_page
/lifepath/vision methods=['POST'] -> process_vision_capture
```

### Code Quality
✅ Ruff linting passed (1 auto-fixable import order issue resolved)
✅ Type signatures verified
✅ Factory signatures match DomainRouteConfig interface

## Backward Compatibility

### Route Paths (100% Preserved)
All 9 routes remain at identical paths:
- UI routes: `/lifepath`, `/lifepath/vision`, `/lifepath/alignment`, `/lifepath/designate`
- API routes: `/api/lifepath/status`, `/api/lifepath/vision`, `/api/lifepath/designate`, `/api/lifepath/alignment`

### Response Formats (Unchanged)
- Status codes: 200 (success), 303 (redirect), 400 (validation), 503 (unavailable)
- JSON structures: Same format for all API responses
- HTML rendering: Same drawer layout, same components

### Service Access (Internal Change Only)
- Before: `lifepath_service = services.lifepath`
- After: `lifepath_service` (injected parameter)
- Impact: Zero external impact, internal implementation detail only

## Pattern Adoption

This migration brings LifePath routes to 23 of 36 route files (64% adoption).

**DomainRouteConfig Pattern Status:**
- Activity domains (6): ✅ tasks, goals, habits, events, choices, principles
- Standard domains (8): ✅ learning, knowledge, context, reports, finance, askesis, journal_projects, **lifepath**
- Phase 3 migrations (9): ✅ transcription, visualization, admin, auth, journals, system, ingestion, insights, nous

## Design Decisions

1. **Empty `api_related_services={}`**
   - LifePathService is self-contained
   - All dependencies accessed via facade (.core, .alignment, .vision, .intelligence)
   - No additional service injection needed

2. **Philosophy Preservation**
   - Domain #14 philosophy docstring maintained in main routes file
   - Additional philosophy context in UI routes file
   - Ensures domain purpose remains visible

3. **Helper Function Placement**
   - All 7 UI helpers moved to `lifepath_ui.py`
   - Keeps API routes pure (4 routes, no helpers)
   - UI file is self-contained with presentation logic

4. **Standard Factory Signatures**
   - API: `(app, rt, lifepath_service)` - minimal dependencies
   - UI: `(_app, rt, lifepath_service, services=None)` - 2026-02-03 standard
   - Main: `(app, rt, services, _sync_service=None)` - bootstrap compatibility

## Next Steps

Remaining route files for DomainRouteConfig migration:
- search_routes.py
- assignment_routes.py
- learning_step_routes.py
- And 10+ others

See `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` for migration guide.

## References

- Pattern documentation: `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`
- Migration summary: `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-02-03.md`
- LifePath architecture: `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`
