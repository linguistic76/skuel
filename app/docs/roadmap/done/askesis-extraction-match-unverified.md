---
title: "Askesis Entity-Extraction Match Is Unverified"
updated: 2026-09-14
status: "done — `test_ask_endpoint_entity_extraction` asks the question that names the in-progress PathStep and asserts the match and `has_citations is True`; the two design observations moved to askesis-extraction-lookup-shape.md"
trigger: "any change to EntityExtractor, to known_or_engaged_ku_uids, to the MEGA-QUERY KNOWLEDGE section, or to the PREREQUISITE / HIERARCHICAL citations branch of QueryProcessor — or the next time test_askesis_ask_endpoint.py is opened for any reason"
check: "grep -c 'Extracted 1 entities' in a `-s` run of tests/integration/test_askesis_ask_endpoint.py — exactly one live question logs a match, and the module asserts on `mentioned_entities` and `has_citations`"
registered: "2026-09-13 (PR #1326 — found while diagnosing the pipeline timeout; spec corrected after Codex review of #1327 and a live probe)"
---

# Askesis Entity-Extraction Match Is Unverified

**Status: ✅ DONE — 2026-09-13.** `test_ask_endpoint_entity_extraction` now asks *"What do I need
to know before Test Guided PathStep?"*, asserts the in-progress PathStep is in
`mentioned_entities.knowledge`, and asserts the answer carries the Sources & Evidence section
naming the step's evidenced prerequisite (`has_citations is True` alongside); the `-s` log of
the module carries exactly one `Extracted 1 entities` line (intent `prerequisite`,
`citations: yes`). The two design observations recorded below are tracked in
[../askesis-extraction-lookup-shape.md](../askesis-extraction-lookup-shape.md). The rest of this
file is the investigation as it stood when the test landed.

**What running the branch found (three defects, all fixed in the test's PR):** the citation
export walked `REQUIRES_KNOWLEDGE` *backwards* (`(node)<-[…]-(prereq)`, reporting a node's
dependents as its prerequisites — every writer records the edge outgoing, per the graph
contract); an empty `CitationBundle` formatted to the truthy placeholder *"No citations
available for this knowledge unit."*, so `has_citations` was `True` with zero citations
(the first draft of this test asserted exactly that, and would have passed on the
placeholder — Codex, #1329); and `test_ask_endpoint_validation`'s `with TestClient(app)`
ran the ASGI lifespan, whose shutdown closed the session-scoped app's driver for every
test after it — the neo4j driver keeps answering after `close()` (deprecation warning),
but every `_is_driver_closed()`-guarded backend read returned nothing, silently. That is
why the branch's output was invisible in a module run and visible in a single-test run.

## The gap

No test in the suite has ever observed `EntityExtractor.extract_entities_from_query` **match** an
entity into `context_used["mentioned_entities"]["knowledge"]`, and therefore none has ever
observed the citations branch of `QueryProcessor._answer_user_question_pipeline` run — it runs
only for `PREREQUISITE` / `HIERARCHICAL` intents **with** a matched knowledge entity. Every live
question in `tests/integration/test_askesis_ask_endpoint.py` logs `Extracted 0 entities from
query`; `test_ask_endpoint_entity_extraction` asserts the *shape* of `mentioned_entities` only
**when present**, which it never is.

Two things hid it: the PS-first enrollment gate turned the two `populated_test_data` tests into
gate tests (fixed in PR #1326 — they now run as the enrolled learner), and none of the questions
asked names anything the learner is engaged with.

## What extraction actually resolves — read this before touching the fixture

`extract_entities_from_query` scopes "knowledge" to `user_context.known_or_engaged_ku_uids()`
(= `mastered ∪ in_progress ∪ blocked`) and resolves each uid through **`self.knowledge_service`,
which the factory wires as `learning_services["ps"]`** — `PsService`, typed
`EntityLookup[PathStep]` (`core/services/askesis_factory.py`). The sets themselves are filled by
the MEGA-QUERY KNOWLEDGE section from `(user)-[:MASTERED|IN_PROGRESS]->(ku:Entity)` — any
Entity, because both edges are written to `(t:Entity {uid})` by `user_backend.py`, and the
`IN_PROGRESS` edge the engagement door writes points at a **PathStep**.

So the sets hold a mix of PathStep uids (in-progress steps, score `coalesce(progress, 0.1)`) and
Ku uids (mastered knowledge, score 1.0) — and only the PathStep uids resolve. A `:Ku` uid
returns not-found from `PsService.get()` before fuzzy matching ever runs. **Adding a learner→Ku
edge to a fixture therefore cannot produce a match** (the first draft of this file prescribed
exactly that; Codex caught it on #1327).

Probed live against the enrolled fixture, 2026-09-13:

```
known_or_engaged_ku_uids: ['ps:test:guided-step']      # the PathStep — via the fixture's existing IN_PROGRESS edge
"What do I need to know before Test Guided PathStep?"
  -> intent: prerequisite, mode: guided
  -> mentioned_entities.knowledge: [{'uid': 'ps:test:guided-step', 'title': 'Test Guided PathStep'}]
  -> has_citations: True                                  # the citations branch ran and produced text
```

The match is reachable **today, with the fixture exactly as it is**.

## The change — build it, don't schedule it

In `test_ask_endpoint_entity_extraction`:

1. **Question**: one that names the in-progress PathStep's title and classifies `PREREQUISITE` —
   *"What do I need to know before Test Guided PathStep?"* did, live. Read the classified intent
   off the `-s` log the first time; the exemplar set changes.
2. **Assertions** — replace the conditional shape check with two facts the probe observed:
   ```python
   knowledge = data["context_used"]["mentioned_entities"]["knowledge"]
   assert any(k["uid"] == enrolled_user_with_lp["ps_uid"] for k in knowledge)
   assert data["has_citations"] is True  # the PREREQUISITE + matched-entity branch produced citation text
   ```
   `has_citations` is `bool(citations_text)` and the key is always present, so asserting its
   *existence* proves nothing (Codex, #1327); asserting `True` is the branch's observable output —
   a regression that drops the `_retrieve_citations_for_knowledge_units` call fails it.
3. **`test_ask_endpoint_semantic_search`** keeps its no-keyword question and gains the sentence
   that it is the other half: the pipeline answers when extraction finds *nothing*.

No fixture change. Cost: one warm live question (~3 s), already paid by the test.

## Two design observations this surfaced — tracked in [../askesis-extraction-lookup-shape.md](../askesis-extraction-lookup-shape.md)

**1. "Knowledge" extraction never matches a mastered Ku, and pays a round-trip to find out.**
Every Ku uid in `mastered_knowledge_uids` is passed to `PsService.get()`, fails, and is skipped
silently — one Neo4j round-trip each, per question. Whether extraction *should* match Kus
(the atomic ontology node) or PathSteps (THE curriculum content entity, per `CLAUDE.md`) is a
product question; the extractor's type says PathStep, the MEGA-QUERY feeds it both. Either
resolve Kus through `KuService` or stop feeding Ku uids to a PathStep lookup — but decide which
first.

**2. `_extract_matching_entities` is N sequential round-trips per question.** It awaits
`service.get(uid)` one uid at a time, for every uid in seven sets (known KUs, active tasks, active
goals, active habits, today + upcoming events, core principles, pending choices), inside the 30 s
`AskesisPipelineTimeout`. That is the exact shape PR #1326 removed from the intent-exemplar load
— except this one is **per question** and grows with the learner: 40 tasks + 20 goals + 30 habits
+ 100 mastered Kus ≈ 190 sequential round-trips ≈ 10–19 s on AuraDB from this machine, every
question. The rich context already carries `entities_rich[...]` with titles for the six activity
domains and `knowledge_rich` for curriculum — the titles are in memory before extraction starts.
Match against the context; do not re-fetch it. The fix is the same size as #1326's.

(Also noted: fuzzy strategy 2 matches any title word longer than three characters — the probe
matched "Test Guided PathStep" from a question about "Test Guided Concept". Loose by design;
recorded so nobody reads a match as precision.)

## Ruled

- **Not a retry, not a stub.** The match is verifiable against the live pipeline in one warm
  question; stubbing the extractor would test the stub.
- **The corpus lives on the learner, not in a global search.** Extraction's scope is
  deliberately the learner's own engaged entities; a test wanting a *global* match would be
  testing a scoping the product does not have.
- **`populated_test_data`'s KUs stay `:Entity` without `:Ku`.** Its consumers only need nodes to
  exist; fix the label the first time a test needs them resolvable, not speculatively.

## Related

- PR #1326 — the diagnosis that found this; the two tests now reach the pipeline.
- PR #1327 — this file's first draft, corrected after Codex review and the live probe.
- [../askesis-intent-classification-activation.md](../askesis-intent-classification-activation.md) —
  the intent side of the same pipeline; the `PREREQUISITE` exemplar shapes live in
  `core/services/askesis/intent_classifier.py`.
- [mega-query-plan-cache-cliff.md](mega-query-plan-cache-cliff.md) — the sibling finding from
  the same investigation; the KNOWLEDGE section it bisects is the one that feeds these sets.
