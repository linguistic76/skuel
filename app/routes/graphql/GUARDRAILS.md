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
- ✅ `/core/models/query/cypher_generator.py` - Query builder
- ❌ `/routes/graphql/` - GraphQL resolvers (NO Cypher here!)

---

### 2. ✅ Apply Limits (Depth, Nodes, Timeouts)

**Rule:** All list queries and graph traversals have enforced limits.

**Why:**
- Prevent DoS attacks (requesting millions of items)
- Prevent expensive graph traversals (depth bombs)
- Ensure predictable performance

**Implementation:**

```python
# Configuration (/routes/graphql/config.py)
@dataclass
class GraphQLConfig:
    max_list_size: int = 100        # Maximum items in any list
    default_list_size: int = 20     # Default if not specified
    max_query_depth: int = 5        # Prevent deeply nested queries
    max_cypher_depth: int = 5       # Maximum graph traversal depth
    cypher_timeout_seconds: int = 10  # Kill slow queries

# Usage in resolvers
@strawberry.field
async def knowledge_units(
    self,
    limit: int | None = None  # Client can request, but we validate
) -> list[KnowledgeNode]:
    # GUARDRAIL: Validate and cap the limit
    safe_limit = validate_list_limit(limit)  # Max 100, default 20

    result = await service.list_knowledge_units(limit=safe_limit)
    return [...]
```

**Enforced Limits:**

| Parameter | Default | Maximum | Purpose |
|-----------|---------|---------|---------|
| `limit` | 20 | 100 | Items per list query |
| `query_depth` | 2 | 5 | Graph traversal depth |
| `timeout` | N/A | 30s | Total query execution |
| `cypher_timeout` | N/A | 10s | Individual Cypher query |

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

    # Success - convert domain model to GraphQL type
    ku = result.value
    return KnowledgeNode(
        uid=ku.uid,
        title=ku.title,
        # ... map other fields
    )

# ❌ WRONG - Direct exception handling
@strawberry.field
async def knowledge_unit(self, uid: str) -> KnowledgeNode:
    try:
        # Calling service that might raise exceptions
        ku = await service.get_knowledge_unit_direct(uid)
        return KnowledgeNode(...)
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

## Query Complexity (Future)

**Planned:** Cost-based query complexity analysis

```python
# Future: Assign costs to fields
@strawberry.field(complexity=10)
async def prerequisites(self) -> list[KnowledgeNode]:
    # This field costs 10 complexity points
    ...

# Query complexity calculated automatically
query {
  knowledgeUnits(limit: 10) {        # 10 points
    prerequisites {                   # 10 * 10 = 100 points
      prerequisites {                 # 100 * 10 = 1000 points (MAX!)
        uid
      }
    }
  }
}
# Total: 1110 points (exceeds max of 1000) → Rejected
```

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

All guardrail settings in `/routes/graphql/config.py`:

```python
from routes.graphql.config import GraphQLConfig, get_graphql_config

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
