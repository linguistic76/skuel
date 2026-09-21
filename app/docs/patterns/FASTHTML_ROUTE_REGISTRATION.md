---
title: FastHTML Route Registration Pattern
updated: 2026-09-21
category: patterns
related_skills:
- domain-route-config
- fasthtml
related_docs:
- /docs/decisions/ADR-020-fasthtml-route-registration-pattern.md
---

# FastHTML Route Registration Pattern

**Critical pattern** — a route factory defines and decorates its handlers and returns
nothing; collecting the decorated handlers in a list leaves sub-routes unregistered (404).

## Quick Start

**Skills:** [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)

For hands-on implementation:
1. Invoke `@fasthtml` for route registration patterns
2. See [QUICK_REFERENCE.md](../../.claude/skills/fasthtml/QUICK_REFERENCE.md) for decorator patterns
3. **NEVER** use `routes = []` / `routes.append()` with `@rt()` decorator
4. Continue below for detailed anti-pattern explanation

**Related ADRs:** [ADR-020](../decisions/ADR-020-fasthtml-route-registration-pattern.md) - Investigation and decision rationale

---

## The Problem

A factory that collects its decorated handlers in a list registers its first route and
loses the sub-routes: the landing answers (401 behind auth), `/domain/section`-shaped
routes answer **404**, and nothing warns at startup. ADR-020 is the record of the incident
that established the rule (a hub's sub-routes 404ing while admin routes written without
the list worked) — the surface it names is gone; the rule is not.

---

## Root Cause

The broken shape is a list collection around `@rt()`:

```python
# BROKEN - causes 404 errors
def create_domain_routes(_app, rt, service, user_service):
    routes = []  # <-- This is the problem

    @rt("/domain")
    async def domain_dashboard(...): ...
    routes.append(domain_dashboard)  # <-- And this

    @rt("/domain/section")
    async def domain_section(...): ...
    routes.append(domain_section)  # <-- And this

    return routes  # <-- And this
```

The `@rt()` decorator registers routes immediately when applied. The additional list management interferes with proper route registration for sub-routes.

---

## Correct Pattern

```python
def create_domain_routes(_app, rt, service, user_service):
    """Create domain routes."""

    get_user_service = make_service_getter(user_service)

    @rt("/domain")
    @require_admin(get_user_service)
    async def domain_dashboard(request: Request, current_user: Any = None):
        ...

    @rt("/domain/section")
    @require_admin(get_user_service)
    async def domain_section(request: Request, current_user: Any = None):
        ...

    @rt("/domain/another")
    @require_admin(get_user_service)
    async def domain_another(request: Request, current_user: Any = None):
        ...

    logger.info("Domain routes registered")
    # No return statement needed
```

### Key Points

1. **No `routes = []`** - Don't create a list to collect routes
2. **No `routes.append()`** - Don't append decorated functions
3. **No `return routes`** - Don't return the list — not as `return [handler, …]`, not as `return []`
4. **Just define and decorate** - The `@rt()` decorator handles registration

### The rule holds at every layer

A route factory returns `None`, whatever its layer:

| Layer | Contract |
|-------|----------|
| `create_{domain}_api_routes` / `create_{domain}_ui_routes` | `DomainRouteConfig.api_factory` / `ui_factory` are `Callable[..., None]` |
| `register_domain_routes()` | returns `None`; a missing primary service is a warning and an early `return` |
| `register_routes(app, rt)` on the route-factory classes (`crud`, `query`, `intelligence`, `analytics`, `lateral`) | returns `None` |
| a single-route helper (`_register_*_route`, `create_knowledge_patterns_api_route`) | applies `rt(path)(handler)` as a statement and returns nothing |
| `create_{domain}_routes` in `*_routes.py` | returns `None`; bootstrap counts `app.routes` once for its summary log |

A test that needs the handler a factory registered captures it from a fake `rt`
(see `tests/unit/infrastructure/test_activity_field_api_factory.py`'s `_RouteRegistry`),
never from a return value.

---

## Anti-Pattern (Do NOT Use)

```python
# DO NOT USE THIS PATTERN
def create_domain_routes(_app, rt, service, user_service):
    routes = []  # DON'T

    @rt("/domain")
    async def domain_dashboard(...): ...
    routes.append(domain_dashboard)  # DON'T

    @rt("/domain/section")
    async def domain_section(...): ...
    routes.append(domain_section)  # DON'T

    return routes  # DON'T
```

---

## Why This Happens

FastHTML (built on Starlette) registers routes when the `@rt()` decorator is applied:

1. Decorator creates a route handler
2. Decorator registers it with the application's route table
3. Decorator returns the wrapped function

The return value can be captured, but doing so via list append appears to interfere with the registration process for sub-routes. The exact mechanism is unclear, but the empirical evidence is clear.

---

## Symptoms

If you see this pattern in your code and experience:

- Main route works (`/domain` → 401)
- Sub-routes fail (`/domain/section` → 404)
- No error messages during startup
- Decorators appear to apply correctly

**Check for the list collection anti-pattern.**

---

## Reference Implementations

**Working examples in the codebase:**

| File | Routes |
|------|--------|
| `adapters/inbound/admin_dashboard_ui.py` | `/admin`, `/admin/users`, `/admin/analytics` |
| `adapters/inbound/admin_routes.py` | Admin API routes |
| `adapters/inbound/tasks_routes.py` | Task domain routes |

No factory in `adapters/inbound/` collects handlers today — `grep -rn 'routes = \[\]'
adapters/inbound/` is the check (the one `routes.append` in the tree is Starlette's own
router list taking the `/ws/agent` `WebSocketRoute`, not this shape).

---

## Route Counting

A factory does not count its own routes — a count in a log line is not a reader of
a handler list, and a hand-maintained number drifts. `scripts/dev/bootstrap.py`
logs one summary after all wiring, from the application's own route table:

```python
route_count = len(getattr(app, "routes", []))
logger.info(f"Route wiring complete: {route_count} routes registered")
```

A per-factory log line, if wanted, names the surface without a count:
`logger.info("Domain routes registered")`.

---

## Page Wrapping Pattern (HTMX Consistency)

Another critical pattern: **all routes should return complete `Html` documents**, not just `Div` elements.

### Why This Matters

When routes return `Div`, FastHTML wraps them with default headers including HTMX 2.0.7. SKUEL standardizes on HTMX 1.9.10, so version mismatches cause navigation issues.

### Correct Pattern

```python
# GOOD: Return complete Html document via BasePage
from ui.layouts.base_page import BasePage

@rt("/tasks")
async def tasks_dashboard(request):
    content = build_task_content(...)
    return BasePage(content=content, title="Tasks", request=request, active_page="tasks")
```

### Incorrect Pattern

```python
# BAD: Returning Div gets wrapped with wrong HTMX version
@rt("/tasks")
async def tasks_dashboard(request):
    return Div(navbar, content)  # Navigation may break!
```

**Symptoms of wrong wrapping:**
- Navbar links reload but stay on same URL
- Navigation requires multiple clicks
- Some pages work, others don't

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical` for full documentation.

---

## See Also

- **Decision context:** [ADR-020](../decisions/ADR-020-fasthtml-route-registration-pattern.md) - Full investigation
- **FastHTML docs:** `/docs/llms.txt/fasthtml-llms.txt`
- **Route factories:** `/docs/patterns/ROUTE_FACTORIES.md`
- **Page layouts:** `/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical`
