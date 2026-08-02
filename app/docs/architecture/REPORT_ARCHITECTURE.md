---
title: Report Architecture
updated: 2026-06-13
status: current
category: architecture
version: 3.2.0
tags:
- report
- activity_report
- entry_report
- activity_domains
- submissions
- exercise
related:
- LEARNING_LOOP_ARCHITECTURE.md
- ADR-038-content-sharing-model.md
- ADR-040-teacher-exercise-workflow.md
related_skills:
- learning-loop
---
# Report Architecture

> "The student submits, the system responds, the teacher refines."

SKUEL's report system is a unified response infrastructure covering three distinct entry points:

1. **Curriculum work** — a student submits against an Exercise; teacher or AI responds (`EntryReport`, shared with the student).
2. **Activity Domains** — a user's Tasks, Goals, Habits, Events, Choices, and Principles; AI or admin responds (`ActivityReport`).
3. **Journal reflections** (ADR-069) — a user requests an LLM reflective response to their own journal-chain entry; produces a **PRIVATE, self-owned** `EntryReport` (`ReportSource.LLM`, `author_uid=null`, no `SHARES_WITH` grant, no entry status transition). See `EntryReportService.generate_entry_response`.

All paths produce report entities. The `EntityType`, `ReportSource`, and `visibility` fields discriminate them.

---
## Related Skills

For implementation guidance, see:
- [@learning-loop](../../.claude/skills/learning-loop/SKILL.md)


## The EntityTypes

| EntityType | Who Creates | Purpose | Discriminator |
|------------|-------------|---------|---------------|
| `USER_ENTRY` | Student uploads file / fills form | Raw student work (audio, text, images, structured form) — the curriculum turn-in | `pipeline` (e.g. `teacher_review`) |
| `ENTRY_REPORT` | Teacher **or** AI | Assessment with `subject_uid` pointing to a submission | `processor_type`: `HUMAN` (teacher) or `LLM` (AI) |
| `ACTIVITY_REPORT` | System **or** Admin | Activity-level feedback (not tied to artifact) | `processor_type`: `AUTOMATIC`, `LLM`, or `HUMAN` |

There is **no** `EXERCISE_SUBMISSION` EntityType — ADR-054 collapsed it (with `JE_INPUT` / `JE_OUTPUT`) into the single `USER_ENTRY` type, discriminated by its `pipeline` field rather than by entity_type.

**Hierarchy:**
- `UserEntry` extends `UserOwnedEntity` — file/processing fields
- `EntryReport` extends `UserOwnedEntity` — report fields only (no file/processing fields, unlike `UserEntry`)
- `ActivityReport` extends `UserOwnedEntity` directly — no file fields, responds to aggregate activity patterns

**Note:** Journaling is a `Pipeline` (`TRANSCRIBE_AND_STRUCTURE`), not a separate domain — the former `JE_INPUT` / `JE_OUTPUT` types were collapsed into `USER_ENTRY` alongside `EXERCISE_SUBMISSION` (ADR-054). See [ENTITY_TYPE_ARCHITECTURE.md](ENTITY_TYPE_ARCHITECTURE.md).

**Deleted EntityTypes / aliases:** `EXERCISE_SUBMISSION`, `JE_INPUT`, and `JE_OUTPUT` are gone from `EntityType`; their legacy string values still *parse* via `from_string()` but redirect to `USER_ENTRY` (not to any standalone type). The old `SUBMISSION_REPORT` / `JOURNAL_SUBMISSION` strings are not in the alias map, so `from_string()` returns `None` for them — assessment now produces an `ENTRY_REPORT`.

> **Canonical discriminator — match the `:UserEntry` label, not `entity_type`.** The write path guarantees `entity_type = 'user_entry'` (leaf default on `UserEntryDTO`/`UserEntry`; a mismatch raises — G6) and the migration relabelled every historical node `:UserEntry` with `entity_type = 'user_entry'`. A curriculum turn-in is identified by the `:UserEntry` label plus either its `pipeline` (`teacher_review`) or a `FULFILLS_EXERCISE` edge — **never** by a distinct entity_type. Read queries for turn-ins (teacher review, assessment, ZPD submission scores, cross-domain, group counts, learning-loop chains) now match `(:Entity:UserEntry)` accordingly; `user_context_queries.py` is migration-aware (counts `entity_type = 'user_entry'` by `pipeline`). The two remaining `entity_type = 'exercise_submission'` / `'je_input'` filters — journal-processing context (`_user_entry_content_mixin.py`) and ZPD journal-engagement (`zpd_backend.py`) — are journal-semantics sites pending a separate decision on journal-entry identity (ADR-054 dropped journal→KU extraction). This doc never depicts a `:UserEntry {entity_type: 'exercise_submission'}` node.

---

## Naming Rationale

**SUBMISSION** (not "assignment") because:
- "Assignment" is what a **teacher gives** — that's an `Exercise` with `scope=ASSIGNED`
- "Submission" is what a **student uploads** — file content going through a processing pipeline
- Backed by the unified content service `UserEntryService` (ADR-054 consolidation; backend port `UserEntryOperations`) — a turned-in `UserEntry` *is* the submission
- Matches route language: `/submit` (UI), `/api/submissions/*` (HTMX preview endpoints)

---

## The Exercise (Curriculum Directive)

An `Exercise` is the teacher's directive — instructions for what students should produce.

```
Exercise (scope=ASSIGNED)
    |
    +-- instructions: str                # What to do (LLM prompt for AI feedback)
    +-- due_date: date                   # When it's due
    +-- group_uid: str                   # Which class
    +-- model: str                       # Which LLM to use for AI feedback
    +-- expected_modality: SubmissionModality  # FILE_UPLOAD or STRUCTURED_FORM
    +-- form_schema: tuple[dict, ...] | None  # Inline form definition (sets STRUCTURED_FORM)
```

**Two scopes:**
- `PERSONAL` — User's own AI template for self-directed feedback
- `ASSIGNED` — Teacher-created directive targeting a Group

**Two modalities** (typed by `SubmissionModality` enum):
- `FILE_UPLOAD` — student uploads a file; `expected_modality` auto-derived when `form_schema` is None
- `STRUCTURED_FORM` — student fills inline form; auto-derived when `form_schema` is present

---

## Curriculum Submission Pipeline

```
1. Teacher creates Exercise (scope=ASSIGNED, targets Group)
       |
       v
2. Student submits → UserEntryService.create_entry() (via /submit ingestion, ADR-054)
       |             Creates a :UserEntry node — status SUBMITTED for the
       |             teacher_review pipeline, else ACTIVE
       v
3. Processing is a separate, explicit step:
       POST /api/user-entries/process → UserEntryProcessingService.process()
       dispatches on entry.pipeline:
         TRANSCRIBE               → Deepgram audio → transcript
         LLM_SUMMARY              → LLM summarization
         TRANSCRIBE_AND_STRUCTURE → transcribe + LLM structuring (2nd UserEntry)
         EXTRACT_ACTIVITIES       → DSL parse → real entities (ADR-069)
         TEACHER_REVIEW / NONE    → no-op
       |
       v
4. Status: SUBMITTED/ACTIVE → COMPLETED (update_processed_content) or FAILED.
       |   No QUEUED/PROCESSING status is persisted; process() emits a
       |   UserEntryProcessingStarted event only.
       v
5. Auto-sharing (teacher_review + exercise link): FULFILLS_EXERCISE {revision}
       |   + SHARED_WITH_GROUP to the exercise's assigned groups (UnifiedSharingService)
       v
6. Teacher reviews via the group-based queue → writes ENTRY_REPORT
       |   submit_report:    SUBMITTED/ACTIVE   → COMPLETED          (Cypher guard)
       |   request_revision: SUBMITTED/ACTIVE   → REVISION_REQUESTED (Cypher guard)
       |   approve_report:   REVISION_REQUESTED → COMPLETED          (Cypher guard)
       v
7. Student sees the report, optionally resubmits — a resubmission is a new
       UserEntry (FULFILLS_EXERCISE / FULFILLS_REVISED_EXERCISE stamped with an
       incremented revision); there is no in-place reprocess
```

Each status guard is enforced atomically in Cypher via `WHERE status IN $allowed_from_statuses` — race-safe, no pre-fetch.

### Relationship Graph

```cypher
// The exercise directive
(teacher:User)-[:OWNS]->(exercise:Exercise {scope: "assigned"})
(exercise)-[:FOR_GROUP]->(group:Group)
(student:User)-[:MEMBER_OF]->(group)

// The submission (a UserEntry — entity_type is always 'user_entry', guaranteed by
// UserEntry.__post_init__; the `pipeline` field distinguishes a curriculum turn-in)
(student)-[:OWNS]->(submission:Entity:UserEntry {entity_type: "user_entry", pipeline: "teacher_review"})
(submission)-[:FULFILLS_EXERCISE]->(exercise)

// Teacher discovers entries via the group-based review queue (ADR-040):
// the entry is SHARED_WITH_GROUP to a Group the teacher OWNS, pipeline = 'teacher_review'
(submission)-[:SHARED_WITH_GROUP]->(group)

// Teacher report — student owns the report (access ownership); teacher is recorded via author_uid
(student)-[:OWNS]->(report:Entity {entity_type: "entry_report", author_uid: "teacher_uid"})
(report)-[:REPORT_FOR]->(submission)
```

---

## Two Entry Points, One Report Infrastructure

```
Curriculum Work                 Activity Domains
     │                               │
     ▼                               ▼
 USER_ENTRY                     (no artifact —
 (curriculum turn-in)            aggregate over
     │                            time window)
     │                               │
     └───────────┬───────────────────┘
                 │
                 ▼
           [REPORT]
            ├── ENTRY_REPORT    (response to exercise submission)
            └── ACTIVITY_REPORT    (response to activity patterns)
```

---

## Report EntityTypes

### 1. `ENTRY_REPORT` — Response to an Exercise Submission

`ENTRY_REPORT` is created in response to a **specific submitted artifact** (a turned-in `UserEntry` — `entity_type` `'user_entry'`).

| Field | Value |
|-------|-------|
| `entity_type` | `"entry_report"` |
| Inherits | `UserOwnedEntity` — NOT Submission |
| `subject_uid` | UID of the submission being evaluated — **graph-native**, projected from the `REPORT_FOR` edge on read (not stored as a node property) |
| `processor_type` | `HUMAN` or `LLM` |
| `assessment_outcome` | `APPROVED`, `NEEDS_REVISION`, or `AI_EVALUATED` (`AssessmentOutcome` enum) |

**Two sources — same entity type:**

| Source | Service | ReportSource | Trigger |
|--------|---------|---------------|---------|
| Teacher writes feedback | `AssessmentService.create_assessment()` | `HUMAN` | Teacher reviews submission in queue |
| AI evaluates via Exercise | `EntryReportService.generate_report()` | `LLM` | Exercise has `instructions`; AI generates response |

Both use atomic Cypher: create entity + `REPORT_FOR` + `SHARES_WITH` (to the submission owner) in one transaction. The typed read path (`EntryReportService.list_for_submission`) is the authoritative source for report content — there is no submission-side denormalization.

**Graph pattern:**
```cypher
// student always owns the report (access ownership)
(student:User)-[:OWNS]->(report:Entity:EntryReport {entity_type: 'entry_report'})
(report)-[:REPORT_FOR]->(submission:Entity:UserEntry {entity_type: 'user_entry'})
// report creation (create_report_node) matches the submission by uid only — no
// entity_type filter — so REPORT_FOR points at the :UserEntry node as written.
// for HUMAN reports, teacher identity is in report.author_uid (null for LLM reports)
```

---

### 2. `ACTIVITY_REPORT` — Response to Activity Patterns

`ACTIVITY_REPORT` is **not** a response to a specific artifact. It is a response to a user's aggregate activity over a time window.

| Field | Value |
|-------|-------|
| `entity_type` | `"activity_report"` |
| Inherits | `UserOwnedEntity` **directly** (no file fields) |
| `subject_uid` | UID of the user whose activity was reviewed |
| `processor_type` | `AUTOMATIC`, `LLM`, or `HUMAN` |

**`ActivityReport` has no `Submission` ancestry by design** — it has no file fields (`original_filename`, `file_path`, `file_size`). It is about a user over time, not a submitted artifact.

**Three sources — same entity type:**

| Source | Service | ReportSource | Trigger |
|--------|---------|---------------|---------|
| Scheduled system | `ProgressReportWorker` → `ProgressReportGenerator` | `AUTOMATIC` | `ProgressSchedule` cron |
| On-demand AI | `ProgressReportGenerator.generate()` | `LLM` | `POST /api/reports/progress/generate` |
| Admin writes feedback | `ActivityReportService.submit_report()` | `HUMAN` | Admin reviews snapshot |

**Graph pattern:**
```cypher
(owner:User)-[:OWNS]->(feedback:Entity:ActivityReport {
    entity_type: 'activity_report',
    subject_uid: 'user_student_uid',
    time_period: '7d',
    processor_type: 'human'  // or 'llm' or 'automatic'
})
```

**Key fields:**
```python
@dataclass(frozen=True)
class ActivityReport(UserOwnedEntity):
    processor_type: ReportSource | None = None
    subject_uid: str | None = None        # user whose activity was reviewed
    time_period: str | None = None        # "7d" | "14d" | "30d" | "90d"
    period_start: datetime | None = None
    period_end: datetime | None = None
    domains_covered: tuple[str, ...] = () # which activity domains
    depth: str | None = None              # "summary" | "standard" | "detailed"
    processed_content: str | None = None  # LLM output or human-written text (immutable)
    processing_error: str | None = None
    insights_referenced: tuple[str, ...] = ()
    # Annotation fields (user voice alongside AI synthesis)
    user_annotation: str | None = None    # Additive commentary alongside AI synthesis
    user_revision: str | None = None      # User-curated replacement for sharing
    annotation_mode: str | None = None    # "additive" | "revision" | None
    annotation_updated_at: datetime | None = None
```

---

## ReportSource Taxonomy

`ReportSource` discriminates the **source** of feedback, not the entity type:

| ReportSource | Who | Applies To |
|---------------|-----|-----------|
| `HUMAN` | Teacher writes | `ENTRY_REPORT` (teacher assessment) |
| `HUMAN` | Admin writes | `ACTIVITY_REPORT` (activity review) |
| `LLM` | AI via Exercise | `ENTRY_REPORT` (AI assessment of submission) |
| `LLM` | AI on demand | `ACTIVITY_REPORT` (activity summary with LLM insights) |
| `AUTOMATIC` | Scheduled system | `ACTIVITY_REPORT` (periodic progress report) |

---

## Visibility Model

Three-level visibility on every entity:

| Level | Who Can See | Use Case |
|-------|-------------|----------|
| `PRIVATE` (default) | Owner only | Work in progress |
| `SHARED` | Owner + SHARES_WITH recipients | Teacher review, peer feedback |
| `PUBLIC` | Anyone | Portfolio showcase |

Only `COMPLETED` entities can be shared (prevents sharing incomplete/failed work).

---

## Services

**Submission track:**

| Service | Protocol | Responsibility |
|---------|----------|---------------|
| `UserEntryService` | concrete facade (backend port `UserEntryOperations`) | UserEntry creation (`create_entry`), exercise linking, audience resolution |
| `UserEntryProcessingService` | `UserEntryProcessingOperations` | Pipeline dispatcher: reads `entry.pipeline`, routes to transcription / LLM processors |
| `UnifiedSharingService` | `SharingOperations` | Visibility control, SHARES_WITH + SHARED_WITH_GROUP management |
| `TeacherReviewService` | `TeacherReviewOperations` | Review queue, human feedback, revision requests, approval (delegates to `UserEntryBackend`, `EntryReportBackend`, `ExerciseBackend`, `GroupBackend`). Status transitions enforced atomically via Cypher `WHERE status IN $allowed_from_statuses` guards — race-safe, no pre-fetch needed. `request_revision_with_exercise()` creates EntryReport + RevisedExercise in a single Neo4j transaction (all-or-nothing). |

**Report producers:**

| Service | Protocol | Produces | Notes |
|---------|----------|---------|-------|
| `AssessmentService` | `AssessmentOperations` (service) | `EntryReport` (HUMAN) | Teacher assessment; verifies group membership. Own protocol since PR #128 (no longer bundled into `EntryReportOperations`) |
| `EntryReportService` | `EntryReportOperations` (service) + `EntryReportBackendOperations` (backend) | `EntryReport` (LLM) | AI evaluation via Exercise instructions (`UnifiedLLMCaller`). Also owns typed report reads: `list_for_submission` → `list[EntryReport]` (delegates to `EntryReportBackend`, which returns typed entities via `from_neo4j_node` — no TypedDict projection). Writes produce `:Entity:EntryReport` dual-labeled nodes; reads discriminate AI vs teacher via `EntryReport.processor_type` on the typed model |
| `ProgressReportGenerator` | `ProgressReportOperations` | `ACTIVITY_REPORT` (AUTOMATIC or LLM) | Activity summary; LLM adds qualitative insights |
| `ActivityReportService` | `ActivityReportOperations` | `ACTIVITY_REPORT` (HUMAN or via persist()) | Processor-neutral CRUD; all write paths converge here |
| `ReviewQueueService` | `ReviewQueueOperations` | `ReviewRequest` nodes | User-initiated review queue management |

**Graph intelligence (Level 1 — no LLM):**

| Service | Protocol | Responsibility |
|---------|----------|---------------|
| `ReportRelationshipService` | `ReportRelationshipOperations` | Pending submissions, report summary, learning loop chain traversal (delegates Cypher to `UserEntryBackend`) |

Methods: `get_pending_submissions()`, `get_unsubmitted_exercises()`, `get_report_summary()`, `get_learning_loop_chain(exercise_uid)`, `get_submission_chain(submission_uid)`. All 5 methods delegate to named `UserEntryBackend` methods (zero inline Cypher). Used by `UserContextIntelligenceFactory`.

**Protocols:** `core/ports/report_protocols.py`

---

## Where Reports Sit in the 4-Layer Architecture

The 4-phase learning loop is: **Exercise → UserEntry → EntryReport → RevisedExercise**. PathStep is the curriculum anchor, linked via `(PathStep)-[:HAS_EXERCISE]->(Exercise)`.

The first three stages are **leaf domains** — each owns its own Neo4j nodes and fits the standard 4-layer pattern:

```
*Operations protocol → *Backend subclass → *Service facade → sub-services

KuBackend               ← owns ORGANIZES, KU curriculum queries
ExerciseBackend         ← owns curriculum linking Cypher + teacher exercise stats
UserEntryBackend        ← owns UserEntry persistence + group-based teacher review queue Cypher
SharingBackend          ← owns SHARES_WITH / SHARED_WITH_GROUP access control (entity-agnostic, ADR-042)
GroupBackend            ← owns MEMBER_OF, teacher group stats
ActivityReportBackend   ← owns ActivityReport persistence + privacy audit queries
```

Reports split into two structurally different positions:

### ENTRY_REPORT — Leaf Domain

`ENTRY_REPORT` fits the leaf domain model. One submission goes in, one EntryReport node comes out. The generating services operate against a focused backend — the scope is a single artifact and its owner.

```
UserEntry  →  EntryReportService / AssessmentService  →  ENTRY_REPORT node
              (one artifact in, one report node out)
```

### ACTIVITY_REPORT — Cross-Domain Aggregator

`ACTIVITY_REPORT` cannot fit the leaf domain model — it reads **across all 6 Activity Domain backends** to produce a synthesis.

```
Tasks + Goals + Habits + Events + Choices + Principles
    ↓ (historical completions, time window)
 ProgressReportGenerator
    ↓ (LLM or programmatic markdown)
ACTIVITY_REPORT node
```

`ProgressReportGenerator` accepts a `UserContextBuilder` (primary data source). The primary data comes from `context_builder.build_rich(user_uid, window=...)` — MEGA_QUERY extended with six activity-window CALL{} blocks. Per SKUEL's architecture rule: **domain-specific Cypher belongs on the domain backend; cross-domain aggregation stays in services.** `ProgressReportGenerator` is the cross-domain aggregation service — it sits above the domain backends by design.

`ActivityReportBackend` owns the ActivityReport entity's persistence and privacy audit queries (get_history, annotate, get_annotation, get_admin_snapshots, get_shares_granted, get_report_schedule). `ProgressReportGenerator` is the cross-domain *aggregation* layer that builds report *content* — the backend handles *storage*. The `build_rich()` result (`context.entities_rich`, `context.knowledge_units_rich`, `context.enrolled_paths_rich`, `context.active_path_steps_rich`) gives the full cross-domain picture in a single Neo4j round-trip.

### Summary

| Report Mode | Structural Position | Why |
|-------------|--------------------|----|
| `ENTRY_REPORT` | Leaf domain — fits 4-layer pattern | One artifact in, one node out; single-domain scope |
| `ACTIVITY_REPORT` | Cross-domain aggregator + `ActivityReportBackend` | Content reads from 6 Activity Domain backends; persistence via `ActivityReportBackend` |

The learning loop does not end at a leaf domain — it fans back out across the user's entire lived activity. That is what makes `ACTIVITY_REPORT` architecturally distinct from the other three stages of the loop.

---

## UI Surfaces

**Curriculum track:**

| Route | Who | What |
|-------|-----|------|
| `/submissions/exercise` | Student | Upload files for processing (`/submit` → 302 here) |
| `/submissions/journal` | Student | Journal file-upload UX (Processing → Source → Browse → Process) |
| `/submissions/{uid}` | Owner | View submission, sharing controls |
| `/journals` | Any user | Chat-style journal entry point; `/submissions/journal` is the file-upload alternative |
| `/profile/shared` | Any user | "Shared With Me" inbox |
| `/api/teaching/review-queue` | Teacher | Pending submission review queue |
| `/api/teaching/review/{uid}/report` | Teacher | Submit human report on submission |
| `/api/teaching/review/{uid}/approve` | Teacher | Approve submission |

**Activity report track:**

| Route | Who | What |
|-------|-----|------|
| `/gradebook` | User | GradeBook "Activity reports" group — flat list, hidden when empty (arc 2 C1) |
| `/activity-reports/detail` (+`/content`) | User | Report detail with annotation UI |
| `/submit-activity-report` | User | On-demand report request form |
| `/reports/progress-list` | User | HTMX fragment (recent reports on the request form) |
| `/api/gradebook/activity-reports/preview` | Teacher | Gradebook report preview |
| `/activity-review` → `/activity-review/queue` | Admin | Pending review queue (`get_pending_reviews`) |
| `/activity-review/new` | Admin | Admin review form |
| `/activity-review/snapshot-fragment` | Admin | HTMX domain snapshot fragment |
| `POST /activity-review/submit-feedback` | Admin | Submit written activity feedback |

**Staged, no route yet (PLANNED tier, ADR-069 §3):** the user-side
"request a review" producer (`ReviewQueueService.request_review` — the admin
queue's missing input) and the privacy-transparency audit surface
(`ActivityReportService.get_privacy_summary`).

---

## Two Trigger Paths for Activity Review

### Admin-Initiated

```
Admin selects user + time window
        ↓
GET /api/activity-review/snapshot → ActivityReportService.create_snapshot(admin_uid=...)
        ↓  (calls context_builder.build_rich(user_uid, window=...) — MEGA_QUERY with activity window)
        ↓  emits ActivitySnapshotAccessed event → audit trail
Admin reads Tasks, Goals, Habits, Events, Choices, Principles summary
        ↓
Admin writes qualitative assessment
        ↓
POST /api/activity-review/submit → ActivityReportService.submit_report()
        ↓  (calls ActivityReportService.persist() — all writes converge here)
ActivityReport(ReportSource.HUMAN) created in Neo4j
```

### User-Initiated

```
User wants a review
        ↓
POST /api/activity-review/request → ReviewQueueService.request_review()
        ↓
ReviewRequest node created → appears in admin queue
        ↓
Admin views queue: GET /api/activity-review/queue → ReviewQueueService.get_pending_reviews()
        ↓
Admin follows admin-initiated path above
```

---

## LLM Report Generation (`ProgressReportGenerator`)

When `openai_service` is available, the generator:

1. Calls `context_builder.build_rich(user_uid, window=time_period)` — MEGA_QUERY extended with 6 activity window CALL{} blocks; `context.entities_rich` contains all domains (same method used by `ActivityReportService.create_snapshot()`)
2. Cross-references active Insights
3. Checks cooldown: if the user has generated a report within the last `ReportTimePeriod.MIN_REPORT_COOLDOWN_MINUTES` (60 min), returns a business error rather than calling the LLM (rate limit)
4. Fetches `user_annotation` from the most recent prior `ActivityReport` (`period_end < current_period_start`) via `_fetch_previous_annotation()`
5. Sends stats as JSON context to LLM via `activity_feedback.md` prompt template; if a prior annotation exists, appends it inside explicit injection-guard boundaries (`--- USER REFLECTION ... --- END USER REFLECTION ---`) with an instruction to treat it as user voice only — not instructions
6. LLM returns qualitative analysis with patterns, trends, recommendations
7. Creates `ActivityReport` with `processed_content = LLM output`, `metadata = raw stats`

**Graceful fallback:** If LLM call fails, falls back to programmatic markdown with `ReportSource.AUTOMATIC` and logs `processing_error`. If no prior annotation exists, the prompt is unchanged.

**Annotation feedback loop:** User annotations flow back into the next report's LLM prompt via `_fetch_previous_annotation()`. The field is also surfaced in `UserContext.latest_activity_report_user_annotation` for API consumers. (Its pre-ADR-082 keyword-triggered inclusion in Askesis's `build_llm_context()` was removed with the intent-selected dump.)

**Prompt template:** `core/prompts/templates/activity_feedback.md`

---

## API Routes

| Route | Method | Who | What |
|-------|--------|-----|------|
| `/api/activity-reports/annotate` | POST | User | Save annotation or revision to own report |
| `/api/activity-reports/annotation` | GET | User | Get current annotation state for a report |
| `/api/reports/progress/generate` | POST | User | On-demand `ACTIVITY_REPORT` generation |
| `/api/reports/progress` | GET | User | List user's `ACTIVITY_REPORT` history |
| `/api/reports/schedule` | POST | User | Create/update generation schedule |
| `/api/reports/schedule/get` | GET | User | Get user's schedule |
| `/api/reports/schedule/update` | POST | User | Update schedule |
| `/api/reports/schedule/delete` | POST | User | Deactivate schedule |
| `/api/activity-review/snapshot` | GET | Admin | Generate activity snapshot for review |
| `/api/activity-review/submit` | POST | Admin | Submit written activity feedback |
| `/api/activity-review/request` | POST | User | Request an activity review from admin |
| `/api/activity-review/queue` | GET | Admin | Pending review queue |
| `/api/activity-review/history` | GET | User/Admin | Received activity feedback history |
| `/api/exercises/report` | POST | Owner or Teacher (per-user FULL tier, ADR-043) | Generate LLM `ENTRY_REPORT` (`REPORT_FOR`) for a submission |
| `/api/reports/assessments` | POST | Teacher | Create teacher assessment (`ENTRY_REPORT`) |
| `/api/reports/assessments/for-student` | GET | Teacher | Student's received assessments |
| `/api/reports/assessments/by-teacher` | GET | Teacher | Teacher's authored assessments |
| `/api/teaching/review-queue` | GET | Teacher | Pending submission review queue |
| `/api/teaching/review/{uid}/report` | POST | Teacher | Submit human report on submission |
| `/api/teaching/review/{uid}/approve` | POST | Teacher | Approve submission |
| `/api/journals/batch-transcribe` | POST | Admin | Batch audio → txt (preview or run) — any server-side path |
| `/api/journals/folder-transcribe` | POST | Any user | Batch audio → txt from vault transcription dirs |

---

## Neo4j Schema

```cypher
// ENTRY_REPORT — tied to a specific submission
(:Entity:EntryReport {
    uid, entity_type: 'entry_report',
    user_uid,             // always the student (access ownership — who the report belongs to)
    author_uid,           // teacher UID for HUMAN reports; null for LLM/AI reports
    visibility: 'shared', // set at create so SHARES_WITH grants access via UnifiedSharingService
    processor_type,       // 'human' or 'llm'
    assessment_outcome,   // 'approved', 'needs_revision', or 'ai_evaluated'
    assessment_score,     // 0.0-1.0 for ASSESSMENT-scope exercises
    title,                // composed at creation: "{prefix} '{subject}'" — subject = fulfilled exercise's title, else the entry's; never a raw UID (feedback-loop UX arc C3)
    processed_content,    // LLM/teacher-generated feedback body (written by create_report_node as processed_content: $feedback)
    created_at, updated_at
})
// subject_uid is NOT stored as a node property — it is projected from the
// REPORT_FOR edge on read by EntryReportBackend.get / list_for_submission:
//   OPTIONAL MATCH (n)-[:REPORT_FOR]->(sub) RETURN n{.*, subject_uid: sub.uid}
(:Entity:EntryReport)-[:REPORT_FOR]->(:Entity:UserEntry {entity_type: 'user_entry'})
(:Entity:EntryReport)-[:SHARES_WITH]->(:User)  // submission owner — makes content visible to the student

// ACTIVITY_REPORT — tied to a user's activity patterns
(:Entity:ActivityReport {
    uid, entity_type: 'activity_report',
    user_uid,        // owner (admin or system)
    subject_uid,     // user whose activity was reviewed
    processor_type,  // 'human', 'llm', or 'automatic'
    time_period,     // '7d', '14d', '30d', '90d'
    period_start, period_end,
    domains_covered, // list
    depth,           // 'summary', 'standard', 'detailed'
    processed_content,     // immutable AI synthesis or human-written text
    processing_error,
    insights_referenced,
    user_annotation,       // additive commentary (annotation_mode='additive')
    user_revision,         // user-curated replacement (annotation_mode='revision')
    annotation_mode,       // 'additive' | 'revision' | null
    annotation_updated_at,
    created_at, updated_at
})
```

---

## Activity Track Data Flow

End-to-end data flow from user activity to feedback and back into UserContext:

```
User activity (Tasks, Goals, Habits, Events, Choices, Principles)
    │
    ▼
UserContextBuilder.build_rich(user_uid, window="7d")
    → Executes MEGA-QUERY (single Neo4j round-trip)
    → Returns UserContext with:
        context.entities_rich["tasks"|"goals"|"habits"|"events"|"choices"|"principles"]
        context.submission_stats (total counts, pending, unsubmitted exercises)
    │
    ▼
ProgressReportGenerator.generate(user_uid, time_period="7d")
    → Injects context_builder: UserContextBuilder
    → Calls build_rich() for cross-domain snapshot
    → Checks cooldown (ReportTimePeriod.MIN_REPORT_COOLDOWN_MINUTES)
    → Fetches prior annotation via _fetch_previous_annotation()
    → Sends to LLM via activity_feedback.md prompt template
    → Fallback: programmatic markdown with ReportSource.AUTOMATIC
    │
    ▼
ActivityReportService.persist(report: ActivityReport)
    → All write paths converge here (LLM, AUTOMATIC, HUMAN)
    → Creates ActivityReport node in Neo4j with OWNS relationship
    │
    ▼
Next build_rich() call picks up the latest report:
    context.latest_activity_report_uid
    context.latest_activity_report_content
    context.latest_activity_report_user_annotation
    │
    ▼
User annotates report (additive or revision mode)
    → Annotation included in next LLM prompt via injection-guard boundaries
    → Feedback loop closes: activity → report → annotation → next report
```

**Key constraint:** `ProgressReportGenerator` is a cross-domain aggregator — it sits above domain backends by design. `ActivityReportBackend` handles entity persistence and privacy audit queries; `ProgressReportGenerator` handles cross-domain content aggregation. The `build_rich()` result provides the full cross-domain picture in a single query.

---

## Test Coverage

| Service | Test File | Tests | Coverage |
|---------|-----------|-------|----------|
| `TeacherReviewService` | `tests/unit/services/test_teacher_review_service.py` | 60 | 76% |
| `UserEntryService` | `tests/unit/services/test_user_entry_service.py` | 41 | 69% |
| `AssessmentService` | `tests/unit/test_assessment_service.py` | 8 | 88% |

---

## See Also

- [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md) — Entry-point overview: two tracks, four phases, how MEGA_QUERY feeds the loop
- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Exercise Workflow](/docs/decisions/ADR-040-teacher-exercise-workflow.md)
- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [Sharing Patterns](/docs/patterns/SHARING_PATTERNS.md)
