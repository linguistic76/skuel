# GraphQL Guardrails

**Production-ready safeguards for SKUEL's GraphQL API**

---

## Overview

These guardrails ensure the GraphQL API is secure, performant, and aligned with SKUEL's architectural patterns.

## The Four Guardrails

### 1. ✅ Keep Cypher in Repositories/Queries, Not in Resolvers

**Rule:** GraphQL resolvers NEVER contain Cypher queries directly.

**Why:**
- Separation of concerns (resolvers orchestrate, repositories query)
- Easier testing (mock repositories, not databases)
- Consistent with SKUEL's architecture (services → backends → Neo4j)

**Implementation:**

```python
# ❌ WRONG - Cypher in resolver
@strawberry.field
async def knowledge_units(self, info: Info) -> list[KnowledgeNode]:
    # BAD: Cypher query directly in GraphQL resolver
    query = "MATCH (ku:Entity) RETURN ku LIMIT 50"
    result = await driver.execute_query(query)
    return [...]

# ✅ CORRECT - Cypher in repository/backend
@strawberry.field
async def knowledge_units(self, info: Info, limit: int | None = None) -> list[KnowledgeNode]:
    safe_limit = validate_list_limit(limit)

    # GOOD: Call service/backend which contains Cypher
    result = await context.services.knowledge.list_knowledge_units(
        limit=safe_limit
    )

    # Cypher is in KnowledgeBackend.list_knowledge_units()
    return [...]
```

**Location of Cypher Queries:**
- ✅ `/adapters/persistence/neo4j/` - Backend implementations
- ✅ `/adapters/persistence/neo4j/query/` - Query builders
- ❌ `/adapters/inbound/graphql/` - GraphQL resolvers (NO Cypher here!)

---

### 2. ✅ Apply Limits (Depth, Nodes, Timeouts)

**Rule:** All list queries and graph traversals have enforced limits.

**Why:**
- Prevent DoS attacks (requesting millions of items)
- Prevent expensive graph traversals (depth bombs)
- Ensure predictable performance

**Implementation:**

```python
# Configuration (/adapters/inbound/graphql/config.py) — every field is enforced.
@dataclass
class GraphQLConfig:
    # Query-shape limits — Strawberry schema extensions (see guardrails.py)
    max_query_depth: int = 5          # QueryDepthLimiter
    max_query_tokens: int = 1000      # MaxTokensLimiter
    max_aliases: int = 10             # MaxAliasesLimiter (alias-based DoS)
    max_query_complexity: int = 1000  # QueryComplexityLimiter (summed field cost)
    # Timeouts (seconds)
    max_query_timeout_seconds: int = 30     # whole-op ceiling (asyncio.wait_for, adapter)
    max_resolver_timeout_seconds: int = 10  # per-resolver ceiling (ResolverTimeoutExtension)
    # List / traversal caps — applied by the validate_* helpers
    max_list_size: int = 100          # validate_list_limit
    default_list_size: int = 20
    max_cypher_depth: int = 5         # validate_query_depth

# Two enforcement points:
#  (1) Schema extensions, wired as factory callables (functools.partial — fresh per
#      request) in create_graphql_schema(): QueryDepthLimiter, MaxTokensLimiter,
#      MaxAliasesLimiter, QueryComplexityLimiter, ResolverTimeoutExtension.
#  (2) Per-resolver validators for the list / traversal caps:
@strawberry.field
async def knowledge_units(self, limit: int | None = None) -> list[KnowledgeNode]:
    safe_limit = validate_list_limit(limit)  # Max 100, default 20
    result = await service.list_knowledge_units(limit=safe_limit)
    return [...]
```

**Enforced Limits:**

| Parameter | Default | Maximum | Enforced by |
|-----------|---------|---------|-------------|
| list `limit` | 20 | 100 | `validate_list_limit` (resolver) |
| graph traversal depth | 2 | 5 | `validate_query_depth` (resolver) |
| query nesting depth | — | 5 | `QueryDepthLimiter` |
| query tokens | — | 1000 | `MaxTokensLimiter` |
| aliases | — | 10 | `MaxAliasesLimiter` |
| query complexity | — | 1000 | `QueryComplexityLimiter` |
| whole-operation timeout | — | 30s | `asyncio.wait_for` (adapter boundary) |
| per-resolver timeout | — | 10s | `ResolverTimeoutExtension` |

> A Cypher/transaction timeout is **not** a GraphQL guardrail (the old
> `cypher_timeout_seconds` was removed). It's a database concern: driver-level
> timeouts come from `DatabaseConfig` (`neo4j_connection.py`); a real per-query
> server-side timeout is a deferred persistence task (no single session chokepoint).

---

### 3. ✅ Project Only What You Need

**Rule:** Never use `RETURN n` without projection - always specify fields.

**Why:**
- Avoid over-fetching (returning entire node objects with all properties)
- Better performance (Neo4j doesn't serialize unused data)
- Clearer intent (explicit about what's needed)

**Implementation:**

```python
# ❌ WRONG - No projection (returns everything)
query = """
MATCH (ku:Entity)
RETURN ku          # Bad: Returns ALL properties
LIMIT 50
"""

# ✅ CORRECT - Project only needed fields
query = """
MATCH (ku:Entity)
RETURN {
    uid: ku.uid,
    title: ku.title,
    summary: ku.summary,
    domain: ku.domain,
    tags: ku.tags,
    quality_score: ku.quality_score
} AS ku
LIMIT 50
"""

# ✅ EVEN BETTER - Use CypherGenerator (already does projection)
query, params = CypherGenerator.build_list_query(
    model=KnowledgeUnit,
    filters={"domain": Domain.TECH},
    limit=50
)
# CypherGenerator automatically projects based on model fields
```

**In SKUEL:**
- ✅ `CypherGenerator` - Automatically projects based on domain models
- ✅ `UniversalNeo4jBackend` - Uses model introspection for projection
- ❌ Raw Cypher with `RETURN n` - Avoided

---

### 4. ✅ Stick to Result[T] Flow

**Rule:** All service calls return `Result[T]`, GraphQL resolvers handle errors consistently.

**Why:**
- Uniform error handling across REST and GraphQL
- Type-safe error propagation
- Prevents exceptions from leaking into GraphQL responses

**Implementation:**

```python
# ✅ CORRECT - Result[T] pattern
@strawberry.field
async def knowledge_unit(
    self,
    uid: str
) -> KnowledgeNode | None:
    context: GraphQLContext = info.context

    # Service returns Result[KnowledgeUnit]
    result = await context.services.knowledge.get_knowledge_unit(uid)

    # Handle Result[T] consistently
    if result.is_error:
        # Error logged by service layer
        # GraphQL returns None (or could return error type)
        return None

    if not result.value:
        # Not found
        return None

    # Success - convert domain model to GraphQL type via mapper
    ku = result.value
    return knowledge_node_from_dto(ku)

# ✅ EVEN BETTER - Use unwrap_result() helper for list queries
from adapters.inbound.graphql.query_helpers import unwrap_result

result = await context.services.ps.core.list(limit=safe_limit, filters=filters)
entities, _count = unwrap_result(result, ([], 0))
return [knowledge_node_from_dto(ku) for ku in entities]

# ❌ WRONG - Direct exception handling
@strawberry.field
async def knowledge_unit(self, uid: str) -> KnowledgeNode:
    try:
        # Calling service that might raise exceptions
        ku = await service.get_knowledge_unit_direct(uid)
        return KnowledgeNode(...)  # Also wrong: use knowledge_node_from_dto()
    except Exception as e:
        # Inconsistent error handling
        raise  # Leaks exception into GraphQL response
```

**Error Flow:**
1. Service operation fails → Returns `Result.fail(error)`
2. Resolver checks `result.is_error` → Returns `None` or error type
3. GraphQL response → `{"data": {"knowledgeUnit": null}}`
4. Consistent with REST API error handling

---

## Query Complexity (Implemented)

Cost-based complexity analysis is enforced by `QueryComplexityLimiter`
(`adapters/inbound/graphql/guardrails.py`), an `AddValidationRules` extension that
walks each operation — resolving fragment spreads, mirroring Strawberry's own
`QueryDepthLimiter` — and rejects operations whose **summed field cost** exceeds
`max_query_complexity`. The cost is **additive and type-weighted** (it caps query
*breadth*; multiplicative list-size blow-up is bounded separately by the depth +
list-size limits):

| Field shape | Cost | Config field |
|-------------|------|--------------|
| Scalar / leaf | 1 | `basic_field_cost` |
| Nested object | 5 | `nested_object_cost` |
| List | 10 | `list_field_cost` |

The summed cost is scaled by `field_complexity_multiplier` and compared to
`max_query_complexity` (default 1000); over-budget operations are rejected at the
validation phase with a `GraphQLError`.

```graphql
query {
  knowledgeUnits {        # list field → 10
    prerequisites {       # list field → 10
      uid title           # 2 leaves → 2
    }
  }
}
# Summed cost 22 (well under 1000) → allowed
```

> Cost weights live in `GraphQLConfig`. `resolver_field_cost` was removed — every
> Strawberry field has a resolver, so it can't be detected faithfully; list-shaped
> fields (the DataLoader-backed ones) already carry `list_field_cost`.

---

## Testing Guardrails

```python
# Test limit validation
async def test_limit_guardrail():
    # Request 1000 items
    query = """
    query {
      knowledgeUnits(limit: 1000) {
        uid
        title
      }
    }
    """
    result = await execute_query(query)

    # Should be capped at 100
    assert len(result.data["knowledgeUnits"]) <= 100

# Test depth validation
async def test_depth_guardrail():
    # Deep nesting
    query = """
    query {
      knowledgeUnit(uid: "ku.001") {
        prerequisites {
          prerequisites {
            prerequisites {
              prerequisites {
                prerequisites {
                  prerequisites {  # 6 levels deep (exceeds max of 5)
                    uid
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    result = await execute_query(query)

    # Should be rejected or capped
    assert result.errors is not None
```

---

## Configuration

All guardrail settings in `/adapters/inbound/graphql/config.py`:

```python
from adapters.inbound.graphql.config import GraphQLConfig, get_graphql_config

# Get current configuration
config = get_graphql_config()

# Adjust limits (if needed)
config.max_list_size = 50  # Reduce maximum
config.max_query_depth = 3  # More restrictive depth
```

---

## Summary

| Guardrail | Purpose | Enforcement |
|-----------|---------|-------------|
| **Cypher in Repos** | Clean architecture | Code review + architecture |
| **Apply Limits** | Prevent abuse | `validate_list_limit()` |
| **Project Fields** | Performance | CypherGenerator |
| **Result[T] Flow** | Consistent errors | Type system + patterns |

**Result:** Production-ready GraphQL API that's secure, performant, and maintainable.
