---
title: "Askesis Entity Extraction — Ku Uids Never Resolve, and the Lookup Is N Round-Trips per Question"
updated: 2026-09-14
status: "done — extraction matches in memory against the rich context (zero graph reads per question) and "knowledge" matches both Kus and PathSteps, each carrying entity_type; ruled by Mike 2026-09-13 (match both)"
trigger: "any change to EntityExtractor or to what the knowledge statement feeds known_or_engaged_ku_uids"
check: "tests/unit/test_askesis_entity_extractor.py::test_the_extractor_reaches_no_service (no service handle exists to read through) and tests/integration/test_askesis_ask_endpoint.py::test_ask_endpoint_matches_a_mastered_ku (a mastered Ku named in a question is matched, typed ku)"
registered: "2026-09-13 (split out of the extraction-match case file when its test landed)"
---

# Askesis Entity Extraction — Ku Uids Never Resolve, and the Lookup Is N Round-Trips per Question

**Status: ✅ DONE — 2026-09-13.** Both observations closed by one change: `EntityExtractor`
matches in memory against the rich context, with no service handle at all, and "knowledge"
matches every MASTERED | IN_PROGRESS target — Ku and PathStep alike — each match carrying the
node's `entity_type`. See *What landed* at the end.

Two observations recorded while verifying the extraction match
([askesis-extraction-match-unverified.md](askesis-extraction-match-unverified.md)
holds the probe and the test that now pins it). Neither is a test question; both are
design questions about `EntityExtractor` (`core/services/askesis/entity_extractor.py`).

## 1. "Knowledge" extraction never matches a mastered Ku — and pays a round-trip to find out

`extract_entities_from_query` scopes "knowledge" to `user_context.known_or_engaged_ku_uids()`
(= mastered + in_progress + blocked) and resolves each uid through `self.knowledge_service`,
which the factory wires as `learning_services["ps"]` — `PsService`, typed
`EntityLookup[PathStep]` (`core/services/askesis_factory.py`). The sets are filled by the
MEGA-QUERY KNOWLEDGE section from `(user)-[:MASTERED|IN_PROGRESS]->(ku:Entity)` — any Entity,
because both edges are written to `(t:Entity {uid})` by `user_backend.py`, and the
`IN_PROGRESS` edge the engagement door writes points at a **PathStep**. So the sets hold a mix
of PathStep uids (in-progress steps) and Ku uids (mastered knowledge) — and **only the PathStep
uids resolve**. Every Ku uid is passed to `PsService.get()`, fails, and is skipped silently:
one Neo4j round-trip each, per question.

Whether extraction *should* match Kus (the atomic ontology node) or PathSteps (THE curriculum
content entity, per `CLAUDE.md`) is a product question; the extractor's type says PathStep,
the MEGA-QUERY feeds it both. Either resolve Kus through `KuService` or stop feeding Ku uids
to a PathStep lookup — but decide which first.

## 2. `_extract_matching_entities` is N sequential round-trips per question

It awaits `service.get(uid)` one uid at a time, for every uid in the five sets the extractor
fetches — known KUs, active tasks, active goals, active habits, today + upcoming events
(`principles` and `choices` are hard-coded to `[]` in `extract_entities_from_query`; they are
not looked up at all, which is its own unwired surface) — inside the 30 s
`AskesisPipelineTimeout`. That is the exact shape PR #1326 removed from the intent-exemplar
load — except this one is **per question** and grows with the learner: 40 tasks + 20 goals +
30 habits + 100 mastered Kus ≈ 190 sequential round-trips ≈ 10–19 s on AuraDB from a
developer machine, every question. The rich context already carries `entities_rich[...]`
with titles for the six activity domains and `knowledge_rich` for curriculum — the titles
are in memory before extraction starts. Match against the context; do not re-fetch it. The
fix is the same size as #1326's.

(Also noted: fuzzy strategy 2 matches any title word longer than three characters — the
probe matched "Test Guided PathStep" from a question about "Test Guided Concept". Loose by
design; recorded so nobody reads a match as precision.)

## What landed

**The decision (Mike, 2026-09-13): match both.** "Knowledge" extraction matches every target of the
learner's `MASTERED | IN_PROGRESS` edges — the concept and the step alike — and each match carries
the node's `entity_type`, so a reader tells a Ku from a PathStep by the label-derived field, never
by the uid's spelling (ADR-013). The facts that made it the right call: `known_or_engaged_ku_uids`
is by its own docstring "knowledge the learner has any relationship with"; the rich context holds
titles for both kinds (`knowledge_units_rich` is keyed by exactly those targets); and both consumers
of the matches accept either uid — the prompt's "Entities User Asked About" block, and the
PREREQUISITE / HIERARCHICAL citations branch, whose export query matches `(end:Entity {uid})`.

**The shape.** `EntityExtractor` holds no service handle. `extract_entities_from_query` is
synchronous: it reads `entities_rich` (tasks, goals, habits, events — and now principles and
choices, which were hard-coded `[]`) and `knowledge_units_rich`, scopes each domain to the uids the
standard context marks live (open tasks, active goals and habits, today's and upcoming events, core
principles, pending choices, engaged knowledge), and fuzzy-matches titles. The processor's Step 5
lost its `await` and the `try/except` that only existed because extraction hit the database.
`AskesisDeps`' five service fields stay — `ContextRetriever` reads them — and `EntityLookup` stays
for its `ps_service`. Neither `blocked_knowledge_uids` (derived from `prerequisites_needed`, which
has no writer) nor the fuzzy matcher changed: a shared significant word is a match by design, and a
match is a mention, not a resolution.

**Measured on the testcontainer, through the running app** (a learner seeded in every section —
the `test_rich_context_statement_equivalence` graph — then the same learner with 100 open tasks):
before, `extract_entities_from_query` made **11 sequential `service.get` awaits per question**
(4 knowledge, two of them Ku uids `PsService` can never resolve; 2 tasks; 1 goal; 2 habits;
2 events) in 199 ms, and **111 awaits in 720 ms** for the fat learner — ~6.5 ms per await on
localhost, ~200 ms each on AuraDB, so ~22 s of the 30 s pipeline budget. After: **0 awaits,
0.23 ms and 0.58 ms**, the same matches plus the principle the old code never looked at.

**Proven to fail first:** `test_ask_endpoint_matches_a_mastered_ku` — the fixture's Ku "Test Guided
Concept" mastered, the question naming it verbatim — matched only the PathStep on the old code
(`knowledge = {'ps:test:guided-step': …}`); it now matches both, the Ku typed `ku`, the step
`path_step`. The pinned PathStep match and its citations (`test_ask_endpoint_entity_extraction`)
pass unchanged. The extractor's unit tests, which asserted only `isinstance(entities, dict)`, now
pin each fuzzy strategy against a real `RichUserContext`, the live-scope filter (a completed task
inside the window is a rich row but not a candidate), and that no `_service` attribute exists.

## Related

- [askesis-extraction-match-unverified.md](askesis-extraction-match-unverified.md) —
  the investigation these came out of; `test_ask_endpoint_entity_extraction` is the pinned match.
- [../askesis-intent-classification-activation.md](../askesis-intent-classification-activation.md) —
  the intent side of the same pipeline.
- PR #1326 — the concurrent exemplar load that observation 2 mirrors.
