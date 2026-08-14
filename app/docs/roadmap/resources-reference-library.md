# Resources/ Reference Library — Ingestion Roadmap

**Status:** **Tier 1 (Pointing) = foundational, near-term.** **Tier 2 (Passage-addressable) = PLANNED, no date** — deliberately unforced; it will take clearer shape as the content matures. Cleaning of raw source files is **external to SKUEL.app** (author-side preprocessing, not a codebase feature).

**Core Principle:** *"Point to the raw; don't over-interpret. Let the resources speak for themselves."*

---

## SKUEL's way — why this is a feature, not a limitation

This is a defining aim of SKUEL, one to hang our hat on: **SKUEL does not interpret the Resources; the Resources exist and speak for themselves, and the user interprets them.** SKUEL points *at* a book and a page — "look at pg xy in book xyz" — and nudges the user to go read it. The books in `Resources/` are understood as *essential reading* for SKUEL; the app's job is to shape structure and context and then point, not to digest the books on the user's behalf.

This is a brand-level stance: **much of life is meant to be met in the raw.** An app that chunks and re-serves a book's every passage quietly asserts that it has already done the reading for you. SKUEL refuses that. It focuses on shapes and context, and hands you the source. Over-interpretation is the failure mode we are designing *against*.

The practical consequence: we resist pulling book *content* into the graph. We hold **pointers**, not bodies. Passage-level ingestion (Tier 2) is possible and may earn its place someday, but it runs against the grain of this principle, so it is held lightly — planned, not scheduled.

> This document is itself part of articulating "SKUEL's way." Documenting the stance in `docs/` disciplines the code; the code, in turn, sharpens the stance.

---

## The situation on disk

Two folders, two representations of the same corpus:

- **`Res/`** — the **ingested** layer. 10 small `resource_*.md` descriptor cards (~900 bytes). Each is a `Resource` entity (`EntityType.RESOURCE`, `ContentOrigin.CURATED`): rich frontmatter (author, publisher, year, ISBN, media_type, tags) + a short annotation. The annotation is embedded as an entity-level vector; the body is **not chunked**. A Resource today is a **catalog card** that points at the raw text on disk.
- **`Resources/`** — the **raw reference library**, walled off. 14 markdown files (some book-length: Transcend ~137k words, Hypermedia ~105–127k, Atlas of the Heart ~79k) + ~146 images. Held out by two walls:
  1. `services_bootstrap/compose.py` — `excluded_dirs={_content_root / "Resources"}` keeps the sync allowlist from sweeping the raw texts.
  2. The raw files carry no `type:` frontmatter, so the ingester cannot classify them anyway.

The wall was a conscious ruling (Arc D descriptor-only, 2026-07-03), not an oversight. Its reason: **chunk dominance.** Chunking Transcend at ~500 words/chunk yields ~275 chunks from one file; all 14 → ~1,500–3,000 chunks — dwarfing the structural vault (Kus, PathSteps) and drowning curriculum search in book passages.

---

## The two tiers

The stated goal — "point to a page in a book" — splits into two very different capabilities.

### Tier 1 — Pointing (foundational, near-term)

"This Ku relates to Transcend, ch. 4 — go read it." The book stays walled on disk. SKUEL holds a **pointer**, not the content. This is maximally faithful to SKUEL's way. Tier 1 ingests **no book bodies**: no chunking, no `:ReferenceChunk`, no embedding cost, no dominance problem.

**Already built (the citation spine exists):**
- `(Ku|PathStep)-[:CITES_RESOURCE]->(Resource)` exists, authored via `resource_uids:` frontmatter, **live** (e.g. `ku_tao-te-ching-v1` cites `resource.tao-te-ching` / `resource.tao-of-pooh`). Askesis traverses it (`get_cited_resources`).
- **PathStep detail already renders a "Resources" section** (`ui/explore/ps_detail.py` — `_resources_section` / `_resource_chip`): media icon, title, author/year, and an external `source_url` link when the descriptor carries one.
- **Edge YAML already supports custom scalar edge properties** (`core/services/ingestion/preparer.py` extracts edge `properties`) — so a `locator` on the edge needs no new ingestion primitive.

**Decisions (ruled 2026-07-08):**
- **Locator authoring = two doors.** Flat `resource_uids:` stays for "cites this *work*" (whole-book, no locator). Located citations are authored as explicit **Edge YAML** in `edges/` (`type: CITES_RESOURCE`, `from`, `to`, `locator: "ch. 4"`). Don't break the easy inline path; add the rich path only where a locator is wanted (accepted cost: a located citation is a separate file).
- **Locator format = free string** (`"ch. 4"`, `"pp. 210–214"`, `"12:30"`, `"the sailboat metaphor"`). No structured schema — Tier 1 only *displays* it; the human interprets; heterogeneous media handled for free.
- **Locator lives on the edge, never on the Resource** — each citation points at its own place.

**Tier 1 scope (what to build):**
1. **`locator` free-string property on `CITES_RESOURCE`** via the Edge-YAML door; render it on the resource chip ("Transcend — Kaufman · ch. 4").
2. **A Resource detail page** — *the biggest single piece.* Today `/library/resources` is a list hub with no per-resource view, and the chip's only click target is an external `source_url`. Build a per-Resource card page (rich descriptor: author, ISBN, annotation, locator, external link) and make it the citation click destination — SKUEL points you at the source so you go read it.
3. **Ku-detail parity** — lift the PathStep "Resources" section onto the Ku detail page (`ui/explore/ku_detail.py` renders no citations today, so live Ku citations surface nowhere). Data path already exists; low effort.
4. **Reciprocal "cited by" on the Resource hub** — "this book is cited by these 5 Kus/PathSteps" (edge is reverse-traversable). A discovery affordance: find curriculum via its sources.
5. **Fix the stale registry comment** — ✅ done 2026-07-08 (`relationship_registry.py` no longer claims "no Ku citations authored yet").

**Marked for future (not Tier 1):**
- **Multi-locator to the same work** ("draws on ch. 4 *and* ch. 9") — would need parallel edges or a locator *list*. YAGNI now; named so we don't design it out.
- **Inline body-anchored citations** — a citation attached to a *spot in the Ku body* (a "↗ Transcend ch. 4" marker mid-prose) rather than the bottom-of-page section. Needs body-level authoring granularity; revisit post-Tier-1. Tier 1 keeps the clean "Resources" section.

### Tier 2 — Passage-addressable (PLANNED, no date)

In-app "jump to the passage" / search *inside* the books. This is where the heavy machinery lives, and where the philosophical tension bites (it pulls content *in*). Held lightly. If it is ever built, the design is:

- **Separate chunk class** — `:ReferenceChunk`, distinct from curriculum `:ContentChunk`, so reference search and curriculum search are **distinct queries by construction** (a structural boundary, not a tuning knob — no cap/weight fiddling, no leakage). Reuses the per-domain chunking params (#560) to give Resource a larger chunk size than atomic Kus.
- **Modeling** — keep the `Res/` card as the entity; hang chunks off it; tag each chunk with its **nearest markdown heading** as metadata. Rough addressability ("near ch. 4") without modeling section nodes. Headings can be promoted to section nodes later *without re-chunking* — a foundation that refines.
- **Reunion mechanics** — the `Res/` card already names its raw path, so the join exists. Narrow (do not demolish) the compose wall to admit only the `.md` bodies of *carded* resources; images and un-carded files stay walled.
- **Hard prerequisite: clean text** (see below). Dirty text → garbage embeddings and unreliable headings → Tier 2 is not buildable.
- **Images** — deferred entirely; a separate arc.

---

## Cleaning — external to SKUEL.app

The raw extractions vary in quality, and **clean text is the gate for Tier 2**. Cleaning is **not** a SKUEL feature — it is author-side preprocessing; the author delivers clean files, and SKUEL only ever ingests a reviewed clean edition. The philosophy holds even here: the raw stays raw and untouched; a human-reviewed edition is what the machine reads.

**Rule of thumb by source provenance:**

| Source | Best cleaning path | Notes |
|---|---|---|
| **EPUB exists** | `pandoc … -t gfm-raw_html` | Near-lossless — EPUB is structured HTML. Correct heading tree, language-tagged code fences, smart quotes, complete prose. Clean at the source; nothing to repair. |
| **PDF-only (scanned)** | Best-available OCR service (datalab.to or similar), then review | Genuine OCR damage (`paradoxicallv`, `RANSC`) cannot be rescued by pandoc. Repairing with an LLM means the model *rewrites the raw* — corrosive to the philosophy; avoid, or gate behind explicit human review. |

**Empirical finding (Hyper Media Systems, EPUB):** pandoc `gfm-raw_html` beat the existing datalab extraction on heading hierarchy (correct nesting vs duplicated/flattened titles), prose completeness (~20% more words — datalab dropped content), code blocks (language-tagged fences vs untagged), and typography (smart quotes preserved). Residual raw HTML (~134 tags) was mostly legitimate tables/links/images GFM can't express, not garbage. **Conclusion: for EPUB-sourced books, re-extract with pandoc; datalab remains the fallback for PDF-only sources.** (Datalab.to was the author's prior best-of-breed choice for the PDF extractions.)

---

## Sequence

1. **Document SKUEL's way** — this file. The "point to the raw" stance justifies the pointing-first design and should graduate toward a first-class principle as it firms up.
2. **Tier 1 — Pointing:** Resource detail page (the click destination) + `locator` free-string via Edge YAML + Ku-detail citation parity + reciprocal "cited by" on the Resource hub. (Stale registry comment already fixed.)
3. **Cleaning (external):** author re-extracts EPUB-sourced books with pandoc, delivers clean files. Valuable on its own (clean reading, stable page numbers to cite *into*).
4. **Tier 2 — Passage-addressable:** PLANNED, no date. Built only if in-app passage retrieval proves genuinely necessary, and only on clean text.

## Open / not-yet-decided

- Whether Tier 2 is ever built at all — deliberately left open.
- (Tier-1 locator schema and UI treatment: **decided** 2026-07-08 — see Tier 1 above.)
