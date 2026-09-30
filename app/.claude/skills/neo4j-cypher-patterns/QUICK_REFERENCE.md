# Neo4J Cypher Patterns - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Cypher Shapes

### Ownership-scoped fetch (multi-tenant security)

```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task {uid: $task_uid})
RETURN t
```

**When to use**: Any user-owned read — missing the OWNS hop is a security bug (return not-found, not forbidden).

### Entity fetch with label guard (G13 shadow rule)

```cypher
// Entity-only paths — bind the universal base label
MATCH (n:Entity {uid: $uid})

// Mixed-label paths (endpoints may be User/Group/…) — exclude the :Content shadow
MATCH (n {uid: $uid}) WHERE NOT n:Content
```

**When to use**: Always. An unlabeled `MATCH ({uid: $uid})` binds BOTH the entity and its `:Content` chunk-store shadow node.

### Temporal comparison on string-stored fields

```cypher
// datetime-typed field (DTO .isoformat() → STRING): coerce the stored side
WHERE datetime(n.created_at) >= datetime($window_start)

// date field (due_date, event_date, ...): SKUEL's standard guard takes the
// YYYY-MM-DD prefix so a *mis-stored* datetime string ("2026-06-17T09:00")
// doesn't make date() ERROR and blank the whole range. "Today" is the
// $today parameter — today in the user's zone, never the server's UTC date()
WHERE date(left(toString(n.due_date), 10)) < date($today)

// genuinely-datetime field compared against a date: parse-then-extract
// (date() ERRORS on a datetime string; date(datetime(...)) or left(...,10) both fix it)
WHERE date(datetime(h.last_completed)) < date($today)
```

**When to use**: Whenever the writer was a DTO (`.isoformat()`). `string >= datetime()` evaluates to `null` — rows silently drop.

---

## Key Infrastructure

### `TimedDriver` — per-query server-side timeout (ADR-064)

Default 120s ceiling (`NEO4J_TRANSACTION_TIMEOUT`). Override per call site:

```python
from adapters.persistence.neo4j.timed_driver import neo4j_query_timeout

with neo4j_query_timeout(300.0):
    ...  # the full await chain must be inside the block (ContextVar read at call time)
```

### `RelationshipName` enum (SKUEL013)

```python
from core.models.relationship_names import RelationshipName

query = f"MATCH (a)-[:{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(b)"
# Property maps in f-strings need escaped braces: {{uid: $uid}}
```

### Identifier validation (labels/rel-types can't be parameterized)

```python
from adapters.persistence.neo4j.query.cypher._helpers import validate_label, validate_identifier
validate_label(label)        # known NeoLabel value or ValueError
validate_identifier(field)   # safe identifier or ValueError
```

---

## Index Inventory (bootstrap: `Neo4jSchemaManager`)

| Index type | Count | Tier | Notes |
|-----------|-------|------|-------|
| Domain (uid constraint / user_uid / status / date / composite) | see the method's docstring | Always | `sync_domain_indexes()` |
| Full-text (Lucene) | one per label in `FULLTEXT_INDEX_DEFINITIONS` | Always | Read by the hybrid rung (Ku/PS/LP, FULL tier, `advanced_search` / `POST /api/search/unified` only) — every other text search is case-insensitive `CONTAINS` |
| Auth / conversation | — | Always | `sync_auth_indexes()` (sessions, rate limiting, email uniqueness), `sync_conversation_indexes()` |
| Vector (`EmbeddingGeometry.DIMENSION` dims, cosine) | `len(EmbeddingGeometry.INDEX_LABELS)` | FULL only | `EmbeddingGeometry.INDEX_LABELS` (`core/constants.py`) is the list — one constant read by both the bootstrap sync (every label at boot) and `scripts/create_vector_indexes.py`; names are `{label.lower()}_embedding_idx`. It holds what exists, not a chosen set: the label-generic semantic/learning rung can ask for a domain outside it and degrades silently (see `deferred-work.md` § Label-Generic Vector Rung) |

```cypher
CALL db.index.fulltext.queryNodes('task_fulltext_idx', 'urgent deadline') YIELD node, score
CALL db.index.vector.queryNodes('entity_embedding_idx', 10, $embedding) YIELD node, score
```

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| Unlabeled `MATCH ({uid: ...})` doubles rows | Label guard: `:Entity` or `WHERE NOT n:Content` (G13) |
| `string >= datetime()` → null, rows vanish | Coerce stored side: `datetime(n.field) >= datetime($w)` |
| `date()` on a datetime string → error | `date(datetime(field))` |
| Per-domain ownership edges (`HAS_TASK`-style) | There is one ownership edge: `(u:User)-[:OWNS]->(e)` (ADR-086) |
| `:Curriculum` label in MATCH | No such label — use `:Ku`/`:PathStep`/`:LearningPath`/`:Exercise` or `:Entity` + `entity_type` |
| Status literals like `'pending'`/`'on_track'` | Not `EntityStatus` values — bind `$statuses` from the enum (SKUEL014) |
| APOC anywhere above the persistence boundary | SKUEL001 (unsuppressable) matches the whole `apoc.*` namespace in `core/`, `adapters/inbound/`, `ui/`; the server allowlist is `apoc.meta.*`, and no product code calls even that |
| Inline Cypher in a service | SKUEL021 — Cypher lives in `adapters/persistence/neo4j/` backends |
| A colon-spelled entity uid (`ps:x:y`) | Not a UID spelling — authored = stored in dot form (`ps.x.y`); ingestion rejects the colon form. Colons mark internal machine ids only (`ue:daily:…`) |
| Cartesian product from stacked OPTIONAL MATCH | `collect(DISTINCT ...)` per branch before the next MATCH |
| `backend.update({"status": ...})` | ADR-087 — a status-bearing write goes through `update_with_status_guard(uid, updates, guard)`; the verdict comes from the prior the statement returns |
| A label or edge name Neo4j silently matches zero rows on | SKUEL030 / CYP011 — every label / edge in persistence Cypher is a `NeoLabel` / `RelationshipName` member |

---

## Where Does Cypher Live?

| Cypher | Location |
|--------|----------|
| Generic CRUD | `UniversalNeo4jBackend` — the `_*Mixin` files its class bases name |
| Domain-specific | the backends in `adapters/persistence/neo4j/backends/` (cluster files; PATTERNS.md § Where Does Cypher Live) |
| Cross-domain aggregation | `adapters/persistence/neo4j/user_context_queries.py` (the MEGA-QUERY's `RICH_CONTEXT_STATEMENTS`), `CrossDomainBackend` — no Cypher in `core/` (SKUEL021) |
| Vector search | `VectorSearchBackend` (FULL tier) |
| DDL | `neo4j_schema_manager.py` (startup, idempotent `IF NOT EXISTS`) |

---

**See Also**: [SKILL.md](SKILL.md) for detailed explanations
**See Also**: [PATTERNS.md](PATTERNS.md) for design patterns (MERGE+SET, UNWIND batching, WHERE guards, temporal coercion)
**See Also**: [examples.md](examples.md) for complete per-domain examples
**See Also**: [reference.md](reference.md) for the relationship catalog
