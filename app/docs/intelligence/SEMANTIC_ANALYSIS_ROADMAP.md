---
title: Semantic Analysis Roadmap
updated: 2026-07-10
status: current
category: intelligence
tags: [analysis, intelligence, roadmap, semantic]
related: []
---

# Semantic Analysis Roadmap

**Status:** Search wiring SHIPPED (#538, body-chunk semantic layer). The
remainder is a 3-item backlog — product-approved 2026-07-10 as a follow-up arc,
one item per PR, each planned fresh when picked up.

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

### 1. Concept clustering

Cross-KU similarity surface: "you studied X — here's Y using the same core
concept." Needs a clustering pass over existing entity/chunk embeddings plus a
user-facing surface. **Open product decision (STOP point): where the surface
lives** (Ku/PS detail page vs /explore vs elsewhere).

### 2. Prerequisite inference

Derive suggested `PREREQUISITE_FOR` edges from content similarity. Suggestions
only — authored Edge YAML stays canonical, and inferred edges are NEVER
auto-written to the graph. **Open product decision (STOP point): the approval
workflow** (admin queue vs drafted Edge YAML in the vault).

### 3. Askesis/ZPD gap-detection feed

Route semantic neighbours of a learner's weak areas into ZPD gap analysis
(`core/services/zpd/`), strengthening "what should I learn next."
**STOP point: any change to user-visible recommendations** that weighs inferred
gaps against authored curriculum order needs a pedagogical ruling.

---

**Trigger:** none — not data-gated. Picked up after the Discovery Analytics
Phase 1 arc (search-event logging + gap surface) completes.
