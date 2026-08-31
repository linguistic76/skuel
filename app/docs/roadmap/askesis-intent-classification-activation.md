# Askesis Intent Classification — Activation Arc

**Status:** SCHEDULED 2026-08-30 (Mike). Contract for a 2-PR arc; PR-3 is registered but gated.

**Core Principle:** *"Intent shapes the answer. It does not narrow what the answer may draw on."*

`IntentClassifier` has never returned anything but `SPECIFIC` in production. This is not a
tuning miss — an entire intent-conditioned layer of Askesis has never executed. This doc is the
contract for turning it on; the discovery that produced it lives in
[deferred-work.md](deferred-work.md) § "Per-Domain Chunking Knobs + Chunk-Type-Aware
Retrieval", Named work 4, which is where the chunk-filter half stays.

---

## What is actually dormant

`classify_intent` has two production callers (`query_processor.py:281, 486`). Its verdict
branches at **three** Askesis sites, all permanently on their else-path:

| site | dormant behaviour | in scope |
|---|---|---|
| `context_retriever.py:256–283` | intent-conditioned **graph context** — prerequisites/blocked knowledge, task counts, learning-path position, the EXPLORATORY overview | **yes** |
| `response_generator.py:389–470` | intent-conditioned **suggested actions** + follow-ups | **yes** |
| `context_retriever.py:127` (`_INTENT_CHUNK_TYPES`) | chunk-type `IN` filter on the RAG draw | **no — PR-3, gated** |

⚠ **`QueryIntent` has non-classifier callers that are already live and are NOT affected.**
`_INTENT_EDGE_SETS` (`cross_domain_backend.py:49`) and `build_graph_context_query`
(`query/graph_traversal.py`) take an EXPLICITLY passed intent — Tasks "dependencies" →
`PREREQUISITE`, and so on. Nothing there is dormant; nothing there changes. Only the
classifier-derived path is asleep. Do not "fix" those call sites.

## Why it can never fire (measured 2026-08-30, AuraDB `d2d160c4`)

`IntelligenceThreshold.INTENT_CLASSIFICATION` = 0.65 is compared against the **mean** cosine
similarity over an intent's **8** exemplars. Averaging 8 diverse short sentences puts the mean
far below any single match, so:

- the 23 ratified `/search` eval queries score **0.078–0.291**;
- a query that IS an exemplar, verbatim, reaches only **0.43–0.56** against its own intent.

**The aggregation choice moves reachability, not correctness.** Twelve intent-shaped probes,
same embeddings, three aggregations:

| aggregation | picks the same intent | clears 0.65 | median score |
|---|---|---|---|
| **mean** (today) | 9/12 | **0/12** | 0.361 |
| **max** | 9/12 | 6/12 | 0.650 |
| **top-3 mean** | 9/12 | 2/12 | 0.511 |

All three rank identically — only the confidence value moves, and the three errors are the same
three under all three. ⚠ **Those 12 probes are a sketch, not evidence**: at least two are
near-verbatim exemplars, so 9/12 is optimistic. Replacing them with a reviewable labelled set
is PR-1 and is the reason PR-1 exists.

**The errors cluster on EXPLORATORY**, which never won: both its probes lost to `AGGREGATION`,
because "Give me an overview" is literally an AGGREGATION exemplar. The two exemplar sets
overlap semantically.

## Rulings (Mike, 2026-08-30)

1. **Intent shapes the ANSWER, not the draw.** PR-2 activates the graph-context and
   response-shaping branches only. `chunk_types` stays `None`, hard-wired with the reason
   stated at the site. The thin-draw fallback is therefore NOT a prerequisite for this arc —
   it is only needed if the filter is ever switched on, which is PR-3's problem.
   *This supersedes the earlier "fix and fallback ship together" framing*: that reasoning holds
   only while activation implies the filter, and it no longer does.
2. **`AGGREGATION` is retired.** Askesis is a learning companion, not a dashboard query
   language — counts belong to the app's own surfaces. Retiring it resolves the EXPLORATORY
   collision for free, and it is the cheapest possible retirement: **no site branches on it**
   (`git grep QueryIntent.AGGREGATION` → exemplars, tests and comments only; it is explicitly
   ABSENT from `_INTENT_EDGE_SETS`).

## Sequencing

### PR-1 — the labelled set + the instrument (no behaviour change)

Same discipline as the chunk-retrieval eval, and the same ratification pattern: **Claude drafts,
Mike ratifies**, first ratified run is the baseline.

- A reviewable intent-labelled query set (`query → expected intent`), carrying a `ratified:`
  date field with the same typo-proof parse as `eval_chunk_retrieval_queries.yaml`.
- A scoring instrument (`./dev eval-intent-classification`) reporting, per aggregation
  strategy: accuracy, score distribution, share clearing the gate, and margin over the
  runner-up. Must classify through `classify_intent_scored` — `classify_intent` converts an
  embedding outage into `Result.ok(SPECIFIC)`, which would score an outage as a finding.
- Fix the AGGREGATION/EXPLORATORY exemplar collision as part of retiring AGGREGATION, and
  measure before/after on the set.
- **Label the corpus honestly:** a content question ("why does my mind keep wandering when I
  meditate") is genuinely `SPECIFIC`. A set that labels everything with a non-SPECIFIC intent
  measures wishful thinking. Expect SPECIFIC to be the largest class and keep it so.

### PR-2 — activation (behaviour change, narrow)

- Aggregation + threshold re-based on PR-1's measurement — **the value of 0.65 is not the
  question**; the mechanism is. Whatever lands must move `core/constants.py`,
  [deferred-work.md](deferred-work.md), [ASKESIS_HOW_IT_WORKS.md](../architecture/ASKESIS_HOW_IT_WORKS.md)
  and [ASKESIS_RAG_PIPELINE.md](../guides/ASKESIS_RAG_PIPELINE.md) together — the change-detector in
  `tests/unit/test_askesis_intent_filter_activation_guard.py` fires precisely so this cannot be
  forgotten.
- `chunk_types` stays off. State the reason at the site, not in a commit message.
- ⚠ **Activation is never neutral.** Two branches that have never run start running for every
  Askesis turn. Before/after the same questions through the real path, and read the ANSWERS,
  not just the classification — a correct intent that produces a worse answer is still a
  regression.
- ⚠ `SPECIFIC` must stay unmapped in `_INTENT_CHUNK_TYPES` — it is the outage fallback, and the
  activation guard pins this.

### PR-3 — the chunk-type filter (REGISTERED, GATED — may never happen)

Blocked on the content-typing classifier ([deferred-work.md](deferred-work.md) Named work 3).
Measured on the live 925-chunk v2 corpus, the current mapping is the worst available shape:

| intent | eligible chunks | note |
|---|---|---|
| PREREQUISITE / HIERARCHICAL / RELATIONSHIP | **786 (85%)** | not a filter — only excludes exercises |
| PRACTICE | 137 (14.8%) | |
| EXPLORATORY | **66 (7.1%)** | `summary` = **2 chunks**, `introduction` = **0 rows** |

No benefit where it is harmless; hardest bite exactly where the labels are weakest (78% of
chunks are the `explanation` keyword FALLBACK) and the classifier is worst (EXPLORATORY). If it
is ever switched on it needs the thin-draw fallback in the same change — that argument survives
intact for PR-3.

## Checks

```bash
# the gate is unreachable — every query classifies SPECIFIC (max_intent_score vs 0.65)
./dev eval-askesis-draw
```

```cypher
// what the PR-3 filter would filter on; `introduction` has never matched a row
MATCH (c:ContentChunk) RETURN c.chunk_type AS t, count(*) AS n ORDER BY n DESC
```

**Trigger:** PR-1 on Mike's next Askesis session. PR-2 on PR-1's ratified baseline. PR-3 only
if the content-typing classifier lands AND its distribution makes a type filter meaningful.
