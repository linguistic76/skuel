# Canon — Book-as-Journaling-Companion

**Status:** **Phases 1–3 = DONE 2026-07-08** (silent voice-infusion). **Quote-and-cite
upgrade DONE 2026-07-09** — the companion now names, quotes verbatim, and cites the shelf on
the journal follow-up path (chapter/section structural anchors + Resource link), governed by
[ADR-076](../decisions/ADR-076-canon-quotation-and-citation-policy.md) /
[CANON_CITATION_DESIGN.md](../architecture/CANON_CITATION_DESIGN.md), which supersede the
original "voice-infused, not quoted" ruling. Remaining work is content (more books) and the
future rungs below (auto-summon, Askesis, clickable in-app citations).

**Core Principle:** *"A curated shelf of books that reasons alongside you as you journal — infused into the companion's voice, always walkable back to the raw."*

This is a **new surface**, split from (not an extension of) the Resources reference-library
arc (`docs/roadmap/done/resources-reference-library.md`). See **§ Relationship to the reference
library** below for why the split matters.

---

## What this is

A growing **canon** — a curated shelf of books the FOUNDER chooses — that the Journals
domain can draw on while journaling. When you reflect, relevant passages from the shelf are
retrieved and **fed into the companion's reasoning** (Stages 2 and 3), shaping its voice
without being quoted verbatim. A light **"Drawing on: *X*"** attribution tells you which
books spoke, so you can always go read them in the raw.

The first book on the shelf is *Hyper Media Systems* (`0vault/Resources/0 Hyper Media Systems.epub`).

### Design decisions (settled 2026-07-08, with Mike)

> **⚠️ Superseded 2026-07-09 — see [ADR-076](../decisions/ADR-076-canon-quotation-and-citation-policy.md)
> and [CANON_CITATION_DESIGN.md](../architecture/CANON_CITATION_DESIGN.md).** The
> "Infusion vs quotation → voice-infused, not quoted back" ruling below was a **prompt
> default over-recorded as a decision**. The companion **may quote and cite the shelf**
> (hybrid: infuse by default, quote-on-demand, always cite with a structural anchor +
> link to the raw). The two rows below are kept struck-through for history; all other rows
> in this table still stand.

| Decision | Ruling |
|---|---|
| ~~**Infusion vs quotation**~~ | ~~**Voice-infused** — passages feed the LLM's reasoning, not quoted back.~~ → **Superseded (ADR-076): quote-on-demand + cite.** |
| ~~**Attribution**~~ | ~~A **light "Drawing on: *book*" footer**~~ → **Superseded (ADR-076): a Sources block with per-quote chapter/section anchor + link to the Resource page** (still the Askesis "Sources & Evidence" footer *shape*, still "point to the raw"). |
| **Trigger** | A **dial, starting at "summoned"** (a toggle on the FOUNDER journal workspace). Architected as a request parameter so it can graduate toward automatic with use — not a hardcoded branch. |
| **Which stages** | **Stage 2 (Thought Partner) + Stage 3 (What Is Related).** Both already build `_build_context_summary`; canon retrieval is a sibling of that. |
| **Shelf scope** | The **whole shelf is always available** for retrieval. |
| **Shelf membership** | **Way A: "chunked = on the shelf."** A book joins the canon by being processed into `:ReferenceChunk` — the act of chunking *is* the act of shelving. No separate opt-in flag; membership can't drift. (A "chunked-but-benched" flag is a possible *later* add, not needed for book one.) |
| **Reusability** | Built as a **domain-agnostic capability**, not a Journals feature. `JournalService` is the *first consumer*; Askesis (or any conversational surface) can call the same retrieve-and-attribute capability later without a rewrite. The retrieval/attribution logic does **not** live inside `JournalService`. |
| **Isolation** | A separate **`:ReferenceChunk`** label, **never reachable from `SearchRouter`** — chunk dominance stays structurally impossible (see below). |
| **Tier** | **FULL only** (embeddings); fail-soft on CORE. |

---

## Why this is philosophy-safe (chunk dominance dissolved)

Tier-2 of the reference-library arc was "held lightly" because chunking books floods the
**shared curriculum index** (`:ContentChunk`, queried by `SearchRouter` for `/search`),
drowning the structural Kus/PathSteps. That fear is *entirely about a shared index*.

This surface sidesteps it by construction: book passages live in a **separate `:ReferenceChunk`
label** that **only the canon-retrieval path queries** and **`SearchRouter` never sees**. The
two vector spaces never touch, so curriculum search cannot be diluted — no matter how many
books are shelved. The raw books stay walled from curriculum ingestion; a **deliberate second
door** reads them for the canon.

And the "point to the raw" principle survives voice-infusion *because of* the attribution
footer: the passage is woven, not quoted, but the "Drawing on: *X*" line always points you
back to the essential reading. The app reasons *alongside* the book; it does not digest it
into curriculum.

## ADR-073 (journals store ZERO) — clean

- Retrieved passages are **ephemeral prompt context** (like the goal/task/habit titles and
  vault-note snippets `_build_context_summary` already injects). Nothing is persisted.
- Embedding the books persists **book content** (a product asset), not journal content.
- **No retrieval log:** which passage met which entry is never stored.
- A companion output that quotes a "Drawing on" line and leaves in a `je_out/` file is the
  user keeping their own file — consistent with ADR-073.

---

## Relationship to the reference library

This **splits** the arc; it does not extend it.

- `done/resources-reference-library.md` — **Tier-1 pointing/citations (done, #562/#564/#565/#566)**
  stays exactly as-is: a Ku/PathStep *cites* a Resource with an optional locator; the Resource
  detail page names its source and shows who cites it. Pointers, no bodies.
- **This doc** — the canon companion is a *different surface, audience, and access path* that
  merely **shares the chunking mechanism**. It replaces the old, philosophy-uncomfortable
  reason to build Tier-2 ("passage search in the library") with a better one ("a book reasons
  with you as you journal"). Tier-2-as-library-search may now simply never be built.

---

## Phasing

### Phase 1 — Canon text prep ✅ DONE (2026-07-08)

- `scripts/clean_reference_book.py` — rerunnable `EPUB → pandoc → clean Markdown` CLI.
  Deterministic (no LLM). AST lua-filter unwraps `<div>`/`<span>`, drops images and stray raw
  HTML, unwraps `<figure>`; `gfm-raw_html` output degrades leftover styling to text;
  `--wrap=none`. HTML shown *as content* (code fences, inline code) is preserved — safe for
  technical books that teach markup.
- Produced `0vault/Resources/0 Hyper Media Systems.md` (102,937 words, 544 code fences, 0
  genuine cruft). Beats the parked datalab extraction (`Hyper-Media-Systems/`, ~20% content
  dropped, headings flattened) on hierarchy, completeness, and code fences.
- **Adding a future book to the canon = run the script on its EPUB**, then Phase 2 ingest.

### Phase 2 — Canon ingest → `:ReferenceChunk` ✅ DONE (2026-07-08)

- A **separate ingest** that intentionally reads the walled `0vault/Resources/` `.md` files,
  chunks them (reuse #560 per-domain chunking params, tuned larger for prose —
  `REFERENCE_CHUNKING_PARAMS`, `100/1000/150`), embeds via the existing post-persist embedding
  worker (ADR-074) through a `ReferenceChunkEmbeddingRequested` event, and writes
  `:ReferenceChunk` nodes linked to their `Resource` via `HAS_REFERENCE_CHUNK`.
- **`:ReferenceChunk` is invisible to `SearchRouter`** — distinct from `:ContentChunk`, its own
  vector index `referencechunk_embedding_idx`, queried only by the (future) canon-retrieval
  capability. A static isolation test (`tests/unit/adapters/test_reference_chunk_isolation.py`)
  freezes the invariant.
- Membership follows automatically: a `Resource` is "on the shelf" iff it has `:ReferenceChunk`
  nodes.
- **Delivered:** `Neo4jReferenceChunkAdapter` (all Cypher), `ReferenceIngestionService`
  (core, `Result[T]`), admin CLI `scripts/ingest_canon_book.py`. FULL tier embeds; CORE writes
  chunks only (fail-soft).

### Phase 3 — Journal retrieval wiring ✅ DONE (2026-07-08)

- **Domain-agnostic capability** shipped: `core/services/canon/` — `CanonRetrievalService`
  retrieves top canon passages for a query and returns a `CanonContext` (passages + the books
  they came from). Reads the walled `referencechunk_embedding_idx` via
  `Neo4jReferenceChunkAdapter.search_reference_chunks` behind the
  `ReferenceChunkSearchOperations` port — SearchRouter never sees it (isolation test green).
  Journals is the first consumer; **Askesis-ready** (nothing journal-specific in the service).
- Wired into `JournalService` Stage 2 + Stage 3 alongside `_build_context_summary`, gated by the
  summon dial. The dial is one seam — `_maybe_summon_canon` — so graduating it from a request
  checkbox to automatic (prefs/heuristics) is a one-method change, not a call-site sweep.
  Passages voice-infuse the system prompt (`CanonContext.to_prompt_block()`, "not a source to
  quote"); the visible output gets a light `*Drawing on:* *book*` footer
  (`attribution_footer()`).
- FULL-tier only; fail-soft to a normal canon-free journal on CORE or any retrieval miss.
  ADR-073 clean — passages are ephemeral prompt context, nothing persisted.
- File path parity: `run_compiled` (the FOUNDER upload/batch compile, which has no
  review gate) takes the same `summon_canon` flag, threaded to both stages. A
  FOUNDER-only "Summon the canon shelf" checkbox rides the upload form
  (`render_upload_form` / `render_right_panel`), Alpine-shown (and enabled) only
  for a single-file `instructions_only` upload — the sole upload shape that
  reaches `run_compiled`. A multi-file/folder upload takes the batch path
  (`JournalBatchService.run_batch_over_dir`, no canon), so the toggle hides + disables itself there
  rather than submit an ignored flag. Default off — the dial stays explicit.
- *Dial shape update (2026-08-21):* on the discussion path (`/journals/start`) the dial has
  since evolved past the single coarse checkbox — the landing panel offers **per-book
  checkboxes** that scope the draw (`canon_book_uids`, with
  `summon_canon = bool(canon_book_uids)` derived in `journals_routes.py`) plus a sibling
  `summon_vault` dial. The upload door (`/journals/upload`) still takes the two coarse
  booleans as described above. The dial remains explicit on both doors — auto-summon is
  still the open rung.

### Future rungs (not scheduled)

- **Auto-summon** — replace the checkbox with prefs/heuristics inside `_maybe_summon_canon`.
- ~~**Askesis** — call `CanonRetrievalService` from the Askesis path~~ → **✅ SHIPPED 2026-07-11
  (ADR-077 Phase 1, #612 + #613):** the guided pipeline retrieves PS-scoped readings
  (`retrieve(resource_uids=…)`), grounds guidance via the mode-aware
  `CanonContext.to_teaching_block()`, and renders sources through the shared
  `ui/canon/CanonSourcesBlock`. Lights up wherever a PS cites a shelved book —
  growing that overlap is content authoring (the "More books" rung below).
- **More books** — content authoring only (Phase 1 EPUB→pandoc→clean → Phase 2 ingest).
- **"What's on the shelf" view** — ✅ **SHIPPED** (rung struck 2026-08-21; it landed
  under a different name, which is why its own grep missed it): the emergent-shelf read
  exists as `list_shelved_books()` on `Neo4jReferenceChunkAdapter`
  (`neo4j_reference_chunk_adapter.py:301`, keeps the wall), exposed via
  `canon_retrieval_service.py`, and surfaced as the per-book picker on the journals
  landing (`ui/journals/chat_page.py`). An admin/canon page linking to Resource detail
  remains possible but is no longer the gap this rung described.
- **Tune retrieval** — calibrate `CANON_RETRIEVAL_MIN_SCORE` (0.3) / `CANON_RETRIEVAL_LIMIT`
  (4) from real draws. `CanonRetrievalService.retrieve()` now logs each draw
  (count · books · score range · min_score) — that log is the measurement input;
  nothing to change until there's data to read.

---

## Key references

- Journals: `core/services/journal/journal_service.py` (Stages 2/3 + `_build_context_summary`),
  `.claude/skills/journals`, ADR-073 (`docs/decisions/ADR-073-journals-zero-persistence-vault-memory.md`).
- Attribution pattern to reuse: `core/services/askesis_citation_service.py` (the "Sources &
  Evidence" footer shape), `core/services/askesis/context_retriever.py` (passage retrieval).
- Vector search seam: `core/services/neo4j_vector_search_service.py`
  (`find_similar_chunks_by_text`), `core/orchestrator/search_router.py`
  (`retrieve_scoped_chunks`), `core/services/ingestion/config.py` (chunk configs, the wall).
- The wall: `services_bootstrap/compose.py` (`excluded_dirs={... "Resources"}`).
- Reference-library arc this splits from: `docs/roadmap/done/resources-reference-library.md`.
