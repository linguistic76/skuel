# SKUEL GraphQL API

**Production-ready GraphQL API with comprehensive guardrails**

---

## Overview

SKUEL's GraphQL API provides a flexible, type-safe alternative to REST for complex nested queries. It solves real N+1 query problems and enables powerful features like:

- **Complex nested queries** - Fetch related data in one request
- **Flexible field selection** - Request only what you need
- **Real-time subscriptions** - Future: learning progress updates
- **Type-safe API** - Python type hints + Strawberry dataclasses
- **DataLoader batching** - Automatic N+1 prevention
- **FastHTML integration** - Server-rendered Python components

## Quick Start

### 1. GraphQL Endpoint

```
http://localhost:8000/graphql
```

### 2. FastHTML Playground

Open http://localhost:8000/graphql in your browser for SKUEL's GraphQL playground.

**100% FastHTML** - No React, no external frameworks. Features:
- Interactive query editor
- JSON variable input
- Live result display
- HTMX-powered execution

### 3. Example Query

```graphql
query GetTasksWithKnowledge {
  tasks(userUid: "user.001", limit: 10) {
    uid
    title
    status
    knowledge {
      uid
      title
      domain
      prerequisites {
        uid
        title
      }
    }
  }
}
```

**Why GraphQL here?**

With REST, this would require:
1. GET `/api/tasks?user_uid=user.001` (10 tasks)
2. GET `/api/knowledge/{uid}` (10 requests for knowledge)
3. GET `/api/knowledge/{uid}/prerequisites` (10+ requests)

**Total: 21+ HTTP requests**

With GraphQL: **1 request** with DataLoader batching

---

## Architecture

### Four Guardrails (Production-Ready)

See [GUARDRAILS.md](./GUARDRAILS.md) for complete documentation.

| Guardrail | Purpose | Implementation |
|-----------|---------|----------------|
| **1. Cypher in Repos** | Clean architecture | All queries delegate to services/backends |
| **2. Apply Limits** | Prevent abuse | `validate_list_limit()` caps at 100, default 20 |
| **3. Project Fields** | Performance | CypherGenerator auto-projects needed fields |
| **4. Result[T] Flow** | Consistent errors | All resolvers handle Result[T] uniformly |

### Key Components

```
routes/graphql/
├── __init__.py          # Package exports
├── schema.py            # Query, Mutation, Subscription definitions
├── types.py             # GraphQL type definitions
├── context.py           # DataLoader + context management
├── config.py            # Guardrails configuration
├── GUARDRAILS.md        # Complete guardrails documentation
└── README.md            # This file
```

### DataLoader Pattern

DataLoaders prevent N+1 queries by batching and caching requests:

```python
# Without DataLoader (N+1 problem):
# For 10 tasks with knowledge:
# - 1 query for tasks
# - 10 queries for knowledge units
# Total: 11 queries

# With DataLoader (batching):
# - 1 query for tasks
# - 1 BATCHED query for all 10 knowledge units
# Total: 2 queries
```

Implementation: [context.py:routes/graphql/context.py](./context.py)

---

## Available Queries

### Knowledge Queries

#### `knowledgeUnit(uid: String!): KnowledgeNode`

Get a single knowledge unit with optional nested relationships.

```graphql
query {
  knowledgeUnit(uid: "ku.math.algebra") {
    uid
    title
    summary
    domain
    tags
    qualityScore
    prerequisites {
      uid
      title
    }
    enables {
      uid
      title
    }
  }
}
```

#### `knowledgeUnits(domain: String, limit: Int, offset: Int): [KnowledgeNode!]!`

List knowledge units with filtering and pagination.

```graphql
query {
  knowledgeUnits(domain: "TECH", limit: 20) {
    uid
    title
    domain
    qualityScore
  }
}
```

**Guardrails:**
- `limit` capped at 100 (default 20)
- Cypher queries in KnowledgeBackend, not here

#### `searchKnowledge(input: SearchInput!): [SearchResult!]!`

Semantic search for knowledge units.

```graphql
query {
  searchKnowledge(input: {
    query: "machine learning fundamentals"
    limit: 10
    minQuality: 0.7
  }) {
    knowledge {
      uid
      title
      summary
    }
    relevance
    explanation
  }
}
```

### Task Queries

#### `task(uid: String!): Task`

Get a single task with optional nested knowledge.

```graphql
query {
  task(uid: "task.001") {
    uid
    title
    status
    priority
    knowledge {
      uid
      title
      domain
    }
  }
}
```

#### `tasks(userUid: String!, includeCompleted: Boolean, limit: Int): [Task!]!`

List user tasks with optional filtering.

```graphql
query {
  tasks(userUid: "user.001", includeCompleted: false, limit: 10) {
    uid
    title
    status
    priority
    knowledge {
      uid
      title
    }
  }
}
```

### Learning Path Queries

#### `learningPath(uid: String!): LearningPath`

Get a learning path with nested steps and knowledge units.

```graphql
query {
  learningPath(uid: "lp.python.basics") {
    uid
    name
    goal
    totalSteps
    estimatedHours
    steps {
      stepNumber
      masteryThreshold
      estimatedTime
      knowledge {
        uid
        title
        domain
      }
    }
  }
}
```

**This solves N+1:** Fetching path → steps → knowledge in one request.

#### `learningPaths(userUid: String, limit: Int): [LearningPath!]!`

List learning paths, optionally filtered by user.

```graphql
query {
  learningPaths(userUid: "user.001", limit: 10) {
    uid
    name
    goal
    totalSteps
    estimatedHours
  }
}
```

### Dashboard Query

#### `userDashboard(userUid: String!): DashboardData!`

Get complete dashboard data in ONE query.

```graphql
query {
  userDashboard(userUid: "user.001") {
    tasksCount
    pathsCount
    habitsCount
  }
}
```

**Why GraphQL shines:** This would require 3+ REST calls.

### Cross-Domain Discovery (Future)

#### `discoverCrossDomain(userKnowledge: [String!]!, targetDomains: [String!], maxOpportunities: Int): [CrossDomainOpportunity!]!`

Discover cross-domain learning opportunities.

```graphql
query {
  discoverCrossDomain(
    userKnowledge: ["ku.tech.python", "ku.tech.data"]
    targetDomains: ["BUSINESS", "PERSONAL"]
    maxOpportunities: 10
  ) {
    source {
      uid
      title
    }
    target {
      uid
      title
    }
    bridgeType
    transferability
    effortRequired
    reasoning
  }
}
```

**Status:** Placeholder - returns empty list with TODO for service integration.

---

## Available Mutations

### Task Mutations

#### `createTask(input: TaskInput!): Task`

Create a new task.

```graphql
mutation {
  createTask(input: {
    title: "Learn Python decorators"
    description: "Study advanced Python concepts"
    priority: "high"
    knowledgeUid: "ku.tech.python.decorators"
  }) {
    uid
    title
    status
    knowledge {
      uid
      title
    }
  }
}
```

#### `updateTask(uid: String!, title: String, description: String, status: String, priority: String): Task`

Update an existing task.

```graphql
mutation {
  updateTask(
    uid: "task.001"
    status: "completed"
    priority: "low"
  ) {
    uid
    title
    status
    priority
  }
}
```

#### `deleteTask(uid: String!): Boolean!`

Delete a task.

```graphql
mutation {
  deleteTask(uid: "task.001")
}
```

Returns `true` if successful, `false` otherwise.

---

## Subscriptions (Future)

### `learningProgress(UserUid: String!, PathUid: String!): Float!`

Subscribe to real-time learning progress updates.

```graphql
subscription {
  learningProgress(UserUid: "user.001", PathUid: "lp.python.basics")
}
```

**Status:** Placeholder - requires WebSocket integration and event bus wiring.

---

## Configuration

All guardrail limits are configured in [config.py:routes/graphql/config.py](./config.py):

```python
@dataclass
class GraphQLConfig:
    max_list_size: int = 100          # Cap list queries
    default_list_size: int = 20       # Default if not specified
    max_query_depth: int = 5          # Prevent depth bombs
    max_cypher_depth: int = 5         # Graph traversal limit
    cypher_timeout_seconds: int = 10  # Kill slow queries
```

### Adjusting Limits

```python
from routes.graphql.config import get_graphql_config

config = get_graphql_config()
config.max_list_size = 50  # Reduce maximum
```

---

## Testing

### Run Integration Tests

```bash
poetry run python test_graphql.py
```

Tests:
- ✅ Schema creation
- ✅ Context creation with DataLoaders
- ✅ Service integration

### Manual Testing with GraphiQL

1. Start the app: `poetry run python main.py`
2. Open http://localhost:8000/graphql
3. Try example queries from this README

---

## Benefits vs REST

| Feature | REST API | GraphQL API |
|---------|----------|-------------|
| **Nested data** | Multiple requests (N+1) | Single request with DataLoader |
| **Over-fetching** | Returns all fields | Client selects fields |
| **Under-fetching** | Multiple endpoints | One query |
| **Type safety** | OpenAPI schema | Built-in introspection |
| **Real-time** | Polling or custom WebSocket | Built-in subscriptions |
| **Developer experience** | Manual testing | GraphiQL playground |

### When to Use GraphQL

✅ **Use GraphQL for:**
- Complex nested queries (tasks with knowledge with prerequisites)
- Dashboard queries (multiple data sources in one request)
- Frontend flexibility (mobile, web, different field requirements)
- Real-time updates (subscriptions)

❌ **Use REST for:**
- Simple CRUD operations
- File uploads/downloads
- Caching with HTTP headers
- Public APIs (wider compatibility)

---

## Integration with FastHTML

GraphQL routes are registered in [bootstrap.py:/home/mike/skuel/app/scripts/dev/bootstrap.py](../../scripts/dev/bootstrap.py):

```python
# GraphQL API routes (Complex nested queries + real-time subscriptions)
try:
    from adapters.inbound.graphql_routes import create_graphql_routes_manual
    create_graphql_routes_manual(app, rt, services)
    logger.info("✅ GraphQL API registered at /graphql (with GraphiQL playground)")
except Exception as e:
    logger.warning(f"⚠️ GraphQL API registration failed: {e}")
    # Continue without GraphQL - it's an enhancement, not critical
```

**Graceful fallback:** If GraphQL fails to load, the app continues with REST API only.

---

## Production Readiness

**✅ Implemented:**
1. **Query Complexity Limits** - QueryDepthLimiter (max depth: 5) + MaxTokensLimiter (1000 tokens)
2. **DataLoader Batching** - Automatic N+1 prevention for knowledge, tasks, learning paths, steps
3. **FastHTML Playground** - 100% Python, no React/TypeScript dependencies
4. **Guardrails** - Cypher in repos, apply limits, project fields, Result[T] flow

**⏳ Optional Enhancements:**
1. **Authentication Hardening** - Replace dev default (`user.mike`) with real session auth
2. **WebSocket Subscriptions** - Real-time updates (or use Server-Sent Events with HTMX)
3. **Cross-Domain Discovery** - Wire up semantic search service

See [ENHANCEMENTS.md](./ENHANCEMENTS.md) for implementation details.

---

## Dependencies

```toml
# pyproject.toml
strawberry-graphql = "^0.284.1"  # GraphQL server with type safety (Pydantic 2.12+ compatible)
```

**Version note:** Using Strawberry 0.284.1 for Pydantic 2.12+ compatibility.

---

## Resources

- **Strawberry GraphQL Docs:** https://strawberry.rocks/
- **GraphQL Spec:** https://spec.graphql.org/
- **DataLoader Pattern:** https://github.com/graphql/dataloader
- **SKUEL Guardrails:** [GUARDRAILS.md](./GUARDRAILS.md)

---

## Summary

SKUEL's GraphQL API is **production-ready** with:

✅ Comprehensive guardrails (limits, timeouts, projection)
✅ DataLoader batching (N+1 prevention)
✅ Type-safe schema with introspection
✅ Result[T] error handling
✅ GraphiQL playground for development
✅ Graceful integration with existing REST API

**GraphQL complements REST** - use the right tool for the job.
