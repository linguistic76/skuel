# GraphQL Authentication

**Strict session-based authentication for SKUEL GraphQL API**

---

## Architecture

Authentication is a **two-layer** system:

| Layer | Responsibility | Module |
|-------|---------------|--------|
| **HTTP** | Reject unauthenticated requests (401) | `adapters/inbound/graphql_routes.py` |
| **Resolver** | Extract user_uid from context (defense-in-depth) | `adapters/inbound/graphql/auth.py` |

### Error Strategy (March 2026)

| Boundary | Behavior |
|----------|----------|
| HTTP (no session) | 401 Unauthorized — hard boundary |
| Resolver (missing user_uid) | `ValueError` — indicates route wiring bug, not client error |
| Data (missing entity) | `None` for single items, `[]` for lists — graceful |

---

## Request Flow

```
1. Client sends GraphQL query with session cookie
   ↓
2. graphql_routes.py calls require_authenticated_user(request)
   → Returns user_uid or raises 401
   ↓
3. create_graphql_context(services, search_router, user_uid=user_uid)
   → Context.user_uid is always a non-empty UserUID
   ↓
4. Resolvers call require_user_uid(info) or resolve_target_user(info, user_uid)
   → Defense-in-depth: ValueError if somehow empty
   ↓
5. Services receive a guaranteed user_uid
```

---

## Resolver Auth Helpers

### `require_user_uid(info) -> UserUID`

Standard way to get the authenticated user in resolvers. Use when the resolver always operates on the current user's data.

```python
from adapters.inbound.graphql.auth import require_user_uid

@strawberry.field
async def tasks(self, info: Info[GraphQLContext, Any]) -> list[Task]:
    user_uid = require_user_uid(info)
    result = await context.services.tasks.get_filtered_context(user_uid=user_uid, ...)
```

### `resolve_target_user(info, user_uid=None) -> UserUID` (async)

For resolvers that accept an optional `user_uid` override (admin queries). Falls back to the authenticated user. When a `user_uid` override is provided, the caller must have ADMIN role — raises `PermissionError` otherwise.

```python
from adapters.inbound.graphql.auth import resolve_target_user

@strawberry.field
async def learning_path_with_context(
    self, info: Info[GraphQLContext, Any],
    path_uid: str,
    user_uid: UserUID | None = None,
) -> LearningPathContext | None:
    target_user_uid = await resolve_target_user(info, user_uid)
```

---

## Key Design Decisions

**No development fallback in GraphQL.** REST routes use `get_current_user_or_default()` for dev convenience. GraphQL uses `require_authenticated_user()` — strict auth, no fallback. This was hardened in January 2026.

**No `user_uid` parameter on user-owned queries.** Resolvers like `tasks`, `user_dashboard` pull user_uid from context only. This prevents UID spoofing.

**`context.user_uid` is `UserUID`, not `str | None`.** Since auth is enforced at the HTTP layer, the context always has a valid typed `UserUID`. The `require_user_uid()` check is defense-in-depth. Both `require_user_uid()` and `resolve_target_user()` return `UserUID`, maintaining type safety from auth boundary through resolvers to services.

---

## Security

- Session cookies: signed, SameSite=lax, secure in production
- No user_uid in query parameters for user-owned data
- Admin override (`resolve_target_user`) enforces ADMIN role check
- Query-shape / cost limits (depth, tokens, aliases, complexity) and the request +
  per-resolver timeouts are enforced as schema extensions — see **GUARDRAILS.md**.

### Not Yet Implemented

- Per-user rate limiting / query budgets (complexity limits today are global, not per-user)
- Audit logging for sensitive queries
