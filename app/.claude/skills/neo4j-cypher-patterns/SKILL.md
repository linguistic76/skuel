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

// Principles guidance
(goal:Goal)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
(choice:Choice)-[:ALIGNED_WITH_PRINCIPLE]->(principle:Principle)

// Life path (everything flows toward the life path)
// The ULTIMATE_PATH edge IS the designation. The node is NOT mutated and gets
// no :LifePath label — a designated path stays an ordinary LearningPath, so
// {entity_type: 'life_path'} matches ZERO rows. Traverse the edge.
(user:User)-[:ULTIMATE_PATH]->(lp:Entity)
(entity:Entity)-[:SERVES_LIFE_PATH]->(lp:Entity)
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

SKUEL has one query builder plus a package of Cypher functions (SKUEL001: no APOC in domain services):

| Builder | Location | Use Case |
|---------|----------|----------|
| **UnifiedQueryBuilder** | `adapters/persistence/neo4j/query/` | Generic CRUD reads (used by backends via `UniversalNeo4jBackend.query_builder`) |
| **`build_*` functions** (module-level, no class) | `adapters/persistence/neo4j/query/cypher/` | Pure Cypher, semantic traversal |

> The sibling `query_builders/` package (`QueryBuilder` + optimizer, template registry,
> validator, faceted builder, graph-context builder) was **deleted 2026-08-17** — built on
> every boot, zero production invocations since 2026-05-12. There is no template registry
> and no runtime query optimizer/validator; don't reach for one.

**SKUEL001 linter rule:** APOC is scoped to `apoc.meta.*` (schema introspection only). Domain services author neither APOC nor Cypher — they call a named backend method, and the backend composes pure Cypher from the `build_*` functions above.

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
| **Vector indexes** | `sync_vector_indexes()` | FULL tier only | 1024-dim cosine — bootstrap creates Entity, ContentChunk, ReferenceChunk, Ku, PathStep, LearningPath; Goal + Task per-label indexes via `scripts/create_vector_indexes.py` (8 total live) |

> **Server side:** the Java Vector API (SIMD) must be enabled for these to run optimally —
> `NEO4J_server_jvm_additional=--add-modules jdk.incubator.vector` in `infrastructure/docker-compose.yml`.
> See [NEO4J_SERVER_TUNING.md](../../../docs/patterns/NEO4J_SERVER_TUNING.md).

Full-text indexes are the **Cypher-first search foundation** — created in both tiers, no embeddings needed. Their one production reader is the SearchRouter hybrid rung (Ku/PathStep/LearningPath, FULL tier, `advanced_search`/`/api/search/unified` only); every other text search — including the `/search` page — runs `CONTAINS`, and that `CONTAINS` is **case-INSENSITIVE** (both predicates lower-case each side: `faceted_search_raw` and `build_text_search_query`). Fulltext therefore buys relevance ranking and vector recall, not case-insensitivity. Two measured limits (Neo4j 2026.06.0): the shipped indexes use the default `standard-no-stop-words` analyzer, so they do **not stem** (`run` misses "Running") — and Lucene matches whole tokens, so `photosyn` misses "Photosynthesis" where `CONTAINS` finds it. Keep a `CONTAINS` fallback on any fulltext-first path. Derive index names from `NeoLabel.fulltext_index_name()`, never flat `label.lower()` (`PathStep` → `path_step_fulltext_idx`):

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

**Note:** The OWNS relationship is THE universal ownership edge (ADR-086). The former per-domain variants (HAS_TASK, HAS_GOAL, etc.) were paper-only and were deleted from RelationshipName — always use OWNS. Events attendance is the separate consent-carrying ATTENDS edge, not ownership.

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

#### Sibling at the driver seam — startup connectivity resilience (`connect_with_retry`)

The per-query timeout bounds a query that *runs too long*. The complementary startup concern is a
server that *isn't answering yet* — an AuraDB Free instance auto-pauses on inactivity and takes a
few seconds to resume. `connect_with_retry()` (`neo4j_connection.py`, ADR-080 Horizon 0) wraps the
startup connectivity probe in bounded exponential backoff, catching `NEO4J_EXCEPTIONS`:

```python
# Single chokepoint: Neo4jAdapter.connect() awaits this, so every startup path
# (app bootstrap + the one-shot ./dev scripts) inherits waking-instance tolerance.
await connect_with_retry(
    connection,
    max_attempts=Neo4jConnectRetry.MAX_ATTEMPTS,          # core/constants.py — 6
    base_delay_seconds=Neo4jConnectRetry.BASE_DELAY_SECONDS,   # 1.0s
    max_delay_seconds=Neo4jConnectRetry.MAX_DELAY_SECONDS,     # 30.0s cap (~31s total)
)
```

`probe_connectivity()` runs `RETURN 1` — a stronger check than the driver's routing-only
`verify_connectivity()`, because it confirms the database is actually **resumed and answering**,
not merely routable (which is what matters for a paused instance waking up). After the bound it
raises one actionable `RuntimeError`, never a bare `ServiceUnavailable` stacktrace.

This is **startup-only**. Deep mid-request reconnect / circuit-breaker across the ~124
`session.run` sites is deliberately deferred (ADR-080 "When to Revisit"); the natural home if it
is ever built is this same driver/executor seam (a thin wrapper), **not** 124 call-site edits —
the same "one chokepoint, not N edits" reasoning behind the `TimedDriver` above.

### 7. Schema-Change Monitoring (opt-in)

`SchemaChangeDetector` (`core/services/schema_change_detector.py`) fingerprints the live Neo4j schema (labels, indexes, constraints, relationship types) and reports drift — classified changes, breaking-change flags, and migration history.

Its former `AdaptiveOptimizationHandler` (auto-registered, cleared the adapter's `_index_aware_builder` / `_enhanced_templates` caches on drift) was deleted 2026-08-17 with the `query_builders/` stack whose caches were its only job. **The detector's value is now drift detection and logging**, not cache invalidation — there are no query-optimization caches left to invalidate.

It is exposed as an **on-demand** capability on the adapter — `Neo4jAdapter.check_schema_changes()`, `initialize_schema_monitoring()`, `stop_schema_monitoring()` — and is wired into the composition root as an **opt-in background poll**:

```bash
# In .env — both default off / 900s
NEO4J_SCHEMA_MONITORING=true            # start the background poll at startup
NEO4J_SCHEMA_MONITORING_INTERVAL=900    # poll interval (seconds); must be ≥ 1
```

- **Off by default.** Gated by `config.database.schema_monitoring_enabled`, *not* by `INTELLIGENCE_TIER` — it's plain graph infrastructure (no API calls), so it can run in either tier. Keeping it off by default adds no always-on worker to CORE (the tier's guarantee is AI-scoped — the hourly `ProgressReportWorker` already runs there).
- **Where it's wired.** `services_bootstrap/compose.py` calls `initialize_schema_monitoring()` right after the startup DDL sync (so it baselines against the freshly-synced schema); `shutdown_skuel` calls `stop_schema_monitoring()`. The detector owns its own `asyncio` poll task, which lives on the single loop shared by bootstrap and `server.serve()`.
- **Non-fatal.** A failed start warns and continues — monitoring is observability, never a correctness gate.
- **Interval is validated at the env boundary** (`DatabaseConfig.from_env` rejects values < 1): a non-positive interval is truthy and would make `asyncio.sleep(<=0)` busy-spin Neo4j introspection.

**Rule:** Don't enable it where the schema is static after startup DDL (the common case) — it catches nothing at runtime and adds periodic introspection load. Enable it only where schema genuinely drifts mid-session.

### 8. Coerce string-stored temporals in comparisons

Date/datetime fields are stored as **ISO strings** (DTO `.isoformat()`), so comparing them directly to `date()`/`datetime()` yields `null` and silently drops rows. Wrap the stored side: `datetime(n.created_at) >= datetime($w)`. `datetime()` is universally safe (parses date and datetime strings, no-op on natives); `date()` **errors on a datetime string** → use `date(datetime(field))`. **The writer decides the type** — a hand-written Cypher writer that does `SET n.ts = datetime($iso)` stores a native `ZONED DATETIME`; the universal backend's `to_neo4j_node` mapper `.isoformat()`-serializes datetimes and stores a **string**. Two nodes in the same family can differ.

**Worked case — telemetry retention (ADR-080 H0), verified with `valueType()` on the live graph.**
`telemetry_retention_backend.py` splits its prune predicates by exactly this rule:

```cypher
-- Native ZONED DATETIME (writer wrapped datetime($iso)): AuthEvent.timestamp,
-- SearchEvent.created_at, VIEWED.last_viewed_at — compare directly.
MATCH (e:AuthEvent) WHERE e.timestamp < datetime() - duration({days: $days})

-- STRING (written through UniversalNeo4jBackend.to_neo4j_node → .isoformat()):
-- Interaction.created_at — parse first, or every row silently fails the filter.
MATCH (e:Interaction) WHERE datetime(e.created_at) < datetime() - duration({days: $days})
```

Same "telemetry node older than N days" intent, opposite predicate shape, because `:Interaction`
persists through the universal mapper while the others use hand-Cypher writers. Before writing any
temporal predicate, confirm the writer — or run `RETURN valueType(e.created_at)` on a live sample.
**See [PATTERNS.md](PATTERNS.md) Pattern 10 + Key Rules #17–18.**

### 9. Relationship reads/writes go through real, config-keyed methods

`UnifiedRelationshipService` has no `__getattr__` — calling a method it doesn't define is an `AttributeError`, and `get_related_uids(method_key, uid)` takes an **exact** `DomainRelationshipConfig` method-key that **fails closed** on a typo. Don't invent `get_<x>_<y>` methods or guess keys; never trust a mocked relationship service (it resolves any attribute). **See [/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md](/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md) § Phantom methods & keys.**

### 10. Batched age-based deletes — loop `WITH … LIMIT … DETACH DELETE` in Python

Canonical shape for pruning a large, unbounded set (telemetry retention, ADR-080 H0). A single
`MATCH … DETACH DELETE` over tens of thousands of nodes holds **one** transaction open — bad against
a per-tx-ceilinged managed instance (the `TimedDriver` 120s bound, or AuraDB's own limits). Delete in
bounded batches instead, each batch its **own** auto-committed transaction, looped from Python until a
batch removes fewer rows than the batch size (candidate set drained):

```cypher
-- One batch. The executor opens a fresh session per execute_query, so each call auto-commits.
MATCH (e:AuthEvent) WHERE e.timestamp < datetime() - duration({days: $days})
WITH e LIMIT $batch          -- WITH … LIMIT bounds the write set BEFORE the DELETE
DETACH DELETE e
RETURN count(e) AS cnt        -- loop again while cnt == $batch
```

```python
# telemetry_retention_backend.py::_run — the driving loop
while True:
    rows = (await self._executor.execute_query(delete_q, {"days": days, "batch": batch})).value or []
    deleted = int(rows[0]["cnt"]) if rows else 0
    total += deleted
    if deleted < batch:       # last (partial) batch drained the set
        break
```

Use `DELETE r` (not `DETACH DELETE`) when pruning **edges** (e.g. stale `:VIEWED`) so the endpoint
Ku/PathStep survives — delete the learner-state edge, never the content it points at.

**Why not `CALL { … } IN TRANSACTIONS`?** That subquery form *looks* like the built-in batcher, but it
**requires an implicit (auto-commit) transaction** and throws inside an explicit/managed tx — which is
how the executor and most call sites run. The Python delete-loop is the portable equivalent and keeps
each batch a normal auto-commit call. (Aside: on the `2026.x` calendar line the modern subquery syntax
is the variable-scope clause `CALL (e) { … }`; the legacy `CALL { WITH e … }` import form is deprecated
— SKUEL's own subqueries (bulk-upsert owner edge + relationship phase, the user-entry upsert, the
cross-domain evidence and recent-activity reads) all use the scope clause, and CYP009 scores both
spellings as a subquery.)

## Additional Resources

- [reference.md](reference.md) - Curated relationship type catalog (enum has 169 members)
- [examples.md](examples.md) - Full query examples for each domain
- [docs/patterns/NEO4J_QUERY_TIMEOUT.md](/docs/patterns/NEO4J_QUERY_TIMEOUT.md) - Per-query server-side timeout (TimedDriver, override mechanism)
- [ADR-064](/docs/decisions/ADR-064-neo4j-per-query-timeout.md) - Why the chokepoint is a driver wrapper, not 124 call-site edits
- [ADR-080](/docs/decisions/ADR-080-auradb-three-horizon-strategy.md) - AuraDB three-horizon strategy: telemetry retention (batched deletes, BP 10), startup connect-retry (BP 6), and the temporal-storage split (BP 8)

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
