# learning-loop Reference: Phase Mechanics & Code Walkthrough

> On-demand reference for the [`learning-loop`](SKILL.md) skill. SKILL.md holds the loop overview, the Ku substrate, the development lens, anti-patterns, key source files, and system layers; this file holds the per-phase mechanics (Phases 1–4, the Interaction Contract, parallel ActivityReport, binding relationships, service architecture, API routes) and the end-to-end code walkthrough.

---

## Phase 1: Exercise — The Directive

**What it is:** The teacher's directive. Instructions for what students should produce,
with an LLM prompt embedded for AI-assisted feedback.

**EntityType:** `EntityType.EXERCISE`
**Model:** `core/models/exercises/exercise.py` — `Exercise(Curriculum)` frozen dataclass
**DTO:** `core/models/exercises/exercise_dto.py`
**Neo4j label:** `:Entity:Exercise`

**Key fields:**
```python
path_step_uid: str | None         # PathStep anchor — REQUIRED for PERSONAL scope (mirrors HAS_EXERCISE edge)
exercise_number: int | None       # Human-readable number (set in YAML, e.g. exercise_number: 7).
                                  # Embedded in the downloaded .md worksheet's frontmatter so
                                  # the submission handler can read it back without a DB query.
instructions: str                 # Teacher's directive — ALSO used as LLM prompt
model: str                        # LLM to use: "claude-sonnet-4-6"
scope: ExerciseScope              # PERSONAL (self-directed) | ASSIGNED (classroom)
due_date: date | None             # ASSIGNED only — when submission is due
group_uid: str | None             # ASSIGNED only — which class receives this
enrichment_mode: EnrichmentMode | None  # ACTIVITY_TRACKING, IDEA_ARTICULATION, CRITICAL_THINKING
context_notes: tuple[str, ...]    # Reference materials (immutable)
form_schema: tuple[dict, ...] | None  # Inline form definition for structured submissions
expected_modality: SubmissionModality  # FILE_UPLOAD or STRUCTURED_FORM (auto-derived from form_schema)
```

**Two submission modes (typed by `SubmissionModality` enum):**

| Mode | `expected_modality` | `form_schema` | Student action | Submission content |
|------|---------------------|--------------|----------------|-------------------|
| **File upload** | `FILE_UPLOAD` | `None` | Uploads file (audio, text, image) | `file_path`, `processed_content` |
| **Inline form** | `STRUCTURED_FORM` | Present | Fills embedded form in PathStep | `metadata["form_data"]`, `processed_content` (JSON) |

`expected_modality` is auto-derived in `__post_init__`: if `form_schema` is set → `STRUCTURED_FORM`,
else → `FILE_UPLOAD`. The corresponding `Submission.modality` field records which path was actually used.
Both modes create `UserEntry` and trigger the same event pipeline (`FULFILLS_EXERCISE` /
`FULFILLS_REVISED_EXERCISE`, auto-share with teacher).

**Four scopes and their constraints (`is_valid()` enforces these):**

| Scope | Created by | Requires | Purpose |
|-------|-----------|---------|---------|
| `PERSONAL` | User/Admin | — (PathStep anchor optional) | Self-directed AI feedback; anchored to a PathStep or a free-standing library template |
| `ASSIGNED` | Teacher | `group_uid` | Teacher assigns to a class — no PathStep required |
| `ASSESSMENT` | Teacher | `scoring_rubric` | Formal graded test — no PathStep required |
| `CURRICULUM` | Content vault (ingestion only) | — | Shared vault-authored exercise, no user owner; anchored via `exercise_uids:` in PathStep YAML |

**Services:**
```python
services.exercises                # ExerciseService facade
services.exercises.core           # CRUD; ExerciseBackend for Cypher
```

**Backend (domain-specific Cypher):**
```python
# ExerciseBackend — domain-specific relationship Cypher
await backend.link_to_path_step(exercise_uid, path_step_uid)  # HAS_EXERCISE (PERSONAL scope creation)
await backend.link_to_curriculum(exercise_uid, ku_uid)        # REQUIRES_KNOWLEDGE
await backend.unlink_from_curriculum(exercise_uid, ku_uid)    # DELETE relationship
await backend.get_required_knowledge(exercise_uid)            # list KUs required
await backend.get_exercise_for_submission(submission_uid)     # FULFILLS_EXERCISE lookup
await backend.get_student_exercises_with_status(user_uid)     # ASSIGNED exercises via group membership
await backend.get_enrolled_ps_exercises_with_status(user_uid) # PERSONAL exercises via enrolled PathSteps
await backend.get_ps_exercises_with_status(ps_uid, user_uid)  # Exercises for a SINGLE PathStep with status
```

**PathStep detail page (2026-06-24 reading-first redesign):**

The PathStep detail page at `/explore/ps/{uid}` is a reading-first column (`max-w-[760px]`,
`BasePage(CUSTOM)`, no sidebar) matching the KU reader design language. Alpine component
`pathstep` (in `static/js/ps-detail.js`) owns progress state (`not_started/learning/read`),
bookmark toggle, and deps accordion. CSRF-protected mutation endpoints:
- `POST /explore/ps/{uid}/progress` (`state=learning|read`) — progress toggle (no TaskTemplates)
- `POST /explore/ps/{uid}/bookmark` (`on=true|false`)
- `GET /explore/ps/{uid}/tasks` — HTMX fragment: tasks spawned from this PS for the current user

**Engage-to-spawn:** when the PS has TaskTemplates (`has_task_templates` in the inline x-data seed), "Start
learning" calls `POST /api/ps/{uid}/engage` instead of the progress endpoint — spawning all
template instances — then fires `ps-engaged` to reload the tasks fragment.

The `/learning-loop/ps/{ps_uid}/*` fragment routes remain wired in `learning_loop_routes.py`
(`create_learning_loop_fragment_routes`) but are not surfaced on the PS detail page:

| Fragment Endpoint | Service Method | Renderer |
|---|---|---|
| `GET /learning-loop/ps/{ps_uid}/exercises` | `ExerciseService.get_exercises_for_path_step_with_status()` | `render_exercise_list()` with `from_ps` context |
| `GET /learning-loop/ps/{ps_uid}/submissions-and-feedback` | `LearningLoopQueryService.get_submissions_for_path_step()` | `render_ps_submissions()` + `render_ps_feedback()` (single query) |
| `GET /learning-loop/ps/{ps_uid}/forms` | `ExploreOrchestrator.get_forms_for_path_step()` → `FormTemplateService` | `render_embedded_forms()` — empty div when no forms linked |
| `POST /learning-loop/ps/{ps_uid}/forms/{template_uid}/submit` | `FormSubmissionService.submit_form()` | success card (outerHTML swap) or form re-render with error banner |

Renderers in `ui/learning_loop/` (`exercise_status.py`, `submissions_section.py`, `feedback_section.py`,
`embedded_forms.py`). Exercise status helpers shared with Library exercises tab (`/library/exercises`).
Status pills follow loop-phase precedence: report > turn-in > declared intent > nothing
(Feedback Available / Revision Requested > Submitted > In Progress > Not Submitted). "In Progress"
is the vault living entry's `fulfills_exercise_uid` intent property with no `FULFILLS_EXERCISE`
edge (`has_in_progress` / `in_progress_uid` on `ExerciseStatusRow`); its action link opens the
living entry at `/gradebook/{uid}`.

Forms are linked to PathSteps via `(PathStep)-[:EMBEDS_FORM]->(FormTemplate)`. Admin wires the relationship via
`POST /api/form-templates/link-path-step`. The fragment returns an empty `<div>` when no forms are linked, so the
section only renders when content exists.

Submissions are discovered via the Interaction graph:
`(user)-[:OWNS]->(sub)-[:RECORDS]<-(interaction)-[:INTERACTION_DURING]->(ps)`.
`PathStepSubmissionRow` TypedDict in `core/ports/query_types.py` defines the return shape.

Unauthenticated visitors see simple exercise links (no status, no submissions/feedback).

**Library surface — two discovery paths (secondary indexes):**

| Path | Relationship | Scope | Trigger |
|------|-------------|-------|---------|
| Group exercise | `(exercise)-[:SHARED_WITH_GROUP]->(group)<-[:MEMBER_OF]-(user)` | `ASSIGNED` | Teacher shares to group (ADR-053) |
| PathStep enrollment | `(ps)-[:HAS_EXERCISE]->(exercise)` + `(user)-[:IN_PROGRESS]->(ps)` | `PERSONAL` | User enrolls in PathStep |

`ExerciseService.get_student_exercises_with_status()` merges both paths and deduplicates by UID. The Library Exercises page calls this method via `GET /library/exercises` (the Library hub at `/library` links to this child page).

**Graph pattern:**
```cypher
// Assigned exercise (classroom)
(teacher:User)-[:OWNS]->(exercise:Entity:Exercise {scope: 'assigned'})
(exercise)-[:SHARED_WITH_GROUP]->(group:Group)
(exercise)-[:REQUIRES_KNOWLEDGE]->(ku:Entity:Ku)

// PathStep-anchored exercise (self-directed personal or vault-authored curriculum)
(ps:Entity)-[:HAS_EXERCISE]->(exercise:Entity:Exercise)  // scope: 'personal' | 'curriculum'
(user:User)-[:IN_PROGRESS]->(ps)
```

**Download worksheet — frictionless submit flow:**

`GET /api/exercises/md?uid=` downloads a Markdown worksheet (`adapters/outbound/exercise_renderer.py`)
with YAML frontmatter pre-filled from the session:

```markdown
---
exercise_uid: ex.mindfulness.small-steps-design
exercise_number: 7
user_uid: user_abc123          ← pre-filled from authenticated session
revision: 1                    ← student increments for resubmissions
---
# Exercise Title
...
```

The student fills in responses and submits the file at `POST /api/user-entries/upload`.
The exercise link is carried by the `fulfills_exercise_uid` form field (set by the `/submissions/exercise`
form via the exercise selector or the `?exercise_uid=` deep-link hidden field); the revision
is computed server-side by `UserEntryService._next_revision()`. The current upload endpoint
does **not** parse the worksheet's YAML frontmatter — that auto-detection is not implemented
here; the pre-filled frontmatter is for the student's reference.

**Student-facing routes:**
- `GET /exercises/get?uid=` — detail page: metadata, form field prompts, instructions, Submit + Download buttons
- `GET /api/exercises/md?uid=` — Markdown worksheet download (pre-filled frontmatter)
- `POST /api/user-entries/upload` — HTMX upload endpoint; exercise link via the `fulfills_exercise_uid` form field

> **Critical (ADR-054):** The teacher review queue is assembled by group membership, not by
> exercise ownership: `TeacherReviewService.get_review_queue()` →
> `UserEntryBackend.get_review_queue_by_groups()` matches
> `(teacher)-[:OWNS]->(:Group)<-[:SHARED_WITH_GROUP]-(entry:UserEntry)` where
> `entry.pipeline = 'teacher_review'`. (The pre-ADR-054 `(teacher)-[:OWNS]->(exercise)`
> traversal is no longer the queue path — relying on it hides valid group-shared entries.)
> Separately, because `Exercise` extends `Curriculum(Entity)` — NOT `UserOwnedEntity` —
> `exercise.user_uid` is always `None`; an exercise's owning teacher is resolved via the OWNS
> edge (`UserEntryBackend.get_exercise_context()` uses the `COALESCE(teacher.uid,
> exercise.user_uid)` pattern; see "Ownership Queries" in the neo4j-cypher-patterns skill).

**Loop role:** Exercise is the *how* — it operationalizes Ku into a concrete task.
Its `instructions` field serves double duty: directive for the student AND prompt for
the AI when generating feedback. This is the bridge between knowledge and evaluation.

---

## Phase 2: UserEntry — The Student's Work

**What it is:** The student's artifact. Any user-authored content — an uploaded file
(audio, text, image), a structured form, or free-form text — that is optionally
processed and then evaluated. ADR-054 collapsed the former `Submission` / `ExerciseSubmission`
/ `JeInput` / `JeOutput` split into this one type, discriminated by a `pipeline` field.

**EntityType:** `EntityType.USER_ENTRY` (always — forced in `__post_init__`)
**Model:** `core/models/user_entry/user_entry.py` — `UserEntry(UserOwnedEntity)` frozen dataclass
**Neo4j labels:** `:Entity:UserEntry`
**UID prefix:** `ue_` (e.g. `ue_a1b2c3d4`)

> **Note (ADR-054):** Journals are no longer a standalone domain — they are a `UserEntry`
> processing pipeline (`Pipeline.TRANSCRIBE_AND_STRUCTURE`). The former `core/models/journal/`
> and `core/services/journal/` packages were deleted.

**Key fields (added on top of `UserOwnedEntity`):**
```python
# File storage — all nullable; a text-only entry has none of these
original_filename: str | None
file_path: str | None
file_size: int | None
file_type: str | None               # MIME type: "audio/mpeg", "text/plain"

# Processing
pipeline: Pipeline = Pipeline.NONE  # Dispatch discriminator (default NONE):
                                    #   NONE | TRANSCRIBE | TRANSCRIBE_AND_STRUCTURE
                                    #   | LLM_SUMMARY | TEACHER_REVIEW
processing_started_at: datetime | None
processing_completed_at: datetime | None
processing_error: str | None
processed_content: str | None       # Transcribed/enriched text — the evaluable content
processed_file_path: str | None
instructions: str | None            # Pipeline-specific instructions (e.g. LLM prompt)
max_retention: int | None           # FIFO cleanup limit (None = permanent)

# Modality — HOW the entry was created (orthogonal to pipeline)
modality: SubmissionModality | None  # FILE_UPLOAD | STRUCTURED_FORM (None for text-only)
```

> **Revision tracking is edge-authoritative, node-mirrored (ADR-054).** `revision_number` is
> not a field on the frozen `UserEntry` dataclass. The authoritative value lives on the
> `FULFILLS_EXERCISE {revision}` edge (and the parallel `FULFILLS_REVISED_EXERCISE {revision}`
> edge for revision-cycle entries): `UserEntryService._next_revision()` computes it as
> `count_entries_for_exercise(...) + 1` and passes it to
> `UserEntryBackend.create_with_exercise_link()`, which stamps it onto the edge. A second
> attempt against the same exercise creates a new `UserEntry` whose edge carries `revision=2`.
> **Post-create**, `UserEntryExerciseLinker.process_exercise_submission()` (fired via the
> `UserEntryCreated` event → `exercise_handler`) reads that edge revision and — **only for
> `ASSIGNED`-scope exercises and valid `RevisedExercise` resubmissions** — writes a revision-aware
> title (`"{exercise_title} v{revision}"`) and a denormalized `revision_number` property back onto
> the node for cheap reads. It returns early (`NOT_ASSIGNED`) for `PERSONAL` / `ASSESSMENT`
> exercises, which therefore keep only the `FULFILLS_EXERCISE {revision}` edge and no node mirror.
> The frozen model class never declares the field either way.

**SubmissionModality vs Pipeline:** `SubmissionModality` records *how* the submission was
created (file upload vs structured form). `Pipeline` records *what* happens to it.
They are orthogonal — a form submission can still be part of a pipeline.

**One type, pipeline-discriminated:**

| `pipeline` | Typical entry | Processing |
|-----------|---------------|-----------|
| `NONE` | Plain text/file entry | None |
| `TRANSCRIBE` | Audio upload | Audio → text (Deepgram) |
| `TRANSCRIBE_AND_STRUCTURE` | Journal flow | Audio → transcribed entry → LLM-structured second entry |
| `LLM_SUMMARY` | Text/file to summarize | LLM summary |
| `TEACHER_REVIEW` | Exercise turn-in | None — routed to a teacher review queue via `SHARED_WITH_GROUP` |

**One create method (`UserEntryService.create_entry()`):**
(The former bytes-to-disk helper `submit_file()` was removed with ADR-073 — `/journals/upload`
is now zero-persistence and processes to `je_out/` without creating a UserEntry.)
```
FILE UPLOAD PATH                            INLINE FORM PATH
POST /api/user-entries/upload               POST /api/user-entries/form
 → builds UserEntryCreateRequest             → builds UserEntryCreateRequest
   (file metadata: name/size/type)             (form_data carried in metadata)
        ↓                                            ↓
        └──────────────► UserEntryService.create_entry() ◄──────────────┘
                                  │
   builds UserEntry (status: SUBMITTED for pipeline=TEACHER_REVIEW — service-owned,
     any other authored status rejected; else authored request.status wins when set
     — e.g. vault frontmatter — falling back to ACTIVE)
   persists node — create_with_exercise_link() for TURN-INS (fulfills_exercise_uid
     set + no caller uid — the /submit form and /upload paths):
     → FULFILLS_EXERCISE {revision} → root Exercise (always)
     → FULFILLS_REVISED_EXERCISE {revision} → RevisedExercise (revision cycles only)
     (a caller-supplied deterministic uid + fulfills is the VAULT LIVING ENTRY
      instead: idempotent upsert, intent stored as the fulfills_exercise_uid node
      property, NO edge/revision/Interaction — the vault exercise channel files
      frozen copies through the turn-in path on `status: submitted`; see
      docs/patterns/UNIFIED_INGESTION_GUIDE.md § Vault exercise channel)
   creates Interaction audit record (turn-ins only)
   resolves audience + shares (UnifiedSharingService)
   publishes UserEntryCreated event
```

**Processing is a separate, explicit step.** The upload / form routes *only* call
`create_entry()` — they do not run a pipeline. To process an entry,
`POST /api/user-entries/process` (JSON body: entry `uid` + an optional per-run
`instructions` override) invokes `UserEntryProcessingService.process(entry)`, which
dispatches strictly on the entry's **stored** `pipeline` (the request's `pipeline`
field is not applied): audio →
Deepgram transcription, text/file → LLM summary/structuring, then
`update_processed_content()` writes `processed_content` and advances status to `COMPLETED`
(or marks `FAILED`). Entries with `pipeline=NONE`/`TEACHER_REVIEW` need no processing.

> **FULFILLS edges & revision.** `UserEntryBackend.create_with_exercise_link()` writes
> `FULFILLS_EXERCISE {revision}` to the **root Exercise** regardless of which node was
> submitted against (it resolves a `RevisedExercise` to its original via `REVISES_EXERCISE`);
> for revision-cycle entries it additionally writes `FULFILLS_REVISED_EXERCISE {revision}` to
> the revision node. The edge is the authoritative `revision` (a node mirror is stamped later by
> `UserEntryExerciseLinker`, but only for `ASSIGNED` / `RevisedExercise` submissions — see above).

**Status:** `create_entry()` sets `SUBMITTED` for `pipeline=TEACHER_REVIEW` (so the entry enters
the teacher review queue) and `ACTIVE` otherwise. `UserEntryProcessingService` advances processed
entries to `COMPLETED` (via `update_processed_content()`) or marks them `FAILED` on error. There
is no central status-transition chokepoint method — status is set at the create / process / review
steps that own it.

**API routes:**
- `POST /api/user-entries/upload` — file upload (multipart form-data)
- `POST /api/user-entries/form` — structured form data (JSON)
- `POST /api/user-entries/process` — run the entry's stored pipeline (JSON: `uid` + optional `instructions`)

**Services:**
```python
services.user_entry            # UserEntryService facade — create/read/update/delete
services.user_entry_processor  # UserEntryProcessingService — pipeline dispatch
                               #   (transcribe, summarize, transcribe-and-structure)
```

**Backend (domain-specific Cypher):**
```python
# UserEntryBackend — :UserEntry node CRUD, exercise linking, review queue, assessment
await backend.create_with_exercise_link(entry, exercise_uid, revision)  # FULFILLS_* edges
await backend.count_entries_for_exercise(user_uid, exercise_uid)        # revision counter
await backend.get_review_queue_by_groups(teacher_uid, status_filter)    # teacher queue
await backend.get_exercise_context(...)                                 # OWNS/COALESCE teacher
```

> **Sharing is entity-agnostic (ADR-042).** `UserEntry` carries no SHARES_WITH Cypher of its
> own. All sharing goes through `UnifiedSharingService` → the entity-agnostic `SharingBackend`
> (`create_share`, `delete_share`, `update_visibility`, `query_access`,
> `query_shared_with_users`, `create_group_share`).

**Access:** `ContentScope.USER_OWNED`. Default `PRIVATE`. Sharing via
`UnifiedSharingService` — three-level model: `PRIVATE → SHARED → PUBLIC`.

**Loop role:** Submission is the *evidence* — the student's demonstration of engagement
with the Ku. The `processed_content` field is what AI and teachers actually evaluate.
Without Submission, the loop has no student voice.

---

## The Interaction Contract — Curriculum Context at Submission Time

When `UserEntryService.create_entry()` creates an exercise-linked `UserEntry`,
it calls `_create_interaction_record()` which persists an **Interaction** node
recording that a submission happened against a given exercise.

**EntityType:** `EntityType.INTERACTION`
**Model:** `core/models/interaction/interaction.py` — `Interaction(UserOwnedEntity)`
**Service:** `core/services/interaction/interaction_service.py` — `InteractionService`
**UID prefix:** `ia_`
**Enums:** `InteractionType` (EXERCISE_SUBMISSION, KU_VIEW, PATH_STEP_COMPLETION, FORM_SUBMISSION),
`InteractionResult` (PENDING → SHARED_WITH_TEACHER → REPORT_GENERATED → COMPLETED, FAILED
from pre-report states — forward-only, wired to the report pipeline 2026-07-19)

**What it captures today (ADR-054; PathStep context wired 2026-07-03).**
`_create_interaction_record()` builds the Interaction with:
- `interaction_type`: `InteractionType.EXERCISE_SUBMISSION`
- `target_uid`: the Exercise UID being submitted against
- `source_entity_uid`: back-pointer to the `UserEntry` UID
- `context_path_step_uid`: from the request's `about_path_step_uid` (the PS page's
  Submit → flow carries it as a hidden form field) — nullable when the submission
  didn't come from a PathStep context

> **Registry requirement (found the hard way):** `create_relationships_batch` validates
> every edge against `LABEL_CONFIGS` in `core/models/relationship_registry.py`. Interaction
> has its own `INTERACTION_CONFIG` there (RECORDS / INTERACTION_DURING / INTERACTION_WITHIN).
> Before it existed, every context edge was rejected as "invalid for Interaction" and the
> audit nodes were persisted as orphans — silently, because creation is fire-and-forget.
> Pinned by `tests/integration/user_entry/test_interaction_record.py`.

> **Still not wired:** LearningPath context (`context_learning_path_uid` →
> `INTERACTION_WITHIN`) — no caller passes it yet; open follow-up (see ZPD/Askesis below).

**Graph relationships:**
```cypher
(interaction)-[:RECORDS]->(submission)           // back-pointer to source artifact — created today
(interaction)-[:INTERACTION_DURING]->(pathstep)  // created when about_path_step_uid rides the submission
(interaction)-[:INTERACTION_WITHIN]->(lp)        // only if context_learning_path_uid is set (currently unset)
```

**Why a separate node, not fields on UserEntry?** Interaction is queryable as
a first-class graph node — you can traverse all interactions for a PathStep, or find
every student who submitted while enrolled in a given LearningPath. Embedding those
fields in UserEntry would bury them.

**Result lifecycle (ADR-051 Phase 2, wired 2026-07-19):** `result_status` transitions
forward-only as the report pipeline progresses. `SHARED_WITH_TEACHER` is recorded
directly by `UserEntryService.create_entry` after a successful TEACHER_REVIEW share;
the rest are event-driven via `core/events/handlers/interaction_result_handler.py`:
`EntryReportGenerated` (AI report) and `UserEntryRevisionRequested` (revision report)
→ REPORT_GENERATED; `ReportSubmitted` (terminal approving feedback — `submit_report`
marks the submission COMPLETED+APPROVED) and `UserEntryApproved` (post-revision
approval) → COMPLETED; `UserEntryProcessingFailed` → FAILED. The transition guard
lives on `InteractionResult.allowed_from()` and runs server-side in
`InteractionBackend.update_result_status_for_entry` — stale events are logged no-ops.

**Phase 2 (deferred):** ZPD and Askesis will query Interaction nodes to reason about
*situated learning trajectories* — not just what a student submitted but where in the
curriculum they were when they submitted it.

**Implementation note:** Interaction creation is best-effort — a failure never blocks
the submission. The UI route uses `getattr(services, "interaction_service", None)` and
logs a warning rather than failing the request.

**See:** `docs/decisions/ADR-051-user-interaction-contract.md`

---

## Phase 3: EntryReport — The Response

**What it is:** The evaluation of a submitted artifact. The loop's reply to the student's work.

### ENTRY_REPORT — Response to an Artifact

**EntityType:** `EntityType.ENTRY_REPORT`
**Model:** `core/models/report/entry_report.py` — `EntryReport(UserOwnedEntity)` frozen dataclass
**Neo4j label:** `:Entity:EntryReport`
**Inherits:** `UserOwnedEntity` directly — NOT Submission. The class adds 7 report-specific fields on top.

**Key fields:**
```python
processed_content: str | None                         # LLM/teacher-generated feedback (written by create_report_node as processed_content: $feedback)
report_generated_at: datetime | None
# GRAPH-NATIVE: projected from the REPORT_FOR edge on read (not a stored node property).
# EntryReportBackend.get / list_for_submission hydrate it via
# `OPTIONAL MATCH (n)-[:REPORT_FOR]->(sub) RETURN n{.*, subject_uid: sub.uid}`.
subject_uid: str | None                           # UID of the submission being evaluated
processor_type: ReportSource | None              # HUMAN (teacher) | LLM (AI)
assessment_outcome: AssessmentOutcome | None       # APPROVED | NEEDS_REVISION | AI_EVALUATED
report_file_path: str | None                       # Path to uploaded .md file (HUMAN) or generated output (LLM)
assessment_score: float | None                     # 0.0-1.0 for ASSESSMENT-scope exercises
```

`assessment_outcome` (`AssessmentOutcome` enum from `learning_enums.py`) makes each report
self-describing — the report records what decision was made, not just feedback text.

**Two sources — same EntityType, different ReportSource:**

| Source | Service | ReportSource | AssessmentOutcome | Trigger |
|--------|---------|---------------|-------------------|---------|
| Teacher submits `.md` file | `TeacherReviewService.submit_report()` | `HUMAN` | `APPROVED` | Teacher uploads feedback file at `/teaching/review/{uid}` |
| Teacher requests revision | `TeacherReviewService.request_revision()` | `HUMAN` | `NEEDS_REVISION` | Teacher fills structured revision form (instructions + categorized feedback points via Alpine.js dynamic list + rationale) |
| AI | `EntryReportService.generate_report()` | `LLM` | `AI_EVALUATED` | Exercise has `instructions` (via `UnifiedLLMCaller`) |

**Two teacher feedback pathways — same service methods, different entry points:**

- **Web UI** — `/teaching/review/{uid}` accepts a `.md` file upload (multipart/form-data). File content → `processed_content` (the report body); path → `report_file_path`. Students download via `GET /api/reports/{report_uid}/download`.
- **CLI (offline batch)** — `scripts/export_submissions.py` exports the review queue to `~/skuel-reviews/pending/<uid>.md` and writes an `export_manifest.json` to track pending state; teacher writes reports to `done/<uid>.md` with YAML frontmatter (`submission_uid`, `action: report|revision|approve`); `scripts/import_reports.py` posts them back. To prevent silent loss of feedback, the import script performs **Pending-State Reconciliation** against the manifest, warning the teacher of any pending/done files that have not been successfully imported. Both scripts call the same `TeacherReviewService` methods.

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(report:Entity:EntryReport {
    processor_type: 'human',            // or 'llm'
    assessment_outcome: 'approved',     // or 'needs_revision' or 'ai_evaluated'
    visibility: 'shared',               // set at create so SHARES_WITH is honored by UnifiedSharingService
    processed_content: 'Your analysis shows...'  // LLM/teacher-generated feedback body
})
(report)-[:REPORT_FOR]->(submission:Entity:UserEntry)  // subject_uid is projected from this edge on read
(report)-[:SHARES_WITH]->(submitter:User)                       // grants read access via UnifiedSharingService
```

**Structural position:** Leaf domain. One submission in, one report node out.
Reads go through `EntryReportBackend` (typed fetches — `get`, `list_for_submission`);
writes (teacher + AI) go through `EntryReportBackend.create_report_node`. Both are reached via
`EntryReportService`, the single service entry point.

**The Revision Cycle (Phase 3 → 4 → 2 → 3):**

After reviewing a submission, the teacher has three outcomes via `TeacherReviewService`
(`core/services/report/teacher_review_service.py`, protocol: `TeacherReviewOperations`
in `core/ports/report_protocols.py`):

| Action | Method | AssessmentOutcome | Allowed From Status | Event Published | Result |
|--------|--------|-------------------|---------------------|-----------------|--------|
| Write report | `submit_report()` | `APPROVED` | `SUBMITTED`, `ACTIVE` | `ReportSubmitted` | `EntryReport` created, loop continues |
| Request revision (with exercise) | `request_revision_with_exercise()` | `NEEDS_REVISION` | `SUBMITTED`, `ACTIVE` | `UserEntryRevisionRequested` + `RevisedExerciseCreated` + `RevisedExerciseEmbeddingRequested` | **Atomic**: EntryReport + RevisedExercise created in one transaction |
| Request revision (report only) | `request_revision()` | `NEEDS_REVISION` | `SUBMITTED`, `ACTIVE` | `UserEntryRevisionRequested` | EntryReport created, no RevisedExercise |
| Approve | `approve_report()` | — (no report created) | `REVISION_REQUESTED` | `UserEntryApproved` | Loop closes for this exercise |

**Cypher-level status guards:** All three methods enforce valid status transitions
atomically in the database via `WHERE submission.status IN $allowed_from_statuses`.
The service passes the allowed source statuses; if the guard rejects, the query
returns empty results and the service returns a validation error (not "not found",
since `_verify_teacher_has_group_access` already confirmed existence). This is race-safe —
no gap between read and write.

Each feedback round creates a new `EntryReport` entity via `REPORT_FOR` —
revision cycles are traceable as first-class graph entities. The loop publishes
`ReportSubmitted`, `UserEntryRevisionRequested`, and `UserEntryApproved` events.
Student notification delivery is **planned** — see the Messaging system in
`CLAUDE.md`. Students currently need to poll `/gradebook` or the
activity feed to discover new reports.

---

---

## Parallel Reporting: ActivityReport — Response to Activity Patterns

> **Not a loop phase.** ActivityReport closes a feedback loop over *lived activity* across
> a time window. It shares the same pedagogical purpose as EntryReport (work → response),
> but is **structurally separate**: different services, different routes, and explicitly
> excluded from `LearningLoopEventHandlerService` and `LearningLoopQueryService`.

### ACTIVITY_REPORT — Response to Activity Patterns

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Model:** `core/models/report/activity_report.py` — `ActivityReport(UserOwnedEntity)` frozen dataclass
**Neo4j label:** `:Entity:ActivityReport`
**Inherits:** `UserOwnedEntity` **directly** — NO file fields by design

**Key fields:**
```python
processor_type: ReportSource | None    # AUTOMATIC | LLM | HUMAN
subject_uid: str | None                 # user whose activity was reviewed
time_period: str | None                 # "7d" | "14d" | "30d" | "90d"
period_start: datetime | None
period_end: datetime | None
domains_covered: tuple[str, ...]        # which activity domains included
depth: str | None                       # "summary" | "standard" | "detailed"
processed_content: str | None           # LLM output or human-written feedback (immutable)
processing_error: str | None

# Annotation fields (Phase 2) — user adds voice alongside AI synthesis
user_annotation: str | None             # Additive commentary
user_revision: str | None              # User-curated replacement for sharing
annotation_mode: str | None            # "additive" | "revision" | None
annotation_updated_at: datetime | None
```

**Three sources — same EntityType:**

| Source | Service | ReportSource | Trigger |
|--------|---------|---------------|---------|
| Scheduled system | `ProgressReportWorker` → `ProgressReportGenerator` | `AUTOMATIC` | Cron schedule |
| On-demand AI | `ProgressReportGenerator.generate()` | `LLM` | User requests via API |
| Admin writes | `ActivityReportService.submit_report()` | `HUMAN` | Admin reviews snapshot |

**Structural position:** Cross-domain aggregator. Cannot fit the leaf domain model
because it reads across all 6 Activity Domain backends **and** the Curriculum track
(KU mastery, LP progress, active PS). `ProgressReportGenerator` accepts a
`UserContextBuilder` and calls `build_rich(user_uid, window=...)` — MEGA_QUERY
with activity window CALL{} blocks. This gives the generator access to full graph
neighbourhoods across both tracks. `ActivityReportService.create_snapshot()` uses
the same method.

**LLM generation flow:**
```
1. Call `context_builder.build_rich(user_uid, time_period=...)` — MEGA_QUERY with
   activity window; `context.entities_rich` covers all 6 Activity Domains;
   `context.knowledge_units_rich`, `context.enrolled_paths_rich`,
   `context.active_path_steps_rich` cover the Curriculum track
2. Cross-reference active Insights
3. Send stats as JSON context to LLM via activity_feedback.md prompt template
4. LLM returns qualitative analysis with patterns, trends, recommendations
5. Create ActivityReport with processed_content = LLM output
6. Graceful fallback: if LLM fails → ReportSource.AUTOMATIC + programmatic markdown
```

**Prompt template:** `core/prompts/templates/activity_feedback.md`

---

## Phase 4: RevisedExercise — The Targeted Revision

**What it is:** A teacher-created revision of an Exercise that addresses specific gaps
identified in `EntryReport`. Forces a reflection step between feedback and
resubmission.

```
PathStep → Exercise v1 → Submission v1 → EntryReport v1
                                              ↓
                                        RevisedExercise v2 → Submission v2 → ...
```

**EntityType:** `EntityType.REVISED_EXERCISE`
**Model:** `core/models/exercises/revised_exercise.py` — `RevisedExercise(UserOwnedEntity)` frozen dataclass
**DTO:** `core/models/exercises/revised_exercise_dto.py`
**Neo4j label:** `:Entity:RevisedExercise`

**Key design:**
- Inherits `UserOwnedEntity` (NOT Curriculum) — needs `user_uid` but not 21 Curriculum fields
- `ContentOrigin.USER_CREATED` — teacher-authored content targeted at a specific student, not shared curriculum
- Teacher-owned, student-targeted (student visibility via `student_uid` field)
- `revision_number` auto-determined per-(exercise, student): `max(existing for the pair) + 1` — never a global per-exercise count, never `len + 1` (duplicate ordinals after deletions). Both writers agree: `RevisedExerciseService.create()` via `get_next_revision_number`, and the atomic `create_report_and_revised_exercise` Cypher
- `feedback_points: tuple[FeedbackPoint, ...]` — typed feedback using `FeedbackCategory` enum (ACCURACY, COMPLETENESS, DEPTH, CLARITY, APPLICATION, METHODOLOGY) + free-text detail. Enables pattern tracking across submissions.
- `expected_modality` and `submission_uid` auto-resolved by service on creation — teacher doesn't provide these
- `parent_entity_uid` set to `report_uid` at `create()` time — the EntryReport is the direct derivation parent. Makes the chain navigable via Python model: no graph query needed to answer "which report prompted this revision?" The `RESPONDS_TO_REPORT` graph edge and `parent_entity_uid` carry the same information.

**Services:**
```python
services.revised_exercises              # RevisedExerciseService — CRUD + chain queries
```

**Backend:**
```python
# RevisedExerciseBackend — domain-specific relationship Cypher (standalone create path)
await backend.link_to_report(re_uid, report_uid)           # RESPONDS_TO_REPORT
await backend.link_to_exercise(re_uid, exercise_uid)      # REVISES_EXERCISE
await backend.get_revision_chain(exercise_uid, teacher_uid, student_uid=None)
# ^ Classroom-scoped (teacher's active groups only — same audience as the write);
#   out-of-classroom reads return an empty chain, identical to a missing exercise
await backend.get_next_revision_number(exercise_uid, student_uid)  # per-pair max+1
await backend.get_by_report_uid(report_uid)                # Lookup RevisedExercise by report

# EntryReportBackend — atomic revision request (preferred path from teaching UI)
await entry_report_backend.create_report_and_revised_exercise(params)
# Single Cypher: creates EntryReport + RevisedExercise + all relationships atomically
# Used by TeacherReviewService.request_revision_with_exercise()
```

**Graph pattern:**
```cypher
(teacher:User)-[:OWNS]->(re:Entity:RevisedExercise {
    original_exercise_uid: '...',
    report_uid: '...',              // domain-specific field
    parent_entity_uid: '...',       // = report_uid — derivation chain mirror
    submission_uid: '...',
    student_uid: '...',
    revision_number: 2,
    feedback_points: '[{"category":"depth","detail":"..."}]'
})
(re)-[:RESPONDS_TO_REPORT]->(report:Entity:EntryReport)
(re)-[:REVISES_EXERCISE]->(exercise:Entity:Exercise)
(submission:Entity:Submission)-[:FULFILLS_EXERCISE]->(exercise)        // root anchor — always
(submission:Entity:Submission)-[:FULFILLS_REVISED_EXERCISE]->(re)     // revision pointer
```

**Event:** `RevisedExerciseCreated` (`revised_exercise.created`) — published on creation,
enables student notification and learning loop progression tracking.

**Access control:**
- **Create:** `create()` (overrides `CrudOperationsMixin.create`; for pre-operation guards, prefer `_validate_create` hook or `_post_create` hook for events — see `/docs/patterns/DOMAIN_SPECIFIC_HOOKS.md`) verifies the `student_uid`
  owns the submission linked to the report (OWNS-based, per ADR-040). Teacher identity is
  role-gated at the route level. Graph path checked:
  `(Report)-[:REPORT_FOR]->(UserEntry)<-[:OWNS]-(Student)`.
  Prevents teachers from creating revisions targeting arbitrary students' feedback.
- **CRUD routes:** Generated by `CRUDRouteFactory` with `require_role=UserRole.TEACHER`. Ownership
  verification ensures only the creating teacher can access their revised exercises.
- **List for student (teacher route):** `list_for_student(student_uid, teacher_uid=)` scopes
  results to revisions owned by the requesting teacher, preventing cross-teacher leakage.
- **Student access:** On creation, a `SHARES_WITH {role: 'student'}` relationship is auto-created
  from the student to the RevisedExercise. Students discover revisions through:
  - "Shared With Me" inbox (SHARES_WITH relationship)
  - `GET /api/revised-exercises/my-revisions` (student_uid match)
  - `GET /api/revised-exercises/view?uid=` (student_uid or owner match)
  - Daily planning: `get_ready_to_work_on_today()` surfaces them at Priority 2.3 via
    `context.pending_revised_exercises` (populated by MEGA-QUERY)

**Student-facing UI (GradeBook sidebar — 2026-04-05):**

Students view their revisions in the GradeBook sidebar under "Revisions":
- `GET /revised-exercises` — list page with `render_revised_exercise_list()`
- `GET /revised-exercises/detail?uid=` — detail page with `render_revised_exercise_detail()` (feedback points, instructions, submit link)
- `GET /revised-exercises/list` — HTMX fragment for filtered list
- `GET /api/gradebook/revised-exercises/preview` — hub preview block

Routes in `adapters/inbound/revised_exercises_ui.py`. Renderers in `ui/learning_loop/revised_exercise.py`.
The detail page links to `/submissions/exercise?exercise_uid={re_uid}` — triggering the two-path Cypher for
`FULFILLS_REVISED_EXERCISE`. The EntryReport detail at `/entry-reports/detail?uid=` shows
a "View Revision" link when a `RevisedExercise` exists for that report (via `get_by_report_uid()`).

**Loop role:** RevisedExercise is the *refinement* — it bridges feedback back into a
new exercise, closing the revision cycle explicitly rather than implicitly.

---

## Why `RevisedExercise` Is Object-Language (Not a Naming Drift)

`RevisedExercise` occasionally raises the question "is this process-language?" — it isn't.
"Revised" here is a past-participle acting as an adjective, and the name reads as "a revised
exercise" (a kind of thing), parallel to `FrozenDataclass`, `CompiledQuery`,
`DerivedAttribute`. The process verb would be `RevisingExercise` or `ExerciseRevision(act of)`
— neither of which is what SKUEL means.

RevisedExercise stays a distinct EntityType (not collapsed into `Exercise` with a kind field)
because it differs from `Exercise` on five structural axes:

- **Hierarchy:** `Entity → UserOwnedEntity → RevisedExercise` vs. `Entity → Curriculum → Exercise`
- **Ownership:** `user_uid = teacher_uid` vs. `user_uid = None` (shared curriculum)
- **Targeting:** individual `student_uid` vs. group (`group_uid`) or personal curriculum (`path_step_uid`)
- **ContentOrigin:** `USER_CREATED` vs. `CURRICULUM`
- **Feedback typing:** `tuple[FeedbackPoint, ...]` with `FeedbackCategory` enum vs. plain `instructions` text

The verb lives on the edge: `(RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)`. Type name =
noun; edge name = verb; variant = enum field. Applied throughout the loop: `UserEntry` uses
`pipeline: Pipeline` to distinguish what would once have been three separate types (ADR-054),
and `EntryReport` uses `report_source: ReportSource` + `assessment_outcome:
AssessmentOutcome` to cover both initial and revision cycles without spawning a
`RevisedEntryReport` type.

**See:** [`/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md § Naming Convention`](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md#naming-convention) for the rule, the two-part test, and additional worked examples. ADR-054 is the reference for the `UserEntry` collapse rationale.

---

## The Binding Graph Relationships

| Relationship | Connects | Purpose |
|---|---|---|
| `REQUIRES_KNOWLEDGE` | `Exercise` → `Ku` | Exercise is grounded in this knowledge |
| `SHARED_WITH_GROUP` | `Exercise` → `Group` | ASSIGNED exercise shared to this classroom (ADR-053) |
| `MEMBER_OF` | `User` → `Group` | Student enrolled in a group (auto-created on PathStep IN_PROGRESS via `PathStepEnrolled` event → admin default group) |
| `FULFILLS_EXERCISE` | `Submission` → `Exercise` (root) | Always anchors to the original Exercise, across all revision iterations |
| `FULFILLS_REVISED_EXERCISE` | `Submission` → `RevisedExercise` | Created alongside FULFILLS_EXERCISE for revision-cycle submissions only |
| `SHARES_WITH` | `User` → `RevisedExercise` | Auto-share revision to student on creation |
| `REPORT_FOR` | `EntryReport` → `Submission` | Report evaluates this specific artifact |
| `RESPONDS_TO_REPORT` | `RevisedExercise` → `EntryReport` | Revision addresses this report |
| `REVISES_EXERCISE` | `RevisedExercise` → `Exercise` | Revision of this original exercise |

**RelationshipName enum locations:**
```python
from core.models.relationship_names import RelationshipName

RelationshipName.REQUIRES_KNOWLEDGE      # Exercise → Ku
RelationshipName.SHARED_WITH_GROUP       # Exercise/PathStep/LearningPath → Group (ADR-053)
RelationshipName.FULFILLS_EXERCISE          # Submission → root Exercise (always)
RelationshipName.FULFILLS_REVISED_EXERCISE  # Submission → RevisedExercise (revision-cycle only)
RelationshipName.REPORT_FOR              # EntryReport → Submission
RelationshipName.SHARES_WITH             # User → RevisedExercise (auto-share to student)
RelationshipName.SHARED_WITH_GROUP       # Submission → Group (group sharing)
RelationshipName.RESPONDS_TO_REPORT     # RevisedExercise → EntryReport
RelationshipName.REVISES_EXERCISE        # RevisedExercise → Exercise
```

---

## Service Architecture Summary

| Phase | Service | Protocol | Backend | Key Methods |
|-------|---------|----------|---------|-------------|
| **Substrate: PathStep** | `PsService` | `PsOperations` | `PsBackend` | CRUD, KU composition (`USES_KU`), learning state (VIEWED/IN_PROGRESS/MASTERED), organize/get_children |
| **Phase 1: Exercise** | `ExerciseService` | `ExerciseOperations` | `ExerciseBackend` | `link_to_curriculum`, `get_exercise_for_submission`, `get_student_exercises`, `get_student_exercises_with_status`, CRUD |
| **RevisedExercise** | `RevisedExerciseService` | `RevisedExerciseOperations` | `RevisedExerciseBackend` | CRUD (CRUDRouteFactory), `list_for_student`, `get_revision_chain` |
| **UserEntry** | `UserEntryService` (concrete facade — routes inject the class, no route-facing protocol) | backend port `UserEntryOperations` | `UserEntryBackend` | `create_entry`, `get_entry`, `list_for_user`, `get_review_queue`, `update_processed_content`, `delete_entry` (sharing via `UnifiedSharingService`, not the backend) |
| **UserEntry processing** | `UserEntryProcessingService` | `UserEntryProcessingOperations` | — (dispatches; updates via `UserEntryService`) | `process(entry)` — pipeline dispatch by `Pipeline` (TRANSCRIBE / LLM_SUMMARY / TRANSCRIBE_AND_STRUCTURE) |
| **Submission report** | `EntryReportService` (AI) + `AssessmentService` (HUMAN) | `EntryReportOperations` (service, AI + reads) + `EntryReportBackendOperations` (backend); `AssessmentOperations` for teacher assessments — split in PR #128, NOT a single-class union | `EntryReportBackend` (typed reads + report-node creation via `create_report_node`) + `UserEntryBackend` (assessment relationship/query ops: authority check, `ASSESSMENT_OF`, auto-share) | `EntryReportService`: `generate_report` (via `UnifiedLLMCaller`), `list_for_submission` → typed `list[EntryReport]` (both sources). `AssessmentService`: `create_assessment`, `get_assessments_for_student/by_teacher`. Writes land as `:Entity:EntryReport` dual-label; reads discriminate AI vs teacher via `processor_type` on the typed model — no TypedDict projection |
| **Journal processing** | *(no standalone service — ADR-054)* | — | — | Journals are a `UserEntry` pipeline (`Pipeline.TRANSCRIBE_AND_STRUCTURE`) handled by `UserEntryProcessingService`; the former `JournalOutputService` was deleted |
| **Learning Loop Intelligence (write)** | `LearningLoopEventHandlerService` | — | `UserEntryBackend` (port `UserEntryOperations`) | `handle_submission_created` (iteration tracking), `handle_report_submitted` (feedback turnaround EMA), `handle_submission_approved` (mastery velocity) |
| **Learning Loop Intelligence (read)** | `LearningLoopQueryService` | — | `UserEntryBackend` (port `UserEntryOperations`) | `get_submissions_for_path_step(user_uid, ps_uid, limit=QueryLimit.COMPREHENSIVE)` — Interaction traversal + report-status enrichment, bounded by `limit` (default 100), entity_type filter parameterized via `EntityType.USER_ENTRY.value`. New learning-loop reads land here, not on a separate search service |
| **Teacher review** | `TeacherReviewService` | `TeacherReviewOperations` | `UserEntryBackend` + `EntryReportBackend` + `ExerciseBackend` + `GroupBackend` | **Review actions:** `get_review_queue`, `get_submission_detail`, `submit_report` (file upload → `processed_content` + `report_file_path`), `request_revision` (text notes), `approve_report`, `get_report_file_path` · **Exercise view:** `get_exercises_with_submission_counts`, `get_submissions_for_exercise` · **Student view:** `get_students_summary` (sources from OWNS exercise_submission — any submitter, no PathStep enrollment required), `get_student_submissions` · **Dashboard:** `get_dashboard_stats`, `get_teacher_groups_with_stats`, `get_group_detail` · **Report listing moved:** use `EntryReportService.list_for_submission()` for typed report reads (not `get_report_history`, which was deleted) |
| **Activity Report (auto/LLM)** | `ProgressReportGenerator` | `ProgressReportOperations` | `UserContextBuilder` | `generate`, `create_scheduled` |
| **Activity Report (scheduled)** | `ProgressReportWorker` | — | — | Background worker; calls `ProgressReportGenerator` on schedule |
| **Activity Report (schedule CRUD)** | `ProgressScheduleService` | `ProgressScheduleOps` | — | `get_schedules`, `create_schedule`, `delete_schedule` |
| **Activity Report (human)** | `ActivityReportService` | `ActivityReportOperations` | `ActivityReportBackend` + `UserContextBuilder` | `create_snapshot`, `submit_report`, `persist`, `get_history`, `annotate` |

**Protocols location:** `core/ports/report_protocols.py` (report + teacher review + review queue + report relationships, both service- and backend-level), `core/ports/user_entry_protocols.py` (the 5 mixin-facing `UserEntry*Operations` slices + the composite `UserEntryOperations` backend port + `UserEntryProcessingOperations` — `submission_protocols.py` was deleted under ADR-054), `core/ports/group_protocols.py` (group CRUD only)

---

## API Routes Per Phase

| Phase | Route | Method | Who |
|-------|-------|--------|-----|
| **PS exercises (HTMX)** | `/learning-loop/ps/{ps_uid}/exercises` | GET | Student |
| **PS submissions + feedback (HTMX)** | `/learning-loop/ps/{ps_uid}/submissions-and-feedback` | GET | Student |
| **PS embedded forms (HTMX)** | `/learning-loop/ps/{ps_uid}/forms` | GET | Student |
| **PS embedded form submit (HTMX)** | `/learning-loop/ps/{ps_uid}/forms/{template_uid}/submit` | POST | Student |
| **Student assignments** | `/exercises` | GET | Student |
| **Submission** | `/submissions/exercise` | GET | Student |
| **Submission detail** | `/gradebook/{uid}` | GET | Student (owner) |
| **Submission reports** | `/api/submissions/{uid}/reports` | GET | Student (owner) |
| **Submission exercise link** | `/gradebook/{uid}/exercise` | GET (HTMX) | Student |
| **Submission** | `/api/submissions/...` | GET/POST | Student |
| **Submission sharing** | `/api/share/group` | POST | Student |
| **Submission sharing** | `/api/submissions/shared-with-me` | GET | Teacher |
| **Submission report** | `/api/reports/assessments` | POST | Teacher |
| **Submission report** | `/api/reports/assessments/given` | GET | Teacher |
| **Submission report** | `/api/reports/assessments/received` | GET | Student |
| **GradeBook** | `/gradebook` | GET | Student |
| **Teacher review** | `/api/teaching/review-queue` | GET | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}` | GET | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/report` | POST | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/revision` | POST | Teacher |
| **Teacher review** | `/api/teaching/review/{uid}/approve` | POST | Teacher |
| **Teacher exercises** | `/api/teaching/exercises` | GET | Teacher |
| **Teacher exercises** | `/api/teaching/exercises/{uid}/submissions` | GET | Teacher |
| **Teacher students** | `/api/teaching/students` | GET | Teacher |
| **Teacher students** | `/api/teaching/students/{uid}/submissions` | GET | Teacher |
| **Teacher groups** | `/api/teaching/groups` | GET | Teacher |
| **Teacher groups** | `/api/teaching/groups/{uid}` | GET | Teacher |
| **Teacher forms** | `/teaching/forms` | GET | Teacher |
| **Teacher forms** | `/teaching/forms/detail?uid=` | GET | Teacher |
| **Teacher forms** | `/teaching/forms/submission?uid=` | GET | Teacher |
| **Notifications** | `/notifications` | GET | Student — **planned, not yet implemented** |
| **Activity report** | `/api/reports/progress/generate` | POST | User |
| **Activity report** | `/api/reports/progress` | GET | User |
| **Activity report** | `/api/reports/schedule` | POST | User |
| **Activity review (admin)** | `/api/activity-review/snapshot` | GET | Admin |
| **Activity review (admin)** | `/api/activity-review/submit` | POST | Admin |
| **Activity review (admin)** | `/api/activity-review/queue` | GET | Admin |
| **Activity review (user)** | `/api/activity-review/history` | GET | User |
| **Annotation** | `/api/activity-reports/annotate` | POST | User |
| **Exercise report detail** | `/entry-reports/detail?uid=` | GET | Student (owner) |
| **Revised exercises (list)** | `/revised-exercises` | GET | Student |
| **Revised exercises (detail)** | `/revised-exercises/detail?uid=` | GET | Student |
| **Revised exercises (HTMX list)** | `/revised-exercises/list` | GET | Student |
| **Revised exercises (hub preview)** | `/api/gradebook/revised-exercises/preview` | GET | Student |
| **Revised exercises (API)** | `/api/revised-exercises/my-revisions` | GET | Student |
| **Revised exercises (API)** | `/api/revised-exercises/view?uid=` | GET | Student or Teacher |

---

## Code Walkthrough

### Curriculum Track (artifact-based)

```
1. KuService.create_ku()                           → core/services/ku/ku_core_service.py
   Admin creates a Knowledge Unit
       ↓
1b. Student browses /explore, clicks a PathStep card        → ui/explore/cards.py
    GET /explore/ps/{uid} renders the learning-loop anchor  → adapters/inbound/explore_ui.py
    HTMX fragments load exercises/submissions/feedback/forms via
      /learning-loop/ps/{ps_uid}/{exercises,submissions-and-feedback,forms} → ui/learning_loop/
    (Learning state: NONE → VIEWED → IN_PROGRESS → MASTERED)
       ↓
2. ExerciseBackend.link_to_curriculum()             → adapters/persistence/neo4j/backends/exercise_backends.py
   Teacher links Exercise to Ku via REQUIRES_KNOWLEDGE
       ↓
3. Student submits file (POST /api/user-entries/upload)
   → UserEntryService.create_entry()              → core/services/user_entry/user_entry_service.py
   Creates :Entity:UserEntry (entity_type='user_entry', pipeline=TEACHER_REVIEW), status SUBMITTED
   (Non-TEACHER_REVIEW pipelines are created ACTIVE and move to COMPLETED/FAILED via
    UserEntryProcessingService — no PROCESSING state is persisted; journals use the
    TRANSCRIBE_AND_STRUCTURE pipeline)
       ↓
4. FULFILLS_EXERCISE relationship created (always → root Exercise)
   FULFILLS_REVISED_EXERCISE also created when submitting against a RevisedExercise
   revision stamped on the FULFILLS_EXERCISE edge; UserEntryExerciseLinker
   (UserEntryCreated → exercise_handler) then mirrors revision_number + a
   revision-aware title onto the node — ASSIGNED / RevisedExercise submissions only
       ↓
5. TeacherReviewService.get_review_queue()          → core/services/report/teacher_review_service.py
   Teacher sees pending user entries (their students' submitted+active
   entries joined to exercises via FULFILLS_EXERCISE)
       ↓
6. TeacherReviewService.submit_report()             → core/services/report/teacher_review_service.py
   Creates EntryReport with ReportSource.HUMAN
   OR EntryReportService.generate_report()     → core/services/report/entry_report_service.py
   Creates EntryReport with ReportSource.LLM (via Exercise instructions)
       ↓
7. Student sees feedback, optionally resubmits (revision cycle)
```

### Activity Track (aggregate-based)

```
1. User activity across 6 Activity Domains + 3 Curriculum Domains
   Tasks, Goals, Habits, Events, Choices, Principles + KU mastery, LP progress, PS progress
       ↓
2. UserContextBuilder.build_rich()                  → core/services/user/user_context_builder.py
   MEGA-QUERY fetches all domain data including submission_stats
       ↓
3. ProgressReportGenerator.generate()               → core/services/report/progress_report_generator.py
   Uses context.entities_rich + LLM (or programmatic fallback)
   Prompt template: core/prompts/templates/activity_feedback.md
       ↓
4. ActivityReportService.persist()                  → core/services/report/activity_report_service.py
   All write paths converge here; creates ActivityReport node in Neo4j
       ↓
5. Latest report flows back into UserContext via MEGA-QUERY
   context.latest_activity_report_uid, context.latest_activity_report_content
   User can annotate (context.latest_activity_report_user_annotation)
   Annotation feeds back into next report's LLM prompt
```
