---
related_skills:
- result-pattern
- fasthtml
- ui-browser
- skuel-ui
- python
---

# SKUEL UI Error Handling

*Last updated: 2026-09-29*

**When to use this skill:** When building UI routes, handling `Result[T]` at boundaries, implementing error banners, creating form validation, or understanding how SKUEL propagates errors from services to UI.

---

## Overview

SKUEL uses a consistent error-handling pattern across all UI routes that makes failures **visible to users** instead of silently returning empty lists or ad-hoc error elements.

**Core Principle:** "Declared params, Result[T] propagation, visible error banners"

This pattern has three key components:
1. **Declared query parameters** — each Activity list names its filters as `(name, default)` pairs
2. **Result[T] propagation** from the service to the route, which checks `.is_error` before `.value`
3. **Error banner rendering** via `render_error_banner()` / `render_inline_error()` for user-visible failures

**Benefits:**
- User-visible errors (clear messages instead of empty lists)
- Full debuggability (error context in logs)
- Consistency (the 6 Activity domains share one generated route set)

**Applied to:** All 6 Activity domains + Teaching, KU, Admin, Insights, UserEntry, Exercises, Calendar, Form Submissions, LifePath, Analytics, Activity Review, Learning Loop

---

## Core Concepts

### 1. Result[T] Pattern for UI

At the UI boundary, we:
- Call a service method that returns `Result[T]` (never wrap it in a try/except of our own)
- Check `.is_error` in route handlers, before touching `.value`
- Render the error's `display_message` in a banner — the safe `user_message`, falling back to `message`
- Keep the fragment's target `id` on the error response, so HTMX swaps it where the content would go

**NOT this:**
```python
# ❌ Silent failure - returns empty list on error
async def get_tasks(user_uid):
    try:
        return (await tasks_service.get_user_tasks(user_uid)).value
    except Exception:
        return []  # User sees nothing, no debugging info
```

**DO this** (the shape `create_activity_ui_routes()` generates for every Activity list):
```python
result = await tasks_service.get_user_tasks(user_uid)
if result.is_error:
    return Div(
        render_error_banner(result.expect_error().display_message),
        id="tasks-content",
    )
tasks = result.value
```

A bare `except Exception` has no place here: the service already turned its failures into a
`Result`, and SKUEL017 rejects an unannotated broad catch (see `result-pattern` § Exception
Narrowing). An optional capability is a typed `None` checked before the call (`if service.ai is
None`), never an exception caught into a "basic mode".

### 2. Declared Query Parameters

An Activity list declares its filters on its `ActivityUIConfig` as `(name, default)` pairs; the
factory reads each from the query string and passes them positionally to a pure `filter_fn`:

```python
# adapters/inbound/tasks_ui.py
config = ActivityUIConfig(
    domain_name="tasks",
    filter_params=(("status", "active"), ("priority", "all"), ("sort_by", "priority")),
    get_all=tasks_service.get_user_tasks,
    filter_fn=filter_tasks,          # core/utils/entity_filters.py
    ...
)
```

Other routes parse query parameters with the shared helpers in
`adapters/inbound/route_factories/route_helpers.py`
(`parse_bool_query_param`, `parse_date_query_param`, `parse_csv_query_param`,
`parse_pagination_params`) — see `/docs/patterns/API_VALIDATION_PATTERNS.md`.

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
- **I/O**: the service method, returning `Result[T]`
- **Computation**: pure functions — filtering and sorting in `core/utils/entity_filters.py`
  (`filter_tasks`, `filter_goals`, …), stats in `core/utils/activity_stats.py`
  (`compute_task_stats`, …, read by the stats bars in `ui/activities/`)
- **Form parsing**: `parse_form_body` into the domain's Pydantic request model (§5)

**Benefits:**
- Testable without async mocks
- Clear separation of concerns
- Single Responsibility Principle

### 5. Form Parsing

A form route parses the whole form into its Pydantic request model — Pydantic is the one
validation layer. Shared body readers live in `adapters/inbound/form_helpers.py`:

- `parse_form_body(request, schema)` → `Result[T]` — form data into a Pydantic model. Empty strings become `None` (an unselected `<select>` posts `""`). A validation failure is `Result.fail` (VALIDATION).
- `parse_body(request, schema)` → `Result[T]` — reads the body by Content-Type (JSON, or a form encoding through `parse_form_body`); the reader at a door both API clients and HTMX forms reach (the CRUD factory's create/update, the admin account actions).
- `parse_json_body(request, schema)` → `Result[T]` — JSON body into a Pydantic model; JSON parse errors and `ValidationError` both become `Result.fail()`. An ownership-verified POST verifies the owner uid wherever it travels: a model field (`TrackHabitRequest.habit_uid` — parse, then `verify_entity_ownership`) or the query string (`POST /api/principles/link?uid=` — verify, then parse; that model's `target_uid` is the link *target*, admitted by the service that writes the edge). Read the route: a model's uid field is not always the owner. ⚠ A query parameter overrides a same-named field of a JSON body (FastHTML merges the query string into the parsed body before any helper reads it), so a body model never reuses a query parameter's name.
- `safe_form_string()`, `safe_form_int()`, `safe_form_bool()` — for the few routes that read a single raw field; each handles `str | UploadFile | None`.

```python
# adapters/inbound/tasks_ui.py — the create POST
parsed = await parse_form_body(request, TaskCreateRequest)
if parsed.is_error:
    content = Div(
        PageHeader("New Task"),
        render_error_banner(parsed.expect_error().display_message),
        TaskCreateForm(),
        cls="space-y-6",
    )
    return render_activity_sidebar_page(content, active="tasks", request=request)

result = await tasks_service.core.create_task(parsed.value, user_uid)
```

A crafted value outside an enum (`priority=evil`) fails the model's validation and renders as a
banner — a 400-class failure, never a 500. A client's datetime is an instant: the request model
types it `ClientDateTime` (`core/models/request_base.py`).

### 6. Raw Fields Bound to an Enum

When a route does read a raw field into an enum-typed value, `dict.get("field", "default")` does
NOT cover the empty string an unselected `<select>` posts — the key exists, so the default is
ignored and `""` reaches the enum:

```python
from adapters.inbound.form_helpers import safe_form_string

# ❌ WRONG — empty string passes through, crashes Pydantic
domain = form_data.get("domain", "personal")

# ✅ CORRECT — safe_form_string strips whitespace, `or` provides fallback for empty
domain = safe_form_string(form_data.get("domain")) or "personal"
```

Prefer binding the whole form to a request model (§5), which makes both problems Pydantic's.

---

## Decision Trees

### Handling Result[T] in Routes

```
Service returns Result[T]
├─ Is this a full page?
│  ├─ YES → Check .is_error, render error banner inside the page chrome (sidebar still works)
│  └─ NO → HTMX fragment?
│     ├─ YES → Return the banner (or render_inline_error) under the fragment's target id
│     └─ NO → Check .is_error, render full page error
│
└─ After error check, extract .value for success case
```

### Choosing How a Page Loads Its Data

```
Need to fetch data for UI?
├─ An Activity domain list or detail page?
│  └─ Configure ActivityUIConfig — create_activity_ui_routes() generates the shell,
│     the content/list fragments and the detail pages, error branches included
│
├─ One service call?
│  └─ Call the facade method; check .is_error; render
│
└─ Several independent calls on one dashboard?
   └─ Collect each section's error separately and banner that section (reference.md
      Pattern 9) — one failing section must not blank the page
```

---

## Implementation Patterns, Examples & Anti-Patterns

The code-heavy detail lives in **[reference.md](reference.md)**:

- **Implementation Patterns** — declared filter params, the generated Activity routes, pure computation helpers, full-page vs HTMX-fragment error rendering, per-section conditional banners.
- **Real-World Examples** — the FilteredContextProvider facade, type-safe route accessors, calendar typed params.
- **Common Mistakes & Anti-Patterns** — the paired ❌/✅ before-after recipes (silent failures, orchestration in routes, error banners, logging with context).

---

## Testing & Verification

### Checklist for Error Handling

When implementing error handling for a new domain:

- [ ] Every service call the route makes returns `Result[T]`, and no route wraps one in a broad `try`
- [ ] All route handlers check `.is_error` before `.value`
- [ ] Error banners rendered for failures (not empty lists), with the error's `display_message`
- [ ] Errors logged with context (user_uid, operation, error details)
- [ ] An Activity list's filters are declared `filter_params`, applied by a pure `filter_fn`
- [ ] Pure computation helpers extracted (testable without mocks)
- [ ] Forms bound to a Pydantic request model with `parse_form_body` — Pydantic is the one validator
- [ ] HTMX fragments return error banners under their target id (not full pages)
- [ ] A full page shows its chrome even on error (navigation still works)
- [ ] Dashboard helpers return `tuple[data, bool]` when partial failure matters
- [ ] Independent service calls use partial error collection (not fail-on-first)
- [ ] All errors use `render_error_banner()` (full-page) or `render_inline_error()` (HTMX fragments)

### Unit Testing Pure Helpers

```python
import pytest
from pydantic import ValidationError

from core.models.task.task_request import TaskCreateRequest
from core.utils.entity_filters import filter_tasks


def test_filter_tasks_active_drops_completed():
    """Pure function: plain data in, plain data out."""
    open_task = make_task(status=EntityStatus.ACTIVE)      # a test's own Task builder
    done_task = make_task(status=EntityStatus.COMPLETED)

    assert filter_tasks([open_task, done_task], status_filter="active") == [open_task]


def test_create_request_rejects_an_unknown_priority():
    """A crafted enum value is a validation failure, not a 500."""
    with pytest.raises(ValidationError):
        TaskCreateRequest.model_validate({"title": "x", "priority": "evil"})
```

**Key:** Pure functions are trivially testable (no async, no mocks, just data). The form rule
lives on the request model, so it is tested there — the route only renders the failure.

---

## Related Documentation

### Core Files
- `/adapters/inbound/tasks_ui.py` - Reference implementation (the `ActivityUIConfig` + the `parse_form_body` create/edit routes)
- `/adapters/inbound/goals_ui.py` - `render_error_banner()` for full-page not-found on create/edit
- `/adapters/inbound/teaching_ui.py` - Non-activity domain, sidebar pages
- `/adapters/inbound/learning_loop_routes.py` - HTMX fragments with `render_inline_error()` preserving target IDs
- `/adapters/inbound/user_entry_ui.py` - HTMX fragments: journal loading, download auth, file-not-found, submission history (unified submissions + journals surface, ADR-054)
- `/adapters/inbound/exercises_ui.py` - `render_error_banner()` for dashboard; edit/view refuse a foreign or missing uid through `refuse` (`render_inline_error()` body at 404, in the page shell for a navigation)
- `/adapters/inbound/habits_ui.py` - `render_inline_error()` for completion, patterns, goal analytics
- `/adapters/inbound/admin_dashboard_ui.py` - `render_error_banner()` for user-not-found, warning severity for partial failures
- `/adapters/inbound/insights_ui.py` - Error state with load-more pagination
- `/ui/analytics/life_path.py` - `EmptyState` for no Life Path; `/ui/analytics/life_summary.py` - `EmptyState` for no weekly data (delegated from `analytics_ui.py`)
- `/adapters/inbound/form_submissions_ui.py` - `render_error_banner()` for full-page, `EmptyState` for empty data
- `/ui/lifepath/vision.py` - `EmptyState` with CTA for no matching Learning Paths (delegated from `lifepath_ui.py`)

### Factory-Centralized Activity Error Handling (`/adapters/inbound/activity_ui_factory.py`)
- `create_activity_ui_routes()` owns fetch + Result propagation + the not-found path for all 6 Activity domains — generated fragments render `render_error_banner()`; routes never hand-roll these states.
- Calendar query params parse via `parse_date_query_param()` from `route_factories`.
- (The former `ui_helpers.py` shared-helper module was deleted 2026-08 with zero consumers.)

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

**Activity Domains** (generated by `create_activity_ui_routes()`):
- ✅ Tasks — reference implementation
- ✅ Goals, Habits, Events, Choices, Principles

**Non-Activity Domains** (render_error_banner standardized, 2026-03-18; render_inline_error for HTMX, 2026-03-19):
- ✅ Teaching (`teaching_ui.py`) — 10 error sites, fixed `.is_ok` → `.is_error` bug (SKUEL003)
- ✅ Learning Loop (`learning_loop_routes.py`) — `render_inline_error()` for HTMX fragments preserving target IDs (absorbed the former `study_ui.py` when Study was decomposed into entity-typed routes)
- ✅ UserEntry (`user_entry_ui.py`) — `render_inline_error()` for journal loading, download auth, file-not-found, submission history (unified submissions + journals surface, ADR-054)
- ✅ Exercises (`exercises_ui.py`) — `render_error_banner()` for dashboard; edit/view not-found is `refuse` → `render_inline_error()` at 404
- ✅ Habits (`habits_ui.py`) — `render_inline_error()` for completion, pattern analysis, goal system/velocity/impact
- ✅ Goals (`goals_ui.py`) — `render_error_banner()` for full-page not-found
- ✅ KU (`ku_ui.py`) — the two learning-state POSTs return the unchanged buttons on a failed `Result` (HTMX swap keeps the page consistent)
- ✅ Admin (`admin_dashboard_ui.py`) — `render_error_banner()` for user-not-found; warning banners for stats, system status
- ✅ Insights (`insights_ui.py`) — error banner on insights/stats load failure, load-more endpoint
- ✅ Finance (`finance_ui.py`) — typed context methods with Result[TypedDict]
- ✅ Calendar (`calendar_ui.py`) — grid fragments swap in `error_response()` (`ui/calendar/components.py`) on a failed view read; the reschedule POST re-renders `reschedule_form(..., error=message)` with the posted values — the VALIDATION reason verbatim, a plain retry line for anything else — because HTMX swaps 200s, not bare 4xx bodies
- ✅ Activities (`activities_ui.py`) — `render_inline_error()` for preview card loading
- ✅ Analytics (`ui/analytics/`) — `EmptyState` for no Life Path, no domain activity, no weekly data (delegated from `analytics_ui.py`)
- ✅ Form Submissions (`form_submissions_ui.py`) — `render_error_banner()` + `EmptyState` for empty data
- ✅ LifePath (`ui/lifepath/`) — `EmptyState` with CTA for no matching Learning Paths (delegated from `lifepath_ui.py`)
- ✅ Activity Review (`activity_review_ui.py` + `ui/activity_review/`) — `render_inline_error()` for missing UID, context builder

**Component exports:** `render_error_banner`, `render_inline_error` from `ui/patterns/error_banner.py`; `EmptyState` from `ui/patterns/empty_state.py`.

### Key Insights

**Why declared params?**
One place names a list's filters and their defaults; the page shell re-forwards them to the fragment

**Why pure helpers?**
Testable without mocks, Single Responsibility

**Why one validator?**
The request model states the rule once; every door that binds it enforces the same rule

**Why Result[T] propagation?**
Explicit error handling, no silent failures, full error context

**Philosophy:** "Errors are first-class citizens - make them visible, clear, and debuggable"
