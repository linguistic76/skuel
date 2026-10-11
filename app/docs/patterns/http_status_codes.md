---
title: HTTP Status Codes - REST Best Practices
updated: 2026-10-11
category: patterns
related_skills: []
related_docs: []
---

# HTTP Status Codes - REST Best Practices

## Quick Reference

SKUEL follows REST/HTTP best practices for status codes, using 201 for resource creation and 200 for actions/operations.

## Core Principle: "Use correct HTTP status codes for semantic clarity"

**SKUEL follows REST/HTTP best practices for status codes:**

| Operation | Success Status | When to Use |
|-----------|---------------|-------------|
| **POST (Create)** | 201 Created | Resource successfully created and persisted |
| **GET** | 200 OK | Resource retrieved successfully |
| **PUT** | 200 OK | Resource updated successfully |
| **DELETE** | 200 OK | Resource deleted successfully |
| **POST (Action)** | 200 OK | Action performed (not creating a resource) |

---

## boundary_handler Decorator

**A POST create route declares 201 on its decorator:**

```python
# adapters/inbound/user_entry_api.py
@rt("/api/user-entries", methods=["POST"])
@csrf_protected
@boundary_handler(success_status=201)
async def create_user_entry_route(request: Request) -> Result[dict[str, Any]]: ...
```

The handler returns its `Result`; the boundary turns a success into a 201 response.
A handler with a bare `@boundary_handler()` answers 200.

---

## When to Use 201 Created

**Use `success_status=201` for POST routes that:**
1. Create a **persistent resource** (stored in database)
2. Return the created resource with a UID
3. Are idempotent or generate unique resources

### Examples of 201 Routes

```python
# adapters/inbound/habits_api.py — records a habit completion
@rt("/api/habits/track", methods=["POST"])
@csrf_protected
@boundary_handler(success_status=201)
async def habit_track(request: Request) -> Result[dict[str, Any]]: ...

# adapters/inbound/pathways_api.py — records progress on a path step
@rt("/api/pathways/progress", methods=["POST"])
@csrf_protected
@boundary_handler(success_status=201)
async def update_progress_route(request: Request) -> Result[dict[str, Any]]: ...
```

---

## When to Use 200 OK

**Use default `@boundary_handler()` (200) for POST routes that:**
1. Perform **actions** on existing resources (complete, cancel, activate, link)
2. Trigger **ephemeral operations** (search, analyze, optimize)
3. Return **computed results** without persistence (generate, predict)

### Examples of 200 Routes

```python
# adapters/inbound/principles_api.py — links the caller's principle to a target
@rt("/api/principles/link", methods=["POST"])
@csrf_protected
@boundary_handler()  # 200 OK (an edge between existing entities, not a new resource)
async def principle_create_link(request: Request) -> Result[dict[str, Any]]: ...

# adapters/inbound/search_routes.py — search creates nothing
@rt("/api/search/unified", methods=["POST"])
@csrf_protected
@boundary_handler()  # 200 OK
async def unified_search_api(request: Request, ...): ...
```

---

## CRUDRouteFactory

**The factory registers its create route with 201:**

```python
# adapters/inbound/route_factories/crud_route_factory.py
instrumented = self._instrument_handler(
    create, f"{self.base_path}/create", success_status=201
)
rt(f"{self.base_path}/create", methods=["POST"])(instrumented)
```

So `POST /api/{domain}/create` answers 201 for every domain the factory serves.

---

## Benefits

1. **REST Compliance** - Follows HTTP/REST standards
2. **API Clarity** - Clients know when resources are created
3. **Semantic Correctness** - Status code matches operation semantics
4. **Developer Experience** - Clear distinction between creation and actions
5. **Tool Compatibility** - Works correctly with REST clients and API tools

---

## Related Documentation

- [Error Handling Standard](ERROR_HANDLING.md)

