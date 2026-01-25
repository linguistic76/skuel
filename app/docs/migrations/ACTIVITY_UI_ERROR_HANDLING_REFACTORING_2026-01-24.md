# Activity Domain UI Error Handling Refactoring

**Date**: 2026-01-24
**Status**: Complete (5/5)
**Related Docs**:
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Pattern documentation
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling

## Objective

Refactor all 6 Activity domain UI routes to use consistent error-handling pattern with:
1. Typed query parameters (dataclasses)
2. Result[T] propagation from helpers
3. Visible error banners instead of empty lists
4. Structured logging with full context

## Motivation

**Before:** Silent failures - users saw empty lists when database was down, making debugging impossible.

**After:** Visible errors - users see clear error messages, logs contain full context (user_uid, error_type, message).

## Pattern Overview

### Type Structures

```python
from dataclasses import dataclass

@dataclass
class Filters:
    """Typed filters for list queries."""
    status: str
    sort_by: str

@dataclass
class CalendarParams:  # Only for calendar-enabled domains
    """Typed params for calendar view."""
    calendar_view: str
    current_date: date
```

### Helper Functions

```python
def parse_filters(request) -> Filters:
    """Extract filter parameters from request query params."""
    return Filters(
        status=request.query_params.get("filter_status", "default"),
        sort_by=request.query_params.get("sort_by", "default"),
    )

def render_error_banner(message: str) -> Div:
    """Render error banner for UI failures."""
    return Div(
        Div(
            P("⚠️ Error", cls="font-bold text-error"),
            P(message, cls="text-sm"),
            cls="alert alert-error",
        ),
        cls="mb-4",
    )
```

### Data Helpers Return Result[T]

```python
async def get_all_{domain}(user_uid: str) -> Result[list[Any]]:
    """Get all {domain} for user."""
    try:
        result = await {domain}_service.get_user_{domain}(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch {domain}: {result.error}")
            return result  # Propagate the error
        return Result.ok(result.value or [])
    except Exception as e:
        logger.error(
            "Error fetching all {domain}",
            extra={
                "user_uid": user_uid,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return Errors.system(f"Failed to fetch {domain}: {e}")
```

### Route Handlers Check Errors

```python
@rt("/{domain}")
async def {domain}_dashboard(request) -> Any:
    user_uid = require_authenticated_user(request)
    filters = parse_filters(request)

    filtered_result = await get_filtered_{domain}(user_uid, filters.status, filters.sort_by)

    # CHECK FOR ERRORS
    if filtered_result.is_error:
        error_content = Div(
            {Domain}ViewComponents.render_view_tabs(active_view=view),
            render_error_banner(f"Failed to load {domain}: {filtered_result.error}"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )
        return create_{domain}_page(error_content, request=request)

    entities, stats = filtered_result.value
    # ... render views ...
```

## Implementation Status

### ✅ Completed Domains

#### 1. Tasks (`tasks_ui.py`) - Reference Implementation
- **Date**: Prior to 2026-01-24
- **Features**: List + Calendar views
- **Status**: ✅ Complete, validated, formatted, linted

#### 2. Goals (`goals_ui.py`)
- **Date**: 2026-01-24
- **Features**: List + Create + Calendar views
- **Filter Fields**: `status` ("active", "completed", "paused", "all"), `sort_by` ("target_date", "priority", "progress", "created_at")
- **Status**: ✅ Complete, validated, formatted, linted

#### 3. Habits (`habits_ui.py`)
- **Date**: 2026-01-24
- **Features**: List + Create + Calendar views
- **Filter Fields**: `status` ("active", "paused", "archived", "completed", "all"), `sort_by` ("streak", "name", "recurrence", "created_at")
- **Status**: ✅ Complete, validated, formatted, linted

#### 4. Events (`events_ui.py`)
- **Date**: 2026-01-24
- **Features**: Calendar + List + Create views (calendar-first design)
- **Filter Fields**: `status` ("scheduled", "completed", "cancelled", "all"), `sort_by` ("start_time", "title", "created_at")
- **Note**: Events use calendar as DEFAULT view (not list)
- **Status**: ✅ Complete, validated, formatted, linted

#### 5. Choices (`choice_ui.py`)
- **Date**: 2026-01-24
- **Features**: List + Create + Analytics views (NO calendar)
- **Filter Fields**: `status` ("pending", "decided", "implemented", "all"), `sort_by` ("deadline", "priority", "created_at")
- **Refactored Helpers**:
  - `get_all_choices()` → `Result[list[Any]]`
  - `get_filtered_choices()` → `Result[tuple[list[Any], dict]]`
  - `get_analytics_data()` → `Result[dict[str, Any]]`
  - `get_choice_types()` → `Result[list[str]]`
  - `get_domains()` → `Result[list[str]]`
- **Status**: ✅ Complete, validated, formatted, linted

#### 6. Principles (`principles_ui.py`)
- **Date**: 2026-01-24
- **Features**: List + Create + Analytics views (NO calendar)
- **Filter Fields**:
  - `category` ("all" or specific categories)
  - `strength` ("all", "core", "strong", "developing", "aspirational")
  - `sort_by` ("strength", "title", "created_at")
- **Critical Bug Fixes**:
  - ✅ Fixed line 263: `if adherence_result.is_ok:` → `if not adherence_result.is_error:`
  - ✅ Fixed line 275: `if reflections_result.is_ok:` → `if not reflections_result.is_error:`
  - ✅ Fixed line 552: `if reflections_result.is_ok:` → `if not reflections_result.is_error:`
- **Refactored Helpers**:
  - `get_all_principles()` → `Result[list[Any]]`
  - `get_filtered_principles()` → `Result[tuple[list[Any], dict]]`
  - `get_analytics_data()` → `Result[dict[str, Any]]`
  - `get_categories()` → `Result[list[str]]`
- **Status**: ✅ Complete, validated, formatted, linted

## Domain-Specific Notes

### Calendar vs Analytics

**Calendar-Enabled** (Goals, Habits, Events):
- Include `CalendarParams` dataclass
- Include `parse_calendar_params()` helper
- Events: calendar is DEFAULT view

**Analytics-Only** (Choices, Principles):
- NO CalendarParams
- Include analytics helper: `get_analytics_data() -> Result[dict]`
- List is DEFAULT view

### Filter Field Variations

Most domains use `status` + `sort_by`, but Principles is different:
- **Standard**: Filters(status, sort_by)
- **Principles**: Filters(category, strength, sort_by)

## Validation Checklist

For each domain after refactoring:

### Functional Tests
- [ ] Main dashboard loads without errors
- [ ] List view shows entities correctly
- [ ] Create view renders form
- [ ] Calendar/Analytics view loads (depending on domain)
- [ ] Filter changes update list
- [ ] Sort changes work

### Error Handling Tests
- [ ] Stop Neo4j → error banner displays on main dashboard
- [ ] Stop Neo4j → HTMX fragments return error banner
- [ ] Empty results show "No {domain}" message (not error banner)
- [ ] Logs show error details (user_uid, error type, message)

### Code Quality
- [ ] `./dev quality` passes (no SKUEL linter errors)
- [ ] No `.is_ok` references (should be `.is_error`)
- [ ] All helpers return `Result[T]`
- [ ] All routes check `.is_error` before using `.value`
- [ ] Python syntax validates: `poetry run python -m py_compile adapters/inbound/{domain}_ui.py`

## Files Modified

### Completed
- ✅ `/adapters/inbound/tasks_ui.py` (reference)
- ✅ `/adapters/inbound/goals_ui.py`
- ✅ `/adapters/inbound/habits_ui.py`
- ✅ `/adapters/inbound/events_ui.py`
- ✅ `/adapters/inbound/choice_ui.py`
- ✅ `/adapters/inbound/principles_ui.py`

## Documentation Updates

### Updated Files
- ✅ `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Added "Activity Domain UI Error Handling Pattern" section
- ✅ `/docs/patterns/ERROR_HANDLING.md` - Added "Layer 4: UI Routes (Activity Domains)" section
- ✅ `/docs/migrations/ACTIVITY_UI_ERROR_HANDLING_REFACTORING_2026-01-24.md` - This file

## Benefits Achieved

1. **User Experience**: Clear error messages instead of confusing empty lists
2. **Debuggability**: Full error context in structured logs (user_uid, error_type, message)
3. **Consistency**: All Activity domains follow same pattern (6 total)
4. **Type Safety**: Dataclasses prevent query parameter extraction bugs
5. **Maintainability**: Single pattern to understand across all domains

## Next Steps

1. ✅ Complete Choices UI refactoring
2. ✅ Complete Principles UI refactoring (+ bug fixes)
3. Test all domains with Neo4j stopped to verify error banners (recommended)
4. Consider extracting common helpers to shared module (future optimization)

## References

- **Tasks Reference**: `/adapters/inbound/tasks_ui.py:64-143`
- **Pattern Docs**: `/docs/patterns/UI_COMPONENT_PATTERNS.md:674-854`
- **Error Handling**: `/docs/patterns/ERROR_HANDLING.md:135-225`
