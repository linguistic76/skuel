---
title: Semantic Analysis Roadmap
updated: 2026-08-21
status: complete
category: intelligence
tags: [analysis, intelligence, roadmap, semantic]
related: []
---

# Semantic Analysis Roadmap

**Status:** COMPLETE. Search wiring SHIPPED (#538, body-chunk semantic layer);
all 3 remainder items shipped 2026-07-10 (one PR each — see per-item notes).
The only open thread is item 3's deferred semantic pool expansion, data-gated
on engagement edges.

---

## What already shipped

The original (2025-11) ambition — "search should understand content
semantically" — is live:

- **Body-chunk semantic layer (#538):** `/search` reaches lesson-body prose via
  `:ContentChunk` embeddings when `enable_semantic_boost` is on; matching body
  passages surface their parent Ku/PS card. Fails soft on the CORE tier.
- **Embedding infrastructure (ADR-074):** all content-bearing entities + body
  chunks are embedded event-driven post-persist, with content-hash idempotency.
- **Chunk semantic types:** ContentChunk carries DEFINITION / EXPLANATION /
  EXAMPLE / CODE / SUMMARY etc. — semantic structure at the passage level.

The original prerequisite (50+ KUs with rich text) is met (121 Kus, ~100%
chunk-embedded).

## Buried (One Path Forward ruling, 2026-07-10)

The 2025-11 draft proposed a `TextAnalysisService` (Flesch readability scores,
regex-based semantic-role extraction) behind a `/api/search/semantic-analysis`
endpoint. **Removed outright, not deferred:** pattern-matching NLP adds nothing
next to the shipped embedding + chunk infrastructure, and nothing consumes
readability scores. If content-complexity-for-ZPD ever matters, it gets
designed fresh against the chunk layer — do not resurrect the old recipe.

---

## The approved remainder (follow-up arc, one PR each)

All three consumers were product-approved 2026-07-10. The embeddings exist;
what's missing is the grouping and a surface to show it. Each PR starts with
its own research + planning pass — the notes below are scope sketches, not
designs.

### 1. Concept clustering — SHIPPED 2026-07-10

Landed as the **"Related concepts"** chip-row on BOTH detail pages
(`/explore/ku/{uid}` + `/explore/ps/{uid}`) — the product ruling chose the
detail-page surface and rejected graph-view/search-strip variants. Mechanic:
on-demand node→node vector similarity (`find_related_concepts` →
`find_similar_to_node` against `ku_embedding_idx` / `pathstep_embedding_idx`),
lazy HTMX fragments at `/explore/{ku,ps}/{uid}/related`. A read-time lens
ONLY — no clustering pass, no persisted edges, no cluster nodes; FULL tier
only (section absent on CORE). Threshold `ku_similar_min_score=0.72` derived
from a full-corpus sweep — see the derivation comment in
`core/config/unified_config.py::VectorSearchConfig`.

### 2. Prerequisite inference — SHIPPED 2026-07-10

Landed as the **admin suggestion queue** at `/admin/prereq-suggestions`:
candidates → LLM judge → per-row approve/reject. Mechanic
(`PrereqSuggestionService` + read-only `PrereqCandidateBackend`):

- **Candidates = MID-similarity band, not the 0.72 knob.** Phase A proved
  authored `PREREQUISITE_FOR` pairs sit at cosine 0.32–0.57; the band is
  0.40–0.72 (0.40 admits 6/8 authored pairs = recall ceiling; 0.72 hands off
  to the "Related concepts" lens), per-Ku cap + 200-pair global bound.
  Pairs already connected by ANY Ku↔Ku edge (both directions) or covered by
  an authored directed path are excluded. Pairwise cosine runs in-process
  over stored `Ku.embedding` — no vector-index round-trips.
- **Judge = LLM (FULL tier)**: {prereq A→B | B→A | related | skip} + one-line
  rationale (`prereq_edge_judge` template, fail-soft per batch). **CORE
  degrades** to undirected pairs — the admin picks relation + direction
  himself (Analog-complete).
- **Approval ruling (Mike, 2026-07-10): approve = the app writes ONE Edge
  YAML file into `{INGESTION_PATH}/edges/`** — the first sanctioned
  vault-write (`EdgeFileWriterPort` / `ContentVaultEdgeWriter`: containment
  after resolve(), strict filename shape, never overwrites, colon-form UIDs
  reverse-normalized, `source: inferred-approved`). The edge lands in the
  graph via the normal content-vault sync; this feature NEVER writes to the
  graph. Reject is stateless v1 (suggestion reappears on regeneration);
  suggestions are ephemeral — no persisted suggestion nodes.

### 3. Askesis/ZPD gap-detection feed — SHIPPED-AS-SCOPED 2026-07-10

Phase A found the real blocker was a **production wiring bug**, not missing
semantics: a second compose-level `UserContextBuilder` shadowed UserService's
internal one, so the ZPD capstone (`zpd_assessment`) never reached
`get_rich_unified_context` — daily-plan P5 ran on `None` since March. Shipped
scope (pedagogical rulings 2026-07-10):

- **Dual-builder fix:** ONE app-wide builder (owned by `UserService`, reused by
  compose; guarded by a source-level regression test) — the capstone now runs
  on the production daily-plan path.
- **ENABLES-proximal:** the zone query's proximal expansion follows
  `PREREQUISITE_FOR|ENABLES` (32 authored ENABLES edges now feed the zone).
  **Ruling: proximal expansion ONLY** — readiness scoring and blocking-gap
  logic stay strictly prerequisite-only; an enabler never becomes a gate.
- **"Related to your next step" chips** on the PS detail page
  (`/explore/next-step/related`, #598 mechanic): the viewer's readiness-ranked
  proximal Kus, each with vector neighbours labeled "related (unordered)" —
  authored-edge logic primary, vector hints explicitly undirected. Fail-soft
  absent on CORE/anonymous/empty-zone.

**Explicitly deferred — semantic pool expansion** (routing vector neighbours of
weak areas INTO the candidate pool): parked until engagement data exists
(Mike's ZPD is empty — zero activity→Ku edges). The fuel arc is
entry-enrichment (EXTRACT_ACTIVITIES /
vector-first entry↔graph linking), which stays parked. Re-open only with
engagement data AND a fresh pedagogical ruling on weighing inferred gaps
against authored order.

---

**Trigger:** none — arc complete. Item 3's deferred remainder is data-gated on
engagement edges (see above).
