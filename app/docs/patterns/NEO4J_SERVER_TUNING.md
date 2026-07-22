# Neo4j Server Tuning (memory, JVM, Vector API)

**Core Principle:** "The server config is data, not code — it lives in one compose file and only `.env` changes across stages."

Every Neo4j **server**-side setting is expressed as a `NEO4J_*` environment variable on the `neo4j`
service in **`infrastructure/docker-compose.yml`** (the single source; the app compose `extends` it).
The Neo4j Docker image translates each `NEO4J_<key>` var into the matching `neo4j.conf` setting
(`__` → `_`, single `_` → `.`). Nothing is hand-edited inside the container. This keeps the config
**environment-agnostic** (ADR-044): only credentials/memory in `.env` change from Docker → Droplet →
AuraDB.

This doc covers the **server process** knobs. For the per-query transaction ceiling wired on the
driver side, see [NEO4J_QUERY_TIMEOUT.md](NEO4J_QUERY_TIMEOUT.md) / ADR-064.

> **Self-host-only (AURA-TEMPORARY):** the memory sizing (heap/page-cache) and the Vector API
> (SIMD) flag below exist **only because SKUEL self-hosts Neo4j**. AuraDB provides both by default
> (memory by instance tier; Vector API on), so they are temporary scaffolding — marked
> `# AURA-TEMPORARY:` in the compose/k8s files and dropped on migration. Don't over-invest in
> tuning them. Checklist: [AURADB_MIGRATION_GUIDE.md § 6.2](../deployment/AURADB_MIGRATION_GUIDE.md).
> The driver-side knobs (per-query timeout, schema monitoring, APOC scoping) port cleanly and are
> **not** temporary.

## Config surface

| Concern | `NEO4J_*` env var | Value | Notes |
|---------|-------------------|-------|-------|
| Heap (initial / max) | `server_memory_heap_initial__size` / `..._max__size` | `${NEO4J_HEAP_INIT}` / `${NEO4J_HEAP_MAX}` | From `.env`; the only memory knobs that change per stage |
| Page cache | `server_memory_pagecache_size` | `${NEO4J_PAGECACHE}` | Graph-traversal working set |
| Server-side tx timeout | `db_transaction_timeout` | `600s` | Bulk ceiling; the driver adds a tighter per-tx bound (ADR-064) |
| Query cache entries | `server_memory_query__cache_per__db__cache__num__entries` | `2000` | Parameterized-query plan cache |
| Cypher planner | `dbms_cypher_planner` | `COST` | Cost-based optimization |
| Slow-query log | `db_logs_query_enabled` / `_threshold` | `INFO` / `1s` | Logs queries > 1s with parameters |
| APOC allowlist | `dbms_security_procedures_allowlist` | `apoc.meta.*` | Meta procedures only (SKUEL001 — domain services use pure Cypher) |
| **JVM extra args** | **`server_jvm_additional`** | **`--add-modules jdk.incubator.vector`** | **Vector API — see below (APPENDS to ~22 vendor flags)** |
| Cypher language | `db_query_default__language` | `CYPHER_5` | Vendor conf pins CYPHER_25 for new installs; SKUEL pins CYPHER_5 until a deliberate migration |

The image's bundled `neo4j.conf` ships ~22 vendor-recommended `server.jvm.additional` lines
(verified on `2026.05.0`/`2026.06.0`: explicit G1GC, `-XX:+AlwaysPreTouch`,
`--enable-native-access=ALL-UNNAMED`, `--add-opens`, netty and Lucene-vectorization flags), and
SKUEL runs with all of them: compose deliberately does **not** mount `/conf`, because the
entrypoint wipes `$NEO4J_HOME/conf/*` whenever `/conf` is mounted (an empty `/conf` mount used to
erase the whole vendor flag set on every boot — restored 2026-07-20; symptoms while erased:
"restricted method ... native access" boot warnings, no `AlwaysPreTouch`, Lucene vectorization
sysprop missing). `NEO4J_server_jvm_additional` is append-not-replace
(`_append_not_replace_configs` in `/startup/docker-entrypoint.sh`), so our Vector API flag
APPENDS: live JVM = 22 vendor flags + `--add-modules jdk.incubator.vector` + `-Xms`/`-Xmx`. One
vendor-conf setting is deliberately overridden: the vendor pins
`db.query.default_language=CYPHER_25` for new installs, while SKUEL's query corpus runs CYPHER_5 —
pinned explicitly in compose and the k8s manifest so a CYPHER_25 migration happens as its own
deliberate arc, never as a config side effect. The setting applies to **newly created** databases
only — an existing database keeps the language it was created with. Verify with
`SHOW DATABASES YIELD name, defaultLanguage`; migrate a pre-pin database with
`ALTER DATABASE neo4j SET DEFAULT LANGUAGE CYPHER 5`. (Dev verified 2026-07-20: `neo4j` and
`system` both report `CYPHER 5`.)

## Vector API (SIMD) — why it is enabled

SKUEL runs **seven 1024-dim cosine vector indexes** — `Entity`, `ContentChunk`, `ReferenceChunk`,
`Goal`, `Task`, `Ku`, and `PathStep` embeddings. Semantic search, canon retrieval (ADR-076/077),
ZPD, and the "Related concepts" detail-page lens all query them via
`db.index.vector.queryNodes(...)`. (Embeddings are generated **Python-side** — OpenAI
`text-embedding-3-small` @1024, ADR-068, BGE staged long-term — never by a Neo4j GenAI plugin; the
server only *indexes and searches* the vectors.)

Neo4j `2026.x` boots with this warning when the incubator module is not loaded:

```
WARN  Java vector incubator module is not readable. For optimal vector performance,
      pass '--add-modules jdk.incubator.vector' to enable Vector API.
```

Without the module, the index's distance math runs **scalar** instead of using vectorized (SIMD) CPU
instructions — slower, and the gap widens as the embedded-node count grows. `--add-modules
jdk.incubator.vector` enables the Java Vector API so those computations are vectorized. This is a
free, additive win for a subsystem SKUEL leans on heavily; the trade-off is nil (the module is
shipped in the JDK, just not opened by default).

## Verifying a JVM/vector change

After changing `server_jvm_additional` (or any `NEO4J_*` var), recreate the container and confirm:

```bash
cd /home/mike/skuel/app
docker compose up -d neo4j            # recreate with the new env (forward, in-place)

# 1. the Vector API warning should be GONE from the boot log
docker logs skuel-neo4j 2>&1 | grep -c "vector incubator"        # -> 0

# 2. the flag is actually in the live JVM (find the java pid, read its args)
JPID=$(docker exec skuel-neo4j sh -c 'for p in /proc/[0-9]*; do grep -qa java "$p/comm" && echo ${p#/proc/}; done' | head -1)
docker exec skuel-neo4j sh -c "tr '\0' '\n' < /proc/$JPID/cmdline" | grep -E 'add-modules|Xmx'

# 3. a real vector query still returns results (data + index intact)
docker exec skuel-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -d neo4j \
  "MATCH (n:Entity) WHERE n.embedding IS NOT NULL WITH n.embedding AS v LIMIT 1
   CALL db.index.vector.queryNodes('entity_embedding_idx', 3, v) YIELD node, score
   RETURN count(*) AS hits;"
```

> Server-config changes are a container **recreate**, which for Neo4j is a forward, in-place restart —
> the store is untouched. (Version *downgrades* are a different matter; see ADR-067 § 3a.)

## See also

- [NEO4J_QUERY_TIMEOUT.md](NEO4J_QUERY_TIMEOUT.md), [ADR-064](../decisions/ADR-064-neo4j-per-query-timeout.md) — the driver-side per-query timeout (the other half of "server behaviour we control")
- [ADR-080 — AuraDB Three-Horizon Strategy](../decisions/ADR-080-auradb-three-horizon-strategy.md) — the strategy behind the `AURA-TEMPORARY` convention: these self-host knobs drop on the (Horizon-0) move to AuraDB Free; §5 formalizes the marker
- [ADR-067 § 3a](../decisions/ADR-067-dependency-upgrade-policy.md) — Neo4j server version policy (calendar line, forward-only upgrades)
- [ADR-068](../decisions/ADR-068-openai-embeddings-now-bge-later.md) — embedding provider (why the vectors exist; the server only indexes them)
- `neo4j-cypher-patterns` skill § vector indexes — the query/DDL side (`sync_vector_indexes()`, `VectorSearchBackend`)
- `infrastructure/README.md` — running the Neo4j service (image, ports, volumes, upgrade steps)
- [AURADB_MIGRATION_GUIDE.md § 6.2](../deployment/AURADB_MIGRATION_GUIDE.md) — the self-host-only (`AURA-TEMPORARY`) knobs that disappear on AuraDB, vs. what ports cleanly
