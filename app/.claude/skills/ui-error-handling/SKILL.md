---
related_skills:
- result-pattern
- fasthtml
- html-htmx
- base-page-architecture
- python
---

# SKUEL UI Error Handling

*Last updated: 2026-02-01*

**When to use this skill:** When building UI routes, handling `Result[T]` at boundaries, implementing error banners, creating form validation, or understanding how SKUEL propagates errors from services to UI.

---

## Overview

SKUEL uses a consistent error-handling pattern across all Activity domains (Tasks, Goals, Habits, Events, Choices, Principles) that makes failures **visible to users** instead of silently returning empty lists.

**Core Principle:** "Typed params, Result[T] propagation, visible error banners"

This pattern has three key components:
1. **Typed query parameters** (dataclasses) for type safety
2. **Result[T] propagation** from services through data helpers
3. **Error banner rendering** for user-visible failures

**Benefits:**
- User-visible errors (clear messages instead of empty lists)
- Full debuggability (error context in logs)
- Type safety (dataclasses prevent param extraction errors)
- Consistency (all domains follow same pattern)

**Applied to:** All 6 Activity domains (100% coverage as of 2026-01-24)

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
async def get_tasks(user_uid) -> Result[list[Any]]:
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
from ui.feedback import Alert, AlertT

def render_error_banner(message: str) -> Div:
    """Render error banner for UI failures."""
    return Alert(
        P("⚠️ Error", cls="font-bold text-error"),
        P(message, cls="text-sm"),
        variant=AlertT.error,
        cls="mb-4",
    )
```

### 4. Pure Computation Helpers

Separate I/O from computation:
- **I/O helpers**: Async functions that fetch data, return `Result[T]`
- **Computation helpers**: Pure functions (stats, filtering, sorting)
- **Validation helpers**: Pure functions that return `Result[None]`

**Benefits:**
- Testable without async mocks
- Clear separation of concerns
- Single Responsibility Principle
- Easy to modify individual pieces

### 5. Early Form Validation

Validate form data BEFORE Pydantic layer:

```python
def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate task form data early.

    Pure function: returns clear error messages for UI.
    """
    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Task title is required")

    if len(title) > 200:
        return Errors.validation("Task title must be 200 characters or less")

    # Date validation
    # ... more validation

    return Result.ok(None)
```

**Benefits:**
- User-friendly error messages (not Pydantic technical errors)
- Early failure (before hitting services)
- Clear validation rules
- Testable without mocking

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
│  └─ async def get_all_tasks() -> Result[list[Any]]
│
├─ Fetch + stats calculation?
│  └─ Split into:
│     - async def get_all_tasks() -> Result[list[Any]]  # I/O
│     - def compute_stats(tasks) -> dict  # Pure
│
└─ Fetch + stats + filter + sort?
   └─ Split into:
      - async def get_all_tasks() -> Result[list[Any]]  # I/O
      - def compute_stats(tasks) -> dict  # Pure
      - def apply_filters(tasks, ...) -> list[Any]  # Pure
      - def apply_sort(tasks, sort_by) -> list[Any]  # Pure
      - async def get_filtered_tasks(...) -> Result[tuple[list, dict]]  # Orchestrator
```

---

## Implementation Patterns

### Pattern 1: Typed Query Parameters

**Use when:** Extracting query parameters from request (filtering, sorting, pagination)

**Example:**
```python
from dataclasses import dataclass
from datetime import date

@dataclass
class TaskFilters:
    """Typed filters for task queries."""
    status: str
    project: str | None
    sort_by: str

@dataclass
class CalendarParams:
    """Typed params for calendar view."""
    calendar_view: str  # "day", "week", "month"
    current_date: date

def parse_task_filters(request) -> TaskFilters:
    """Extract task filter parameters from request."""
    return TaskFilters(
        status=request.query_params.get("filter_status", "active"),
        project=request.query_params.get("project"),
        sort_by=request.query_params.get("sort_by", "due_date"),
    )

def parse_calendar_params(request) -> CalendarParams:
    """Extract calendar view parameters."""
    calendar_view = request.query_params.get("calendar_view", "month")
    date_str = request.query_params.get("date", "")

    try:
        current_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        current_date = date.today()  # Fallback to today

    return CalendarParams(
        calendar_view=calendar_view,
        current_date=current_date,
    )
```

**Usage in route:**
```python
@rt("/tasks")
async def tasks_dashboard(request):
    filters = parse_task_filters(request)  # Type-safe access
    calendar_params = parse_calendar_params(request)

    # Use filters.status, filters.project, filters.sort_by
```

---

### Pattern 2: I/O Helper with Result[T]

**Use when:** Fetching data from services (all data access)

**Example:**
```python
from core.utils.result_simplified import Errors, Result
from core.utils.logging import get_logger

logger = get_logger("skuel.ui.tasks")

async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
    """
    Get all tasks for user.

    Returns Result[list] to propagate errors to UI.
    """
    try:
        result = await tasks_service.get_user_tasks(user_uid)

        if result.is_error:
            logger.warning(
                f"Service failed to fetch tasks: {result.error}",
                extra={"user_uid": user_uid},
            )
            return result  # Propagate the error

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

**Key Features:**
- Returns `Result[T]` (not exceptions)
- Logs errors with context (user_uid, error type, message)
- Propagates service errors (`.is_error` check)
- Catches unexpected exceptions (fallback to Errors.system)

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

### Pattern 4: Orchestrator Helper

**Use when:** Combining I/O + multiple computation steps

**Example:**
```python
async def get_filtered_tasks(
    user_uid: str,
    project: str | None = None,
    status_filter: str = "active",
    sort_by: str = "due_date",
) -> Result[tuple[list[Any], dict[str, int]]]:
    """
    Get filtered and sorted tasks for user.

    Orchestrates: fetch (I/O) → stats → filter → sort.
    Pure computation delegated to testable helper functions.

    Returns: Result[(tasks, stats)] - stats calculated BEFORE filtering
    """
    try:
        # I/O: Fetch all tasks
        tasks_result = await get_all_tasks(user_uid)
        if tasks_result.is_error:
            logger.warning(f"Failed to fetch tasks for filtering: {tasks_result.error}")
            return tasks_result  # Propagate error

        tasks = tasks_result.value

        # Computation: Calculate stats BEFORE filtering (show total count)
        stats = compute_task_stats(tasks)

        # Computation: Apply filters
        filtered_tasks = apply_task_filters(tasks, project, status_filter)

        # Computation: Apply sort
        sorted_tasks = apply_task_sort(filtered_tasks, sort_by)

        return Result.ok((sorted_tasks, stats))

    except Exception as e:
        logger.error(
            "Error filtering tasks",
            extra={
                "user_uid": user_uid,
                "project": project,
                "status_filter": status_filter,
                "error_type": type(e).__name__,
            },
        )
        return Errors.system(f"Failed to filter tasks: {e}")
```

**Key Features:**
- **Thin orchestrator** (18 lines vs 90 before refactoring)
- **Single I/O call** (get_all_tasks)
- **Pure computation delegated** (compute_stats, apply_filters, apply_sort)
- **Clear flow** (fetch → stats → filter → sort)
- **Error propagation** (checks .is_error, returns Result[T])

**Complexity Reduction:** 90 lines → 18 lines (67% reduction)

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
        content = TasksViewComponents.render_list_view(tasks, stats, filters)
    elif view == "calendar":
        content = TasksViewComponents.render_calendar_view(
            tasks,
            calendar_params.calendar_view,
            calendar_params.current_date,
        )
    elif view == "analytics":
        content = TasksViewComponents.render_analytics_view(tasks, stats)
    else:
        content = TasksViewComponents.render_list_view(tasks, stats, filters)

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
    return TasksViewComponents.render_list_view(tasks, stats, filters)
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
    title = form_data.get("title", "").strip()
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


async def create_task_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
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

**Example:**
```python
from fasthtml.common import Div, P

def render_error_banner(message: str) -> Div:
    """
    Render error banner for UI failures.

    Uses Alert wrapper with error variant.
    """
    return Alert(
        P("⚠️ Error", cls="font-bold text-error"),
        P(message, cls="text-sm"),
        variant=AlertT.error,
        cls="mb-4",
    )
```

**Usage:**
```python
# In main route
if result.is_error:
    return BasePage(
        render_error_banner(f"Failed to load data: {result.error}"),
        title="Error",
        request=request,
    )

# In HTMX fragment
if result.is_error:
    return render_error_banner(f"Failed to load data: {result.error}")
```

**Styling:**
- MonsterUI alert (red background, error icon)
- Bold title with emoji (⚠️ Error)
- Small text for message
- Bottom margin (mb-4)

---

## Real-World Examples

### Example 1: Tasks Dashboard (Complete Pattern)
**File:** `/adapters/inbound/tasks_ui.py:50-120`

```python
# Typed parameters
@dataclass
class TaskFilters:
    status: str
    project: str | None
    sort_by: str

# Pure computation
def compute_task_stats(tasks: list[Any]) -> dict[str, int]:
    return {"total": len(tasks), "completed": ...}

def apply_task_filters(tasks: list[Any], ...) -> list[Any]:
    # ... filtering logic

def apply_task_sort(tasks: list[Any], sort_by: str) -> list[Any]:
    # ... sorting logic

# I/O helper
async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            return result
        return Result.ok(result.value or [])
    except Exception as e:
        return Errors.system(f"Failed to fetch tasks: {e}")

# Orchestrator
async def get_filtered_tasks(...) -> Result[tuple[list[Any], dict]]:
    tasks_result = await get_all_tasks(user_uid)
    if tasks_result.is_error:
        return tasks_result

    stats = compute_task_stats(tasks_result.value)
    filtered = apply_task_filters(tasks_result.value, ...)
    sorted_tasks = apply_task_sort(filtered, sort_by)

    return Result.ok((sorted_tasks, stats))

# Main route
@rt("/tasks")
async def tasks_dashboard(request):
    filters = parse_task_filters(request)
    filtered_result = await get_filtered_tasks(...)

    if filtered_result.is_error:
        return BasePage(
            render_error_banner(f"Failed: {filtered_result.error}"),
            ...
        )

    tasks, stats = filtered_result.value
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

    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Choice title is required")

    if len(title) > 200:
        return Errors.validation("Title must be 200 characters or less")

    # Options validation (choices need at least 2 options)
    option1 = form_data.get("option1", "").strip()
    option2 = form_data.get("option2", "").strip()

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


async def create_choice_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
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
async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
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

**Correct approach:**
```python
# ✅ DO THIS - Split into focused functions

# Pure computation (no async, no mocks needed)
def compute_task_stats(tasks: list[Any]) -> dict[str, int]:
    return {"total": len(tasks), "completed": ...}

def apply_task_filters(tasks, project, status):
    # ... filtering logic
    return filtered_tasks

def apply_task_sort(tasks, sort_by):
    # ... sorting logic
    return sorted_tasks

# Thin orchestrator (18 lines)
async def get_filtered_tasks(...) -> Result[tuple[list, dict]]:
    tasks_result = await get_all_tasks(user_uid)  # I/O
    if tasks_result.is_error:
        return tasks_result

    stats = compute_task_stats(tasks_result.value)  # Pure
    filtered = apply_task_filters(tasks_result.value, ...)  # Pure
    sorted_tasks = apply_task_sort(filtered, sort_by)  # Pure

    return Result.ok((sorted_tasks, stats))
```

**Complexity Reduction:** 90 lines → 18 lines (67% reduction)

---

### Mistake 4: Late Validation (Pydantic Only)

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
async def create_task_from_form(form_data: dict, user_uid: str):
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
async def create_task_from_form(form_data: dict, user_uid: str) -> Result[Any]:
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
async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
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
async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
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
- [ ] All errors use `render_error_banner()` (consistency)

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
- `/adapters/inbound/goals_ui.py` - Calendar-enabled variant
- `/adapters/inbound/choice_ui.py` - Form validation example

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
All 6 Activity domains use this pattern (100% coverage as of 2026-01-24):
- ✅ Tasks
- ✅ Goals
- ✅ Habits
- ✅ Events
- ✅ Choices
- ✅ Principles

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
