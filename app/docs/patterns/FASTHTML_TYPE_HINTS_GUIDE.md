---
title: FastHTML Type Hints Pattern Guide
updated: 2026-10-11
category: patterns
related_skills:
- ui-browser
- fasthtml
related_docs: []
---
# FastHTML Type Hints Pattern Guide

## Related Skills

For implementation guidance, see:
- [@fasthtml](../../.claude/skills/fasthtml/SKILL.md)
- [@ui-browser](../../.claude/skills/ui-browser/SKILL.md)

## Core Principle

**"A type hint extracts a parameter; it does not validate one"**

FastHTML fills a handler's parameters from the request by name and type hint: `request`
itself, path parameters, query parameters, and the top-level keys of a JSON or form body.
It converts each value by calling the annotation's converter. What a bad value answers
depends on the type, and it is never SKUEL's answer — so a hint is the right tool for a
`str` (a uid, an optional string filter) and for a path segment, and a `route_helpers`
parser or a request model is the tool for everything else.

---

## What FastHTML Does With a Hint

Measured on a bare `fast_app()` with `TestClient`:

| Type hint | Accepts | A bad value answers |
|-----------|---------|---------------------|
| `str` | anything | — |
| `int`, `float` | `"42"`, `"3.14"` | **404** |
| `date` | ISO `"2025-11-18"` | **404** |
| `bool` | `"true"`/`"1"`/`"yes"` → `True`; `"false"`/`"0"`/`"off"` → `False` | **500** (`"maybe"`) |
| `datetime` | nothing — a valid ISO string raises too | **500** |
| `list[str]` | repeated keys, `?tags=a&tags=b` → `["a", "b"]` (a CSV `a,b,c` stays one item; absent → `[]`) | — |
| a Pydantic model | — never declare one (see below) | **500** |

A required parameter the request does not carry answers **400** (`Missing required field:
uid`) — FastHTML's plain-text body, not the `Errors.validation` JSON envelope.

The same conversion runs on a body's keys, JSON or form: `n: int` with `{"n": "z"}` is a 404.
A JSON body's non-string value skips the converter (`{"n": 5}` binds the number as sent);
a union is converted by its first member that is not `None`.

FastHTML also merges the query string into the JSON body it parses and caches on the
request (`data |= dict(conn.query_params)`), so `await request.json()` hands back
`?uid=` in place of the body's `uid`. A route reads a JSON body through
`form_helpers.read_json_body` (the body's bytes) — `parse_json_body` / `parse_body` do.

---

## SKUEL's Rules

1. **An authenticated handler takes `request: Request`** — `require_authenticated_user(request)`
   reads the session from it. Import `Request` from `adapters.inbound.fasthtml_types`
   (SKUEL035); `request: Any` is a FastHTML 400 (SKUEL020).
2. **A mutation declares `methods=["POST"]` and `@csrf_protected`.** A `@rt(path)` with no
   `methods=` answers GET, HEAD and POST, so a method-less mutation is reachable by a link
   or a prefetch. Enforced by `scripts/audit_route_security.py` — a `@csrf_protected`
   handler that names no `methods=`, or names a safe one, fails `./dev quality`
   (`fasthtml` skill, `routing-patterns.md` § Function Name Conventions).
3. **Read a body inside the handler** with `parse_body` / `parse_json_body` /
   `parse_form_body` — never a model in the signature. See
   [API_VALIDATION_PATTERNS.md](API_VALIDATION_PATTERNS.md) § Read the body inside the handler.
4. **Never bind a `bool` / `int` / `float` / `date` / `datetime` / enum parameter outside
   the path.** Read it from `request.query_params` with a `route_helpers` parser — a
   silent fallback for a read (`parse_bool_query_param`, `parse_int_query_param`,
   `parse_pagination_params`: an unreadable value is the default) or a strict 400 for a
   value a write stores (`parse_float_param_strict`, `parse_date_param_strict`). A value
   that arrives as a body field FastHTML binds is typed `str` (or a `str`-first union) and
   read with `parse_bool_value` / `parse_int_value` / `parse_float_param_strict`. A typed
   path segment stays: a segment that does not read is a URL that names nothing (404).
   `tests/unit/adapters/test_request_input_census.py` holds every registered handler to
   this.
5. **Never `await request.json()`** — `read_json_body(request)` (see above).

---

## Examples

### A read with a numeric query value

```python
# adapters/inbound/insights_api.py
@rt("/api/insights/active")
@boundary_handler(success_status=200)
async def get_active_insights(
    request: Request,
    domain: str | None = None,
) -> Result[dict[str, Any]]:
    user_uid = require_authenticated_user(request)
    limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1)
    ...
```

`?limit=abc` reads as 50, the default — a typed `limit: int` would have answered 404.

### A score a write stores

```python
# adapters/inbound/route_factories/lateral_route_factory.py
async def create_blocking(
    request: Request,
    uid: str,
    target_uid: str,
    reason: str,
    confidence: str | float | None = None,  # form text or a JSON number
    ...
) -> Result[dict[str, Any]]:
    ...
    confidence_score = parse_edge_score(confidence, "confidence", 1.0)
    if confidence_score.is_error:
        return Result.fail(confidence_score)  # 400, nothing written
```

`parse_edge_score` is `parse_float_param_strict` over 0.0-1.0: a missing score is the
default, and text that is not a number, a non-finite number, or one out of range is a 400.

### A mutation with a query uid and a body

```python
# adapters/inbound/context_aware_api.py
@rt("/api/context/goal/tasks", methods=["POST"])
@csrf_protected
@boundary_handler(success_status=201)
async def create_tasks_from_goal_context_route(
    request: Request, goal_uid: str
) -> Result[list[Task]]:
    user_uid = require_authenticated_user(request)
    parsed = await parse_body(request, ContextualGoalTaskGenerationRequest)
    if parsed.is_error:
        return Result.fail(parsed)
    body = parsed.value
    return await context_service.create_tasks_from_goal_context(
        goal_uid=goal_uid,
        user_uid=user_uid,
        context_preferences=body.context_preferences,
        auto_create=body.auto_create,
    )
```

### A query value parsed by a helper

```python
# adapters/inbound/context_aware_api.py
@rt("/api/context/dashboard")
@boundary_handler()
async def get_context_dashboard_route(request: Request) -> Result[ContextDashboard]:
    user_uid = require_authenticated_user(request)
    params = dict(request.query_params)
    include_predictions = parse_bool_query_param(params, "include_predictions", default=True)
    ...
```

`?include_predictions=maybe` reads as `False` (an absent or blank value takes the default) instead of answering 500.

---

## Testing

A handler takes `request`, so a test drives the registered route through Starlette's
`TestClient` on a bare `fast_app()` — which also exercises FastHTML's extraction, the part
a direct call would skip. `tests/unit/adapters/test_context_aware_api_routes.py` is a
compact harness: it registers the routes against a mocked service, patches
`require_authenticated_user`, and mints a CSRF token for each POST.

---

## References

- Route factory: `/adapters/inbound/route_factories/crud_route_factory.py`
- Query parsers: `/adapters/inbound/route_factories/route_helpers.py`
- Body readers: `/adapters/inbound/form_helpers.py`
