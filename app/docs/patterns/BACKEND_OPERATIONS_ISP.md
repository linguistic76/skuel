---
title: BackendOperations Protocol Architecture
updated: 2026-07-26
category: patterns
related_skills: []
related_docs:
- /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
- /docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md
- /docs/patterns/TESTING_PATTERNS.md
- /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
---

# BackendOperations Protocol Architecture

*Last updated: 2026-07-26*

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
    async def update(self, uid: str, updates: Neo4jProperties) -> Result[T]: ...
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]: ...
    async def list(self, limit: int = 100, offset: int = 0, filters: FilterParams | None = None, ...) -> Result[tuple[list[T], int]]: ...
```

### EntitySearchOperations[T] (3 methods)
Search and query operations for entities.

```python
class EntitySearchOperations[T: DomainModelProtocol](Protocol):
    async def search(self, query: str, limit: int = 10) -> Result[list[T]]: ...
    async def find_by(self, limit: int = 100, **filters: Neo4jValue) -> Result[list[T]]: ...
    async def count(self, **filters: Neo4jValue) -> Result[int]: ...
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
        properties: Neo4jProperties | None = None,
    ) -> Result[bool]: ...
    async def get_relationships(self, uid: str, rel_type: RelationshipName | None = None, direction: Direction = "both") -> Any: ...
    async def has_relationship(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[bool]: ...
    async def create_relationships_batch(self, relationships: list[tuple[str, str, str, Neo4jProperties | None]]) -> Result[int]: ...
    async def delete_relationship(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[bool]: ...
    async def delete_relationships_batch(self, relationships: list[tuple[str, str, str]]) -> Result[int]: ...
```

### RelationshipMetadataOperations (3 methods)
Operations for relationship edge properties/metadata.

```python
class RelationshipMetadataOperations(Protocol):
    async def get_relationship_metadata(self, from_uid: str, to_uid: str, relationship_type: RelationshipName) -> Result[RelationshipMetadata | None]: ...
    async def update_relationship_properties(self, from_uid: str, to_uid: str, relationship_type: RelationshipName, properties: Neo4jProperties) -> Result[bool]: ...
    async def get_relationships_batch(self, relationships: list[tuple[str, str, str]]) -> Result[list[RelationshipMetadata]]: ...
```

### RelationshipQueryOperations (3 methods)
Query operations for graph relationships.

```python
class RelationshipQueryOperations(Protocol):
    async def count_related(self, uid: str, relationship_type: RelationshipName, direction: Direction = "outgoing", properties: Neo4jProperties | None = None) -> Result[int]: ...
    async def get_related_uids(self, uid: str, relationship_type: RelationshipName, direction: Direction = "outgoing", limit: int = 100, properties: Neo4jProperties | None = None) -> Result[list[str]]: ...
    async def count_relationships_batch(self, requests: list[tuple[str, str, str | None]]) -> Result[dict]: ...
```

### GraphTraversalOperations (2 methods)
Graph traversal operations for path finding and context queries.

```python
class GraphTraversalOperations(Protocol):
    async def traverse(self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False) -> Any: ...
    async def get_domain_context_raw(self, entity_uid: EntityUID, entity_label: str, relationship_types: list[str], depth: int = 2, min_confidence: float = 0.7, bidirectional: bool = False) -> Result[list[GraphContextNode]]: ...
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
class TasksService(BaseService[TasksOperations, Task]):
    """Task service with full backend capabilities."""

    def __init__(self, backend: TasksOperations) -> None:
        super().__init__(backend)
```

All 6 Activity Domain facades and their sub-services use domain-specific protocols, not the
generic `BackendOperations[T]`:

| Facade | Protocol | Sub-services |
|--------|----------|-------------|
| `TasksService` | `TasksOperations` | `TasksCoreService`, `TasksSearchService`, etc. |
| `GoalsService` | `GoalsOperations` | `GoalsCoreService`, `GoalsSearchService`, etc. |
| `HabitsService` | `HabitsOperations` | `HabitsCoreService`, `HabitsSearchService`, etc. |
| `EventsService` | `EventsOperations` | `EventsCoreService`, `EventsSearchService`, etc. |
| `ChoicesService` | `ChoicesOperations` | `ChoicesCoreService`, `ChoicesSearchService`, etc. |
| `PrinciplesService` | `PrinciplesOperations` | `PrinciplesCoreService`, `PrinciplesSearchService`, etc. |

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

### Introduce a Minimal Protocol, Have the Broad One Inherit It

The pattern above depends on a sub-protocol that *already exists*. When a service
uses only one slice of a broad protocol but **no narrow protocol covers that slice
yet**, do not pass the wide protocol and accept the over-broad dependency — extract
the minimal slice and make the broad protocol inherit it. The wide contract is
preserved for any future consumer; the dependency is honestly narrowed.

Worked example (`Neo4jSchemaService`): the service builds all schema introspection
(labels, properties, indexes, constraints) on a single primitive — raw query
execution — yet its constructor declared the full six-method `SchemaOperations`.
The other five methods live on the service itself, so the only adapter that drives
it (`Neo4jAdapter`) implements just `execute_query` and could not satisfy the wide
protocol.

```python
# core/ports/infrastructure_protocols.py
@runtime_checkable
class SchemaQueryExecutor(Protocol):
    """Minimal raw-query slice consumed by Neo4jSchemaService."""

    async def execute_query(self, query: str, params: Metadata | None = None) -> list[Metadata]:
        ...


@runtime_checkable
class SchemaOperations(SchemaQueryExecutor, Protocol):  # wide contract preserved
    """Database schema operations."""

    async def get_node_labels(self) -> list[str]: ...
    # ...four more introspection methods


# adapters/persistence/neo4j/schema_service.py
class Neo4jSchemaService:
    def __init__(self, neo4j_adapter: SchemaQueryExecutor, ...) -> None:  # narrowed
        self.neo4j_adapter = neo4j_adapter
```

**Why this is the right move, not a workaround:** the type error was true — the
adapter genuinely did not satisfy the declared contract. Suppressing it (`# type: ignore`)
would hide a real over-broad dependency. Narrowing to the slice actually used makes
the dependency honest, satisfies the type checker with zero suppressions, and keeps
`SchemaOperations` intact for any consumer that needs the full surface. This is the
mypy `arg-type` enforcement (see [functional-direction.md](../roadmap/functional-direction.md))
surfacing a design signal, not an annotation chore.

`LpProgressBackendOperations` (July 2026) is the same move in `curriculum_protocols.py`:
`LpProgressService` consumes three reads out of `LpOperations`' ~90-method surface, so
the three were extracted and `LpOperations` inherits the slice.

### When the Broad Protocol Must *Not* Inherit the Slice

The inheritance half of the pattern assumes the broad protocol is single-layer. When
it is **dual-layer** — the same name typing both `self.backend` inside a service *and*
a facade handed to a collaborator — inheriting a backend slice leaks backend
signatures to facade holders, and the two layers' signatures can legitimately differ.

`PsOperations` is the live example: it types `PsCoreService.backend` *and*
`EntityExtractor.knowledge_service` (which receives the `PsService` facade), it is
satisfied by neither `PsBackend` nor `PsService`, and its ORGANIZES signatures match
the *service*'s while `_OrganizesMixin`'s match the *backend*'s. So
`PsOrganizesBackendOperations`, `PsProgressBackendOperations` and
`PsIntelligenceBackendOperations` each stand alone, with signatures lifted from the
backend rather than from `PsOperations`. Accept the duplicated declaration and write
the reason at the seam — it is two contracts, not one repeated.

**Rule of thumb:** before making a broad protocol inherit a new slice, grep its
consumers. Every consumer typing `backend:`/`self.backend` → single-layer, inherit.
Any consumer receiving a *facade* → dual-layer, keep the slice separate.

### Verify Satisfiability, Don't Assume It

A protocol annotation that a green `./dev quality` accepts can still be a contract the
injected object cannot meet: an `Any`-typed factory parameter anywhere upstream
launders the argument at the injection point, so nothing is ever checked there. Prove
it directly instead:

```python
def _probe(b: TheConcreteBackend) -> None:
    x: TheProtocolYouChose = b   # MyPy must accept this
```

Two `Any` laundering points are known and deliberate:
`create_ps_sub_services(backend: Any, ...)` and
`create_curriculum_sub_services(backend: Any, ...)` in
`core/services/curriculum_domain_config.py`.

Note also that `UniversalNeo4jBackend` defines `__getattr__` for dynamic CRUD-alias
compliance, so **typing `self.backend` against a concrete backend subclass gives no
attribute checking at all** — every misspelled method resolves to `Any`. Typing
against the protocol is what turns those into `attr-defined` errors.

### A New Port Declares Typed Rows, Not `dict[str, Any]`

Narrowing the *method set* is only half the job. A slice whose reads return
`Result[list[dict[str, Any]]]` still leaves the row shape unchecked, so a change to a
Cypher `RETURN` clause's keys or value types drifts silently across the very boundary
you just drew. Give each read a per-query `TypedDict` in `core/ports/query_types.py`
(`*Row` for raw reads, `*Result` / `*Analytics` for what the service returns after
scoring) — the `_OrganizesMixin` ↔ `PsOrganizesBackendOperations` pair does this with
`OrganizerResult`, and `PsIntelligenceBackendOperations` follows with four `Ps*Row`
types.

Two rules make this real rather than decorative:

- **Construct the row at the adapter; never just annotate it.**
  `Neo4jQueryExecutor.execute[T](...) -> Result[T]` infers `T` **solely from the call
  site's return annotation** and, given no `processor`, returns the driver's raw
  `list[dict[str, Any]]` untouched. So a bare annotation is an *unchecked claim*: rename
  a `RETURN` alias and MyPy stays silent while the service reads the missing key as zero.
  **Nothing statically links a Cypher alias to a TypedDict key.** Pass a `processor` that
  builds each row by indexing its alias (`_to_practice_counts_rows` in
  `ps_intelligence_backend.py`; the explicit comprehension in `_OrganizesMixin`) — drift
  then raises `KeyError` at the boundary and surfaces as a failed `Result` through
  `@with_error_handling`. What the `TypedDict` buys *statically* is every consumer site.
- **Declare the row type on the protocol *and* the implementation, in the same change.**
  A `TypedDict` on the port with `dict[str, Any]` on the backend makes the port
  unsatisfiable — that is precisely the shape of several of the return-type conflicts
  that stop `PsBackend` from satisfying `PsOperations`. Re-run the satisfiability probe
  after changing either side.

Reserve `dict[str, Any]` for rows that are *genuinely* heterogeneous (variable `RETURN`
clauses), and mark those with a `# boundary:` comment per the `Any` policy.

## Benefits

1. **One Path Forward** - `BackendOperations` is THE protocol, no legacy alternatives
2. **ISP-Compliant** - Services can depend on only the operations they need
3. **Easier Testing** - Mock only the sub-protocols you use
4. **Clear Hierarchy** - 7 focused sub-protocols compose into 1 full protocol
5. **Type Safety** - Generic type parameter `T` provides compile-time safety

## Implementation

`UniversalNeo4jBackend[T]` is the single implementation that satisfies `BackendOperations[T]`.

### February 2026: Mixin Decomposition

`universal_backend.py` was decomposed from a 4,214-line monolith into a shell + 6 focused mixin files (initially 5 in February 2026; `_relationship_mixin.py` was further split into query and CRUD mixins in March 2026 — see below), following the same pattern used for `BaseService` in January 2026. The class declaration now uses multiple inheritance:

```python
class UniversalNeo4jBackend[T: DomainModelProtocol](
    _CrudMixin[T],
    _SearchMixin[T],
    _RelationshipQueryMixin[T],
    _RelationshipCrudMixin[T],
    _UserEntityMixin[T],
    _TraversalMixin,
):
    """
    100% dynamic backend for all domain entities.
    Implements BackendOperations[T] protocol.

    Methods live in focused mixin files (_*_mixin.py).
    Shell retains: __init__, helpers, factory functions.
    """

    def __init__(self, driver: AsyncDriver, label: str, model_class: type[T]) -> None:
        self.driver = driver
        self.label = label
        self.model_class = model_class
```

**Mixin Boundary Map:**

| File | Protocol(s) | Key Methods |
|------|-------------|-------------|
| `_crud_mixin.py` | `CrudOperations[T]` | `create`, `get`, `get_many`, `update`, `delete`, `list` |
| `_search_mixin.py` | `EntitySearchOperations[T]` | `find_by_date_range`*, `search`, `find_by`, `count`, `health_check`, `get_domain_context_raw`, `execute_query` |
| `_relationship_query_mixin.py` | `RelationshipMetadata*`, `RelationshipQuery*` | `get_related_entities`, `get_related_uids`, `get_relationship_metadata`, `get_edge_metadata`, `relate()`, batch queries |
| `_relationship_ordered_mixin.py` | Ordered/hierarchical queries | `get_ordered_related_uids`, `get_related_with_metadata`, `reorder_relationships`, `create_relationship_with_properties`, `get_hierarchical_children_{single,two_level,deep}`, lateral-getter wrappers (`get_prerequisites`, `get_enables`, `get_related`, `get_children`, `get_parent`, `get_depends_on`, `get_blocks`) |
| `_relationship_crud_mixin.py` | `RelationshipCrud*` | `create_relationship`, `delete_relationship`, `has_relationship`, `count_related`, `create_relationships_batch`, `_build_direction_pattern`, helpers |
| `_user_entity_mixin.py` | Generic user-entity ops | `create_user_relationship`, `get_user_entities`*, `count_user_entities`*, `update_relationship_access`, `delete_user_relationship` |
| `_traversal_mixin.py` | `GraphTraversalOperations` | `add_relationship`, `get_relationships`, `traverse`, `find_path` |

\* **Security hardened (March 2026):** Methods marked with `*` validate interpolated field names via `validate_field_name()` from `core/utils/validation_helpers.py` to prevent Cypher injection. Invalid field names are rejected with a logged warning and safe fallback values. Domain backends additionally use `_validate_rel_name()` (rejects non-`[A-Z0-9_]` characters in relationship names) and `_ALLOWED_ORDER_BY` (whitelist for ORDER BY fields) to prevent injection in domain-specific Cypher queries.
| `universal_backend.py` (shell) | Coordination | `__init__`, `_track_db_metrics`, `_default_filter_*`, `_inject_default_filters`, `__getattr__` |

**Cross-mixin dependencies** are declared via `TYPE_CHECKING` stubs (zero runtime cost):

```python
# In _crud_mixin.py — declares stubs for methods it calls from other mixins
if TYPE_CHECKING:
    async def create_user_relationship(  # from _UserEntityMixin
        self, user_uid: UserUID, entity_uid: EntityUID, ...
    ) -> Result[bool]: ...

    def _track_db_metrics(self, op: str, dur: float, is_error: bool = False) -> None: ...
    def _default_filter_clause(self, node_var: str = "n") -> str: ...
```

MRO is left-to-right. Mixins are stateless method containers — no `super().__init__()` required.

### March 2026: _relationship_mixin.py Split

The original February 2026 decomposition created a single `_relationship_mixin.py` (1,567 lines) for all relationship work. This was further split into two focused files:

| File | Lines | Responsibility |
|------|-------|---------------|
| `_relationship_query_mixin.py` | ~666 | `RelationshipMetadata*`, `RelationshipQuery*`: `get_related_entities`, `get_related_uids`, `get_relationship_metadata`, `get_edge_metadata`, fluent `relate()`, batch queries |
| `_relationship_crud_mixin.py` | ~983 | `RelationshipCrud*`: `create_relationship`, `delete_relationship`, `has_relationship`, `count_related`, `create_relationships_batch`, `_build_direction_pattern`, private helpers |

`_relationship_query_mixin.py` stubs `_build_direction_pattern` via `TYPE_CHECKING` (declared in `_relationship_crud_mixin.py`). Public API unchanged — 2,817 tests pass.

### April 2026: Ordered/hierarchical extraction

`_relationship_query_mixin.py` grew to ~1,174 lines through the typed-query migration. The ordered/hierarchical section was extracted into `_relationship_ordered_mixin.py` (~567 lines), leaving the core mixin at ~666 lines. The new mixin holds 14 methods: 3 ordered queries, 1 edge-property create, 3 hierarchical traversals (single/two-level/deep), and 7 lateral-getter convenience wrappers that forward to `get_related_entities` via MRO. Wired into `UniversalNeo4jBackend` parent list immediately after `_RelationshipQueryMixin`.

### Query Execution Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| `self.backend.method()` | **Services** — all domain queries | `await self.backend.find_by(status="active")` |
| `self.execute_query(query, params)` | **Domain backends only** — domain-specific Cypher | `await self.execute_query(query, {"uid": uid})` |

**Rule:** Services call named backend methods. Domain backends call `self.execute_query()` (inherited from `UniversalNeo4jBackend`). No code should use `self.driver.session()` directly — `execute_query()` handles session management, the driver-closed guard, and returns `Result[list[dict]]`.

**Fail-Fast:** Driver guards are unnecessary in services — driver is REQUIRED at bootstrap.

## Key Files

| File | Purpose |
|------|---------|
| `/core/ports/base_protocols.py` | Protocol definitions |
| `/adapters/persistence/neo4j/universal_backend.py` | Shell: `__init__`, helpers, factory functions (~527 lines) |
| `/adapters/persistence/neo4j/_crud_mixin.py` | `CrudOperations[T]` implementation |
| `/adapters/persistence/neo4j/_search_mixin.py` | `EntitySearchOperations[T]` implementation |
| `/adapters/persistence/neo4j/_relationship_query_mixin.py` | Relationship query + edge metadata + fluent `relate()` API |
| `/adapters/persistence/neo4j/_relationship_ordered_mixin.py` | Ordered/hierarchical traversals + lateral-getter convenience wrappers |
| `/adapters/persistence/neo4j/_relationship_crud_mixin.py` | Relationship CRUD + validation helpers |
| `/adapters/persistence/neo4j/_user_entity_mixin.py` | Generic user-entity relationship ops (5 methods) |
| `/adapters/persistence/neo4j/_traversal_mixin.py` | `GraphTraversalOperations` implementation |
| `/adapters/persistence/neo4j/_backend_helpers.py` | Shared validation: `_validate_rel_name()`, `_ALLOWED_ORDER_BY` |
| `/adapters/persistence/neo4j/_organizes_mixin.py` | `_OrganizesMixin` — ORGANIZES relationship management (12 methods) |
| `/adapters/persistence/neo4j/_learning_state_mixin.py` | `_LearningStateMixin` — user progress tracking (13 methods) |
| `/adapters/persistence/neo4j/_semantic_mixin.py` | `_SemanticMixin` — semantic relationships + graph analysis (11 methods) |
| `/adapters/persistence/neo4j/_knowledge_context_mixin.py` | `_KnowledgeContextMixin` — context, discovery, readiness (13 methods) |
| `/adapters/persistence/neo4j/_adaptive_mixin.py` | `_AdaptiveMixin` — practice, search, adaptive mastery (10 methods) |
| `/adapters/persistence/neo4j/backends/` | 31 domain backend subclasses across 9 cluster files (`activity_backends.py`, `curriculum_backends.py`, `exercise_backends.py`, `user_entry_backend.py`, `sharing_backend.py`, `forms_backends.py`, `templates_backends.py`, `collab_backends.py`, `misc_backends.py`). Import directly from the cluster file, e.g. `from adapters.persistence.neo4j.backends.activity_backends import TasksBackend`. |
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

**`UniversalNeo4jBackend` is the hexagonal boundary.** `BackendOperations[T]` is the protocol contract at that boundary — it defines what the service layer can ask of the backend without knowing it is Neo4j. Everything below the boundary is Neo4j-specific. Neo4j is a committed architectural choice, not a swappable adapter. See: [ADR-044](../decisions/ADR-044-neo4j-committed-architectural-choice.md).
