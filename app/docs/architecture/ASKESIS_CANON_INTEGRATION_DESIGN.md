# Askesis × Canon — PS-Scoped Readings in Socratic Guidance

**Status:** Approved design — Phase 1 shipped.
PR-A (scoped retrieval + teaching framing) shipped 2026-07-11 (#612); PR-B (Askesis wiring + citations) shipped 2026-07-11 (#613).
**Companion ADR:** [ADR-077](../decisions/ADR-077-askesis-canon-scoped-retrieval.md)
**Builds on:** [CANON_CITATION_DESIGN.md](CANON_CITATION_DESIGN.md) · [ADR-076](../decisions/ADR-076-canon-quotation-and-citation-policy.md) · [ASKESIS_SOCRATIC_ARCHITECTURE.md](ASKESIS_SOCRATIC_ARCHITECTURE.md)
**Roadmap:** [`docs/roadmap/canon-journaling-companion.md`](../roadmap/canon-journaling-companion.md) — "Future rungs → Askesis"
**Date:** 2026-07-09

> **Purpose.** The canon quote-and-cite capability (`core/services/canon/`, PR #572 / ADR-076)
> was built domain-agnostic so Askesis could call it "without a rewrite." This doc decides
> *exactly how* — the one retrieval seam that lets journal (whole shelf) and Askesis
> (PS-scoped) share a single path, the teaching-time prompt framing, the citation-surface
> DRY resolution, and the honest bound on what "chunk PS Resources too" can cover in phase 1.
> **Prime directive: reuse `core/services/canon/` and the reference-chunk pipeline; do NOT
> fork a parallel retrieval/citation stack.**

---

## 1. The problem, precisely

Askesis is a **Socratic companion** anchored to a learner's active PathStep (PS). It already
loads the PS's cited Resources — `ContextRetriever.load_ps_bundle()` traverses
`(PathStep/Ku)-[:CITES_RESOURCE]->(Resource)` and hangs the results on
`PsBundle.resources`, surfaced to the LLM as **compact metadata summaries** in
`PsBundle.curriculum_context_text` ("## Referenced Resources — *title* — *150-char blurb*").

So Askesis knows *that* a PS cites *Hypermedia Systems*. It cannot draw on **what the book
actually says**. Meanwhile the canon companion can quote and cite that exact book verbatim —
but only from the journal follow-up path, and only against the **whole shelf**.

**The requirement:** while guiding a learner on their focus PS, Askesis should weave the
**actual passages** of that PS's readings into its Socratic questions and **cite them**,
reasoning *with* the reading — drawing **only** on Resources reachable from the focus PS,
never the whole shelf.

### Mike's locked decisions (the frame this doc designs to)

1. **Scope = PS-connected only.** Draw only on Resources reachable from the focus PS — its
   own `CITES_RESOURCE` **and** its Kus' Resources (`PS-[:USES_KU]->Ku-[:CITES_RESOURCE]->Resource`).
   Never the whole shelf. It is **not** an explicit "talk to the book" mode.
2. **Interaction = infuse-and-cite.** Weave the reading's passages into the Socratic guidance
   and cite them — reasoning *with* the reading, not a separate quote-on-demand surface.
3. **Quotability = chunk PS Resources too.** Extend chunking so PS/Ku-cited Resources become
   quotable, not just the FOUNDER shelf books.
4. **Per-source importance weighting is a refinable foundation.** How much each source counts is
   tuned with use and experience — not solved up front. The design must *admit* weight, not
   hard-code equal footing.

---

## 1a. The broader frame — scope is the unifying primitive (2026-07-09 sharpening)

The peer of Askesis's **PathStep** is not a single journal entry — it is the user's **vault,
minus what is marked private** (the VaultBridge personal vault, ADR-070). Both are a **scope**: a
bounded region that defines *what the companion may ground its response in*. The PS scopes a
region of the **curriculum** graph; the vault-minus-private scopes a region of the user's
**personal** files. A journal entry is just the *anchor* note within the vault scope, exactly as
the PS is the anchor within its curriculum scope.

So each companion grounds in **two scoped corpora** — one public, one personal:

| | **Public corpus** (freely cited) | **Personal corpus** (owner-scoped, private-gated) |
|---|---|---|
| **Journals** | canon shelf (`:ReferenceChunk`, walled) | the user's **vault-minus-private** (`:ContentChunk`/knowledge) |
| **Askesis** | PS curriculum + PS-cited Resources (`:ContentChunk` + `:ReferenceChunk`) | the learner's **own work on the PS** (UserEntries, owner-scoped) |

The retrieval *operation* is identical across all four cells — **resolve a scope → rank by
relevance × importance → infuse-and-cite.** What differs is the **substrate + visibility**: the
walled reference index (public, invisible to SearchRouter) vs. the main content index
(owner-scoped via `SearchVisibility`, private-gated). That distinction is load-bearing.

**Two axes fall out, and they must not be conflated:**
- **Privacy = a hard gate**, not a weight. Private-marked units are excluded outright — never
  retrieved, never cited (ADR-073, owner-scoping #512–#514). Applies whenever the personal
  corpus is in scope.
- **Importance = a soft weight** over the non-private remainder: per-unit, **uniform default**,
  named signals to grow into (recency, pinned/`#important`/MOC membership, link-centrality,
  note-type). Ranking = f(similarity, weight). The **foundation** is to admit weight in the
  contract so refinement is a weight-function change, not a re-plumb — **not** to build the
  weight machinery before the scope that needs it (phase-1's reference slice stays uniform).

**Consequence for this doc.** The seam below is the *first realization* of a general **corpus-scope
contract** (`retrieve(query, *, scope, …)`), spelled for the reference shelf as an optional
`resource_uids`. The vault-minus-private scope is the sibling realization over the existing
owner-scoped content path — same contract, same framing, same citation renderer, **different
index**. Unification lives at the contract/framing/citation layer, never a merged query across
the walled and owner-scoped indexes. See [ADR-077](../decisions/ADR-077-askesis-canon-scoped-retrieval.md).

---

## 2. What is already true (verified, so we don't reinvent or misdiagnose)

- **The retrieval capability is domain-agnostic and callable.** `CanonRetrievalService.retrieve(query_text, *, limit, min_score) -> Result[CanonContext]` (`core/services/canon/canon_retrieval_service.py:49`) embeds the query and reads the walled index behind the `ReferenceChunkSearchOperations` port. It takes **no scope argument today** — it always searches the whole shelf.
- **The read is the only door to the wall.** `Neo4jReferenceChunkAdapter.search_reference_chunks(query_embedding, limit, threshold)` (`:168`) is the *sole* reader of `referencechunk_embedding_idx`. Isolation is frozen by `tests/unit/adapters/test_reference_chunk_isolation.py` (SearchRouter + `VectorSearchBackend` must never name the index).
- **Chunks carry their own embedding vector.** `ReferenceChunk.embedding` is set on the node by the shared embedding worker (verified live: `resource.hypermedia-systems` = 105 chunks, **105 embedded**). This is what makes a *scoped* exact-cosine query possible without the global index.
- **Askesis already has the scope in hand.** `PsBundle.resources: tuple[Resource, ...]` is built per-question from the CITES_RESOURCE traversal. The set of `resource.uid` there **is** the retrieval scope — no new traversal needed for phase 1.
- **Askesis is FULL-tier only.** `services.askesis is None` in CORE; `/api/askesis/ask` returns 403 below MEMBER (ADR-043). Canon is likewise FULL-only, fail-soft. The tiers already agree.
- **Only one book is on the shelf.** `resource.hypermedia-systems`. "Chunk PS Resources too" is where new content acquisition is required — see §6.

---

## 3. Reuse map — shared as-is vs. thin new seam

| Need | Reuse **as-is** | Thin **new seam** |
|---|---|---|
| Query embedding + Result plumbing | `CanonRetrievalService.retrieve()` | add an **optional `resource_uids` scope arg** (§4) |
| Walled read | `Neo4jReferenceChunkAdapter` + `referencechunk_embedding_idx` | add **one scoped branch** to `search_reference_chunks` (§4) |
| Port contract | `ReferenceChunkSearchOperations` (`core/ports/chunk_protocols.py:90`) | widen its one method signature with `resource_uids` |
| Passage value objects | `CanonPassage`, `CanonContext`, `CanonSource` (`canon_models.py`) | **one new render method** `to_teaching_block()` (§5) — no new value object |
| Faithfulness contract | §4 of CANON_CITATION_DESIGN (quote-only-retrieved, cite-only-supplied, refuse gracefully) | reused verbatim inside `to_teaching_block()` |
| Structured citations | `CanonContext.sources() -> tuple[CanonSource, ...]` + the clickable Sources renderer (#572) | render it as a **distinct Askesis sub-block** (§7) |
| PS-scope resolution | `PsBundle.resources` (already loaded per question) | read `.uid`s — no new query in phase 1 |
| Chunking a book | `ReferenceIngestionService.ingest_book(resource_uid, markdown_text)` + `scripts/ingest_canon_book.py` | unchanged; the gap is **content acquisition** (§6), not the pipeline |

**Nothing forks.** One retrieval service, one adapter method, one value-object family, one
citation renderer — extended, not duplicated.

---

## 4. The ONE scoped-retrieval seam (the crux)

Journal wants the **whole shelf**; Askesis wants **only the focus PS's Resources**. These must
be one code path, or the capability is no longer "shelf-and-scope-agnostic."

### 4.1 The seam

Widen the single port method with an **optional** scope. `None` = today's behaviour, exactly.

```python
# core/ports/chunk_protocols.py — ReferenceChunkSearchOperations
async def search_reference_chunks(
    self,
    query_embedding: list[float],
    limit: int,
    threshold: float,
    resource_uids: list[str] | None = None,   # NEW — None = whole shelf
) -> list[ReferenceChunkHit]: ...
```

```python
# core/services/canon/canon_retrieval_service.py — retrieve()
async def retrieve(
    self,
    query_text: str,
    *,
    limit: int = CANON_RETRIEVAL_LIMIT,
    min_score: float = CANON_RETRIEVAL_MIN_SCORE,
    resource_uids: list[str] | None = None,   # NEW — passthrough to the adapter
) -> Result[CanonContext]: ...
```

Journal callers pass nothing (whole shelf). Askesis passes
`resource_uids=[r.uid for r in ps_bundle.resources]` (PS scope). **One method, two shelves.**

### 4.2 Why the adapter needs *two* Cypher branches — and why the scoped one is better

Neo4j 5.26's `db.index.vector.queryNodes` (the current whole-shelf query, `:200`) has **no
metadata pre-filter** — you cannot ask the index for "nearest neighbours *among these
resources*." Post-filtering its top-K by `resource_uids` silently loses recall: if a PS's
book is a small slice of a large shelf, its best passages may never enter the candidate pool.

The fix is not a bigger candidate pool — it is to **not use the global index for the scoped
case at all**. Because every `:ReferenceChunk` stores its own `embedding`, a scoped query can
score **every chunk in the scoped set exactly** with `vector.similarity.cosine()`:

```cypher
// SCOPED branch (resource_uids provided) — exact, no index-recall loss
MATCH (r:Resource)-[rel:HAS_REFERENCE_CHUNK]->(chunk:ReferenceChunk)
WHERE r.uid IN $resource_uids AND chunk.embedding IS NOT NULL
WITH chunk, r, rel, vector.similarity.cosine(chunk.embedding, $query_embedding) AS score
WHERE score >= $threshold
RETURN chunk.uid AS chunk_uid, chunk.text AS text, chunk.context_window AS context_window,
       chunk.heading AS heading, chunk.section_path AS section_path,
       rel.sequence AS sequence, score AS similarity_score,
       r.uid AS resource_uid, r.title AS book_title
ORDER BY score DESC
LIMIT $limit
```

**Verified live against the shelf** (2026-07-09): this query runs on Neo4j 5.26, filters by
`resource_uid`, returns correct anchors (heading/section_path/sequence), and a seed chunk
scored against itself returns `1.0` (sanity check). For a PS's handful of books (hundreds of
chunks, not the whole corpus) a full scan is both **exact** and **fast** — strictly better
recall than the index would give, precisely where scoping bites.

The whole-shelf branch (`resource_uids is None`) keeps the existing `queryNodes` path —
correct at corpus scale where a full scan would not be. The projection is identical, so both
branches return the same `ReferenceChunkHit` shape and everything downstream is unchanged.

**Isolation stays green.** The scoped branch still lives *only* in `Neo4jReferenceChunkAdapter`
and never names `referencechunk_embedding_idx` in SearchRouter or `VectorSearchBackend`. The
existing isolation test continues to pass unchanged; we add an assertion that the scoped
branch is reachable only through this adapter.

---

## 5. Prompt framing — a third `CanonContext` method, not a third value object

The two existing renderers on `CanonContext` don't fit teaching-time infuse-and-cite:

- `to_prompt_block()` — silent infusion, **explicitly forbids** naming/quoting/citing. Violates decision #2 (we must cite).
- `to_discussion_block()` — "you MAY discuss them openly… quote when the user wants to see." This is a *discussion* stance (the journal "talk to the book" surface). Askesis is **not** that — it must keep the Socratic method: draw on the reading to *ground a question*, not hand the learner the book's answer because the book states it.

**Recommendation: add `CanonContext.to_teaching_block()`** — reusing `CanonPassage` /
`CanonSource` and the §4-faithfulness contract verbatim, but with a Socratic framing:

> ## Readings for This Step
> These passages are from the readings this learning step cites. Ground your Socratic
> guidance in them: let a passage sharpen the question you ask, the analogy you offer, the
> distinction you draw. When you lean on a specific idea, name its book and cite the location
> shown. Quote **verbatim and sparingly** — only the text below, never from memory — when the
> exact words matter. **Do not surrender the method**: a passage stating the answer is a
> reason to ask a better question, not to recite it. If the readings hold nothing on the
> learner's point, guide from the curriculum and say so — never invent a passage, chapter, or
> section.

This honours "reuse `CanonContext` — do not build a parallel value object." It is **one new
method** on the existing frozen dataclass, alongside `to_prompt_block` / `to_discussion_block`.

### Where it injects into the Socratic prompt

`ResponseGenerator.build_guided_system_prompt(guidance, ps_bundle, user_context) -> str`
(`response_generator.py:195`) dispatches to mode-specific builders that render templates via
`PROMPT_REGISTRY`. The readings block is **orthogonal to GuidanceMode** — it grounds
*whatever* Socratic move the mode chose. So:

1. `QueryProcessor` retrieves canon **after** `load_ps_bundle` (it needs the PS's `resource_uids`) and **on the user's question** (mirrors the journal keying retrieval on `user_reply`, not the raw entry).
2. It passes the resulting `CanonContext` into `build_guided_system_prompt`, which **appends `canon_context.to_teaching_block()`** to the assembled system prompt (empty string when no passages — the existing `has_passages` gate).

This keeps `ResponseGenerator` the single prompt-assembly point and touches no template files.

**As shipped (PR-B #613, Codex P2):** the block is **mode-aware**, not fully uniform.
SOCRATIC / EXPLORATORY / ENCOURAGING keep the "do not surrender the method" paragraph;
DIRECT mode — which promises answers, including the user's explicit mode override — gets a
direct-answer grounding paragraph instead (`to_teaching_block(preserve_method=False)`), so
the readings ground the answer rather than contradict the mode. The faithfulness contract
is identical in both framings.

---

## 6. The content-source gap — what "chunk PS Resources too" can actually cover

This is the honest bound on phase 1. To chunk a Resource you need its **full text**. The shelf
got text from a FOUNDER-placed **EPUB → cleaned `.md`** in `0vault/Resources/`, ingested by
`ReferenceIngestionService.ingest_book(resource_uid, markdown_text)`. For arbitrary PS-cited
Resources, the text may not exist anywhere in SKUEL.

`Resource` (`core/models/resource/resource.py`) carries **metadata + a ~200-word annotation**,
never the work's body: `media_type` (`book|talk|film|music|article|podcast`), `source_url`,
`author`, `publisher`, `isbn`. The reference-library UI (#562–#566) surfaces the annotation and
an "open source →" link — it deliberately does **not** hold full text.

| Resource kind | Full text obtainable? | Path to chunkable |
|---|---|---|
| **Book (EPUB/PDF the FOUNDER holds)** | ✅ yes | Exactly today's pipeline: `clean_reference_book.py` → `ingest_canon_book.py --resource-uid …` |
| **Book (no file on hand)** | ⚠️ acquisition-gated | Needs a licensed/owned source file first; then identical pipeline |
| **Long-form article (open web)** | ⚠️ maybe | Needs a fetch-and-clean step (new tooling); licensing/robots care |
| **Paywalled article / paper** | ❌ no | No lawful full text to hold |
| **Talk / film / podcast / music** | ❌ not as text | Would require transcription (Deepgram exists, but that's a separate pipeline + rights question) |
| **Bare URL** | ❌ no | Pointer only, by design |

**Consequence for phasing (blunt):** phase 1 can only draw on PS Resources that are **already
shelved** — i.e., books whose cleaned `.md` a FOUNDER has ingested. Today that is a set of
**one** (*Hypermedia Systems*), and only where a PS/Ku actually cites it. "Chunk PS Resources
too" is therefore **not a code feature you finish in phase 1** — it is a *content-acquisition
capability* that grows book-by-book through the existing (unchanged) ingest pipeline. The
retrieval/citation seam (§4–§5, §7) is what phase 1 delivers; the corpus is what makes it
progressively useful. Expanding chunking to non-book kinds (article fetcher, transcription) is
explicitly a **later, kind-by-kind** effort, each with its own source-acquisition + cleaning +
content↔repo-boundary questions (`0vault/Resources/` is content-vault, never committed).

---

## 7. Citation-surface DRY — one renderer, a distinct block

Askesis already appends a **"Sources & Evidence"** footer: `AskesisCitationService` →
`CitationBundle.format_for_askesis()` renders **prerequisite-knowledge provenance**
(REQUIRES_KNOWLEDGE chains, evidence counts) — provenance of the *curriculum graph*.

Canon `sources()` produces **reading provenance** — which book, which in-book locations. These
are **different kinds of source**, and conflating them would muddy both. The resolution:

- **Keep them as two blocks, not one.** "Sources & Evidence" (why these concepts are
  prerequisites) stays; a **distinct "Drawing on the Readings"** block (which book passages
  grounded the guidance) is appended alongside it.
- **But share one renderer.** The "Drawing on the Readings" block is rendered from
  `CanonContext.sources()` using the **same clickable Sources renderer built for the journal
  in #572** (`CanonSource` → `<a href="/library/resources/get?uid=…">` per book + its in-book
  locators). We do **not** route canon sources through `CitationBundle`, and we do **not**
  build a second canon renderer for Askesis.

So: **two provenance blocks (they mean different things), one renderer per provenance type
(no duplication).** The canon Sources renderer is lifted to a shared UI helper both the
journal `FollowUpFragment` and the Askesis response call — the single fork-avoidance point for
the citation surface.

---

## 8. The wall & membership — confirmed clean

A PS-cited book chunked into `:ReferenceChunk` stays invisible to SearchRouter — **correct and
unchanged.** "Chunked = on the shelf" extends cleanly to PS-cited Resources: a PS-cited book
that has been chunked is simply another shelf book that *also* has CITES_RESOURCE edges. There
is **no new membership concept** — shelf membership stays emergent (`HAS_REFERENCE_CHUNK`
exists), and CITES_RESOURCE is an orthogonal curriculum edge. What restricts Askesis to the
PS's readings is the **scope argument** (§4), not the wall. The isolation test stays green;
we extend it to assert the scoped branch is also adapter-only.

One subtlety worth stating: a Resource can be **cited but not shelved** (metadata only, no
chunks) or **shelved but not PS-cited** (a FOUNDER shelf book no PS references). Askesis draws
on the **intersection**: PS-cited **and** shelved. `search_reference_chunks(resource_uids=…)`
yields nothing for the cited-but-unshelved ones (no chunks to match) — the correct, silent
degradation. No guard needed.

---

## 9. Where it slots — current PS first, spaced-repetition later

- **Phase 1 — current-PS Socratic guidance.** Retrieval scoped to the *active* PS's Resources
  (`PsBundle.resources`), injected into the live guided prompt. This is the natural home:
  Askesis is already anchored to the focus PS, the scope is already loaded, the seam is thin.
- **Later — past-PS spaced repetition.** Drawing on a *prior* PS's readings during review is
  valuable but needs (a) a signal for *which* PS is under review, and (b) a wider, unioned
  scope across prior PSs — more scope-resolution machinery and a different trigger. Recommend
  **deferring** it to its own phase once phase 1 proves the teaching-block framing lands. It
  reuses the exact same seam (§4) with a different `resource_uids` set — no new retrieval path.

---

## 10. Tier — FULL-only, fail-soft, already aligned

Mirror canon exactly, and it's essentially free: Askesis doesn't run on CORE at all (403
below MEMBER; `services.askesis is None`). If canon retrieval returns `Errors.unavailable`
(CORE) or an empty `CanonContext` (no passages / miss / read error — the adapter fails open),
Askesis simply proceeds with a **canon-free** system prompt (`to_teaching_block()` returns
`""`). A readings miss degrades guidance to normal Socratic guidance, never breaks it —
identical to the journal's fail-soft contract.

---

## 11. Phased plan (for review — no code until approved)

**Phase 1 — the scoped seam + teaching framing (current-PS).**
- **1a. Scope the retrieval (one seam).** Add optional `resource_uids` to
  `ReferenceChunkSearchOperations.search_reference_chunks`, the adapter (new exact-cosine
  scoped branch, §4.2), and `CanonRetrievalService.retrieve`. Journal callers unchanged.
- **1b. Teaching framing.** Add `CanonContext.to_teaching_block()` (§5) — reuses passages +
  faithfulness contract; Socratic-stance instruction.
- **1c. Askesis wiring.** In `QueryProcessor`, after `load_ps_bundle`, retrieve canon on the
  **user's question** scoped to `[r.uid for r in ps_bundle.resources]`; pass `CanonContext`
  into `build_guided_system_prompt`, which appends `to_teaching_block()`. FULL-only, fail-soft.
- **1d. Citation surface.** Lift the #572 canon Sources renderer to a shared UI helper; render
  a distinct **"Drawing on the Readings"** block on the Askesis response alongside
  "Sources & Evidence" (§7).
- **1e. Verification.** Unit: scoped branch returns only in-scope chunks + correct anchors;
  `to_teaching_block` quotes only provided passages, keeps Socratic stance, empty when no
  passages; isolation test green + extended for the scoped branch. Runtime (headless CDP as a
  FULL-tier learner on a PS that cites *Hypermedia Systems*): guidance grounds a question in a
  real passage, cites Ch./section, links to the Resource page, refuses to invent; a PS that
  cites nothing shelved degrades silently to normal guidance.

**Phase 2 — grow the shelf (content, not code).** Each new PS-cited **book** the FOUNDER can
source: `clean_reference_book.py` → `ingest_canon_book.py --resource-uid …`. Pure content
authoring on the unchanged pipeline; makes phase 1 progressively useful. Track which PS-cited
Resources are shelvable vs. pointer-only.

**Phase 3 — vault-minus-private scope for Journals (the sibling realization).** SHIPPED
2026-07-12 (ADR-077 amendment). The Journals
personal cell of the 2×2 is realized:

- **Substrate:** knowledge-pipeline UserEntries are chunked at the ingest door
  (`_chunk_entity_content`, additive — the body stays on the entity); `private: true`
  frontmatter → never embedded/chunked at all + hard WHERE in every retrieval Cypher;
  flip retracts on the next sync. Backfill via `./dev vault-sync --force`.
- **Retrieval shape:** `CanonRetrievalService.retrieve_vault(query_text, user_uid, *, limit,
  min_score)` — the sibling of `retrieve` over the OTHER port
  (`VectorSearchBackendOperations.semantic_search_chunks(owner_uid=…, viewer_uid=…,
  parent_filters={"pipeline": "knowledge"})`): OWNS-edge owner scope +
  `coalesce(parent.private,false)=false` in the one content-index Cypher, on top of the
  audience clause every chunk query carries (`viewer_uid` — ADR-085 G8, 2026-08-30; the
  vault scope narrows the audience, it does not replace it). There is no unscoped chunk
  query any more: a viewer-less call reads published curriculum only.
- **Contract:** the same `CanonPassage`/`CanonContext` family with a `SourceKind` discriminator
  (VAULT reinterprets `book_title` := note title, `resource_uid` := entry uid; `vault_path` is
  the locator); `weight: float = 1.0` landed (uniform, contract letter). Citations link to the
  owner-verified `/gradebook/{uid}` via the shared `CanonSourcesBlock` (kind-aware).
- **Dial:** second independent FOUNDER toggle `summon_vault` (Stages 2/3 absorb; follow-up may
  name/quote; compile threads both). When on, the grounded block **replaces** the shallow
  `_build_context_summary` note snippets (de-dup); off → byte-identical prior behavior.

**Later (deferred).**
- **Past-PS spaced repetition.** Union-scope across prior PSs during review (§9). Same seam,
  different scope, new trigger.
- **The learner's own-work personal scope for Askesis** — the Askesis peer of the vault: draw
  on and cite the learner's *own past work* on the PS (owner-scoped UserEntries), the personal
  half of the 2×2 (§1a).
- **Non-book source kinds** — article fetch-and-clean; transcript ingestion (Deepgram). Each its
  own source-acquisition + cleaning + rights + content-boundary review before any chunking.

---

## 12. Design principle recorded here

**One retrieval capability, genuinely scope-agnostic — unified at the contract, not the index.**
Every grounding surface calls one **corpus-scope contract** (`retrieve(query, *, scope, …)`):
journal (whole shelf), Askesis (PS-scoped), and the vault-minus-private personal corpus
(`retrieve_vault`, shipped P3).
For the reference shelf the difference is a single optional `resource_uids` argument and which
Cypher branch runs inside the one adapter; the vault scope is the same contract over the existing
owner-scoped content path. The unification lives in the **contract + the `to_teaching_block`
framing + the shared citation renderer** — **never** a merged query across the walled reference
index and the owner-scoped content index (that would breach the wall and the privacy gate).
Privacy is a gate above weighting; weighting is admitted by the contract and refined with use.
If a second retrieval path, a parallel value object, or a duplicate citation renderer appears,
the design has failed its prime directive. Reuse the stack; extend at exactly one seam per concern.
