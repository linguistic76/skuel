---
title: "Askesis Entity-Extraction Match Is Unverified"
updated: 2026-09-13
status: "open — specified, not built (one fixture edge + one question + one assertion)"
trigger: "any change to EntityExtractor, to known_or_engaged_ku_uids, or to the PREREQUISITE / HIERARCHICAL citations branch of QueryProcessor — or the next time test_askesis_ask_endpoint.py is opened for any reason"
check: "grep -c 'Extracted 0 entities' in a `-s` run of tests/integration/test_askesis_ask_endpoint.py — every live question in the module logs 0 today; the task is closed when at least one logs a match and asserts on it"
registered: "2026-09-13 (PR #1326 — found while diagnosing the pipeline timeout)"
---

# Askesis Entity-Extraction Match Is Unverified

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The gap

No test in the suite has ever observed `EntityExtractor.extract_entities_from_query` **match** a
knowledge unit and carry it into the answer as `context_used["mentioned_entities"]`. Every live
question in `tests/integration/test_askesis_ask_endpoint.py` logs `Extracted 0 entities from
query`, and `test_ask_endpoint_entity_extraction` — the test named for it — asserts only the
*shape* of `mentioned_entities` **when present**, which it never is.

Two things hid this, in sequence:

1. **The PS-first enrollment gate (July 2026)** turned the two "pipeline" tests that used
   `populated_test_data` into gate tests: that fixture's user has no PathStep and no Learning
   Path, so `answer_user_question` returned the enrollment-gate short-circuit — no intent, no
   extraction, no LLM — and the shape assertions passed on the gate's response. PR #1326 moved
   both tests onto `enrolled_user_with_lp` and asserts `mode != "enrollment_gate"`, so they now
   run the pipeline.
2. **Neither fixture gives the learner a KU that extraction can see.** Extraction is scoped to
   `user_context.known_or_engaged_ku_uids()` = `mastered ∪ in_progress ∪ blocked`, and the
   MEGA-QUERY's KNOWLEDGE section fills those from edges **directly on the user**:
   `(user)-[:MASTERED|IN_PROGRESS]->(ku:Entity)`. `enrolled_user_with_lp` puts `IN_PROGRESS` on
   the *PathStep* and links the PathStep to its Ku by `CONTAINS_KNOWLEDGE` — the learner never
   touches the Ku. `populated_test_data`'s three KUs are `MERGE (k:Entity {uid})` with no `:Ku`
   label and no learner edge at all, so even before the gate existed they were invisible to
   extraction, and `KuService.get(uid)` would not have resolved them.

So the extraction → `mentioned_entities` → citations path (`_retrieve_citations_for_knowledge_units`
runs only for `PREREQUISITE` / `HIERARCHICAL` intents **with** matched knowledge entities) has no
regression test. A change that broke fuzzy matching, the uid scoping, or the citations branch
would pass the module.

## What a verifying test needs — the whole specification

Extraction matches when all four hold; the enrolled fixture already gives three of them:

| Requirement | Source | `enrolled_user_with_lp` today |
|---|---|---|
| Learner passes the enrollment gate | `_passes_enrollment_gate` — `current_ps_uids` or `enrolled_path_uids` | ✅ `IN_PROGRESS → PathStep`, `ENROLLED_IN → LearningPath` |
| The KU is a `:Entity:Ku` node with `entity_type = 'ku'` | `KuService.get(uid)` resolves by label | ✅ `ku_test_guided_concept`, title "Test Guided Concept" |
| The KU is in `known_or_engaged_ku_uids()` | `(user)-[:MASTERED\|IN_PROGRESS]->(ku)` in the MEGA-QUERY KNOWLEDGE section | ❌ **missing** — the edge is on the PathStep, not the Ku |
| The question contains the KU's title | `EntityExtractor._fuzzy_match(entity.title, query_lower)` | ❌ the current questions name "async programming", which no fixture KU is titled |

### The change (small — build it, don't schedule it)

1. **Fixture** — in `tests/integration/conftest.py::enrolled_user_with_lp`, one more statement
   after the PS→Ku link:
   ```cypher
   MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $ku_uid})
   MERGE (u)-[r:IN_PROGRESS]->(k)
   SET r.progress = 0.1
   ```
   `IN_PROGRESS` rather than `MASTERED` so the guided pipeline's "non-mastered candidate"
   condition (`test_guided_pipeline_activates`) is untouched. The teardown already deletes by
   uid list, which takes the edge with it.
2. **Question** — `test_ask_endpoint_entity_extraction` asks a question that names the KU and
   classifies `PREREQUISITE`, e.g. *"What do I need to know before Test Guided Concept?"*
   (the `PREREQUISITE` exemplars are "What do I need to learn before …" shapes — check the
   classified intent in the `-s` log, not assume it).
3. **Assertions** — replace the conditional shape check with:
   ```python
   knowledge = data["context_used"]["mentioned_entities"]["knowledge"]
   assert any(k["uid"] == enrolled_user_with_lp["ku_uid"] for k in knowledge)
   ```
   and, because a matched knowledge entity on a `PREREQUISITE` question is exactly what turns
   the citations branch on, assert `"has_citations" in data` and record which value it takes —
   the fixture KU has no evidence, so it is expected `False`; the point is that the branch ran.
4. **`test_ask_endpoint_semantic_search`** keeps its no-keyword question; it exists to show the
   pipeline answers when extraction finds *nothing* — say so in its docstring so the pair reads
   as the two halves they are.

### What this does NOT close

`populated_test_data`'s KUs remain `:Entity` without `:Ku` — every consumer of that fixture
(`test_enrollment_gate_fires`, and the RAG-wiring module) only needs *some* nodes to exist, so
this is cosmetic until a test needs them resolvable through `KuService`. Fix it the first time
one does; do not fix it speculatively.

## Ruled

- **Not a retry, not a stub.** The match is verifiable against the live pipeline in one warm
  question (~3 s); stubbing the extractor would test the stub.
- **The corpus lives on the learner, not in a global search.** Extraction's scope is
  deliberately the learner's own KUs (`known_or_engaged_ku_uids`, see the docstring on
  `EntityExtractor.extract_entities_from_query`). A test that wanted a *global* match would be
  testing a scoping the product does not have.

## Related

- PR #1326 — the diagnosis that found this; the two tests now reach the pipeline.
- [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md) —
  the intent side of the same pipeline; the `PREREQUISITE` exemplar shapes live in
  `core/services/askesis/intent_classifier.py`.
