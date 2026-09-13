---
title: "Askesis Entity Extraction — Ku Uids Never Resolve, and the Lookup Is N Round-Trips per Question"
updated: 2026-09-13
status: "open — two observations from the extraction-match investigation; the product question (Kus or PathSteps?) has to be decided before either is coded"
trigger: "any change to EntityExtractor._extract_matching_entities or to what the MEGA-QUERY KNOWLEDGE section feeds known_or_engaged_ku_uids — or a learner with more than a few dozen engaged entities reporting slow Askesis answers"
check: "count the `service.get(uid)` awaits per question in EntityExtractor._extract_matching_entities against a learner with N engaged entities: today it is N sequential round-trips; closed when matching reads the titles already on the rich context (zero per-question lookups) AND every uid fed to the knowledge lookup is of the type that lookup resolves"
registered: "2026-09-13 (split out of the extraction-match case file when its test landed)"
---

# Askesis Entity Extraction — Ku Uids Never Resolve, and the Lookup Is N Round-Trips per Question

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Two observations recorded while verifying the extraction match
([done/askesis-extraction-match-unverified.md](done/askesis-extraction-match-unverified.md)
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

## Related

- [done/askesis-extraction-match-unverified.md](done/askesis-extraction-match-unverified.md) —
  the investigation these came out of; `test_ask_endpoint_entity_extraction` is the pinned match.
- [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md) —
  the intent side of the same pipeline.
- PR #1326 — the concurrent exemplar load that observation 2 mirrors.
