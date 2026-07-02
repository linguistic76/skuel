# ADR-074: Ingestion Never Embeds Inline — One Post-Persist Event Chokepoint for Both Doors

**Status:** Accepted — PR 1 (#487, post-persist chokepoint), PR 2 (#488, chunk unification),
and PR 3 (--stale backfill + empty-body clear path) shipped (see *Implementation Status*).
**Date:** 2026-07-02
**Related:** ADR-043 (intelligence tier toggle), ADR-063 (LLM/embedding SDK ports),
ADR-068 (OpenAI embeddings now, BGE later), ADR-070 (VaultBridge — vault sync as the primary write path)

---

## Context

A full audit of the embedding pipeline (2026-07-02) found the write side mostly
disconnected from how content actually enters SKUEL:

- The event-driven pipeline (`*EmbeddingRequested` → `EmbeddingBackgroundWorker`) covered
  only in-app Activity creates. The **batch/directory door** — the primary path post-ADR-070
  (vault reconciler, "Sync from Obsidian", admin content sync, `./dev vault-sync`) — produced
  **no embeddings, no chunks, no events**.
- The single-file door's inline-embed branch was dead in the app: `compose.py` constructed
  `UnifiedIngestionService` with `embeddings_service=None` and a "will be created later"
  comment that no code ever fulfilled.
- Nothing re-embedded on update or re-ingest. Nearly all live embeddings existed because of
  one manual backfill run (2026-06-10), and the majority had gone stale — bulk re-syncs bump
  `updated_at` and touched nothing embedding-shaped.
- PathStep content had a shape fork: the single-file door popped the body to
  `:Content`/`:ContentChunk` nodes; the batch door left it as a `content` property on the
  entity node — so the chunk/RAG substrate only ever materialized through the door nobody used.

## Decision

### 1. Ingestion never embeds inline — one post-persist event chokepoint

Ingestion's only contact with embeddings is *after* persistence: publish the entity's
`*EmbeddingRequested` event and let the background worker embed asynchronously. The inline
path (`prepare_entity_data_async` + `embeddings_service` on the ingestion service) is deleted,
not gated — preparation is one sync function for both doors.

The chokepoint is `core/events/embedding_publisher.py`:

- `EMBEDDING_EVENT_TYPES` — the one `EntityType → event class` map (12 types, mirroring the
  worker's subscriptions).
- `publish_embedding_requested(event_bus, entity_type, source, logger, changed_fields=...)` —
  used by **every** producer: both ingest doors (via
  `UnifiedIngestionService._publish_embedding_requests`), all in-app create paths, and all
  in-app update paths. The `changed_fields` gate skips the publish when no changed field is
  in `EMBEDDING_FIELD_MAPS` (a status flip must not enqueue a redundant re-embed).

In-app updates re-embed: all 9 update sites (6 Activity domains + PS/LP/Exercise) publish
through the chokepoint with `changed_fields`. The 5 formerly-PLANNED curriculum events are
live producers.

### 2. Tier gate at the composition root

`UnifiedIngestionService` gets `event_bus=event_bus if tier.ai_enabled else None`
(`compose.py`) — the same gate and rationale `BatchChunkingService` already had: publishing
embedding events in CORE is a queue-with-no-listener. The ingestion step treats
`event_bus is None` as a silent no-op, so CORE boots and ingests with zero listener-less
publishes. Chunking and `:Content` persistence still run in CORE — chunks are Analog
(stored, not embedded), per the graceful-degradation contract.

### 3. Chunk unification — one shared PathStep chunk step for both doors

`UnifiedIngestionService._chunk_path_step_content(uid, content_body, file_format,
source_path)` is THE chunk step: chunk → `store_content_with_chunks` (`:Content` +
`:ContentChunk` + `:ContentMetadata`) → one `ChunkEmbeddingRequested` carrying every
persisted chunk id. The single-file door calls it directly; the batch engine pops `content`
off each PathStep pre-upsert (setting `word_count` in its place), threads the popped body to
`post_persist_fn` as `PathStepChunkSource`, and the callback
(`_ingest_post_persist`) runs the same step. "Content chunks are created during ingestion
in both modes" is now true of both doors. Chunk-step failures never fail ingestion.

### 4. PathStep ENTITY embedding = frontmatter fields; body semantics = CHUNK embeddings

On every trigger path (ingest, in-app update, backfill), the PathStep **entity** vector is
built from frontmatter fields only — the popped body is deliberately never re-attached for
embedding-text purposes. Body-content semantics live in the **chunk** vectors. One recipe,
three triggers (Kody-review design ruling on #487).

### 5. Empty-body re-ingest takes an explicit clear path

Ruled 2026-07-02: a PathStep re-ingested with its body emptied must not keep the previous
body's state. Both doors thread the empty body through the shared chunk step, whose
empty-body branch deletes the `:Content` subtree leaf-first
(`Neo4jContentAdapter.delete_content_subtree` — chunks + metadata, then content; deleting
the `:Content` node alone would orphan chunks in the vector index), and both doors write
`word_count` unconditionally so `0` overwrites the stale count — the bulk upsert
(`n += props`) never removes omitted keys, so a skipped write would silently keep it.

### 6. Resource deviation — staged, not wired

`ResourceEmbeddingRequested` has **no possible producer**: Resource is not file-ingestible
(no `ENTITY_CONFIGS` entry) and `ResourceService` is read-only. The mapping stays in
`EMBEDDING_EVENT_TYPES` with a staged note so the first Resource creation path embeds with
zero extra wiring. This is deliberate staging (PLANNED-tier thinking), not dead code.

### 7. Script-mode freshness gap → in-process drain, `--stale` backfill as backstop

One-shot syncs (`./dev vault-sync`, the script-mode reconciler) publish to an **in-process**
bus whose embedding worker timer loop only runs in the app process. Originally their events
evaporated with the script and the backfill script was the documented freshness path — a
two-command recipe that was forgotten the same day it shipped (the #490 force-verify left
110 entities drift-stale). Closed at the root: the worker's subscription step is split out
(`subscribe()`) and a `drain()` mode processes both queues once, without the timer loop.
`vault_bridge_sync.py` subscribes the worker before the sync and drains after persistence,
so a script-mode sync's entity **and chunk** events flow through the same event path as the
app process. Termination is guaranteed by the worker's bounded retries
(MAX_GENERATION_ATTEMPTS).

`scripts/generate_embeddings_batch.py` remains the **backstop**, not a required follow-up —
for pre-existing coverage gaps or drift (e.g. events lost from the in-memory queue on an app
restart). Both modes: the default run embeds nodes with no embedding yet (so `--stale`
deliberately skips them), and `--stale` re-embeds drifted ones
(`embedding_updated_at < updated_at` or `embedding_version` mismatching the current
`EMBEDDING_VERSION`; NULL counts as a mismatch). The two stay separate modes so re-embedding
— which re-spends API money on existing vectors — is always an explicit choice. The
predicate coerces `updated_at` through `datetime()` because its storage type is
writer-decided — ISO strings and native datetimes coexist in the live graph, and a bare `<`
across types is null in Cypher (silently skips nodes).

## Rejected Alternatives

- **Inline embedding at ingest** (wire `embeddings_service` into ingestion as the dead
  comment promised): couples ingestion latency to a network API, forks the write path from
  the in-app event pipeline, and re-creates the two-recipe drift the audit found. Deleted
  instead.
- **Backfill-sweep as the only freshness mechanism** (scheduled/admin `--stale` runs, no
  events): leaves the app's own writes stale between sweeps and makes freshness a cron
  concern. The sweep is the *backstop* (Decision 7), not the mechanism.
- **Per-PathStep chunk fan-out in the batch door**: rejected as premature at 19-PathStep
  scale; the shared step runs serially.

## Consequences

- Both ingest doors and all in-app create/update paths converge on one publish chokepoint —
  new embeddable types need exactly one map entry and one `publish_embedding_requested` call.
- Embedding freshness = event pipeline (app process **and** script process, via
  subscribe-then-drain) + `--stale` backstop. There is no third path.
- CORE tier: zero embedding publishes, zero workers, chunks still persist (Analog).
- The batch door no longer leaks `content` (or `_file_path`) as entity-node properties.
  Pre-existing nodes carry them until the one-shot cleanups run (see below).

## Implementation Status

- **PR 1 (#487, merged 2026-07-02):** chokepoint + `_publish_embedding_requests` post-persist
  step in both doors; inline-embed path deleted; compose tier gate; update publishes with
  `changed_fields`; `_file_path` leak fixed.
- **PR 2 (#488, merged 2026-07-02):** shared `_chunk_path_step_content`; batch engine pops
  PathStep `content` pre-upsert and threads `PathStepChunkSource` to `_ingest_post_persist`.
- **PR 3 (this ADR's PR):** `--stale` flag; empty-body clear path
  (`delete_content_subtree` + unconditional `word_count`); docs pass.
- **One-shot cleanups (verification pass, live DB):** `REMOVE e._file_path` sweep;
  full-mode PathStep re-sync (migrates the 19 entity-prop PathSteps to the `:Content` shape);
  explicit `MATCH (ps:PathStep) WHERE ps.content IS NOT NULL REMOVE ps.content` sweep — the
  re-sync alone cannot clear it (`n += props` never removes omitted keys); then one
  `--stale` run to re-embed the drifted corpus.
- **Follow-up (post-arc review PR 2, 2026-07-02):** the backstop now covers chunks —
  `generate_embeddings_batch.py --label ContentChunk` (coverage) and `--stale` (version
  mismatch; chunks are immutable so there is no `updated_at` predicate). The chunk version
  stamp is unified: the worker passes `EMBEDDING_VERSION` instead of a hardcoded `"v1"`, and
  `EMBEDDING_NODE_LABELS` (chokepoint) replaces the worker's and the script's private label
  maps. The superseded `migrate_embeddings_version.py` / `migrate_chunk_embeddings.py`
  scripts are deleted (One Path Forward — the backfill is THE backstop). Live: 305/305
  chunks re-embedded v1→v3.
- **Follow-up (post-arc review, 2026-07-02):** script-mode freshness gap closed at the root —
  `EmbeddingBackgroundWorker.subscribe()` split from `start()`, new `drain()` one-shot mode,
  wired into `vault_bridge_sync.py` (subscribe before sync, drain after). Prompted by live
  evidence: the #490 verify left 110 entities drift-stale because the two-command backfill
  recipe wasn't run.
- **Follow-up (arc residue 4):** the re-sync above required manually invalidating
  `IngestionMetadata` rows (`SET s.content_hash='force', s.file_mtime=0.0`) because the vault
  wall upgrades full → smart and unchanged files never re-process through any admin door.
  Productized as `force` re-ingestion — `ingest_directory(force=True)`,
  `POST /api/vault/sync/content` body `{"force": true}`, `./dev vault-sync --force` — which
  bypasses only the hash/mtime skip while keeping the wall, metadata re-stamping, and deletion
  reconciliation (force ≠ full). See `UNIFIED_INGESTION_GUIDE.md § Ingestion Modes`.
