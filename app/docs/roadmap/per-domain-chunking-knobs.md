---
title: "Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval"
updated: 2026-09-05
status: "partly done — filter half staged"
registered: 2026-08-28
ruled: 2026-08-30
trigger: "a measured miss traced to chunk grain (judged on best_rank); a content-typing classifier for chunk_type_weights and for switching the Askesis filter on"
check: "the two Cypher counts in the case file (fragments 7 after v2); git grep -n chunk_type_weights -- core/ empty until built"
---

# Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The chunking-params foundation shipped in #560 (2026-07-08): `ChunkingParams` on
`EntityIngestionConfig` (`core/services/ingestion/config.py`), every domain on
`DEFAULT_CHUNKING_PARAMS` (min 50 / max 500 words / context 100), `REFERENCE_CHUNKING_PARAMS`
(100/1000/150) for canon books, per-domain re-chunk via `regenerate_chunks(force=False)`
(`core/services/chunks/batch_chunking_service.py:101`). Two forward threads were recorded only in
memory: (1) **tune the knobs — "measure first"** (Mike's ruling), with the measurement never named;
(2) **chunk-type-aware retrieval** — chunks carry `chunk_type` (`ContentChunkType`, nine members:
definition / explanation / example / exercise / code / summary / section / introduction /
conclusion) but `_augment_with_body_chunks`
(`core/orchestrator/search_router.py:1120`) is type-blind. The sketch: a `chunk_type_weights`
table on `VectorSearchConfig` (`core/config/unified_config.py:142`, beside
`body_chunk_search_min_score = 0.68`), score = `vector_score × type_weight`, flat table first,
query-intent-conditioned later (ADR-034 Phase 2). `git grep chunk_type_weights` → 0 hits.

**Measured 2026-08-28 (AuraDB `d2d160c4`); re-measured 2026-08-30 unchanged, then acted on (Named work 1):** 998 `:ContentChunk`, all `chunking_version = 'v1'`,
all under `(:Content)-[:HAS_CHUNK]->`. By type: explanation **788**, exercise 142, definition 62,
example 3, summary 3; `code`, `section`, `introduction`, `conclusion` — 0 today. **By parent: path_step 386 chunks (21 parents), ku 309 (30),
user_entry 303 (15)** — the index is 30% personal-vault knowledge notes (canon P3), not
curriculum alone. In WORDS — the
unit the knobs are in, read from the persisted whitespace-aware count (`ContentChunk.word_count`
= `len(text.split())`, stored as `c.end_index` by `neo4j_content_adapter.py:193` — the name is
the adapter's, not a span): median **27**, p25 13, p90 75, max 496. **753 of 998 (75%) sit
below the configured `min_chunk_size` of 50** — the floor is
inert, never enforced (`core/services/ingestion/reference_ingestion.py:127` says so; #560
recorded 0 strategy references), and its default is above the corpus median. **83 chunks were
under 5 words — 75 of them `user_entry`** (`---` rules, bare `-` markers, link-only and
label-only lines; 72 typed `explanation`; 32 under 20 characters), 6 path_step (one was
`**5-4-3-2-1:**`), 2 ku; none exceeded the 500-word `max_chunk_size` (max 496 — the naive `split` had counted 2 over by counting empty tokens). 41 `:SearchEvent` in total, flat since 2026-07-22.

**What the numbers say (revised 2026-08-30).**
- **The type split is a classifier artifact, not a corpus fact.** `_detect_chunk_type`
  (`core/models/ps_content/content_chunks.py`) is a keyword heuristic whose FALLBACK is
  `EXPLANATION` — 79% means "no keyword matched" (and its `startswith(("a ", "an ", …))` →
  DEFINITION rule is over-broad). The distribution will NOT flatten from content growth; only a
  classifier that types by content changes it. A weight table built on it would re-rank a
  fallback label and look like it worked.
- **Chunk-type-aware retrieval exists on the Askesis path as a HARD filter — and has NEVER RUN.**
  `_INTENT_CHUNK_TYPES` (`core/services/askesis/context_retriever.py`) →
  `retrieve_scoped_chunks(chunk_types=)` → `chunk.chunk_type IN $chunk_types`. Re-measured on the
  925-chunk v2 corpus (2026-08-30): EXPLORATORY **66 of 925** (7.1%) — of which `introduction`,
  one of its three named types, matches **zero rows**; PRACTICE 137 (14.8%); the other mapped
  intents 786 (85.0%). The v2 re-chunk moved none of it (was 65/145/850 of 998), as predicted.
  ⚠ **EXPLORATORY's mapping may be answering the wrong question entirely.** Its
  `INTENT_EXEMPLARS` describe *catalog browsing* ("Show me what's available", "Browse available
  knowledge"), while `INTRODUCTION`/`SUMMARY`/`DEFINITION` chunks answer *topic orientation*
  ("introduce me to stoicism") — two intents under one name. PR-1 of
  [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)
  decides which it is; if it lands on browsing, this mapping is wrong on its own terms and the
  7.1% is beside the point.
  **But those are counterfactuals.** Driving the production path (`./dev eval-askesis-draw`)
  showed all 23 queries classify to **SPECIFIC**, which is unmapped → `chunk_types=None` → no
  filter. The cause was one layer up and was not a tuning miss: classification needed
  `IntelligenceThreshold.INTENT_CLASSIFICATION` = **0.65** *average* cosine similarity across an
  intent's **8** exemplars. Averaging over 8 diverse short sentences is a far stricter gate than
  it reads: the 23 eval queries scored **0.078–0.291**, and a query that IS one of the exemplars,
  verbatim, still only reached **0.43–0.56** against its own intent (practice 0.562,
  hierarchical 0.561, relationship 0.561, aggregation 0.482, prerequisite 0.480, exploratory
  0.429). Nothing could clear it, so `classify_intent` could only ever return SPECIFIC — the
  starvation was real arithmetic with zero production effect.
  ⚠ **STATE CHANGE (PR-2, 2026-08-31): the gate is 0.35 and queries DO classify to mapped
  intents — the filter stays off by a DIFFERENT mechanism.** `retrieve_relevant_context` now
  hard-wires `chunk_types=None` at the call site instead of deriving it from the intent: the
  map is explicitly disconnected (greppable), no longer shadowed by an unreachable gate. See
  Named work 4, now a RULING.
- **The fragments were an ingestion-hygiene defect, 90% in vault notes** — `/search` never showed
  them (`_aggregate_body_chunk_parents` drops non-Ku/PS parents); they only crowded the vector
  candidate pool and Askesis draws. "Enforce `min_chunk_size`" as configured would have folded
  three-quarters of the corpus — that IS the blind tuning Mike ruled against, so the floor's
  VALUE stays with the measured thread below.
- **Ride-along, found by this re-measure:** Askesis chunk retrieval was owner-UNSCOPED over that
  30% vault-note share — closed the same day as ADR-085 **G8** (#1195).

**Named work:**
1. ✅ **Sub-sentence fragments — DONE 2026-08-30 (#1196 + live re-chunk).** Chunking algorithm
   **v2**: `FRAGMENT_FLOOR_WORDS = 5` (`content_chunks.py`), re-based from the corpus median,
   deliberately NOT the 50-word knob. Thematic breaks and bare list markers are dropped; any
   other sub-5-word prose fragment folds into a prose neighbour (never into a code fence; a
   merged chunk re-types from its final text; a section made only of fragments joins into ONE
   chunk — the designed residual). Live run: `regenerate_chunks(force=False)` 66/66 parents,
   998 → **925** chunks all `v2`, fragments 83 → **7** (every survivor a link-only MOC-style
   note with nothing to fold into — a content property, not a splitter defect), embedding
   `NULL` = 0 after the worker drain, median 27 → 30 words.
2. **Knob tuning — instrument SHIPPED 2026-08-30 (eval arc PR-1), baseline RATIFIED
   2026-08-30:** `scripts/eval_chunk_retrieval.py` (`./dev eval-chunk-retrieval`) scores
   hit@5 over the reviewable query set `scripts/eval_chunk_retrieval_queries.yaml`
   (23 queries with expected Ku/PathStep hits) through the SEARCH path that retrieves
   chunks — `SearchRouter.faceted_search` with semantic boost, the sole caller of
   `_augment_with_body_chunks` (`log_event=False`, so eval runs never write
   :SearchEvent telemetry); `advanced_search`
   searches parent entities and never touches a `ContentChunk`, so a baseline run through it
   would be blind to every knob here (Askesis reaches chunks separately via
   `retrieve_scoped_chunks` — the knobs move that too, and it is audience-scoped since ADR-085 G8 (#1195) — but the eval targets search). Mike ratifies the query→expected-hit pairs
   (the set's `ratified:` field carries the date); the first RATIFIED run IS the baseline.
   **BASELINE (v2, ratified 2026-08-30, AuraDB `d2d160c4`, 925-chunk v2 corpus): hit@5 =
   23/23 = 1.00, 18 via the body fold, 0 errors; best_rank 1×19 / 2×3 / 3×1, mean 1.22.**
   ⚠ **The headline metric is SATURATED and can only detect regression, not improvement.**
   It reads 1.00 because the v2 widening admitted the Kus the two `real_usage` rows were
   already returning — not because retrieval changed (the 21/23 draft ran on the same
   corpus and the same code). A knob change that improves ordering cannot show up in
   hit@5, so **tuning is judged on `best_rank` and `expected_missing`**, which are in the
   `--json` rows and are NOT saturated. The one live residual: for the bare query `body`
   the fold contributes **0 chunk candidates** (nothing clears
   `body_chunk_search_min_score = 0.68`; corpus best 0.651) and both expected PathSteps
   stay absent — yet `ps.self-awareness.understanding-your-emotions` is reached at rank 1
   via the fold by "noticing feelings in my body before I react", so the gap is that
   query's specificity against the score floor, not that PathStep's retrievability. Only a measured
   miss traced to chunk
   grain earns a `chunking_params` change on one `EntityIngestionConfig` + a domain-scoped
   re-chunk. This is also where `min_chunk_size`'s default is re-based: 50 words is above the
   corpus median, so enforcing it is a tuning decision, not a defect fix. (The two older
   scripts still measure something else: `analyze_search_metrics.py` is latency/score
   from logs; `benchmark_hybrid_queries.py` is query-pattern latency.)
   **PR-2 (2026-08-30):** set widened to **v2** on Mike's ratification review — both
   `real_usage` rows had been too narrow, and both notes now carry the measurement that
   settled them. **Body-fold status shipped:** `SearchResponse.body_fold`
   (`BodyFoldReport` + `BodyFoldStatus`, ruled 2026-08-30) reports whether the fold ran,
   how many passages cleared the floor and how many parent cards it added — the fold fails
   SOFT, so without it a chunk-blind response is indistinguishable from a chunk-aware one
   that matched nothing. It REPLACED the eval's out-of-band probe, which proved only that a
   SIBLING call succeeded while the scored response's own fold ran afterwards and could fail
   independently.
   **Append-never-promote (measured, not a defect claim).** `_augment_with_body_chunks`
   ends `merged = list(response.results) + body_results`, and a parent already present from
   frontmatter is deduped OUT of the body list. So the fold can append but never re-rank:
   for `breath`, chunk retrieval scores `ps.mindfulness.breath-awareness-basics` the **#1
   parent at 0.755** while it sits at merged rank **6**, below five title-CONTAINS Kus. Mike
   ruled 2026-08-30 that those five are genuinely relevant, so this is recorded as a
   structural fact, not scheduled work; it is what a future ordering change would have to
   contend with.
3. **`chunk_type_weights`:** only when (a) the eval set exists and (b) a content-typing
   classifier has replaced the keyword fallback AND its distribution has flattened enough for
   weights to change an ordering (explanation < 50%) — (b) is a classifier decision, not a
   threshold the corpus crosses by growing (first bullet above).
   The table must carry all nine `ContentChunkType` members — a type with 0 chunks today
   (`code`, `section`, `introduction`, `conclusion`) weights 1.0 until it is measured, never
   "absent"; the distribution check below groups by whatever types exist.
4. **Askesis intent filter — MEASURED INERT 2026-08-30; now a RULING, not a build.**
   The thin-draw comparison shipped as `scripts/eval_askesis_chunk_draw.py`
   (`./dev eval-askesis-draw [--user <uid>]`): three arms — `filtered` (production),
   `thin_draw` (keep every filtered hit, BACKFILL from an unfiltered draw up to k — never
   loses an intent-appropriate passage the way "use the unfiltered draw when thin" can) and
   `unfiltered` (control) — over the same reviewable query set, reproducing the production
   draw (`limit=5`, `min_score=0.6` — NOT /search's 0.68 — and `user_uid` as the ADR-085
   audience). Recall is scored at the **prompt window of 3**, not the draw limit:
   `retrieve_relevant_context` keeps `relevant_chunks[:3]` and that is what `llm_service`
   inlines, so a parent reached only at draw rank 4 is retrieved and thrown away.
   Starvation is measured against the same 3 for the mirror reason. **Result: all three
   arms identical (recall@3 22/23, 0 starved), run both curriculum-only and with the
   audience, because 0 of 23 queries reached a filtered intent.** The script printed that
   as a loud banner, with the measured margin (`max_intent_score` 0.29 against the then-0.65
   gate) so the zero read as "unreachable gate", not "unusual queries" (banner re-worded at
   PR-2: the gate is reachable now, so an all-unmapped run reads as "these queries score
   low") —
   `filtered_intent_queries: 0` means the arms are an identity, not a finding. It classifies
   through `IntentClassifier.classify_intent_scored` (added here), NOT the fail-soft
   `classify_intent`: that one converts an embedding outage into `Result.ok(SPECIFIC)`, which
   is byte-identical to a real low-confidence verdict, so an outage could have manufactured
   this very finding with `errors: 0`. The scored variant fails loudly and a failed
   classification invalidates its row. It also reports `unlabelled_in_windows` PER ARM (1 in each of the three on the
   `--user` run, 0 curriculum-only), because a viewer's own notes compete for the prompt
   window while the set labels only published Ku/PathStep. Per arm, not per run: once
   the filter is live the three arms hold different windows, and a note sitting in only
   one of them would depress that arm alone and make the delta look like filtering.
   **So the thin-draw fallback would change nothing today**, and shipping it alone would be
   dead code guarding dead code.
   **RULED 2026-08-30 (Mike): NOT (a) — do not delete. The shape is (b); the present state
   is (c).** **REFINED the same day, once the dormant surface was measured: the classifier fix
   is SCHEDULED and the chunk filter is NOT part of it** — see
   [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md).
   The classifier gates SIX Askesis branches across its two callers, and this filter is the
   weakest of them; the other five (graph context, suggested actions, citations — which had
   consequently never attached to any Askesis answer until PR-2 — plus the context-query
   API's own prose and actions branches) need no chunk types at all. So activation happened there first with `chunk_types` hard-wired off
   (LANDED 2026-08-31, PR-2 — `retrieve_relevant_context` no longer calls
   `_intent_to_chunk_types`; the map's disconnection is stated at the call site), and
   "fix and fallback ship together" narrows to its true scope: it binds whoever switches the
   FILTER on, not whoever fixes the classifier. This entry keeps the filter half.
   The plumbing stays because the intent is to *connect* it, not to retire it:
   `_INTENT_CHUNK_TYPES` + `chunk_types=` are a staged surface awaiting a reason to fire, so
   they are **PLANNED, not dead** — the One Path Forward carve-out for deliberately
   staged-but-unwired work. **Switching this filter on is ONE change with the thin-draw
   fallback**: activation is never neutral, and a live filter without the fallback imposes
   the 66-of-925 EXPLORATORY starvation on draws that today see all 925. The fallback is the
   prerequisite for ACTIVATING THE FILTER — not for fixing the classifier, which the arc doc
   does with the filter left off. Until then (3)'s weight table is arguing about a path that
   does not execute.
   ⚠ **The EXPLORATORY mapping is now wrong ON ITS OWN TERMS (PR-1 of the arc, 2026-08-31).**
   PR-1 settled `EXPLORATORY` as **catalog browsing** — *"what is there to learn here?"* — and
   NOT topic orientation (*"introduce me to stoicism"*, which is a content question and stays
   `SPECIFIC`). `INTRODUCTION`/`SUMMARY`/`DEFINITION` types an orientation answer, so this row
   maps an intent to the chunk types of a DIFFERENT intent. That is independent of the 7.1%
   eligibility measured above: even with a perfect content-typing classifier and a rich
   `introduction` population, the mapping would be answering a question EXPLORATORY no longer
   asks. Whoever builds (3)'s weight table or switches this filter on re-derives that row
   first — the arc doc's ruling 3 carries the reasoning.
   **Named cost while inert — SHRUNK by PR-2 (2026-08-31):** until then every reader of
   `context_retriever.py` — and, until #1198, four docs — saw an intent→chunk-type filter that
   appeared operative and was not, legible only through this entry plus the
   `./dev eval-askesis-draw` banner. The call site now states the disconnection itself
   (`chunk_types=None`, hard-wired, with the reason), and `_intent_to_chunk_types` is
   registered in `PLANNED_METHODS`.
   ⚠ **"Fix the classifier" DOES now mean "move the gate" — this reversed on the ratified
   baseline (2026-08-31), and the earlier reading here was wrong.** It said the fix must not be
   assumed to be a lower threshold, because a verbatim exemplar's 0.43–0.56 self-similarity
   implicates the *averaging over 8 diverse exemplars*, and because all three aggregations were
   thought to rank identically. Measured on 45 labelled queries, both halves fail: the
   aggregations do NOT rank identically (mean 30/31, max 29/31, top-3 29/31), and the production
   `mean` **dominates at the exact zero-wrong-activation frontier** — it activates 21 of 45 at
   0.3329 (78% accuracy), against max 17/45 at 0.5353 (69%) and top-3 15/45 at 0.4911 (64%).
   ⚠ Exact, not ladder-rounded: the frontier is pinned by one query and a 0.05 grid rounds it up,
   which understated all three arms (#1206). The averaging is not the defect; it is the
   best-behaved of the three. So the indicated fix is the one the old reading warned against:
   keep the mean, move the gate — **0.35, deliberately not the frontier itself**, which is an
   observed score and drifts between runs. **SHIPPED 2026-08-31 (PR-2)**: the gate is 0.35;
   the `AGGREGATION` carve-out PR-2 introduced was lifted the same day by the tool-selection
   first slice ([askesis-tool-selection-queries.md](askesis-tool-selection-queries.md)) in the
   same commit that added the aggregation tool; the arc doc's PR-2 section records the
   post-change measurement. Note what flipping queries off SPECIFIC does and does not touch: with `chunk_types`
   held off it re-routes the two answer-shaping branches and NOT the chunk draw, which is
   exactly why the arc proceeded without the fallback.
   **Both halves of that are RUNNABLE, not just prose**
   (`tests/unit/test_askesis_intent_filter_activation_guard.py`): mapping `SPECIFIC` fails —
   it is the verdict `classify_intent` returns on an embeddings OUTAGE, so a mapping would let
   a provider failure silently answer from a type-filtered slice, and that holds after the fix
   too; and switching the score from a mean to a max fails — originally because the averaging
   was the mechanism the "not just lower 0.65" reading rested on, and now for a better reason
   that outlived it: the mean is MEASURED to mis-route least. Neither asserts the filter is inert —
   that is live-corpus state and stays with `./dev eval-askesis-draw`.

**Trigger:** (1) ✅ done; (2) ✅ instrument + body-fold status shipped (PR-2), set ratified at
v2 and the baseline recorded on #1197 — the thread is now open only for a measured miss traced to
chunk grain (judged on `best_rank`, not the saturated hit@5); (4) ✅ measured and RULED — and the
ruling SPLIT it in two, so read both halves before starting: the **classifier fix is scheduled
separately** and does NOT touch this filter
([askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)),
while **switching this filter on** stays here, gated on (3)'s content-typing classifier and
carrying the thin-draw fallback in the same change. Inert with the cost named until then;
(3) needs that classifier regardless, and gates the filter half of (4) — not the classifier arc,
which does not depend on it.
**Check** (one statement per block — paste each on its own; words, not characters, because the
knobs are word counts; `c.end_index` is the persisted whitespace-aware `word_count`, so a chunk
with line breaks or doubled spaces is counted the way ingestion counted it — a naive
`split(text, ' ')` disagrees on 4 of 998 chunks and inflates the max to 599):
```cypher
MATCH (c:ContentChunk) WITH c.chunk_type AS t, c.end_index AS words
RETURN t, count(*) AS n, percentileCont(words, 0.5) AS p50_words,
       sum(CASE WHEN words < 5 THEN 1 ELSE 0 END) AS fragments,
       sum(CASE WHEN words < 50 THEN 1 ELSE 0 END) AS under_min_chunk_size
ORDER BY n DESC
```
```cypher
MATCH (c:ContentChunk) WHERE c.end_index < 5 RETURN count(*) AS fragments   // 83 pre-v2 → 7 after the 2026-08-30 re-chunk (all link-only notes); a rise = new fragment-shaped ingestion
```
plus `git grep -n chunk_type_weights -- core/` (empty until built).
The intent filter's disconnection IS greppable since PR-2 (2026-08-31): the one production
call site hard-wires `chunk_types=None` with the reason stated
(`retrieve_relevant_context`, `core/services/askesis/context_retriever.py`) — before that the
code was wired and reachable and only the unreachable 0.65 gate kept it inert.
`./dev eval-askesis-draw --json` → `filtered_intent_queries` now counts queries whose
CLASSIFIED intent has a mapping — a counterfactual input to the filter arms, not "production
filtered here"; non-zero is EXPECTED at the 0.35 gate, and the arms measure what the filter
WOULD do for PR-3.
**Named cost while parked:** a type table built today would be tuned against a fallback-dominated
corpus (78% one label on the v2 corpus), and EXPLORATORY's eligible slice stays 66-of-925 — a
counterfactual while the filter cannot fire, and the number to beat the moment it can.
