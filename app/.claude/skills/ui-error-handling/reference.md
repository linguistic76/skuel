# ui-error-handling Reference: Patterns, Examples & Anti-Patterns

> On-demand reference for the [`ui-error-handling`](SKILL.md) skill. SKILL.md holds the overview, core concepts (Result[T], error types, safe_form_string), decision trees, the testing checklist, and related docs; this file holds the code-heavy detail — Implementation Patterns, Real-World Examples, and the Common Mistakes & Anti-Patterns before/after recipes.

---

## Implementation Patterns

### Pattern 1: Declared Query Parameters

**Use when:** An Activity list takes filters (status, priority, category, sort)

The list names its filters on its `ActivityUIConfig` as `(name, default)` pairs. The factory
reads each from the query string, passes them positionally to the pure `filter_fn`, re-forwards
the non-default ones from the page shell to its content fragment, and pushes them back into the
URL (`HX-Push-Url`) so a filtered view survives a refresh:

```python
# adapters/inbound/goals_ui.py
config = ActivityUIConfig(
    domain_name="goals",
    filter_params=(("status", "active"), ("category", "all"), ("sort_by", "target_date")),
    get_all=goals_service.get_user_goals,
    filter_fn=filter_goals,   # filter_goals(goals, status, category, sort_by)
    ...
)
```

Outside the Activity lists, query parameters parse through
`adapters/inbound/route_factories/route_helpers.py` (`parse_bool_query_param`,
`parse_date_query_param`, `parse_csv_query_param`, `parse_pagination_params`).

---

### Pattern 2: The Generated Activity Routes

**Use when:** Building an Activity domain's list or detail pages

**Factory-centralized** (`adapters/inbound/activity_ui_factory.py`): `create_activity_ui_routes()` owns the fetch path for all 6 Activity domains — Result propagation, filtering, connection fetch and the error branch live in the factory's `_fetch_filtered()`, so a domain's `*_ui.py` carries no fetch boilerplate. It generates:

| Route | What it returns | On error |
|-------|-----------------|----------|
| `GET /{domain}` | Page shell inside the Tasks+ sidebar, with a loading placeholder | — (no fetch) |
| `GET /{domain}/content` | Filter bar + list + stats bar, under `id="{domain}-content"` | `render_error_banner(error.display_message)` under the same id |
| `GET /{domain}/list-fragment` | The filtered list only, plus `HX-Push-Url` | the banner under `id="{singular}-list"` |
| `GET /{domain}/detail` + its content fragment | The detail shell, then the owned entity | not-found / not-owned through the ownership read |

```python
# The content fragment's error branch — the shape every Activity list shares
error, all_items, filtered, connections_map, param_values = await _fetch_filtered(request)
if error is not None:
    return Div(render_error_banner(error.display_message), id=f"{domain}-content")
```

The create/edit POSTs stay in the domain's `*_ui.py` — see Example 2.

---

### Pattern 3: Pure Computation Helpers

**Use when:** Processing data (stats, filtering, sorting)

The Activity lists' computation is already pure and shared:

- `core/utils/entity_filters.py` — `filter_tasks`, `filter_goals`, `filter_habits`,
  `filter_events`, `filter_choices`, `filter_principles`: filter + sort, the `filter_fn` each
  `ActivityUIConfig` names.
- `core/utils/activity_stats.py` — `compute_task_stats`, `compute_goal_stats`, …: the typed
  stats each domain's stats bar renders (`ui/activities/`).

```python
def filter_tasks(
    tasks: list[Task],
    status_filter: str = "active",
    priority_filter: str = "all",
    sort_by: str = "priority",
) -> list[Task]:
    """Apply filters and sorting to a task list."""
```

A "today" inside such a helper is the user's day (`today_in(current_zone())`), never the host's.

**Key Features:**
- No `async` (pure computation)
- No `await` (no I/O)
- No service calls (testable with plain data)
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
        return await self.core.get_all_for_user(user_uid)

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

**In a caller** (the daily-planning intelligence reads it — `core/services/user/intelligence/daily_planning.py`; the Activity list pages use the factory's `get_all` + `filter_fn` instead):
```python
result = await tasks_service.get_filtered_context(user_uid, status_filter=status_filter, sort_by=sort_by)
if result.is_error:
    return Result.fail(result)
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

### Pattern 5: A Hand-Written Page Route

**Use when:** A page outside the generated Activity routes fetches its own data

The shell renders at once inside the page chrome; its content fragment fetches, checks the
`Result` before touching `.value`, and answers under the placeholder's `id` either way — so a
failure lands where the content would have, and navigation still works:

```python
# adapters/inbound/exercises_ui.py
@app.get("/exercises/content")
@ui_boundary_handler("Error loading exercises", fragment_id="exercises-content")
async def exercises_content_fragment(request: Request) -> FT:
    """HTMX fragment: the caller's own exercises — a failed read says so."""
    user_uid = require_authenticated_user(request)
    result = await exercises_service.list_user_exercises(user_uid)
    if result.is_error:
        return Div(render_error_banner("Error loading exercises"), id="exercises-content")
    return Div(render_exercises_list(result.value), id="exercises-content")
```

The shell (`GET /exercises`) is a `BasePage` holding
`content_loading_placeholder("/exercises/content", "exercises-content")`.
`@ui_boundary_handler` catches what escapes the handler and renders the same banner under the same
id.

---

### Pattern 6: HTMX Fragment Route

**Use when:** Returning a fragment that HTMX swaps into a target

Return the error under the target's `id`, so it lands where the content would have — never a
full page inside a fragment:

```python
if result.is_error:
    return Div(render_inline_error("Could not load data"), id="content-section")
```

---

### Pattern 7: Form Binding

**Use when:** A POST takes a form

Bind the whole form to the domain's Pydantic request model with `parse_form_body` and render the
failure's `display_message` above the re-rendered form — see Example 2. Field and cross-field
rules live on the model (`Field` constraints, validators), so every door that binds the model —
the form, the JSON API, the vault — enforces the same rule. There is no separate
`validate_*_form_data()` layer.

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
        render_error_banner(result.expect_error().display_message),
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
    result = await services.user.list_users(...)
    if result.is_error:
        return stats, True
    # ... populate stats ...
    return stats, False
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

**Applied to:** no live endpoint composes several intelligence calls into one fragment today; the pattern is the reference for the next multi-call fragment

---

## Real-World Examples

### Example 1: Tasks List (Generated Routes)
**Files:** `/adapters/inbound/tasks_ui.py`, `/adapters/inbound/activity_ui_factory.py`

```python
# adapters/inbound/tasks_ui.py — the domain supplies data, filters and components
config = ActivityUIConfig(
    domain_name="tasks",
    domain_singular="task",
    page_title="Tasks",
    filter_params=(("status", "active"), ("priority", "all"), ("sort_by", "priority")),
    get_all=tasks_service.get_user_tasks,
    get_owned=tasks_service.verify_ownership,
    backend=connection_fetch_backend,
    filter_fn=filter_tasks,
    link_label=NeoLabel.TASK,
    filter_config=FILTER_CONFIGS["tasks"],
    list_component=TaskList,
    stats_component=TaskStatsBar,
    detail_component=TaskDetailView,
    create_href="/tasks/create",
)
create_activity_ui_routes(app, rt, config)
```

The factory's content fragment checks the fetch's `Result`, renders a banner under
`id="tasks-content"` on failure, and otherwise returns the filter bar, the filtered list and the
stats bar (computed over the unfiltered set).

**Pattern:** Declared params, pure helpers, one generated error branch

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
# ✅ DO THIS — the service already returns a Result; the route shows its failure
result = await tasks_service.get_user_tasks(user_uid)
if result.is_error:
    return Div(render_error_banner(result.expect_error().display_message), id="tasks-content")
tasks = result.value
```

No wrapper helper and no broad `try`: the service turned its failures into the `Result`, and
SKUEL017 rejects an unannotated `except Exception`.

---

### Mistake 2: Accessing .value Without Error Check

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
result = await tasks_service.get_user_tasks(user_uid)
tasks = result.value  # None on failure — the page renders "no tasks" or crashes later
return TaskList(tasks)
```

**Problems:**
- Crashes on error (AttributeError or similar)
- No user-visible error message
- Poor UX (white screen of death)

**Correct approach:**
```python
# ✅ DO THIS
result = await tasks_service.get_user_tasks(user_uid)

# CHECK FIRST
if result.is_error:
    return Div(render_error_banner(result.expect_error().display_message), id="tasks-content")

# Extract .value only after error check
return TaskList(result.value)
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

**Correct approach — split the I/O from the computation:**
```python
# ✅ DO THIS — the service fetches; pure functions filter, sort and count
result = await tasks_service.get_user_tasks(user_uid)        # I/O, Result[list[Task]]
if result.is_error:
    return Div(render_error_banner(result.expect_error().display_message), id="tasks-content")
all_tasks = result.value
filtered = filter_tasks(all_tasks, status_filter, priority_filter, sort_by)   # pure
stats = compute_task_stats(all_tasks)                                         # pure
```

For the Activity lists this split is already the factory's (`get_all` + `filter_fn` + the stats
bar); a service that needs all three in one call uses `build_filtered_context()`
(`core/services/filtered_context.py`, Pattern 4).

---

### Mistake 4: Validating Beside the Request Model

**Why it's wrong:**
```python
# ❌ DON'T DO THIS — a bespoke validator the other doors never run
def validate_task_form_data(form_data: dict) -> Result[None]:
    if not form_data.get("title"):
        return Errors.validation("Task title is required")
    ...
```

**Problems:**
- The JSON API and the vault bind the same request model and never see this rule
- Two statements of one rule drift apart
- The form route grows a validation layer the model already has

**Correct approach:**
```python
# ✅ DO THIS — the rule lives on the model; the route renders the failure
parsed = await parse_form_body(request, TaskCreateRequest)
if parsed.is_error:
    content = Div(
        PageHeader("New Task"),
        render_error_banner(parsed.expect_error().display_message),
        TaskCreateForm(),
        cls="space-y-6",
    )
    return render_activity_sidebar_page(content, active="tasks", request=request)
```

A rule the user must be able to read goes on the model as a `Field` constraint or a validator,
with a message written for the user.

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
    return render_error_banner(third_result.expect_error().display_message)  # Only this one is correct
```

**Problems:**
- Inconsistent UX (different styles for same concept)
- Some errors miss styling (just plain text)
- Hard to find all error rendering code

**Correct approach:**
```python
# ✅ DO THIS - Always use render_error_banner, with the error's safe message
if result.is_error:
    return render_error_banner(result.expect_error().display_message)

if other_result.is_error:
    return render_error_banner("Failed to process your request")
```

**Consistency:** All errors use same component (alert, emoji, styling)

---

### Mistake 6: Forgetting to Log Errors

**Why it's wrong:**
```python
# ❌ DON'T DO THIS
result = await tasks_service.get_user_tasks(user_uid)
if result.is_error:
    return render_error_banner("Failed to load tasks")  # nothing in the logs says why
```

**Problems:**
- No debugging info (can't trace failures)
- No context (which user? what operation?)
- Silent errors (only user sees message)

**Correct approach:**
```python
# ✅ DO THIS — log the error with its context, then render the safe message
result = await tasks_service.get_user_tasks(user_uid)
if result.is_error:
    error = result.expect_error()
    logger.warning(
        "Failed to load tasks",
        extra={"user_uid": user_uid, "error_code": error.code, "error": error.message},
    )
    return render_error_banner(error.display_message)
```
