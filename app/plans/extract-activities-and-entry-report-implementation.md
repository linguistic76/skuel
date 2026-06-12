# Implementation Plan: EXTRACT_ACTIVITIES Pipeline + EntryReport Convergence

> **Source of truth for the design:** `docs/decisions/ADR-069-extract-activities-pipeline-and-entry-report.md`
> (Decisions 1–2). Decision 3 (Reports bloat campaign) is explicitly **deferred** — its four
> ASK-MIKE items remain open; nothing in these PRs deletes or registers those findings, except
> that PR-3 naturally *wires* the two design-claimed methods (`get_pending_submissions`,
> `get_submission_chain`), taking them off the dead list.
>
> **How to execute:** one PR per section, each in a FRESH Claude Code session. Lead the session
> with: "EXECUTE this PR section from `plans/extract-activities-and-entry-report-implementation.md`
> — no plan file, no go-ahead needed." Verify integration behavior on local Docker Neo4j
> (CI runs no pytest). Run `scripts/request_codex_review.sh <PR#>` after the final push.
> App-code PRs wait for Mike's merge word.

---

## PR-1 — `Pipeline.EXTRACT_ACTIVITIES` (Analog parser + optional Digital bridge)

**Goal:** text entry → DSL parse → real entities, with graph provenance and designed idempotency.

### 1. Enum + request surface

- `core/models/enums/pipeline.py`: add `EXTRACT_ACTIVITIES = "extract_activities"` + docstring
  row. `allows_sharing()` unchanged (returns False only for TRANSCRIBE_AND_STRUCTURE).
- `UserEntryProcessRequest` (in `core/models/user_entry/user_entry_request.py`): add
  `force: bool = False` — re-run override for the completed-run guard.

### 2. Extractor modernization (`core/services/dsl/activity_extractor.py`)

- Signature `extract_and_create(report: SubmissionEntity, ...)` → `(entry: UserEntry, ...)`.
  `SubmissionEntity` is already a pre-6b alias for `UserEntry` (`core/models/entity_types.py:64`)
  — switch to the direct name (One Path Forward; do NOT delete the alias here if other files
  still use it — that's bloat-campaign scope).
- Repoint `_update_report_metadata` (line 1330): replace the retired
  `get_submission`/`update_submission` calls with the injected `UserEntryService`
  (`get_entry` + `backend.update` metadata merge — same pattern `_fail` uses in the
  processing service). Rename the injection param `report_service` → `entry_service` and
  drop the recursive "submissions from submissions" `_create_report` branch — it targets the
  retired flow the ADR forbids resurrecting (delete `_create_report` + the
  `reports_found/created` counting; keep the dataclass fields out too).
- **Fix the lying docstring** (line 24): replace the "Idempotent: re-extraction updates
  existing entities" claim with the real mechanism (§4 below).
- **Ownership gating:** extraction runs as the entry's owner. Ku/PS/LP creation is
  SHARED-tier/admin-only (CLAUDE.md ownership table) — for non-admin users, curriculum
  `@context(ku|ls|lp)` *creation* lines are recorded in `creation_errors` as
  "curriculum creation requires admin" and skipped. `@ku(...)` *references* on activity
  lines still resolve against existing Kus (read is public).

### 3. Processing-service branch (`user_entry_processing_service.py`)

- `__init__` gains `dsl_bridge: LLMDSLBridgeService | None = None` and
  `activity_extractor: ActivityExtractorService | None = None`.
- `process()` dispatch: `EXTRACT_ACTIVITIES → _run_extract_activities(entry, instructions)`.
- `_run_extract_activities`:
  1. Guard: extractor configured (else `Errors.system`, phase=`setup`); source text =
     `entry.processed_content or entry.content`, non-empty (else validation error).
  2. **Completed-run guard:** `entry.metadata["activity_extraction"]` records a completed
     run and `force` is not set → `Result.ok(entry)` no-op (mirrors `NONE` semantics).
  3. **Bridge pre-pass (optional):** if `dsl_bridge` is set (FULL tier), `transform(source)`;
     on success append `\n\n## Extracted Activities\n` + transformed lines to the working
     text. Bridge **absent** = silently skip (not an error — Analog-complete). Bridge call
     **fails** = record the error into `processing_error`, continue parser-only over the
     original text (ProgressReportGenerator degradation precedent).
  4. Extraction: `extractor.extract_and_create(entry, user_uid)` over the working text
     (pass text explicitly — add a `content_override: str | None` param so the bridge output
     is used without mutating the entry).
  5. **Provenance:** for each created UID, write
     `(created)-[:EXTRACTED_FROM {extracted_at, source_line_hash}]->(entry)` via
     `backend.add_relationship(..., properties=...)` (supports properties —
     `_traversal_mixin.py:70`). New `RelationshipName.EXTRACTED_FROM` with comment
     `(created Entity)-[:EXTRACTED_FROM]->(UserEntry source) — DSL extraction provenance`.
     `source_line_hash` = sha256 of the whitespace-normalized DSL line. The extractor must
     return per-entity line provenance — extend `ActivityExtractionResult` UID lists to
     `(uid, line_hash)` pairs or a parallel map.
  6. **Line-hash dedup (under `force`):** before creating an entity for a parsed line, skip
     if an `EXTRACTED_FROM` edge with the same `source_line_hash` already points at this
     entry (one read query up front: collect existing hashes for the entry, set-membership
     check per line — no per-line queries).
  7. **Ku edges:** for every created Ku and every resolved `@ku()` reference, write
     `(entry)-[:APPLIES_KNOWLEDGE]->(ku)` (canonical edge — the substance/ZPD contract).
  8. Persist run summary `entry.metadata["activity_extraction"] = extraction.to_dict()`
     (+ `"status": "completed"`), `_emit_completed`. New `_fail` phases: `bridge` (only if
     we choose to fail—we don't; it degrades), `extract`, `persist_links`, `persist_metadata`.

### 4. Composition (`services_bootstrap/compose.py`)

- Construct `ActivityExtractorService` with the `.core` sub-services (tasks/goals/habits/
  events/principles/choices), `ku/ps/lp` core services, `entry_service`, calendar + lifepath
  services; `finance_service=None` (ADR-052 — degrade path already handled).
- FULL tier: build `LLMDSLBridgeService` via `adapters/external/llm/dsl_bridge_factory.py`
  (ChatCompletionPort injection — core stays SDK-free). CORE tier: `None`.
- Pass both into `UserEntryProcessingService`.

### 5. Bloat ledger + docs

- Re-run `./dev bloat`. De-register from `PLANNED_METHODS` what went live
  (`extract_and_create`, likely `has_errors`); `preview_extraction`,
  `transform_with_context`, `transform_sync` stay PLANNED (update their reason strings to
  point at ADR-069 — sync variant is explicitly NOT the CORE fallback, opt-in only).
- Update `docs/dsl/DSL_USAGE_GUIDE.md` wiring-status note + the extractor/bridge module
  docstrings that say "staged".

### 6. Verification (live Neo4j, FULL + CORE)

- CORE tier (no keys): entry with hand-tagged `@context(task)`/`@context(habit)` prose →
  process → entities exist, `EXTRACTED_FROM` edges with hashes, metadata summary written.
- Re-process without `force` → no-op; with `force` → zero duplicates (hash dedup).
- FULL tier: untagged prose → bridge pre-pass → entities. Kill the LLM key → degraded
  parser-only run with `processing_error` set, tagged lines still extracted.
- Non-admin user with `@context(ku)` creation line → skipped with creation_error;
  `@ku()` reference on a task line → `APPLIES_KNOWLEDGE` edge exists.
- `./dev quality` zero errors.

---

## PR-2 — Intelligence consumers (substance channel + ZPD 4th signal)

**Goal:** the `(UserEntry)-[:APPLIES_KNOWLEDGE]->(Ku)` edge becomes load-bearing.

1. **UserContext MEGA-QUERY** (`adapters/persistence/neo4j/user_context_queries.py` + the
   UserContext model): add `entry_knowledge_applied: dict[str, list[str]]`
   (entry_uid → ku_uids), subquery shaped exactly like `task_knowledge_applied`
   (`unified_user_context.py:322`), scoped to the user's owned `:UserEntry` nodes.
2. **Substance:** `core/services/ps/ps_intelligence_service.py:~540` — replace the hardcoded
   `journal_count = 0` with the per-Ku count over `entry_knowledge_applied`. Formula
   unchanged: `min(0.20, count * 0.07)`. Rename local `journal_*` variables to `entry_*`
   for honesty (the source is UserEntries, journaling is one producer).
3. **Substance event:** `KnowledgeReflectedInEntry(knowledge_uid, entry_uid, user_uid)` in
   `core/events/knowledge_substance_events.py` (mirror `KnowledgeAppliedInTask`); publish
   from PR-1's edge-write site in `_run_extract_activities`; subscribe in
   `services_bootstrap/_event_wiring.py` → `KuBackend.increment_substance` with a new
   metric key following the existing naming (`times_applied_in_tasks` →
   `times_reflected_in_entries`). Register the event in `PLANNED_EVENTS` only if the
   publish site ships in a later commit than the class — otherwise it's live on arrival.
4. **ZPD:** `core/models/zpd/zpd_assessment.py` — `ZoneEvidence.entry_application: bool =
   False`; `signal_count` counts 4 types (`is_confirmed` stays ≥ 2).
   `core/services/zpd/zpd_service.py:280` `_build_zone_evidence` gains an entry-engagement
   set; extend the ZPD backend's zone-data query with the
   `(User)-[:OWNS]->(:UserEntry)-[:APPLIES_KNOWLEDGE]->(ku)` leg, same shape as the
   task/habit sets.
5. **Docs:** `docs/architecture/knowledge_substance_philosophy.md` — flip the
   "Journal channel (not yet implemented)" note (~line 350) to the live mechanism; the
   weights table's "Journals" row becomes "Entries (reflection)" with the same 0.07/0.20.
   ZPD skill + ZPD docs: "three signal types" → four. **Do not** edit the ADR-054
   Postscript (dated history stays).
6. **Verification (live Neo4j):** create entry → extract with a `@ku()` reference →
   `calculate_user_substance` moves by 0.07 for the touched PathStep; Ku node's
   `times_reflected_in_entries` incremented; `build_rich` → `zpd_assessment` shows
   `entry_application=True` and compound evidence at 2 signals when paired with one other.

---

## PR-3 — EntryReport (rename + journal responses)

**Goal:** one honest per-artifact report entity; LLM responses to journal entries.

### 1. Rename `ExerciseReport` → `EntryReport` (mechanical sweep, zero data migration)

Graph verified empty (0 ExerciseReport nodes, 2026-06-12) — no Cypher migration, but
re-verify emptiness at execution time before skipping the migration script.

- `EntityType.EXERCISE_REPORT` → `ENTRY_REPORT` (`"entry_report"`), all enum tables in
  `entity_enums.py` (display name "Entry Report", ContentOrigin.REPORT row, default-status,
  required-fields). `from_string` map: replace the identity alias; **no legacy alias** —
  reports are never file-ingested and the graph is empty.
- `NeoLabel.EXERCISE_REPORT` → `ENTRY_REPORT` (`EntryReport`); `neo4j_schema_manager.py`
  index/constraint DDL renamed (drop-if-exists old names is unnecessary on an empty label,
  but keep the manager idempotent).
- UID prefix: check `ExerciseReportService`/`TeacherReviewService` generation call and move
  to the matching new prefix; update the UID-format table in
  `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`.
- File/class renames: `core/models/report/exercise_report{,_dto}.py` →
  `entry_report{,_dto}.py`; `ExerciseReportService` → `EntryReportService`
  (`entry_report_service.py`); inbound `exercise_report_api.py`/`exercise_reports_ui.py` →
  `entry_report_*`; routes `/exercise-reports*` → `/entry-reports*`; protocol names in
  `core/ports/report_protocols.py`; UI labels in `ui/learning_loop/report.py`,
  `feedback_section.py`, gradebook, teaching detail. ~50–70 files — grep-driven
  (`ExerciseReport|exercise_report|exercise-reports`), update every call site, no shims.
- Comment/docstring sweep: `relationship_names.py` (REPORT_FOR / RESPONDS_TO_REPORT),
  `ReportSource` docstring, `RevisedExercise` model comments, CLAUDE.md (learning-loop
  line + 25-EntityTypes cluster), `docs/architecture/REPORT_ARCHITECTURE.md`,
  `REPORT_MASTERY_ARCHITECTURE.md`, learning-loop skill. ADR-054 body/postscript stays
  untouched (dated record).
- `scripts/detect_bloat.py`: update any `PLANNED_*` keys/strings naming renamed classes
  (the stale-planned check will flag leftovers).

### 2. Backend parameterization

`create_report_node` (`exercise_backends.py:713`): add `visibility: str` and
`create_student_share: bool` params. Existing teacher/AI paths pass
`('shared', True)` — behavior identical. Journal-response path passes
`('private', False)`.

### 3. Journal-response generation

- `EntryReportService.generate_entry_response(entry_uid, user_uid)`:
  1. Ownership-verified fetch (404-not-403).
  2. Eligibility: entry is on the journal chain — `pipeline == EXTRACT_ACTIVITIES`, OR a
     `TRANSFORMS` child (`pipeline == NONE` with an outgoing TRANSFORMS edge), OR
     `pipeline == TRANSCRIBE_AND_STRUCTURE` (respond to the source's transcript). Reject
     others with a business error (exercise turn-ins go through teacher review).
  3. LLM via a new `PROMPT_REGISTRY` template (`entry_response`) — reflective response over
     `processed_content or content`; FULL tier only (business error
     `llm_tier_required` at CORE — same shape as LLM_SUMMARY).
  4. Persist via `create_report_node` with `processor_type=ReportSource.LLM`,
     `assessment_outcome=None`, `author_uid=None`, `visibility='private'`,
     `create_student_share=False`, **no status transition** (`submission_status=None`).
- Trigger: `POST /api/entry-reports/respond` (csrf-protected, owner-only) + a button on the
  entry detail page. Event-driven trigger is explicitly out of scope (follow-up).

### 4. Wire the two design-claimed queries

- `ReportRelationshipService.get_pending_submissions` gains an optional
  `pipelines: list[Pipeline] | None` filter (backend raw query takes the values); the
  responder UI lists "entries awaiting a response" with journal pipelines.
- `get_submission_chain` renders a "Responses" section on the entry detail page
  (entry → its EntryReports). Inject the service where the entry detail route lives
  (orchestrator pattern if the page already uses one).
- These two come off the bloat dead-list by *being wired* — no PLANNED registration needed.

### 5. Verification

- `./dev quality` zero errors (MyPy 0, route audit, linter — watch SKUEL020 on new routes).
- Live Neo4j: journal flow end-to-end — entry → EXTRACT_ACTIVITIES → respond → EntryReport
  node `:Entity:EntryReport` with `REPORT_FOR` edge, PRIVATE, no SHARES_WITH; teacher flow
  regression — submit/approve/request-revision still transitions UserEntry status and
  propagates mastery (the 9 live Exercises make a real fixture).
- Headless-Chrome check of the renamed routes + the new detail-page section (runtime UI
  verification rule), including a negative control (other user's entry → 404).

---

## Sequencing + ground rules

- PR-1 → PR-2 → PR-3, each independently green; PR-2 depends on PR-1's edge writes,
  PR-3 is independent of PR-2 (can land in parallel after PR-1 if needed).
- No backward compatibility anywhere: every rename updates all call sites in the same PR.
- Re-verify "graph is empty" claims at execution time (`COUNT` queries) before skipping
  migrations — the vault sync is live and state may have changed.
- Decision 3's four ASK-MIKE findings stay untouched until Mike rules
  (ADR-069 §3 table is the ledger).
