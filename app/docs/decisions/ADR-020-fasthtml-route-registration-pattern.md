# ADR-020: FastHTML Route Registration Pattern

**Status:** Accepted
**Date:** 2025-12-07
**Category:** Pattern/Practice

## Context

Finance Hub sub-routes were returning 404 errors while the main `/finance` route worked correctly:
- `/finance` → 401 (working)
- `/finance/expenses` → 404 (broken)
- `/finance/budgets` → 404 (broken)
- `/finance/invoices` → 404 (broken)

Meanwhile, Admin routes using the same decorator pattern all worked:
- `/admin` → 401 (working)
- `/admin/users` → 401 (working)
- `/admin/analytics` → 401 (working)

## Investigation

Comparing the working Admin route files with the broken Finance route files revealed a key structural difference:

### Broken Pattern (Finance)

```python
def create_finance_ui_routes(_app, rt, finance_service, user_service):
    routes = []  # <-- Collecting routes

    @rt("/finance")
    @require_admin(get_user_service)
    async def finance_dashboard(...): ...
    routes.append(finance_dashboard)  # <-- Appending

    @rt("/finance/expenses")
    @require_admin(get_user_service)
    async def finance_expenses(...): ...
    routes.append(finance_expenses)  # <-- Appending

    # ... more routes ...

    return routes  # <-- Returning list
```

### Working Pattern (Admin)

```python
def create_admin_dashboard_routes(_app, rt, services):

    @rt("/admin")
    @require_admin(get_user_service)
    async def admin_overview(...): ...
    # No append, no list

    @rt("/admin/users")
    @require_admin(get_user_service)
    async def admin_users(...): ...
    # No append, no list

    # No return statement
```

## Decision

**Do NOT use `routes = []` / `routes.append()` / `return routes` pattern with FastHTML's `@rt()` decorator.**

The `@rt()` decorator registers routes immediately when applied. The additional list management somehow interferes with proper route registration, causing sub-routes to fail.

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

    logger.info("Domain routes registered")
    # No return statement needed
```

## Anti-Pattern (Do Not Use)

```python
def create_domain_routes(_app, rt, service, user_service):
    routes = []  # DON'T DO THIS

    @rt("/domain")
    async def domain_dashboard(...): ...
    routes.append(domain_dashboard)  # DON'T DO THIS

    return routes  # DON'T DO THIS
```

## Files Changed

| File | Change |
|------|--------|
| `adapters/inbound/finance_ui.py` | Removed routes list pattern |
| `adapters/inbound/finance_api.py` | Removed routes list pattern |
| `adapters/inbound/finance_routes.py` | Removed route counting logic |

## Implementation

**Related Skills:**
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md) - FastHTML route registration patterns

**Pattern Documentation:**
- [FASTHTML_ROUTE_REGISTRATION.md](/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md) - Route registration patterns

**Code Locations:**
- `/adapters/inbound/` - All route files (no `routes = []` pattern)
- `/scripts/dev/bootstrap.py` - Route registration orchestration

---

## Consequences

### Positive
- Finance Hub routes now work correctly
- Consistent pattern across all route files
- Simpler code without unnecessary list management

### Negative
- Cannot programmatically count registered routes (use logging instead)
- Route factory callers cannot capture return values (not needed anyway)

## Technical Note

FastHTML (built on Starlette) registers routes when the `@rt()` decorator is applied. The decorator:
1. Creates a route handler
2. Registers it with the application's route table
3. Returns the wrapped function

The return value can be captured, but doing so via list append appears to interfere with the registration process in certain scenarios. The exact mechanism is unclear, but the empirical evidence is clear: routes work without the list pattern and fail with it.

## Related

- **Implementation guide:** `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` - How to avoid this anti-pattern
- `adapters/inbound/admin_dashboard_ui.py` - Reference implementation (working pattern)
- `adapters/inbound/admin_routes.py` - Reference implementation (working pattern)
