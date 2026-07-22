---
title: "Neo4j Per-Query Server-Side Timeout"
updated: 2026-05-28
status: current
category: patterns
tags: [neo4j, persistence, performance, timeout, adapters]
related: [ADR-044, ADR-064]
---

# Neo4j Per-Query Server-Side Timeout

**Core Principle:** "Every Neo4j query has a server-side ceiling — set once at compose, override per operation."

## What it gives you

Every `session.run(...)`, `driver.execute_query(...)`, and `session.begin_transaction(...)` that flows through the app-wide shared driver carries a server-side `Query(timeout=)` / `begin_transaction(timeout=)` ceiling. A runaway Cypher is **aborted by the Neo4j server**, not by the client giving up.

- **Default:** `120s` (`DatabaseConfig.transaction_timeout`, env `NEO4J_TRANSACTION_TIMEOUT`, `0`=unbounded).
- **Bulk ingestion:** `600s` (baked into `BulkUpsertBackend.upsert_nodes` / `create_relationships` / `upsert_with_relationships`).
- **Startup DDL:** untimed — `Neo4jSchemaManager` is constructed from the raw (unwrapped) driver in compose; vector / full-text / domain index creation on a large `:Entity` label can exceed 120s legitimately.
- **Migration / one-off scripts** that build their own `Neo4jConnection` directly bypass the wrapper for the same reason.

## How the chokepoint works

There is no global "default tx timeout" knob on the neo4j 5.x driver, and the ~124 `session.run` sites across `adapters/persistence/neo4j/` each open their own `self.driver.session()`. The wrapper creates the chokepoint that doesn't exist by proxying the **one** shared `AsyncDriver` at the composition root.

```text
services_bootstrap/compose.py:117   (right after driver validation)
    raw_driver = driver
    driver = TimedDriver(raw_driver, default_timeout=cfg.transaction_timeout or None)
    │
    ├── Neo4jQueryExecutor(driver)          # MEGA-QUERY + analytics
    ├── create_all_backends(driver, ...)    # all 11 UniversalNeo4jBackend mixin bases
    ├── make_unified_ingestion_service(driver=driver, ...)  # ingestion
    └── Neo4jSchemaManager(raw_driver)      # startup DDL: untimed by design
```

`TimedDriver.session()` returns a `TimedSession` that:

- wraps `str` queries in `neo4j.Query(text, timeout=resolved)` on `.run()`;
- respects a caller-supplied `Query` (its own `timeout` wins);
- injects `timeout=resolved` into `.begin_transaction()` when the caller passed none (so `CypherExecutor` batch ingestion via `tx.run(...)` inherits the limit);
- delegates everything else (`close`, `last_bookmarks`, `cancel`, etc.) via `__getattr__`.

The `LiteralString` pyright friction is contained in a single localized `# pyright: ignore[reportArgumentType]` inside `_as_timed_query`, mirroring the precedent at `ingestion_write_backend.py:54`.

## Override mechanism — `contextvars`

```python
from adapters.persistence.neo4j.timed_driver import (
    neo4j_query_timeout,
    unbounded_neo4j_query_timeout,
)

# Bound the enclosed block to N seconds:
with neo4j_query_timeout(600.0):
    async with self._driver.session() as session:
        result = await session.run(very_long_query, params)

# Remove the bound entirely (escape hatch — admin maintenance, etc.):
with unbounded_neo4j_query_timeout():
    ...
```

Semantics:

- The override is a `ContextVar` with a `_UNSET` sentinel that distinguishes "no override in scope" (use the default) from "explicitly unbounded" (`None` → no server timeout).
- Propagates across `await` and `asyncio.gather` within the current task.
- A task created with `asyncio.create_task` *inside* the `with` block inherits the value at creation time. **Resetting on `with` exit does NOT reach into a child task that is still running** — keep the awaited work inside the block.
- Calling order: per-op override > driver default > 120s.

## When (and when NOT) to wrap

| Scenario | Wrap? | Why |
|---|---|---|
| Standard CRUD, list queries, single-entity reads | ❌ No | 120s default is generous (typical query: ms to seconds). |
| MEGA-QUERY (`user_context_queries.execute_mega_query`) | ❌ No | Typically 5–30s, well under 120s — a true runaway is still caught. |
| Heavy analytics (`cross_domain_backend.find_knowledge_hubs`, `analyze_prerequisite_depth`) | ❌ No | Same — default headroom is enough; if a tenant's graph legitimately needs longer, wrap that one call site. |
| Bulk ingestion (`upsert_nodes` / `create_relationships` / `upsert_with_relationships`) | ✅ Already wrapped (600s) | Large MD/YAML imports legitimately exceed 120s; the wrap is in `BulkUpsertBackend`. |
| Constraint / index creation on a large label | ✅ Use `unbounded_neo4j_query_timeout()` | DDL workloads can run minutes on a populated graph; `Neo4jSchemaManager` already gets the raw driver at compose. |
| One-off admin maintenance through the wrapped driver | Consider `unbounded_neo4j_query_timeout()` | Only when you're certain it's intentional and bounded by another mechanism. |

## Configuration

| Env var | Default | Maps to | Effect |
|---|---|---|---|
| `NEO4J_TRANSACTION_TIMEOUT` | `120` | `DatabaseConfig.transaction_timeout` | Per-query server-side ceiling, in seconds. `0` is treated as unbounded (compose maps `0` → `None`). |

The other `NEO4J_*` knobs (`NEO4J_CONNECTION_TIMEOUT`, `NEO4J_CONNECTION_ACQUISITION_TIMEOUT`, `NEO4J_MAX_TRANSACTION_RETRY_TIME`, pool size, lifetime) bound *driver-level* operations (connection establishment, pool acquisition, managed-tx retry) — NOT a single query's execution time. Both layers are wired and complementary.

## Relationship to server-side `db.transaction.timeout`

The Neo4j server itself has a global default tx timeout (`db.transaction.timeout`, set to `600s` in `docs/deployment/DO_MIGRATION_GUIDE.md`). That setting is the **fallback** for transactions that arrive without a per-tx timeout. With this app, every query now carries a client-supplied `timeout=`, so the server config is effectively superseded by ours — keep the server bound as a defense-in-depth ceiling, but the day-to-day limit is the value in `.env`.

## Where to look

- **Implementation:** `adapters/persistence/neo4j/timed_driver.py` (~210 lines: `TimedDriver`, `TimedSession`, `neo4j_query_timeout`, `unbounded_neo4j_query_timeout`, `_as_timed_query`).
- **Wiring:** `services_bootstrap/compose.py:117` (the one wrap site + the `Neo4jSchemaManager(raw_driver)` carve-out).
- **Config:** `core/config/unified_config.py` (`DatabaseConfig.transaction_timeout`).
- **Ingestion wrap site:** `adapters/persistence/neo4j/bulk_upsert_backend.py` (`with neo4j_query_timeout(600.0):`).
- **Tests:** `tests/unit/test_timed_driver.py` (12 tests — fake-session captures the `Query` object), `tests/integration/test_timed_driver.py` (5 tests against `neo4j:2026.06.0` testcontainer; busy Cartesian-product Cypher — no APOC, per SKUEL001).

## See also

- [ADR-044 — Neo4j as Committed Architectural Choice](../decisions/ADR-044-neo4j-committed-architectural-choice.md)
- [ADR-064 — Neo4j Per-Query Server-Side Timeout](../decisions/ADR-064-neo4j-per-query-timeout.md)
- [`docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`](MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md) — the backend layer the wrapper sits above.
- [`docs/deployment/DO_MIGRATION_GUIDE.md`](../deployment/DO_MIGRATION_GUIDE.md) — server-side `db.transaction.timeout` configuration.
- [`@neo4j-cypher-patterns` skill — Best Practice 6](../../.claude/skills/neo4j-cypher-patterns/SKILL.md#6-per-query-server-side-timeout-timeddriver) — actionable how-to for query authors.
- [ADR-080 — AuraDB Three-Horizon Strategy](../decisions/ADR-080-auradb-three-horizon-strategy.md) — the **startup** connectivity sibling of this per-query ceiling. The timeout bounds a query that runs too long; `connect_with_retry` / `probe_connectivity` (Horizon 0, `neo4j_connection.py`) bound a server that *isn't answering yet* (a paused/waking AuraDB Free instance). Distinct concerns, same driver seam.
