---
title: BackendOperations Protocol Architecture
updated: 2026-01-07
category: patterns
related_skills: []
related_docs:
- /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
- /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
- /docs/patterns/TESTING_PATTERNS.md
---

# BackendOperations Protocol Architecture

*Last updated: 2026-01-07*

## Core Principle

**"One path forward, ISP-compliant composition"**

`BackendOperations[T]` is THE full backend protocol for SKUEL. It composes 7 focused sub-protocols following the Interface Segregation Principle (ISP).

## Protocol Hierarchy

```
BackendOperations[T]  ← THE protocol (UniversalNeo4jBackend implements this)
    ├── CrudOperations[T]              (6 methods)
    ├── EntitySearchOperations[T]      (3 methods)
    ├── RelationshipCrudOperations     (6 methods)
    ├── RelationshipMetadataOperations (3 methods)
    ├── RelationshipQueryOperations    (3 methods)
    ├── GraphTraversalOperations       (2 methods)
    └── LowLevelOperations             (2 methods + driver)
```

## Sub-Protocol Details

### CrudOperations[T] (6 methods)
Core CRUD operations for domain entities. The fundamental operations every backend must support.

```python
class CrudOperations[T: DomainModelProtocol](Protocol):
    async def create(self, entity: T) -> Result[T]: ...
    async def get(self, uid: str) -> Result[T | None]: ...
    async def get_many(self, uids: list[str]) -> Result[list[T | None]]: ...
    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]: ...
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]: ...
    async def list(self, limit: int = 100, offset: int = 0, ...) -> Result[tuple[list[T], int]]: ...
```

### EntitySearchOperations[T] (3 methods)
Search and query operations for entities.

```python
class EntitySearchOperations[T: DomainModelProtocol](Protocol):
    async def search(self, query: str, limit: int = 10) -> Result[list[T]]: ...
    async def find_by(self, limit: int = 100, **filters: Any) -> Result[list[T]]: ...
    async def count(self, **filters: Any) -> Result[int]: ...
```

### RelationshipCrudOperations (6 methods)
CRUD operations for graph relationships (edges).

```python
class RelationshipCrudOperations(Protocol):
    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]: ...
    async def get_relationships(self, uid: str, rel_type: RelationshipName | None = None, direction: Direction = "both") -> Any: ...
    async def has_relationship(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[bool]: ...
    async def create_relationships_batch(self, relationships: list[tuple[str, str, str, dict | None]]) -> Result[int]: ...
    async def delete_relationship(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[bool]: ...
    async def delete_relationships_batch(self, relationships: list[tuple[str, str, str]]) -> Result[int]: ...
```

### RelationshipMetadataOperations (3 methods)
Operations for relationship edge properties/metadata.

```python
class RelationshipMetadataOperations(Protocol):
    async def get_relationship_metadata(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[dict | None]: ...
    async def update_relationship_properties(self, from_uid: str, to_uid: str, relationship_type: RelationshipName, properties: dict) -> Result[bool]: ...
    async def get_relationships_batch(self, relationships: list[tuple[str, str, str]]) -> Result[list[dict]]: ...
```

### RelationshipQueryOperations (3 methods)
Query operations for graph relationships.

```python
class RelationshipQueryOperations(Protocol):
    async def count_related(self, uid: str, relationship_type: RelationshipName, direction: Direction = "outgoing", properties: dict | None = None) -> Result[int]: ...
    async def get_related_uids(self, uid: str, relationship_type: RelationshipName, direction: Direction = "outgoing", limit: int = 100, properties: dict | None = None) -> Result[list[str]]: ...
    async def count_relationships_batch(self, requests: list[tuple[str, str, str | None]]) -> Result[dict]: ...
```

### GraphTraversalOperations (2 methods)
Graph traversal operations for path finding and context queries.

```python
class GraphTraversalOperations(Protocol):
    async def traverse(self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False) -> Any: ...
    async def get_domain_context_raw(self, entity_uid: str, entity_label: str, relationship_types: list[str], depth: int = 2, min_confidence: float = 0.7, bidirectional: bool = False) -> Result[list[GraphContextNode]]: ...
```

### LowLevelOperations (2 methods + driver)
Low-level infrastructure operations.

```python
class LowLevelOperations(Protocol):
    driver: Any  # Neo4j AsyncDriver
    async def execute_query(self, query: str, params: dict | None = None) -> Result[list[dict]]: ...
    async def health_check(self) -> Result[bool]: ...
```

## Usage Patterns

### Domain Protocols Inherit from BackendOperations

Domain protocols (TasksOperations, GoalsOperations, etc.) inherit from `BackendOperations` and add domain-specific methods:

```python
class TasksOperations(BackendOperations["Task"], GraphRelationshipOperations, Protocol):
    """Task-specific operations beyond generic CRUD."""

    async def create_task(self, data: Metadata) -> Result[EntityUID]:
        """Create task from request data."""
        ...

    async def update_task(self, task_id: EntityUID, data: Metadata) -> Result[bool]:
        """Update task from request data."""
        ...
```

### Services Use Domain Protocols

```python
class TasksService(BaseService[BackendOperations[Task], Task]):
    """Task service with full backend capabilities."""

    def __init__(self, backend: BackendOperations[Task]) -> None:
        super().__init__(backend)
```

### Focused Dependencies (ISP-Compliant)

When a service only needs a subset of operations, depend on the specific sub-protocol:

```python
class SimpleReadService:
    """Service that only reads entities."""

    def __init__(self, backend: CrudOperations[Task]) -> None:
        self.backend = backend  # Only needs CRUD, not relationships

    async def get_task(self, uid: str) -> Result[Task | None]:
        return await self.backend.get(uid)


class RelationshipAnalyzer:
    """Service that only queries relationships."""

    def __init__(self, backend: RelationshipQueryOperations) -> None:
        self.backend = backend  # Only needs relationship queries

    async def count_dependencies(self, uid: str) -> Result[int]:
        return await self.backend.count_related(uid, RelationshipName.DEPENDS_ON)
```

## Benefits

1. **One Path Forward** - `BackendOperations` is THE protocol, no legacy alternatives
2. **ISP-Compliant** - Services can depend on only the operations they need
3. **Easier Testing** - Mock only the sub-protocols you use
4. **Clear Hierarchy** - 7 focused sub-protocols compose into 1 full protocol
5. **Type Safety** - Generic type parameter `T` provides compile-time safety

## Implementation

`UniversalNeo4jBackend[T]` is the single implementation that satisfies `BackendOperations[T]`:

```python
class UniversalNeo4jBackend[T: DomainModelProtocol]:
    """
    100% dynamic backend for all domain entities.
    Implements BackendOperations[T] protocol.
    """

    def __init__(self, driver: AsyncDriver, label: str, model_class: type[T]) -> None:
        self.driver = driver
        self.label = label
        self.model_class = model_class
```

### Internal Helper Methods (January 2026)

The backend includes internal helpers to reduce duplication:

**`_build_direction_pattern()`** - Consolidates ~30 lines of duplicated Cypher pattern building:

```python
def _build_direction_pattern(
    self,
    relationship_type: str,
    direction: Direction,
    source_var: str = "n",
    target_var: str = "related",
    rel_var: str | None = None,
    target_label: str | None = None,
) -> Result[str]:
    """Build Cypher pattern for directional relationship traversal.

    Used by: get_related_entities(), get_related_uids(), count_related()
    """
    match direction:
        case "outgoing":
            return Result.ok(f"({source_var})-[:{rel_type}]->({target_var})")
        case "incoming":
            return Result.ok(f"({source_var})<-[:{rel_type}]-({target_var})")
        case "both":
            return Result.ok(f"({source_var})-[:{rel_type}]-({target_var})")
```

### Driver Access Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `self.backend.method()` | Standard CRUD, search, relationships | `await self.backend.find_by(status="active")` |
| `self.backend.driver.execute_query()` | Complex graph queries returning EagerResult | Semantic relationships, aggregations |
| `self.backend.driver.session()` | Multi-statement transactions | AVOID - prefer execute_query() |

**Fail-Fast:** Driver guards are unnecessary in services - driver is REQUIRED at bootstrap.

## Key Files

| File | Purpose |
|------|---------|
| `/core/ports/base_protocols.py` | Protocol definitions |
| `/adapters/persistence/neo4j/universal_backend.py` | UniversalNeo4jBackend implementation |
| `/core/services/base_service.py` | BaseService using BackendOperations |
| `/core/ports/domain_protocols.py` | Domain-specific protocols |

## Cascade Deletion Pattern
*Last updated: 2026-01-07*

**Core Principle:** "Data integrity over convenience"

The `delete()` method's `cascade` parameter controls how entities with relationships are handled:

### The Problem

When you create an entity with a `user_uid`, the backend **automatically creates a user-entity relationship**:

```
(User)-[:HAS_TASK]->(Task)
(User)-[:HAS_GOAL]->(Goal)
(User)-[:HAS_EVENT]->(Event)
...
```

Neo4j correctly refuses to delete nodes that have existing relationships. This enforces referential integrity.

### The Solution: cascade=True

```python
# ❌ FAILS - Entity has relationships
result = await backend.delete("task_001")
# Error: "Cannot delete Task 'task_001' - has existing relationships"

# ✅ WORKS - Relationships are deleted first
result = await backend.delete("task_001", cascade=True)
```

### When to Use cascade=True

| Scenario | cascade | Rationale |
|----------|---------|-----------|
| **Test cleanup** | `True` | Tests create entities with user relationships |
| **User-initiated deletion** | `True` | User owns the entity and its relationships |
| **Orphan cleanup** | `True` | Removing abandoned data |
| **Selective deletion** | `False` | Only delete if no relationships (safety check) |

### Design Insight

The backend's behavior is **correct by design**:

1. **Auto-creates** user relationships on entity creation (no orphaned entities)
2. **Prevents** deletion of nodes with relationships (data integrity)
3. **Requires** explicit cascade for deletion (intentionality)

This pattern follows SKUEL's "fail-fast" philosophy - errors happen immediately at the point of misuse, not silently causing data inconsistencies later.

### Implementation Detail

When `cascade=True`, the backend executes:

```cypher
MATCH (n:Task {uid: $uid})
DETACH DELETE n
RETURN count(n) > 0 as deleted
```

When `cascade=False` (default):

```cypher
MATCH (n:Task {uid: $uid})
WHERE NOT (n)--()  // Only if no relationships
DELETE n
RETURN count(n) > 0 as deleted
```

---

## Philosophy

This architecture follows the SKUEL principle: **"Deal with fundamentals."**

- The protocol hierarchy reflects the fundamental operations a backend performs
- No backward compatibility baggage - one clear path forward
- ISP compliance means components only know what they need to know
- Type safety as translation - protocols encode domain language into compiler-verifiable structure
