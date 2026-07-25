# ADR-083: Qwen + BGE End-State — Committed Destination, Staged Convergence

**Status:** Accepted — founder-confirmed 2026-07-24
**Date:** 2026-07-24
**Deciders:** MCF
**Arc:** LLM-root convergence — upgrades ADR-081's north star ("Qwen + BGE; don't build against
that grain") from *don't-foreclose* to a committed destination with a staged roadmap.
**Related:** ADR-068 (OpenAI embeddings now, BGE staged — interim mechanics stay authoritative),
ADR-063 (SDK ports), ADR-049 (superseded in model choice), ADR-081 (north star origin).

## Context

The embeddings/LLM stack has converged through three decisions: ADR-049 (March 2026) staged BGE
via the HuggingFace Inference API, ADR-068 (June 2026) wired OpenAI `text-embedding-3-small`
@1024 behind the single chokepoint `create_embedding_client()` with BGE kept as staged code, and
ADR-081 (July 2026) named **Qwen + BGE** the north star for a future self-directed LLM — but
deliberately scoped no code and no commitment.

The PR E review (2026-07-24) that replaced the obsolete GENAI_SETUP rewrite found the
architecture largely aligned with that north star (1024 dims chosen for BGE compatibility;
`EMBEDDING_VERSION`-outranks-hash freshness makes a provider swap self-healing; prefix-routed
chat switcher extends naturally) — and three points where drift works *against* it:

1. **Chunk grain exceeds the staged BGE window.** Curriculum chunks pack up to 500 words
   (~3,000 chars) and reference chunks up to 1,000 words (~6,000 chars), while the staged
   `bge-large-en-v1.5` adapter caps input at 2,000 chars (~512 tokens) and `EmbeddingsService`
   silently truncates to the client's `max_input_chars`. On swap day, every curriculum chunk
   would lose its tail and reference chunks would lose ~60–70% of their content — silently.
2. **OpenAI is wired as permanently required.** FULL-tier bootstrap fail-fasts on
   `OPENAI_API_KEY` for both chat and embeddings, and the chat degrade path assumes OpenAI is
   always present. Correct today; wrong at the destination, where Qwen + BGE are the required
   pair and OpenAI/Anthropic become optional switcher entries.
3. **The index dimension (1024) was hardcoded twice** (bootstrap `sync_vector_indexes` call and
   `scripts/create_vector_indexes.py`), unguarded against drifting apart from the adapters.

## Decision

### 1. The end-state is committed: Qwen chat + BGE embeddings

SKUEL's destination is a self-directed model stack — **Qwen** as the chat/serving model
(ultimately the trained/fine-tuned LLM of ADR-081) and **BGE** dense embeddings. The interim
stack — OpenAI embeddings (ADR-068) and the OpenAI/Anthropic per-conversation chat switcher —
remains fully supported until each arc lands, and the ChatGPT/Claude choice survives the
end-state as optional switcher entries. This is a commitment of *direction*, not a rewrite:
nothing in the interim changes for users.

### 2. The BGE target model is **BGE-M3**, superseding `bge-large-en-v1.5`

`BAAI/bge-m3` reads 8,192 tokens of context and emits 1024-dim dense vectors — the truncation
conflict (Context #1) vanishes with no re-chunking and no index migration, and the trained
end-state gets a retrieval model worth fine-tuning against. The ADR-049/068 staged choice
(`bge-large-en-v1.5`) is superseded on paper here; the staged adapter's model/cap update lands
in Arc 1, not this change. Until then the adapter deliberately still says `bge-large-en-v1.5`.

### 3. Design rules — the "don't work against the grain" contract

These bind all new code from now until convergence:

- **1024 dims is frozen.** The embedding/index dimension lives in ONE place
  (`EmbeddingGeometry.DIMENSION`, `core/constants.py`); both embedding adapters, bootstrap
  index sync, and the index script read it. Changing it is an ADR-level decision (index
  `--recreate` + full re-embed), never a local edit.
- **Embedding-text budgets are judged against the END-STATE model's window, not just the wired
  provider's.** Any chunking-grain change must check both `OpenAIEmbeddingAdapter` and the
  staged BGE adapter's `MAX_INPUT_CHARS`. Arc 1 adds a guard so the two can't drift apart
  silently again.
- **No new OpenAI-required assumptions.** OpenAI stays required in FULL tier *today*, but that
  fact is expressed in exactly two places — `create_embedding_client()` and
  `create_chat_client()`. New code must route through those chokepoints and the
  provider-agnostic `UnifiedLLMCaller`/`resolve_chat_model` path; it must never read
  `OPENAI_API_KEY`, hardcode a provider, or assume OpenAI presence anywhere else. Inverting
  "required" to "optional" at convergence must touch only the two factories.
- **Provider swaps happen ONLY at the two factories.** Per-conversation model choice via
  `resolve_chat_model()` remains the one selection surface; new model families join by prefix
  route (`qwen*`), not by new call paths.

### 4. The roadmap: three arcs

- **Arc 1 — BGE-M3 readiness (no switcher):** update the staged HF adapter to `BAAI/bge-m3`
  with its real input cap; add the chunk-budget guard (chunking params validated against the
  staged adapter's window at quality-gate time, not swap time).
- **Arc 2 — Qwen in the switcher (additive):** a third chat adapter behind an
  OpenAI-compatible endpoint (vLLM/DashScope/Together — the droplet has no GPU, so serving is
  hosted initially), `qwen*` prefix route in `UnifiedLLMCaller`, headline-model entry. The
  existing ChatGPT/Claude switcher is untouched.
- **Arc 3 — embeddings switcher + cutover (deliberately postponed):** `EMBEDDINGS_PROVIDER`
  read in `create_embedding_client()`, `EMBEDDING_VERSION` v3→v4 bump, batch re-embed via the
  existing `--stale`/version machinery, ops runbook. Postponed by design — recorded here so no
  interim work fights it.

### 5. Shipped with this ADR (the redefined PR E polish)

`GENAI_SETUP.md` → `EMBEDDINGS_SETUP.md` (the content was already rewritten to ADR-068 reality
in June; the name lagged), `README_GENAI_SCRIPTS.md` → `README_EMBEDDING_SCRIPTS.md` (content
still described the v2 HF era as current), `EmbeddingGeometry.DIMENSION` extraction, the LLM
factory default aligned to `DEFAULT_CHAT_MODEL` (was a second literal, `gpt-4` vs `gpt-4o`),
and the last plugin-era comment sweep (`entity.py`, `prometheus_metrics.py` docstring).

## Consequences

- The interim stack is unchanged for users; this ADR's force is on *new code* (design rules)
  and *sequencing* (arcs).
- ADR-068 remains the authoritative record of interim embedding mechanics; ADR-049 is now fully
  superseded in model choice (provider by ADR-068, model by this ADR).
- `HF_API_TOKEN` stays a staged credential (catalogued, not read at bootstrap) until Arc 3.
- Every future review can test a change against §3 the way ADR-081 tested its slice: "does this
  design against Qwen + BGE?" now has a written contract to answer with.

## Follow-ups

- Arc 1 (BGE-M3 adapter + chunk-budget guard) shipped in PR #802 (2026-07-24).
- Arc 2 (Qwen adapter + route) is **trigger-gated, not next-in-line** (founder-reviewed
  2026-07-24): it starts when ADR-081 work needs a live Qwen endpoint — fine-tuning
  experiments, or any other concrete reason to chat with Qwen. Until then hosted vanilla
  Qwen offers nothing the wired providers don't, at extra cost, and every piece of the arc
  is perishable (endpoint market, model names, pricing). All four pieces defer together —
  endpoint choice, adapter, `qwen*` route, headline entry; nothing is pre-staged, since the
  §3 rules already keep the arc purely additive. The hosted serving endpoint is chosen at
  arc start, not before.
- Arc 3 needs only Arc 1 plus a scheduled re-embed window — it does NOT depend on Arc 2.
  (The original "until Arcs 1–2 land" sequencing was ordering by fiat, not a technical
  dependency; the embeddings cutover must not wait on a chat feature with no planned usage.)
