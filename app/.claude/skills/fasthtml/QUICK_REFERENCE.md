# Fasthtml - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Route Shapes

### API mutation route (the full SKUEL stack)

```python
@rt("/api/insights/{uid}/dismiss", methods=["POST"])
@csrf_protected
@boundary_handler(success_status=200)   # 201 for creates
async def dismiss_insight(request: Request, uid: str) -> Result[FT]:
    user_uid = require_authenticated_user(request)
    result = await service.do_thing(uid, user_uid)
    if result.is_error:
        return Result.fail(result)
    return Result.ok(FragmentComponent())
```

**When to use**: Every state-changing API route — explicit `methods=["POST"]`, CSRF, boundary, `Result[FT]` fragment return (`Result[Any]` in a handler is a regression).

### Route registration — decorator registers IMMEDIATELY

```python
def create_domain_routes(app: Any, rt: Any, service: SomeService) -> None:
    @rt("/domain/dashboard")
    def domain_dashboard(request: Request): ...
    # NO routes = [] / routes.append(...) — @rt() already registered it
```

**When to use**: All route wiring. `routes = []` + `append` double-registers and is the documented anti-pattern (`docs/patterns/FASTHTML_ROUTE_REGISTRATION.md`).

### UI page route with layout wrapper

```python
page = BasePage(
    content,
    title="Tasks",
    page_type=PageType.STANDARD,   # CUSTOM = full-width, page manages layout
    request=request,
    active_page="tasks",
)
```

**When to use**: Every authenticated page. `BasePage` is async — always `await` it. Unauthenticated flows (login/register/landing) use `AuthPage(content, title=...)` — no navbar/chrome.

### FT component factory (typed boundary)

```python
def stat_card(*content: Any, cls: str = "") -> Any:  # boundary: fasthtml-elements
    return Div(*content, cls=f"rounded-lg border p-4 {cls}".strip())
```

**When to use**: Any FT helper. FastHTML ships no `py.typed`, so `*c: Any, **kwargs: Any` needs the `# boundary: fasthtml-elements` comment. The explicit `cls: str = ""` parameter + merge is the SKUEL024-safe shape — hardcoding `cls=` while splatting `**kwargs` raises `TypeError: multiple values for 'cls'`.

### Query params over path params (API convention)

```python
@rt("/api/tasks/get")            # ?uid=task_abc — preferred for APIs
def get_task(request: Request, uid: str): ...
```

**When to use**: All API routes. Path params (`/users/{uid}`) are for SEO-friendly UI routes only (`routing-patterns.md`). POST for all mutations.

---

## Key Infrastructure

### Typing the FastHTML boundary — `adapters/inbound/fasthtml_types.py`

- `Request` — re-exported concrete Starlette class. Handlers MUST annotate `request: Request`, never `request: Any` — FastHTML 400s "Missing required field: request" before any gate runs (SKUEL020).
- `RouteDecorator` / `FastHTMLApp` — Protocols for `rt`/`app` in wiring-function signatures.

### `boundary_handler(success_status=...)` — `adapters/inbound/boundary.py`

Converts a handler's `Result[FT]` into an HTTP response. Status conventions: POST create → 201, POST action → 200, GET/PUT/DELETE → 200.

### Auth + ownership — `adapters/inbound/auth`, `route_factories/route_helpers.py`

```python
user_uid = require_authenticated_user(request)                    # -> UserUID
err = await verify_entity_ownership(service, uid, user_uid, dom)  # API: error Result or None
entity, resp = await require_owned_entity(service, uid, user_uid, "Task")  # UI routes
found = require_found(result, "Entity", uid)                      # adapters/inbound/result_helpers.py
```

### Query-param validation — `route_factories/route_helpers.py`

`parse_bool_query_param`, `parse_date_query_param`, `parse_pagination_params` — GET params fail with 400; JSON bodies use Pydantic request models (422 on failure).

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `routes = []` / `routes.append()` with `@rt()` | Delete the list — the decorator registers on definition |
| `request: Any` in a handler → FastHTML 400 | `request: Request` from `adapters.inbound.fasthtml_types` (SKUEL020) |
| `@rt(path)` with no `methods=` defaults to **GET+POST** | Page handler can SHADOW its CSRF-protected POST twin — always pass explicit `methods=`; guarded by `scripts/audit_route_security.py` |
| Hardcoded `cls=` + `**kwargs` splat in an FT helper | `cls: str = ""` param + `cls=f"...base... {cls}".strip()` (SKUEL024) |
| `Result[Any]` return on a handler | `Result[FT]` (fragments), `Result[Goal]` (models), or `Response` (redirects) |
| Hand-assembled `<link>` tags / `NotStr` full documents | `BasePage`/`AuthPage` — CSS/JS load through `build_head()` |
| Path params on API routes | Query params (`/tasks/get?uid=...`); path params are UI/SEO only |
| Forgetting `await` on `BasePage(...)` | It's `async def` — returns a coroutine, not FT |
| Untyped `*c: Any, **kwargs: Any` without annotation | Add `# boundary: fasthtml-elements` (ASGI plumbing: `# boundary: fasthtml-app`) |
| Forward-reference unions `"Type" \| None` | Use `Optional["Type"]` |

---

**See Also**: [SKILL.md](SKILL.md) for detailed explanations
**See Also**: [routing-patterns.md](routing-patterns.md) for query-vs-path param rules and APIRouter
**See Also**: [components-reference.md](components-reference.md) for the FT component reference
**See Also**: `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` + ADR-020 for the registration pattern
