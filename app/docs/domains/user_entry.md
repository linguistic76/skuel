---
title: UserEntry Domain
created: 2026-09-01
updated: 2026-09-01
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
| `TRANSCRIBE_AND_STRUCTURE` | Audio → transcribed entry → LLM-structured second entry (legacy; preserved for existing nodes) |
| `LLM_SUMMARY` | Text/file → LLM summary |
| `EXTRACT_ACTIVITIES` | Text → DSL parse → real entities with `EXTRACTED_FROM` provenance (ADR-069) |
| `TEACHER_REVIEW` | No processing; the entry waits in the teacher queue via `SHARED_WITH_GROUP` |
| `JOURNAL` | Journals-domain entry; processing driven by `JournalTier`. Always private |
| `KNOWLEDGE` | Grounded knowledge entry — the `je_pro` channel |
| `REFERENCE` | Reserved; no producer today (ADR-073 §4) |

`modality` (`SubmissionModality`: `FILE_UPLOAD` / `STRUCTURED_FORM`) is designed as
**orthogonal** to `pipeline` — how the entry was created, rather than what happens to it.

⚠️ **Staged, not live.** No production path assigns it: both `UserEntryCreateRequest`
constructors in `adapters/inbound/user_entry_api.py` omit `modality`, and the only
`SubmissionModality` producers in the tree set `Exercise.expected_modality`. Every
persisted entry therefore carries the `None` default, so the field cannot be read to
learn how an entry was created until a writer exists.

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
| Assessment reads | `/core/services/user_entry/assessment_service.py` |
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
| `modality` | `SubmissionModality?` | How the entry was created — **always `None` today**, see above |
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

### `revision_number` is not a field

Revision lives on the `FULFILLS_EXERCISE {revision}` **edge**, not the node. A
second attempt against the same exercise creates a new `UserEntry` with a new
edge carrying `revision=2`.

### Intent vs. turn-in

`fulfills_exercise_uid` is the exercise the author declares they are working
against (`fulfills_exercise_uid:` frontmatter on a vault file, or the create
request). It is **intent, not the turn-in**: the turn-in truth stays on the
`FULFILLS_EXERCISE` edge, which only frozen submission copies carry. A living
vault entry has the property and never the edge; removing the frontmatter line
removes the property on the next sync. This mirrors the
`Exercise.path_step_uid` membership-property precedent.

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
| **Turn-in** | `fulfills_exercise_uid` and no caller-supplied uid | `create_with_exercise_link` — writes the `FULFILLS_EXERCISE {revision}` edge atomically |
| **Living entry** | Caller-supplied deterministic uid | `upsert` — idempotent; re-syncing an edited vault file updates the same node in place |
| **Plain create** | Neither | `create` |

Creation then auto-records an `Interaction` audit row (turn-ins only), wires an
optional `TRANSFORMS` edge for multi-stage pipelines, and resolves audience
through `UnifiedSharingService`:

- `pipeline=TEACHER_REVIEW` + exercise link + no explicit audience → auto-share
  to the exercise's assigned groups
- `pipeline=TEACHER_REVIEW` + no audience + no exercise → **validation error**
  (ADR-054 §3: no silent no-audience turn-ins)
- otherwise → honour explicit `share_with_groups` / `share_with_users`

Audience is always **declared at submit time**. There is no implicit
student→teacher sharing inferred from a `FULFILLS_EXERCISE` traversal plus a
role check.

`AudienceResolver` is deliberately a standalone helper rather than facade-private:
the `/upload` ingestion path reuses the same validation without going through
the facade.

## Events/Publishing

Payloads below are the dataclass fields, minus the `occurred_at` / `metadata`
every event carries.

| Event | Trigger |
|-------|---------|
| `UserEntryCreated` | Entry persisted |
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
| The `/submit` form | HTMX-posts multipart to `POST /api/user-entries/upload`; the handler in `adapters/inbound/user_entry_api.py` builds the request and calls `create_entry()` **directly** |
| Vault / YAML sync | `UnifiedIngestionService` → `ingest_user_entry()` in `core/services/ingestion/user_entry_ingestion.py` (ADR-054) → `create_entry()` |

Neither uses the directory-ingest door that serves content-vault curriculum.
`create_entry()` is the one convergence point — which is why the audience,
exercise-link and `Interaction` rules live there rather than on either door.

`ensure_periodic_note()` covers the three stored periodic-note kinds; the
membership vocabulary is the single `PERIODIC_NOTE_KINDS` frozenset on the
model, imported by every consumer.

## Routes

**UI** (`adapters/inbound/user_entry_ui.py`): `/submissions`,
`/submissions/exercise`, `/submit`, `/submissions/journal`,
`/submissions/history` (+ `/list`, `/delete`), `/submissions/knowledge`,
`/submit/journals/{uid}/download`, `/gradebook` (+ `/lines`, `/{uid}`), and
`POST /api/entry-reports/respond`.

**API** (`adapters/inbound/user_entry_api.py`): `POST|GET /api/user-entries`,
`POST /api/user-entries/upload`, `/form`, `/process`, `/delete`,
`/grounding/remove`, and `GET /api/user-entries/get`.

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
- [Learning Loop](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md)
- [Search Architecture](/docs/architecture/SEARCH_ARCHITECTURE.md)
- [Sharing Patterns](/docs/patterns/SHARING_PATTERNS.md)
