---
title: HTTP Status Codes - REST Best Practices
updated: 2025-10-17
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

**Two ways to specify 201 status for POST create routes:**

### Method 1: Decorator Parameter (Preferred)

```python
# ✅ CORRECT - Specify status in decorator
@rt("/api/tasks", methods=["POST"])
@boundary_handler(success_status=201)
async def create_task_route(request):
    result = await tasks_service.create(task)
    return result  # Automatically returns 201 status
```

### Method 2: Return Statement (Alternative)

```python
# ✅ ALSO CORRECT - Specify in return helper
@rt("/api/tasks", methods=["POST"])
@boundary_handler()
async def create_task_route(request):
    result = await tasks_service.create(task)
    return success_response(result, status_code=201)  # Explicit 201
```

---

## When to Use 201 Created

**Use `success_status=201` for POST routes that:**
1. Create a **persistent resource** (stored in database)
2. Return the created resource with a UID
3. Are idempotent or generate unique resources

### Examples of 201 Routes

```python
# Resource creation (database persistence)
@rt("/api/goals/{uid}/progress", methods=["POST"])
@boundary_handler(success_status=201)
async def create_progress_record(request): ...

@rt("/api/learning/paths", methods=["POST"])
@boundary_handler(success_status=201)
async def create_learning_path(request): ...

@rt("/api/principles/{uid}/links", methods=["POST"])
@boundary_handler(success_status=201)
async def create_principle_link(request): ...
```

---

## When to Use 200 OK

**Use default `@boundary_handler()` (200) for POST routes that:**
1. Perform **actions** on existing resources (complete, cancel, activate)
2. Trigger **ephemeral operations** (search, analyze, optimize)
3. Return **computed results** without persistence (generate, predict)

### Examples of 200 Routes

```python
# Actions on existing resources
@rt("/api/tasks/{uid}/complete", methods=["POST"])
@boundary_handler()  # 200 OK (action, not creation)
async def complete_task(request): ...

# Ephemeral operations
@rt("/api/search", methods=["POST"])
@boundary_handler()  # 200 OK (search doesn't create resource)
async def search(request): ...

# Generation without persistence
@rt("/api/adaptive-learning/generate-path", methods=["POST"])
@boundary_handler()  # 200 OK (ephemeral generation)
async def generate_path(request): ...
```

---

## CRUDRouteFactory

**The factory automatically uses 201 for POST create:**

```python
# Factory pattern (line 205 in crud_route_factory.py)
@rt(f"{self.base_path}", methods=["POST"])
@boundary_handler(success_status=201)  # Automatic 201
async def create_route(request):
    result = await service.create(entity)
    return result
```

---

## Migration Complete (October 16, 2025)

**Status:** All POST resource creation routes now return 201 Created.

### Updated Files

- `goals_api.py` - 3 routes (progress, milestones, habits)
- `learning_api.py` - 3 routes (paths, progress, steps) - uses return statement method
- `principles_api.py` - 2 routes (expressions, links)
- `system_api.py` - 2 routes (register, thresholds)
- All other domain APIs - Already using factory or correct status codes

### Consistency Achieved

- ✅ Factory-generated routes: 201 (via `success_status=201`)
- ✅ Manual creation routes: 201 (via decorator or return)
- ✅ Action routes: 200 (default behavior)
- ✅ Search/analysis routes: 200 (ephemeral operations)

---

## Benefits

1. **REST Compliance** - Follows HTTP/REST standards
2. **API Clarity** - Clients know when resources are created
3. **Semantic Correctness** - Status code matches operation semantics
4. **Developer Experience** - Clear distinction between creation and actions
5. **Tool Compatibility** - Works correctly with REST clients and API tools

---

## Related Documentation

- [Error Handling Standard](/home/mike/0bsidian/skuel/docs/patterns/error_handling.md) (if exists)
- [Service Creation Template](/home/mike/0bsidian/skuel/docs/reference/templates/service_creation.md)

---

**Last Updated:** October 17, 2025
**Status:** Active - Migration complete, all routes follow REST best practices
