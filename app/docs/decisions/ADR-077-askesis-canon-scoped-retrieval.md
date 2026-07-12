# ADR-077: Companion Grounding via a Shared Corpus-Scope Seam — Askesis (PS-scoped) & Journals (vault-scoped) Share One Retrieve-and-Cite Contract

**Status:** Accepted (Mike, 2026-07-11) — Phase 1 shipped per
`plans/askesis-canon-phase1-implementation.md`: PR-A (scoped retrieval seam +
`to_teaching_block` framing) shipped 2026-07-11 (#612); PR-B (Askesis consumer + citation
surface) shipped 2026-07-11 (#613).
**Amendment (2026-07-11, Codex #613 P2):** the teaching block is **mode-aware**, not
mode-orthogonal as Decision 6 originally stated — `to_teaching_block(preserve_method=)`
keeps the Socratic method paragraph for SOCRATIC/EXPLORATORY/ENCOURAGING but swaps it
for a direct-answer framing in DIRECT mode (which promises answers; the original
"ask a better question, not recite" wording contradicted the user's explicit mode
choice). The ADR-076 faithfulness contract is identical in both framings.
**Date:** 2026-07-09
**Related:** ADR-076 (canon may quote & cite), ADR-073 (journals zero-persistence),
ADR-074 (post-persist embedding events), ADR-070 (Obsidian VaultBridge — the personal vault),
ADR-043 (intelligence tier toggle), ADR-044 (Neo4j hexagonal boundary),
#565/#566 (Resources reference library — `CITES_RESOURCE` + `locator`), #572 (canon quote-and-cite on journals),
#512/#513/#514 (user-entry search + `SearchVisibility` owner-scoping)
**Design doc:** [`docs/architecture/ASKESIS_CANON_INTEGRATION_DESIGN.md`](../architecture/ASKESIS_CANON_INTEGRATION_DESIGN.md)
**Extends:** [ADR-076](ADR-076-canon-quotation-and-citation-policy.md) — the reusable capability it created.

---

## Context

ADR-076 built the canon quote-and-cite capability (`core/services/canon/`) **domain-agnostic**
so other surfaces could call it "without a rewrite." Two surfaces want it: **Askesis** (a
Socratic companion anchored to a learner's active PathStep) and **Journals** (a reflective
companion over the user's writing). The question this ADR settles is *what they share*.

**The reframing that sets the shape (2026-07-09).** The peer of Askesis's **PathStep** is not
a single journal entry — it is the user's **vault, minus what is marked private** (the
VaultBridge personal vault, ADR-070; e.g. `/home/mike/0bsidian/skuel`). Both are a **scope**:
a bounded region that defines *what the companion may ground its response in*. The PS scopes a
region of the **curriculum** graph; the vault-minus-private scopes a region of the user's
**personal** files. A journal entry is just the *anchor* note within the vault scope, exactly
as the PS is the anchor within its curriculum scope.

Seen this way, each companion grounds in **two scoped corpora** — one public, one personal:

| | **Public corpus** (freely cited) | **Personal corpus** (owner-scoped, private-gated) |
|---|---|---|
| **Journals** | canon shelf (`:ReferenceChunk`, walled) | the user's **vault-minus-private** (`:ContentChunk`/knowledge, owner-scoped) |
| **Askesis** | PS curriculum + PS-cited Resources (`:ContentChunk` + `:ReferenceChunk`) | the learner's **own work on the PS** (UserEntries, owner-scoped) |

The retrieval *operation* is identical across all four cells — **resolve a scope → rank by
relevance × importance → infuse-and-cite**. What differs is the **substrate + visibility**: the
walled reference index (public, invisible to SearchRouter) vs. the main content index
(owner-scoped via `SearchVisibility`). That distinction is load-bearing and must not be erased.

**Two structural facts** constrain the concrete first slice (the reference shelf):
1. Canon retrieval is **unscoped** — `search_reference_chunks()` searches the whole shelf via
   `db.index.vector.queryNodes` on the walled `referencechunk_embedding_idx`.
2. Neo4j 5.26's vector index has **no metadata pre-filter**; post-filtering its top-K by
   resource silently loses recall. But each `:ReferenceChunk` stores its own `embedding`, so a
   scoped set can be scored **exactly** with `vector.similarity.cosine()` (verified live against
   the shelf, 2026-07-09).

Mike's locked decisions: **(1)** scope = the connected corpus only (PS-connected for Askesis;
vault-minus-private for Journals), never the whole world; **(2)** interaction = infuse-and-cite
(reason *with* the corpus), not a separate "talk to the source" mode; **(3)** quotability =
chunk the connected sources too, not just FOUNDER shelf books; **(4)** per-source **importance
weighting** is a foundation to be refined with use, not solved up front.

## Decision

**1. One corpus-scope contract — the seam.** Retrieval is parameterized by a **corpus scope**
(a selector that resolves to the set of retrievable units the companion may ground in) plus a
per-unit **weight**. The contract shape is `retrieve(query, *, scope, …) → passages`, and every
grounding surface calls it. This is the unification — *at the contract, framing, and citation
layer*, one path; the underlying index is chosen by the scope.

**2. First realization — the reference-chunk scope (PS-scoped).** Widen the single port method
`ReferenceChunkSearchOperations.search_reference_chunks` (and `CanonRetrievalService.retrieve`)
with an **optional `resource_uids: list[str] | None = None`**. `None` = whole shelf (journal,
unchanged). A list = PS scope (Askesis passes `[r.uid for r in ps_bundle.resources]`). **No
second retrieval service, no parallel value object, no forked adapter.**

**3. The scoped reference case uses exact cosine, not the global index.** Inside the one adapter
method, `resource_uids is None` keeps the existing `db.index.vector.queryNodes` path; a provided
list runs a scoped branch scoring every in-scope `:ReferenceChunk` with
`vector.similarity.cosine(chunk.embedding, $query_embedding)`. Exact (no index-recall loss) and
fast for a handful of books. Both branches return the same `ReferenceChunkHit` shape.

**4. Sibling realization (later) — the vault-minus-private scope.** Journals' personal corpus
rides the **existing owner-scoped content path** (SearchRouter / `VectorSearchBackend.semantic_search_chunks`
on `contentchunk_embedding_idx`), scoped by the user's `SearchVisibility`/`OWNS` declaration and
gated by private-marking. It satisfies the **same contract** (scope → ranked passages →
infuse-and-cite) and reuses the same framing + citation renderer — but it is **not** the walled
reference index and **not** the same Cypher. This elevates today's shallow `_build_context_summary`
(≤8 note snippets) into real scoped-and-weighted retrieval.

**5. Two axes — a hard privacy gate above a soft importance weight.**
- **Privacy = a gate, not a weight.** Private-marked vault files are excluded outright (never
  retrieved, never cited) — the ownership/privacy axis (ADR-073 zero-persist, owner-scoping,
  #512–#514). Non-negotiable whenever the personal corpus is in scope.
- **Importance = a per-unit weight** over the non-private remainder, with a **uniform default**
  and named signals to grow into (recency, explicit marks like pinned/`#important`/MOC
  membership, link-centrality, note-type). Ranking = f(similarity, weight). This is the
  **foundation to refine with use** — the contract *admits* weight so tuning it later is a
  weight-function change, not a re-plumb. **Phase-1's reference slice ships uniform (no weight
  machinery)** — the weight field lands with the vault scope that needs it, so no speculative
  unwired code now.

**6. Teaching-time framing is a third `CanonContext` render method.** Add
`CanonContext.to_teaching_block()` — reusing `CanonPassage`/`CanonSource` and ADR-076's
faithfulness contract verbatim, with a **Socratic stance** (ground questions in the passages;
cite book + structural anchor; quote verbatim and sparingly; *do not surrender the method* — a
passage stating the answer is a reason to ask a better question). `to_prompt_block` (silent) and
`to_discussion_block` (open discussion) unchanged. Injected by
`ResponseGenerator.build_guided_system_prompt` appending the block — empty when no passages.
*Amended in PR-B (see header): the framing is mode-aware — DIRECT mode gets a
direct-answer grounding paragraph via `preserve_method=False` instead of the Socratic
method paragraph; the faithfulness contract is unchanged.*

**7. Citation surface: two provenance blocks, one renderer each.** Askesis's existing
"Sources & Evidence" footer (prerequisite-knowledge provenance via `CitationBundle`) stays. A
distinct **"Drawing on the Readings"** block (reading/personal provenance) is rendered from
`CanonContext.sources()` using the **same clickable renderer built for the journal in #572**,
lifted to a shared UI helper. Canon/personal sources do **not** route through `CitationBundle`;
no second renderer is built. Personal-corpus citations respect owner-scoping.

**8. "Chunk the connected sources too" is content acquisition on the unchanged pipeline.** A
PS-cited Resource becomes quotable exactly as shelf books do (`clean_reference_book.py` →
`ingest_canon_book.py`). Phase-1 draws only on sources **already shelved** (today: one book).
The corpus grows book-by-book; non-book kinds (article fetch, transcription) are deferred,
kind-by-kind, each with its own source/rights/content-boundary review.

**9. The wall is unchanged — two indexes, one contract, not one Cypher.** The walled reference
index and the owner-scoped content index stay distinct substrates. "Chunked = on the shelf"
extends cleanly; `:ReferenceChunk` stays invisible to SearchRouter (isolation test green,
extended to assert the scoped branch is adapter-only). Unification lives in the contract + the
`to_teaching_block` framing + the shared citation renderer — **never** a merged query across the
two indexes (that would breach the wall and the privacy gate).

**10. FULL-only, fail-soft — already aligned.** Askesis is FULL-tier only (403 below MEMBER;
`services.askesis is None` in CORE); canon is likewise. On unavailable/empty/miss, the block is
`""` and the companion proceeds ungrounded — degrades to normal guidance/reflection, never
breaks. Quoted passages stay ephemeral prompt context (ADR-073 unaffected).

**11. Phasing.**
- **P1 — PS-scoped reference seam** (uniform, no weight machinery): scope arg + exact-cosine
  branch + `to_teaching_block` + Askesis wiring + shared citation block. Verify end-to-end.
- **P2 — grow the shelf** (content, not code).
- **P3 — vault-minus-private scope for Journals**: elevate `_build_context_summary` to
  owner-scoped weighted content retrieval satisfying the same contract; land the private gate +
  the weight field (uniform default). This is where the weighting foundation first pays off.
- **Later (deferred):** past-PS spaced repetition (same seam, union scope); the learner's
  own-work personal scope for Askesis (the Askesis peer of the vault); non-book source kinds.

## Consequences

**Positive.**
- One contract serves both companions and all four corpus cells; ADR-076's "reusable, not a
  Journals feature" intent is realized without a rewrite, and now provably symmetric with Askesis.
- The scoped reference branch is *more* accurate than the index where it matters (exact cosine
  over a small set), verified live before committing.
- Weighting is designed-in as a contract shape, not built speculatively — refinable with use per
  Mike's mandate, with zero unwired code in phase-1.
- Wall, owner-scoping, and zero-persistence guarantees inherited intact; the privacy gate is
  explicit and sits above weighting.

**Negative / accepted.**
- Two substrates remain (walled reference index; owner-scoped content index). Unification is at
  the contract/framing/citation layer, not one Cypher — a deliberate honesty, not a compromise.
- The adapter's reference method now holds two Cypher branches (the index cannot pre-filter).
- Phase-1 usefulness is **corpus-bound**: it lights up only where a PS cites an already-shelved
  book (today, effectively *Hypermedia Systems*). A content ramp, not a code gap.
- The vault scope (P3) depends on confirming the private-marking mechanism (VaultBridge
  allowlist / frontmatter flag) and the exact owner-scoped chunk-retrieval entry point.

## Alternatives considered

- **Keep the seam as `resource_uids`-only.** Rejected — the vault-scope reframing shows the true
  primitive is a corpus scope; hard-coding to resource lists would force a parallel path for the
  vault later. The generalized contract costs nothing now (reference slice is still just an
  optional list) and prevents the fork.
- **One literal Cypher path across the walled + owner-scoped indexes.** Rejected — breaches the
  canon wall and the privacy gate. The two indexes have opposite visibility by design; they
  share a contract, never a query.
- **Solve per-file weighting up front.** Rejected — Mike's mandate is a refinable foundation.
  Ship uniform, admit weight in the contract, tune with experience.
- **Post-filter the global index by `resource_uids`.** Rejected — silent recall loss; exact
  cosine over the scoped set is correct and affordable.
- **A separate `AskesisCanonService` / route canon sources through `CitationBundle`.** Rejected —
  forks the retrieval/citation stack the prime directive forbids.
- **Ship the personal scopes (vault / learner-own-work) in phase-1.** Deferred — private gate +
  weight machinery + owner-scoped entry point are their own slice; phase-1 proves the contract on
  the public reference corpus first.
