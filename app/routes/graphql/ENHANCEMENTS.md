# GraphQL - Optional Enhancements

## Overview

SKUEL's GraphQL API is **complete and production-ready** with:
- ✅ All core queries (learning paths, knowledge graph, tasks, dashboard)
- ✅ DataLoader batching (N+1 prevention)
- ✅ FastHTML playground (100% Python, no React)
- ✅ Four production guardrails
- ✅ Session-based authentication (two-layer: HTTP + resolver)
- ✅ Cross-domain discovery (wired to `AdaptiveLpCrossDomainService`)
- ✅ Subscriptions (wired to event bus with `LearningPathProgressUpdated`)
- ✅ Comprehensive tests (134 unit tests, 98% schema.py coverage)

These enhancements are **optional** - implement only if needed.

---

## P1: WebSocket Transport for Subscriptions

### Current State

The `learning_progress` subscription is implemented and wired to the event bus. It subscribes to `LearningPathProgressUpdated` events, filters by user/path, yields progress values, and cleans up on disconnect. However, it requires a WebSocket transport layer to function in production.

### Implementation Options

**Option 1: Server-Sent Events (Simpler, FastHTML-native)**

```python
@rt("/api/learning-progress/{path_uid}")
async def learning_progress_sse(request, path_uid: str):
    async def event_stream():
        async for event in event_bus.subscribe("learning.progress"):
            if event.path_uid == path_uid:
                yield f"data: {event.progress_percentage}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# Client-side (HTMX)
# <div hx-ext="sse" sse-connect="/api/learning-progress/lp.python" sse-swap="message">
```

**Option 2: WebSocket with Strawberry (More Complex)**

```python
from strawberry.asgi import GraphQL

graphql_app = GraphQL(
    schema,
    subscription_protocols=["graphql-transport-ws"]
)
app.mount("/graphql-ws", graphql_app)
```

**Recommendation:** Use Server-Sent Events with HTMX - fits FastHTML philosophy better.

---

## P2: Rate Limiting Per User

Per-user query rate limits to prevent abuse. Not yet implemented.

---

## P3: Cross-Domain Discovery Enrichment

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
- ✅ Authentication (complete — session-based, two-layer)
- ✅ Cross-domain discovery (complete)
- ✅ Subscriptions (complete — needs WebSocket transport for production)
- ✅ Tests (134 unit tests, 98% schema.py coverage)
- ⏳ WebSocket transport (optional)
- 📋 Rate limiting (optional)
