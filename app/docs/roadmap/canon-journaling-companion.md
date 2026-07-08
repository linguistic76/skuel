# Canon — Book-as-Journaling-Companion

**Status:** **Phase 1 (canon text prep) = DONE 2026-07-08.** Phases 2–3 = designed, not yet built.

**Core Principle:** *"A curated shelf of books that reasons alongside you as you journal — infused into the companion's voice, always walkable back to the raw."*

This is a **new surface**, split from (not an extension of) the Resources reference-library
arc (`docs/roadmap/resources-reference-library.md`). See **§ Relationship to the reference
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

| Decision | Ruling |
|---|---|
| **Infusion vs quotation** | **Voice-infused** — passages feed the LLM's reasoning, not quoted back. |
| **Attribution** | A **light "Drawing on: *book*" footer** — the *shape* of the Askesis "Sources & Evidence" footer, but sourced from retrieved passages, not graph edges. Keeps infusion honest with "point to the raw." |
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

- `resources-reference-library.md` — **Tier-1 pointing/citations (done, #562/#564/#565/#566)**
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

### Phase 2 — Canon ingest → `:ReferenceChunk` (designed, not built)

- A **separate ingest** that intentionally reads the walled `0vault/Resources/` `.md` files,
  chunks them (reuse #560 per-domain chunking params, tuned larger for prose), embeds via the
  existing post-persist embedding worker (ADR-074), and writes `:ReferenceChunk` nodes linked
  to their `Resource` entity.
- **`:ReferenceChunk` must be invisible to `SearchRouter`** — distinct from `:ContentChunk`,
  its own vector index, queried only by the canon-retrieval capability.
- Membership follows automatically: a `Resource` is "on the shelf" iff it has `:ReferenceChunk`
  nodes.

### Phase 3 — Journal retrieval wiring (designed, not built)

- A **domain-agnostic capability** — retrieve top passages from the canon for a query, and
  return an attribution of what it drew on. Journals is the first consumer; Askesis-ready.
- Wire into `JournalService` Stage 2 + Stage 3 alongside `_build_context_summary`, gated by
  the summon dial. Append the light "Drawing on: *book*" attribution to the stage output.
- FULL-tier only; fail-soft on CORE.

---

## Key references

- Journals: `core/services/journal/journal_service.py` (Stages 2/3 + `_build_context_summary`),
  `.claude/skills/journals`, ADR-073 (`docs/decisions/ADR-073-journals-zero-persistence-vault-memory.md`).
- Attribution pattern to reuse: `core/services/askesis_citation_service.py` (the "Sources &
  Evidence" footer shape), `core/services/askesis/context_retriever.py` (passage retrieval).
- Vector search seam: `core/services/neo4j_vector_search_service.py`
  (`find_similar_chunks_by_text`), `core/models/search/search_router.py`
  (`retrieve_scoped_chunks`), `core/services/ingestion/config.py` (chunk configs, the wall).
- The wall: `services_bootstrap/compose.py` (`excluded_dirs={... "Resources"}`).
- Reference-library arc this splits from: `docs/roadmap/resources-reference-library.md`.
