---
related_skills:
- result-pattern
- fasthtml
- ui-browser
- skuel-ui
- python
---

# SKUEL UI Error Handling

*Last updated: 2026-07-09*

**When to use this skill:** When building UI routes, handling `Result[T]` at boundaries, implementing error banners, creating form validation, or understanding how SKUEL propagates errors from services to UI.

---

## Overview

SKUEL uses a consistent error-handling pattern across all UI routes that makes failures **visible to users** instead of silently returning empty lists or ad-hoc error elements.

**Core Principle:** "Typed params, Result[T] propagation, visible error banners"

This pattern has three key components:
1. **Typed query parameters** (dataclasses) for type safety
2. **Result[T] propagation** from services through data helpers
3. **Error banner rendering** via `render_error_banner()` for user-visible failures

**Benefits:**
- User-visible errors (clear messages instead of empty lists)
- Full debuggability (error context in logs)
- Type safety (dataclasses prevent param extraction errors)
- Consistency (all domains follow same pattern)

**Applied to:** All 6 Activity domains + Teaching, KU, Admin, Insights, UserEntry, Exercises, Calendar, Form Submissions, LifePath, Analytics, Activity Review, Learning Loop (standardized 2026-03-19; the former Study domain was decomposed into entity-typed routes)

---

## Core Concepts

### 1. Result[T] Pattern for UI

At the UI boundary, we:
- Return `Result[T]` from all data helpers (not exceptions)
- Check `.is_error` in route handlers
- Render error banners for user-visible failures
- Log errors with full context

**NOT this:**
```python
# ❌ Silent failure - returns empty list on error
async def get_tasks(user_uid):
    try:
        return await tasks_service.list_for_user(user_uid)
    except Exception:
        return []  # User sees nothing, no debugging info
```

**DO this:**
```python
# ✅ Explicit Result[T] with error propagation
async def get_tasks(user_uid) -> Result[list[Task]]:
    try:
        result = await tasks_service.list_for_user(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch tasks: {result.error}")
            return result  # Propagate the error
        return Result.ok(result.value or [])
    except Exception as e:
        logger.error("Error fetching tasks", extra={...})
        return Errors.system(f"Failed to fetch tasks: {e}")
```

### 2. Typed Query Parameters

Use `@dataclass` for query parameter extraction:

```python
from dataclasses import dataclass

@dataclass
class Filters:
    """Typed filters for list queries."""
    status: str
    sort_by: str

@dataclass
class CalendarParams:
    """Typed params for calendar view."""
    calendar_view: str
    current_date: date
```

**Benefits:**
- Type safety (autocomplete, MyPy checking)
- Single source of truth for parameters
- Easy to test (pass Filters instance, not mock request)
- Clear parameter documentation

### 3. Error Banner Component

User-visible error messages using Alert wrapper:

```python
from ui.patterns.error_banner import render_error_banner

# Simple error
render_error_banner("Unable to save task")

# With technical details (shown in dev mode)
render_error_banner(
    "Unable to save task",
    technical_details="Database connection timeout",
    severity="error"
)
```

**Important:** Do NOT pass `role="alert"` to `Alert()` — SKUEL's `Alert` already sets `role="alert"` internally, and duplicating it causes a `TypeError: got multiple values for keyword argument 'role'`.

### 4. Pure Computation Helpers

Separate I/O from computation:
- **I/O helpers**: Async functions that fetch data, return `Result[T]`
- **Computation helpers**: Pure functions (stats, filtering, sorting)
- **Form parsing helpers**: Pure functions that parse form data into typed requests

**Benefits:**
- Testable without async mocks
- Clear separation of concerns
- Single Responsibility Principle
- Easy to modify individual pieces

### 5. Pure Form Parsing Helpers

All 6 activity domain UI files extract form parsing into module-level pure functions under a `# Form Parsing Helpers` section. These have no service calls and no request access. Shared primitives live in `adapters/inbound/form_helpers.py`:

**Individual field helpers** (for UI routes with simple forms):
- `safe_form_string()`, `safe_form_int()`, `safe_form_bool()` — type-safe extraction from `str | UploadFile | None`
- `parse_enum_safe(enum_class, value, default)` — replaces try/except ValueError pattern
- `parse_date_safe()`, `parse_time_safe()`, `parse_datetime_safe()` — ISO string → typed value or None
- `ActivityFilters` + `parse_activity_filters()` — shared 2-field filter dataclass for Goals, Habits, Events, Choices

**Structured body helpers** (for API routes with Pydantic models):
- `parse_json_body(request, schema, extra=None)` → `Result[T]` — parses JSON body into a Pydantic model. Handles both JSON parse errors and ValidationError, converting to `Result.fail()`. Use `extra=` to merge additional fields (e.g., entity UID from ownership decorator).
- `parse_form_body(request, schema)` → `Result[T]` — parses form data into a Pydantic model. Empty strings become `None` (handles HTML form quirk). Use when form data has enough fields to warrant a Pydantic model with validators.

```python
# adapters/inbound/tasks_ui.py — module level, before route factory
from adapters.inbound.form_helpers import parse_enum_safe, parse_date_safe, safe_form_string

def parse_task_create_request(form_data: dict[str, Any]) -> TaskCreateRequest:
    """Parse form data into a TaskCreateRequest. Pure function, no side effects."""
    title = safe_form_string(form_data.get("title"))
    description = safe_form_string(form_data.get("description")) or None
    priority = parse_enum_safe(Priority, form_data.get("priority", "medium"), Priority.MEDIUM)
    due_date = parse_date_safe(form_data.get("due_date", ""))
    # ...
    return TaskCreateRequest(title=title, description=description, priority=priority, ...)

def parse_task_update_payload(form: Any) -> dict[str, Any]:
    """Parse edit-modal form into an update dict. Pure function, no side effects."""
    updates: dict[str, Any] = {}
    title = safe_form_string(form.get("title"))
    if title:
        updates["title"] = title
    # ... parse other fields
    return updates
```

Route handlers become thin — just auth + parse + service call:

```python
async def create_task_from_form(form_data: dict[str, Any], user_uid: UserUID) -> Result[Task]:
    """Domain-specific task creation logic."""
    create_request = parse_task_create_request(form_data)
    return await tasks_service.create_task(create_request, user_uid)
```

**Note:** `validate_*_form_data()` functions were eliminated (March 2026) — Pydantic is the sole validation layer. Route handlers catch `PydanticValidationError` and render error banners automatically.

### 6. Safe Enum Parsing for HTML Forms

HTML `<select>` elements and optional dropdowns send empty strings (`""`) when no option is selected. `dict.get("field", "default")` does NOT catch this — the key exists with value `""`, so the default is ignored and the empty string reaches Pydantic enum validation, causing a crash.

```python
from adapters.inbound.form_helpers import safe_form_string

# ❌ WRONG — empty string passes through, crashes Pydantic
domain = form_data.get("domain", "personal")

# ✅ CORRECT — safe_form_string strips whitespace, `or` provides fallback for empty
domain = safe_form_string(form_data.get("domain")) or "personal"
event_type = safe_form_string(form_data.get("event_type")) or "meeting"
```

**Rule:** For any form field bound to a Pydantic enum, always use `safe_form_string(form_data.get("field")) or "default"`.

**Additionally**, use `parse_enum_safe()` from `form_helpers` for enum constructor calls — a crafted form can submit any string value:

```python
from adapters.inbound.form_helpers import parse_enum_safe

priority_str = safe_form_string(form_data.get("priority")) or "medium"
priority = parse_enum_safe(Priority, priority_str, Priority.MEDIUM)
```

All 6 activity domain `*_ui.py` files use `parse_enum_safe()` for enum conversions. The only exceptions are conditional-set patterns in update payloads (e.g., `tasks_ui.py` update), which use `contextlib.suppress(ValueError)` because they only set the key on success.

---

## Decision Trees

### Handling Result[T] in Routes

```
Data helper returns Result[T]
├─ Is this the main dashboard route?
│  ├─ YES → Check .is_error, render error banner with tabs/nav
│  └─ NO → HTMX fragment?
│     ├─ YES → Return error banner directly (HTMX swap)
│     └─ NO → Check .is_error, render full page error
│
└─ After error check, extract .value for success case
```

### Choosing Data Helper Pattern

```
Need to fetch data for UI?
├─ Simple fetch (no filtering/sorting)?
│  └─ async def get_all_tasks() -> Result[list[Task]]
│
├─ Fetch + stats calculation?
│  └─ Split into:
│     - async def get_all_tasks() -> Result[list[Task]]  # I/O
│     - def compute_stats(tasks) -> dict  # Pure
│
└─ Fetch + stats + filter + sort?
   └─ Split into:
      - async def get_all_tasks() -> Result[list[Task]]  # I/O
      - def compute_stats(tasks) -> dict  # Pure
      - def apply_filters(tasks, ...) -> list[Any]  # Pure
      - def apply_sort(tasks, sort_by) -> list[Any]  # Pure
      - async def get_filtered_tasks(...) -> Result[tuple[list, dict]]  # Orchestrator
```

---

## Implementation Patterns, Examples & Anti-Patterns

The code-heavy detail lives in **[reference.md](reference.md)**:

- **Implementation Patterns** — filter dataclasses, optional-service injection, pure computation helpers, full-page vs HTMX-fragment error rendering, per-section conditional banners.
- **Real-World Examples** — FilteredContextProvider facade, type-safe route accessors, calendar typed params.
- **Common Mistakes & Anti-Patterns** — the paired ❌/✅ before-after recipes (silent failures, orchestration in routes, early validation, error banners, logging with context).

---

## Testing & Verification

### Checklist for Error Handling

When implementing error handling for a new domain:

- [ ] All data helpers return `Result[T]` (not exceptions)
- [ ] All route handlers check `.is_error` before `.value`
- [ ] Error banners rendered for failures (not empty lists)
- [ ] Errors logged with context (user_uid, operation, error details)
- [ ] Query parameters extracted with typed dataclasses
- [ ] Pure computation helpers extracted (testable without mocks)
- [ ] Early form validation with user-friendly messages
- [ ] HTMX fragments return error banners (not full pages)
- [ ] Main dashboard shows tabs even on error (navigation still works)
- [ ] Dashboard helpers return `tuple[data, bool]` when partial failure matters
- [ ] Independent service calls use partial error collection (not fail-on-first)
- [ ] All errors use `render_error_banner()` (full-page) or `render_inline_error()` (HTMX fragments)

### Unit Testing Pure Helpers

```python
def test_compute_task_stats():
    """Test stats calculation without mocks."""
    tasks = [
        Mock(status=ActivityStatus.COMPLETED),
        Mock(status=ActivityStatus.PENDING, due_date=date.today() - timedelta(days=1)),
    ]

    stats = compute_task_stats(tasks)

    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["overdue"] == 1


def test_apply_task_filters_active():
    """Test active filter without mocks."""
    tasks = [
        Mock(status=ActivityStatus.COMPLETED),
        Mock(status=ActivityStatus.PENDING),
    ]

    filtered = apply_task_filters(tasks, status_filter="active")

    assert len(filtered) == 1
    assert filtered[0].status == ActivityStatus.PENDING


def test_validate_task_form_data_missing_title():
    """Test form validation returns clear error."""
    form_data = {"title": "", "description": "Test"}

    result = validate_task_form_data(form_data)

    assert result.is_error
    assert "Task title is required" in result.error
```

**Key:** Pure functions are trivially testable (no async, no mocks, just data)

---

## Related Documentation

### Core Files
- `/adapters/inbound/tasks_ui.py` - Reference implementation (all patterns)
- `/adapters/inbound/goals_ui.py` - `render_error_banner()` for full-page not-found on create/edit
- `/adapters/inbound/choices_ui.py` - Form validation example
- `/adapters/inbound/teaching_ui.py` - Non-activity domain, sidebar pages
- `/adapters/inbound/learning_loop_routes.py` - HTMX fragments with `render_inline_error()` preserving target IDs
- `/adapters/inbound/user_entry_ui.py` - HTMX fragments: journal loading, download auth, file-not-found, submission history (unified submissions + journals surface, ADR-054)
- `/adapters/inbound/exercises_ui.py` - `render_error_banner()` for dashboard, `render_inline_error()` for edit/view
- `/adapters/inbound/habits_ui.py` - `render_inline_error()` for completion, patterns, goal analytics
- `/adapters/inbound/ku_ui.py` - Error state vs empty state distinction
- `/adapters/inbound/admin_dashboard_ui.py` - `render_error_banner()` for user-not-found, warning severity for partial failures
- `/adapters/inbound/insights_ui.py` - Error state with load-more pagination
- `/adapters/inbound/calendar_api.py` - `render_inline_error()` for reschedule validation
- `/adapters/inbound/activities_ui.py` - `render_inline_error()` for preview card loading
- `/ui/analytics/life_path.py` - `EmptyState` for no Life Path; `/ui/analytics/life_summary.py` - `EmptyState` for no weekly data (delegated from `analytics_ui.py`)
- `/adapters/inbound/form_submissions_ui.py` - `render_error_banner()` for full-page, `EmptyState` for empty data
- `/ui/lifepath/vision.py` - `EmptyState` with CTA for no matching Learning Paths (delegated from `lifepath_ui.py`)

### Factory-Centralized Activity Error Handling (`/adapters/inbound/activity_ui_factory.py`)
- `create_activity_ui_routes()` owns fetch + Result propagation + the not-found path for all 6 Activity domains — generated fragments render `render_error_banner()`; routes never hand-roll these states.
- Calendar query params parse via `parse_date_query_param()` from `route_factories`.
- (The former `/adapters/inbound/ui_helpers.py` shared-helper module was deleted 2026-08 with zero consumers.)

### Error Banner Component
- `/ui/patterns/error_banner.py` - `render_error_banner()`, `render_inline_error()`, `render_empty_state_with_error()`
- `/ui/patterns/__init__.py` - Package-level exports

### Documentation
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Complete UI patterns (see the Error Handling section)
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
- `/CLAUDE.md` - Error handling section

### Related Skills
- **result-pattern** - Result[T] type, Errors factory, error propagation
- **skuel-ui** - BasePage usage, page structure
- **fasthtml** - FastHTML routes, form handling
- **ui-browser** - HTMX fragments, swapping patterns
- **python** - Type hints, async/await, dataclasses

---

## See Also

### Implementation Status

**Activity Domains** (full pattern with typed params + Result[T] helpers, 2026-01-24):
- ✅ Tasks — reference implementation
- ✅ Goals, Habits, Events, Choices, Principles

**Non-Activity Domains** (render_error_banner standardized, 2026-03-18; render_inline_error for HTMX, 2026-03-19):
- ✅ Teaching (`teaching_ui.py`) — 10 error sites, fixed `.is_ok` → `.is_error` bug (SKUEL003)
- ✅ Learning Loop (`learning_loop_routes.py`) — `render_inline_error()` for HTMX fragments preserving target IDs (absorbed the former `study_ui.py` when Study was decomposed into entity-typed routes)
- ✅ UserEntry (`user_entry_ui.py`) — `render_inline_error()` for journal loading, download auth, file-not-found, submission history (unified submissions + journals surface, ADR-054)
- ✅ Exercises (`exercises_ui.py`) — `render_error_banner()` for dashboard; `render_inline_error()` for edit/view not-found
- ✅ Habits (`habits_ui.py`) — `render_inline_error()` for completion, pattern analysis, goal system/velocity/impact
- ✅ Goals (`goals_ui.py`) — `render_error_banner()` for full-page not-found
- ✅ KU (`ku_ui.py`) — error banner on Ku list failure, logging for bookmark failures
- ✅ Admin (`admin_dashboard_ui.py`) — `render_error_banner()` for user-not-found; warning banners for stats, system status
- ✅ Insights (`insights_ui.py`) — error banner on insights/stats load failure, load-more endpoint
- ✅ Finance (`finance_ui.py`) — typed context methods with Result[TypedDict]
- ✅ Calendar (`calendar_api.py`) — `render_inline_error()` for reschedule validation
- ✅ Activities (`activities_ui.py`) — `render_inline_error()` for preview card loading
- ✅ Analytics (`ui/analytics/`) — `EmptyState` for no Life Path, no domain activity, no weekly data (delegated from `analytics_ui.py`)
- ✅ Form Submissions (`form_submissions_ui.py`) — `render_error_banner()` + `EmptyState` for empty data
- ✅ LifePath (`ui/lifepath/`) — `EmptyState` with CTA for no matching Learning Paths (delegated from `lifepath_ui.py`)
- ✅ Activity Review (`activity_review_ui.py` + `ui/activity_review/`) — `render_inline_error()` for missing UID, context builder

**Component exports:** `render_error_banner`, `render_inline_error` from `ui/patterns/error_banner.py`; `EmptyState` from `ui/patterns/empty_state.py`.

### Key Insights

**Why typed parameters?**
Type safety, autocomplete, clear documentation, testability

**Why pure helpers?**
Testable without mocks, Single Responsibility, 67% complexity reduction

**Why early validation?**
User-friendly errors, fast failure, clear validation rules

**Why Result[T] propagation?**
Explicit error handling, no silent failures, full error context

**Philosophy:** "Errors are first-class citizens - make them visible, clear, and debuggable"
