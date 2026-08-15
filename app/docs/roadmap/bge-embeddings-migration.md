# BGE Embeddings Migration (ADR-083 Arc 3)

**Created:** 2026-07-24
**Status:** Ready to execute — Arc 1 (staging) merged as PR #802 (2026-07-24); Arc 3 (cutover)
deliberately postponed, independent of Arc 2 (Qwen chat)
**Authority:** `/docs/decisions/ADR-083-qwen-bge-end-state-commitment.md`,
`/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md`
**Runbook:** `/docs/operations/EMBEDDING_VERSION_UPGRADE.md`

Switching production embeddings from OpenAI `text-embedding-3-small` to `BAAI/bge-m3` via the
HuggingFace Inference API. The architecture was built so this swap is boring: a small PR, one
secret on the droplet, and one batch re-embed.

---

## Already in Place (After Arc 1)

| Piece | State | Where |
|-------|-------|-------|
| BGE adapter | Implemented, pointed at `BAAI/bge-m3`, same `EmbeddingClientOperations` port as OpenAI | `adapters/external/embeddings/huggingface_adapter.py` |
| Dimension parity | 1024 frozen via `EmbeddingGeometry.DIMENSION`; OpenAI already requests 1024 via `dimensions` param; BGE-M3 emits 1024 natively | `core/constants.py` |
| Vector indexes | All 7 AuraDB indexes at 1024/COSINE — **no drop/recreate needed** | `scripts/create_vector_indexes.py`, `adapters/persistence/neo4j/query/schema_ddl.py` |
| Credential catalog | `HF_API_TOKEN` catalogued (optional, sensitive, staged) | `core/config/credential_setup.py` |
| Re-embed tooling | `--stale` backfill, idempotent, version-outranks-hash | `scripts/generate_embeddings_batch.py` |
| Chunk-budget guard | Prevents chunking grain drifting past the 8192-token M3 window | `tests/unit/test_chunk_embedding_budget.py` |

## Cutover Steps (Arc 3)

1. **Swap the factory** — `create_embedding_client()` in
   `adapters/external/embeddings/factory.py` is the single provider chokepoint (ADR-068).
   Per ADR-083, Arc 3 introduces an `EMBEDDINGS_PROVIDER` env var read here rather than
   hardcoding the other adapter, so the droplet can flip providers via config.
2. **Bump `EMBEDDING_VERSION` v3 → v4** in `core/services/embeddings_service.py` and extend
   the version-history comment (`v4 = BGE-M3 @1024 via HF Inference API`). The bump is what
   marks every stored vector stale — version outranks the text-hash freshness check (ADR-074
   §8), so the whole corpus re-embeds even where text is unchanged.
3. **Supply `HF_API_TOKEN`** — keychain locally; on the droplet add to
   `/opt/skuel/secrets.env` (mode 0600). `OPENAI_API_KEY` stays required regardless: chat
   still runs on OpenAI until Arc 2.
4. **Restart, then re-embed:**
   ```bash
   uv run python scripts/generate_embeddings_batch.py --stale
   ```
   Walks all 13 embeddable entity types (`EMBEDDABLE_LABELS`) plus ContentChunk/ReferenceChunk. Idempotent and
   resumable.
5. **Verify** — done when nothing is left on v3:
   ```cypher
   MATCH (n:Entity) WHERE n.embedding IS NOT NULL
   RETURN n.embedding_version AS version, COUNT(n) AS count
   ORDER BY version
   ```

## What to Weigh Before Flipping

- **Migration window.** While the backfill runs, v3 (OpenAI) and v4 (BGE) vectors coexist in
  the same indexes — geometrically compatible but semantically different spaces, so search
  quality degrades mid-migration. Run the backfill immediately after the flip; don't let the
  mixed state drift.
- **Runtime dependency trade.** OpenAI's embeddings endpoint is exchanged for the HuggingFace
  Inference API — different latency, rate limits, and reliability profile. The adapter carries
  the same tenacity retry pattern, but HF serverless inference for BGE-M3 can cold-start.
  This is the main operational unknown; sanity-check latency/availability before cutting over
  the droplet.

## Non-Issues

- **Index migration** — both providers emit 1024 dims; `--recreate` is not needed.
- **Arc 2 dependency** — none. Embeddings cutover is decoupled from the Qwen chat adapter.
- **OpenAI removal** — not part of this migration; `OPENAI_API_KEY` remains a FULL-tier
  requirement for chat until Arc 2 lands.
