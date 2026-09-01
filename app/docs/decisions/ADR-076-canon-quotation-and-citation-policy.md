---
updated: 2026-07-09
---

# ADR-076: Canon Quotation & Citation Policy — the Companion May Quote and Cite the Shelf

**Status:** Accepted — design confirmed with Mike; Phases A–D implemented on the journal
follow-up path and verified end-to-end (companion names + quotes *Hypermedia Systems* with
chapter/section citations; quotes confirmed verbatim against the chunks; summon-off is
canon-free).
**Date:** 2026-07-09
**Related:** ADR-073 (journals zero-persistence), ADR-074 (post-persist embedding events),
ADR-068 (OpenAI embeddings now), ADR-040/#565/#566 (Resources reference library — `CITES_RESOURCE` + `locator`)
**Design doc:** [`docs/architecture/CANON_CITATION_DESIGN.md`](../architecture/CANON_CITATION_DESIGN.md)
**Supersedes:** the "Infusion vs quotation → voice-infused, not quoted back" row of
`docs/roadmap/canon-journaling-companion.md` (2026-07-08).

---

## Context

The canon shelf (a curated set of reference books the FOUNDER journal companion can draw
on — first book: *Hypermedia Systems*, 105 embedded `:ReferenceChunk` nodes) shipped as
**silent voice-infusion**: retrieved passages shape the model's tone but the model is
instructed *"do NOT quote them, name them, or cite them inline… not sources to attribute"*
(`core/services/canon/canon_models.py`). A user asking *"talk about Hypermedia Systems —
have you read it?"* is therefore told **"I haven't read the book directly."**

Two facts reframe this:

1. **The "no quotation" rule was never an architectural decision.** It lives only in the
   roadmap table, one prompt string, and one test asserting that string is present
   (`tests/unit/services/canon/test_canon_models.py`). No ADR, no schema, no data fence.
   It is a reversible prompt default that the 2026-07-08 roadmap over-recorded as a ruling.

2. **The product requirement is the opposite.** To be genuinely useful (and competitive —
   many products promise "chat with your book" and win or lose on whether it *works*), the
   companion must **name the book, quote its exact words, and cite where the words came
   from**, verifiably. Silent infusion cannot meet that bar by design.

The book is an **EPUB** — reflowable, with **no fixed page numbers**. Citation must use
structural anchors, not literal pages (see the design doc).

## Decision

**1. The canon companion MAY quote and cite the shelf.** Replace the blanket "never quote
or name" instruction with a **hybrid grounded-RAG policy**:
- **Infuse by default** — brief reflective turns let passages shape voice (the existing
  `to_prompt_block` behaviour is retained for surfaces that choose it).
- **Quote on demand** — when the user asks to discuss, see, or verify the text, the model
  quotes **verbatim from the retrieved passages** and attributes them.
- **Always cite when quoting** — every quote carries a verifiable location anchor and a
  link back to the book's Resource page.

**2. Faithfulness is the hard rule (best-practice grounding).** The model may quote **only
text that was actually retrieved and placed in its context**, and may cite **only the
anchor supplied with that passage**. It must never fabricate a quote, a chapter, or a page
it was not given, and must say "I don't have that passage on the shelf" rather than
invent. This is the quality bar that separates a product that works from one that doesn't.

**3. Location = structural anchors, not pages (EPUB reality).** Cite by **chapter +
section heading + position within the book + a deep-link to the Resource page**
(`/library/resources/get?uid=…`). Literal print pages (via an embedded EPUB page-map or a
paginated PDF source) are **considered and deferred** — recorded in the design doc so the
reasoning is legible, but not built.

**4. Reuse existing citation machinery.** Build on the Askesis "Sources & Evidence" footer
shape (`askesis_citation_service.py`), the Tier-1 `CITES_RESOURCE` `locator` rendering
(#565/#566), and the live Resource detail page — do not invent a parallel citation stack.

**5. Journal follow-up is the first surface; the capability stays reusable.** The
retrieval + quotation + citation capability is domain-agnostic (Askesis-ready and
ready for a future dedicated "chat with the shelf" surface). It is wired into the journal
**follow-up** path first — the path the user actually tested, which today has **zero canon
wiring** — retrieving on the **user's question**, not the raw journal entry.

## Consequences

- **Positive:** the companion can genuinely discuss a book — name it, quote it, and point
  you to the exact place — which is the requested and market-relevant capability. Quotes
  are verifiable against the source (honest "point to the raw"). Nothing new is invented:
  data (verbatim `text`), citation patterns, and the Resource page already exist.
- **Cost / scope:** location anchors require surfacing `HAS_REFERENCE_CHUNK.sequence`,
  capturing `chapter` during EPUB cleaning, extending `CanonPassage`, and a one-time
  re-ingest. The follow-up path needs canon wiring. See design doc Phases A–D.
- **Guardrail debt:** faithfulness is enforced by prompt instruction + retrieved-only
  context, not by a hard fence. The design doc specifies the anti-fabrication prompt
  contract and the runtime test that checks the model refuses to invent a quote/anchor.
- **ADR-073 unaffected:** quoted passages remain ephemeral prompt context; nothing is
  persisted. Quoting *book* content (a product asset) is not persisting *journal* content.
- **Isolation unaffected:** `:ReferenceChunk` stays invisible to `SearchRouter`
  (`test_reference_chunk_isolation.py` remains green).

## Alternatives considered

- **Keep silent infusion, only fix the follow-up plumbing.** Rejected: makes the footer
  appear but still cannot answer "what does the book say / have you read it" — does not
  meet the requirement.
- **Literal page numbers now.** Deferred: EPUB has no pages; would force a PDF ingestion
  path (largest scope) for marginal gain over chapter/section anchors, which is how
  best-in-class reading apps cite reflowable books.
- **A separate "chat with the book" surface first.** Deferred: bigger new surface; the
  capability is built reusably so it can back that surface later without a rewrite.
