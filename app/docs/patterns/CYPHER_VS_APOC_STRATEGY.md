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

An `apoc.periodic.iterate` call from `core/`, `adapters/inbound/`, or `ui/` therefore
fails twice: the linter rejects it before commit, and Neo4j refuses the procedure at
runtime.

> **⚠ The persistence layer itself is not linted for APOC.** SKUEL001's scope stops at
> the boundary, so a new `apoc.meta.*` call inside `adapters/persistence/` passes every
> automated gate — only the server allowlist would still permit it, and only for that one
> namespace. Nothing in the product calls APOC today, so treat any such call as a
> deliberate architectural reversal requiring review, not as a permitted default.
> This is the one APOC gap with no automated control; `CODE_REVIEW_CHECKLIST.md` carries
> it as a manual check.

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

### APOC — the product runtime calls none of it

**No application code path invokes an APOC procedure.** Not in `core/`, not in
`adapters/`, not at boot. `apoc.meta.*` is allowlisted at the server, but nothing in
the product calls it — the only live `apoc.meta.*` callers are the integration canary
and the hand-run migration archive.

| Use | Procedure | Where | Status |
|-----|-----------|-------|--------|
| One-shot data migrations | `apoc.periodic.iterate`, `apoc.create.*`, `apoc.util.sha256` | `scripts/migrations/*.cypher` (3 files) | **The only live use.** A deliberate archive — run once by hand, excluded from both Cypher linters |
| Plugin canary | `apoc.meta.*`, `apoc.periodic.iterate`, `apoc.convert.fromJsonMap`, `apoc.version()` | `tests/integration/test_apoc_canary.py` | Test-only, under a permissive fixture — see Operational Hygiene §2 |
| Schema introspection | `apoc.meta.*` | — | Allowlisted at the server, **not called by any product code** |

**Migrations are not a precedent for new code.** They are historical records of
already-executed schema changes; both Cypher linters exclude that directory by design.

> **There is no boot-time APOC probe**, despite appearances.
> `Neo4jSchemaService._check_apoc_available()` (`schema_service.py:378`) contains the
> only `apoc.version()` call in application code and is **unreachable twice over**: it
> has no callers anywhere in the tree, and it early-returns on `if not self.use_apoc`
> before reaching the query — while both instantiation sites
> (`neo4j_adapter.py:128`, `services_bootstrap/_learning_services.py:95`) take the
> `use_apoc: bool = False` default. Do not cite it as a version signal; the canary is
> the only thing that actually probes the plugin.

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

`SemanticRelationshipType` members compile to edge types via `to_neo4j_name()` — but
**that mapping is many-to-one, not an identity**. The precise namespaced predicate is
*not* the edge type:

```python
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType

rel_pattern = "|".join(
    st.to_neo4j_name()
    for st in [
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.BUILDS_MENTAL_MODEL,
    ]
)
# → "REQUIRES_KNOWLEDGE|RELATED_TO"      (executed — NOT the member names)
```

`RelationshipName` owns the edge type — the coarse bucket — and
`REQUIRES_THEORETICAL_UNDERSTANDING` is **not** a `RelationshipName` member, so writing
it as an edge type produces a relationship outside the graph contract that ordinary
semantic queries never traverse (and SKUEL030 flags it in persistence Cypher). The
collapse is made non-lossy by the `semantic_type` **property**, which is part of the
MERGE identity so two predicates sharing one bucket stay distinct.

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

Query producers return `tuple[str, dict[str, ...]]` — the query and its parameters,
never an interpolated string. Relationship *types* are validated against the enum before
they reach the pattern (SKUEL030), which is why they may be inlined while every value
stays a `$parameter`.

**The 54 are not uniform — 8 do not fit that shape.** Check the signature before
unpacking:

| Function | Returns | Why it differs |
|----------|---------|----------------|
| `build_relationship_filter_fragments` | `list[str]` | Emits WHERE fragments the caller AND-joins — not a query |
| `build_search_visibility_clause` | `tuple[str, dict[str, str]] \| None` | **Returns `None`** when no scoping applies; `query, params = ...` raises `TypeError` |
| `build_publication_clause` | `tuple[str, dict[str, str]]` | Clause builder — composes *into* a query |
| `build_knowledge_read_clause` | `tuple[str, Neo4jProperties]` | Clause builder |
| the 4 `build_batch_*` in `relationship_queries.py` | `tuple[str, dict[str, Any]]` | Heterogeneous batch payloads |

The remaining 46 return `tuple[str, dict[str, Neo4jValue]]`. The clause and fragment
builders are *composition helpers*: they produce a piece of a query, and calling one
where a full query is expected yields Cypher that does not parse.

**Do not hand-author the write.** Relationship writes go through `build_semantic_merge()`,
which resolves the edge type, validates it as a safe identifier, and puts `semantic_type`
in the MERGE pattern so the write is idempotent *per predicate*:

```python
from adapters.persistence.neo4j.query import build_semantic_merge
from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata, SemanticRelationshipType, SemanticTriple,
)

query, params = build_semantic_merge(
    SemanticTriple(
        subject="task.learn_async",
        predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        object="ku.python_basics",
        metadata=RelationshipMetadata(confidence=0.95, source="tasks_service_explicit"),
    )
)
```

which emits (executed, verbatim):

```cypher
MERGE (s {uid: $subject})
MERGE (o {uid: $object})
MERGE (s)-[r:REQUIRES_KNOWLEDGE {semantic_type: $semantic_type}]->(o)
ON CREATE SET r = {confidence: $confidence, strength: $strength, created_at: $created_at, source: $source, semantic_type: $semantic_type}
ON MATCH SET r += {confidence: $confidence, strength: $strength, created_at: $created_at, source: $source, semantic_type: $semantic_type}
```

Note the edge type is `REQUIRES_KNOWLEDGE`, not the predicate name, and that
`semantic_type` appears **inside the MERGE pattern** — a hand-written
`MERGE (a)-[r:...]->(b)` that omits it silently merges two distinct predicates onto one
edge.

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

### 2. Canary suite — a plugin canary, **not** a lockdown test

`tests/integration/test_apoc_canary.py` runs against a Neo4j testcontainer and asserts
the plugin still answers after an image bump: `apoc.version()` agreeing with the server
line, `apoc.meta.graph()`, `apoc.meta.nodeTypeProperties()`, `apoc.periodic.iterate()`,
and `apoc.convert.fromJsonMap()`, plus companion classes covering semantic relationship
types and variable-length patterns.

```bash
uv run pytest tests/integration/test_apoc_canary.py -v
```

Run it before and after any Neo4j image bump.

> **⚠ It does not exercise the production security profile.**
> `tests/integration/conftest.py` sets `NEO4J_dbms_security_procedures_unrestricted`
> to `apoc.*` and **never sets the allowlist at all** — so the fixture is strictly more
> permissive than compose, and two of the canaries (`apoc.periodic.iterate`,
> `apoc.convert.fromJsonMap`) deliberately probe procedures production blocks. Two
> consequences: a green suite is **not** evidence that the compose allowlist is intact,
> and the suite would keep passing if that allowlist were misconfigured or dropped.
> Treat it as "is the plugin alive?", never as "is the lockdown on?" — the allowlist is
> enforced by configuration only, and nothing currently tests it.

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
| Procedure allowlist | `apoc.meta.*` | `infrastructure/docker-compose.yml` | ⚠️ Config-only — **untested** |
| Boundary enforcement | SKUEL001 / SKUEL021 | `scripts/lint_skuel.py` | ✅ Enforced + tested |
| Canary tests | Plugin liveness only | `tests/integration/test_apoc_canary.py` | ✅ Shipped (permissive fixture) |
| Batch writes via APOC | Rejected | — | ❌ Not adopted |

**See also:** [query_architecture.md](./query_architecture.md) for the three query
layers and the full `build_*` inventory.
