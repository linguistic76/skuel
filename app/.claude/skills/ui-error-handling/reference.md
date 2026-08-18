# ui-error-handling Reference: Patterns, Examples & Anti-Patterns

> On-demand reference for the [`ui-error-handling`](SKILL.md) skill. SKILL.md holds the overview, core concepts (Result[T], error types, safe_form_string), decision trees, the testing checklist, and related docs; this file holds the code-heavy detail — Implementation Patterns, Real-World Examples, and the Common Mistakes & Anti-Patterns before/after recipes.

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

**Calendar params** parse via `parse_date_query_param()` from `route_factories`.

**Usage in route:**
```python
@rt("/tasks")
async def tasks_dashboard(request):
    filters = parse_filters(request)  # Type-safe access

    # Use filters.status, filters.project, filters.sort_by
```

---

### Pattern 2: I/O Helper with Result[T]

**Use when:** Fetching data from services (all data access)

**Factory-centralized** (`adapters/inbound/activity_ui_factory.py`): `create_activity_ui_routes()` owns the fetch path for all 6 Activity domains — Result propagation, `or []` defaulting, structured logging, and the error branch live in the factory's `_fetch_filtered()`, so routes carry no fetch boilerplate. (The former `ui_helpers.fetch_user_entities()` helper was deleted 2026-08 with zero consumers.)

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
result = await tasks_service.get_filtered_context(user_uid, status_filter, sort_by)
if result.is_error:
    return render_error_banner(result)
ctx = result.value
tasks: list[Task] = ctx["entities"]   # annotate to narrow: entities is list[Any]
stats = ctx["stats"]                  # dict[str, int | float]
```

**Key Features:**
- **Service owns orchestration** (not route-level helpers)
- **`ListContext` TypedDict** with `entities`, `stats: dict[str, int | float]`, `metadata`
- **`ListContext` is a TypedDict** — `entities`/`stats` always present, `metadata` optional (`ctx.get("metadata", {})`); annotate `entities` to narrow it from `list[Any]`
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
    if view == "analytics":
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
- Typed parameters (parse_task_filters)
- Error check BEFORE .value access
- Error banner with navigation (tabs still visible)
- Multi-view support (list/analytics)
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
- `render_error_banner()`: SKUEL `Alert` from `ui.components` (red background, error icon), severity variants via `AlertT`
- `render_inline_error()`: `text-error text-sm` with `role="alert"` + `aria-live="polite"`
- `role="alert"` is set automatically by `Alert` in render_error_banner (do NOT pass it as a kwarg — causes duplicate kwarg TypeError)

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
        result = await services.user.list_users(...)
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
- Independent partial results: N independent calls with a `partial_errors` list (see Pattern 10)

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

**Applied to:** historically the /profile intelligence HTMX endpoint (removed 2026-07-05 with the dead overview surface); the pattern remains the reference for any multi-call fragment

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

# Route consumes the TypedDict directly

@rt("/tasks")
async def tasks_dashboard(request):
    filtered_result = await tasks_service.get_filtered_context(user_uid, status_filter, sort_by)

    if filtered_result.is_error:
        return BasePage(render_error_banner(f"Failed: {filtered_result.error}"), ...)

    ctx = filtered_result.value
    tasks: list[Task] = ctx["entities"]   # annotate to narrow: entities is list[Any]
    stats = ctx["stats"]                  # dict[str, int | float]
    # ... render views
```

**Pattern:** Complete error handling with typed params, pure helpers, Result[T] propagation

---

### Example 2: Form Validation (Choices)
**File:** `/adapters/inbound/choices_ui.py` (create handler)

Bespoke `validate_*_form_data()` functions are gone. Form validation is
`parse_form_body(request, PydanticRequestModel)` — field rules live on the
Pydantic request model (`core/models/choice/choice_request.py`), and the
handler re-renders the form with an error banner on failure:

```python
from adapters.inbound.form_helpers import parse_form_body
from core.models.choice.choice_request import ChoiceCreateRequest
from ui.patterns.error_banner import render_error_banner

parsed = await parse_form_body(request, ChoiceCreateRequest)
if parsed.is_error:
    err = parsed.expect_error()
    content = Div(
        PageHeader("New Choice"),
        render_error_banner(err.display_message),
        ChoiceCreateForm(),
        cls="space-y-6",
    )
    return render_activity_sidebar_page(content, active="choices", request=request)
req = parsed.value  # validated ChoiceCreateRequest
```

**Pattern:** Pydantic request model owns the field rules; the route owns the error rendering

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
