---
title: UserEntry Domain
created: 2026-09-01
updated: 2026-09-26
status: current
category: domains
tags: [user-entry, learning-loop, domain]
---

# UserEntry Domain

**Type:** Learning-loop domain (Phase 2 — the learner's answer)
**Entity Type:** `EntityType.USER_ENTRY`
**Entity Label:** `:Entity:UserEntry`
**Config:** `USER_ENTRY_CONFIG` (from `core.models.relationship_registry`)

## Purpose

UserEntry is **all user-authored content**: exercise turn-ins, journal entries,
uploaded files, periodic notes, free-form text. ADR-054 collapsed four separate
types — `Submission`, `ExerciseSubmission`, `JeInput`, `JeOutput` — into this one.

It is the busiest domain in the app, because it is the phase of the learning loop
the learner actually writes in: **Exercise → UserEntry → EntryReport →
RevisedExercise → UserEntry → …**

## The dispatch model

The types this domain replaced used `entity_type` as a switch. UserEntry does not:
`entity_type` is always `USER_ENTRY`, and a separate `pipeline: Pipeline` field
decides what (if anything) happens after creation.

| Pipeline | What it does |
|----------|--------------|
| `NONE` | Plain submission or text entry — no processing |
| `TRANSCRIBE` | Audio → text (Deepgram) |
| `TRANSCRIBE_AND_STRUCTURE` | Audio → transcribed entry → LLM-structured second entry. The enum calls it legacy, but the path is **live**, not read-only: a client can select it on `POST /api/user-entries` or as a `/api/user-entries/process` override, and `_run_transcribe_and_structure` still dispatches it (FULL tier) |
| `LLM_SUMMARY` | Text/file → LLM summary |
| `EXTRACT_ACTIVITIES` | Text → DSL parse → real entities with `EXTRACTED_FROM` provenance (ADR-069) |
| `TEACHER_REVIEW` | No processing; the entry waits in the teacher queue — but **only via `SUBMITTED_TO_GROUP`** (the feedback request, ADR-088 §2 — the one pipeline that writes it), see the trap below |
| `KNOWLEDGE` | Grounded knowledge entry — the `je_pro` channel |
| `REFERENCE` | Reserved; no producer today (ADR-073 §4) |

`modality` (`SubmissionModality`: `FILE_UPLOAD` / `STRUCTURED_FORM`) is designed as
**orthogonal** to `pipeline` — how the entry was created, rather than what happens to it.

⚠️ **Nothing derives it, and it is client-settable — so it is not provenance.** The two
routes that actually *know* how the entry arrived omit it: both `UserEntryCreateRequest`
constructors in `adapters/inbound/user_entry_api.py` (multipart upload, structured form)
leave `modality` unset, and the only `SubmissionModality` producers in the tree set
`Exercise.expected_modality`. Meanwhile `POST /api/user-entries` parses a full
`UserEntryCreateRequest` from the JSON body, so an authenticated caller can supply — or
spoof — any value, which `create_entry()` copies straight onto the model.

Read it as a client-supplied hint, never as a trustworthy record of how an entry was
created. Making it real means having the upload and form routes stamp it themselves.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/user_entry/user_entry.py` |
| DTO | `/core/models/user_entry/user_entry_dto.py` |
| Request Models | `/core/models/user_entry/user_entry_request.py` |
| Enums | `/core/models/enums/user_entry_enums.py`, `/core/models/enums/pipeline.py` |
| Facade | `/core/services/user_entry/user_entry_service.py` |
| Processing dispatcher | `/core/services/user_entry/user_entry_processing_service.py` |
| Audience resolution | `/core/services/user_entry/audience_resolver.py` |
| Exercise linking | `/core/services/user_entry/exercise_linker.py` |
| Learning-loop queries | `/core/services/user_entry/learning_loop_query.py` |
| Learning-loop handlers | `/core/services/user_entry/learning_loop_handler.py` |
| Orchestrator | `/core/orchestrator/user_entry_orchestrator.py` |
| Protocol | `/core/ports/user_entry_protocols.py` |
| Backend | `/adapters/persistence/neo4j/backends/user_entry_backend.py` |
| Ingestion door | `/core/services/ingestion/user_entry_ingestion.py` |
| Events | `/core/events/user_entry_events.py` |
| API Routes | `/adapters/inbound/user_entry_api.py` |
| UI Routes | `/adapters/inbound/user_entry_ui.py` |
| Route wiring | `/adapters/inbound/user_entry_routes.py` |
| View Components | `/ui/user_entry/forms.py`, `/ui/user_entry/knowledge_notes.py` |
| Config | `USER_ENTRY_CONFIG` in `/core/models/relationship_registry.py` |

The backend is split across five mixins in `/adapters/persistence/neo4j/`:
`_user_entry_crud_mixin.py`, `_user_entry_content_mixin.py`,
`_user_entry_lifecycle_mixin.py`, `_user_entry_assessment_mixin.py`,
`_user_entry_report_query_mixin.py`.

## Model Fields

Inherits identity, content, status, sharing, meta and embedding fields from
`UserOwnedEntity`. Domain-specific additions:

| Field | Type | Description |
|-------|------|-------------|
| `pipeline` | `Pipeline` | Dispatch discriminator (table above) |
| `modality` | `SubmissionModality?` | A client-supplied hint, **not provenance** — nothing derives it; see above |
| `private` | `bool` | Never grows a vector — no entity embedding, no `:ContentChunk` subtree, and a hard exclusion in companion-retrieval Cypher. Gates companion retrieval only; orthogonal to `visibility` |
| `original_filename` | `str?` | Upload only |
| `file_path` | `str?` | Upload only |
| `file_size` | `int?` | Upload only |
| `file_type` | `str?` | MIME type, upload only |
| `processing_started_at` | `datetime?` | Pipeline timestamps |
| `processing_completed_at` | `datetime?` | |
| `processing_error` | `str?` | |
| `processed_content` | `str?` | Pipeline output |
| `processed_file_path` | `str?` | |
| `instructions` | `str?` | Pipeline-specific instructions (e.g. LLM prompt) |
| `journal_mode` | `str?` | `JournalMode` value captured at upload time |
| `max_retention` | `int?` | FIFO cleanup limit (`None` = permanent) |
| `fulfills_exercise_uid` | `str?` | Declared exercise **intent** — see below |
| `turn_in_exercise_uid` | `str?` | The **turn-in snapshot**: the root exercise's uid, stamped by the writer — see below |
| `turn_in_exercise_title` | `str?` | The root exercise's title as it read at submission |
| `turn_in_revision` | `int?` | The attempt number, stamped with the snapshot — the edge revision's copy that outlives the exercise |

### `revision_number` is not a field

The live revision is the `FULFILLS_EXERCISE {revision}` **edge**: a second
attempt against the same exercise creates a new `UserEntry` with a new edge
carrying `revision=2`. The writer copies the number onto the node as
`turn_in_revision`, beside the exercise snapshot, so the version survives the
exercise's deletion exactly as the title does; nothing writes `revision_number`
on a UserEntry.

### The title is the student's

A turn-in's `title` is whatever the student typed (Submit & Share arc PR 7
ruling). Handed in with none, the writer titles it `"<root exercise title>
v<N>"` in the statement that stamps the snapshot; a non-turn-in with no title
takes its upload's filename. Which exercise and which attempt a turn-in is
comes from the snapshot, never from the title: every surface that lists or
opens a turn-in prints "`<exercise> · v<N>`" beside the title through
`ui/learning_loop/turn_in_label.py` (the queue, the review page, the student's
history, `/gradebook/{uid}`, the PathStep page's list, the recipient card, the
`/exchange` thread's "rev N").

### Intent vs. turn-in

`fulfills_exercise_uid` is the exercise the author declares they are working
against (`fulfills_exercise_uid:` frontmatter on a vault file, or the create
request). It is **intent, not the turn-in**: the turn-in truth stays on the
`FULFILLS_EXERCISE` edge, which only frozen submission copies carry. A living
vault entry has the property and never the edge; removing the frontmatter line
removes the property on the next sync. This mirrors the
`Exercise.path_step_uid` membership-property precedent.

### The turn-in snapshot marks a turn-in

`turn_in_exercise_uid` / `turn_in_exercise_title` are stamped by the turn-in
writer (`create_with_exercise_link`) in the same statement that writes the
edge — never by the author. The uid is the **root** exercise's (a revision
resolves through `REVISES_EXERCISE`, then `original_exercise_uid`); the title
is the root's at submission. An entry that carries them **is** a turn-in, and
the snapshot is the exchange key: the GradeBook lines, the `/exchange` thread,
the review queue's copy collapse and the report titles group on it. Because a
`DETACH DELETE` of the exercise removes the `FULFILLS_EXERCISE` edge but never
a property, an exchange outlives its exercise — it renders as
**Exercise removed** with the snapshotted title instead of falling into Other
feedback (Submit & Share arc R12). A living vault entry carries neither.

## Relationships

### Outgoing (UserEntry → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `source_entry` | `TRANSFORMS` | UserEntry | Multi-stage pipelines. ⚠️ The edge runs **derived → source**: the LLM-structured child is written with `transforms_of_uid` pointing back at the transcript it came from, so traversing `TRANSFORMS` outward walks *up* the pipeline, not down. The field name is the tell |
| `exercise` | `FULFILLS_EXERCISE` | Exercise | What the entry answers; carries `revision` |
| `applied_knowledge` | `APPLIES_KNOWLEDGE` | Ku | Knowledge applied/reflected in the entry — THE substance/ZPD contract edge. **Two writers, one event:** explicit `@ku()` refs via the `EXTRACT_ACTIVITIES` pipeline (ADR-069), and vector grounding via `EntryGroundingService`, which stamps `inferred: true` + `confidence` + `grounded_at` so an inferred edge stays distinguishable from an authored one (and removable on its own terms) |

### Incoming (Other → UserEntry)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `reports` | `REPORT_FOR` | EntryReport | Reports evaluating this entry — 1-to-many by design (an AI report and a teacher report can coexist; `ReportSource` discriminates) |

Ownership is the universal `(User)-[:OWNS]->(UserEntry)` edge, with the
`user_uid == :OWNS` owner invariant (ADR-086).

## Create Paths

`UserEntryService.create_entry()` persists via three mutually exclusive paths:

| Path | Condition | Backend call |
|------|-----------|--------------|
| **Turn-in** | `fulfills_exercise_uid` and no caller-supplied uid (the Submit page; a vault note's frozen copy) | `create_with_exercise_link` — writes the `FULFILLS_EXERCISE {revision}` edge atomically |
| **Living entry** | Caller-supplied deterministic uid (every vault note, from its first sync) | `upsert` — idempotent; re-syncing an edited vault file updates the same node in place. A draft: never `teacher_review`, never submitted or shared (R9) |
| **Plain create** | Neither | `create` |

Creation then auto-records an `Interaction` audit row (turn-ins only), wires an
optional `TRANSFORMS` edge for multi-stage pipelines, and — for every path but the
living entry — resolves audience through `UnifiedSharingService`:

- `pipeline=TEACHER_REVIEW` → a feedback request (`SUBMITTED_TO_GROUP`): `teacher:<group_uid>`
  targets, and `teachers` (the default when nothing is named) as the exercise's assigned groups
  the submitter belongs to (a curriculum exercise: the default group; no exercise: every group
  they study in). A request that would reach no teacher is **refused before the write**
  (ADR-054 §3: no silent no-audience turn-ins).
- every pipeline → `group:<uid>` / `user:<username>` are shares (`SHARED_WITH_GROUP` /
  `SHARES_WITH`); a feedback target on any other pipeline writes no link.

Audience is always **declared at submit time**, in the one vocabulary (`AudienceSpec`,
`core/models/user_entry/audience.py` — ADR-088): the Submit page's (`/submissions/submit`) `audience` field, the JSON
body's `audience`, and the vault's `audience:` all parse through it. There is no implicit
student→teacher sharing inferred from a `FULFILLS_EXERCISE` traversal plus a role check.

⚠️ **A share is not a feedback request.** The review queue in
`adapters/persistence/neo4j/_user_entry_assessment_mixin.py` matches **only**
`SUBMITTED_TO_GROUP` edges (ADR-088 §2). `AudienceResolver.validate()` therefore refuses a
`TEACHER_REVIEW` request whose explicit audience names no teacher (`group:` alone, `user:`
alone, `public`, `private`) with guidance naming `teacher:<group_uid>`; `[teachers, group:<uid>]`
— submit and share — is valid. `group:<uid>` is always a share.

**Every target is validated before the first write** (`AudienceResolver.validate_references`):
a `user:` must be a co-member (R8 — an unknown and a non-co-member username get one not-found;
the owner's own username is refused), a `group:` / `teacher:` must exist, be active and be one
the owner belongs to or owns, and `teachers` is expanded there. The post-persist writes
(`resolve_and_share`) re-check their own authorisation in the statement; a write refused after
validation compensates the node this call created. A living vault note (a caller-supplied uid)
is a draft and is never submitted or shared (R9): an audience naming anyone on a caller uid is
refused, and a `teacher_review` pipeline with one is too. The vault door hands a note's
`audience:` to the frozen copy `status: submitted` files — a fresh node stamped with
`submitted_from_uid` and a `submission_fingerprint` (`create_entry(..., copy_of=...)`), filed
once per authored snapshot.

`AudienceResolver` is deliberately a standalone helper rather than facade-private; the vault
door's request builder is pure (it parses, `create_entry` validates), so there is one place the
lookups run.

## Events/Publishing

Payloads below are the dataclass fields, minus the `occurred_at` every event inherits
from `BaseEvent`. (That is the *only* inherited field — `EventMetadata` is a standalone
opt-in dataclass, not a `BaseEvent` member, and none of these four carry one.)

| Event | Trigger |
|-------|---------|
| `UserEntryCreated` | Entry persisted; `submitted_group_uids` (the created `SUBMITTED_TO_GROUP` subset) rings the owning teachers' `submission_for_review` bell — a re-filed request rings nobody |
| `UserEntryProcessingStarted` | Pipeline dispatch begins |
| `UserEntryProcessingCompleted` | Pipeline finished |
| `UserEntryProcessingFailed` | Pipeline raised |

`LearningLoopEventHandlerService` subscribes fire-and-forget handlers that track
iteration counts, teacher feedback turnaround, and mastery velocity.

## Ingestion

The vault is the source of truth for user data. Two doors reach
`UserEntryService.create_entry()`, and they do **not** share a middle layer:

| Door | Path |
|------|------|
| The Submit page | `/submissions/submit` (the one route; `?exercise_uid=` names the exercise the turn-in answers). Its two-question form (feedback? / share with) HTMX-posts multipart to `POST /api/user-entries/upload`; the handler in `adapters/inbound/user_entry_api.py` builds the request and calls `create_entry()` **directly** |
| Vault / YAML sync | `UnifiedIngestionService` → `ingest_user_entry()` in `core/services/ingestion/user_entry_ingestion.py` (ADR-054) → `create_entry()` |

Neither uses the directory-ingest door that serves content-vault curriculum.
`create_entry()` is the one convergence point — which is why the audience,
exercise-link and `Interaction` rules live there rather than on either door.

`ensure_periodic_note()` covers the stored periodic-note kinds — the ladder of
nesting periods (daily → weekly → monthly → quarterly → yearly); the
membership vocabulary is the single `PERIODIC_NOTE_KINDS` frozenset on the
model, imported by every consumer.

## Routes

**UI** (`adapters/inbound/user_entry_ui.py`): `/submissions`,
`/submissions/submit`, `/submissions/journal`,
`/submissions/history` (+ `/submissions/history/list`, `POST /submissions/history/delete`),
`/submissions/knowledge`, `/submit/journals/{uid}/download`, `/gradebook`
(+ `/gradebook/lines`, `/gradebook/{uid}`), and `POST /api/entry-reports/respond`.

**API** (`adapters/inbound/user_entry_api.py`): `GET /api/user-entries` (list),
`POST /api/user-entries` (create), `POST /api/user-entries/upload`,
`POST /api/user-entries/form`, `POST /api/user-entries/process`,
`POST /api/user-entries/delete`, `POST /api/user-entries/grounding/remove`, and
`GET /api/user-entries/get`.

## Search

**Visibility:** `OWNER_ONLY` — derived from the config's
`user_ownership_relationship=OWNS`, not declared separately, so the two cannot
silently disagree. `SearchRouter.search()` **refuses an unscoped call**: without
a `user_uid` the visibility clause emits no ownership predicate, which would
return every user's entries.

UserEntry is additionally the one searchable domain **excluded from the cross-domain
sweep** — a personal-content domain should not surface in an "everything" query, so it
is filtered out of `faceted_search`'s eligible domains.

An **owner-scoped single-domain** request is supported and is the canonical UI path
(the `/search` dropdown): `faceted_search` refuses `user_entry` only when `user_uid` is
absent, and refuses loudly rather than falling through to the sweep and returning an
empty success to a misprogrammed caller.

| Config field | Value |
|--------------|-------|
| `search_fields` | `title`, `content`, `processed_content`, `original_filename` |
| `search_order_by` | `created_at` |
| `category_field` | `pipeline` |
| `entity_label` | `Entity` |

## Privacy

`private: true` frontmatter keeps a note out of every retrieval surface that
could quote it back: no entity embedding, no chunk subtree, and a hard `WHERE`
exclusion in companion-retrieval Cypher. It is orthogonal to `visibility`
(sharing) and to `je_use` (ingestion consent) — the owner's own surfaces
(`/gradebook`, search) still show private notes.

Journal *sessions* are never stored at all (ADR-073); periodic notes are the one
deliberate stored journal feature.

## History

UserEntry is the third name for this content. `JournalPure` was merged into
`Report` (February 2026) and the Journal domain was absorbed into the Reports
domain; ADR-054 then collapsed Reports' submission half — together with
`ExerciseSubmission`, `JeInput` and `JeOutput` — into UserEntry (April 2026,
`scripts/migrations/collapse_submissions_to_user_entry_2026_04.cypher`). The
legacy labels `ExerciseSubmission`, `JeInput` and `JeOutput` remain as read
aliases in the relationship registry's entity-type map.

## See Also

- [ADR-054: UserEntry Unified Submissions](../decisions/ADR-054-user-entry-unified-submissions.md)
- [ADR-069: Extract-Activities Pipeline](../decisions/ADR-069-extract-activities-pipeline-and-entry-report.md)
- [ADR-073: Journals Zero Persistence](../decisions/ADR-073-journals-zero-persistence-vault-memory.md)
- [ADR-086: Universal OWNS](../decisions/ADR-086-universal-owns-and-attends-attendance.md)
- [Learning Loop](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
- [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md)
- [Sharing Patterns](../patterns/SHARING_PATTERNS.md)
