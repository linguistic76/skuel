# ADR-069: EXTRACT_ACTIVITIES Pipeline + EntryReport Convergence

**Status:** Accepted (Decisions 1–2, Mike 2026-06-12). Decision 3 ruled
and executed 2026-06-12: all 10 findings PLANNED, no deletions (§3 table).
**Date:** 2026-06-12
**Builds on:** [ADR-054 UserEntry](ADR-054-user-entry-unified-submissions.md) (incl. Postscript),
[ADR-043 Intelligence Tier Toggle](ADR-043-intelligence-tier-toggle.md)
**Related:** `/docs/architecture/REPORT_ARCHITECTURE.md`,
`/docs/architecture/knowledge_substance_philosophy.md`

> **Settled inputs (Mike, 2026-06-12 — not re-litigated here):**
> Ruling 1 — wire `Pipeline.EXTRACT_ACTIVITIES`: the staged DSL parser becomes a
> `UserEntryProcessingService.process()` pipeline step, with `llm_dsl_bridge.py` as an
> optional LLM pre-pass (prose → DSL) before deterministic extraction. Both, composed.
> Never resurrect the retired ADR-054 submission-metadata flow.
> Ruling 2 — the per-entry report entity stretches to cover LLM-authored responses to
> journal-pipeline UserEntries: `ReportSource.LLM` + owner-only visibility. No new
> EntityType. Journal privacy policy unchanged (`Pipeline.allows_sharing()` stays
> `False` only for `TRANSCRIBE_AND_STRUCTURE`).

## Context

ADR-054 collapsed all user-authored content into `UserEntry` and made the learning
loop emergent from edges. Its Postscript records that the journal *mechanism*
(`TRANSCRIBE_AND_STRUCTURE` → `TRANSFORMS` child entry) survived but feeds **no
downstream consumer**: the ZPD `je_input` signal was removed (#183), the 0.07/entry
substance channel is reserved-but-unimplemented, and ActivityReports don't read
UserEntries.

The verified current state (all claims checked against code and the live graph,
2026-06-12):

- `Pipeline` has 5 values; `process()` dispatches at
  `core/services/user_entry/user_entry_processing_service.py:93-114`. The only
  trigger is `POST /api/user-entries/process`
  (`adapters/inbound/user_entry_api.py:276`).
- The staged DSL surface (PLANNED tier): `ActivityExtractorService.extract_and_create`
  (`core/services/dsl/activity_extractor.py:482`) parses `@context(...)` Activity
  Lines and creates real entities across 12 domains;
  `LLMDSLBridgeService.transform` (`core/services/dsl/llm_dsl_bridge.py:221`)
  converts free prose → tagged DSL. The extractor's metadata writer
  (`_store_extraction_metadata`, line 1330) still targets the retired
  `get_submission`/`update_submission` surface and must be repointed.
- **The extractor's "Idempotent" docstring claim (line 24) is false.** No
  existence check, dedup key, or update-instead-of-create path exists anywhere in
  the file. Idempotency must be *designed*, not assumed.
- `ExerciseReport` is graph-native and singular-scope: `create_report_node`
  (`adapters/persistence/neo4j/backends/exercise_backends.py:713-784`) **requires**
  the target entry (`MATCH (submission:Entity {uid: $report_uid})`), always creates
  `(report)-[:REPORT_FOR]->(entry)`, hardcodes `visibility: 'shared'` + a
  `SHARES_WITH {role:'student'}` edge, and optionally transitions the entry's
  status. `subject_uid` is projected from the edge on read, never stored.
  Mastery propagates via `ReportMasteryService` keyed off the **linked Exercise's**
  `mastery_impact` (AI 0.4–0.8 / teacher 0.6–0.95).
- `ActivityReport` is aggregate-scope and denormalized: time window
  (`period_start`/`period_end`/`time_period`), `domains_covered`, denormalized
  `subject_uid`, **no REPORT_FOR**, no assessment, no gating, plus a user-annotation
  surface. Created by `ProgressReportGenerator` (LLM with `AUTOMATIC` fallback +
  `processing_error`) or admin-written.
- `ZoneEvidence.signal_count` (`core/models/zpd/zpd_assessment.py:49-57`) counts
  3 signal types (submissions, habit reinforcement, task application);
  `is_confirmed` needs ≥ 2.
- `calculate_user_substance` (`core/services/ps/ps_intelligence_service.py:496-555`)
  computes `journal_score = min(0.20, journal_count * 0.07)` with
  `journal_count = 0` hardcoded — the reserved channel exists in the formula,
  starved at the source.
- **The live graph is empty on this entire plane:** 0 UserEntry, 0 ExerciseReport,
  0 ActivityReport, 0 TRANSFORMS, 0 ReviewRequest, 0 ReportSchedule (9 Exercises
  exist). Every decision below has zero data-migration cost today.

---

## Decision 1 — `Pipeline.EXTRACT_ACTIVITIES` wiring

### 1.1 The enum value and dispatch

```python
class Pipeline(StrEnum):
    ...
    EXTRACT_ACTIVITIES = "extract_activities"   # text → DSL parse → real entities
```

`allows_sharing()` is unchanged — it returns `False` only for
`TRANSCRIBE_AND_STRUCTURE`. An extraction entry is ordinary user content; the
journal privacy norm does not extend to it (Ruling 2 scope).

`process()` gains one branch → `_run_extract_activities(entry, instructions)`:

1. **Source text:** `entry.processed_content or entry.content`; validation error
   if empty (same shape as `LLM_SUMMARY`).
2. **Optional LLM pre-pass (Digital layer):** if an injected
   `LLMDSLBridgeService` is available (FULL tier), call
   `transform_with_context(source_text, active_goals=…)` grounded in the user's
   active goals via the shared `core/services/dsl/grounding.py` builder — the
   same grounding the inert journal "Suggested activities" preview uses, so the
   entity-creating path and the preview recognise prose against identical
   context. Append the returned Activity Lines under an `## Extracted Activities`
   section of the working text. Grounding is a soft signal: a missing goals
   service or a goals-query failure degrades to ungrounded recognition, never an
   error. If the bridge is **absent** (CORE tier / not wired), this is **not an
   error** — skip the pre-pass.
   *Amendment 2026-08-03 (periodic-notes arc PR 3, ruling E3):* **periodic
   entries (`UserEntry.is_periodic_note()`) bypass the pre-pass entirely** —
   entities in daily/weekly/monthly notes come only from checkbox lines +
   explicit `@context()` markers, never inferred from prose, so both tiers
   behave identically there. See `docs/roadmap/done/calendar-periodic-notes-arc.md`
   and `docs/dsl/DSL_USAGE_GUIDE.md` § Periodic Notes — The Parse Contract.
3. **Deterministic extraction (Analog layer):**
   `ActivityExtractorService.extract_and_create()` over the working text. The
   parser matches explicit `@context(...)` lines plus, via a second pass,
   obsidian-tasks checkbox lines (`- [ ] … 📅 … ⏫ #tag` →
   `core/services/dsl/obsidian_tasks_adapter.py`), so at CORE tier a user who
   hand-writes DSL tags *or* authors a periodic note in Obsidian gets full
   extraction with zero API keys — the Analog-layer-complete principle holds
   because the *parser* is the engine and the LLM is only a tagger.
4. **Failure semantics:** bridge *call failure* at FULL tier (LLM exception)
   degrades to parser-only over the original text, records the bridge error in
   `processing_error`, and still succeeds if extraction does — the
   `ProgressReportGenerator` precedent (LLM fails → programmatic fallback +
   `processing_error`). Parser failure or persistence failure fails the run via
   `_fail(entry, err, phase=...)` with new phases `bridge` / `extract` /
   `persist_links`.
5. **Run summary** is stored in `entry.metadata["activity_extraction"]`
   (counts, errors, timing — `ActivityExtractionResult.to_dict()` already builds
   it), persisted through `UserEntryService` — **repointing**
   `_store_extraction_metadata` away from the retired
   `get_submission`/`update_submission` surface (the file's own header flags
   this). This is a metadata write on the live UserEntry path, NOT the retired
   ADR-054 submission-metadata flow.

**`transform_sync` (rule-based no-LLM tagger) was NOT wired as a default CORE-tier
fallback and has since been deleted.** Its substring patterns ("should", "must", "$")
would silently create junk entities from ordinary prose — auto-creating entities from
a heuristic the user never sees violates the default-deny ingestion posture. No
rule-based fallback is planned; LLM is a required dependency. CORE tier extraction =
explicit tags only.

### 1.2 Provenance: `EXTRACTED_FROM` edges

Each created entity links back to its source entry:

```
(created:Entity)-[:EXTRACTED_FROM {extracted_at, source_line_hash}]->(source:UserEntry)
```

- New `RelationshipName.EXTRACTED_FROM`. Precedents: `TRANSFORMS`
  (entry-derivation, bare), `SPAWNED_FROM` (instance→template, carries
  `spawned_at`). `EXTRACTED_FROM` follows the `SPAWNED_FROM` shape — a
  graph-native back-reference with a timestamp.
- `source_line_hash` = SHA-256 of the normalized DSL line that produced the
  entity. This is the **idempotency key**.
- Written below the boundary (the extractor hands UIDs + hashes to a backend
  method; no Cypher in `core/` — SKUEL021).

### 1.3 Idempotency (designed, since the docstring lied)

Two guards, both exact-match and fail-closed:

1. **Completed-run guard:** if `entry.metadata["activity_extraction"]` records a
   completed run, re-`process()` is a no-op success unless the request carries an
   explicit `force` flag. (Mirrors `NONE`'s "already complete" semantics.)
2. **Line-hash dedup:** under `force`, before creating an entity for a parsed
   line, check for an existing `EXTRACTED_FROM` edge from this entry with the
   same `source_line_hash` — skip if present. Deterministic parser output makes
   this sound for tagged prose; the LLM pre-pass can reword lines between runs,
   which is exactly why guard 1 (don't re-run by default) is primary and the
   hash is the backstop.

No fuzzy matching, no "update existing entity" — re-extraction *skips*, it never
mutates (AST-lint philosophy: structural rules over unsound heuristics). The
extractor docstring's idempotency claim is rewritten to describe this mechanism.

> **Addendum (2026-07-03, systems-review R3 ruling — Arc C, PR #501):** the
> anticipated weakness above materialized — the LLM pre-pass rewords its lines
> every run, so guard 2 missed and every re-sync duplicated bridge-extracted
> entities (G8). A third guard was added: **semantic dedup for bridge-generated
> lines only**, keyed by `(source entry, node label, normalized title)`
> (whitespace-collapse + casefold — a structural key, not a fuzzy heuristic).
> On match the line resolves to the existing entity; nothing is created and the
> entity's original `EXTRACTED_FROM` edge is left untouched. User-typed lines
> keep the exact guard-2 semantics decided here.

### 1.4 Un-reserving the substance channel + the ZPD 4th signal

The contract is **one edge**: when extraction resolves a Ku reference (a
`@context(ku)` line or `@ku(...)` attribute on an activity), it writes

```
(source:UserEntry)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
```

— the same canonical edge Tasks and Events use. Consumers then need no new
concepts:

- **Substance:** UserContext MEGA-QUERY gains `entry_knowledge_applied:
  dict[str, list[str]]` (entry_uid → ku_uids), built exactly like
  `task_knowledge_applied` (`unified_user_context.py:322`).
  `calculate_user_substance` replaces the hardcoded `journal_count = 0` with the
  per-Ku count over that dict. The formula already exists:
  `min(0.20, count * 0.07)`. A `KnowledgeReflectedInEntry` event (mirroring
  `KnowledgeAppliedInTask`) feeds `KuBackend.increment_substance` for the
  graph-side counter.
- **ZPD:** `ZoneEvidence` gains `entry_application: bool = False`;
  `signal_count` counts 4 types; `is_confirmed` stays ≥ 2 (compound evidence got
  one signal *richer*, not easier). `_build_zone_evidence`
  (`zpd_service.py:280`) gains an entry-engagement set sourced from the same
  edge, exactly like the task/habit sets.

This deliberately composes with the staged **entry-enrichment capability**
(vector-first entry↔graph linking): extraction writes the edge for *explicit*
references now; enrichment will write the same edge for *implicit* semantic links
later. One read path, two writers, no new schema when enrichment lands.

---

## Decision 2 — Report convergence: boundary, naming, enum honesty

### 2.1 The boundary statement

| | Per-artifact report | Aggregate report |
|---|---|---|
| Entity | `ExerciseReport` → **`EntryReport`** (renamed, §2.2) | `ActivityReport` |
| Anchored by | `(report)-[:REPORT_FOR]->(UserEntry)` — required edge | `period_start`/`period_end` + `domains_covered` — no artifact edge |
| Responds to | **one** UserEntry (exercise turn-in *or* journal entry) | a **time window** of activity |
| May gate | the target entry's status (exercise mode only) | never gates anything |
| Mastery | propagates in exercise mode only (via the linked Exercise) | never |

**ActivityReport's influence on the journal-response design: indirect and
automatic — no code changes.** Once `EXTRACT_ACTIVITIES` creates real Tasks,
Habits, Goals, etc., a periodic ActivityReport *already* covers journal-derived
activity, because those entities are ordinary domain entities inside the window.
ActivityReport never reads UserEntries directly and never should — the extracted
entities are the interface. Per-entry responses are exclusively
EntryReport's job. The line: **ActivityReport never responds to a single entry;
EntryReport never aggregates a window.**

### 2.2 Naming: rename `ExerciseReport` → `EntryReport` (recommendation, not a hedge)

The inverse test from the brief, answered with the code: a journal response
carries no Exercise (no `FULFILLS_EXERCISE` anywhere in its chain), no
`assessment_score`, no mastery propagation, no APPROVED/NEEDS_REVISION gate.
Calling it an *Exercise*Report is dishonest. Further evidence the name was
already one hop off:

- `REPORT_FOR` points at a **UserEntry**, not at an Exercise
  (`exercise_backends.py:773`) — the entity's identity has always been
  "response to an entry"; exercise-ness lives on the *target entry's* edges.
- ADR-054's own principle: the loop is emergent from edges; types should not
  encode context. `EntryReport` with exercise semantics as one mode (live when
  the target entry `FULFILLS_EXERCISE`, dormant otherwise) is that principle
  applied to the report side.
- Mike's framing "journaling is essentially an exercise" is honored at the
  *mechanics* level — same entity, same edge, same service — without baking the
  word into a name that is false for the journal mode.

**Cost weighed:** EntityType value (`exercise_report` → `entry_report`),
NeoLabel, UID prefix, `ExerciseReportService`/DTO/request renames, routes
(`/exercise-reports` → `/entry-reports`), UI labels, docs/skills sweep. Bounded,
mechanical, precedented (Feedback→Report rename). **Data migration cost: zero —
the live graph has 0 ExerciseReport nodes.** This is the cheapest this rename
will ever be; deferring it means paying a Cypher relabel migration later. One
Path Forward: rename now, in the same PR that stretches the entity, all call
sites updated, no aliases.

`ActivityReport` keeps its name — "activity over a window" remains exactly what
it is.

### 2.3 `assessment_outcome` / `MasteryImpact` for a journal response

**No enum changes.** The honest shape is *absence*, not a new value:

- `assessment_outcome = None` — a journal response assesses nothing. Adding a
  pseudo-outcome (e.g. `RESPONDED`) would encode "no assessment happened" as a
  kind of assessment. UI branches on presence (badge only when set), which the
  detail view already tolerates since the field is `| None` today.
- `MasteryImpact` never appears: it lives on the Exercise and is resolved from
  the linked exercise at approval time (`teacher_review_service.py:538`). A
  journal chain has no exercise, so mastery propagation is structurally
  unreachable — no guard code needed.
- Provenance is carried by the fields that already exist:
  `processor_type=ReportSource.LLM`, `author_uid=None`.

### 2.4 Owner-only visibility (mechanical change required)

`create_report_node` hardcodes `visibility: 'shared'` + a
`SHARES_WITH {role:'student'}` edge. Journal responses are owner-only (Ruling 2):
parameterize the backend method (`visibility`, `create_student_share: bool`);
the journal-response path passes `PRIVATE` / no share edge. The owner reads their
own report; nothing else can (404-not-403 posture unchanged).

### 2.5 The journal-response trigger

A new `EntryResponseService` method (on the renamed report service) generates an
LLM response for a journal-pipeline entry: find owned UserEntries on the journal
chain (the `TRANSFORMS` child, `pipeline=NONE`, or the extraction entry) with no
`REPORT_FOR` pointing at them — **exactly the staged
`ReportRelationshipService.get_pending_submissions` query** (§3, finding 1) plus
a pipeline filter. Trigger is explicit (a button / route) in the first PR;
event-driven (`UserEntryProcessingCompleted` subscriber) is a follow-up once the
manual path is proven. FULL tier only; CORE tier simply has no responder (the
entry itself remains fully functional — Analog-complete).

---

## Decision 3 — Reports bloat-campaign rulings (10 findings)

Wiring evidence verified 2026-06-12: the 5 `ReportRelationshipService` methods
have **zero callers** — the service is constructed and injected into
UserContextIntelligence (`core/services/user/intelligence/core.py:218`) and never
invoked (the phantom-injection pattern). `ProgressReportWorker` **is started** at
bootstrap (`scripts/dev/bootstrap.py:802`) and calls
`get_due_schedules`/`mark_generated` — but no route creates a schedule, so the
loop polls an eternally-empty table (0 ReportSchedule nodes). The admin review
queue page is **live** (`activity_review_ui.py` → `get_pending_reviews`) but no
route calls `request_review`, so the queue is eternally empty (0 ReviewRequest
nodes). `get_privacy_summary`'s docstring claims `GET /api/privacy/audit` — **no
privacy route exists anywhere in `adapters/inbound/`**.

| # | Finding | Ruling | Reason |
|---|---|---|---|
| 1 | `report_relationship_service.get_pending_submissions` | **PLANNED — claimed by this design** | The §2.5 response-trigger query ("owned entries with no REPORT_FOR"), needs a pipeline filter. Completes in PR-3. |
| 2 | `get_submission_chain` | **PLANNED — claimed by this design** | Student view "what happened after my entry" — the entry detail page's response chain in PR-3. |
| 3 | `get_unsubmitted_exercises` | **PLANNED (Mike, 2026-06-12)** | Assigned-work nag for daily planning — staged under the daily-plan phantom-dispatch repair thread. |
| 4 | `get_report_summary` | **PLANNED (Mike, 2026-06-12)** | Completion-rate read surface over REPORT_FOR; wire a progress/dashboard consumer. |
| 5 | `get_learning_loop_chain` | **PLANNED (Mike, 2026-06-12)** | Exercise-rooted loop traversal; awaits a teaching-UI exercise detail view (the entry-rooted twin is design-claimed). |
| 6–8 | `progress_schedule_service.create_schedule` / `get_user_schedule` / `deactivate_schedule` | **PLANNED — completion backlog of a live consumer** | The worker runs at every bootstrap; these are the missing *producer* surface (a settings route/UI). Deleting them strands a running loop — incoherent. Periodic ActivityReports are also this design's §2.1 aggregate lens over journal-derived activity. |
| 9 | `activity_report_service.get_privacy_summary` | **PLANNED (Mike, 2026-06-12)** | Privacy-transparency surface aligned with the security posture (admin-snapshot audit events already publish for it). The docstring's claimed-but-nonexistent `GET /api/privacy/audit` route reference is fixed in the campaign PR. |
| 10 | `review_queue_service.request_review` | **PLANNED — completion backlog of a live consumer** | The admin queue page ships and reads `get_pending_reviews`; this is its missing producer (user-side "request a review" button). All-or-nothing cross-surface rule: either both sides live or both go — the consumer is live. |

**Campaign executed 2026-06-12 (no-deletion campaign):** all 10 findings registered
in `PLANNED_METHODS` with the one-path-forward reasons above; findings 1–2 come
back off the ledger when PR-3 wires them.

---

## Sequenced implementation plan

Each PR is independently shippable and verified on live Neo4j.

1. **PR-1 — `EXTRACT_ACTIVITIES` pipeline (Decision 1).**
   Enum value + dispatch branch + `_run_extract_activities`; repoint
   `_store_extraction_metadata` to `UserEntryService`; `EXTRACTED_FROM`
   relationship + backend writer; idempotency guards; `APPLIES_KNOWLEDGE` edge
   writes for Ku references; extractor docstring rewritten to the real
   idempotency mechanism. De-register the completed DSL PLANNED entries
   (`extract_and_create`, `preview_extraction`, `has_errors`, `transform`);
   `transform_with_context` stayed PLANNED at the time (`transform_sync` deleted
   — rule-based path abandoned). *Update:* `transform_with_context` is now wired
   on both bridge callers — the journal "Suggested activities" preview (#473) and
   the EXTRACT_ACTIVITIES pre-pass (active-goal grounding) — and is no longer
   PLANNED.
   *Verify:* tagged-prose extraction at CORE tier (no keys), bridge pre-pass at
   FULL tier, re-process no-op, edges in the graph.
2. **PR-2 — intelligence consumers.**
   MEGA-QUERY `entry_knowledge_applied`; `journal_count` unhardcoded in
   `calculate_user_substance`; `KnowledgeReflectedInEntry` event →
   `increment_substance`; `ZoneEvidence.entry_application` 4th signal.
   *Verify:* substance moves on a live entry with a Ku reference; ZPD compound
   evidence counts the new signal.
3. **PR-3 — EntryReport (Decision 2).**
   Rename `ExerciseReport` → `EntryReport` (EntityType, label, UID prefix,
   services, DTOs, routes, UI, docs — zero data migration, graph is empty);
   parameterize `create_report_node` visibility/share; journal-response
   generation method + explicit trigger route; wire findings 1–2
   (`get_pending_submissions` with pipeline filter, `get_submission_chain` on
   the entry detail page).
4. **PR-4 — Reports bloat campaign.**
   Execute the §3 table: register PLANNED entries, delete what Mike confirms,
   fix the `get_privacy_summary` docstring either way.
5. **Later / separate threads:** event-driven response trigger; entry-enrichment
   capability (second writer of `APPLIES_KNOWLEDGE`); schedule-settings UI
   (completes findings 6–8); review-request button (completes finding 10).

## Consequences

- The journal pipeline finally feeds consumers: extraction (entities), substance
  (0.07 channel live), ZPD (4th signal), responses (EntryReport), aggregates
  (ActivityReport via extracted entities) — all through canonical edges, no new
  parallel systems.
- One honest report taxonomy: EntryReport (per-artifact) / ActivityReport
  (aggregate), with exercise assessment as a *mode*, not an identity.
- The rename touches ~the usual sweep of files but zero data; deferring it would
  convert a free rename into a paid migration.
- The rule-based sync tagger (`transform_sync`) was deleted — its noisy
  auto-tagging had no place in the default path. CORE tier stays deterministic
  and default-deny; LLM is a required dependency.
