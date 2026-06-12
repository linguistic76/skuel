# Investigation Prompt: Journal Pipeline Wiring + Report Domain Convergence

> **How to use:** paste the prompt below into a FRESH Claude Code session (clean context).
> Memory has been updated (`journals-ingestion-reports-direction`) so the session will recall
> the rulings; this prompt carries the full brief regardless.

---

## Prompt

Investigate and design two connected capabilities for SKUEL. This is a design investigation —
the deliverable is a decision document + implementation plan (an ADR if warranted), not code.
Read `docs/decisions/ADR-054-user-entry-unified-submissions.md` (including the Postscript) and
the PLANNED-tier DSL entries in `scripts/detect_bloat.py` before forming opinions.

### Background (settled — do not re-litigate)

- **Journals are UserEntries** (ADR-054): `Pipeline.TRANSCRIBE_AND_STRUCTURE` is the live
  journal pipeline (audio → Deepgram → LLM structuring → second UserEntry via `TRANSFORMS`
  edge, forced PRIVATE). Journals currently feed NO downstream consumer (ZPD journal signal
  removed in #183; the 0.07/entry substance channel is RESERVED; ActivityReports don't read
  UserEntries).
- **Ruling 1 (Mike, 2026-06-12):** wire `Pipeline.EXTRACT_ACTIVITIES` — the staged DSL parser
  (`core/services/dsl/activity_extractor.py`, PLANNED tier) becomes a
  `UserEntryProcessingService.process()` pipeline step, with `llm_dsl_bridge.py` as an
  optional LLM pre-pass converting free prose → DSL before deterministic extraction.
  "Parser vs LLM" is resolved: both, composed. NEVER resurrect the retired ADR-054
  submission-metadata flow.
- **Ruling 2 (Mike, 2026-06-12):** ExerciseReport stretches to cover LLM-authored responses
  to journal-pipeline UserEntries — `ReportSource.LLM` + owner-only visibility. No new
  EntityType. Journal privacy policy unchanged (`Pipeline.allows_sharing()` stays False for
  TRANSCRIBE_AND_STRUCTURE).

### Investigate

1. **EXTRACT_ACTIVITIES wiring design** — where the new `Pipeline` value slots into
   `user_entry_processing_service.py`; how extracted entities link back to the source
   UserEntry (graph edges — consider `TRANSFORMS` precedent); how this un-reserves the
   0.07/entry substance channel and what a restored journal-shaped ZPD signal looks like
   (ZoneEvidence currently counts 3 signal types; compound evidence needs 2+); idempotency
   (re-processing must not duplicate entities); failure semantics when the bridge LLM call
   is unavailable at CORE tier (deterministic parser should still work on tagged prose —
   Analog-layer-complete principle).

2. **ExerciseReport ↔ ActivityReport alignment and coherence** — this is the heart of the
   investigation. Today: ExerciseReport is singular-scope, graph-native
   (`-[:REPORT_FOR]->` UserEntry), loop-gating, mastery-propagating; ActivityReport is
   aggregate-scope, denormalized (no REPORT_FOR), loop-peripheral. Questions to answer with
   evidence from the code:
   - Does ActivityReport have any influence on (or overlap with) the journal-response
     design? E.g. should a periodic ActivityReport *read* journal-derived activity, while
     per-entry responses stay ExerciseReport? Draw the boundary explicitly.
   - Does the name `ExerciseReport` still fit once it responds to journals? Mike's framing:
     "journaling is essentially an exercise" — so possibly yes. But test the inverse: if a
     journal response carries no Exercise, no mastery propagation, no
     APPROVED/NEEDS_REVISION gate, is it still honestly an *Exercise*Report, or does the
     entity want a more neutral name (e.g. `EntryReport`/`Report`) with exercise semantics
     as one mode? Weigh the rename cost (EntityType value, labels, routes, UI) against
     One Path Forward — recommend, don't hedge.
   - How `assessment_outcome`/`MasteryImpact` behave for a journal response (no exercise,
     no assessment score) — what's the honest enum/field shape?

3. **Reports bloat campaign interaction** — the campaign (~10 findings) is queued next:
   all 5 `report_relationship_service.py` methods, 3 test-only `progress_schedule_service.py`
   CRUD methods, `get_privacy_summary()`, `request_review()`. Several
   (`get_learning_loop_chain`, `get_submission_chain`, the review-request queue) are exactly
   the plumbing a journal-response feature might want. For each finding, rule: superseded
   (delete) vs staged-for-this-design (PLANNED with a one-path-forward reason). Follow the
   canonical campaign protocol (memory: deletion-campaigns-superseded-vs-staged) — when a
   finding is feature-shaped and the design doesn't claim it, the default is ask Mike.

### Deliverable

A design document (`docs/` or ADR) covering: the EXTRACT_ACTIVITIES wiring plan, the
ExerciseReport/ActivityReport boundary statement, the naming recommendation with rationale,
and the per-finding bloat-campaign ruling table. Sequenced implementation plan at the end
(what ships in which PR). Verify all behavioral claims against the code and the live graph
(local Neo4j + neo4j-cypher MCP) — do not trust doc/comment claims without checking.
