---
title: Query Architecture
updated: 2026-01-21
category: patterns
related_skills:
- skuel-search-architecture
- neo4j-cypher-patterns
related_docs: []
---

# Query Architecture

## Quick Start

**Skills:** [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md), [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)

For hands-on implementation:
1. Invoke `@neo4j-cypher-patterns` for Cypher query patterns
2. Invoke `@skuel-search-architecture` for unified search patterns
3. Continue below for complete query architecture

**Related Documentation:**
- [SEARCH_ARCHITECTURE.md](../architecture/SEARCH_ARCHITECTURE.md) - Unified search architecture

---

## Architecture — Intentional Layering, Not Fragmentation

SKUEL's query infrastructure is a **single facade with specialized backends**, not competing approaches:

```
UnifiedQueryBuilder  ← THE single entry point (fluent API)
├── ModelQueryBuilder      → cypher/ build_* functions (CRUD/search)
├── SemanticQueryBuilder   → semantic_queries.py (graph traversal)
└── TemplateQueryBuilder   → QueryBuilder service (optimization/templates)
```

These aren't three ways to do the same thing — they're three categories of query (data access, graph traversal, optimized templates) behind one discoverable API. `UnifiedQueryBuilder` IS the consolidation.

### Where Search Actually Flows (orientation)

A common misreading of this doc: the builders above are NOT the search path.
The `/search` page flows `SearchRouter.faceted_search()` →
`BaseService.graph_aware_faceted_search()` → `backend.faceted_search_raw()`
(`adapters/persistence/neo4j/_search_raw_mixin.py`), which composes its Cypher
from the plain builder *functions* in
`adapters/persistence/neo4j/query/cypher/crud_queries.py`
(`build_text_search_query`, `build_search_visibility_clause`, ...) plus the
relationship-filter fragments — no `UnifiedQueryBuilder` involved.

Use this doc when writing CRUD, analytics, traversal, or optimization
queries; use [SEARCH_ARCHITECTURE.md](../architecture/SEARCH_ARCHITECTURE.md)
(§ "One Search, End to End") to understand what a user-facing search runs.

### Supporting Infrastructure (Leaf-Level Utilities)

These are consumed by the query builders above, not alternative query paths:

| Utility | Purpose | Why It Exists Separately |
|---------|---------|--------------------------|
| `confidence_filter.py` | Cypher clause fragments for confidence filtering | Standardizes `coalesce()` patterns across all builders |
| `convert_value_for_neo4j()` | Python→Neo4j type conversion (enums, datetimes) | Neo4j driver doesn't auto-serialize; complements Pydantic (HTTP boundary) |
| `QueryConstraint.to_cypher()` | WHERE clause fragment generation | Adapter-layer model in `adapters/persistence/` — persistence models doing persistence work |

## Query Infrastructure (October 3, 2025)

### Core Principle: "Query models are infrastructure, not domain-specific"

**CRITICAL:** Query models were elevated from search domain to infrastructure level at `/adapters/persistence/neo4j/query/`. Boundary types (`QueryIntent`, `IndexStrategy`) live in `/core/models/query_types.py`; search boundary models (`FacetSetRequest`, `SearchQueryRequest`, `SearchResultDTO`) live in `/core/models/search_models.py`.

### Infrastructure Location

```
/adapters/persistence/neo4j/query/  # Infrastructure level, accessible to ALL domains
├── _query_models.py       # Adapter-layer query building models (QueryConstraint, QuerySort, etc.)
├── confidence_filter.py   # Cypher clause helpers for confidence-based filtering
├── cypher_template.py     # Query optimization strategies
├── cypher/                # Cypher query generators (crud, semantic, domain, relationship, intelligence)
│   └── _helpers.py        # Shared utilities (validate_label, validate_identifier, convert_value_for_neo4j)
├── unified_query_builder.py  # UnifiedQueryBuilder — THE single entry point
├── __init__.py            # Clean public API
└── README.md              # Usage documentation
```

### Correct Usage

```python
# ✅ CORRECT - Import from infrastructure
from core.models.query_types import QueryIntent, IndexStrategy  # Boundary types
from adapters.persistence.neo4j.query import (
    UnifiedQueryBuilder,   # THE single entry point
    QueryBuildRequest,     # Declarative query construction
    create_search_request, # Helper for common patterns
)
```

### Query Intent - Semantic Understanding

**Generic Intents (Cross-Domain):**
```python
QueryIntent.HIERARCHICAL     # Parent/child traversal
QueryIntent.PREREQUISITE     # Prerequisite chains
QueryIntent.PRACTICE         # Exercises/examples
QueryIntent.EXPLORATORY      # Broad discovery
QueryIntent.SPECIFIC         # Targeted search
QueryIntent.AGGREGATION      # Statistical queries
QueryIntent.RELATIONSHIP     # Graph traversal
```

**Domain-Specific Intents:**
```python
QueryIntent.GOAL_ACHIEVEMENT      # Goal achievement path analysis (Goals' default_context_intent)
```

See [Intent-Based Traversal Pattern](#intent-based-traversal-pattern-december-2025) below for complete architecture.

### Domain Usage Examples

**Knowledge Domain:**
```python
from adapters.persistence.neo4j.query import create_search_request
from core.models.query_types import QueryIntent

request = create_search_request(
    labels=["Ku"],
    search_text="quantum mechanics",
    intent=QueryIntent.PREREQUISITE
)
```

**Tasks Domain:**
```python
from adapters.persistence.neo4j.query import build_graph_context_query
from core.models.query_types import QueryIntent

context = build_graph_context_query(
    node_uid=task.uid,
    intent=QueryIntent.HIERARCHICAL,
    depth=3
)
```

## Query Building - Single Source of Truth (October 8, 2025)

### Core Principle: "One facade, specialized backends"

UnifiedQueryBuilder is THE single entry point. It routes internally to three specialized backends:

| Backend | Accessed Via | Purpose | When to Use |
|---------|-------------|---------|-------------|
| **ModelQueryBuilder** | `.for_model()` | `query/cypher/` build_* functions (CRUD/search) | Dynamic queries from dataclass introspection |
| **SemanticQueryBuilder** | `.semantic()` | semantic_queries.py (graph traversal) | Prerequisite chains, semantic context |
| **TemplateQueryBuilder** | `.template()` | QueryBuilder service (optimization) | Registered templates, performance-critical queries |

### Cypher Query Generators - Pure Cypher Queries

**Location:** `/adapters/persistence/neo4j/query/cypher/`

**Use for:** Model introspection queries, semantic relationship traversal, pure Cypher generation.

These are **module-level functions**, not methods on a class — import and call them
directly. (There is no `CypherGenerator` class; see [Naming](#no-cyphergenerator-class) below.)

```python
from adapters.persistence.neo4j.query import (
    build_count_query,
    build_list_query,
    build_prerequisite_chain,
    build_search_query,
    build_semantic_context,
    build_semantic_traversal,
)
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType

# Dynamic query generation (auto-introspects model fields)
query, params = build_search_query(
    Task,
    {'priority': 'high', 'status': 'in_progress'}
)

# List with pagination
query, params = build_list_query(
    Task,
    limit=50,
    order_by='due_date',
    order_desc=False
)

# Count with filters
query, params = build_count_query(
    Task,
    filters={'priority__in': ['high', 'urgent']}
)

# Semantic context traversal
query, params = build_semantic_context(
    node_uid="task.123",
    semantic_types=[
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL
    ],
    depth=3,
    min_confidence=0.8
)

# Prerequisite chain discovery
query, params = build_prerequisite_chain(
    node_uid="ku.advanced_python",
    semantic_types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING],
    depth=5
)

# Shortest path with semantic types
query, params = build_semantic_traversal(
    start_uid="ku.python_basics",
    end_uid="ku.async_programming",
    semantic_types=[SemanticRelationshipType.PROVIDES_FOUNDATION_FOR],
    max_depth=5
)
```

**Convenience Functions:**
```python
from adapters.persistence.neo4j.query import search, get_by, list_entities, count

# Shorthand for common operations
query, params = search(Task, priority='high', status='in_progress')
query, params = get_by(Task, 'uid', 'task-123')
query, params = list_entities(Task, limit=100, order_by='created_at')
query, params = count(Task, priority='high')
```

### Phase 2 Infrastructure Functions (January 2026)

**Location:** `/adapters/persistence/neo4j/query/cypher/crud_queries.py`

Three infrastructure functions were added to support BaseService operations:

| Function | Purpose | Used By |
|----------|---------|---------|
| `build_distinct_values_query()` | Get distinct field values | `list_user_categories()`, `list_all_categories()` |
| `build_hierarchy_query()` | Parent/child traversal | `get_hierarchy()` |
| `build_prerequisite_traversal_query()` | Prerequisite chains | `get_prerequisites()`, `get_enables()` |

**Usage Examples:**

```python
from adapters.persistence.neo4j.query.cypher import (
    build_distinct_values_query,
    build_hierarchy_query,
    build_prerequisite_traversal_query,
)

# Get distinct categories for a user
query, params = build_distinct_values_query("Task", "category", user_uid="user:123")

# Get parent/child hierarchy — the label must be a NeoLabel value ("Lp" is not one)
query, params = build_hierarchy_query("LearningPath", "lp.python-basics")

# Get prerequisites (outgoing) or enables (incoming)
query, params = build_prerequisite_traversal_query(
    "Ku", "ku.advanced-python", ["REQUIRES_KNOWLEDGE"],
    depth=3, direction="outgoing"  # or "incoming" for enables
)
```

**Record Extraction Pattern:**

These functions return `RETURN n` consistently. Use `from_neo4j_node` to convert:

```python
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

result = await backend.execute_query(query, params)
entities = [from_neo4j_node(record["n"], EntityClass) for record in result.value]
```

Record→model conversion happens below the hexagonal boundary — backends return typed domain models (Tier 6).

### QueryBuilder - Service Layer Facade (Legacy)

**Location:** `/adapters/persistence/neo4j/query_builders/query_builder.py`

**Status:** Legacy - Use UnifiedQueryBuilder for new code

**Architecture:** Facade orchestrating 5 specialized sub-services

QueryBuilder was decomposed from a 1,614-line monolith (November 10, 2025) into a 225-line facade coordinating 5 sub-services:

| Sub-Service | Lines | Purpose |
|-------------|-------|---------|
| **QueryOptimizer** | 748 | Index-aware optimization using Neo4j index stats |
| **QueryTemplateRegistry** | 433 | Template registration and retrieval |
| **QueryValidator** | 346 | Query validation, NL-to-Cypher conversion |
| **FacetedQueryBuilder** | 380 | Faceted search query construction |
| **GraphContextBuilder** | 55 | Graph traversal query generation |

**Location:** `/adapters/persistence/neo4j/query_builders/` (sub-services, alongside the facade)

**When to Use QueryBuilder Directly:**

Use ONLY when:
1. Implementing new UnifiedQueryBuilder features that need templates
2. Testing template functionality in isolation
3. Accessing optimization internals for analysis

**Recommended Usage:**

```python
# ✅ PREFERRED - Use UnifiedQueryBuilder (auto-initializes QueryBuilder)
from adapters.persistence.neo4j.query import UnifiedQueryBuilder

templates = UnifiedQueryBuilder(driver).list_templates()
result = await UnifiedQueryBuilder(driver).template("search").params(...).execute()

# ⚠️ LEGACY - Direct QueryBuilder usage (backward compatibility only)
from adapters.persistence.neo4j.query_builders import QueryBuilder

qb = QueryBuilder(schema_service)
templates = qb.get_template_library()
```

## Three-Layer Query Architecture (November 2025)

**Core Principle:** "Clear separation between user-facing API, orchestration, and utilities"

SKUEL uses a three-layer query architecture with distinct responsibilities:

```
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION LAYER: UnifiedQueryBuilder                     │
│ - User-facing fluent API                                    │
│ - PREFERRED for all new code                                │
│ - Method chaining: .for_model().filter().execute()         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ SERVICE LAYER: QueryBuilder (Facade)                        │
│ - Orchestrates 5 specialized sub-services                   │
│ - Legacy support - backward compatible                      │
│ - Optimization, templates, validation, faceted search       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE LAYER: query/cypher/ build_* functions       │
│ - Pure Cypher query utilities (module-level functions)      │
│ - Model introspection, semantic traversal                   │
│ - Shared by all layers                                      │
└─────────────────────────────────────────────────────────────┘
```

<a id="no-cyphergenerator-class"></a>
> **Naming — there is no `CypherGenerator` class.** The infrastructure layer is a
> *package of module-level functions* (`query/cypher/`, 54 `build_*` functions), not a
> type. `CypherGenerator` was a proposed class in a 2025 design note that was never
> built; the functions it proposed shipped as plain functions instead. The name is not
> importable — `from ...query.cypher import CypherGenerator` raises `ImportError`.
> Older docs and comments used it as an informal collective label for these functions.

### Layer 1: Application Layer → UnifiedQueryBuilder

**Location:** `/adapters/persistence/neo4j/query/unified_query_builder.py`

**Purpose:** User-facing API with fluent interface (method chaining)

**Used by:** All application code, domain services, route handlers

```python
from adapters.persistence.neo4j.query import UnifiedQueryBuilder

# Fluent API for generic CRUD operations
builder = UnifiedQueryBuilder(driver)
tasks = await builder.for_model(Task).filter(priority='high').limit(50).execute()

# Template-based queries
result = await UnifiedQueryBuilder(driver).template("search").params(
    labels=["Ku"],
    search_text="quantum mechanics",
    filters={'domain': 'TECH'}
).execute()

# Count queries
count = await builder.for_model(Task).count(status='completed')
```

**When to use:**
- **ALL new code** - this is the preferred API
- Building generic `.list()`, `.find_by()`, `.count()` methods
- Need fluent API with method chaining
- Generic CRUD across all domains

**Architecture Note:** UniversalBackend powers ALL domains (Tasks, Events, Habits, Goals, Finance, etc.), making UnifiedQueryBuilder's fluent API widely used.

**Security (March 2026):** `ModelQueryBuilder.order_by()` validates field names via `validate_field_name()` — invalid fields (e.g. injection attempts) are silently ignored with a logged warning.

### Layer 2: Orchestration Layer → QueryBuilder (Facade)

**Location:** `/adapters/persistence/neo4j/query_builders/query_builder.py`

**Purpose:** Orchestration facade coordinating 5 sub-services

**Status:** Legacy - maintained for backward compatibility

```python
from adapters.persistence.neo4j.query_builders import QueryBuilder

# ⚠️ LEGACY - Only use if absolutely necessary
qb = QueryBuilder(schema_service)

# Index-aware optimization (delegates to QueryOptimizer)
result = await qb.build_optimized_query(request)

# Template management (delegates to QueryTemplateRegistry)
templates = qb.get_template_library()

# Query validation (delegates to QueryValidator)
validation = await qb.validate_query(query_string)
```

**When to use:**
- Implementing new UnifiedQueryBuilder features
- Testing template/optimization internals
- Backward compatibility for existing code

**The 5 Sub-Services:**

All five live in `/adapters/persistence/neo4j/query_builders/`, alongside the facade.

1. **QueryOptimizer** (`query_optimizer.py`, 748 lines)
   - Index-aware query optimization using Neo4j index statistics
   - Automatic index selection for performance
   - Query plan analysis and explanation

2. **QueryTemplateRegistry** (`query_template_registry.py`, 433 lines)
   - Template registration and retrieval
   - Template library management
   - Parameterized query templates

3. **QueryValidator** (`query_validator.py`, 346 lines)
   - Query validation against schema
   - Natural language to Cypher conversion
   - Constraint checking

4. **FacetedQueryBuilder** (`faceted_query_builder.py`, 380 lines)
   - Faceted search query construction
   - Filter aggregation and counting
   - Multi-facet combination logic
   - Generic facet field names validated via `validate_field_name()` (March 2026)

5. **GraphContextBuilder** (`graph_context_builder.py`, 55 lines)
   - Graph traversal query generation
   - Relationship-aware context queries
   - Depth-limited graph exploration

### Layer 3: Infrastructure Layer → Cypher Query Generators

**Location:** `/adapters/persistence/neo4j/query/cypher/`

**Purpose:** Pure Cypher query utilities — module-level functions, no orchestration, no state

**Used by:** All layers (Application, Service, and direct usage)

```python
from adapters.persistence.neo4j.query import (
    build_prerequisite_chain,
    build_search_query,
    build_semantic_context,
)

# Model introspection queries
query, params = build_search_query(
    Task,
    {'priority': 'high', 'status': 'in_progress'}
)

# Semantic graph traversal
query, params = build_semantic_context(
    node_uid="ku.python_basics",
    semantic_types=[SemanticRelationshipType.PROVIDES_FOUNDATION_FOR],
    depth=3
)

# Prerequisite chains
query, params = build_prerequisite_chain(
    node_uid="ku.advanced_python",
    semantic_types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING],
    depth=5
)
```

**When to use:**
- Semantic relationship queries
- Prerequisite chains
- Cross-domain knowledge bridges
- Complex graph traversal
- When you need pure Cypher without orchestration

### Deprecation Path

**Recommended Migration:**

```python
# ❌ OLD - Direct QueryBuilder usage
from adapters.persistence.neo4j.query_builders import QueryBuilder
qb = QueryBuilder(schema_service)
result = await qb.search(labels=["Ku"], search_text="quantum")

# ✅ NEW - UnifiedQueryBuilder
from adapters.persistence.neo4j.query import UnifiedQueryBuilder
result = await UnifiedQueryBuilder(driver).template("search").params(
    labels=["Ku"],
    search_text="quantum"
).execute()
```

**Backward Compatibility:** QueryBuilder facade maintains the same API as the original monolithic implementation, ensuring zero breaking changes for existing code.

### Quick Reference Table

| Use Case | Layer | Builder | Example |
|----------|-------|---------|---------|
| List tasks by priority | Application | UnifiedQueryBuilder | `builder.for_model(Task).filter(priority='high')` |
| Count completed tasks | Application | UnifiedQueryBuilder | `builder.for_model(Task).count(status='completed')` |
| Template-based search | Application | UnifiedQueryBuilder | `builder.template("search").params(...)` |
| Get semantic prerequisites | Infrastructure | `query/cypher/` function | `build_prerequisite_chain(uid, types)` |
| Cross-domain bridges | Infrastructure | `query/cypher/` function | `build_cross_domain_bridges(domain_a, domain_b, types)` |
| Template internals | Service | QueryBuilder | `qb.get_template_library()` (legacy) |
| Index optimization | Service | QueryBuilder | `qb.build_optimized_query()` (legacy) |

## Filter Operators

All query builders support consistent filter operators:

| Operator | Usage | Example |
|----------|-------|---------|
| `eq` | Equality (default) | `priority='high'` |
| `gt` | Greater than | `due_date__gt=date.today()` |
| `lt` | Less than | `estimated_hours__lt=5.0` |
| `gte` | Greater than or equal | `due_date__gte=date.today()` |
| `lte` | Less than or equal | `priority_score__lte=8` |
| `contains` | String contains | `title__contains='urgent'` |
| `in` | List membership | `priority__in=['high', 'urgent']` |

## TypedDicts for Type-Safe Queries (January 2026)

**Core Principle:** "Replace `dict[str, Any]` with typed filter specs, update intents, and update payloads"

SKUEL provides TypedDicts in `/core/ports/query_types.py` for type-safe query/filter
construction, and frozen `*UpdateIntent` dataclasses (ADR-066) for Activity Domain updates:

### Filter Specifications

```python
from core.ports.query_types import ActivityFilterSpec, PropertyFilterSpec

# Activity domain filters with IDE autocomplete
filters: ActivityFilterSpec = {
    "status": "active",
    "category": "work",
    "sort_by": "due_date",
    "limit": 50,
}

# Property filters with operator support
property_filters: PropertyFilterSpec = {
    "strength__gte": 0.8,
    "confidence__gte": 0.7,
}
```

### Update values (ADR-066)

Activity Domain updates are **frozen `*UpdateIntent` dataclasses**, not TypedDicts —
the service `update` is parameterized over the update type `U` (`SupportsToChanges`):

```python
from core.models.task import TaskUpdateIntent

# Task update — the contract is the type; only set fields are written.
intent = TaskUpdateIntent(
    status=EntityStatus.COMPLETED.value,
    priority=Priority.HIGH.value,
)
await tasks_service.update_task(uid, intent)
```

Non-activity domains (curriculum, finance, reports) keep TypedDict patches, passed as a
`RawChanges` value (a `dict` subclass that satisfies `SupportsToChanges`):

```python
from core.models.update_contracts import RawChanges
from core.ports.query_types import LpUpdatePayload

updates: LpUpdatePayload = {"progress": 0.75, "is_completed": False}
await lp_service.update(uid, RawChanges(updates))
```

### Available query/update types

| Category | Types |
|----------|------------|
| **Filter Specs** | `BaseFilterSpec`, `ActivityFilterSpec`, `CurriculumFilterSpec`, `PrinciplesFilterSpec`, `PropertyFilterSpec` |
| **Activity update intents** | `TaskUpdateIntent`, `GoalUpdateIntent`, `HabitUpdateIntent`, `EventUpdateIntent`, `ChoiceUpdateIntent`, `PrincipleUpdateIntent` (in `core/models/<domain>/`) |
| **Non-activity update payloads** | `KuUpdatePayload`, `PsUpdatePayload`, `LpUpdatePayload`, `FinanceUpdatePayload`, `ReportUpdatePayload` (extend `BaseUpdatePayload`) |
| **Update contracts** | `SupportsToChanges`, `SupportsToIntent`, `RawChanges` (in `core/models/update_contracts.py`) |

See [Three-Tier Type System](/docs/patterns/three_tier_type_system.md#the-typed-write-boundary--update-intents--payloads-adr-066) and [ADR-066](/docs/decisions/ADR-066-typed-update-intents.md) for complete documentation.

## Benefits of Consolidation

1. **Single Source of Truth** - One authoritative implementation per query type
2. **Clear Responsibilities** - Each builder has distinct, non-overlapping purpose
3. **Two-Layer Architecture** - Backends use `UnifiedQueryBuilder` and the `query/cypher/` functions; services call named backend methods. A service cannot use these builders — `core/` may not import `adapters/` (SKUEL022) and may not author Cypher (SKUEL021).
4. **Type Safety** - Full type hints, static typing throughout
5. **Performance** - Pure Cypher benefits from query planner caching
6. **Maintainability** - 25% code reduction (2,427 → ~1,800 lines)
7. **Discoverability** - Clear two-layer pattern guides usage

## Post-Query Processors (January 2026)

### Core Principle: "Cypher for traversal, Python for calculation"

Some computed fields cannot be efficiently calculated in Cypher (e.g., percentage calculations, streak summaries). Post-Query Processors handle these calculations in Python after the query returns.

### Architecture

```
Cypher Query → Raw Data → Post-Processor → Computed Field
    │              │            │               │
    │              │            │               └─ graph_context["habit_summary"]
    │              │            └─ calculate_habit_streak_summary()
    │              └─ graph_context["contributing_habits"] = [{...}, {...}]
    └─ OPTIONAL MATCH (g)<-[:SUPPORTS_GOAL]-(h)
```

### Configuration in Registry

```python
# In relationship_registry.py
HABITS_CONFIG = DomainRelationshipConfig(
    relationships=(...),
    post_processors=(
        PostProcessor(
            source_field="habits",               # Input from Cypher
            target_field="habit_summary",        # Output field
            processor_name="calculate_habit_streak_summary",  # Function name
        ),
    ),
)
```

### BaseService Integration

`BaseService._parse_context_result()` automatically applies post-processors:

```python
for processor in config.post_processors:
    source_data = graph_context.get(processor.source_field, [])
    if source_data:
        graph_context[processor.target_field] = apply_processor(
            processor.processor_name, source_data
        )
```

### Available Processors

| Processor | Input | Output | Use Case |
|-----------|-------|--------|----------|
| `calculate_habit_streak_summary` | `habits[]` | `{total, active, total_streak_days, avg_streak}` | Habit analytics |
| `calculate_task_status_summary` | `tasks[]` | `{total, completed, in_progress, pending, completion_percentage}` | Task breakdown |

### Key Files

- **Processor functions:** `/adapters/persistence/neo4j/query/cypher/post_processors.py`
- **Registry config:** `/core/models/relationship_registry.py`
- **BaseService integration:** `/core/services/base_service.py` (`_parse_context_result`)

See [Service Consolidation Patterns](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md#4-post-query-processors) for detailed usage guide.

## Intent-Based Traversal Pattern (December 2025)

> **SUPERSEDED below this banner — historical (pre-Phase-1, 2026-06-04).** The
> intent-traversal/registry convergence retired this design. As of the curriculum-convergence
> teardown, **all 6 Activity Domains and all 3 curriculum domains (Ku/Ps/Lp) read graph context
> through mechanism B** — the shared `_CoreIntelligenceMixin.get_with_context` →
> `UnifiedRelationshipService.get_with_context`, with the edge vocabulary **registry-sourced** from
> `DomainConfig.cross_domain_relationship_types`, not per-domain `{Domain}RelationshipService`
> subclasses. The model-suggested `Entity.get_suggested_query_intent()` method and the dead
> `QueryIntent` values (`PRINCIPLE_EMBODIMENT`/`PRINCIPLE_ALIGNMENT`/`SCHEDULED_ACTION`) + the
> never-written `CONFLICTS_WITH_GOAL` edge are **deleted**. Direction-aware bucketing (PR #243)
> then folded `query_with_intent` onto the shared incident-edge producer
> `build_domain_context_with_paths` and **deleted** the flat `build_context_query_for_intent`;
> for a non-registry caller `QueryIntent`/`default_context_intent` now selects the edge slice
> from `_INTENT_EDGE_SETS` in `cross_domain_backend` (`HIERARCHICAL`/`PREREQUISITE`/`PRACTICE`/
> `GOAL_ACHIEVEMENT` + generic all-edges fallback). The content below is retained as historical
> context (it still references the deleted flat builder); a full rewrite is pending. The
> authoritative current state is
> [`docs/roadmap/intent-traversal-registry-convergence.md`](../roadmap/intent-traversal-registry-convergence.md)
> and [`INTENT_BASED_TRAVERSAL.md`](INTENT_BASED_TRAVERSAL.md).

### Core Principle: "Domain-specific semantic understanding of graph queries"

All 6 Activity Domains now use intent-based graph traversal via `GraphIntelligenceService.query_with_intent()`. Each domain has a suggested intent that optimizes Cypher queries for that domain's semantics.

### Complete 6-Domain Intent Architecture

| Domain | Intent | Focus | Relationships Traversed |
|--------|--------|-------|------------------------|
| Tasks | PRACTICE | Task execution and dependencies | EXECUTES_TASK, REQUIRES_KNOWLEDGE, DEPENDS_ON |
| Goals | GOAL_ACHIEVEMENT | Achievement path analysis | FULFILLS_GOAL, SUPPORTS_GOAL, SUBGOAL_OF, GUIDED_BY_PRINCIPLE |
| Principles | PRINCIPLE_EMBODIMENT | How principle is LIVED | GUIDED_BY_PRINCIPLE, INSPIRES_HABIT, GUIDES_GOAL |
| Habits | PRACTICE | Practice patterns and streaks | REINFORCES_KNOWLEDGE, SUPPORTS_GOAL, PREREQUISITE_HABIT |
| Choices | PRINCIPLE_ALIGNMENT | Principle-guided decisions | ALIGNED_WITH_PRINCIPLE, INFORMED_BY_KNOWLEDGE, SUPPORTS_GOAL |
| Events | SCHEDULED_ACTION | Task→Event execution context | EXECUTES_TASK, APPLIES_KNOWLEDGE, REINFORCES_HABIT |

### Architecture Pattern

Each domain's RelationshipService follows this pattern:

```python
class {Domain}RelationshipService(GenericRelationshipService[...]):
    def __init__(
        self,
        backend: {Domain}Operations,
        graph_intel: Any | None = None,  # GraphIntelligenceService
    ) -> None:
        super().__init__(...)
        self.graph_intel = graph_intel

    @requires_graph_intelligence("get_{entity}_with_context")
    async def get_{entity}_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[{Entity}, GraphContext]]:
        """Get entity with full graph context using intent-based traversal."""
        entity_result = await self.backend.get(uid)
        entity = self._context_to_domain_model(entity_result.value)

        # Use domain's suggested intent
        intent = entity.get_suggested_query_intent()  # e.g., GOAL_ACHIEVEMENT

        context_result = await self.graph_intel.query_with_intent(
            uid=uid,
            intent=intent,
            depth=depth,
        )
        return Result.ok((entity, context_result.value))

    @requires_graph_intelligence("get_{entity}_{analysis}_analysis")
    async def get_{entity}_{analysis}_analysis(self, uid: str) -> Result[dict[str, Any]]:
        """Domain-specific analysis using intent-based context."""
        # Returns domain-specific metrics and recommendations
        ...
```

### Service Wiring

Each facade service wires `graph_intel` to its RelationshipService:

```python
# In {Domain}Service.__init__():
self.relationships = {Domain}RelationshipService(
    backend=backend, graph_intel=graph_intel
)
```

### Model Integration

Each domain model returns its suggested intent:

```python
# In {Entity}.get_suggested_query_intent():
def get_suggested_query_intent(self) -> QueryIntent:
    return QueryIntent.{DOMAIN_INTENT}  # e.g., GOAL_ACHIEVEMENT
```

### GraphIntelligenceService Handlers

Each intent has a dedicated Cypher handler in `_build_context_query_for_intent()`:

```python
elif intent_value == QueryIntent.GOAL_ACHIEVEMENT.value:
    return f"""
    MATCH (origin {{uid: $uid}})
    OPTIONAL MATCH path = (origin)-[*0..{depth}]-(related)
    WHERE any(r in relationships(path) WHERE type(r) IN [
        'FULFILLS_GOAL', 'SUPPORTS_GOAL', 'REQUIRES_KNOWLEDGE',
        'SUBGOAL_OF', 'GUIDED_BY_PRINCIPLE'
    ])
    ...
    """
```

### Key Files

| Component | File |
|-----------|------|
| QueryIntent enum | `/core/models/query_types.py` |
| GraphIntelligenceService | `/core/services/infrastructure/graph_intelligence_service.py` |
| Domain RelationshipServices | `/core/services/{domain}/{domain}_relationship_service.py` |
| Domain Models | `/core/models/{domain}/{domain}.py` |

## Related Documentation

### Primary (This Document)
This is the **primary query architecture documentation**. Start here.

### Specialized Query Docs

| Document | Purpose | When to Use |
|----------|---------|-------------|
| [curriculum_query_patterns.md](curriculum/curriculum_query_patterns.md) | Curriculum-specific patterns (LP, KU, substance) | Learning path queries, life alignment |
| [PEDAGOGICAL_QUESTIONS.md](../intelligence/PEDAGOGICAL_QUESTIONS.md) | 7 core pedagogical questions and their production service cross-references | Understanding what the intelligence layer answers |

### Archived
- [QUERY_DECISION_MATRIX.md](../archive/patterns/QUERY_DECISION_MATRIX.md) - Phase 5/7 decision matrix (October 2025, superseded by this doc)

### Key Files

| Component | Location |
|-----------|----------|
| UnifiedQueryBuilder (facade) | `/adapters/persistence/neo4j/query/unified_query_builder.py` |
| Cypher Query Generators | `/adapters/persistence/neo4j/query/cypher/` |
| Query Models (adapter-layer) | `/adapters/persistence/neo4j/query/_query_models.py` |
| QueryBuilder (legacy facade) | `/adapters/persistence/neo4j/query_builders/query_builder.py` |
| GraphIntelligenceService | `/core/services/infrastructure/graph_intelligence_service.py` |
| QueryIntent enum | `/core/models/query_types.py` |

---

## FilteredContextProvider — Per-Domain Query Protocol

All 11 domain facades (6 Activity + 5 Curriculum) implement `get_filtered_context()` returning `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. This provides the standard interface through which both UI routes and intelligence services access per-domain entity state.

**Architecture:** UserContext is the **map** (broad snapshot from MEGA_QUERY, ~250 fields). `get_filtered_context()` is the **zoom lens** (per-domain filtered view with stats, on-demand).

**Shared skeleton** (`core/services/filtered_context.py`): `build_filtered_context()` enforces the fetch → stats → filter → sort → return pattern. Each domain provides callables for domain-specific stats, filters, and sorting.

**Protocol** (`core/ports/filtered_context_protocols.py`): `FilteredContextProvider` with common params `user_uid`, `status_filter`, `sort_by`. Concrete facades add domain-specific params with defaults (structural subtyping).

**`ListContext` TypedDict** (`core/ports/query_types.py`): `entities` (filtered list), `stats` (dict[str, int | float] — guaranteed `total` + `active` per `BaseStats` contract), `metadata` (dict[str, Any], optional — Tasks: projects/assignees; Principles/Goals/Habits: categories from enums).

**`BaseStats` contract**: Every `_compute_*_stats()` function returns at least `total: int` and `active: int`. Domain-specific keys are additional. Enables generic health checks without domain-specific knowledge.

**Typed accessors** (`core/utils/list_context_helpers.py`): `get_entities(ctx, Task)` → `list[Task]`, `get_stats(ctx)`, `get_metadata(ctx)` for type-safe `ListContext` consumption.

**Intelligence integration:** `UserContextIntelligence.filtered_providers` dict maps 11 domain names to `FilteredContextProvider` facades. Wired in `services_bootstrap/_intelligence_hub.py` via `_create_intelligence_hub()`. Consumed by `DailyPlanningMixin._generate_domain_health_warnings()` which queries all 6 Activity domain stats:
- **Single-domain:** >30 active tasks, no active goals, no habits tracked, 5+ events today, 5+ pending choices, no core principles
- **Cross-domain:** many goals but no habits (missing consistency anchors), many tasks but no goals (lacks strategic direction)

| Key File | Purpose |
|----------|---------|
| `core/services/filtered_context.py` | Shared `build_filtered_context()` skeleton |
| `core/ports/filtered_context_protocols.py` | `FilteredContextProvider` protocol |
| `core/ports/query_types.py` | `ListContext` TypedDict + `BaseStats` contract |
| `core/utils/list_context_helpers.py` | Typed accessors (`get_entities`, `get_stats`, `get_metadata`) |
| `core/services/user/intelligence/core.py` | `self.filtered_providers` dict |

**See:** `docs/patterns/UI_COMPONENT_PATTERNS.md` → "Single-Fetch `get_filtered_context()`" section

---

---

## `execute_query` in Services — Permitted Tiers

**Core Rule:** "Services call `self.backend.method_name()` — never inline Cypher via `execute_query()`."

In practice, `execute_query` appears in ~63 files. This is intentional — the rule applies to **domain CRUD**, not to every query in the system. The usage falls into clear tiers:

### Tier 1: Always Permitted — Cross-Domain Aggregation

Services that span multiple domains now use typed standalone backends (April 2026 migration). Two exceptions remain that inject `QueryExecutor` directly.

| Service | Access Pattern | Why |
|---------|---------------|-----|
| `UserProgressService` | `self.backend` (`UserProgressBackend`) | Traverses User + KU + PS domains for readiness/prerequisites |
| `AdminStatsService` | `self.backend` (`CrossDomainBackend`) | System-wide counts across all 6 Activity domains + knowledge |
| `LpIntelligenceService` | `self.backend` (`LpBackend`) | LP progression analytics across LP + User + KU |
| `GraphIntelligenceService` | `self.backend` | Cross-domain graph traversal for context retrieval |
| `user_context_queries.py` | `QueryExecutor` directly | MEGA-QUERY (full user state snapshot) |
| `CrossDomainQueryService` | `QueryExecutor` directly | 9 targeted cross-domain reads (returns frozen typed dataclasses) |

### Tier 2: Always Permitted — Infrastructure Services

Database-level concerns that operate below the domain layer. Most now use typed standalone backends.

| Service | Access Pattern | Why |
|---------|---------------|-----|
| `Neo4jSchemaService` | `self.neo4j_adapter.execute_query()` | Schema introspection (`CALL db.labels()`, `SHOW INDEXES`) |
| `Neo4jVectorSearchService` | `self.backend` (`VectorSearchBackend`) | Vector index operations (`db.index.vector.queryNodes()`) |
| `UnifiedIngestionService` | `self.backend` (`IngestionBackend`) + `self.driver.execute_query()` | Bulk cross-domain writes |
| `UnifiedRelationshipService` | `self.backend.execute_query()` | Cross-domain relationship ops with complex edge metadata |

### Tier 3: Always Permitted — BaseService Mixins

The BaseService mixins *implement* the backend abstraction. They call `execute_query` because they are the infrastructure that makes `self.backend.search()` work.

| Mixin | Methods |
|-------|---------|
| `SearchOperationsMixin` | `search()`, `get_by_relationship()`, `search_connected_to()` |
| `RelationshipOperationsMixin` | `get_prerequisites()`, `get_enables()` |
| `TimeQueryMixin` | `get_user_items_in_range()`, `get_upcoming()`, `get_overdue()`, `get_active()` |
| `ContextOperationsMixin` | `get_with_context()` |

### Tier 4: Tolerated — Domain Sub-Services

Domain sub-services that need complex domain-specific queries can call `self.backend.execute_query()` for one-off queries that go *through* the backend object (not around it).

**Current state (April 2026):** After Phases 1-14, nearly all domain sub-service queries have been migrated to named backend methods. One tolerated case remains: `semantic_relationship_linker.py` (1 `self.backend.execute_query()` call — through backend, acceptable).

**Decision criteria for new queries:**
- Query used in 2+ places → extract to domain backend method
- Query represents a core domain concept → extract to domain backend method
- Query is a one-off analytical query in a single sub-service → `execute_query` through backend is acceptable

---

**Last Updated:** April 11, 2026
**Status:** Active - Core pattern for all query operations in SKUEL
