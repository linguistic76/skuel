# GraphQL - Optional Enhancements

## Overview

SKUEL's GraphQL API is **complete and production-ready** with:
- ✅ All core queries (learning paths, knowledge graph)
- ✅ DataLoader batching (N+1 prevention)
- ✅ FastHTML playground (100% Python, no React)
- ✅ Four production guardrails

These enhancements are **optional** - implement only if needed.

---

## P0: Production Authentication (Required for Multi-User)

### Current State

Development mode using default user:

```python
# Current: get_current_user_or_default returns "user.mike"
user_uid = get_current_user_or_default(request)
```

### Production Implementation

Replace with real session-based auth:

```python
# Production: require authenticated user
def require_authenticated_user(request) -> str:
    user_uid = get_current_user(request)
    if not user_uid:
        raise HTTPException(401, "Login required")
    return user_uid

# In GraphQL route
user_uid = require_authenticated_user(request)
context = create_graphql_context(services, services.search_router, user_uid=user_uid)
```

**Note:** SKUEL's architecture is already multi-user ready. Services filter by `user_uid`, data model includes `user_uid` on all entities. This just replaces the dev default with real authentication.

---

## P1: Query Complexity Limits (Already Implemented)

**Status:** ✅ Complete

SKUEL already has query complexity limits:

```python
# routes/graphql/schema.py
schema = strawberry.Schema(
    query=Query,
    extensions=[
        QueryDepthLimiter(max_depth=5),      # Prevent deep nesting
        MaxTokensLimiter(max_token_count=1000)  # Prevent huge queries
    ]
)
```

See [COMPLEXITY.md](./COMPLEXITY.md) for details.

---

## P2: WebSocket Subscriptions (Low Priority)

### Why Low Priority

- **Complex Setup**: Requires WebSocket server configuration
- **Limited Use Cases**: Only useful for real-time updates
- **Alternative Solutions**: Server-Sent Events or polling simpler with FastHTML

### Current State

Subscription placeholder exists:

```python
@strawberry.subscription
async def learning_progress(
    self,
    _info: Info[GraphQLContext, Any],
    _user_uid: str,
    _path_uid: str
) -> AsyncIterator[float]:
    # TODO: Implement with event bus integration
    import asyncio
    while True:
        await asyncio.sleep(5)
        yield 0.0
```

### FastHTML Implementation (If Needed)

**Option 1: Server-Sent Events (Simpler)**

```python
# FastHTML route for SSE
@rt("/api/learning-progress/{path_uid}")
async def learning_progress_sse(request, path_uid: str):
    """
    Server-Sent Events for real-time progress updates.

    FastHTML-native approach - no WebSockets needed.
    """
    async def event_stream():
        async for event in event_bus.subscribe("learning.progress"):
            if event.path_uid == path_uid:
                yield f"data: {event.progress_percentage}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# Client-side (HTMX)
<div hx-ext="sse" sse-connect="/api/learning-progress/lp.python" sse-swap="message">
    Progress: <span id="progress">0%</span>
</div>
```

**Option 2: WebSocket with Strawberry (More Complex)**

```python
# Requires ASGI mount
from strawberry.asgi import GraphQL

graphql_app = GraphQL(
    schema,
    subscription_protocols=["graphql-transport-ws"]
)

# Mount in FastHTML app (if FastHTML supports ASGI mounting)
app.mount("/graphql-ws", graphql_app)
```

**Recommendation:** Use Server-Sent Events with HTMX - fits FastHTML philosophy better.

---

## P3: Cross-Domain Discovery (Complete)

### Current State

Wired to `AdaptiveLpCrossDomainService`. The `discoverCrossDomain` resolver builds a `KnowledgeState` from client-provided KU UIDs, discovers opportunities via the service, and loads real KnowledgeNodes via DataLoader for source/target representation. Falls back to domain-level placeholder nodes when no real KU is available.

### Remaining Enhancements

- Enrich `KnowledgeState` with real mastery data from `UserContext.zpd_assessment` instead of treating applied = mastered
- Consider `source_knowledge: [KnowledgeNode]` (list) instead of single representative node

---

## Summary

**Production Checklist:**
- ✅ DataLoader batching (complete)
- ✅ Query complexity limits (complete)
- ✅ FastHTML playground (complete)
- ⏳ Authentication hardening (replace dev default)
- 📋 WebSocket subscriptions (optional)
- 📋 Cross-domain discovery (optional)

**Priority:** Implement **P0: Authentication** before multi-user deployment.

**Note:** TypeScript codegen is not needed - SKUEL uses FastHTML (Python) for frontend, which already has full type safety through Python type hints and Strawberry dataclasses.
