# Askesis Intent Classification — Activation Arc

**Status:** PR-1 SHIPPED + **BASELINE RATIFIED 2026-08-31** (Mike) — instrument, 45-query
labelled set, exemplar disambiguation. **PR-2 (activation) is next and is measured against
that baseline**; PR-3 is registered but gated.

**Core Principle:** *"Intent shapes the answer. It does not narrow what the answer may draw on."*

`IntentClassifier` has never returned anything but `SPECIFIC` in production. This is not a
tuning miss — an entire intent-conditioned layer of Askesis has never executed. This doc is the
contract for turning it on; the discovery that produced it lives in
[deferred-work.md](deferred-work.md) § "Per-Domain Chunking Knobs + Chunk-Type-Aware
Retrieval", Named work 4, which is where the chunk-filter half stays.

---

## What is actually dormant

`classify_intent` has **two production callers**, and BOTH must be in scope — an activation
validated on only one of them ships unmeasured behaviour on the other:

| caller | entry point |
|---|---|
| `_answer_user_question_pipeline` (`query_processor.py:281`) | `answer_user_question` — the chat/Ask surface |
| `_process_query_with_context_pipeline` (`query_processor.py:486`) | `process_query_with_context` — the public context-query API |

Its verdict branches at **six** sites across the two, all permanently on their else-path:

| site | dormant behaviour | in scope |
|---|---|---|
| `context_retriever.py:256–283` | intent-conditioned **graph context** — prerequisites/blocked knowledge, task counts, learning-path position, the EXPLORATORY overview | **yes** |
| `response_generator.py:389–470` | intent-conditioned **suggested actions** + follow-ups | **yes** |
| `query_processor.py:379–386` | **citations** — `_retrieve_citations_for_knowledge_units` has ONE call site, behind **two** gates: the intent must be `PREREQUISITE`/`HIERARCHICAL` **and** `extracted_entities["knowledge"]` must be non-empty (with a `uid`). The intent gate alone is enough to prove **no Askesis answer has ever carried a citation**; ⚠ but activation only opens the FIRST gate — see PR-2 | **yes** (user-visible) |
| `context_retriever.py:127` (`_INTENT_CHUNK_TYPES`) | chunk-type `IN` filter on the RAG draw | **no — PR-3, gated** |

Those four are reachable from `answer_user_question`. The second caller has **two more of its
own**, and they are different methods, not the same ones re-entered:

| site | dormant behaviour |
|---|---|
| `query_processor.py:517` → `_generate_context_aware_response(intent=…)` | intent-conditioned **prose** on the context-query API |
| `query_processor.py:528` → `response_generator.generate_suggested_actions(…, intent)` | a DIFFERENT method from `generate_actions` used by the other caller — its own intent branches |

`_build_query_response_result` also carries `intent` into the returned dict, so the API's
response shape changes for its clients too.

### ⚠ Activation reaches the two answer paths UNEQUALLY

`answer_user_question` Step 8 forks (`query_processor.py:344`), and the fork decides how much
of this the learner actually sees:

| | `_generate_guided_answer` (Socratic — the enrolled-user default) | `generate_context_aware_answer` (explicit facet scope, or no PS bundle) |
|---|---|---|
| receives `intent` | **no** | yes |
| receives `relevant_context` | **no** | yes (`additional_context=`) |
| answer PROSE changes on activation | **no** | yes |
| suggested actions / citations / `context_used` change | yes | yes |

So on the guided path the graph-context branch shapes **metadata, actions and citations — not
the prose**, because `_generate_guided_answer` takes only the question, the guided system
prompt and the PS bundle. Wiring `relevant_context` into the guided prompt is a **separate
decision**, not a side effect of activation: that prompt is deliberately narrow (ADR-077 /
`ASKESIS_SOCRATIC_ARCHITECTURE.md`), and widening it is a pedagogical change. Found by Codex on
#1201, confirmed in code.

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

⚠ **SUPERSEDED by PR-1's 45-query measurement below**, and in both directions: ranking is much
BETTER than 9/12 (30/31 on the mean arm), and the three arms do NOT rank identically (30/31,
29/31, 29/31). The table stays because it is what scheduled the arc, not because it is the
number to reason from.

**The errors cluster on EXPLORATORY**, which never won: both its probes lost to `AGGREGATION`,
because "Give me an overview" is literally an AGGREGATION exemplar. The two exemplar sets
overlap semantically — and reading them side by side says *how*:

**The discriminator is the OBJECT, not the verb.** *"Summarize my learning"* (AGGREGATION) and
*"give me an overview of stoicism"* (EXPLORATORY) share their verb and differ only in what they
are about — your records, or a subject. Worse, AGGREGATION's `"Give me an overview"` carries **no
object at all**, which makes it a magnet: the probe *"give me an overview of this topic"* matched
it at **0.792**. Short-sentence embeddings are dominated by the verb, which is exactly why an
average over eight of them separates these two so badly.

⚠ **`EXPLORATORY` meant two different things — RESOLVED by PR-1, see ruling 3.** Its exemplars
were *catalog browsing* ("Show me what's available", "Browse available knowledge", "What else is
there?") while its chunk-type mapping is `INTRODUCTION`/`SUMMARY`/`DEFINITION`, which answers
*topic orientation* ("introduce me to stoicism") — two intents under one name.

## Rulings

1. **Intent shapes the ANSWER, not the draw. Ruled 2026-08-30 (Mike).** PR-2 activates the graph-context and
   response-shaping branches only. `chunk_types` stays `None`, hard-wired with the reason
   stated at the site. The thin-draw fallback is therefore NOT a prerequisite for this arc —
   it is only needed if the filter is ever switched on, which is PR-3's problem.
   *This supersedes the earlier "fix and fallback ship together" framing*: that reasoning holds
   only while activation implies the filter, and it no longer does.
2. **`AGGREGATION` STAYS — member and exemplars. Ruled 2026-08-31 (Mike): position (b).**
   Askesis *does* answer questions about the user's own records; the safe mechanism is LLM
   **tool-selection** over vetted, parameterized, server-scoped tools — never generated Cypher
   ([askesis-tool-selection-queries.md](askesis-tool-selection-queries.md), whose direction this
   ratifies).

   ⚠ **This SUPERSEDES the 2026-08-30 retirement**, which was ruled one day earlier on the
   opposite premise — *"Askesis is a learning companion, not a dashboard query language; counts
   belong to the app's own surfaces"* — i.e. position (a), stated in those words. The same
   question was put twice; the later, fuller framing governs, and the mechanical outcome of the
   earlier one is reversed with it rather than kept on a dead rationale.

   **What survives the reversal is the collision — and it is now LOAD-BEARING.** Today a
   mis-route costs nothing, because nothing fires. Under (b), routing *"introduce me to
   stoicism"* to `AGGREGATION` sends a learner's exploratory question to a **count tool** and
   answers it with a number: a user-visible wrong answer where today there is merely a dormant
   one. Disambiguating the two exemplar sets is therefore a **correctness prerequisite** for
   tool-selection, not tidying.

3. **`EXPLORATORY` means CATALOG BROWSING, not topic orientation. Drafted by PR-1 and
   RATIFIED 2026-08-31 (Mike), with the labelled set that carries it.** *"What is there to learn here?"* is EXPLORATORY;
   *"introduce me to stoicism"* is a content question and stays `SPECIFIC`.

   Three reasons, in the order they decided it:
   - **It is the only choice that keeps EXPLORATORY separable from `SPECIFIC`.** `SPECIFIC` has
     no exemplars — it is what the classifier returns when nothing clears the gate — so it can
     never win a comparison, only be fallen back to. Making EXPLORATORY mean *topic orientation*
     would point its exemplars at the same objects every ordinary content question names, and
     the catch-all has no exemplar set with which to defend its own rows. Browsing's object
     ("the catalog") is one no content question has.
   - **It is what the live code already does.** `retrieve_relevant_context`'s `EXPLORATORY`
     branch (`context_retriever.py:285–294`) injects an overview of the user's own graph —
     tasks, goals, habits, knowledge units, MOCs. That answers *"where am I / what is here"*.
     Under topic orientation it would answer "introduce me to stoicism" with the learner's task
     statistics, and PR-2 would have had to rewrite it. **It does not: PR-2 activates that
     branch as written.**
   - **The object discriminator then partitions cleanly**: the catalog (EXPLORATORY), the
     user's own records (AGGREGATION), a subject (SPECIFIC). Under topic orientation the
     partition needs breadth-vs-depth — a distinction of shape, not object, which is the kind
     short-sentence embeddings resolve worst.

   ⚠ **Consequence, recorded in [deferred-work.md](deferred-work.md) Named work 4:** the
   `_INTENT_CHUNK_TYPES` mapping `INTRODUCTION`/`SUMMARY`/`DEFINITION` is now wrong *on its own
   terms* — it types chunks for topic orientation under an intent that no longer means that. A
   browsing question does not want an introduction passage; it wants the catalog. That is
   independent of the 7.1%-eligibility measurement, and it lands on PR-3, which is gated.

## Sequencing

### PR-1 — the labelled set + the instrument ✅ SHIPPED 2026-08-31

**What landed**

- `scripts/eval_intent_classification_queries.yaml` — **45 labelled queries** (`query →
  expected intent`), with the same typo-proof `ratified:` parse as the chunk-retrieval set
  (both now share `scripts/eval_query_set.py`, so the ratification contract cannot drift
  between them). Labels: SPECIFIC 14 (the largest class, on purpose), AGGREGATION 6,
  and 5 each for EXPLORATORY / PREREQUISITE / HIERARCHICAL / PRACTICE / RELATIONSHIP.
- `scripts/eval_intent_classification.py` (`./dev eval-intent-classification`) — three
  aggregation arms (`mean` = production, `max`, `top3_mean`) over the SAME query embedding and
  the SAME exemplar embeddings, reporting per arm: accuracy at the live gate, gate-blind
  ranking accuracy, score and margin distributions, share clearing the gate, and a threshold
  sweep for PR-2.
- The AGGREGATION / EXPLORATORY exemplar rewrite, with the editing rule stated above
  `INTENT_EXEMPLARS` so the next editor is standing in front of it.

⚠ **Every arm is checked against production, per run.** The `mean` arm is a
re-implementation, and a re-implementation that silently diverges would make the two
counterfactual arms meaningless. So every row is ALSO classified through
`classify_intent_scored` (never `classify_intent`, which converts an embeddings outage into
`Result.ok(SPECIFIC)` — the exact finding under test, manufactured from a provider blip), and
the run FAILS on any disagreement — a different predicted intent OR a score more than
1e-3 from production's. Measured across three runs: 45/45 checked, **0 disagreements**, max
score delta **8.4e-05 – 1.3e-04**. Re-embedding the same text is NOT bit-identical (that
spread is the evidence), which is why the check is a tolerance and why the delta is reported
on every run rather than assumed once.

**The acceptance condition HOLDS.** After the rewrite, **0 of 45 queries clear
`IntelligenceThreshold.INTENT_CLASSIFICATION` on the production arm** (highest score in the
set: 0.540, the verbatim HIERARCHICAL exemplar; highest AGGREGATION or EXPLORATORY row: 0.517).
The exemplar edits therefore ship here, not in PR-2 — nothing became reachable.

**Measured before → after (AuraDB `d2d160c4`, 45-query set, gate 0.65)**

| arm | accuracy at gate | ranking (gate-blind) | clears the gate | wrong activations |
|---|---|---|---|---|
| **mean** (production) | 31% → **31%** | 30/31 → **30/31 (97%)** | 0 → **0** | 0 → **0** |
| max | 47% → **51%** | 28/31 → **29/31** | 9 → **9** | 1 → **0** |
| top-3 mean | 33% → **33%** | 29/31 → **29/31** | 1 → **1** | 0 → **0** |

Two things in that table matter more than the accuracy column:

1. **The classifier's RANKING is already almost right — 30 of 31 — and only the gate is out of
   reach.** The 12-probe sketch above put ranking at 9/12; on a reviewable set that is not
   stacked with near-verbatim exemplars, the mean arm ranks 97% correctly and fires on nothing.
   *"It can't tell intents apart"* was never the problem. **The gate is the whole problem**,
   which is what makes PR-2 a threshold/aggregation decision rather than an exemplar-tuning one.
   Sweep, mean arm: threshold 0.30 → 80% accuracy, 24 of 45 fire, **1** wrong activation.
2. **The magnet is gone.** `"give me an overview of this topic"` matched AGGREGATION at
   **0.792** under `max` — the highest score in the whole set bar the verbatim exemplar — and
   was the ONLY wrong activation any arm produced. After the rewrite it matches
   `prerequisite@0.472`, and `"introduce me to stoicism"` moves from `aggregation@0.313` to
   `exploratory@0.293`. **No topic-orientation query routes to AGGREGATION under any arm** —
   the acceptance bar, met.

**Residuals, recorded rather than tuned away** (a 45-query set is too small to tune against;
none of these fires today):

- Three SPECIFIC rows still take AGGREGATION as their mean-arm argmax — including *"why do I
  regret things I didn't do more than things I did"*. The rewrite made AGGREGATION uniformly
  first-person-possessive, so a first-person question about a SUBJECT drifts toward it. At
  scores of 0.15–0.25 an argmax is noise, not a routing claim; it becomes one only if PR-2
  lowers the gate that far, which the sweep's single wrong activation at 0.30 already prices in.
- `"where should I go after finishing the mindfulness path"` (HIERARCHICAL) is the one ranking
  error on the mean arm, and it lands on AGGREGATION — same possessive pull.
- `"give me an overview of this topic"` no longer resolves to a stable argmax at all: across
  runs it landed on EXPLORATORY (0.342) and then PREREQUISITE (0.320) as near-tied intents
  swapped places. Topic orientation vs catalog browsing is a soft boundary in the embedding
  space even after the object rewrite; the gate is what keeps it harmless.

**Reading the report honestly.** `kind: near_exemplar` rows are UPPER BOUNDS, not evidence —
the instrument now names each row's nearest exemplar and its similarity, so an unmarked
near-duplicate is visible instead of flattering the score. Exactly one row sits within 0.85 of
an exemplar (`"what should I learn next"` ≈ `"What should I learn next?"` @ 0.943), and it is
the deliberate ceiling probe.

### BASELINE — RATIFIED 2026-08-31 (Mike)

`scripts/eval_intent_classification_queries.yaml` carries `ratified: 2026-08-31`; the labels,
and with them ruling 3, are Mike's. **This is the first ratified run — PR-2 is measured against
it.** (AuraDB `d2d160c4`, set v1, 45 queries, gate 0.65, 0 errors, production agreement 45/45
with max score delta 9e-05.)

| arm | accuracy at gate | ranking (gate-blind) | clears the gate | wrong / missed |
|---|---|---|---|---|
| **mean** (production) | **14/45 (31%)** | **30/31 (97%)** | **0** | 0 / 31 |
| max | 23/45 (51%) | 29/31 (94%) | 9 | 0 / 22 |
| top-3 mean | 15/45 (33%) | 29/31 (94%) | 1 | 0 / 30 |

Best-score distribution (min / median / max) — mean **0.112 / 0.314 / 0.540**, max
0.166 / 0.483 / 0.943, top-3 0.142 / 0.402 / 0.734. Median margin over the runner-up: 0.055 /
0.080 / 0.070.

Per-label on the production arm: `specific` **14/14**, every other intent **0/n** — not because
they rank wrong (they rank 30/31 right) but because none of them reaches 0.65. That is the
dormancy, stated as a number.

**The three ranking errors across all arms** (the only ones there are):

| arm | query | labelled | ranked |
|---|---|---|---|
| mean | *"where should I go after finishing the mindfulness path"* | HIERARCHICAL | `aggregation@0.245` |
| max, top-3 | *"what should I learn first to understand compounding"* | PREREQUISITE | `hierarchical@0.527 / 0.472` |
| max | *"what subjects does this cover"* | EXPLORATORY | `hierarchical@0.493` |

The second is the PREREQUISITE/HIERARCHICAL *direction* confusion (first vs next) and the third
is a browsing question read as a progression one — both genuine, neither a set defect.

**Threshold sweep — the input PR-2 re-bases on.** ⚠ Read the **wrong-activation** column, not
accuracy: under ruling 2 a wrong activation routes a question to a tool that answers it
confidently and incorrectly, while a miss just leaves today's behaviour in place. Those are not
symmetric costs, and the arm with the best accuracy is not the arm with the fewest wrong
answers.

| threshold | mean: acc / fire / wrong | max: acc / fire / wrong | top-3: acc / fire / wrong |
|---|---|---|---|
| 0.30 | 80% / 24 / 1 | 80% / 36 / 8 | 84% / 32 / 5 |
| 0.35 | 73% / 19 / **0** | 82% / 33 / 6 | 82% / 28 / 3 |
| 0.40 | 64% / 15 / 0 | 78% / 27 / 4 | 76% / 23 / 2 |
| 0.45 | 44% / 6 / 0 | 78% / 25 / 3 | 67% / 17 / 1 |
| 0.50 | 38% / 3 / 0 | 76% / 21 / 1 | 58% / 12 / **0** |
| 0.55 | 31% / 0 / 0 | 62% / 14 / **0** | 49% / 8 / 0 |
| 0.60 | 31% / 0 / 0 | 58% / 12 / 0 | 42% / 5 / 0 |
| **0.65** (today) | **31% / 0 / 0** | **51% / 9 / 0** | **33% / 1 / 0** |
| 0.70–0.80 | 31% / 0 / 0 | 40→33% / 4→1 / 0 | 33→31% / 1→0 / 0 |

**What that says, and it is the opposite of "raise the aggregation".** Every arm has a
zero-wrong-activation threshold. Compare them at that frontier — the only comparison that
matters if a wrong activation is the expensive error.

⚠ **Compare at the EXACT frontier, not at a ladder step.** The frontier is pinned by a single
query — the highest-scoring mis-route — and the 0.05 sweep rounds that up to the next step,
crediting an arm with a stricter gate and fewer activations than it actually needs. Rounding
understated all three arms and narrowed nothing consistently, so it could have inverted the
comparison (Codex, #1206). `zero_wrong_frontier` in the report computes it at observed scores:

| arm | exact zero-wrong gate | activates | accuracy | pinned by |
|---|---|---|---|---|
| **mean** (production) | **0.3329** | **21 of 45** | **78%** | *"give me an overview of this topic"* @ 0.320 |
| max | 0.5353 | 17 of 45 | 69% | *"what should I learn first to understand compounding"* @ 0.527 |
| top-3 mean | 0.4911 | 15 of 45 | 64% | same query @ 0.472 |

The mean arm wins on both columns, and the arms fail differently: the mean's frontier is pinned
by the topic-orientation probe, the other two by the PREREQUISITE/HIERARCHICAL *direction*
confusion. Fix the pinning query's routing and that arm's gate can come down.

**The production aggregation wins on its own terms.** It activates the most queries without
mis-routing any AND scores highest doing it; `max` and `top3_mean` reach their higher *ladder*
accuracy only by firing past their own frontier, where they mis-route 3–8. So the mechanism does
not need replacing — **moving the gate on the aggregation we already have is the smaller and
safer change.**

⚠ **Do not adopt 0.3329 as the gate.** A frontier value IS an observed score, and scores move
between runs (the production-agreement delta is 1e-4 – 3e-4, and re-embedding is not
bit-identical). A gate set exactly at the frontier sits 0.013 above the mis-route that pins it
and could flip on a re-run. **0.35 is the proposal**: it clears the pinning score (0.320) by
0.03 — two orders of magnitude more than the observed drift — and costs 2 activations (19 rather
than 21). The frontier's value is the comparison BETWEEN arms; it is not a threshold to copy.

Two further caveats before any of this becomes a decision: 45 queries is a thin base for a
threshold (each mis-route is 2.2 points), and the frontier is measured on a set containing no
adversarial phrasing.

⚠ **The baseline makes ruling 2's coverage gate URGENT, not theoretical.** At **either**
candidate threshold, **all 6 of 6 AGGREGATION queries fire** — it is the best-separated intent in
the set. So the moment PR-2 lowers the gate, count questions classify, and the tool catalog's
first slice covers neither the bare count nor the predicate-bearing shape. PR-2 must therefore
land the tool-selection first slice WITH it, or hold `AGGREGATION` out of the reachable set until
that exists. There is no threshold that activates the other five intents while leaving
AGGREGATION dormant.

### PR-2 — activation (behaviour change, narrow)

⚠ **The ratified baseline changed this PR's shape. Re-read this section; it was rewritten
2026-08-31 against the measurement, and the pre-baseline framing was wrong in its central
claim.** That framing said *"the value of 0.65 is not the question; the mechanism is"* — the
aggregation was assumed to be the defect and the threshold a symptom. The baseline says the
reverse: the production `mean` aggregation **ranks 30 of 31 correctly** and, at its exact
zero-wrong gate, both activates more queries and scores higher than either alternative (21/45 at
78%, vs max 17/45 at 69% and top-3 15/45 at 64%). The mechanism is not the defect. **The value is the question**, and it is a one-line change to
`IntelligenceThreshold.INTENT_CLASSIFICATION` (`core/constants.py:293`).

**That relocates the whole risk of this PR.** Nothing subtle happens in the classifier; the
subtle things happen in the five branches downstream that have never executed. Budget the review
accordingly: the constant is the easy part.

#### The proposal, and what would reject it

**Keep `mean`; move the gate to 0.35.** On the ratified set that is 19 of 45 queries activating
with **zero** wrong activations, all six intents represented. ⚠ Deliberately NOT the exact
frontier (0.3329, 21 queries): a frontier value is an observed score and drifts between runs,
while 0.35 clears the mis-route pinning it (0.320) by 0.03 — see the baseline. Reject the
proposal if any of these turn out true — each is a real check, not a formality:

- **A wrong activation appears off-set.** The zero-wrong frontier is measured on 45 queries with
  no adversarial phrasing. One mis-route is 2.2 points of accuracy and, under ruling 2, a
  user-visible wrong answer. If before/after surfaces a mis-route the set does not contain, the
  gate moves up, not the aggregation sideways.
- **0.30 is argued for on accuracy.** It scores higher (80% vs 73%) and activates 24, but it
  mis-routes *"give me an overview of this topic"* → `prerequisite@0.320`. Accuracy is the wrong
  column; the wrong-activation column is the one that costs a user something.
- **AGGREGATION cannot be answered yet** — see the sequencing constraint below. That does not
  reject 0.35; it decides whether AGGREGATION is in the reachable set at all.

#### What actually activates at 0.35 — it is lopsided, and the before/after must follow it

| classified intent | fires (of 45) | what that means for validation |
|---|---|---|
| AGGREGATION | **6** | the most-activated intent — and the one with nothing behind it yet |
| EXPLORATORY | **5** | activates the own-graph overview branch (ruling 3: correct as written) |
| PREREQUISITE | 3 | + citations |
| HIERARCHICAL | 2 | + citations |
| PRACTICE | 2 | task-count branch |
| RELATIONSHIP | **1** | barely reachable — one query in 45 |

⚠ So *"five branches start running for every Askesis turn"* — the pre-baseline framing — is
wrong in emphasis. **Activation is partial and uneven.** Two intents carry 11 of the 19 firings;
RELATIONSHIP fires once. A before/after that samples questions uniformly will barely exercise
half of what it is meant to validate. **Drive the branches that actually fire, and drive
RELATIONSHIP deliberately rather than hoping a sample reaches it.**

#### The work

- **Move the threshold, and move its documentation in the same change — SEVEN places, not four.**
  The change-detector in `tests/unit/test_askesis_intent_filter_activation_guard.py` fires
  precisely so this cannot be forgotten, and its failure message carries the list:
  1. `core/constants.py` — the constant, and the comment above it explaining why 0.65 was strict
     (that explanation stops being true).
  2. [deferred-work.md](deferred-work.md) — Named work 4.
  3. [ASKESIS_HOW_IT_WORKS.md](../architecture/ASKESIS_HOW_IT_WORKS.md) — the measured-inert box.
  4. [ASKESIS_RAG_PIPELINE.md](../guides/ASKESIS_RAG_PIPELINE.md) — Step 5a.
  5. `docs/intelligence/ASKESIS_INTELLIGENCE.md` — "≥0.65 threshold", stated as live behaviour.
  6. [askesis-tool-selection-queries.md](askesis-tool-selection-queries.md) — **twice**: the
     trigger and the AGGREGATION-gap argument, both of which rest on the gate being unreachable.
     ⚠ Those two are not documentation of the threshold; they are ARGUMENTS that stop holding.
  7. `docs/INDEX.md` — the arc's one-line summary.

  ⚠ Entries 5–7 were missing from this list until a review found them (Codex, #1206), which is
  the point: **re-derive it** with `git grep -n '0\.65' -- docs core` rather than trusting the
  enumeration. A checklist of references decays exactly like the references it lists.
- ⚠ **Re-point the eval's own acceptance message — it will cry failure on a CORRECT PR-2 run.**
  `scripts/eval_intent_classification.py` prints *"⚠ PR-1 ACCEPTANCE FAILS: N query(ies) clear
  the live gate"* whenever anything fires (`_print_human`, and the condition is stated in the
  module docstring). That was PR-1's acceptance condition; after PR-2 a non-zero `cleared_gate`
  is the **intended** state. Left alone, the instrument that measures this arc reports success as
  failure. Replace it with what PR-2 actually cares about: **wrong activations must stay at 0**.
- **`chunk_types` stays off.** State the reason at the site, not in a commit message.
- ✅ **`retrieve_relevant_context`'s `EXPLORATORY` branch is activated AS WRITTEN.** It injects an
  overview of the user's own graph, which is what catalog browsing asks for — and browsing is what
  EXPLORATORY means (ruling 3). The conditional rewrite this section used to carry was contingent
  on PR-1 choosing topic orientation; it did not, so there is nothing to rewrite.
- ⚠ **`AGGREGATION` must not become reachable before something can answer it — and no threshold
  avoids it.** All **6 of 6** AGGREGATION queries fire at both candidate gates; it is the
  best-separated intent in the set. There is no gate that activates the other five while leaving
  this one dormant, so this is a **sequencing constraint, not a risk to monitor**: either the
  tool-selection first slice ([askesis-tool-selection-queries.md](askesis-tool-selection-queries.md))
  lands **with** this PR, or PR-2 holds `AGGREGATION` out of the reachable set explicitly. A
  window where the intent classifies with nothing behind it answers count questions with an
  invented number — a regression, not a staging step. (Codex, #1202.)
- ⚠ **Citations become POSSIBLE for the first time ever — on at most ~11% of questions, and
  probably fewer. Activation opens only the first of two gates.** `PREREQUISITE` and
  `HIERARCHICAL` fire on **5 of 45** at 0.35, but the call site
  (`query_processor.py:379–386`) then requires `extracted_entities["knowledge"]` to be non-empty
  and to carry a `uid`, and `_retrieve_citations_for_knowledge_units` applies
  `min_evidence_count=1` on top. **Those 5 rows are citation CANDIDATES, not citations.** The
  eval cannot tell you the real rate: it measures classification and never exercises entity
  extraction. So:
  - **Do not read "no citations appeared" as "activation did nothing"** — it is far more likely
    the second gate, and diagnosing it as the first would send PR-2 chasing the threshold.
  - The before/after must use questions that **name a corpus concept** ("what do I need before
    *the eight-fold path*"), not merely prerequisite-shaped phrasing — otherwise extraction
    resolves nothing and the branch stays dark whatever the gate does.
  - **Measure and record the real activation rate**; it is unknown today, and this PR is the
    first thing that can find out. Check the citation block renders where the answer is
    displayed. (Codex, #1206.)
- ⚠ **Both callers get before/after, not just the chat surface.** `process_query_with_context`
  has its own prose branch and its own actions method; validating only `answer_user_question`
  would ship the API's change unmeasured.
- ⚠ **Read the right output for each path** (per the fork table above): on the context-aware path
  read the ANSWER prose; on the guided path read `suggested_actions`, `context_used` and
  citations, because the prose cannot change there. Scoring "no answer change" on the guided path
  as a null result would be measuring a wire that isn't connected.
- ⚠ `SPECIFIC` must stay unmapped in `_INTENT_CHUNK_TYPES` — it is the outage fallback, and the
  activation guard pins this.
- **Re-run `./dev eval-intent-classification` after the change and record it.** The baseline is a
  pre-activation measurement of a classifier nothing consumed; the post-activation run is the
  first time these numbers describe behaviour a user can receive. `wrong_activations` on the mean
  arm is the number to carry forward.

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
# PR-1's instrument: 45 labelled queries x 3 aggregation arms, checked against production.
# `cleared_gate` on the mean arm is the acceptance condition; the sweep is PR-2's input.
./dev eval-intent-classification            # human summary
./dev eval-intent-classification --json     # the recorded report

# the gate is unreachable — every query classifies SPECIFIC (max_intent_score vs 0.65)
./dev eval-askesis-draw
```

```cypher
// what the PR-3 filter would filter on; `introduction` has never matched a row
MATCH (c:ContentChunk) RETURN c.chunk_type AS t, count(*) AS n ORDER BY n DESC
```

**Trigger:** PR-1 DONE 2026-08-31. PR-2 on PR-1's ratified baseline. PR-3 only
if the content-typing classifier lands AND its distribution makes a type filter meaningful.
