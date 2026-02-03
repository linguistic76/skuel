# UI Factory Signature Standardization

**Date:** 2026-02-03
**Status:** ✅ Complete
**Impact:** Low (signature-only changes, no behavioral changes)

## Overview

Standardized all activity domain UI factory signatures to consistently accept a `services` container parameter, improving maintainability and API consistency.

## Problem

UI factory functions across activity domains had inconsistent parameter signatures:

| Domain | Before | Issue |
|--------|--------|-------|
| **Tasks** | `(_app, rt, tasks_service, services=None)` | ✅ Already correct |
| **Goals** | `(_app, rt, goals_service)` | ❌ Missing `services` parameter |
| **Habits** | `(_app, rt, habits_service, goals_service=None)` | ❌ Hardcoded `goals_service` instead of generic container |
| **Choices** | `(_app, rt, choices_service)` | ❌ Missing `services` parameter |
| **Principles** | `(_app, rt, principles_service)` | ❌ Missing `services` parameter |

This inconsistency made the API harder to understand and violated DRY principles.

## Solution

All UI factory signatures now follow the standard pattern:

```python
def create_{domain}_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    {domain}_service: {Domain}FacadeProtocol,
    services: Any = None,
) -> list:
    """
    Args:
        _app: FastHTML app instance
        rt: Route decorator
        {domain}_service: Domain service instance
        services: Full services container (unused, kept for API compatibility)
    """
```

## Changes Made

### 1. Goals UI (`adapters/inbound/goals_ui.py`)
- **Added:** `services: Any = None` parameter
- **Updated:** Docstring with parameter documentation

### 2. Habits UI (`adapters/inbound/habits_ui.py`)
- **Changed:** `goals_service=None` → `services: Any = None`
- **Updated:** Docstring (removed `goals_service` reference)
- **Note:** `goals_service` was never used internally, so no functional changes

### 3. Habits Routes Config (`adapters/inbound/habits_routes.py`)
- **Removed:** `ui_related_services` configuration (now unnecessary)
- **Kept:** `api_related_services` (still needed for API routes)

### 4. Choices UI (`adapters/inbound/choice_ui.py`)
- **Added:** `services: Any = None` parameter
- **Updated:** Docstring with parameter documentation

### 5. Principles UI (`adapters/inbound/principles_ui.py`)
- **Added:** `services: Any = None` parameter
- **Updated:** Docstring with parameter documentation

## Benefits

1. **Consistency:** All 5 activity domain UI factories now have identical signature patterns
2. **Maintainability:** Easier to understand and modify UI route registration
3. **Extensibility:** Future UI routes can easily access related services via the container
4. **DRY Compliance:** Eliminates the hardcoded `goals_service` parameter special case

## Testing

- ✅ Ruff checks passed (no import errors)
- ✅ MyPy type checks passed
- ✅ No behavioral changes (parameters are optional with None defaults)

## Files Modified

```
adapters/inbound/
├── goals_ui.py        (signature + docstring)
├── habits_ui.py       (signature + docstring)
├── habits_routes.py   (removed ui_related_services)
├── choice_ui.py       (signature + docstring)
└── principles_ui.py   (signature + docstring)
```

## Migration Notes

**No migration required.** This is a signature-only change with backward compatibility:
- Existing calls without `services` parameter continue to work (defaults to `None`)
- The `register_domain_routes` function already handles optional parameters correctly
- No UI route implementations were changed (all ignore the `services` parameter currently)

## Future Enhancement

If a UI route needs to access related services in the future, it can now extract them from the `services` container:

```python
def create_example_ui_routes(_app, rt, example_service, services=None):
    # Access related services if needed
    if services:
        user_service = services.user_service
        goals_service = services.goals
        # Use as needed...
```

This is cleaner than adding domain-specific parameters and maintains consistency across all domains.
