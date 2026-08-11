---
title: 'Pure Cypher vs APOC: Strategic Decision Guide'
updated: '2026-08-11'
category: patterns
related_skills:
- neo4j-cypher-patterns
related_docs: []
---
---
title: Pure Cypher vs APOC: Strategic Decision Guide
updated: 2026-08-11
status: current
category: patterns
tags: [apoc, cypher, patterns, strategy]
related: []
---

# Pure Cypher vs APOC: Strategic Decision Guide

**Principle**: *"Pure Cypher for core graph logic. APOC is not part of the product runtime."*

---
## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)

---

## Naming — there are no `SemanticCypherBuilder`, `ApocQueryBuilder`, or `SemanticGraphBuilder` classes

<a id="no-builder-classes"></a>
> This document previously described the query layer as three classes:
> `SemanticCypherBuilder`, `ApocQueryBuilder`, and `SemanticGraphBuilder`, and listed
> the first two as "✅ Implemented". **None of the three was ever built.** They appear
> in no `.py` file in the tree, and `git log --all -S"class SemanticCypherBuilder"`
> finds the string only in this document. The names are not importable —
> `from adapters.persistence.neo4j.query import SemanticCypherBuilder` raises
> `ImportError`.
>
> What shipped instead is a **package of module-level functions**:
> `adapters/persistence/neo4j/query/cypher/` — 54 `build_*` functions across
> `crud_queries.py` (16), `domain_queries.py` (13), `intelligence_queries.py` (9),
> `semantic_queries.py` (8), `relationship_queries.py` (7), and
> `relationship_filter_fragments.py` (1). Import and call them directly; there is no
> object to construct.
>
> This is the same defect class as the `CypherGenerator` fiction — see
> [query_architecture.md § Naming](./query_architecture.md#no-cyphergenerator-class).
> The APOC half of the fiction is worse than cosmetic: `ApocQueryBuilder` was
> presented as the *sanctioned* home for `apoc.periodic.iterate` batch writes, but
> SKUEL001 makes APOC unsuppressable above the persistence boundary and the compose
> allowlist blocks every namespace except `apoc.meta.*` at the server. A reviewer
> following the old text would have approved code the linter and the database both reject.

---

## The Decision, As Enforced

The "hybrid strategy" this document once recommended — wrap APOC behind an adapter class
so it can be swapped for pure Cypher later — **was not adopted**. The codebase went
further: APOC was removed from the product runtime entirely, and two linter rules now
hold the line.

| Guard | Rule | Scope | Severity |
|-------|------|-------|----------|
| No APOC above the boundary | **SKUEL001** | `core/`, `adapters/inbound/`, `ui/` — whole-namespace match, `apoc.meta.*` included | CRITICAL, **unsuppressable** |
| No raw Cypher above the boundary | **SKUEL021** | same three trees; all Cypher lives in `adapters/persistence/neo4j/` | ERROR |

At the server, the allowlist is narrower still — `infrastructure/docker-compose.yml`
pins **both** knobs to the one namespace we use:

```yaml
NEO4J_dbms_security_procedures_unrestricted: "apoc.meta.*"
NEO4J_dbms_security_procedures_allowlist: "apoc.meta.*"
```

An `apoc.periodic.iterate` call from application code therefore fails twice: the linter
rejects it before commit, and Neo4j refuses the procedure at runtime.

---

## Why Pure Cypher Wins for Core Graph Logic

1. **Query planner** — cost-based optimization over MATCH/MERGE patterns
2. **Index usage** — `uid` lookups hit the index automatically
3. **Query cache** — parameterized queries reuse execution plans
4. **Statistics** — pattern matching benefits from cardinality estimates
5. **Inline filtering** — `WHERE r.confidence > 0.8` composes with the traversal

APOC procedures bypass the planner, so even where they are available they forfeit 1–4.

---

## Decision Matrix: When to Use What

### Pure Cypher (everything in the product runtime)

| Operation | Pattern | Where it lives |
|-----------|---------|----------------|
| Single relationship | `MATCH (a)-[r:TYPE]->(b)` | `query/cypher/semantic_queries.py` |
| Fixed-depth traversal | `MATCH (a)-[r:TYPE*1..3]->(b)` | `query/cypher/semantic_queries.py` |
| Prerequisite chains | variable-length + distance | `build_prerequisite_chain()` |
| Confidence filtering | `WHERE r.confidence >= $min_confidence` | `query/confidence_filter.py` |
| MERGE operations | `MERGE (a)-[r:TYPE]->(b)` | `UniversalNeo4jBackend` |
| Property updates | `SET r += $props` | `UniversalNeo4jBackend` |
| CRUD / search / count | model introspection | `query/cypher/crud_queries.py` |
| Fluent composition | method chaining | `UnifiedQueryBuilder` |

### APOC — two carve-outs, neither in the request path

| Use | Procedure | Where | Why it's allowed |
|-----|-----------|-------|------------------|
| Schema introspection | `apoc.meta.*` | `adapters/persistence/neo4j/` | The one allowlisted namespace |
| Version probe | `apoc.version()` | `schema_service.py` | Reports plugin version at boot |
| One-shot data migrations | `apoc.periodic.iterate`, `apoc.create.*`, `apoc.util.sha256` | `scripts/migrations/*.cypher` | A deliberate archive — run once by hand, excluded from the linters |

**Migrations are not a precedent for new code.** They are historical records of
already-executed schema changes; both Cypher linters exclude that directory by design.

### Never APOC

| Operation | Use instead |
|-----------|-------------|
| Simple MATCH | `MATCH (n)-[r]->(m)` |
| Simple MERGE | `MERGE (a)-[r:TYPE]->(b)` |
| Property updates | `SET n.prop = $value` |
| Bounded traversal | `MATCH path = (a)-[*1..3]->(b)` |
| Subgraph extraction | variable-length patterns + `collect()` |

---

## Semantic Types Compile to Pure Cypher

`SemanticRelationshipType` members carry their own Neo4j spelling, so type-safe enums
become relationship patterns with no string handling at the call site:

```python
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType

rel_pattern = "|".join(
    st.to_neo4j_name()
    for st in [
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL,
    ]
)
# → "REQUIRES_THEORETICAL_UNDERSTANDING|BUILDS_MENTAL_MODEL"
```

In practice you do not assemble the pattern yourself — the `build_*` functions take the
enum members and emit both the query and its parameters. Each call below was executed
against the current tree:

```python
from adapters.persistence.neo4j.query import (
    build_prerequisite_chain,
    build_semantic_context,
)
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType

# Neighbourhood context around a node
query, params = build_semantic_context(
    node_uid="ku.python_basics",
    semantic_types=[
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL,
    ],
    depth=2,
)
# params → {"uid", "semantic_type_values", "min_confidence"}

# Transitive prerequisites, confidence-gated
query, params = build_prerequisite_chain(
    node_uid="ku.async_python",
    semantic_types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING],
    depth=3,
    min_confidence=0.7,
)
# params → {"uid", "semantic_type_values", "min_confidence", "min_strength"}
```

Every function returns `tuple[str, dict[str, Neo4jValue]]` — the query and its
parameters, never an interpolated string. Relationship *types* are validated against the
enum before they reach the pattern (SKUEL030), which is why they may be inlined while
every value stays a `$parameter`.

Relationship writes are `MERGE`, and therefore idempotent:

```cypher
MATCH (a {uid: $from_uid})
MATCH (b {uid: $to_uid})
MERGE (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
SET r += $metadata
RETURN r
```

---

## Operational Hygiene

### 1. Version pinning — server and driver are decoupled

| Component | Pin | Location |
|-----------|-----|----------|
| Neo4j server | `neo4j:2026.06.0` (calendar line, exact — never a floating tag) | `infrastructure/docker-compose.yml` |
| Python driver | `neo4j==5.26.0` (deliberate cap) | `app/pyproject.toml` |
| APOC plugin | `NEO4J_PLUGINS: '["apoc"]'` — version tracks the server image | `infrastructure/docker-compose.yml` |

The driver pin is **intentional and decoupled** from the server version (Bolt is
forward-compatible). Neither is a routine Renovate bump. See ADR-067 §3/§3a.

### 2. Canary suite — already in place

`tests/integration/test_apoc_canary.py` runs against a Neo4j testcontainer and asserts
the plugin still answers: `apoc.version()` agreeing with the server line,
`apoc.meta.graph()`, `apoc.meta.nodeTypeProperties()`, plus companion classes covering
semantic relationship types and variable-length patterns.

```bash
uv run pytest tests/integration/test_apoc_canary.py -v
```

Run it before and after any Neo4j image bump.

### 3. Procedure lockdown lives in compose, not `apoc.conf`

There is **no `apoc.conf` file** in this repo. The allowlist is set through
`NEO4J_*` environment variables on the `neo4j` service (shown above), which is stricter
than the older `unrestricted`-only advice: `allowlist` blocks the procedure outright
rather than merely removing its elevated privileges.

### 4. No triggers for business logic

```python
# ❌ WRONG - hidden reactive side effect
"CALL apoc.trigger.add('auto_timestamps', 'MATCH (n) SET n.updated_at = timestamp()', {})"

# ✅ CORRECT - explicit write in the backend
"MATCH (n:Task {uid: $uid}) SET n += $data RETURN n"
```

Triggers are invisible to review, untestable in isolation, and would sit outside the
allowlisted namespace anyway.

---

## Status

| Component | Strategy | Location | Status |
|-----------|----------|----------|--------|
| Semantic relationships | Pure Cypher | `query/cypher/semantic_queries.py` | ✅ Shipped |
| CRUD / search | Pure Cypher | `query/cypher/crud_queries.py` | ✅ Shipped |
| Writes / MERGE | Pure Cypher | `UniversalNeo4jBackend` | ✅ Shipped |
| APOC in product runtime | Removed | — | ✅ None remaining |
| Procedure allowlist | `apoc.meta.*` | `infrastructure/docker-compose.yml` | ✅ Enforced |
| Boundary enforcement | SKUEL001 / SKUEL021 | `scripts/lint_skuel.py` | ✅ Enforced |
| Canary tests | Testcontainer suite | `tests/integration/test_apoc_canary.py` | ✅ Shipped |
| Batch writes via APOC | Rejected | — | ❌ Not adopted |

**See also:** [query_architecture.md](./query_architecture.md) for the three query
layers and the full `build_*` inventory.
