---
title: "ADR-064: Neo4j Per-Query Server-Side Timeout via Driver Wrapper"
updated: 2026-05-28
status: current
category: decisions
tags: [adr, decisions, architecture, neo4j, persistence, performance, hexagonal]
related: [ADR-044, ADR-049, ADR-063]
---

# ADR-064: Neo4j Per-Query Server-Side Timeout via Driver Wrapper

**Status:** Accepted

**Date:** 2026-05-28

**Decision Type:** ✅ Pattern/Practice

**Related ADRs:**
- Extends: ADR-044 (Neo4j as Committed Architectural Choice) — applies the same "create the chokepoint at the adapter root" mindset that put all Cypher below `adapters/persistence/neo4j/`.
- Sibling: ADR-063 (LLM & Embedding SDKs Behind Ports) — same hexagonal-boundary philosophy applied to outbound SDKs vs this inbound-to-Neo4j wrapper.

---

## Context

`DatabaseConfig.query_timeout=60` and `transaction_timeout=120` were declared in `core/config/unified_config.py` for months but **completely unwired** — no env loading, no usage, no enforcement. A runaway Cypher could only be killed by the client giving up; the Neo4j server never aborted it on the app's behalf. Driver-level timeouts (`connection_timeout`, `connection_acquisition_timeout`, `max_transaction_retry_time`, pool size, lifetime) were already wired in `adapters/persistence/neo4j/neo4j_connection.py` (PR #86), but those bound *connection* concerns, not query execution.

The reason `transaction_timeout` stayed dead: the neo4j 5.x driver has **no global "default tx timeout" knob**. Per-query timeout is *only* applied via `neo4j.Query(text, timeout=...)` for auto-commit `session.run()` and `session.begin_transaction(timeout=...)` for explicit transactions. And there was **no single chokepoint** in the codebase to apply either:

- ~124 `session.run(...)` sites across 24 files in `adapters/persistence/neo4j/` each open their own `self.driver.session()` (mixin pattern under `UniversalNeo4jBackend`).
- `Neo4jQueryExecutor` (the QueryExecutor port adapter) has its own `session.run` sites — used by MEGA-QUERY and analytics.
- `CypherExecutor` (bulk ingestion) uses `session.begin_transaction()` + `tx.run(...)`.
- `IngestionWriteBackend` uses `driver.execute_query()` (a separate native path).

The codebase docstrings explicitly flagged this: "A per-query server-side timeout has no single chokepoint … and is tracked as a separate persistence-layer task." (`neo4j_connection.py`, `unified_config.py`).

## Decision

**Create the chokepoint by wrapping the one shared `AsyncDriver` at the composition root**, not by editing 124 call sites.

A new module `adapters/persistence/neo4j/timed_driver.py` provides:

- `TimedDriver(raw_driver, default_timeout)` — proxies the `AsyncDriver`. `.session()` hands out `TimedSession`; `.execute_query()` auto-wraps `str` queries in `neo4j.Query(text, timeout=resolved)`; everything else delegates via `__getattr__`.
- `TimedSession(raw_session, default_timeout)` — proxies the `AsyncSession`. `.run(query, ...)` wraps `str` queries with the resolved timeout; respects a caller-supplied `Query` (no clobber). `.begin_transaction(metadata=None, timeout=None)` injects `timeout=resolved` only when the caller passed none — this is how `CypherExecutor.execute_batch` (ingestion) inherits the limit on its `tx.run(...)` calls (which themselves take no Query object).
- A `contextvars.ContextVar` with a `_UNSET` sentinel carries the per-operation override. Two context managers set it: `neo4j_query_timeout(seconds)` and `unbounded_neo4j_query_timeout()`.
- A single helper `_as_timed_query(text, timeout) -> Query` contains the one localized `# pyright: ignore[reportArgumentType]` for the `LiteralString` typing friction.

**Wiring** in `services_bootstrap/compose.py:117` (immediately after driver validation, before any consumer):

```python
raw_driver = driver
driver = TimedDriver(raw_driver, default_timeout=config.database.transaction_timeout or None)
# Every downstream consumer reads `driver` and gets the wrapped instance:
query_executor = Neo4jQueryExecutor(driver)
schema_manager = Neo4jSchemaManager(raw_driver)   # ← intentional raw-driver carve-out
# create_all_backends(driver, ...), make_unified_ingestion_service(driver=driver, ...)
```

**Per-operation policy:**

- Default: `120s` (`DatabaseConfig.transaction_timeout`, env `NEO4J_TRANSACTION_TIMEOUT`, `0`=unbounded).
- Bulk ingestion: `600s` via `with neo4j_query_timeout(600.0):` in `BulkUpsertBackend.{upsert_nodes, create_relationships}` (and `upsert_with_relationships`, which delegates to both). Large MD/YAML imports legitimately exceed 120s; a wedged import still self-heals after 10 minutes.
- MEGA-QUERY + analytics: no wrap. Typical run is 5–30s, well under 120s; a true runaway is still caught.
- Startup DDL (`Neo4jSchemaManager`): uses the raw (unwrapped) driver. Vector / full-text / domain index creation on a large `:Entity` label can exceed 120s; aborting at bootstrap would be wrong.
- Migration / one-off scripts that instantiate `Neo4jConnection` directly bypass the wrapper for the same reason.

**Dead-code removal:** `DatabaseConfig.query_timeout` deleted. Only `transaction_timeout` maps to a real neo4j mechanism; two knobs would invite drift over which one "wins." Matches SKUEL's One Path Forward philosophy.

## Alternatives considered

### Alternative 1 — Edit every `session.run` site (explicit-helper pattern)

Add a `to_timed_query(text) -> Query` helper and edit all ~124 `session.run` sites + the `begin_transaction` paths to use it. Add a lint rule (proposed SKUEL023) banning bare `session.run(<str>)` to prevent regressions.

**Pros:** Explicit at every call site; no proxy "magic"; per-site timeout is trivially visible in code; no `__getattr__` indirection to reason about.

**Cons:** ~124 edits across 24 files = large, error-prone diff and review burden; every new `session.run` must remember the helper (hence the need for SKUEL023, itself new code to maintain); the override mechanism still needs a `ContextVar` anyway, so it doesn't avoid that complexity; easy to miss the `begin_transaction` path in `CypherExecutor`.

**Why rejected:** the wrapper achieves the same coverage with a ~3-line compose change + one new module, centralizes the one `LiteralString` pyright-ignore, and auto-covers any future call site. The "no chokepoint" framing was a real constraint — the structurally-correct answer is to *create* the chokepoint, not to spray the timeout across the surface area.

### Alternative 2 — Route every mixin through `Neo4jQueryExecutor`

Make the `UniversalNeo4jBackend` mixins call `self.executor.execute_query(...)` instead of opening their own sessions, then add the timeout in one place inside the executor.

**Pros:** Consolidates session management at the persistence boundary.

**Cons:** The mixin result-consumption patterns vary widely (`.single()` vs `.data()` vs streaming vs transaction-bounded), so a uniform executor signature would force semantic changes far beyond timeout handling. Net: a bigger refactor than the explicit-helper alternative, with the same downside.

**Why rejected:** the wrapper covers `Neo4jQueryExecutor` too (it receives the `TimedDriver` at compose), so this consolidation is unnecessary for the timeout problem.

### Alternative 3 — Wrap inside `Neo4jConnection.connect()`

Have `Neo4jConnection.connect()` itself return a `TimedDriver`, so even migration/index scripts that instantiate `Neo4jConnection` directly get the wrapped driver.

**Pros:** One consistent driver type everywhere.

**Cons:** Migration scripts and one-off index DDL legitimately run for minutes (vector index creation on a populated `:Entity` label); aborting them at 120s would be wrong. They'd then need to wrap every call in `unbounded_neo4j_query_timeout()`, defeating the point.

**Why rejected:** keeping `Neo4jConnection` raw lets scripts opt out by construction. The compose boundary is the right seam — it separates "the running app" (timed) from "ad-hoc DDL" (untimed).

## Consequences

### Positive

- Every runaway query is now bounded by the server, not the client. The integration test demonstrates this: a busy nested-`UNWIND range` Cartesian-product query is aborted by the Neo4j server at the 1s bound in well under 15s wall-clock — without APOC (banned by SKUEL001) and without the client hanging.
- The previously-dead `DatabaseConfig.transaction_timeout` field is live and env-tunable (`NEO4J_TRANSACTION_TIMEOUT`).
- New `session.run` / `begin_transaction` / `execute_query` sites added in the future are automatically covered — no lint rule needed.
- The `LiteralString` pyright friction (caused by SKUEL's dynamic f-string Cypher) is centralized in one helper; no per-site `# pyright: ignore` proliferation.
- Bulk ingestion has a single, visible policy lever (`_BULK_INGESTION_TIMEOUT_SECONDS = 600.0`) — easy to tune or remove.

### Negative / caveats

- `CypherExecutor` is annotated `session: AsyncSession` and receives a `TimedSession` (a duck-typed proxy, not subclass). This passes under SKUEL's mypy even with `arg-type` now enforced on `adapters/`: the backends are annotated `driver: AsyncDriver`, so the executor sees an `AsyncSession` and there is no in-tree mismatch — the proxies flow through the composition boundary as the neo4j driver type. pyright (warning-gate only) is silent here. If a proxy were ever passed where the concrete type is statically required, the fix is a small structural `Protocol` (`SessionLike` with `run` + `begin_transaction`) — not a redesign.
- ContextVars copy at `asyncio.create_task` time. A task that outlives a `with neo4j_query_timeout(...)` block keeps its copy; `reset()` on the outer token does not reach into it. Documentation flags this; SKUEL's ingestion path does not spawn detached mid-upsert tasks, so it doesn't bite in practice.
- A reader at a `session.run` site does not see the timeout being applied; the value is set at compose and overridden via ContextVar. This indirection is documented in `timed_driver.py`'s module docstring and in `docs/patterns/NEO4J_QUERY_TIMEOUT.md`.

### Migration

None required for existing code. The wrapper is fully backward-compatible at the call site (the `TimedSession` / `TimedDriver` proxies are transparent). The only deletion is the unused `DatabaseConfig.query_timeout` field; a stale docstring reference at `adapters/inbound/graphql/config.py:22` was updated in the same PR.

## References

- **PR:** [#89 — feat(neo4j): wire per-query server-side transaction timeout via TimedDriver proxy](https://github.com/linguistic76/skuel/pull/89) (merged commit `c865dc61`).
- **Pattern doc:** [`docs/patterns/NEO4J_QUERY_TIMEOUT.md`](../patterns/NEO4J_QUERY_TIMEOUT.md) — how-to for query authors, override mechanism, when-to-wrap table.
- **Implementation:** `adapters/persistence/neo4j/timed_driver.py`, `services_bootstrap/compose.py` (lines ~116-128, ~140-143), `core/config/unified_config.py` (`DatabaseConfig.transaction_timeout`).
- **Tests:** `tests/unit/test_timed_driver.py` (12 tests), `tests/integration/test_timed_driver.py` (5 tests against the pinned calendar-release testcontainer — the tag is read from `infrastructure/docker-compose.yml`).
- **Related code-side notes:**
  - `adapters/persistence/neo4j/neo4j_connection.py` module docstring — explains why `Neo4jConnection` itself stays raw.
  - `adapters/persistence/neo4j/bulk_upsert_backend.py` — the `_BULK_INGESTION_TIMEOUT_SECONDS = 600.0` constant and the three wrap sites.
