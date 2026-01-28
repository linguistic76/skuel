---
title: FastHTML Route Registration Pattern
updated: 2026-01-15
status: current
category: patterns
tags:
- patterns
- fasthtml
- routes
- anti-pattern
- critical
related:
- ADR-020-fasthtml-route-registration-pattern.md
related_skills:
- fasthtml
---

# FastHTML Route Registration Pattern

**Critical pattern** - prevents real bugs that caused 404 errors in production.

**Decision context:** See [ADR-020](/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md) for the investigation details.

---

## The Problem

Finance Hub sub-routes were returning 404 errors:

| Route | Expected | Actual |
|-------|----------|--------|
| `/finance` | 401 (auth) | 401 (working) |
| `/finance/expenses` | 401 (auth) | **404 (broken)** |
| `/finance/budgets` | 401 (auth) | **404 (broken)** |

Meanwhile, Admin routes using the same decorator pattern all worked correctly.

---

## Root Cause

The broken routes used a list collection pattern:

```python
# BROKEN - causes 404 errors
def create_finance_routes(_app, rt, service, user_service):
    routes = []  # <-- This is the problem

    @rt("/finance")
    async def finance_dashboard(...): ...
    routes.append(finance_dashboard)  # <-- And this

    @rt("/finance/expenses")
    async def finance_expenses(...): ...
    routes.append(finance_expenses)  # <-- And this

    return routes  # <-- And this
```

The `@rt()` decorator registers routes immediately when applied. The additional list management interferes with proper route registration for sub-routes.

---

## Correct Pattern

```python
def create_domain_routes(_app, rt, service, user_service):
    """Create domain routes."""

    def get_user_service():
        return user_service

    @rt("/domain")
    @require_admin(get_user_service)
    async def domain_dashboard(request, current_user):
        ...

    @rt("/domain/section")
    @require_admin(get_user_service)
    async def domain_section(request, current_user):
        ...

    @rt("/domain/another")
    @require_admin(get_user_service)
    async def domain_another(request, current_user):
        ...

    logger.info("Domain routes registered")
    # No return statement needed
```

### Key Points

1. **No `routes = []`** - Don't create a list to collect routes
2. **No `routes.append()`** - Don't append decorated functions
3. **No `return routes`** - Don't return the list
4. **Just define and decorate** - The `@rt()` decorator handles registration

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

**Fixed files (were broken, now fixed):**

| File | Fix Applied |
|------|-------------|
| `adapters/inbound/finance_ui.py` | Removed routes list pattern |
| `adapters/inbound/finance_api.py` | Removed routes list pattern |
| `adapters/inbound/finance_routes.py` | Removed route counting logic |

---

## Route Counting Alternative

If you need to count routes for logging:

```python
def create_domain_routes(_app, rt, service, user_service):
    """Create domain routes."""

    @rt("/domain")
    async def domain_dashboard(...): ...

    @rt("/domain/section")
    async def domain_section(...): ...

    @rt("/domain/another")
    async def domain_another(...): ...

    # Log route count manually
    route_count = 3
    logger.info(f"Domain routes registered: {route_count}")
```

---

## Page Wrapping Pattern (HTMX Consistency)

Another critical pattern: **all routes should return complete `Html` documents**, not just `Div` elements.

### Why This Matters

When routes return `Div`, FastHTML wraps them with default headers including HTMX 2.0.7. SKUEL standardizes on HTMX 1.9.10, so version mismatches cause navigation issues.

### Correct Pattern

```python
# GOOD: Return complete Html document via layout function
from ui.layouts.activity_layout import create_activity_page

@rt("/tasks")
async def tasks_dashboard(request):
    content = build_task_content(...)
    return create_activity_page(content, domain="tasks", request=request)
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

- **Decision context:** [ADR-020](/docs/decisions/ADR-020-fasthtml-route-registration-pattern.md) - Full investigation
- **FastHTML docs:** `/docs/fasthtml-llms.txt`
- **Route factories:** `/docs/patterns/ROUTE_FACTORIES.md`
- **Page layouts:** `/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical`
