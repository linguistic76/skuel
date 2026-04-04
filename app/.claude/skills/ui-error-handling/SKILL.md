---
related_skills:
- result-pattern
- fasthtml
- html-htmx
- base-page-architecture
- python
---

# SKUEL UI Error Handling

*Last updated: 2026-03-20*

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

**Applied to:** All 6 Activity domains + Teaching, Study, KU, Admin, Insights, Submissions, Journals, Exercises, Calendar, Form Submissions, LifePath, Analytics, Activity Review (standardized 2026-03-19)

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

**Important:** Do NOT pass `role="alert"` to `Alert()` — MonsterUI's `MAlert` already sets `role="alert"` internally, and duplicating it causes a `TypeError: got multiple values for keyword argument 'role'`.

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

## Implementation Patterns

### Pattern 1: Typed Query Parameters

**Use when:** Extracting query parameters from request (filtering, sorting, pagination)

**Two filter patterns:**
- **`ActivityFilters`** (shared, from `form_helpers`) — 2-field `status + sort_by` for Goals, Habits, Events, Choices
- **Custom `Filters`** (per-domain) — Tasks (5 fields), Principles (3 fields)

**Example:**
```python
from adapters.inbound.form_helpers import ActivityFilters, parse_activity_filters

# Goals, Habits, Events, Choices — use shared ActivityFilters
def parse_filters(request) -> ActivityFilters:
    return parse_activity_filters(request, default_status="active", default_sort_by="target_date")

# Tasks — custom 5-field Filters (stays local)
@dataclass
class Filters:
    project: str
    assignee: str
    due_filter: str
    status_filter: str
    sort_by: str
```

**Calendar params** use `parse_calendar_params()` from `ui_helpers` (unchanged).

**Usage in route:**
```python
@rt("/tasks")
async def tasks_dashboard(request):
    filters = parse_filters(request)  # Type-safe access
    calendar_params = parse_calendar_params(request)

    # Use filters.status, filters.project, filters.sort_by
```

---

### Pattern 2: I/O Helper with Result[T]

**Use when:** Fetching data from services (all data access)

**Shared helper** (`adapters/inbound/ui_helpers.py`):
```python
from adapters.inbound.ui_helpers import fetch_user_entities

# Simple — service always available:
async def get_all_goals(user_uid: UserUID) -> Result[list[Goal]]:
    return await fetch_user_entities(goals_service.get_user_goals, "goals", user_uid, logger)

# Optional service — pass None when unavailable:
async def get_all_events(user_uid: UserUID) -> Result[list[Event]]:
    service_method = events_service.get_user_events if events_service else None
    return await fetch_user_entities(service_method, "events", user_uid, logger)
```

`fetch_user_entities(service_method, domain_name, user_uid, logger)` handles:
- Returns `Result[T]` (not exceptions)
- Logs errors with context (user_uid, error type, message)
- Propagates service errors (`.is_error` check)
- Catches unexpected exceptions (fallback to `Errors.system`)
- Returns `Result.ok([])` when service_method is None

---

### Pattern 3: Pure Computation Helpers

**Use when:** Processing data (stats, filtering, sorting)

**Example:**
```python
from datetime import date
from core.models.enums.activity_enums import ActivityStatus, Priority

# ========================================================================
# PURE COMPUTATION HELPERS (Testable without mocks)
# ========================================================================

def compute_task_stats(tasks: list[Any]) -> dict[str, int]:
    """
    Calculate task statistics.

    Pure function: testable without database or async.
    Returns: {"total": N, "completed": N, "overdue": N}
    """
    today = date.today()
    return {
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t.status == ActivityStatus.COMPLETED),
        "overdue": sum(
            1
            for t in tasks
            if t.due_date and t.due_date < today and t.status != ActivityStatus.COMPLETED
        ),
        "pending": sum(1 for t in tasks if t.status == ActivityStatus.PENDING),
    }


def apply_task_filters(
    tasks: list[Any],
    project: str | None = None,
    status_filter: str = "active",
) -> list[Any]:
    """
    Apply filter criteria to task list.

    Pure function: testable without database or async.
    """
    # Filter: project
    if project:
        tasks = [t for t in tasks if t.project == project]

    # Filter: status
    if status_filter == "active":
        tasks = [t for t in tasks if t.status != ActivityStatus.COMPLETED]
    elif status_filter == "completed":
        tasks = [t for t in tasks if t.status == ActivityStatus.COMPLETED]
    elif status_filter == "overdue":
        today = date.today()
        tasks = [
            t
            for t in tasks
            if t.due_date
            and t.due_date < today
            and t.status != ActivityStatus.COMPLETED
        ]
    # "all" - no filtering

    return tasks


def apply_task_sort(tasks: list[Any], sort_by: str = "due_date") -> list[Any]:
    """
    Sort tasks by specified field.

    Pure function: testable without database or async.
    """
    if sort_by == "due_date":
        # Sort by due_date, None last
        return sorted(tasks, key=lambda t: (t.due_date is None, t.due_date))

    elif sort_by == "priority":
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        return sorted(tasks, key=lambda t: priority_order.get(t.priority, 999))

    elif sort_by == "created_at":
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    else:  # Default: due_date
        return sorted(tasks, key=lambda t: (t.due_date is None, t.due_date))
```

**Key Features:**
- No `async` (pure computation)
- No `await` (no I/O)
- No service calls (testable with plain data)
- Clear docstrings (explains what, not how)
- Single responsibility (one function, one job)

---

### Pattern 4: FilteredContextProvider (Service Facade)

**Use when:** Combining I/O + multiple computation steps for list views

All 6 Activity Domain facades implement `get_filtered_context() -> Result[ListContext]`,
delegating to `build_filtered_context()` in `core/services/filtered_context.py`.

**Example:**
```python
from core.ports.query_types import ListContext

# In the service facade:
async def get_filtered_context(
    self, user_uid: UserUID, status_filter: str = "active", sort_by: str = "due_date",
) -> Result[ListContext]:
    """Get filtered and sorted tasks with pre-filter stats in a single query."""

    async def fetch_all() -> Result[list[Task]]:
        return await self.core.get_for_user_filtered(user_uid, "all")

    def apply_filters(all_tasks: list[Any]) -> list[Any]:
        return apply_entity_filter(all_tasks, status_filter, _TASK_FILTER_CONFIG)

    return await build_filtered_context(
        fetch_all=fetch_all,
        compute_stats=_compute_task_stats,
        apply_filters=apply_filters,
        apply_sort=_apply_task_sort,  # delegates to apply_entity_sort() with _TASK_SORT_CONFIG
        sort_by=sort_by,
    )
```

**In the route:**
```python
from core.utils.list_context_helpers import get_entities, get_stats

result = await tasks_service.get_filtered_context(user_uid, status_filter, sort_by)
if result.is_error:
    return render_error_banner(result)
ctx = result.value
tasks = get_entities(ctx, Task)   # list[Task]
stats = get_stats(ctx)            # dict[str, int | float]
```

**Key Features:**
- **Service owns orchestration** (not route-level helpers)
- **`ListContext` TypedDict** with `entities`, `stats: dict[str, int | float]`, `metadata`
- **Type-safe accessors** via `core/utils/list_context_helpers.py`
- **Pure computation callables** passed to generic `build_filtered_context()`

See: `core/services/filtered_context.py`, `core/ports/query_types.py:ListContext`

---

### Pattern 5: Main Dashboard Route

**Use when:** Building the main page for a domain (handles all views)

**Example:**
```python
from ui.layouts.base_page import BasePage
from ui.tokens import Container, Spacing

@rt("/tasks")
async def tasks_dashboard(request) -> Any:
    """Main tasks dashboard with list/calendar/analytics views."""
    user_uid = require_authenticated_user(request)

    # Parse query parameters (typed)
    view = request.query_params.get("view", "list")
    filters = parse_task_filters(request)
    calendar_params = parse_calendar_params(request)

    # Fetch filtered data
    filtered_result = await get_filtered_tasks(
        user_uid=user_uid,
        project=filters.project,
        status_filter=filters.status,
        sort_by=filters.sort_by,
    )

    # CHECK FOR ERRORS - show banner instead of empty list
    if filtered_result.is_error:
        error_content = Div(
            # Still show tabs/navigation
            TasksViewComponents.render_view_tabs(active_view=view),
            # Error banner with clear message
            render_error_banner(f"Failed to load tasks: {filtered_result.error}"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )
        return BasePage(
            error_content,
            title="Tasks",
            request=request,
            active_page="tasks",
        )

    # Extract values only AFTER error check
    tasks, stats = filtered_result.value

    # Render appropriate view
    if view == "list":
        content = TasksViewComponents.render_list_view(ctx=page_ctx)
    elif view == "calendar":
        content = TasksViewComponents.render_calendar_view(
            tasks,
            calendar_params.calendar_view,
            calendar_params.current_date,
        )
    elif view == "analytics":
        content = TasksViewComponents.render_analytics_view(tasks, stats)
    else:
        content = TasksViewComponents.render_list_view(ctx=page_ctx)

    return BasePage(
        content,
        title="Tasks",
        request=request,
        active_page="tasks",
    )
```

**Key Features:**
- Typed parameters (parse_task_filters, parse_calendar_params)
- Error check BEFORE .value access
- Error banner with navigation (tabs still visible)
- Multi-view support (list/calendar/analytics)
- BasePage for consistency

---

### Pattern 6: HTMX Fragment Route

**Use when:** Building HTMX-swappable fragments (tab content, filtered lists)

**Example:**
```python
@rt("/tasks/view/list")
async def tasks_view_list(request) -> Any:
    """HTMX fragment for list view (swapped via hx-get)."""
    user_uid = require_authenticated_user(request)

    # Parse filters
    filters = parse_task_filters(request)

    # Fetch filtered data
    filtered_result = await get_filtered_tasks(
        user_uid=user_uid,
        project=filters.project,
        status_filter=filters.status,
        sort_by=filters.sort_by,
    )

    # Handle errors (return banner directly for HTMX swap)
    if filtered_result.is_error:
        return render_error_banner(f"Failed to load tasks: {filtered_result.error}")

    # Success: render list view
    tasks, stats = filtered_result.value
    return TasksViewComponents.render_list_view(ctx=page_ctx)
```

**Key Differences from Main Route:**
- **Returns fragment** (not full BasePage)
- **Error banner only** (no tabs/nav - HTMX swaps into container)
- **No view switching** (single view per route)

**HTMX Usage:**
```html
<div id="tasks-content" hx-get="/tasks/view/list?filter_status=active" hx-trigger="load">
  <!-- Content swapped here -->
</div>
```

---

### Pattern 7: Early Form Validation

**Use when:** Validating form data before Pydantic layer

**Example:**
```python
def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate task form data early.

    Pure function: returns clear error messages for UI.
    """
    # Required fields
    title = safe_form_string(form_data.get("title"))
    if not title:
        return Errors.validation("Task title is required")

    if len(title) > 200:
        return Errors.validation("Task title must be 200 characters or less")

    # Date validation
    scheduled_date_str = form_data.get("scheduled_date", "")
    due_date_str = form_data.get("due_date", "")

    if scheduled_date_str and due_date_str:
        try:
            scheduled = date.fromisoformat(scheduled_date_str)
            due = date.fromisoformat(due_date_str)

            if due < scheduled:
                return Errors.validation("Due date cannot be before scheduled date")

        except ValueError:
            return Errors.validation("Invalid date format (use YYYY-MM-DD)")

    # Priority validation
    priority = form_data.get("priority")
    if priority and priority not in ["low", "medium", "high", "critical"]:
        return Errors.validation(f"Invalid priority: {priority}")

    return Result.ok(None)


async def create_task_from_form(form_data: dict[str, Any], user_uid: UserUID) -> Result[Task]:
    """Create task from form data with early validation."""

    # VALIDATE EARLY (before hitting services)
    validation_result = validate_task_form_data(form_data)
    if validation_result.is_error:
        logger.warning(f"Form validation failed: {validation_result.error}")
        return validation_result  # Return to UI with clear message

    # Continue with form processing...
    # ... build CreateTaskRequest, call service ...
```

**Benefits:**
- **User-friendly errors** ("Task title is required" vs Pydantic "Field required: title")
- **Early failure** (before hitting services, faster feedback)
- **Testable** (pure function, no mocks)
- **Clear rules** (all validation logic in one place)

---

### Pattern 8: Error Banner Component

**Use when:** Rendering errors to users (all error cases)

**Two components for different contexts:**

| Component | Use case | Output |
|-----------|----------|--------|
| `render_error_banner()` | Full-page errors, dashboard failures | Alert box with icon, optional technical details |
| `render_inline_error()` | HTMX fragments, form fields, compact spaces | Small `P` with `role="alert"` + `aria-live="polite"` |

**Import:** `from ui.patterns.error_banner import render_error_banner, render_inline_error`

**Usage:**
```python
# Full-page error (main route)
if result.is_error:
    return BasePage(
        render_error_banner(f"Failed to load data: {result.error}"),
        title="Error",
        request=request,
    )

# HTMX fragment error (compact, accessible)
if result.is_error:
    return render_inline_error("Could not load data")

# HTMX fragment with target ID preservation
if result.is_error:
    return Div(render_inline_error("Report not found"), id="content-section")

# With severity levels (full banner only)
render_error_banner("Some data may be incomplete", severity="warning")
```

**Choosing between them:**
- **`render_error_banner()`** — full Alert component, use for page-level errors where space is available
- **`render_inline_error()`** — compact `P` element with WCAG attributes, use for HTMX fragment returns, form field errors, and anywhere a full alert would be visually heavy

**Styling:**
- `render_error_banner()`: MonsterUI alert (red background, error icon), severity variants
- `render_inline_error()`: `text-error text-sm` with `role="alert"` + `aria-live="polite"`
- `role="alert"` set automatically by MAlert in render_error_banner (do NOT pass it as a kwarg — causes duplicate kwarg TypeError)

---

### Pattern 9: Dashboard Partial Failure Banners

**Use when:** A dashboard page makes multiple independent service calls and some may fail while others succeed.

**Key Insight:** Dashboards aggregate data from multiple services. A failure in one section should not blank the entire page. Return `tuple[data, bool]` from helpers where the bool indicates an error, then conditionally render warning banners per section.

**Helper pattern:**
```python
async def _get_user_stats(services) -> tuple[dict, bool]:
    """Returns (stats_dict, had_error)."""
    stats = {"total": 0, "admins": 0, ...}
    try:
        result = await services.user_service.list_users(...)
        if result.is_error:
            return stats, True
        # ... populate stats ...
        return stats, False
    except Exception:
        return stats, True
```

**Consumer pattern:**
```python
user_stats, stats_error = await _get_user_stats(services)

# Conditional banner per section
Card(
    H2("User Statistics"),
    render_error_banner("User statistics unavailable", severity="warning")
    if stats_error
    else AdminUIComponents.render_user_stats(user_stats),
)
```

**Applied to:**
- Admin dashboard: system status, user stats, detail stats, KU metrics, user progress (each independent)
- Teaching dashboard: dashboard stats banner above zero-state dashboard
- Profile intelligence: 4 independent calls with `partial_errors` list (see Pattern 10)

---

### Pattern 10: Independent Partial Results (Intelligence)

**Use when:** Multiple async calls are independent and expensive — a single failure should not block the rest.

**Key Insight:** Instead of a cascading fail-on-first-error chain, call each method independently, collect partial errors, and let the UI render whatever succeeded.

```python
daily_plan = alignment = synergies = path_steps = None
partial_errors: list[str] = []

plan_result = await intelligence.get_ready_to_work_on_today()
if plan_result.is_error:
    partial_errors.append("Daily plan unavailable")
else:
    daily_plan = plan_result.value

# ... same for alignment, synergies, path_steps ...

if all(v is None for v in [daily_plan, alignment, synergies, path_steps]):
    return Result.fail(Errors.system("All intelligence calls failed"))

return Result.ok({
    "daily_plan": daily_plan, "alignment": alignment,
    "synergies": synergies, "path_steps": path_steps,
    "partial_errors": partial_errors,
})
```

**Consumer renders only successful sections:**
```python
partial_errors = intel_data.get("partial_errors", [])
sections = [_chart_visualizations_section()]

if partial_errors:
    sections.append(render_error_banner(
        "Some intelligence features are temporarily unavailable",
        severity="warning",
    ))

if intel_data.get("alignment") is not None:
    sections.append(_alignment_breakdown(intel_data["alignment"]))
# ... conditionally append each section ...
```

**Applied to:** Profile intelligence HTMX endpoint (`/api/profile/intelligence-section`)

---

## Real-World Examples

### Example 1: Tasks Dashboard (FilteredContextProvider Pattern)
**Files:** `/core/services/tasks_service.py`, `/adapters/inbound/tasks_ui.py`

```python
# Service facade — implements FilteredContextProvider protocol
# Pure computation helpers are module-level functions passed as callables
async def get_filtered_context(
    self, user_uid: UserUID, status_filter: str = "active", sort_by: str = "due_date",
) -> Result[ListContext]:
    """Get filtered and sorted tasks with pre-filter stats."""

    async def fetch_all() -> Result[list[Task]]:
        return await self.core.get_for_user_filtered(user_uid, "all")

    def apply_filters(all_tasks: list[Any]) -> list[Any]:
        return apply_entity_filter(all_tasks, status_filter, _TASK_FILTER_CONFIG)

    return await build_filtered_context(
        fetch_all=fetch_all,
        compute_stats=_compute_task_stats,
        apply_filters=apply_filters,
        apply_sort=_apply_task_sort,  # delegates to apply_entity_sort() with _TASK_SORT_CONFIG
        sort_by=sort_by,
    )

# Route consumes via type-safe accessors
from core.utils.list_context_helpers import get_entities, get_stats

@rt("/tasks")
async def tasks_dashboard(request):
    filtered_result = await tasks_service.get_filtered_context(user_uid, status_filter, sort_by)

    if filtered_result.is_error:
        return BasePage(render_error_banner(f"Failed: {filtered_result.error}"), ...)

    ctx = filtered_result.value
    tasks = get_entities(ctx, Task)   # list[Task]
    stats = get_stats(ctx)            # dict[str, int | float]
    # ... render views
```

**Pattern:** Complete error handling with typed params, pure helpers, Result[T] propagation

---

### Example 2: Goals Calendar View (Calendar-Specific)
**File:** `/adapters/inbound/goals_ui.py:180-250`

```python
# Calendar-specific typed params
@dataclass
class CalendarParams:
    calendar_view: str  # "day", "week", "month"
    current_date: date

def parse_calendar_params(request) -> CalendarParams:
    calendar_view = request.query_params.get("calendar_view", "month")
    date_str = request.query_params.get("date", "")

    try:
        current_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        current_date = date.today()

    return CalendarParams(calendar_view, current_date)

# Calendar view route
@rt("/goals/view/calendar")
async def goals_view_calendar(request):
    calendar_params = parse_calendar_params(request)

    goals_result = await get_all_goals(user_uid)
    if goals_result.is_error:
        return render_error_banner(f"Failed: {goals_result.error}")

    # Render calendar with current_date and calendar_view
    return render_calendar_view(
        goals_result.value,
        calendar_params.calendar_view,
        calendar_params.current_date,
    )
```

**Pattern:** Calendar-specific typed params with date parsing

---

### Example 3: Form Validation (Choices)
**File:** `/adapters/inbound/choice_ui.py:300-350`

```python
def validate_choice_form_data(form_data: dict[str, Any]) -> Result[None]:
    """Validate choice form data early."""

    title = safe_form_string(form_data.get("title"))
    if not title:
        return Errors.validation("Choice title is required")

    if len(title) > 200:
        return Errors.validation("Title must be 200 characters or less")

    # Options validation (choices need at least 2 options)
    option1 = safe_form_string(form_data.get("option1"))
    option2 = safe_form_string(form_data.get("option2"))

    if not option1 or not option2:
        return Errors.validation("At least two options are required")

    # Decision date validation
    decision_date_str = form_data.get("decision_date", "")
    if decision_date_str:
        try:
            decision_date = date.fromisoformat(decision_date_str)
            if decision_date < date.today():
                return Errors.validation("Decision date cannot be in the past")
        except ValueError:
            return Errors.validation("Invalid date format")

    return Result.ok(None)


async def create_choice_from_form(form_data: dict[str, Any], user_uid: UserUID) -> Result[Choice]:
    """Create choice with early validation."""

    # Validate early
    validation_result = validate_choice_form_data(form_data)
    if validation_result.is_error:
        return validation_result

    # Continue with form processing
    # ... build request, call service
```

**Pattern:** Domain-specific validation (choices need 2+ options)

---

## Common Mistakes & Anti-Patterns

### Mistake 1: Silent Failure (Returning Empty List)

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
async def get_all_tasks(user_uid):
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        return result.value if not result.is_error else []  # Silent failure
    except Exception:
        return []  # User sees empty list, no debugging info
```

**Problems:**
- User sees empty list (thinks they have no tasks)
- No error message (confusing UX)
- No logging (impossible to debug)
- Silent failure (errors hidden)

**Correct approach:**
```python
# ✅ DO THIS
async def get_all_tasks(user_uid: UserUID) -> Result[list[Task]]:
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch tasks: {result.error}")
            return result  # Propagate error
        return Result.ok(result.value or [])
    except Exception as e:
        logger.error("Error fetching tasks", extra={...})
        return Errors.system(f"Failed to fetch tasks: {e}")
```

---

### Mistake 2: Accessing .value Without Error Check

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
@rt("/tasks")
async def tasks_dashboard(request):
    result = await get_filtered_tasks(user_uid)

    tasks, stats = result.value  # CRASHES if result.is_error!

    return BasePage(render_list(tasks), ...)
```

**Problems:**
- Crashes on error (AttributeError or similar)
- No user-visible error message
- Poor UX (white screen of death)

**Correct approach:**
```python
# ✅ DO THIS
@rt("/tasks")
async def tasks_dashboard(request):
    result = await get_filtered_tasks(user_uid)

    # CHECK FIRST
    if result.is_error:
        return BasePage(
            render_error_banner(f"Failed: {result.error}"),
            ...
        )

    # Extract .value only after error check
    tasks, stats = result.value
    return BasePage(render_list(tasks), ...)
```

---

### Mistake 3: Mixed I/O and Computation (God Helper)

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
async def get_filtered_tasks(...) -> Result[tuple[list, dict]]:
    """90-line god helper doing 5 things."""
    # 1. Fetch (I/O) - 10 lines
    tasks_result = await get_all_tasks(user_uid)

    # 2. Calculate stats (computation) - 15 lines
    stats = {"total": len(tasks), "completed": ...}

    # 3. Filter by project (computation) - 10 lines
    if project:
        tasks = [t for t in tasks if t.project == project]

    # 4. Filter by status (computation) - 15 lines
    if status == "active":
        tasks = [t for t in tasks if ...]

    # 5. Sort (computation + complex logic) - 30 lines
    if sort_by == "due_date":
        tasks = sorted(tasks, key=get_due_date_key)
    # ... more sorting options

    return Result.ok((tasks, stats))
```

**Problems:**
- Cannot unit test computation without async mocks
- 90 lines doing 5 distinct things
- Hard to modify one aspect without affecting others
- Single Responsibility Principle violated

**Correct approach — use `FilteredContextProvider` pattern:**
```python
# ✅ DO THIS - Service facade owns orchestration via build_filtered_context()

# Pure computation callables (no async, no mocks needed)
def compute_task_stats(tasks: list[Any]) -> dict[str, int | float]:
    return {"total": len(tasks), "completed": ...}

def apply_task_filters(tasks: list[Any], ...) -> list[Any]:
    return filtered_tasks

def apply_task_sort(tasks: list[Any], sort_by: str) -> list[Any]:
    return sorted_tasks

# Service facade method — delegates to build_filtered_context()
async def get_filtered_context(self, user_uid, status_filter, sort_by) -> Result[ListContext]:
    return await build_filtered_context(
        fetch_all=lambda: self.core.get_for_user_filtered(user_uid, "all"),
        compute_stats=compute_task_stats,
        apply_filters=lambda all: _apply_status_filter(all, status_filter),
        apply_sort=apply_task_sort,
        sort_by=sort_by,
    )
```

See: `core/services/filtered_context.py`, `core/ports/query_types.py:ListContext`

---

### Mistake 4: Late Validation (Pydantic Only)

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
async def create_task_from_form(form_data: dict, user_uid: UserUID):
    # No early validation - Pydantic errors are technical

    request = CreateTaskRequest(**form_data)  # May fail with: "Field required: title"
    return await tasks_service.create_task(request, user_uid)
```

**Problems:**
- Technical error messages ("Field required: title" vs "Task title is required")
- No business rule validation (e.g., "Due date cannot be before scheduled date")
- Errors happen deep in stack (harder to debug)
- Poor UX (generic validation errors)

**Correct approach:**
```python
# ✅ DO THIS - Validate early with clear messages
async def create_task_from_form(form_data: dict, user_uid: UserUID) -> Result[Task]:
    # Validate FIRST
    validation_result = validate_task_form_data(form_data)
    if validation_result.is_error:
        return validation_result  # User-friendly error

    # Build request (Pydantic still validates, but we've already checked)
    request = CreateTaskRequest(**form_data)
    return await tasks_service.create_task(request, user_uid)
```

---

### Mistake 5: Inconsistent Error Messages

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
if result.is_error:
    return Div("Error!", cls="text-red-500")  # Inconsistent styling

if other_result.is_error:
    return P(f"Failed: {other_result.error}")  # Different structure

if third_result.is_error:
    return render_error_banner(third_result.error)  # Only this one is correct
```

**Problems:**
- Inconsistent UX (different styles for same concept)
- Some errors miss styling (just plain text)
- Hard to find all error rendering code

**Correct approach:**
```python
# ✅ DO THIS - Always use render_error_banner
if result.is_error:
    return render_error_banner(f"Failed to load data: {result.error}")

if other_result.is_error:
    return render_error_banner(f"Failed to process: {other_result.error}")
```

**Consistency:** All errors use same component (alert, emoji, styling)

---

### Mistake 6: Forgetting to Log Errors

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
async def get_all_tasks(user_uid: UserUID) -> Result[list[Task]]:
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            return result  # No logging - can't debug
        return Result.ok(result.value or [])
    except Exception as e:
        return Errors.system(f"Failed: {e}")  # No logging - can't debug
```

**Problems:**
- No debugging info (can't trace failures)
- No context (which user? what operation?)
- Silent errors (only user sees message)

**Correct approach:**
```python
# ✅ DO THIS - Always log with context
async def get_all_tasks(user_uid: UserUID) -> Result[list[Task]]:
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            logger.warning(
                f"Service failed to fetch tasks: {result.error}",
                extra={"user_uid": user_uid},
            )
            return result

        return Result.ok(result.value or [])

    except Exception as e:
        logger.error(
            "Unexpected error fetching tasks",
            extra={
                "user_uid": user_uid,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return Errors.system(f"Failed to fetch tasks: {e}")
```

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
- `/adapters/inbound/goals_ui.py` - Calendar-enabled variant, `render_error_banner()` for full-page + `render_inline_error()` for gantt
- `/adapters/inbound/choices_ui.py` - Form validation example
- `/adapters/inbound/teaching_ui.py` - Non-activity domain, sidebar pages
- `/adapters/inbound/study_ui.py` - HTMX fragments with `render_inline_error()` preserving target IDs
- `/adapters/inbound/submissions_ui.py` - HTMX fragments: category selector, tags manager, shared users
- `/adapters/inbound/journals_ui.py` - Journal loading, download auth, file-not-found errors (standalone domain)
- `/adapters/inbound/exercises_ui.py` - `render_error_banner()` for dashboard, `render_inline_error()` for edit/view
- `/adapters/inbound/habits_ui.py` - `render_inline_error()` for completion, patterns, goal analytics
- `/adapters/inbound/ku_ui.py` - Error state vs empty state distinction
- `/adapters/inbound/admin_dashboard_ui.py` - `render_error_banner()` for user-not-found, warning severity for partial failures
- `/adapters/inbound/insights_ui.py` - Error state with load-more pagination
- `/adapters/inbound/calendar_api.py` - `render_inline_error()` for reschedule validation
- `/adapters/inbound/activities_ui.py` - `render_inline_error()` for preview card loading
- `/adapters/inbound/analytics_ui.py` - `EmptyState` for no Life Path, no domain activity, no weekly data
- `/adapters/inbound/form_submissions_ui.py` - `render_error_banner()` for full-page, `EmptyState` for empty data
- `/adapters/inbound/lifepath_ui.py` - `EmptyState` with CTA for no matching Learning Paths

### Shared Helpers (`/adapters/inbound/ui_helpers.py`)
- `render_dashboard_error_page(title, subtitle, error_message, view, render_view_tabs, page_creator, request)` — Standard error page for dashboard routes with tabs/nav preserved (all 6 Activity domains). Domains with multiple calls (e.g., Principles) wrap this in a local `_dashboard_error()` helper to DRY the static args.
- `render_entity_not_found_page(entity_label, uid, domain_slug, request)` — Standard "Entity Not Found" full page for detail views (all 6 Activity domains)
- `fetch_user_entities(service_method, domain_name, user_uid, logger)` — Fetch all entities with consistent Result[T] error handling/logging (4 domains)
- `parse_calendar_params(request)` — Calendar view parameters (4 calendar-enabled domains)
- `render_safe_error_response(user_message, error_context, logger, log_extra)` — Sanitized error Response for API routes

### Error Banner Component
- `/ui/patterns/error_banner.py` - `render_error_banner()`, `render_inline_error()`, `render_empty_state_with_error()`
- `/ui/patterns/__init__.py` - Package-level exports

### Documentation
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Complete UI patterns (lines 751-1199)
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
- `/CLAUDE.md` - Error handling section

### Related Skills
- **result-pattern** - Result[T] type, Errors factory, error propagation
- **base-page-architecture** - BasePage usage, page structure
- **fasthtml** - FastHTML routes, form handling
- **html-htmx** - HTMX fragments, swapping patterns
- **python** - Type hints, async/await, dataclasses

---

## See Also

### Implementation Status

**Activity Domains** (full pattern with typed params + Result[T] helpers, 2026-01-24):
- ✅ Tasks — reference implementation
- ✅ Goals, Habits, Events, Choices, Principles

**Non-Activity Domains** (render_error_banner standardized, 2026-03-18; render_inline_error for HTMX, 2026-03-19):
- ✅ Teaching (`teaching_ui.py`) — 10 error sites, fixed `.is_ok` → `.is_error` bug (SKUEL003)
- ✅ Study (`study_ui.py`) — `render_inline_error()` for HTMX fragments preserving target IDs
- ✅ Submissions (`submissions_ui.py`) — `render_inline_error()` for category selector, tags manager, shared users, report loading
- ✅ Journals (`journals_ui.py`) — `render_inline_error()` for journal loading, download auth, file-not-found
- ✅ Exercises (`exercises_ui.py`) — `render_error_banner()` for dashboard; `render_inline_error()` for edit/view not-found
- ✅ Habits (`habits_ui.py`) — `render_inline_error()` for completion, pattern analysis, goal system/velocity/impact
- ✅ Goals (`goals_ui.py`) — `render_error_banner()` for full-page not-found; `render_inline_error()` for gantt view
- ✅ KU (`ku_ui.py`) — error banner on Ku list failure, logging for bookmark failures
- ✅ Admin (`admin_dashboard_ui.py`) — `render_error_banner()` for user-not-found; warning banners for stats, system status
- ✅ Insights (`insights_ui.py`) — error banner on insights/stats load failure, load-more endpoint
- ✅ Finance (`finance_ui.py`) — typed context methods with Result[TypedDict]
- ✅ Calendar (`calendar_api.py`) — `render_inline_error()` for reschedule validation
- ✅ Activities (`activities_ui.py`) — `render_inline_error()` for preview card loading
- ✅ Analytics (`analytics_ui.py`) — `EmptyState` for no Life Path, no domain activity, no weekly data
- ✅ Form Submissions (`form_submissions_ui.py`) — `render_error_banner()` + `EmptyState` for empty data
- ✅ LifePath (`lifepath_ui.py`) — `EmptyState` with CTA for no matching Learning Paths
- ✅ Activity Review (`activity_review_ui.py`) — `render_inline_error()` for missing UID, context builder

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
