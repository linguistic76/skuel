---
title: Route Decorator Architecture
updated: '2026-02-08'
category: patterns
related_skills:
- fasthtml
- result-pattern
- domain-route-config
related_docs:
- /docs/architecture/ROUTING_ARCHITECTURE.md
- /docs/patterns/ROUTE_FACTORIES.md
- /docs/patterns/FASTHTML_ROUTE_REGISTRATION.md
- /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
---

# Route Decorator Architecture

*For MCF and anyone building routes in SKUEL*

## The Core Idea

Every API route in SKUEL follows one pattern — **two decorators stacked**:

```python
@rt("/api/tasks", methods=["POST"])
@boundary_handler(success_status=201)
async def create_task(request: Request, ...) -> Result[dict[str, Any]]:
    result = await service.create(...)
    if result.is_error:
        return result
    return Result.ok({"task": result.value})
```

That's it. `@rt` registers the route with FastHTML. `@boundary_handler` converts `Result[T]` to `JSONResponse`. The handler itself only deals with `Result` — never with status codes, never with response objects, never with try/except.

This is not an invention. It's how FastHTML is designed to be used: decorators handle infrastructure, handler functions handle domain logic.

---

## Why Two Decorators?

### What `@rt()` Does

FastHTML's `@rt()` decorator:
1. Registers the route with Starlette's route table
2. Inspects the function signature for automatic parameter extraction
3. Inspects the `return_annotation` and tries to use it as a response class

Point 3 is subtle and critical. If you write `-> dict[str, Any] | tuple[dict[str, Any], int]`, FastHTML sees `types.UnionType` and calls it as if it were a response class — which crashes:

```
TypeError: 'types.UnionType' object is not callable
```

### What `@boundary_handler()` Does

The `boundary_handler` decorator (`core/utils/error_boundary.py`) solves this by wrapping the handler:

```python
@wraps(func)
async def wrapper(*args, **kwargs):
    result = await func(*args, **kwargs)
    if isinstance(result, Result):
        return result_to_response(result, success_status)
    return result
```

It returns a `JSONResponse` — a Starlette `Response` subclass. When FastHTML sees an `isinstance(resp, Response)` result, it passes it through directly. The return annotation is never inspected. This is intentional Starlette/FastHTML design: if you return a `Response` object, the framework respects it.

### The Stack

```
HTTP Request
    │
    ▼
@rt("/path")              ← Registers route, extracts params
    │
    ▼
@boundary_handler()       ← Converts Result → JSONResponse
    │
    ▼
async def handler(...)    ← Pure business logic, returns Result[T]
    │
    ▼
JSONResponse              ← FastHTML passes through (it's a Response)
```

The handler never touches HTTP concerns. The decorators handle everything.

---

## How All Route Types Fit Together

SKUEL has four kinds of route files. They all use the same decorator pattern:

### 1. Route Factories (Generated Routes)

Factories generate routes from configuration. The handler code lives inside the factory class.

| Factory | What It Generates | File |
|---------|-------------------|------|
| CRUDRouteFactory | create, get, update, delete, list | `crud_route_factory.py` |
| StatusRouteFactory | activate, pause, complete, archive | `status_route_factory.py` |
| CommonQueryRouteFactory | by-status, by-category, active, recent | `query_route_factory.py` |
| IntelligenceRouteFactory | context, analytics, insights | `intelligence_route_factory.py` |
| AnalyticsRouteFactory | Custom analytics endpoints | `analytics_route_factory.py` |
| **LateralRouteFactory** | Blocking, prerequisites, alternatives, graph | `lateral_route_factory.py` |

Every generated handler uses `@boundary_handler()` internally. When you call `factory.register_routes(app, rt)`, you get properly decorated routes.

### 2. Domain API Routes (Hand-Written)

For domain-specific logic that factories can't generate:

```python
# adapters/inbound/tasks_api.py
@rt("/api/tasks/complete", methods=["POST"])
@boundary_handler(success_status=200)
async def complete_task(request: Request, uid: str) -> Result[dict[str, Any]]:
    ...
```

### 3. Domain UI Routes (HTML Responses)

UI routes return FastHTML components, not JSON. They use `@rt()` alone — no `@boundary_handler`:

```python
# adapters/inbound/tasks_ui.py
@rt("/tasks/{uid}")
async def task_detail(request: Request, uid: str):
    ...
    return await BasePage(content=content, title=task.title, request=request)
```

`BasePage` returns a FastHTML `FT` object that the framework renders to HTML.

### 4. Domain-Specific Lateral Routes (Specialized Relationships)

Beyond the generic lateral relationships (blocking, prerequisites, alternatives, complementary, siblings), some domains have unique relationship types:

| Domain | Relationship | Route |
|--------|-------------|-------|
| Habits | STACKS_WITH (habit chaining) | `/api/habits/{uid}/lateral/stacks` |
| Events | CONFLICTS_WITH (scheduling) | `/api/events/{uid}/lateral/conflicts` |
| Choices | CONFLICTS_WITH (value conflicts) | `/api/choices/{uid}/lateral/conflicts` |
| Principles | CONFLICTS_WITH (value tensions) | `/api/principles/{uid}/lateral/conflicts` |
| KU | ENABLES (learning unlocks) | `/api/ku/{uid}/lateral/enables` |

These live in `adapters/inbound/lateral_routes.py` and follow the same `@rt` + `@boundary_handler` pattern.

---

## The Wiring: How Routes Get Registered

Route registration follows a consistent composition pattern:

```
bootstrap.py
    │
    ├── create_tasks_routes(app, rt, services)
    │       │
    │       ├── tasks_api.py → @rt() + @boundary_handler() handlers
    │       │       │
    │       │       ├── CRUDRouteFactory.register_routes()
    │       │       ├── StatusRouteFactory.register_routes()
    │       │       ├── CommonQueryRouteFactory.register_routes()
    │       │       ├── IntelligenceRouteFactory.register_routes()
    │       │       └── Hand-written domain routes
    │       │
    │       └── tasks_ui.py → @rt() handlers (HTML responses)
    │
    ├── create_lateral_routes(app, rt, services)
    │       │
    │       ├── LateralRouteFactory × 9 domains (generic routes)
    │       └── Domain-specific lateral routes (conflicts, stacking, enables)
    │
    └── ... (all other domains follow the same pattern)
```

### File Naming Convention

| Tier | Purpose | Naming |
|------|---------|--------|
| Entry Point | Wiring factory | `{domain}_routes.py` |
| API Layer | JSON endpoints | `{domain}_api.py` |
| UI Layer | HTML rendering | `{domain}_ui.py` |

The entry point composes the API and UI layers. It receives the `Services` container and extracts what each layer needs.

---

## The Lateral Route System

Lateral routes are the within-domain relationship API — how entities of the same type relate to each other (blocking, prerequisites, alternatives).

### Architecture

```
lateral_routes.py (Orchestrator)
    │
    ├── LateralRouteFactory × 9
    │   (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP)
    │   │
    │   └── Generates per domain:
    │       ├── POST .../blocks          (create blocking)
    │       ├── GET  .../blocking         (get blockers)
    │       ├── GET  .../blocked          (get blocked-by)
    │       ├── POST .../prerequisites    (create prereq)
    │       ├── GET  .../prerequisites    (get prereqs)
    │       ├── POST .../alternatives     (create alternative)
    │       ├── GET  .../alternatives     (get alternatives)
    │       ├── POST .../complementary    (create complementary)
    │       ├── GET  .../complementary    (get complementary)
    │       ├── GET  .../siblings         (get siblings)
    │       ├── DELETE .../{type}/{target} (delete relationship)
    │       ├── GET  .../chain            (blocking chain - Phase 5)
    │       ├── GET  .../alternatives/compare (comparison - Phase 5)
    │       └── GET  .../graph            (Vis.js network - Phase 5)
    │
    └── Domain-specific routes (hand-written)
        ├── Habits: stacking
        ├── Events: scheduling conflicts
        ├── Choices: value conflicts
        ├── Principles: value tensions
        └── KU: enables / enabled-by
```

**14 generic routes × 9 domains = 126 routes** from a single factory class. Plus 11 domain-specific routes. That's 137 lateral API endpoints from two files.

### Why a Factory?

Without `LateralRouteFactory`, each domain would need ~14 hand-written route handlers. Across 9 domains, that's ~126 handlers — roughly 3,000 lines of nearly identical code. The factory generates all of them from 3 configuration values: `domain`, `lateral_service`, `entity_name`.

---

## The Handler Pattern

Every API handler follows the same structure:

```python
@rt("/api/{domain}/{uid}/lateral/blocks", methods=["POST"])
@boundary_handler(success_status=201)
async def create_blocking(
    request: Request,
    uid: str,
    target_uid: str,
    reason: str,
    severity: str = "required",
) -> Result[dict[str, Any]]:
    user_uid = require_authenticated_user(request)

    result = await service.create_blocking_relationship(
        blocker_uid=uid,
        blocked_uid=target_uid,
        reason=reason,
        severity=severity,
        user_uid=user_uid,
    )

    if result.is_error:
        return result          # Pass through service error

    return Result.ok({         # Wrap success
        "message": "Blocking relationship created",
        "blocker_uid": uid,
        "blocked_uid": target_uid,
    })
```

Three steps:
1. **Authenticate** — `require_authenticated_user(request)` returns `user_uid` or raises 401
2. **Delegate** — Call the service, get a `Result`
3. **Return** — Pass errors through, wrap successes in `Result.ok()`

The `@boundary_handler` maps error categories to HTTP status codes automatically:

| ErrorCategory | HTTP Status |
|---------------|-------------|
| VALIDATION | 400 |
| FORBIDDEN | 403 |
| NOT_FOUND | 404 |
| BUSINESS | 422 |
| DATABASE | 503 |
| INTEGRATION | 502 |
| SYSTEM | 500 |

POST routes that create resources use `@boundary_handler(success_status=201)`.

---

## FastHTML Alignment

This architecture is deliberately aligned with FastHTML's design philosophy:

### 1. Decorator Composition

FastHTML encourages `@rt()` as the primary way to register routes. Additional behavior layers on via decorators. This is the standard Python decorator pattern — no framework magic, no metaclasses, no registry objects.

### 2. Automatic Parameter Extraction

FastHTML inspects function signatures to extract parameters from query strings, path segments, and form data. Our handlers use type-hinted parameters (`uid: str`, `severity: str = "required"`) and FastHTML does the rest.

### 3. Response Passthrough

FastHTML's `_resp` function checks `isinstance(resp, Response)` first. If the handler returns a Starlette `Response`, FastHTML passes it through untouched. `@boundary_handler` exploits this intentionally — it always returns `JSONResponse`, which is a `Response` subclass.

### 4. Reduced Ceremony

Compare this SKUEL route:

```python
@rt("/api/tasks", methods=["POST"])
@boundary_handler(success_status=201)
async def create_task(request: Request, title: str, priority: str = "medium") -> Result[dict]:
    user_uid = require_authenticated_user(request)
    result = await service.create(title=title, priority=priority, user_uid=user_uid)
    if result.is_error:
        return result
    return Result.ok({"task": result.value})
```

With a typical Flask/Django equivalent:

```python
@app.route("/api/tasks", methods=["POST"])
def create_task():
    try:
        data = request.get_json()
        title = data.get("title")
        if not title:
            return jsonify({"error": "title required"}), 400
        priority = data.get("priority", "medium")
        user_uid = get_authenticated_user(request)
        if not user_uid:
            return jsonify({"error": "unauthorized"}), 401
        task = service.create(title=title, priority=priority, user_uid=user_uid)
        return jsonify({"task": task}), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": "internal error"}), 500
```

The SKUEL version has zero try/except, zero manual status codes, zero `jsonify()`, zero `request.get_json()`. FastHTML extracts parameters. `@boundary_handler` maps errors to HTTP. The handler is pure business logic.

---

## Key Files

| File | Purpose |
|------|---------|
| `core/utils/error_boundary.py` | `boundary_handler()`, `result_to_response()` |
| `core/infrastructure/routes/lateral_route_factory.py` | Generic lateral route generation (9 domains) |
| `adapters/inbound/lateral_routes.py` | Lateral route orchestrator + domain-specific routes |
| `core/infrastructure/routes/crud_route_factory.py` | CRUD route generation |
| `core/infrastructure/routes/intelligence_route_factory.py` | Intelligence route generation |
| `adapters/inbound/{domain}_routes.py` | Domain entry points |
| `adapters/inbound/{domain}_api.py` | Domain API handlers |
| `adapters/inbound/{domain}_ui.py` | Domain UI handlers |
| `scripts/dev/bootstrap.py` | Route registration orchestration |

## See Also

- [Routing Architecture](/docs/architecture/ROUTING_ARCHITECTURE.md) — Three-layer architecture (routes, services, persistence)
- [Route Factories](/docs/patterns/ROUTE_FACTORIES.md) — Factory reference (CRUD, Status, Query, Intelligence, Analytics)
- [Route Naming Convention](/docs/patterns/ROUTE_NAMING_CONVENTION.md) — File naming: `_routes.py`, `_api.py`, `_ui.py`
- [FastHTML Route Registration](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) — Critical anti-pattern: never use `routes = []` with `@rt()`
- [DomainRouteConfig Pattern](/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md) — Configuration-driven route registration
- [Error Handling](/docs/patterns/ERROR_HANDLING.md) — `Result[T]` pattern and `Errors` factory
- [Lateral Relationships Core](/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md) — Lateral relationship architecture
