# SKUEL GraphQL API

**Production-ready GraphQL API with comprehensive guardrails**

---

## Overview

SKUEL's GraphQL API provides a flexible, type-safe alternative to REST for complex nested queries. It solves real N+1 query problems and enables powerful features like:

- **Complex nested queries** - Fetch related data in one request
- **Flexible field selection** - Request only what you need
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
adapters/inbound/graphql/
├── __init__.py          # Package exports
├── schema.py            # Query + Mutation (disabled) definitions
├── types.py             # GraphQL type definitions (Strawberry @strawberry.type)
├── mappers.py           # Domain model → GraphQL type conversion functions
├── query_helpers.py     # unwrap_result/unwrap_list + GraphQLQueryHelpers
├── context.py           # DataLoader + GraphQLContext (per-request)
├── config.py            # Guardrails configuration (GraphQLConfig)
├── guardrails.py        # QueryComplexityLimiter + ResolverTimeoutExtension
├── auth.py              # require_user_uid(), resolve_target_user()
├── protocols.py         # Structural protocols (PathStepLike, etc.)
├── GUARDRAILS.md        # Complete guardrails documentation
├── AUTHENTICATION.md    # Two-layer auth design
├── DATALOADER_GUIDE.md  # N+1 prevention patterns
├── COMPLEXITY.md        # Depth/token/alias/complexity limits + timeouts
├── QUERY_EXAMPLES.md    # Real-world example queries
├── ENHANCEMENTS.md      # Future improvements
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

Implementation: [context.py:adapters/inbound/graphql/context.py](./context.py)

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

#### `tasks(includeCompleted: Boolean, limit: Int): [Task!]!`

List tasks for the authenticated user. No `userUid` parameter — uses session auth to prevent UID spoofing.

```graphql
query {
  tasks(includeCompleted: false, limit: 10) {
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

#### `learningPaths(limit: Int, allPaths: Boolean): [LearningPath!]!`

List learning paths. Default: authenticated user's paths. Set `allPaths: true` for discovery mode.

```graphql
query {
  learningPaths(limit: 10) {
    uid
    name
    goal
    totalSteps
    estimatedHours
  }
}
```

### Dashboard Query

#### `userDashboard: DashboardData!`

Get complete dashboard data in ONE query. Uses authenticated user from session.

```graphql
query {
  userDashboard {
    tasksCount
    pathsCount
    habitsCount
  }
}
```

**Why GraphQL shines:** This would require 3+ REST calls.

### Cross-Domain Discovery

#### `discoverCrossDomain(userKnowledge: [String!]!, targetDomains: [String!], maxOpportunities: Int): [CrossDomainOpportunity!]!`

Discover cross-domain learning opportunities. Wired to `AdaptiveLpCrossDomainService`.

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
    practicalProjects
    successPatterns
    supportingExamples
  }
}
```

**Status:** Implemented. Source/target nodes are loaded as real KnowledgeNodes via DataLoader when `source_knowledge_uids`/`target_knowledge_uids` are available on the opportunity. Falls back to domain-level placeholder nodes when no real KU exists.

---

## Mutations

**Mutations are DISABLED.** GraphQL is read-only for complex nested queries. Use the REST API for all mutations (POST, PUT, DELETE). This keeps mutations in one place and leverages GraphQL's strength: flexible, composable reads.

---

## Configuration

All guardrail limits are configured in [config.py:adapters/inbound/graphql/config.py](./config.py):

```python
@dataclass
class GraphQLConfig:
    max_query_depth: int = 5            # QueryDepthLimiter (depth bombs)
    max_query_tokens: int = 1000        # MaxTokensLimiter
    max_aliases: int = 10               # MaxAliasesLimiter
    max_query_complexity: int = 1000    # QueryComplexityLimiter (summed field cost)
    max_query_timeout_seconds: int = 30     # whole-op ceiling (asyncio.wait_for)
    max_resolver_timeout_seconds: int = 10  # per-resolver ceiling
    max_list_size: int = 100            # validate_list_limit
    default_list_size: int = 20
    max_cypher_depth: int = 5           # validate_query_depth
```

See **GUARDRAILS.md** for how each is enforced. A Cypher/transaction timeout is a
database concern (driver-level timeouts come from `DatabaseConfig`), not a GraphQL
guardrail — the old `cypher_timeout_seconds` was removed.

### Adjusting Limits

```python
from adapters.inbound.graphql.config import get_graphql_config

config = get_graphql_config()
config.max_list_size = 50  # Reduce maximum
```

---

## Testing

### Unit Tests (129 tests, 98% schema.py coverage)

```bash
uv run pytest tests/unit/test_graphql_schema_resolvers.py tests/unit/test_graphql_mappers.py -v
```

Tests cover all resolvers, helper functions, auth, config, context, DataLoader batching, type field resolvers, and schema factory. No Neo4j required — all services mocked.

### Integration Tests

```bash
uv run pytest tests/integration/test_graphql_queries.py tests/integration/test_graphql_complex_queries.py tests/integration/test_graphql_type_contracts.py -v
```

### Manual Testing with Playground

1. Start the app: `uv run python main.py`
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
| **Developer experience** | Manual testing | GraphiQL playground |

### When to Use GraphQL

✅ **Use GraphQL for:**
- Complex nested queries (tasks with knowledge with prerequisites)
- Dashboard queries (multiple data sources in one request)
- Frontend flexibility (mobile, web, different field requirements)

❌ **Use REST for:**
- Simple CRUD operations
- File uploads/downloads
- Caching with HTTP headers
- Public APIs (wider compatibility)

---

## Integration with FastHTML

GraphQL routes are registered in [bootstrap.py:/home/mike/skuel/app/scripts/dev/bootstrap.py](../../scripts/dev/bootstrap.py):

```python
from adapters.inbound.graphql_routes import create_graphql_routes

create_graphql_routes(app, rt, services)
```

---

## Production Readiness

**✅ Implemented:**
1. **Query Complexity Limits** - QueryDepthLimiter (max depth: 5) + MaxTokensLimiter (1000 tokens)
2. **DataLoader Batching** - Automatic N+1 prevention for knowledge, tasks, learning paths, steps
3. **FastHTML Playground** - 100% Python, no React/TypeScript dependencies
4. **Guardrails** - Cypher in repos, apply limits, project fields, Result[T] flow
5. **Session Authentication** - `require_authenticated_user()` at HTTP layer, defense-in-depth at resolver layer
6. **Cross-Domain Discovery** - Wired to `AdaptiveLpCrossDomainService` with DataLoader-backed KU nodes
7. **Comprehensive Tests** - unit tests (98% schema.py coverage), integration tests, type contract tests

**⏳ Optional Enhancements:**
1. **Rate Limiting** - Per-user query rate limits
2. **Audit Logging** - Log sensitive queries for compliance

See [ENHANCEMENTS.md](./ENHANCEMENTS.md) for implementation details.

---

## Dependencies

```toml
# pyproject.toml
strawberry-graphql = ">=0.289.0"  # GraphQL server with type safety (Pydantic 2.12+ compatible)
```

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
