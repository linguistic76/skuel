---
title: "Pattern: Shell-First Page Loading"
updated: 2026-07-11
status: current
category: patterns
tags: [ui, htmx, performance, page-load]
related: [docs/patterns/UI_COMPONENT_PATTERNS.md, docs/patterns/HUB_PAGE_PATTERN.md]
---

# Shell-First Page Loading Pattern

> Route handlers return page chrome immediately (zero DB calls). A `hx-trigger="load"` placeholder fires the content fragment once the browser has painted the shell.

```python
from ui.patterns.loading import content_loading_placeholder
```

`content_loading_placeholder` renders an `animate-pulse` skeleton shimmer (four bars at varying widths) while the fragment is in flight.  The `loading_text` arg is kept as a `sr-only` label for screen readers — it does not appear visually.

## Why

Before this pattern, route handlers blocked on Neo4j queries before returning any HTML. The browser showed a blank screen until the DB finished. Shell-first eliminates the blank screen: the navbar, sidebar, and page header appear in ~50ms regardless of DB latency. Content fills in shortly after.

## The Mechanical Transformation

**Before (blocks on DB):**
```python
@rt("/domain")
async def domain_page(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    result = await some_service.get_data(user_uid)   # BLOCKS — browser sees nothing
    return await SomeSidebarPage(Div(PageHeader(...), DataComponent(result.value)), ...)
```

**After (shell-first):**
```python
@rt("/domain")
async def domain_page(request: Request) -> Any:
    require_authenticated_user(request)               # auth only, no DB
    content = Div(
        PageHeader("Domain"),
        content_loading_placeholder("/domain/content", "domain-content"),
    )
    return await SomeSidebarPage(content, ...)        # returns in ~50ms

@rt("/domain/content")
async def domain_content_fragment(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    result = await some_service.get_data(user_uid)   # DB work here, after paint
    return Div(DataComponent(result.value), id="domain-content")
```

## Naming Conventions

| Page type | Shell route | Fragment route |
|-----------|-------------|----------------|
| List page | `GET /domain` | `GET /domain/content` |
| Detail (query param) | `GET /domain/detail` | `GET /domain/detail/content?uid=` |
| Detail (path param) | `GET /domain/{uid}` | `GET /domain/{uid}/content` |

## Shell Responsibilities

The shell does exactly four things:
1. Auth check (`require_authenticated_user`)
2. UID extraction from query/path params
3. Fast error for missing UID (no DB needed to know if `uid=""`)
4. Forwarding page-URL state (filter/query params) into the fragment URL

Everything else belongs in the fragment.

## The Query-Param Trap

The page URL and the fragment request are **two separate HTTP requests**. Any
state carried in the page URL (`/tasks?status=completed`) is invisible to the
fragment unless the shell explicitly re-forwards it into the fragment URL. A
hardcoded `content_loading_placeholder("/tasks/content", ...)` silently drops
the params and the fragment renders with defaults — links, bookmarks, and
refreshes of a filtered view all land on the default view instead.

This class of bug hides easily: it passes casual inspection whenever the
user's data happens to look right under the default filter (worked-by-
coincidence). The fix is a whitelist-forward in the shell:

```python
forwarded = {
    name: request.query_params[name]
    for name, _default in config.filter_params   # whitelist, not passthrough
    if name in request.query_params
}
fragment_url = f"/{domain}/content"
if forwarded:
    fragment_url = f"{fragment_url}?{urlencode(forwarded)}"
```

The inverse direction matters too: when a fragment applies user-chosen state
(e.g. the filter bar's `list-fragment`), it should sync the browser URL with
an `HX-Push-Url` response header pointing at the canonical *page* URL (never
the fragment URL — a refresh of a pushed fragment URL would render bare HTML):

```python
return config.list_component(filtered, connections_map), HttpHeader(
    "HX-Push-Url", page_url    # e.g. "/tasks?status=completed"
)
```

Both halves live in `adapters/inbound/activity_ui_factory.py` for the 6
Activity Domains.

## Fragment Responsibilities

The fragment does all the work the shell deferred:
- All service/DB calls
- Ownership verification
- Content rendering
- Error states (wrapped with `id=` so retry can re-target)

## Variants

### Detail page with query param UID

```python
@rt("/tasks/detail")
async def task_detail_page(request: Request) -> Any:
    require_authenticated_user(request)
    uid = request.query_params.get("uid", "")
    if not uid:
        return await render_activity_sidebar_page(
            Div(render_error_banner("Missing task UID")), active="tasks", request=request
        )
    content = Div(
        content_loading_placeholder(f"/tasks/detail/content?uid={uid}", "task-detail-content"),
    )
    return await render_activity_sidebar_page(content, active="tasks", request=request)

@rt("/tasks/detail/content")
async def task_detail_content_fragment(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    uid = request.query_params.get("uid", "")
    task_result = await tasks_service.get_task(uid)
    if task_result.is_error or task_result.value.user_uid != user_uid:
        return Div(render_error_banner("Task not found"), id="task-detail-content")
    task = task_result.value
    # connection_fetch_backend implements the ConnectionFetchOperations port (below the boundary, ADR-044)
    connections_map = await connection_fetch_backend.fetch_entity_connections(config, [task.uid])
    return TaskDetailView(task, connections_map.get(task.uid, []))
```

### Detail page with path param

```python
@rt("/explore/ku/{uid}")
async def explore_ku_detail(request: Request, uid: str) -> Any:
    content = content_loading_placeholder(f"/explore/ku/{uid}/content", "ku-detail-content")
    return await render_explore_sidebar_page(content=content, sidebar_data=None, request=request)

@rt("/explore/ku/{uid}/content")
async def explore_ku_content_fragment(request: Request, uid: str) -> Any:
    ku_result = await orchestrator.get_ku(uid)
    if ku_result.is_error:
        return Div(render_error_banner(f"Not found: {uid}"), ButtonLink("← Back", href="/explore"), id="ku-detail-content")
    return build_ku_main_column(ku_result.value, ...)
```

### Role-gated pages (teaching routes)

Apply `@require_role` to **both** shell and fragment:

```python
@rt("/teaching/students")
@require_role(UserRole.TEACHER, get_user_service)
async def teaching_students_page(request, current_user=None):
    content = Div(PageHeader("Students"), content_loading_placeholder("/teaching/students/content", "students-content"))
    return await render_teaching_sidebar_page(content, active="students", request=request)

@rt("/teaching/students/content")
@require_role(UserRole.TEACHER, get_user_service)
async def teaching_students_content_fragment(request, current_user=None):
    user_uid = require_authenticated_user(request)
    result = await orchestrator.get_students_summary(teacher_uid=user_uid)
    ...
```

## Notification Bell — Miniature Version

`_notification_badge_placeholder()` in `ui/layouts/navbar.py` is the same pattern applied to a navbar element:

```python
Div(
    _notification_button(0),          # renders 0-count immediately
    id="notification-bell",
    hx_get="/api/navbar/notification-badge",
    hx_trigger="load",
    hx_swap="outerHTML",
    cls="relative",
)
```

The `GET /api/navbar/notification-badge` fragment fetches the actual unread count and replaces the placeholder, so the navbar never blocks on a DB call.

## What This Pattern Does NOT Apply To

| Case | Reason |
|------|--------|
| POST mutation routes | Must return synchronous confirmation |
| Hub pages (`/home`, `/submissions`, `/gradebook`, `/library`) | Already use HTMX tab blocks |
| Fragment endpoints themselves | DB calls in fragments are expected and correct |
| Admin pages | Lower traffic; simpler blocking approach is fine |

## Pages Using This Pattern (as of 2026-04-08)

**Activity domain lists (6):** `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`

**Activity domain detail pages (6):** `/tasks/detail`, `/goals/detail`, `/habits/detail`, `/events/detail`, `/choices/detail`, `/principles/detail`

**Calendar (3):** `/events/month/{year}/{month}`, `/events/week/{date_str}`, `/events/day/{date_str}`

**Library (1):** `/library/path-steps`

**Pathways (4):** `/pathways`, `/pathways/browse`, `/pathways/path/{uid}`, `/pathways/analytics`

**LifePath (2):** `/lifepath`, `/lifepath/alignment`

**GradeBook detail (1):** `/activity-reports/detail`

**Other pages (10):** `/settings`, `/exercises`, `/exercises/get`, `/learning-paths`, `/teaching/students`, `/teaching/students/{uid}`, `/teaching/review/{uid}`, `/explore`, `/explore/ku/{uid}`, `/explore/ps/{uid}`

**Navbar:** notification bell placeholder (all authenticated pages)

## See Also

- `skuel-ui` skill → "Shell-First Page Loading — The Standard Pattern"
- `ui-browser` skill → "Shell-First Page Loading"
- `docs/patterns/HUB_PAGE_PATTERN.md` — OOB swaps for shared-data hub blocks (complementary pattern)
