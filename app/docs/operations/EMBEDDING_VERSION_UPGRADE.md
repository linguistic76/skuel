# Embedding Version Upgrade Workflow

## Overview

When changing the embedding model or its parameters (e.g., the staged OpenAI → BGE swap,
ADR-068), follow this workflow to re-embed all entities with version tracking.

**Version source of truth:** the `EMBEDDING_VERSION` constant in
`core/services/embeddings_service.py`. Both the background worker and the backfill script store
through `EmbeddingsService.store_embedding_with_metadata()`, so there is exactly one writer of
version/model metadata. There are NO embedding env vars (ADR-068 deleted `EmbeddingConfig`).

**Applies to:** all 12 embeddable labels (Task, Goal, Habit, Event, Choice, Principle, Ku,
Resource, Exercise, PathStep, LearningPath, RevisedExercise).

---

## Prerequisites

- Database backup completed (production only)
- New model available through an `EmbeddingClientOperations` adapter
- `OPENAI_API_KEY` (or the new provider's key) available via keychain/env

---

## Step 1: Swap the Provider / Bump the Version (code change)

1. **Provider/model:** edit `create_embedding_client()` in
   `adapters/external/embeddings/factory.py` — THE provider chokepoint. For the staged BGE swap
   this means returning `HuggingFaceEmbeddingAdapter` instead of `OpenAIEmbeddingAdapter`.
2. **Version:** increment `EMBEDDING_VERSION` in `core/services/embeddings_service.py` and
   extend its history comment.
3. Restart the application.

**Dimension changes require index recreation** — `CREATE VECTOR INDEX IF NOT EXISTS` never
alters an existing index, and Neo4j vector indexes silently ignore wrong-dimension vectors:

```bash
uv run python scripts/create_vector_indexes.py --recreate
```

(The current 1024-dim indexes already match both `text-embedding-3-small` @1024 and
`bge-large-en-v1.5`, so the OpenAI↔BGE swap does NOT need this step.)

---

## Step 2: Identify Entities Needing Re-embedding

```cypher
MATCH (n:Entity)
WHERE n.embedding IS NOT NULL
RETURN n.embedding_version AS version, n.entity_type AS entity_type, count(n) AS count
ORDER BY version, count DESC
```

Anything with a version older than the current constant needs re-embedding;
`verify_fresh_embeddings()` (THE skip decision — version outranks text hash) and its
consumers (worker pre-check, `--stale` fine filter, `get_or_create_embedding()`) treat
it as stale automatically.

---

## Step 3: Re-embed

```bash
# Stale sweep — entities (version mismatch or edited-after-embed) AND content
# chunks (version mismatch) in one run
uv run python scripts/generate_embeddings_batch.py --stale

# Or: backfill nodes with no embedding at all (also covers chunks)
uv run python scripts/generate_embeddings_batch.py [--label Ku|ContentChunk]
```

**Version outranks hash (ADR-074 §8):** `verify_fresh_embeddings`'s content-hash skip never
applies to a version-mismatched node — a deliberate version bump re-embeds the whole corpus
even though every `embedding_text_hash` still matches its unchanged text. Do NOT expect the
hash to (and never make it) short-circuit a model migration. The unrelated `--stamp-hashes`
mode is also version-gated: it only ever stamps *current*-version vectors.

One script, both modes (ADR-074 §7 — the backfill is THE backstop; the former
`migrate_embeddings_version.py` / `migrate_chunk_embeddings.py` scripts are
deleted, superseded by `--stale` and `--label ContentChunk`).

Cost at SKUEL scale is negligible with `text-embedding-3-small` (a few hundred entities ≈
well under $0.01).

---

## Step 4: Monitor

### Version distribution

Re-run the Step 2 query — old-version counts should drain to zero.

### Worker metrics (event-driven embeddings)

```bash
curl -s http://localhost:8000/metrics | grep skuel_embedding
```

---

## Step 5: Verify Complete

```cypher
MATCH (n:Entity)
WHERE n.embedding IS NOT NULL
  AND n.embedding_version <> $current_version
RETURN count(n) AS remaining
```

**Expected:** `remaining: 0`. Spot-check `n.embedding_model` and `size(n.embedding)` on a few
nodes.

---

## Rollback Strategy

1. Revert the factory/constant commit (provider + version are code, not env).
2. Restart the application.
3. Re-run the re-embedding sweep at the reverted version, or restore the pre-upgrade Neo4j
   backup if vectors must be byte-identical.

---

## Version History

| Version | Date       | Change |
|---------|------------|--------|
| v1      | pre-2026-03 | OpenAI `text-embedding-3-small` @1536 via Neo4j GenAI plugin |
| v2      | 2026-03-12 | BGE `bge-large-en-v1.5` @1024 via HF Inference API (ADR-049 — never backfilled) |
| v3      | 2026-06-10 | OpenAI `text-embedding-3-small` @1024 via API `dimensions` param (ADR-068) |

---

## Related Documentation

- `/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md` — provider decision + chokepoint
- `/docs/decisions/ADR-083-qwen-bge-end-state-commitment.md` — committed end-state + roadmap (v4 = the Arc 3 BGE cutover)
- `/docs/development/EMBEDDINGS_SETUP.md` — setup guide
- `/core/services/background/embedding_worker.py` — worker implementation
- `/scripts/generate_embeddings_batch.py` — backfill (service-mediated, version-aware)
