---
updated: 2026-07-09
---

# Canon Citation & Discussion — Design Choices

**Status:** Design / decision-support (Deliverable 1). Implementation pending review.
**Companion ADR:** [ADR-076](../decisions/ADR-076-canon-quotation-and-citation-policy.md)
**Roadmap:** [`docs/roadmap/canon-journaling-companion.md`](../roadmap/canon-journaling-companion.md)
**Date:** 2026-07-09

> **Purpose.** This doc exists so the design choices are legible *before* they are built —
> the options, their trade-offs, and a recommended best-practice path for each. It is the
> foundation for a "chat with the book" capability that has to work *well*, because a
> product like this is chosen (or abandoned) on whether it actually does what it promises.

---

## 1. The problem, precisely

The FOUNDER journal companion can draw on a curated **canon shelf** of books (first book:
*Hypermedia Systems*). Asked to *discuss* the book, it answers **"I haven't read the book
directly"** and shows no citation. That is not a bug in retrieval — it is the shipped
design working as written: passages were injected as invisible "background you have
absorbed," with an explicit instruction to **never quote, name, or cite** them.

**The requirement is the inverse:** name the book, quote its exact words, and point to
where those words live — verifiably. This doc decides *how* to do that well.

### What is already true (so we don't reinvent or misdiagnose)
- **Data is healthy.** 105 `:ReferenceChunk` nodes for *Hypermedia Systems*, all embedded;
  vector index `referencechunk_embedding_idx` ONLINE; `INTELLIGENCE_TIER=full`.
- **Exact quotes already work at the data layer.** The full passage `text` is stored and
  returned verbatim by `search_reference_chunks()`. Only the *prompt* forbids quoting.
- **The "no quote" rule is soft.** It lives in one prompt string
  (`core/services/canon/canon_models.py` → `to_prompt_block`) and one test — not in any
  ADR, schema, or data constraint. Reversible by design.
- **The path the user tested (journal follow-up) has no canon wiring at all** —
  `run_follow_up` never retrieves. A plain gap, independent of the quotation policy.

---

## 2. Choice A — Quotation policy

**What may the companion do with a retrieved passage?**

| Option | Behaviour | Trade-off |
|---|---|---|
| **A1 Infuse-only** *(current)* | Passages shape tone; never named/quoted | Honest, low-risk, but **cannot discuss or verify** — fails the requirement |
| **A2 Always-cite** | Every turn quotes + cites | Verifiable, but heavy/pedantic; turns a reflective companion into a citation machine |
| **A3 Hybrid — infuse by default, quote on demand** ✅ | Brief reflection infuses; when the user asks to discuss/see/verify, quote verbatim + cite | Best of both; needs the model to judge intent (a normal LLM strength) |

**Recommended: A3.** Reflection stays light; "what does the book say about X?" gets a real,
quoted, cited answer. The infuse path (`to_prompt_block`) is retained for surfaces that
opt into it; a new **discussion path** (`to_discussion_block`) permits naming + verbatim
quotation of the provided passages.

---

## 3. Choice B — Location granularity (the "pages" question) — **DECIDED: structural anchors**

An EPUB is **reflowable**: text has no fixed pages (a "page" depends on the reader's font
and screen). "Point to page 47" is not a property the source carries. Best-in-class reading
tools (Kindle, Readwise, Apple Books) cite reflowable books by **chapter / section /
location / %**, not print pages, for exactly this reason.

| Option | Anchor shown | Cost | Verdict |
|---|---|---|---|
| **B1 Structural anchors** ✅ | *"Ch. 3 ('Hypermedia Controls'): '…quote…'" → [open book]* | Surface `sequence`; capture `chapter` at ingest; extend `CanonPassage`; one re-ingest | **Chosen** — works for any EPUB, faithful, best-practice |
| **B2 EPUB page-map** | *"p. 47"* if the file embeds print-page breaks | Detect + parse the page-map; falls back to B1 where absent | Deferred — file-dependent, unverified for HMS |
| **B3 PDF source (real pages)** | *"p. 47 (print ed.)"* | A second ingestion path + reprocessing per book | Deferred — largest scope, marginal gain over B1 |

**Chosen: B1 structural anchors.** Cite **chapter + section heading + position-in-book +
deep-link** to the Resource page. B2/B3 are recorded here as considered-and-deferred so the
reasoning survives; not built.

**What the data supports today vs. needs:**
- ✅ Exact quote text — stored (`ReferenceChunk.text`), retrieved verbatim.
- ✅ Book title / author / publisher — on the `Resource` node.
- ⚠️ Section heading — `ReferenceChunk.heading` exists but is the *immediate* heading only.
- ⚠️ Position — `HAS_REFERENCE_CHUNK.sequence` exists but is **not surfaced** in retrieval.
- ❌ Chapter — **not captured**; smallest fix = read top-level headings from the pandoc AST
  during cleaning (`scripts/clean_reference_book.py`) and carry a `chapter` field through
  `reference_ingestion.py`.
- ❌ Page number — not a property of the format (see above).

---

## 4. Choice C — Faithfulness guardrails (the "does it actually work" bar)

The failure mode that kills these products is **confident fabrication** — inventing a quote
or a page. The policy:

1. **Quote only retrieved text.** The model may quote **only** passages actually placed in
   its context this turn — never from parametric memory.
2. **Cite only the supplied anchor.** Chapter/section/position come from the passage's
   metadata; the model may not guess a location.
3. **Refuse gracefully.** If the shelf returned nothing resonant, say "I don't have a
   passage on that from the shelf" — never manufacture one.
4. **Verifiable by construction.** Every quote links to the Resource page so the human can
   check it against the raw — the honest core of "point to the raw."

These are enforced by the discussion prompt contract + retrieved-only context, and checked
by a runtime test that confirms the model refuses to invent a quote/anchor it wasn't given.

---

## 5. Choice D — Surface & retrieval query

- **First surface: the journal follow-up** — where the user hit the wall. Its `_Composer`
  carries the summon state forward (OOB hidden input) so a summoned session stays summoned;
  retrieval keys on the **user's question** (`user_reply`), not the raw entry, because the
  question is what "discuss the book" should match against.
- **Reusable capability.** Retrieval + quotation + citation stay domain-agnostic
  (`core/services/canon/`), so a later **dedicated "chat with the shelf" surface** and
  **Askesis** can call the same capability without a rewrite (matches the roadmap's
  "reusable, not a Journals feature" intent).

---

## 6. Reuse map (best-practice: lean on the stack, don't reinvent)

| Need | Existing component to build on |
|---|---|
| Structure extraction from EPUB | **pandoc AST** already used in `scripts/clean_reference_book.py` — read chapter headings from it |
| Vector retrieval | `Neo4jReferenceChunkAdapter.search_reference_chunks` + `referencechunk_embedding_idx` (walled from SearchRouter) |
| Citation footer shape | `askesis_citation_service.py` → `CitationBundle.format_for_askesis` ("Sources & Evidence") |
| Located citation rendering | Tier-1 `CITES_RESOURCE` **`locator`** free-string on Ku/PS + Resource detail (#565/#566) |
| "Point to the raw" destination | Resource detail page `ui/library/resource_detail.py` → `/library/resources/get?uid=…` |
| Passage value objects | `CanonPassage` / `CanonContext` — extend with `heading`/`chapter`/`sequence` |

---

## 7. Proposed implementation (Phases A–D — for review, not yet built)

- **A — Location metadata.** Surface `HAS_REFERENCE_CHUNK.sequence` in the retrieval
  projection (`neo4j_reference_chunk_adapter.py` + `ReferenceChunkHit` in
  `core/ports/query_types.py`); capture `chapter` during cleaning → ingest; extend
  `CanonPassage` with `heading`/`chapter`/`sequence` + a computed locator; re-ingest HMS
  (`scripts/ingest_canon_book.py --force`).
- **B — Discussion prompt.** Add `CanonContext.to_discussion_block()` (names books, permits
  verbatim quotation of provided passages only, per-quote location line, anti-fabrication
  contract from §4); keep `to_prompt_block()` for infuse-only surfaces; update the one
  asserting test.
- **C — Follow-up wiring.** `run_follow_up(summon_canon)` → retrieve on `user_reply` +
  footer; `follow_up_system_prompt(canon_context)`; `journals_follow_up` reads the flag;
  `_Composer` carries summon state; FOUNDER-gated.
- **D — Citation surface.** Upgrade the footer from "*Drawing on: Book*" to a Sources block:
  book + chapter/section/position + link to the Resource page (Askesis-footer shape).

**Verification (Phase A–D):** unit (discussion block quotes only provided passages + carries
location; follow-up injects + degrades cleanly; isolation test green); data (retrieval
returns chapter/heading/sequence; a known quote maps to the right chapter); runtime (headless
CDP as `linguistic76`: summon on → "what does Hypermedia Systems say about X?" → names the
book, quotes verbatim, cites Ch./section, links to the Resource page, refuses to invent).

---

## 7a. Sources render as real HTML links (not markdown text)

Journal response bubbles render as **plain text** (`whitespace-pre-wrap`, the copy-to-Obsidian
design), so a markdown link in the reply text would show as literal `[text](url)`. The
follow-up therefore returns **structured** sources (`CanonContext.sources()` → `CanonSource`),
not a markdown footer: `run_follow_up` returns a `JournalFollowUp(text, sources)` and
`FollowUpFragment` renders a real `<a href="/library/resources/get?uid=…">` per book +
its in-book locations — a genuinely clickable "point to the raw" (Codex #572 P2). The model's
inline quotes/citations live in the plain-text reply; the clickable back-pointers live in the
Sources block. Applying the same treatment to the compiled-file path (still a markdown
artifact) is a later, optional refinement.

## 8. Design principle recorded here

**Build to best-practice, on the existing stack, as if the project may not survive.** Lean
on pandoc's AST, the Neo4j vector index, the embedding worker, and the citation components
above rather than bespoke scaffolding — so the foundation is sound and reusable even if the
project is one day abandoned. A capability worth building is worth building on solid ground.
