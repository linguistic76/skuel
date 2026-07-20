---
name: neo4j-cypher-patterns
description: Expert guide to Neo4j Cypher queries and SKUEL's graph patterns. Use when writing Cypher queries, optimizing graph traversals, understanding relationship types, analyzing query performance, or when the user mentions Cypher, Neo4j, graph queries, or asks about relationships between entities.
allowed-tools: Read, Grep, Glob
---

# Neo4j Cypher Patterns for SKUEL

## Quick Start

SKUEL uses Neo4j as its graph database with a Entity Type Architecture. All domains flow toward LifePath (the destination).

### Entity Labels (Neo4j Node Labels)

All domain entities use **multi-label architecture**: every entity gets `:Entity` (universal base) plus a domain-specific label. Match on the domain label for fast indexed queries, or `:Entity` for cross-domain queries.

| Domain | Label | UID Format | Example |
|--------|-------|------------|---------|
| **Activity (6) — user-owned** | | | |
| Tasks | `Task` | `task_{slug}_{random}` | `task_fix-bug_abc123` |
| Goals | `Goal` | `goal_{slug}_{random}` | `goal_launch-product_def456` |
| Habits | `Habit` | `habit_{slug}_{random}` | `habit_daily-run_xyz789` |
| Events | `Event` | `event_{slug}_{random}` | `event_team-standup_ghi012` |
| Choices | `Choice` | `choice_{slug}_{random}` | `choice_accept-offer_jkl345` |
| Principles | `Principle` | `principle_{slug}_{random}` | `principle_small-steps_mno678` |
| **Curriculum (4) — shared content** | | | |
| Knowledge Units | `Ku` | `ku.{ns}.{slug}` (vault) or `ku_{slug}_{random}` (API) — both sanctioned, never sniff (ADR-013) | `ku.stoicism.dichotomy-of-control` |
| Path Steps | `PathStep` | `ps.{namespace}.{slug}` (authored `ps:{ns}:{slug}`; ingestion normalizes `:` → `.`) | `ps.python.intro` |
| Learning Paths | `LearningPath` | `lp.{namespace}.{slug}` (same colon→dot normalization) | `lp.python.developer` |
| Exercises | `Exercise` | varies | |
| **Ontology — shared taxonomy** | | | |
| Knowledge Domains | `KnowledgeDomain` | `kd.{domain_name}` | `kd.self_awareness` |
| **Curated Content — shared content** | | | |
| Resources | `Resource` | *(no fixed format)* | |
| **User-authored content + Reports (3) — ADR-054** | | | |
| User Entries | `UserEntry` | `ue_{slug}_{random}` | `ue_my-essay_abc123` |
| Activity Reports | `ActivityReport` | `ar_{random}` | |
| Entry Reports | `EntryReport` | `sr_{random}` | |
| **Destination** | | | |
| Life Path | `LifePath` | `lp_{random}` | `lp_abc123` |
| **Other** | | | |
| Users | `User` | `user_{name}` | `user_mike` |
| Finance | `Expense` | `expense_{random}` | `expense_abc123` |
| Groups | `Group` | `group_{slug}_{random}` | |

### Core Relationships (Most Common)

```cypher
// Ownership - Universal OWNS relationship (all Activity Domains)
(user:User)-[:OWNS]->(task:Task)
(user:User)-[:OWNS]->(goal:Goal)
(user:User)-[:OWNS]->(habit:Habit)

// Knowledge application
(task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
(goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku:Ku)
(habit:Habit)-[:REINFORCES_KNOWLEDGE]->(ku:Ku)

// Goal hierarchy
(task:Task)-[:FULFILLS_GOAL]->(goal:Goal)
(habit:Habit)-[:SUPPORTS_GOAL]->(goal:Goal)
(goal:Goal)-[:SUBGOAL_OF]->(parent:Goal)

// Knowledge structure
(ku:Ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Ku)
(ku:Ku)-[:ENABLES_KNOWLEDGE]->(enabled:Ku)
(ku:Ku)-[:RELATED_TO]->(related:Ku)

// MOC organization — any Ku can organize other Kus (emergent identity)
(moc:Ku)-[:ORGANIZES {order: 1}]->(child:Ku)

// Resource citations — curriculum cites reference material
(ps:PathStep)-[:CITES_RESOURCE]->(r:Resource)
(ku:Ku)-[:CITES_RESOURCE]->(r:Resource)

// Domain taxonomy (World Layer)
(ku:Ku)-[:IN_DOMAIN]->(d:KnowledgeDomain)

// Principles guidance
(goal:Goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
(choice:Choice)-[:ALIGNED_WITH_PRINCIPLE]->(principle:Principle)

// Life path (everything flows toward the life path)
// Designation flips entity_type on the LP node — it does NOT add a :LifePath
// label, so match by property, never by label.
(user:User)-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
(entity:Entity)-[:SERVES_LIFE_PATH]->(lp:Entity {entity_type: 'life_path'})
```

## Query Patterns

### Pattern 1: Get User's Entities

```cypher
// Get all active tasks for a user via universal OWNS relationship
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
WHERE t.status IN ['pending', 'in_progress']
RETURN t
ORDER BY t.priority DESC, t.due_date ASC
```

### Pattern 2: Entity with Graph Context

```cypher
// Get task with its full neighborhood
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
RETURN t,
       collect(DISTINCT ku) as applied_knowledge,
       collect(DISTINCT g) as goals,
       collect(DISTINCT dep) as dependencies
```

### Pattern 3: Relationship Traversal

```cypher
// Find all knowledge required for a goal (including transitive)
MATCH (g:Goal {uid: $goal_uid})
MATCH path = (g)-[:REQUIRES_KNOWLEDGE*1..3]->(ku:Ku)
RETURN DISTINCT ku
ORDER BY length(path)
```

### Pattern 4: Graph-Aware Search

```cypher
// Search tasks with relationship filter
MATCH (t:Task)
WHERE t.title CONTAINS $query OR t.description CONTAINS $query
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
WITH t, collect(ku) as knowledge
WHERE size(knowledge) > 0  // Only tasks that apply knowledge
RETURN t, knowledge
```

### Pattern 5: User Learning Progress

```cypher
// Get user's mastery state for knowledge units
MATCH (u:User {uid: $user_uid})-[r:MASTERED|IN_PROGRESS|VIEWED]->(ku:Ku)
RETURN ku.uid,
       type(r) as status,
       r.mastery_score as score,
       r.mastered_at as mastered_at
```

## Query Builders (SKUEL Infrastructure)

SKUEL has two query builders for domain services (SKUEL001: no APOC in domain services):

| Builder | Location | Use Case |
|---------|----------|----------|
| **UnifiedQueryBuilder** | `adapters/persistence/neo4j/query/` | Generic CRUD (used by backends) |
| **CypherGenerator** | `adapters/persistence/neo4j/query/cypher/` | Pure Cypher, semantic traversal |

**SKUEL001 linter rule:** APOC is scoped to `apoc.meta.*` (schema introspection only). Domain services use pure Cypher — never APOC in `core/services/`.

### Three-Layer Architecture

```
Layer 1: UniversalNeo4jBackend (Generic CRUD)
├── Uses UnifiedQueryBuilder for generic operations
└── Powers ALL 25 entity types with CRUD, search, relationships

Layer 2: Domain Backends (Domain-Specific Cypher)
├── 31 typed subclasses in backends/ (9 cluster files — import directly from the cluster file)
├── ~23 standalone backends in adapters/persistence/neo4j/ (CrossDomainBackend, UserBackend, VectorSearchBackend, ZPDBackend, EmbeddingsBackend, IngestionBackend, ...) — full inventory: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
├── Domain-specific relationship Cypher (ORGANIZES, SHARES_WITH, FULFILLS_EXERCISE, etc.)
└── Rule: If a Cypher query uses domain-specific relationships, it belongs here

Layer 3: Services (Business Logic + Cross-Domain Aggregation)
├── Domain services delegate to backend methods, NOT execute_query()
├── Two service-layer Cypher exceptions (both use QueryExecutor directly):
│   ├── user_context_queries.py — MEGA-QUERY (full user state snapshot)
│   └── CrossDomainQueryService — 9 targeted cross-domain reads (returns frozen typed dataclasses)
└── Orchestration, events, validation — no other inline Cypher
```

## Filter Operators

All query builders support these operators:

| Operator | Usage | Cypher Output |
|----------|-------|---------------|
| `eq` (default) | `priority='high'` | `n.priority = 'high'` |
| `gt` | `due_date__gt=date` | `n.due_date > $date` |
| `lt` | `hours__lt=5.0` | `n.hours < 5.0` |
| `gte` | `due_date__gte=date` | `n.due_date >= $date` |
| `lte` | `score__lte=8` | `n.score <= 8` |
| `contains` | `title__contains='urgent'` | `n.title CONTAINS 'urgent'` |
| `in` | `priority__in=['high', 'urgent']` | `n.priority IN ['high', 'urgent']` |

## Intent-Based Traversal

All 9 domains (6 Activity + Ku/Ps/Lp) read graph context through **mechanism B**: the shared
`_CoreIntelligenceMixin.get_with_context` → `UnifiedRelationshipService.get_with_context`. The edge
vocabulary is **registry-sourced** from `DomainConfig.cross_domain_relationship_types` (the single
source of truth) — there is no per-domain `get_suggested_query_intent()` (deleted) and no per-domain
`{Domain}RelationshipService` subclass.

Both graph readers (`query_with_intent` and `get_cross_domain_context`) now run ONE
incident-edge-attributed producer (`build_domain_context_with_paths`); the old flat
`build_context_query_for_intent` is deleted (PR #243). For a non-registry caller,
`QueryIntent` / a domain's `default_context_intent` selects the edge slice from
`_INTENT_EDGE_SETS` (in `cross_domain_backend`). Those slices:

| Intent | Focus Relationships |
|--------|---------------------|
| `HIERARCHICAL` | HAS_SUBTASK, HAS_SUBGOAL, HAS_SUBHABIT, HAS_SUBEVENT, HAS_SUBCHOICE, HAS_SUBPRINCIPLE, HAS_STEP, ORGANIZES |
| `PREREQUISITE` | REQUIRES_KNOWLEDGE, PREREQUISITE_FOR, ENABLES |
| `PRACTICE` | REINFORCES_KNOWLEDGE, APPLIES_KNOWLEDGE |
| `GOAL_ACHIEVEMENT` | FULFILLS_GOAL, SUPPORTS_GOAL, SUBGOAL_OF, GUIDED_BY_PRINCIPLE, CONTRIBUTES_TO_GOAL |
| else (`EXPLORATORY`/`SPECIFIC`/`AGGREGATION`/`RELATIONSHIP`) | generic traversal, no edge filter |

**See:** `docs/roadmap/intent-traversal-registry-convergence.md` (authoritative).

## Index Architecture (Bootstrap)

Neo4j indexes are created automatically at startup via `Neo4jSchemaManager` in `services_bootstrap/compose.py`:

| Index Type | Method | When Created | Purpose |
|-----------|--------|-------------|---------|
| **Domain indexes** | `sync_domain_indexes()` | Always | UID, user_uid, status, date, composite — 48 indexes |
| **Full-text indexes** | `sync_fulltext_indexes()` | Always | Lucene keyword search across 14 domains (6 Activity + 4 Curriculum + 2 Learning Loop + 2 Forms) — Cypher-first foundation |
| **Auth indexes** | `sync_auth_indexes()` | Always | Rate limiting, session lookup, email uniqueness |
| **Vector indexes** | `sync_vector_indexes()` | FULL tier only | 1024-dim cosine — bootstrap creates Entity, ContentChunk, ReferenceChunk; Goal + Task per-label indexes via `scripts/create_vector_indexes.py` (5 total live) |

> **Server side:** the Java Vector API (SIMD) must be enabled for these to run optimally —
> `NEO4J_server_jvm_additional=--add-modules jdk.incubator.vector` in `infrastructure/docker-compose.yml`.
> See [NEO4J_SERVER_TUNING.md](../../../docs/patterns/NEO4J_SERVER_TUNING.md).

Full-text indexes are the **Cypher-first search foundation** — always available, no embeddings needed:

```cypher
// Full-text search (Lucene-based, relevance-ranked)
CALL db.index.fulltext.queryNodes('task_fulltext_idx', 'urgent deadline')
YIELD node, score
RETURN node.uid, node.title, score

// Vector search (FULL tier only, 1024-dim; OpenAI text-embedding-3-small — ADR-068, BGE staged)
CALL db.index.vector.queryNodes('entity_embedding_idx', 10, $embedding)
YIELD node, score
RETURN node.uid, node.title, score
```

All DDL is idempotent (`IF NOT EXISTS`) — safe on every startup.

## Best Practices

### 0. Never MATCH by uid without a label guard (G13 shadow rule)

The chunk store's `:Content` node shares its entity's uid, so an unlabeled
`MATCH (n {uid: $uid})` binds BOTH nodes — duplicated rows, doubled MERGE
edges, misread labels (found live: doubled INTERACTION_DURING, systems
review 2026-07-03; codebase-wide sweep in Arc E). Two sanctioned forms:

```cypher
// Entity-only paths — bind the universal base label
MATCH (n:Entity {uid: $uid})

// Mixed-label paths (endpoints may be User/Group/…) — exclude the shadow
MATCH (n {uid: $uid}) WHERE NOT n:Content
```

### 1. Always Use Parameters

```cypher
// GOOD - parameterized
MATCH (t:Task {uid: $uid})

// BAD - string interpolation (SQL injection risk)
MATCH (t:Task {uid: '${uid}'})
```

**Exception: labels, property names, and relationship types cannot be parameterized in Neo4j.** SKUEL validates all interpolated values at the infrastructure boundary:

```python
# Shared guards in _helpers.py (used by all 5 query builder modules)
from adapters.persistence.neo4j.query.cypher._helpers import validate_label, validate_identifier
validate_label(label)             # raises ValueError if not a known NeoLabel value
validate_identifier(field)        # raises ValueError if not a safe identifier (^[a-zA-Z_][a-zA-Z0-9_]*$)

# Relationship types — also validated in _build_direction_pattern() (single choke point for mixin Cypher)
# Uses validate_relationship_type() from core/utils/validation_helpers.py
# Accepts RelationshipName enum values OR safe identifiers

# Field names — validated in _search_mixin.py, _user_entity_mixin.py, and all query builders
from core.utils.validation_helpers import validate_field_name
validate_field_name(name)    # regex check, max 64 chars
```

**Coverage:** All 5 query builder modules (`crud_queries.py`, `domain_queries.py`, `relationship_queries.py`, `semantic_queries.py`, `intelligence_queries.py`) validate labels, field names, relationship types, and property keys before f-string interpolation. `_build_direction_pattern()` is the single choke point for mixin-level relationship Cypher (`get_related_entities`, `get_related_uids`, `count_related`). `traverse()` and `find_path()` validate pipe-separated patterns.

The same pattern applies to DDL (vector indexes, schema creation) — validate `label`, `field_name`, and `similarity` before building the query string. See `adapters/persistence/neo4j/neo4j_schema_manager.py` for the pattern.

### 2. Use OPTIONAL MATCH for Nullable Relationships

```cypher
// GOOD - returns task even without knowledge
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)

// RISKY - returns nothing if no knowledge relationship
MATCH (t:Task {uid: $uid})-[:APPLIES_KNOWLEDGE]->(ku:Ku)
```

### 3. Use COLLECT to Prevent Cartesian Products

```cypher
// GOOD - one row per task
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
RETURN t, collect(DISTINCT ku) as knowledge, collect(DISTINCT g) as goals

// BAD - cartesian product of knowledge × goals
MATCH (t:Task {uid: $uid})
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)
RETURN t, ku, g
```

### 4. Use RelationshipName Enum (SKUEL013)

```python
from core.models.relationship_names import RelationshipName

# GOOD - type-safe, IDE autocomplete
query = f"MATCH (a)-[:{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(b)"

# GOOD - multi-line with Neo4j property maps (escape braces!)
query = f"""
MATCH (parent:Entity {{uid: $uid}})-[:{RelationshipName.HAS_SUBTASK.value}]->(child)
RETURN child
"""

# BAD - typo-prone, no compile-time check
query = "MATCH (a)-[:REQURES_KNOWLEDGE]->(b)"  # typo!
```

### 5. Check Ownership for Multi-Tenant Security

```cypher
// GOOD - ownership verified via universal OWNS relationship
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task {uid: $task_uid})
RETURN t

// BAD - no ownership check (security risk)
MATCH (t:Task {uid: $task_uid})
RETURN t
```

**Note:** The OWNS relationship is the universal ownership pattern. Per-domain variants (HAS_TASK, HAS_GOAL, etc.) exist in RelationshipName but backends neither write nor query them — always use OWNS.

### 6. Per-Query Server-Side Timeout (TimedDriver)

Every query through the shared driver carries a server-side per-tx ceiling. **Default 120s** (env `NEO4J_TRANSACTION_TIMEOUT`); a runaway is aborted by the Neo4j server, not by the client hanging. Bulk ingestion is already wrapped to 600s; MEGA-QUERY and analytics inherit the default. Startup DDL (Neo4jSchemaManager) is intentionally untimed (raw driver).

If a *specific* query legitimately needs longer, wrap the call site:

```python
from adapters.persistence.neo4j.timed_driver import (
    neo4j_query_timeout,
    unbounded_neo4j_query_timeout,
)

# Bound the enclosed block to 300s instead of the default 120s:
with neo4j_query_timeout(300.0):
    async with self._driver.session() as session:
        result = await session.run(long_running_aggregation, params)

# Escape hatch for one-off admin maintenance through the wrapped driver:
with unbounded_neo4j_query_timeout():
    ...
```

**Rule:** Don't wrap by default — the 120s ceiling exists to catch *unintended* runaways (a Cartesian explosion, a typo'd `MATCH` with no anchor). Only wrap when you know the query is legitimately long-running. The `with` block MUST enclose the full `await` chain — the override is a `ContextVar` read at call time, so awaited work outside the block is unbounded by it.

See: [`docs/patterns/NEO4J_QUERY_TIMEOUT.md`](/docs/patterns/NEO4J_QUERY_TIMEOUT.md) for the override mechanism, when-to-wrap table, and the `ContextVar` + `asyncio.create_task` caveat.

### 7. Schema-Change Monitoring (opt-in)

`SchemaChangeDetector` (`core/services/schema_change_detector.py`) fingerprints the live Neo4j schema (labels, indexes, constraints, relationship types) and, on drift, invalidates the adapter's lazily-built query-optimization caches (`_index_aware_builder`, `_enhanced_templates`) via the auto-registered `AdaptiveOptimizationHandler`.

It is exposed as an **on-demand** capability on the adapter — `Neo4jAdapter.check_schema_changes()`, `initialize_schema_monitoring()`, `stop_schema_monitoring()` — and is wired into the composition root as an **opt-in background poll**:

```bash
# In .env — both default off / 900s
NEO4J_SCHEMA_MONITORING=true            # start the background poll at startup
NEO4J_SCHEMA_MONITORING_INTERVAL=900    # poll interval (seconds); must be ≥ 1
```

- **Off by default.** Gated by `config.database.schema_monitoring_enabled`, *not* by `INTELLIGENCE_TIER` — it's plain graph infrastructure (no API calls), so it can run in either tier. Keeping it off by default preserves the CORE-tier "no background workers" guarantee.
- **Where it's wired.** `services_bootstrap/compose.py` calls `initialize_schema_monitoring()` right after the startup DDL sync (so it baselines against the freshly-synced schema); `shutdown_skuel` calls `stop_schema_monitoring()`. The detector owns its own `asyncio` poll task, which lives on the single loop shared by bootstrap and `server.serve()`.
- **Non-fatal.** A failed start warns and continues — monitoring is an optimization, never a correctness gate.
- **Interval is validated at the env boundary** (`DatabaseConfig.from_env` rejects values < 1): a non-positive interval is truthy and would make `asyncio.sleep(<=0)` busy-spin Neo4j introspection.

**Rule:** Don't enable it where the schema is static after startup DDL (the common case) — it catches nothing at runtime and adds periodic introspection load. Enable it only where schema genuinely drifts mid-session.

### 8. Coerce string-stored temporals in comparisons

Date/datetime fields are stored as **ISO strings** (DTO `.isoformat()`), so comparing them directly to `date()`/`datetime()` yields `null` and silently drops rows. Wrap the stored side: `datetime(n.created_at) >= datetime($w)`. `datetime()` is universally safe (parses date and datetime strings, no-op on natives); `date()` **errors on a datetime string** → use `date(datetime(field))`. The writer decides the type: DTO `.isoformat()` → string (coerce); Cypher `= datetime()` → native (leave). **See [PATTERNS.md](PATTERNS.md) Pattern 10 + Key Rules #17–18.**

### 9. Relationship reads/writes go through real, config-keyed methods

`UnifiedRelationshipService` has no `__getattr__` — calling a method it doesn't define is an `AttributeError`, and `get_related_uids(method_key, uid)` takes an **exact** `DomainRelationshipConfig` method-key that **fails closed** on a typo. Don't invent `get_<x>_<y>` methods or guess keys; never trust a mocked relationship service (it resolves any attribute). **See [/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) § Phantom methods & keys.**

## Additional Resources

- [reference.md](reference.md) - Curated relationship type catalog (enum has 169 members)
- [examples.md](examples.md) - Full query examples for each domain
- [docs/patterns/NEO4J_QUERY_TIMEOUT.md](/docs/patterns/NEO4J_QUERY_TIMEOUT.md) - Per-query server-side timeout (TimedDriver, override mechanism)
- [ADR-064](/docs/decisions/ADR-064-neo4j-per-query-timeout.md) - Why the chokepoint is a driver wrapper, not 124 call-site edits

## Related Skills

- **[skuel-search-architecture](../skuel-search-architecture/SKILL.md)** - Unified search using Cypher patterns
- **[python](../python/SKILL.md)** - Python services executing Cypher queries

## Deep Dive Resources

**Architecture:**
- [Query Architecture](/docs/patterns/query_architecture.md) - Graph database architecture
- [RELATIONSHIPS_ARCHITECTURE.md](/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md) - Lateral relationship types, service API, Cypher patterns
- [ADR-037](/docs/decisions/ADR-037-lateral-relationships-visualization-phase5.md) - Lateral relationships visualization

**Patterns:**
- [query_architecture.md](/docs/patterns/query_architecture.md) - Query architecture patterns

**Code:**
- `/core/models/relationship_names.py` - RelationshipName enum (source of truth for all 169 relationship types)

---

## Foundation

This skill has no prerequisites. It is a foundational pattern.

## See Also

- `/docs/patterns/query_architecture.md` - Query architecture documentation
- `/docs/patterns/query_architecture.md` - Database architecture
- `/core/models/relationship_names.py` - RelationshipName enum (source of truth)
