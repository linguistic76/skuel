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

## Quick Reference

SKUEL's query architecture uses a two-layer pattern with three specialized builders for optimal separation of concerns.

## Query Infrastructure (October 3, 2025)

### Core Principle: "Query models are infrastructure, not domain-specific"

**CRITICAL:** Query models were elevated from search domain to infrastructure level at `/core/models/query/`.

### Infrastructure Location

```
/core/models/query/  # Infrastructure level, accessible to ALL domains
├── _query_models.py       # Core query building, APOC operations
├── cypher_template.py     # Query optimization strategies
├── query_analysis.py      # Query parsing (legacy, consolidated)
├── cypher/                # Cypher query generators (domain, intelligence, etc.)
├── __init__.py            # Clean public API
└── README.md              # Usage documentation
```

### Correct Usage

```python
# ✅ CORRECT - Import from infrastructure
from core.models.query import (
    QueryIntent,           # Semantic query understanding
    IndexStrategy,         # Neo4j index optimization
    ApocQueryBuilder,      # APOC-powered queries (THE single source)
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

**Domain-Specific Intents (December 2025):**
```python
QueryIntent.GOAL_ACHIEVEMENT      # Goal achievement path analysis
QueryIntent.PRINCIPLE_EMBODIMENT  # How principle is LIVED across domains
QueryIntent.PRINCIPLE_ALIGNMENT   # Choice alignment with principles
QueryIntent.SCHEDULED_ACTION      # Event as scheduled task execution
```

See [Intent-Based Traversal Pattern](#intent-based-traversal-pattern-december-2025) below for complete architecture.

### ApocQueryBuilder - THE Single Source for APOC

```python
# Intent-based graph context queries
apoc_query = ApocQueryBuilder.build_graph_context_query(
    node_uid="task.123",
    intent=QueryIntent.HIERARCHICAL,
    depth=2
)

# Batch operations (10x faster than individual MERGE)
batch_query = ApocQueryBuilder.build_batch_merge_nodes(nodes)
batch_edges = ApocQueryBuilder.build_batch_merge_edges(edges)

# Schema-aware operations
merge_query = ApocQueryBuilder.build_schema_aware_merge(node, schema)
```

### Domain Usage Examples

**Knowledge Domain:**
```python
from core.models.query import create_search_request, QueryIntent

request = create_search_request(
    labels=["Ku"],
    search_text="quantum mechanics",
    intent=QueryIntent.PREREQUISITE
)
```

**Tasks Domain:**
```python
from core.models.query import ApocQueryBuilder, QueryIntent

context = ApocQueryBuilder.build_graph_context_query(
    node_uid=task.uid,
    intent=QueryIntent.HIERARCHICAL,
    depth=3
)
```

**Events Domain:**
```python
from core.models.query import ApocQueryBuilder

batch_query = ApocQueryBuilder.build_batch_merge_nodes(event_nodes)
```

## Query Building - Single Source of Truth (October 8, 2025)

### Core Principle: "One builder per query type, consolidated architecture"

**CRITICAL:** SKUEL has consolidated from 4 query builders to 3 specialized builders with clear responsibilities.

### The Three Query Builders

| Builder | Purpose | When to Use |
|---------|---------|-------------|
| **CypherGenerator** | Pure Cypher query generation | Dynamic queries, semantic graph traversal |
| **ApocQueryBuilder** | APOC-powered operations | Batch operations, schema-aware merges |
| **QueryBuilder** | Index-aware optimization | Performance-critical queries, search |

### Cypher Query Generators - Pure Cypher Queries

**Location:** `/core/models/query/cypher/`

**Use for:** Model introspection queries, semantic relationship traversal, pure Cypher generation.

```python
from core.models.query import CypherGenerator
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType

# Dynamic query generation (auto-introspects model fields)
query, params = CypherGenerator.build_search_query(
    Task,
    {'priority': 'high', 'status': 'in_progress'}
)

# List with pagination
query, params = CypherGenerator.build_list_query(
    Task,
    limit=50,
    order_by='due_date',
    order_desc=False
)

# Count with filters
query, params = CypherGenerator.build_count_query(
    Task,
    filters={'priority__in': ['high', 'urgent']}
)

# Semantic context traversal
query, params = CypherGenerator.build_semantic_context(
    node_uid="task.123",
    semantic_types=[
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL
    ],
    depth=3,
    min_confidence=0.8
)

# Prerequisite chain discovery
query, params = CypherGenerator.build_prerequisite_chain(
    node_uid="ku.advanced_python",
    semantic_types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING],
    depth=5
)

# Shortest path with semantic types
query, params = CypherGenerator.build_semantic_traversal(
    start_uid="ku.python_basics",
    end_uid="ku.async_programming",
    semantic_types=[SemanticRelationshipType.PROVIDES_FOUNDATION_FOR],
    max_depth=5
)
```

**Convenience Functions:**
```python
from core.models.query import search, get_by, list_entities, count

# Shorthand for common operations
query, params = search(Task, priority='high', status='in_progress')
query, params = get_by(Task, 'uid', 'task-123')
query, params = list_entities(Task, limit=100, order_by='created_at')
query, params = count(Task, priority='high')
```

### Phase 2 Infrastructure Functions (January 2026)

**Location:** `/core/models/query/cypher/crud_queries.py`

Five new infrastructure functions were added to support BaseService operations:

| Function | Purpose | Used By |
|----------|---------|---------|
| `build_distinct_values_query()` | Get distinct field values | `list_user_categories()`, `list_all_categories()` |
| `build_hierarchy_query()` | Parent/child traversal | `get_hierarchy()` |
| `build_prerequisite_traversal_query()` | Prerequisite chains | `get_prerequisites()`, `get_enables()` |
| `build_user_progress_query()` | User mastery data | `get_user_progress()` |
| `build_user_curriculum_query()` | User's curriculum | `get_user_curriculum()` |

**Usage Examples:**

```python
from core.models.query.cypher import (
    build_distinct_values_query,
    build_hierarchy_query,
    build_prerequisite_traversal_query,
    build_user_progress_query,
    build_user_curriculum_query,
)

# Get distinct categories for a user
query, params = build_distinct_values_query("Task", "category", user_uid="user:123")

# Get parent/child hierarchy
query, params = build_hierarchy_query("Lp", "lp:python-basics")

# Get prerequisites (outgoing) or enables (incoming)
query, params = build_prerequisite_traversal_query(
    "Ku", "ku:advanced-python", ["REQUIRES_KNOWLEDGE"],
    depth=3, direction="outgoing"  # or "incoming" for enables
)

# Get user progress on an entity
query, params = build_user_progress_query("Ku", "user:123", "ku:python-basics")

# Get user's curriculum entities
query, params = build_user_curriculum_query("Ku", "user:123", include_completed=False)
```

**Record Extraction Pattern:**

These functions return `RETURN n` consistently. Use `from_neo4j_node` to convert:

```python
from core.utils.neo4j_mapper import from_neo4j_node

result = await backend.execute_query(query, params)
entities = [from_neo4j_node(record["n"], EntityClass) for record in result.value]
```

BaseService provides `_records_to_domain_models()` helper for this pattern.

### ApocQueryBuilder - APOC Operations

**Location:** `/core/models/query/_query_models.py`

**Use for:** Batch operations, schema-aware merges, complex graph operations requiring APOC.

```python
from core.models.query import ApocQueryBuilder, QueryIntent

# Intent-based graph context
apoc_query = ApocQueryBuilder.build_graph_context_query(
    node_uid="task.123",
    intent=QueryIntent.HIERARCHICAL,
    depth=2
)

# Batch merge nodes (10x faster than individual MERGE)
batch_query = ApocQueryBuilder.build_batch_merge_nodes(nodes)

# Batch merge edges
batch_edges = ApocQueryBuilder.build_batch_merge_edges(edges)

# Schema-aware merge
merge_query = ApocQueryBuilder.build_schema_aware_merge(node, schema)
```

### QueryBuilder - Service Layer Facade (Legacy)

**Location:** `/core/services/query_builder.py`

**Status:** Legacy - Use UnifiedQueryBuilder for new code

**Architecture:** Facade orchestrating 5 specialized sub-services

QueryBuilder was decomposed from a 1,614-line monolith (November 10, 2025) into a 225-line facade coordinating 5 sub-services:

| Sub-Service | Lines | Purpose |
|-------------|-------|---------|
| **QueryOptimizer** | 689 | Index-aware optimization using Neo4j index stats |
| **QueryTemplateManager** | 335 | Template registration and retrieval |
| **QueryValidator** | 275 | Query validation, NL-to-Cypher conversion |
| **FacetedQueryBuilder** | 315 | Faceted search query construction |
| **GraphContextBuilder** | 68 | Graph traversal query generation |

**Location:** `/core/services/query/` (sub-services)

**When to Use QueryBuilder Directly:**

Use ONLY when:
1. Implementing new UnifiedQueryBuilder features that need templates
2. Testing template functionality in isolation
3. Accessing optimization internals for analysis

**Recommended Usage:**

```python
# ✅ PREFERRED - Use UnifiedQueryBuilder (auto-initializes QueryBuilder)
from core.models.query import UnifiedQueryBuilder

templates = UnifiedQueryBuilder(driver).list_templates()
result = await UnifiedQueryBuilder(driver).template("search").params(...).execute()

# ⚠️ LEGACY - Direct QueryBuilder usage (backward compatibility only)
from core.services.query_builder import QueryBuilder

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
│ INFRASTRUCTURE LAYER: CypherGenerator                       │
│ - Pure Cypher query utilities                               │
│ - Model introspection, semantic traversal                   │
│ - Shared by all layers                                      │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1: Application Layer → UnifiedQueryBuilder

**Location:** `/core/models/query/unified_query_builder.py`

**Purpose:** User-facing API with fluent interface (method chaining)

**Used by:** All application code, domain services, route handlers

```python
from core.models.query import UnifiedQueryBuilder

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

### Layer 2: Service Layer → QueryBuilder (Facade)

**Location:** `/core/services/query_builder.py`

**Purpose:** Orchestration facade coordinating 5 sub-services

**Status:** Legacy - maintained for backward compatibility

```python
from core.services.query_builder import QueryBuilder

# ⚠️ LEGACY - Only use if absolutely necessary
qb = QueryBuilder(schema_service)

# Index-aware optimization (delegates to QueryOptimizer)
result = await qb.build_optimized_query(request)

# Template management (delegates to QueryTemplateManager)
templates = qb.get_template_library()

# Query validation (delegates to QueryValidator)
validation = await qb.validate_query(query_string)
```

**When to use:**
- Implementing new UnifiedQueryBuilder features
- Testing template/optimization internals
- Backward compatibility for existing code

**The 5 Sub-Services:**

1. **QueryOptimizer** (`/core/services/query/query_optimizer.py`, 689 lines)
   - Index-aware query optimization using Neo4j index statistics
   - Automatic index selection for performance
   - Query plan analysis and explanation

2. **QueryTemplateManager** (`/core/services/query/query_template_manager.py`, 335 lines)
   - Template registration and retrieval
   - Template library management
   - Parameterized query templates

3. **QueryValidator** (`/core/services/query/query_validator.py`, 275 lines)
   - Query validation against schema
   - Natural language to Cypher conversion
   - Constraint checking

4. **FacetedQueryBuilder** (`/core/services/query/faceted_query_builder.py`, 315 lines)
   - Faceted search query construction
   - Filter aggregation and counting
   - Multi-facet combination logic
   - Generic facet field names validated via `validate_field_name()` (March 2026)

5. **GraphContextBuilder** (`/core/services/query/graph_context_builder.py`, 68 lines)
   - Graph traversal query generation
   - Relationship-aware context queries
   - Depth-limited graph exploration

### Layer 3: Infrastructure Layer → Cypher Query Generators

**Location:** `/core/models/query/cypher/`

**Purpose:** Pure Cypher query utilities (no orchestration, no state)

**Used by:** All layers (Application, Service, and direct usage)

```python
from core.models.query import CypherGenerator

# Model introspection queries
query, params = CypherGenerator.build_search_query(
    Task,
    {'priority': 'high', 'status': 'in_progress'}
)

# Semantic graph traversal
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python_basics",
    semantic_types=[SemanticRelationshipType.REQUIRES_FOUNDATION],
    depth=3
)

# Prerequisite chains
query, params = CypherGenerator.build_prerequisite_chain(
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
from core.services.query_builder import QueryBuilder
qb = QueryBuilder(schema_service)
result = await qb.search(labels=["Ku"], search_text="quantum")

# ✅ NEW - UnifiedQueryBuilder
from core.models.query import UnifiedQueryBuilder
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
| Get semantic prerequisites | Infrastructure | CypherGenerator | `CypherGenerator.build_prerequisite_chain(uid, types)` |
| Cross-domain bridges | Infrastructure | CypherGenerator | `CypherGenerator.build_cross_domain_bridges()` |
| Batch import 1000 KUs | Infrastructure | ApocQueryBuilder | `ApocQueryBuilder.build_batch_merge_nodes()` |
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

**Core Principle:** "Replace `dict[str, Any]` with typed filter specs and update payloads"

SKUEL provides TypedDicts in `/core/ports/query_types.py` for type-safe query construction:

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

### Update Payloads

```python
from core.ports.query_types import TaskUpdatePayload, GoalUpdatePayload

# Task update with type-checked fields
updates: TaskUpdatePayload = {
    "status": EntityStatus.COMPLETED.value,
    "priority": Priority.HIGH.value,
}

# Goal update with progress tracking
updates: GoalUpdatePayload = {
    "progress_percentage": 75.0,
    "completion_date": date.today(),
}
```

### Available TypedDicts

| Category | TypedDicts |
|----------|------------|
| **Filter Specs** | `BaseFilterSpec`, `ActivityFilterSpec`, `CurriculumFilterSpec`, `PrinciplesFilterSpec`, `PropertyFilterSpec` |
| **Update Payloads** | `TaskUpdatePayload`, `GoalUpdatePayload`, `HabitUpdatePayload`, `EventUpdatePayload`, `ChoiceUpdatePayload`, `PrincipleUpdatePayload`, `FinanceUpdatePayload`, `AssignmentUpdatePayload`, `KuUpdatePayload`, `LsUpdatePayload`, `LpUpdatePayload` |

See [Three-Tier Type System](/docs/patterns/three_tier_type_system.md#typeddicts-for-service-operations-january-2026) for complete documentation.

## Migration from Deprecated Builders

**DynamicQueryBuilder (DEPRECATED):**
```python
# ❌ OLD - DynamicQueryBuilder (deprecated)
from core.utils.dynamic_query_builder import DynamicQueryBuilder
query, params = DynamicQueryBuilder.build_search_query(Task, filters)

# ✅ NEW - CypherGenerator
from core.models.query import CypherGenerator
query, params = CypherGenerator.build_search_query(Task, filters)
```

**SemanticCypherBuilder (DEPRECATED):**
```python
# ❌ OLD - SemanticCypherBuilder (deprecated)
from core.services.semantic_cypher_builder import SemanticCypherBuilder
query, params = SemanticCypherBuilder.build_knowledge_context(uid, types)

# ✅ NEW - CypherGenerator (note method name change)
from core.models.query import CypherGenerator
query, params = CypherGenerator.build_semantic_context(uid, types)
```

**Method Name Changes:**
- `build_knowledge_context` → `build_semantic_context` (more generic, clearer intent)
- All other methods remain unchanged

## Benefits of Consolidation

1. **Single Source of Truth** - One authoritative implementation per query type
2. **Clear Responsibilities** - Each builder has distinct, non-overlapping purpose
3. **Two-Layer Architecture** - Backend uses UnifiedQueryBuilder, services use CypherGenerator
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
    │              │            │               └─ graph_context["milestone_progress"]
    │              │            └─ calculate_milestone_progress()
    │              └─ graph_context["milestones"] = [{...}, {...}]
    └─ OPTIONAL MATCH (g)-[:HAS_MILESTONE]->(m)
```

### Configuration in Registry

```python
# In relationship_registry.py
GOALS_CONFIG = DomainRelationshipConfig(
    relationships=(...),
    post_processors=(
        PostProcessor(
            source_field="milestones",           # Input from Cypher
            target_field="milestone_progress",   # Output field
            processor_name="calculate_milestone_progress",  # Function name
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
| `calculate_milestone_progress` | `milestones[]` | `{total, completed, percentage}` | Goal progress |
| `calculate_habit_streak_summary` | `habits[]` | `{total, active, total_streak_days, avg_streak}` | Habit analytics |
| `calculate_task_status_summary` | `tasks[]` | `{total, completed, in_progress, pending, completion_percentage}` | Task breakdown |

### Key Files

- **Processor functions:** `/core/models/query/cypher/post_processors.py`
- **Registry config:** `/core/models/relationship_registry.py`
- **BaseService integration:** `/core/services/base_service.py` (`_parse_context_result`)

See [Service Consolidation Patterns](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md#4-post-query-processors) for detailed usage guide.

## Intent-Based Traversal Pattern (December 2025)

### Core Principle: "Domain-specific semantic understanding of graph queries"

All 6 Activity Domains now use intent-based graph traversal via `GraphIntelligenceService.query_with_intent()`. Each domain has a suggested intent that optimizes Cypher queries for that domain's semantics.

### Complete 6-Domain Intent Architecture

| Domain | Intent | Focus | Relationships Traversed |
|--------|--------|-------|------------------------|
| Tasks | PRACTICE | Task execution and dependencies | EXECUTES_TASK, REQUIRES_KNOWLEDGE, DEPENDS_ON |
| Goals | GOAL_ACHIEVEMENT | Achievement path analysis | FULFILLS_GOAL, SUPPORTS_GOAL, SUBGOAL_OF, HAS_MILESTONE |
| Principles | PRINCIPLE_EMBODIMENT | How principle is LIVED | GUIDED_BY_PRINCIPLE, INSPIRES_HABIT, GUIDES_GOAL |
| Habits | PRACTICE | Practice patterns and streaks | REINFORCES_KNOWLEDGE, SUPPORTS_GOAL, PREREQUISITE_HABIT |
| Choices | PRINCIPLE_ALIGNMENT | Principle-guided decisions | ALIGNED_WITH_PRINCIPLE, INFORMED_BY_KNOWLEDGE, SUPPORTS_GOAL |
| Events | SCHEDULED_ACTION | Task→Event execution context | EXECUTES_TASK, PRACTICES_KNOWLEDGE, REINFORCES_HABIT |

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
    backend=backend, graph_intel=graph_intelligence_service
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
        'SUBGOAL_OF', 'HAS_MILESTONE', 'GUIDED_BY_PRINCIPLE'
    ])
    ...
    """
```

### Key Files

| Component | File |
|-----------|------|
| QueryIntent enum | `/core/models/query/_query_models.py` |
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
| [SKUEL_QUERY_USAGE_GUIDE.md](SKUEL_QUERY_USAGE_GUIDE.md) | 10 SKUEL query templates with examples | Service integration, template usage |

### Archived
- [QUERY_DECISION_MATRIX.md](../archive/patterns/QUERY_DECISION_MATRIX.md) - Phase 5/7 decision matrix (October 2025, superseded by this doc)

### Key Files

| Component | Location |
|-----------|----------|
| Cypher Query Generators | `/core/models/query/cypher/` |
| ApocQueryBuilder | `/core/models/query/_query_models.py` |
| QueryBuilder | `/core/services/query_builder.py` |
| GraphIntelligenceService | `/core/services/infrastructure/graph_intelligence_service.py` |
| QueryIntent enum | `/core/models/query/_query_models.py` |

---

**Last Updated:** January 24, 2026
**Status:** Active - Core pattern for all query operations in SKUEL
