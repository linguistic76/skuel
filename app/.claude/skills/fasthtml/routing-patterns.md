# FastHTML Routing Patterns

Every route named here is registered in SKUEL — check a new example against the runtime
catalog before writing it (`uv run python scripts/health/route_claims.py --file <this file> --fences`).

## SKUEL API Conventions

SKUEL routes take two shapes, and both are live on API and UI routes alike:

```python
# 1. Query-param read — CRUD reads, lists and filters. This is the CRUDRouteFactory
#    shape (/api/{domain}/get, /update, /delete) and the page shape (/tasks/detail?uid=).
@rt("/api/tasks/get")
async def get_task(request: Request, uid: str):        # uid from ?uid=...
    ...

# 2. Path-uid door — a per-entity action or a related-set read. This is the
#    create_activity_field_api_routes shape (POST /api/{domain}/{uid}/status), the
#    lateral / hierarchy families (/api/tasks/{uid}/lateral/*, /tasks/{uid}/dependencies)
#    and reads like GET /api/path-steps/{uid}/organizers.
@rt("/api/tasks/{uid}/status", methods=["POST"])
async def update_status(request: Request, uid: str):   # uid from the path
    ...
```

**Which shape to use:** a CRUD-factory read or a list is a query parameter (`/api/tasks/get?uid=`,
`/api/user-entries/get?uid=`, `/gradebook/lines?status=&source=`); a door onto one entity —
a write or a related-set read — is a path segment (`POST /api/tasks/{uid}/priority`,
`POST /api/ku/{uid}/mark-studying`, `PATCH /api/goals/{uid}`, `GET /api/path-steps/{uid}/organizers`,
`GET /api/teaching/review/{uid}`). Measured on the runtime catalog: 186 of the 598 API paths carry a
path parameter (2026-09-20; re-measure by dumping `runtime_route_table()`). Do not add a
CRUD read in the path-uid shape — there is no `GET /api/tasks/{uid}`.

**Why query params for reads:**
- Type hints provide automatic parameter extraction (`uid: str` binds from `?uid=`)
- Cleaner route definitions (no `request.path_params["uid"]`)
- One shape for `get` / `update` / `delete` across all `CRUDRouteFactory` domains

## Route Decorator Behavior

### Basic Routing

SKUEL always passes an explicit path — function-name routing (`@rt` with no argument) is
not used, and the `@app.get(...)` spelling survives in two files only (`analytics_ui.py`,
`exercises_ui.py`; `grep -rn '@app.get(' adapters/inbound/`).

```python
from adapters.inbound.fasthtml_types import Request, RouteDecorator

# Bare @rt(path) registers GET, HEAD and POST — fast_app()'s default
@rt("/tasks")
async def tasks_page(request: Request): ...

# Method-specific — the norm for any mutation
@rt("/tasks/create", methods=["GET"])
async def task_create_form(request: Request): ...

@rt("/tasks/create", methods=["POST"])
async def task_create(request: Request): ...
```

⚠ A bare `@rt(path)` page handler can SHADOW its CSRF-protected POST twin on the same
path — always pass explicit `methods=` when a path serves more than one verb
(`scripts/audit_route_security.py` guards this).

### HTTP Method Specificity

```python
@rt("/api/path-steps/organize", methods=["POST"])
async def organize_route(request: Request): ...

@rt("/api/reports/{report_uid}/download", methods=["GET"])
async def download_report_file(request: Request, report_uid: str): ...

@rt("/api/transcriptions/delete", methods=["DELETE"])
async def delete_transcription(request: Request, uid: str): ...

@rt("/api/goals/{uid}", methods=["PATCH"])              # inline title edit (HierarchyRouteFactory)
async def update_node(request: Request, uid: str): ...

@rt("/api/path-steps/tags", methods=["DELETE", "POST"])  # two verbs, one path
async def tags_route(request: Request): ...
```

There is no `PUT` route in SKUEL; updates are `POST /api/{domain}/update` or the field door.

### Function Name Conventions

FastHTML can derive the method from a handler named `get`/`post`/`put`/`delete`. SKUEL
does not use it — every handler has a descriptive name. The convention is `methods=` on
every mutation and a bare `@rt(path)` (GET, HEAD and POST) only for reads; it is a
convention, not yet an invariant — 287 registrations are bare against 216 with `methods=`,
and 18 of the bare ones are CSRF-protected mutations (`/settings/save`, `/jupyter/save`,
`/api/admin/users/hard-delete`, `/askesis/api/submit`, …) that ride the default GET+POST
(`grep -rn -A1 -E '@rt\("[^"]+"\)$' adapters/inbound/*.py | grep -c csrf_protected`,
2026-09-20). What IS enforced is the shadowing rule below.

## Path Parameters

### Type Conversion

SKUEL registers **no Starlette converter** — no `{id:int}`, `{amount:float}`, `{x:uuid}`
anywhere in `adapters/inbound/`. The only converter spelling in the tree is `fast_app()`'s
own static catch-all (`{fname:path}.{ext:static}`), which bootstrap strips and replaces with
one `app.mount("/static", StaticFiles(...))`. Coercion comes from the handler annotation:

```python
# Nearly every path parameter is a `str` uid
@rt("/explore/ps/{uid}")
async def ps_detail(request: Request, uid: str): ...

@rt("/api/tasks/{uid}/lateral/{relationship_type}/{target_uid}", methods=["DELETE"])
async def delete_lateral_relationship(request: Request, uid: str, relationship_type: str, target_uid: str): ...

# The calendar and journal period routes annotate ints and FastHTML coerces them
@rt("/cal/month/{year}/{month}")
def calendar_month(request: Request, year: int, month: int): ...

@rt("/journals/monthly/{year}/{month}")
async def journal_monthly_note(request: Request, year: int, month: int): ...
```

A non-numeric `{year}` on an `int` parameter is a **404** from parameter extraction, before
the handler runs (FastHTML treats an uncoercible required parameter as missing; measured with
a `TestClient` on a bare `fast_app()`) — not the 400 that `install_request_validation_guard`
gives a rejected Pydantic body.

## Query Parameters

### Basic Usage

```python
# Type-annotated params bind from the query string
@rt("/api/tasks/get")
async def get_task(request: Request, uid: str): ...
# GET /api/tasks/get?uid=task_abc

# Optional with defaults
@rt("/gradebook/lines")
async def gradebook_lines(request: Request, status: str = "all", source: str = "all"): ...
# GET /gradebook/lines            → both defaults
# GET /gradebook/lines?status=pending
```

### Type Coercion — two live mechanisms, two failure codes

FastHTML coerces an annotated query parameter itself (`limit: int = 10`), and an uncoercible
value is a **404** before the handler runs (measured with a `TestClient` on a bare
`fast_app()`; a missing value takes the default). Thirteen handlers rely on that
(`ai_routes.py`'s `limit: int`, the calendar fragments —
`grep -rnE 'request: Request[^)]*: (int|float|bool)\b' adapters/inbound/`). The SKUEL shape
for a parameter that carries validation — a range, a date format, a CSV list, a bool
spelling — is a `route_factories/route_helpers.py` parser, which answers a **400**
(`ErrorCategory.VALIDATION`) with the field named, never a silent default (36 call sites):

```python
from adapters.inbound.route_factories.route_helpers import (
    parse_bool_query_param, parse_int_query_param, parse_pagination_params,
)

@rt("/api/context/dashboard")
@boundary_handler()
async def get_context_dashboard_route(request: Request) -> Result[ContextDashboard]:
    params = dict(request.query_params)
    include_predictions = parse_bool_query_param(params, "include_predictions", default=True)
    # GET /api/context/dashboard?include_predictions=false
    ...

@rt("/api/path-steps/root-organizers")
@boundary_handler()
async def list_root_organizers_route(request: Request) -> Result[list[RootOrganizerResult]]:
    params = dict(request.query_params)
    limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
    # GET /api/path-steps/root-organizers?limit=20
    ...
```

### Enum Constraints

FastHTML ships `str_enum` for constrained query values; SKUEL does not use it. Enum-valued
parameters are the domain `StrEnum`s resolved at the boundary with `from_string()` (aliases
are input-only — see CLAUDE.md § Naming Conventions, Emission rule), and an unknown value is
refused as a validation error, not a 404.

## Parameter Sources

FastHTML searches for parameters in order:
1. Path parameters
2. Query parameters
3. Cookies
4. Headers
5. Session
6. Form data

```python
@rt("/api/tasks/{uid}/status", methods=["POST"])
async def update_field(request: Request, uid: str):   # uid: path — request: the Starlette request
    user_uid = require_authenticated_user(request)     # session, read through the auth helper
    form = await request.form()                        # form data, read explicitly
    ...
```

Handlers annotate `request: Request` from `adapters.inbound.fasthtml_types` (SKUEL020 /
SKUEL035) and read the session through `require_authenticated_user(request)` — never a bare
`sess` parameter.

## Route References & URL Generation

FastHTML can build a URL from a handler (`handler.to(...)`) and accept a handler as a form
`action`. SKUEL uses neither — URLs are f-strings on registered paths, so the catalog can
check them:

```python
# Redirect after a successful create — always a 303 to the query-param detail page
return RedirectResponse(f"/tasks/detail?uid={result.value.uid}", status_code=303)

# HTMX attributes point at registered fragment routes
Div(hx_get=f"/learning-loop/ps/{uid}/exercises", hx_trigger="load", hx_swap="outerHTML")
```

## Modular Routes — DomainRouteConfig, not APIRouter

FastHTML's `APIRouter` is not used. A domain's routes live in `adapters/inbound/{domain}_routes.py`
and are registered by a wiring function with one canonical signature, called from bootstrap:

```python
# adapters/inbound/transcription_routes.py
TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,   # registers /api/transcriptions/*
    ui_factory=None,                               # API-only domain
    api_related_services={},
)


def create_transcription_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Services | None, _sync_service: Any = None
) -> None:
    register_domain_routes(app, rt, services, TRANSCRIPTION_CONFIG)
```

See the `domain-route-config` skill for the three wiring patterns.

## Request Object Access

```python
@rt("/library/exercises")
async def library_exercises(request: Request):
    user_uid = require_authenticated_user(request)
    method = request.method
    path = request.url.path
    query = request.query_params
    is_htmx = request.headers.get("HX-Request")
    ...
```

## Exception Handlers

SKUEL installs two exception handlers, both on the parameter-extraction seam (a body is
parsed BEFORE the handler and before any route guard runs):

```python
# adapters/inbound/boundary.py — called from bootstrap
install_malformed_json_guard(app)          # JSONDecodeError → 400
install_request_validation_guard(app)      # pydantic.ValidationError → 400
```

No `exception_handlers=` is passed to `fast_app()`. After that seam the two route kinds
have two boundaries: an API handler returns `Result[T]` and `@boundary_handler()` converts
it to the HTTP response (a non-`Result` value passes through unchanged); a UI or HTMX
handler returns FT nodes and `@ui_boundary_handler()` renders an unexpected exception as an
error banner fragment, never a JSON body (both in `adapters/inbound/boundary.py`; the
`ui-error-handling` skill has the UI side).

## Async Routes

Async for I/O, sync for computation (SKUEL029 rejects an `async def` with no `await`):

```python
# Sync — renders from already-loaded data
@rt("/cal/month/{year}/{month}")
def calendar_month(request: Request, year: int, month: int): ...

# Async — awaits a service
@rt("/explore/ps/{uid}")
async def ps_detail(request: Request, uid: str):
    result = await ps_service.get_step(uid)
    ...

# File uploads read the multipart form explicitly
@rt("/api/user-entries/upload", methods=["POST"])
async def upload_entry(request: Request):
    form = await request.form()
    uploaded_file = form.get("file")
    if not isinstance(uploaded_file, UploadFile):
        return Result.fail(Errors.validation("No file provided", field="file"))
    file_content = await uploaded_file.read()
    ...
```

## Middleware — not Beforeware

FastHTML's `Beforeware(before=...)` is not used. Cross-cutting request work is Starlette
middleware appended in bootstrap (`AuthContextMiddleware` inside the session middleware,
`RequestTimingMiddleware`, `RequestIDMiddleware`), and per-route gates are decorators:
`require_authenticated_user(request)` inside the handler, `@require_admin(get_user_service)`
/ `@require_teacher(...)` / `@require_role(...)` on it, `@csrf_protected` on every mutation.
See the `security` skill and `/docs/patterns/AUTH_PATTERNS.md`.

## Common Patterns

### Redirect After POST

```python
@rt("/tasks/create", methods=["POST"])
async def task_create(request: Request):
    user_uid = require_authenticated_user(request)
    ...
    return RedirectResponse(f"/tasks/detail?uid={result.value.uid}", status_code=303)
```

### Shell page + content fragment (instead of sniffing HX-Request)

The default page shape is a shell route that renders immediately and a sibling content
route the shell loads over HTMX — `/tasks` + `/tasks/content`, `/explore/ps/{uid}` +
`/explore/ps/{uid}/content` (`/docs/patterns/SHELL_FIRST_PAGE_PATTERN.md`). A handler that
answers both a full page and a fragment from one path does exist (`/library/exercises`
returns the fragment when `HX-Request` is set) but is the exception, not the pattern.

### Factory-registered routes

Routes are registered in loops by the route factories — one spec, one registration per
domain or per field:

```python
# adapters/inbound/route_factories/activity_field_api_factory.py
def create_activity_field_api_routes(rt: RouteDecorator, config: ActivityFieldApiConfig[T]) -> None:
    """Register ``POST /api/{domain}/{uid}/{field}`` routes for one domain."""
    for spec in config.fields:
        _register_field_route(rt, config, spec)   # → /api/tasks/{uid}/status, /api/tasks/{uid}/priority
```

⚠ Never collect routes in a list and register them later — `@rt()` registers on definition
(`/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`).
